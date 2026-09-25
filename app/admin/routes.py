"""Chassis admin shell routes — server-rendered USWDS pages (chassis v0.7).

Mirrors the app/frontend.py pattern (Jinja2 + USWDS, cookie/Bearer auth via
optional_current_user, redirect-to-login when unauthenticated). Reuses the
shared `templates` instance and `_common_context` so the header/nav render
consistently.

Authorization model:
  - The whole shell requires admin rights. The seeded `user` role holds
    `users:read`/`orgs:read`, so a read-permission gate would let any user
    in; we therefore gate user-management on `users:write` (only the `admin`
    role — chassis-wide OR per-org — has it).
  - Org Management is platform-admin only (is_superuser or chassis-wide
    `admin` role), per the chassis admin spec.

Data scoping:
  - Platform admins see ALL users; org admins see only their current org's
    members. Org Management is hidden from org-only admins.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.admin.docs_service import get_doc, list_docs, load_doc_html
from app.admin.health_service import gather_system_health
from app.admin.reports_service import gather_report
from app.admin.service import (
    AdminError,
    create_user,
    is_platform_admin,
    list_all_orgs,
    list_all_users,
    list_org_member_users,
    set_user_active,
)
from app.auth.models import User
from app.auth.service import EmailAlreadyRegistered
from app.compliance.fisma_audit import service as fisma_audit_service
from app.compliance.inventory import service as platform_health_service
from app.db import SessionDep, set_current_org_id
from app.frontend import _common_context, optional_current_user, templates
from app.llm import service as llm_service
from app.mcp import service as mcp_service
from app.orgs.service import SlugTaken, create_org
from app.rbac.permissions import CorePermissions
from app.rbac.service import is_privileged_user, user_has_permission

admin_router = APIRouter(prefix="/admin", tags=["admin"], include_in_schema=False)

_VALID_ROLES = {"user", "admin"}


async def _resolve(
    request: Request,
    session: SessionDep,
    *,
    require_platform: bool,
    permission: str = CorePermissions.USERS_WRITE,
) -> tuple[User | None, bool, int | None, Response | None]:
    """Resolve + authorize the requesting admin.

    Returns (user, is_platform, org_id, early_response). When early_response
    is not None the caller MUST return it immediately (redirect to login or a
    403 page).
    """
    user = await optional_current_user(request, session)
    if user is None:
        return None, False, None, RedirectResponse(
            "/auth/login", status_code=status.HTTP_303_SEE_OTHER
        )

    platform = await is_platform_admin(session, user)

    # Best-effort bind the user's default org so per-org permission grants
    # are visible to user_has_permission. Never 400 an orgless platform admin.
    from app.orgs.service import get_default_org_for_user

    org = await get_default_org_for_user(session, user)
    org_id = org.id if org is not None else None
    if org_id is not None:
        set_current_org_id(org_id)

    if require_platform:
        authorized = platform
    else:
        authorized = await user_has_permission(session, user, permission)

    # IA-2(1) (chassis-program v1.0.0, FISMA Moderate): a privileged
    # (admin-class) account must have MFA enrolled to use the admin shell
    # at all — even a superuser/platform-admin who technically holds every
    # permission is blocked here until they enroll. Checked after the
    # ordinary permission check so a non-privileged user without the
    # permission still gets the plain 403 forbidden page, not an
    # MFA-specific one.
    if authorized and await is_privileged_user(session, user) and not user.mfa_enabled:
        authorized = False

    if not authorized:
        ctx = _common_context(request, user)
        return (
            None,
            platform,
            org_id,
            templates.TemplateResponse(
                request, "admin/forbidden.html", ctx, status_code=status.HTTP_403_FORBIDDEN
            ),
        )
    return user, platform, org_id, None


def _ctx(request: Request, user: User, platform: bool, **extra: Any) -> dict[str, Any]:
    ctx = _common_context(request, user)
    ctx["is_platform_admin"] = platform
    ctx.update(extra)
    return ctx


# ─── Dashboard ────────────────────────────────────────────────────────────


@admin_router.get("", response_class=HTMLResponse)
async def admin_dashboard(request: Request, session: SessionDep) -> Response:
    user, platform, org_id, early = await _resolve(
        request, session, require_platform=False
    )
    if early is not None:
        return early
    assert user is not None
    return templates.TemplateResponse(request, "admin/dashboard.html", _ctx(request, user, platform))


# ─── User Management ────────────────────────────────────────────────────────


@admin_router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, session: SessionDep) -> Response:
    user, platform, org_id, early = await _resolve(
        request, session, require_platform=False
    )
    if early is not None:
        return early
    assert user is not None

    if platform:
        users = await list_all_users(session)
    elif org_id is not None:
        users = await list_org_member_users(session, org_id)
    else:
        users = []
    return templates.TemplateResponse(
        request,
        "admin/users.html",
        _ctx(request, user, platform, users=users, current_user_id=user.id),
    )


@admin_router.post("/users", response_class=HTMLResponse)
async def users_create(
    request: Request,
    session: SessionDep,
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(""),
    role: str = Form("user"),
) -> Response:
    user, platform, org_id, early = await _resolve(
        request, session, require_platform=False
    )
    if early is not None:
        return early
    assert user is not None

    role_name = role if role in _VALID_ROLES else "user"
    # Platform admins create chassis-wide users (org_id=None); org admins add
    # the new user to their own org with the chosen per-org role.
    target_org = None if platform else org_id

    try:
        await create_user(
            session,
            email=email,
            password=password,
            full_name=full_name or None,
            role_name=role_name,
            org_id=target_org,
        )
        await session.commit()
    except EmailAlreadyRegistered:
        return await _users_with_flash(
            request, session, user, platform, org_id,
            kind="error", message=f"A user with email {email} already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )
    except AdminError as exc:
        return await _users_with_flash(
            request, session, user, platform, org_id,
            kind="error", message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse("/admin/users", status_code=status.HTTP_303_SEE_OTHER)


@admin_router.post("/users/{user_id}/deactivate", response_class=HTMLResponse)
async def users_deactivate(
    request: Request, session: SessionDep, user_id: int
) -> Response:
    return await _toggle_active(request, session, user_id, active=False)


@admin_router.post("/users/{user_id}/reactivate", response_class=HTMLResponse)
async def users_reactivate(
    request: Request, session: SessionDep, user_id: int
) -> Response:
    return await _toggle_active(request, session, user_id, active=True)


async def _toggle_active(
    request: Request, session: SessionDep, user_id: int, *, active: bool
) -> Response:
    user, platform, org_id, early = await _resolve(
        request, session, require_platform=False
    )
    if early is not None:
        return early
    assert user is not None

    if user_id == user.id and not active:
        return await _users_with_flash(
            request, session, user, platform, org_id,
            kind="error", message="You can't deactivate your own account.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        await set_user_active(
            session, user_id, active, platform=platform, org_id=org_id
        )
        await session.commit()
    except AdminError as exc:
        return await _users_with_flash(
            request, session, user, platform, org_id,
            kind="error", message=str(exc),
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return RedirectResponse("/admin/users", status_code=status.HTTP_303_SEE_OTHER)


async def _users_with_flash(
    request: Request,
    session: SessionDep,
    user: User,
    platform: bool,
    org_id: int | None,
    *,
    kind: str,
    message: str,
    status_code: int,
) -> Response:
    """Re-render the users list with a flash banner (error path)."""
    if platform:
        users = await list_all_users(session)
    elif org_id is not None:
        users = await list_org_member_users(session, org_id)
    else:
        users = []
    ctx = _ctx(request, user, platform, users=users, current_user_id=user.id)
    ctx["flash"] = {"kind": kind, "message": message}
    return templates.TemplateResponse(request, "admin/users.html", ctx, status_code=status_code)


# ─── Org Management (platform admins only) ──────────────────────────────────


@admin_router.get("/orgs", response_class=HTMLResponse)
async def orgs_page(request: Request, session: SessionDep) -> Response:
    user, platform, org_id, early = await _resolve(
        request, session, require_platform=True
    )
    if early is not None:
        return early
    assert user is not None
    orgs = await list_all_orgs(session)
    return templates.TemplateResponse(
        request, "admin/orgs.html", _ctx(request, user, platform, orgs=orgs)
    )


@admin_router.post("/orgs", response_class=HTMLResponse)
async def orgs_create(
    request: Request,
    session: SessionDep,
    name: str = Form(...),
    slug: str = Form(...),
) -> Response:
    user, platform, org_id, early = await _resolve(
        request, session, require_platform=True
    )
    if early is not None:
        return early
    assert user is not None

    try:
        await create_org(session, user, name=name, slug=slug)
        await session.commit()
    except SlugTaken:
        orgs = await list_all_orgs(session)
        ctx = _ctx(request, user, platform, orgs=orgs)
        ctx["flash"] = {"kind": "error", "message": f"Slug '{slug}' is already taken."}
        return templates.TemplateResponse(
            request, "admin/orgs.html", ctx, status_code=status.HTTP_409_CONFLICT
        )
    return RedirectResponse("/admin/orgs", status_code=status.HTTP_303_SEE_OTHER)


# ─── System Health (platform admins only) ───────────────────────────────────


@admin_router.get("/system-health", response_class=HTMLResponse)
async def system_health_page(request: Request, session: SessionDep) -> Response:
    user, platform, org_id, early = await _resolve(
        request, session, require_platform=True
    )
    if early is not None:
        return early
    assert user is not None
    health = await gather_system_health(session)
    return templates.TemplateResponse(
        request, "admin/system-health.html", _ctx(request, user, platform, health=health)
    )


# ─── Reporting (any admin; scope follows the admin) ─────────────────────────


@admin_router.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request, session: SessionDep) -> Response:
    user, platform, org_id, early = await _resolve(
        request, session, require_platform=False
    )
    if early is not None:
        return early
    assert user is not None
    report = await gather_report(session, org_id=org_id, platform=platform)
    return templates.TemplateResponse(
        request, "admin/reports.html", _ctx(request, user, platform, report=report)
    )


# ─── Documentation (any admin) ──────────────────────────────────────────────


@admin_router.get("/docs", response_class=HTMLResponse)
async def docs_index(request: Request, session: SessionDep) -> Response:
    user, platform, org_id, early = await _resolve(
        request, session, require_platform=False
    )
    if early is not None:
        return early
    assert user is not None
    return templates.TemplateResponse(
        request, "admin/docs.html", _ctx(request, user, platform, docs=list_docs())
    )


@admin_router.get("/docs/{slug}", response_class=HTMLResponse)
async def docs_view(request: Request, session: SessionDep, slug: str) -> Response:
    user, platform, org_id, early = await _resolve(
        request, session, require_platform=False
    )
    if early is not None:
        return early
    assert user is not None

    entry = get_doc(slug)
    if entry is None:
        ctx = _ctx(request, user, platform, docs=list_docs())
        ctx["flash"] = {"kind": "error", "message": "That document does not exist."}
        return templates.TemplateResponse(
            request, "admin/docs.html", ctx, status_code=status.HTTP_404_NOT_FOUND
        )

    try:
        doc_html = load_doc_html(entry)
    except (FileNotFoundError, OSError):
        doc_html = ""
    return templates.TemplateResponse(
        request, "admin/doc.html", _ctx(request, user, platform, doc=entry, doc_html=doc_html)
    )


# ─── LLM Provider Keys (admin; shared keys + access policy are platform-only) ─


async def _build_llm_ctx(
    request: Request,
    session: SessionDep,
    user: User,
    platform: bool,
    org_id: int | None,
) -> dict[str, Any]:
    """Assemble the system context for the LLM keys page.

    - org admins see their org's keys.
    - platform admins additionally see shared keys + the per-org
      shared-access policy table.
    """
    org_keys = (
        await llm_service.list_keys(session, org_id=org_id, include_shared=False)
        if org_id is not None
        else []
    )
    shared_keys = []
    org_access = []
    if platform:
        shared_keys = await llm_service.list_keys(
            session, org_id=None, include_shared=True
        )
        access_map = await llm_service.list_org_access(session)
        for org in await list_all_orgs(session):
            org_access.append(
                {
                    "id": org.id,
                    "name": org.name,
                    "slug": org.slug,
                    "allow_shared_key": access_map.get(org.id, False),
                }
            )
    return _ctx(
        request,
        user,
        platform,
        org_id=org_id,
        org_keys=org_keys,
        shared_keys=shared_keys,
        org_access=org_access,
    )


@admin_router.get("/llm", response_class=HTMLResponse)
async def llm_page(request: Request, session: SessionDep) -> Response:
    user, platform, org_id, early = await _resolve(
        request, session, require_platform=False, permission=CorePermissions.LLM_WRITE
    )
    if early is not None:
        return early
    assert user is not None
    ctx = await _build_llm_ctx(request, session, user, platform, org_id)
    return templates.TemplateResponse(request, "admin/llm.html", ctx)


@admin_router.post("/llm/keys", response_class=HTMLResponse)
async def llm_key_create(
    request: Request,
    session: SessionDep,
    provider: str = Form(...),
    api_key: str = Form(...),
    scope: str = Form("org"),
) -> Response:
    user, platform, org_id, early = await _resolve(
        request, session, require_platform=False, permission=CorePermissions.LLM_WRITE
    )
    if early is not None:
        return early
    assert user is not None

    async def _flash(kind: str, message: str, code: int) -> Response:
        ctx = await _build_llm_ctx(request, session, user, platform, org_id)
        ctx["flash"] = {"kind": kind, "message": message}
        return templates.TemplateResponse(request, "admin/llm.html", ctx, status_code=code)

    # Only platform admins may set the platform-shared key.
    target_org: int | None
    if scope == "shared":
        if not platform:
            return await _flash(
                "error", "Only platform admins can set the shared key.", 403
            )
        target_org = None
    else:
        if org_id is None:
            return await _flash(
                "error", "You must belong to an organization to add an org key.", 400
            )
        target_org = org_id

    try:
        await llm_service.set_key(
            session,
            provider=provider,
            plaintext=api_key,
            org_id=target_org,
            created_by_user_id=user.id,
        )
        await session.commit()
    except ValueError as exc:
        return await _flash("error", str(exc), 400)
    return RedirectResponse("/admin/llm", status_code=status.HTTP_303_SEE_OTHER)


@admin_router.post("/llm/keys/{key_id}/deactivate", response_class=HTMLResponse)
async def llm_key_deactivate(
    request: Request, session: SessionDep, key_id: int
) -> Response:
    user, platform, org_id, early = await _resolve(
        request, session, require_platform=False, permission=CorePermissions.LLM_WRITE
    )
    if early is not None:
        return early
    assert user is not None

    key = await llm_service.get_key(session, key_id)
    # Authorization: org admins may only touch their own org's keys; shared
    # keys are platform-only.
    allowed = key is not None and (
        platform or (key.organization_id is not None and key.organization_id == org_id)
    )
    if not allowed:
        ctx = await _build_llm_ctx(request, session, user, platform, org_id)
        ctx["flash"] = {"kind": "error", "message": "You can't modify that key."}
        return templates.TemplateResponse(
            request, "admin/llm.html", ctx, status_code=status.HTTP_403_FORBIDDEN
        )
    await llm_service.deactivate_key(session, key)
    await session.commit()
    return RedirectResponse("/admin/llm", status_code=status.HTTP_303_SEE_OTHER)


@admin_router.post("/llm/access", response_class=HTMLResponse)
async def llm_access_set(
    request: Request,
    session: SessionDep,
    org_id_target: int = Form(...),
    allow: str = Form(""),
) -> Response:
    # Per-org shared-access policy is a platform-admin action.
    user, platform, org_id, early = await _resolve(
        request, session, require_platform=True
    )
    if early is not None:
        return early
    assert user is not None
    await llm_service.set_org_shared_access(
        session, org_id=org_id_target, allow=(allow == "on")
    )
    await session.commit()
    return RedirectResponse("/admin/llm", status_code=status.HTTP_303_SEE_OTHER)


# ─── MCP Server Connections (FR-MCPCLIENT; org-admin-scoped, client only) ──


@admin_router.get("/mcp", response_class=HTMLResponse)
async def mcp_page(request: Request, session: SessionDep) -> Response:
    user, platform, org_id, early = await _resolve(
        request, session, require_platform=False, permission=CorePermissions.MCP_WRITE
    )
    if early is not None:
        return early
    assert user is not None
    connections = (
        await mcp_service.list_connections(session, org_id=org_id)
        if org_id is not None
        else []
    )
    return templates.TemplateResponse(
        request,
        "admin/mcp.html",
        _ctx(request, user, platform, org_id=org_id, connections=connections),
    )


@admin_router.post("/mcp/servers", response_class=HTMLResponse)
async def mcp_server_create(
    request: Request,
    session: SessionDep,
    name: str = Form(...),
    url: str = Form(...),
    credential: str = Form(""),
) -> Response:
    user, platform, org_id, early = await _resolve(
        request, session, require_platform=False, permission=CorePermissions.MCP_WRITE
    )
    if early is not None:
        return early
    assert user is not None

    async def _flash(kind: str, message: str, code: int) -> Response:
        connections = (
            await mcp_service.list_connections(session, org_id=org_id)
            if org_id is not None
            else []
        )
        ctx = _ctx(request, user, platform, org_id=org_id, connections=connections)
        ctx["flash"] = {"kind": kind, "message": message}
        return templates.TemplateResponse(request, "admin/mcp.html", ctx, status_code=code)

    if org_id is None:
        return await _flash(
            "error",
            "You must belong to an organization to register an MCP server.",
            status.HTTP_400_BAD_REQUEST,
        )

    try:
        await mcp_service.create_connection(
            session,
            org_id=org_id,
            name=name,
            url=url,
            credential=credential or None,
            created_by_user_id=user.id,
        )
        await session.commit()
    except ValueError as exc:
        return await _flash("error", str(exc), status.HTTP_400_BAD_REQUEST)
    return RedirectResponse("/admin/mcp", status_code=status.HTTP_303_SEE_OTHER)


async def _mcp_own_connection_or_flash(
    request: Request,
    session: SessionDep,
    user: User,
    platform: bool,
    org_id: int | None,
    connection_id: int,
) -> tuple[Any, Response | None]:
    """Resolve `connection_id` scoped to `org_id`. Returns (connection, None)
    on success, or (None, 403-flash-response) if it doesn't exist in this
    org (FR-MCPCLIENT-8 — never another org's connection, even by id)."""
    connection = (
        await mcp_service.get_connection(session, org_id=org_id, connection_id=connection_id)
        if org_id is not None
        else None
    )
    if connection is not None:
        return connection, None
    connections = (
        await mcp_service.list_connections(session, org_id=org_id) if org_id is not None else []
    )
    ctx = _ctx(request, user, platform, org_id=org_id, connections=connections)
    ctx["flash"] = {"kind": "error", "message": "You can't modify that connection."}
    return None, templates.TemplateResponse(
        request, "admin/mcp.html", ctx, status_code=status.HTTP_403_FORBIDDEN
    )


@admin_router.post("/mcp/servers/{connection_id}/enable", response_class=HTMLResponse)
async def mcp_server_enable(
    request: Request, session: SessionDep, connection_id: int
) -> Response:
    return await _mcp_toggle(request, session, connection_id, enabled=True)


@admin_router.post("/mcp/servers/{connection_id}/disable", response_class=HTMLResponse)
async def mcp_server_disable(
    request: Request, session: SessionDep, connection_id: int
) -> Response:
    return await _mcp_toggle(request, session, connection_id, enabled=False)


async def _mcp_toggle(
    request: Request, session: SessionDep, connection_id: int, *, enabled: bool
) -> Response:
    user, platform, org_id, early = await _resolve(
        request, session, require_platform=False, permission=CorePermissions.MCP_WRITE
    )
    if early is not None:
        return early
    assert user is not None

    connection, early_403 = await _mcp_own_connection_or_flash(
        request, session, user, platform, org_id, connection_id
    )
    if early_403 is not None:
        return early_403
    if enabled:
        await mcp_service.enable_connection(session, connection)
    else:
        await mcp_service.disable_connection(session, connection)
    await session.commit()
    return RedirectResponse("/admin/mcp", status_code=status.HTTP_303_SEE_OTHER)


@admin_router.post("/mcp/servers/{connection_id}/delete", response_class=HTMLResponse)
async def mcp_server_delete(
    request: Request, session: SessionDep, connection_id: int
) -> Response:
    user, platform, org_id, early = await _resolve(
        request, session, require_platform=False, permission=CorePermissions.MCP_WRITE
    )
    if early is not None:
        return early
    assert user is not None

    connection, early_403 = await _mcp_own_connection_or_flash(
        request, session, user, platform, org_id, connection_id
    )
    if early_403 is not None:
        return early_403
    await mcp_service.delete_connection(session, connection)
    await session.commit()
    return RedirectResponse("/admin/mcp", status_code=status.HTTP_303_SEE_OTHER)


# ─── Platform Health (chassis-program FR-PLATHEALTH) ───────────────────────


@admin_router.get("/platform-health", response_class=HTMLResponse)
async def platform_health_page(request: Request, session: SessionDep) -> Response:
    user, platform, org_id, early = await _resolve(
        request,
        session,
        require_platform=True,
        permission=CorePermissions.PLATFORM_HEALTH_READ,
    )
    if early is not None:
        return early
    assert user is not None
    latest = await platform_health_service.get_latest_scan(session)
    latest_successful = await platform_health_service.get_latest_successful_scan(session)
    history = await platform_health_service.list_scan_history(session)
    findings = (
        await platform_health_service.list_findings(session, latest_successful.id)
        if latest_successful is not None
        else []
    )
    inventory = (
        await platform_health_service.list_inventory(session, latest_successful.id)
        if latest_successful is not None
        else []
    )
    remediations = await platform_health_service.list_remediations(session)
    return templates.TemplateResponse(
        request,
        "admin/platform-health.html",
        _ctx(
            request,
            user,
            platform,
            latest=latest,
            latest_successful=latest_successful,
            is_stale=(latest is not None and latest.id != (latest_successful.id if latest_successful else None)),
            history=history,
            findings=findings,
            inventory=inventory,
            remediations=remediations,
        ),
    )


@admin_router.post("/platform-health/scan", response_class=HTMLResponse)
async def platform_health_trigger_scan(request: Request, session: SessionDep) -> Response:
    user, platform, org_id, early = await _resolve(
        request,
        session,
        require_platform=True,
        permission=CorePermissions.PLATFORM_HEALTH_WRITE,
    )
    if early is not None:
        return early
    assert user is not None
    await platform_health_service.run_scan(session, triggered_by_user_id=user.id)
    await session.commit()
    return RedirectResponse("/admin/platform-health", status_code=status.HTTP_303_SEE_OTHER)


@admin_router.post(
    "/platform-health/remediations/{proposal_id}/decide", response_class=HTMLResponse
)
async def platform_health_decide_remediation(
    request: Request,
    session: SessionDep,
    proposal_id: int,
    decision: str = Form(...),
) -> Response:
    user, platform, org_id, early = await _resolve(
        request,
        session,
        require_platform=True,
        permission=CorePermissions.PLATFORM_HEALTH_WRITE,
    )
    if early is not None:
        return early
    assert user is not None
    from app.compliance.inventory.models import RemediationProposal

    proposal = await session.get(RemediationProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await platform_health_service.decide_remediation(
        session, proposal=proposal, decision=decision, user_id=user.id
    )
    await session.commit()
    return RedirectResponse("/admin/platform-health", status_code=status.HTTP_303_SEE_OTHER)


# ─── FISMA Controls Self-Audit + Report (chassis-program FR-FISMAAUDIT) ─────


@admin_router.get("/fisma-audit", response_class=HTMLResponse)
async def fisma_audit_page(request: Request, session: SessionDep) -> Response:
    user, platform, org_id, early = await _resolve(
        request,
        session,
        require_platform=True,
        permission=CorePermissions.FISMA_AUDIT_READ,
    )
    if early is not None:
        return early
    assert user is not None
    latest = await fisma_audit_service.get_latest_report(session)
    history = await fisma_audit_service.list_report_history(session)
    return templates.TemplateResponse(
        request,
        "admin/fisma-audit.html",
        _ctx(request, user, platform, latest=latest, history=history),
    )


@admin_router.post("/fisma-audit/run", response_class=HTMLResponse)
async def fisma_audit_run(request: Request, session: SessionDep) -> Response:
    user, platform, org_id, early = await _resolve(
        request,
        session,
        require_platform=True,
        permission=CorePermissions.FISMA_AUDIT_READ,
    )
    if early is not None:
        return early
    assert user is not None
    await fisma_audit_service.run_audit(session, triggered_by_user_id=user.id)
    await session.commit()
    return RedirectResponse("/admin/fisma-audit", status_code=status.HTTP_303_SEE_OTHER)


# ─── CHASSIS-EXTENSION-POINT: admin-pages ───────────────────────────────────
# Slots MAY register additional admin pages on `admin_router` here (e.g. a
# domain-specific settings page). Keep them gated via the same `_resolve(...)`
# helper so the RBAC model stays uniform. One route block per slot page.
# ─────────────────────────────────────────────────────────────────────────
