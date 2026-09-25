"""Greeting slot routes — DESIGN.md §7 API Contracts, §7A UI.

CurrentOrg is required on every route here (binds org_id for the chassis
TenantScoped auto-filter — see app/slots/example/routes.py's note).

TASK-APP-003 + TASK-APP-004 + TASK-UI-001 all produce this one file,
chained by explicit dependency exactly as the draft TASKS.md states.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse

from app.db import SessionDep
from app.deps import CurrentOrg, CurrentUser, requires
from app.error_messages import message_for_status
from app.frontend import _common_context, templates
from app.logging import get_logger
from app.slots.greeting import GREETINGS_HISTORY_READ, GREETINGS_WRITE
from app.slots.greeting.providers.translation import SUPPORTED_LOCALES
from app.slots.greeting.schemas import (
    ErrorCode,
    GreetingHistoryEntry,
    GreetingHistoryResponse,
    GreetingRequest,
    GreetingResponse,
)
from app.slots.greeting.service import GreetingRateLimited, greet, history

log = get_logger("slots.greeting")

router = APIRouter(prefix="/api/greetings", tags=["greetings"])

_MAX_NAME_LENGTH = 100


def _validation_error(message: str) -> HTTPException:
    """400 with the NFR-004 closed-set error_code body."""
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"error_code": ErrorCode.VALIDATION_FAILED.value, "message": message},
    )


@router.post(
    "",
    response_model=GreetingResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(requires(GREETINGS_WRITE))],
)
async def create_greeting(
    payload: GreetingRequest,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> GreetingResponse:
    """FR-001, FR-002, FR-003. org_id and actor come from the session —
    never from the request body (BR-001)."""
    name = payload.name.strip()
    if not name or len(name) > _MAX_NAME_LENGTH:
        raise _validation_error(
            f"name must be 1-{_MAX_NAME_LENGTH} characters after trimming whitespace"
        )

    try:
        event, greeting_text, tools_used = await greet(
            session,
            actor_user_id=user.id,
            org_id=org.id,
            name=name,
            locale=payload.locale,
            use_llm=payload.use_llm,
        )
    except GreetingRateLimited as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error_code": ErrorCode.RATE_LIMITED.value,
                "message": message_for_status(429),
            },
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    return GreetingResponse(
        greeting=greeting_text,
        locale=event.locale_used,
        locale_fallback=event.locale_fallback,
        translation_source=event.translation_source,  # type: ignore[arg-type]
        tools_used=list(tools_used),
    )


@router.get(
    "/history",
    response_model=GreetingHistoryResponse,
    dependencies=[Depends(requires(GREETINGS_HISTORY_READ))],
)
async def read_history(
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    locale: Annotated[str | None, Query()] = None,
) -> GreetingHistoryResponse:
    """FR-004, FR-005. Requires the `greetings:history:read` permission
    (granted to the admin role only — a non-admin gets 403 from
    `requires()` before this body ever runs) PLUS an explicit MFA
    assertion below (DESIGN.md §5A requires BOTH; the chassis's built-in
    MFA mandate in `requires()` is scoped to platform-wide privileged
    accounts only — see app/rbac/service.py:is_privileged_user — so a
    per-org admin's MFA state is asserted here, not by the chassis gate).
    """
    if not user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": ErrorCode.AUTHORIZATION_FAILED.value,
                "message": message_for_status(403),
            },
        )

    if locale is not None and locale not in SUPPORTED_LOCALES:
        raise _validation_error(f"locale must be one of: {', '.join(sorted(SUPPORTED_LOCALES))}")

    rows, total = await history(session, page_number=page, locale=locale)
    return GreetingHistoryResponse(
        entries=[GreetingHistoryEntry.model_validate(r) for r in rows],
        page=page,
        total=total,
    )


# ────────────────────────────────────────────────────────────────────────
# UI page — TASK-UI-001
# ────────────────────────────────────────────────────────────────────────

page_router = APIRouter(tags=["greetings-ui"])


@page_router.get("/greet", response_class=HTMLResponse)
async def greeting_page(request: Request, user: CurrentUser, org: CurrentOrg) -> HTMLResponse:
    """Server-rendered greeting form (FR-001/002, NFR-003). No business
    logic here — the form posts to the JSON API above via fetch()."""
    # CP-B.8 fix (Chassis Program, 2026-09-02): this handler built its own
    # ad hoc context dict ({"user", "org", "supported_locales"}) instead of
    # reusing _common_context() like every other page in this chassis. Every
    # other key base.html reads (settings, current_user, app_name, form_data,
    # errors, flash) was simply absent, so the page 500'd the instant a real
    # request rendered it -- base.html's nav unconditionally reads
    # `settings.is_gov_app`. Found live via CP-B.8's real Playwright E2E pass
    # (a template that only ever got exercised by unit tests calling the
    # service layer directly never hit this). Reuse the shared helper and
    # layer the greeting-specific keys on top, matching the pattern every
    # other HTML route in this chassis already follows.
    ctx = _common_context(request, user)
    ctx["org"] = org
    ctx["supported_locales"] = sorted(SUPPORTED_LOCALES)
    return templates.TemplateResponse(request, "greeting/greeting.html", ctx)
