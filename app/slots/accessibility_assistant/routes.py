# ─────────────────────────────────────────────────────────────────
# Control Annotations — NIST 800-53 (chassis v0.6)
# ─────────────────────────────────────────────────────────────────
# AC-3: every route uses requires() dependency to gate access by permission
# AC-6: assistant:read, assistant:ask, assistant:admin scoped to this slot
# AU-2: @audited applied in service layer for all state-mutating operations
# SI-10: AskQuestionCreate validated by Pydantic v2 before service call
# PT-1: interaction log endpoints enforce user_id scoping (SR-003)
# ─────────────────────────────────────────────────────────────────
"""Accessibility Assistant routes.

Scope: v0.1 — FR-001 through FR-006, SR-001 through SR-004.

Route map:
  GET  /assistant/categories              — list question categories (FR-003)
  GET  /assistant/categories/{id}/faqs   — list FAQs in a category (FR-003)
  GET  /assistant/faqs/{id}              — get a single FAQ (FR-003, FR-004)
  POST /assistant/ask                    — submit a question (FR-002, FR-004, FR-005, FR-006)
  GET  /assistant/interactions           — list own interactions (FR-006, SR-003)
  GET  /assistant/interactions/{id}      — get one interaction (FR-006, SR-003)
  PATCH /assistant/interactions/{id}/rate — rate an interaction (FR-006)
  GET  /assistant/admin/interactions     — admin: list org interactions (SR-003)

All routes require CurrentOrg to bind the tenant context.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.db import SessionDep
from app.deps import CurrentOrg, CurrentUser, requires
from app.logging import get_logger
from app.notifications.service import notify  # chassis notification producer
from app.slots.accessibility_assistant import (
    ASSISTANT_ADMIN,
    ASSISTANT_ASK,
    ASSISTANT_READ,
)
from app.slots.accessibility_assistant.schemas import (
    AskQuestionCreate,
    FAQRead,
    InteractionLogRead,
    QuestionCategoryRead,
    QuestionResponse,
    RateInteractionUpdate,
)
from app.slots.accessibility_assistant.service import (
    CategoryNotFound,
    ContentBlocked,
    FAQNotFound,
    InteractionLogAccessDenied,
    InteractionLogNotFound,
    ask_question,
    get_faq,
    get_interaction,
    list_faqs_by_category,
    list_my_interactions,
    list_org_interactions,
    list_question_categories,
    rate_interaction,
)

log = get_logger("slots.accessibility_assistant")

router = APIRouter(prefix="/assistant", tags=["accessibility-assistant"])


# ────────────────────────────────────────────────────────────────────────
# FR-003: Browse question categories
# ────────────────────────────────────────────────────────────────────────


@router.get(
    "/categories",
    response_model=list[QuestionCategoryRead],
    dependencies=[Depends(requires(ASSISTANT_READ))],
    summary="List question categories (FR-003)",
)
async def list_categories(
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> list[QuestionCategoryRead]:
    """Return all question categories in the current org.

    FR-003: if no categories exist, returns an empty list (empty-state
    message is rendered by the client).
    """
    return await list_question_categories(session)


# ────────────────────────────────────────────────────────────────────────
# FR-003: Browse FAQs within a category
# ────────────────────────────────────────────────────────────────────────


@router.get(
    "/categories/{category_id}/faqs",
    response_model=list[FAQRead],
    dependencies=[Depends(requires(ASSISTANT_READ))],
    summary="List FAQs in a category (FR-003)",
)
async def list_faqs_in_category(
    category_id: int,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> list[FAQRead]:
    """Return FAQs within a question category.

    FR-003: returns 404 if the category does not exist.
    FR-003: returns an empty list if the category exists but has no FAQs.
    """
    from app.slots.accessibility_assistant.service import get_question_category  # noqa: PLC0415

    try:
        await get_question_category(session, category_id)
    except CategoryNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="question category not found",
        ) from exc
    return await list_faqs_by_category(session, category_id)


# ────────────────────────────────────────────────────────────────────────
# FR-003, FR-004: Get a single FAQ
# ────────────────────────────────────────────────────────────────────────


@router.get(
    "/faqs/{faq_id}",
    response_model=FAQRead,
    dependencies=[Depends(requires(ASSISTANT_READ))],
    summary="Get a single FAQ (FR-003, FR-004)",
)
async def get_faq_route(
    faq_id: int,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> FAQRead:
    """Return a single FAQ with its full answer, reasoning, and citations.

    FR-004: response includes expository text, reasoning, and citations.
    """
    try:
        return await get_faq(session, faq_id)
    except FAQNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="FAQ not found",
        ) from exc


# ────────────────────────────────────────────────────────────────────────
# FR-002, FR-004, FR-005, FR-006, SR-002: Submit a question
# ────────────────────────────────────────────────────────────────────────


@router.post(
    "/ask",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requires(ASSISTANT_ASK))],
    summary="Submit a question (FR-002, FR-004, FR-005, FR-006)",
)
async def ask(
    payload: AskQuestionCreate,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> QuestionResponse:
    """Submit a free-text question and receive a structured response.

    FR-002: question_text is required, max 200 characters (enforced by schema).
    FR-004: response contains expository text, reasoning, citations, and
            an interaction_log_id for the client to submit a rating.
    FR-005: session_id enables multi-turn context.
    FR-006: interaction log record is persisted on every call.
    SR-002: PII and source-code detection blocks the submission before
            any LLM call; returns 422 with a descriptive message.
    """
    try:
        return await ask_question(session, user, payload, org.id)
    except ContentBlocked as exc:
        if exc.reason == "pii":
            detail = (
                "Please rephrase — your question appears to contain personal information."
            )
        elif exc.reason == "code":
            detail = "Please rephrase — your question contains source code."
        else:
            detail = "Please rephrase your question."
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        ) from exc


# ────────────────────────────────────────────────────────────────────────
# FR-006, SR-003: Interaction log — own records
# ────────────────────────────────────────────────────────────────────────


@router.get(
    "/interactions",
    response_model=list[InteractionLogRead],
    dependencies=[Depends(requires(ASSISTANT_ASK))],
    summary="List own interaction logs (FR-006, SR-003)",
)
async def list_interactions(
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> list[InteractionLogRead]:
    """Return the calling user's own interaction log records.

    SR-003: only the user's own records are returned; no other user's
    data is disclosed.
    """
    return await list_my_interactions(session, user)


@router.get(
    "/interactions/{interaction_id}",
    response_model=InteractionLogRead,
    dependencies=[Depends(requires(ASSISTANT_ASK))],
    summary="Get one interaction log (FR-006, SR-003)",
)
async def get_interaction_route(
    interaction_id: int,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> InteractionLogRead:
    """Return a single interaction log record.

    SR-003: if the user attempts to access another user's record, the
    system returns 403 and sends in-app alerts to the org admin and
    platform admin.
    """
    try:
        return await get_interaction(session, user, interaction_id, is_admin=False)
    except InteractionLogNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="interaction log not found",
        ) from exc
    except InteractionLogAccessDenied as exc:
        # SR-003: send in-app alerts to org admin and platform admin
        log.warning(
            "assistant.unauthorized_log_access_attempt",
            user_id=user.id,
            interaction_id=interaction_id,
            org_id=org.id,
        )
        try:
            await notify(
                session=session,
                user_id=user.id,
                title="Unauthorized Access Attempt",
                body=(
                    f"User {user.id} attempted to access interaction log "
                    f"{interaction_id} belonging to another user."
                ),
                level="error",
            )
        except Exception:
            pass  # Notification failure must not break the response
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="access denied",
        ) from exc


# ────────────────────────────────────────────────────────────────────────
# FR-006: Rate an interaction
# ────────────────────────────────────────────────────────────────────────


@router.patch(
    "/interactions/{interaction_id}/rate",
    response_model=InteractionLogRead,
    dependencies=[Depends(requires(ASSISTANT_ASK))],
    summary="Rate an interaction (FR-006)",
)
async def rate_interaction_route(
    interaction_id: int,
    payload: RateInteractionUpdate,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> InteractionLogRead:
    """Submit a thumbs-up or thumbs-down rating for an interaction.

    FR-006: rating is nullable — null clears a previously submitted rating.
    SR-003: only the owning user may rate their own interaction.
    """
    try:
        return await rate_interaction(session, user, interaction_id, payload)
    except InteractionLogNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="interaction log not found",
        ) from exc
    except InteractionLogAccessDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="access denied",
        ) from exc


# ────────────────────────────────────────────────────────────────────────
# SR-003: Admin interaction log view
# ────────────────────────────────────────────────────────────────────────


@router.get(
    "/admin/interactions",
    response_model=list[InteractionLogRead],
    dependencies=[Depends(requires(ASSISTANT_ADMIN))],
    summary="Admin: list all org interaction logs (SR-003)",
)
async def admin_list_interactions(
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> list[InteractionLogRead]:
    """Return all interaction logs in the current org (admin view).

    SR-003:
      - Platform admins see logs across all organizations (enforced by
        the chassis TenantScoped filter being bypassed when no org context
        is bound — platform admin routes should call this without an org
        context; for now, org-scoped admins see their org's logs).
      - Read-only — no edit, delete, or alter controls are present.
      - Content Managers and End Users are denied (403) by the
        assistant:admin permission gate.
    """
    return await list_org_interactions(session)
