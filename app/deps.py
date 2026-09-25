"""Shared FastAPI dependencies.

Routes pull `current_user` here. Slot code (under `app/slots/`) imports the
same dependency — it's the canonical handshake between chassis-owned auth
and slot-owned business logic.

Slots NEVER reach into `app.auth.service` directly. They use `current_user`
+ `requires(...)` exclusively.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status

from app.auth.models import User
from app.auth.service import AuthError, decode_token, get_user_by_id
from app.db import SessionDep, set_current_org_id
from app.deps_context import set_current_user_id

# K.8 — centralized user-facing error strings.
from app.error_messages import (
    ERR_BAD_REQUEST,
    ERR_FORBIDDEN,
    ERR_UNAUTHENTICATED,
)
from app.orgs.models import Organization
from app.orgs.service import get_default_org_for_user
from app.rbac.service import is_privileged_user, user_has_permission

# Canonical chassis cookie name. Slots and downstream tooling can rely on this constant.
ACCESS_TOKEN_COOKIE = "chassis_access_token"


async def get_current_user(
    request: Request,
    session: SessionDep,
    cookie_token: Annotated[str | None, Cookie(alias=ACCESS_TOKEN_COOKIE)] = None,
) -> User:
    """Resolve the authenticated user.

    Two valid token sources, checked in order:
      1. `Authorization: Bearer <token>` header (programmatic clients, CLIs)
      2. HTTP-only cookie `chassis_access_token` (browsers)

    Returns 401 on missing/invalid/expired token, or 401 on inactive user.
    Slot code can rely on this returning an ACTIVE user — no extra check needed.
    """
    token = _extract_bearer_token(request) or cookie_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_UNAUTHENTICATED,
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(token)
    except AuthError as exc:
        # K.8 — surface the canonical 401 to the user; bind the
        # auth-specific reason on structlog contextvars for triage.
        # (Slot code that needs to differentiate token-expired vs
        # token-invalid SHOULD inspect the auth_failure log line, not
        # the user-facing string.)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_UNAUTHENTICATED,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await get_user_by_id(session, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERR_UNAUTHENTICATED,
        )
    # Bind user id to the shared context var so audit + slot code can
    # read it without re-injecting the user object.
    set_current_user_id(user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def _extract_bearer_token(request: Request) -> str | None:
    """Pull the JWT from the Authorization header, if present and well-formed."""
    auth = request.headers.get("Authorization")
    if not auth:
        return None
    parts = auth.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


async def get_current_org(
    user: CurrentUser, session: SessionDep
) -> Organization:
    """Resolve the user's active org and bind its id to the tenant-context var.

    Once bound, every subsequent ORM SELECT against `TenantScoped` tables
    filters by `WHERE org_id = X` and every INSERT auto-populates `org_id`.
    Slot code never has to remember either.

    Raises 400 if the user has no orgs — slot routes that need an org
    context MUST require this dependency; routes that work without one
    (org listing, account settings, etc.) MUST NOT.
    """
    org = await get_default_org_for_user(session, user)
    if org is None:
        # K.8 — user-facing canonical 400; the orgless-user remediation
        # path lives in the API docs / onboarding flow, not in the error
        # detail string.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERR_BAD_REQUEST,
        )
    set_current_org_id(org.id)
    return org


CurrentOrg = Annotated[Organization, Depends(get_current_org)]


def requires(permission: str) -> Callable[..., object]:
    """Dependency factory: org-scoped permission gate.

    Returns a Depends-able callable that:
      1. Resolves CurrentUser (auth).
      2. Resolves CurrentOrg — this is essential because `user_has_permission`
         consults per-org grants via `memberships.role_id`, which requires
         current_org_id_var to be bound. If `requires()` did NOT depend on
         CurrentOrg, FastAPI would resolve dependencies in declaration order,
         and `dependencies=[Depends(requires(...))]` listed in the decorator
         would run BEFORE the route's own CurrentOrg parameter resolves,
         giving the chassis-wide check no per-org context to consult.
      3. Calls `user_has_permission` and raises 403 with the missing
         permission name on failure.

    Slot routes can use it via `dependencies=[Depends(requires("foo:bar"))]`
    on the decorator OR as a `_: Annotated[User, Depends(requires("..."))]`
    parameter when they want the gate's return value (the User).

    Chassis-owned routes that DON'T have org context (e.g. /auth/me) MUST
    NOT use this dep — by design it 400s if the user has no orgs. Add a
    sibling `requires_chassis_only(permission)` if a v1.x chassis route
    needs RBAC without an org context.
    """

    async def _check(
        user: CurrentUser,
        org: CurrentOrg,
        session: SessionDep,
    ) -> User:
        # `org` parameter is intentionally unused in the body — its sole
        # role is to force the dep graph to resolve get_current_org first,
        # which binds current_org_id_var so user_has_permission can read it.
        del org

        if not await user_has_permission(session, user, permission):
            # K.8 — canonical 403 to the user; the specific missing
            # permission is bound to the structlog log line on the
            # failing request for operator triage.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ERR_FORBIDDEN,
            )

        # IA-2(1) (chassis-program v1.0.0, FISMA Moderate): MFA is
        # mandatory for privileged (admin-class) accounts. A privileged
        # user who hasn't completed MFA enrollment is blocked from every
        # permission-gated action — not just admin-only ones — so there is
        # no route that lets an un-enrolled admin account operate normally.
        # This is deliberately checked AFTER the ordinary permission check
        # (a non-privileged user without the permission still gets a plain
        # 403, not a confusing MFA message) and BEFORE returning the user
        # (nothing downstream ever sees a privileged-but-unenrolled caller
        # as authorized).
        if await is_privileged_user(session, user) and not user.mfa_enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ERR_FORBIDDEN,
            )
        return user

    return _check
