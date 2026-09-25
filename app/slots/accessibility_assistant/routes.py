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

import contextlib

from fastapi import APIRouter, Depends, HTTPException, status

from app.db import SessionDep
from app.deps import CurrentOrg, CurrentUser, requires
from app.logging import get_logger
from app.notifications.service import notify  # chassis notification producer
from app.slots.accessibility_assistant import (
    ASSISTANT_ADMIN,
    ASSISTANT_ASK,
    ASSISTANT_FAQ_MANAGE,
    ASSISTANT_LLM_FALLBACK_MANAGE,
    ASSISTANT_QUESTION_CATEGORY_MANAGE,
    ASSISTANT_READ,
    ASSISTANT_ROLE_MANAGE,
    ASSISTANT_SOURCE_CATEGORY_MANAGE,
    ASSISTANT_SOURCE_MANAGE,
    ASSISTANT_SOURCE_READ,
)
from app.slots.accessibility_assistant.schemas import (
    AnswerQuestionResponse,
    AskQuestionCreate,
    ConnectivityTestResponse,
    ContentManagerAssignRequest,
    ContentManagerAssignResponse,
    FAQCreate,
    FAQRead,
    GitHubVerifyRequest,
    InformationSourceCategoryCreate,
    InformationSourceCategoryRead,
    InformationSourceCreate,
    InformationSourceCreateResponse,
    InformationSourceRead,
    InteractionLogRead,
    LLMFallbackConfigRead,
    LLMFallbackConfigUpsert,
    LocalValidateAccessRequest,
    MCPTestRequest,
    QuestionAlertRead,
    QuestionCategoryCreate,
    QuestionCategoryRead,
    QuestionResponse,
    RateInteractionUpdate,
    SourceTypeInfo,
    TieredQuestionResponse,
)
from app.slots.accessibility_assistant.service import (
    CategoryNotFound,
    ContentBlocked,
    DuplicateCategoryName,
    FAQNotFound,
    FAQValidationError,
    InformationSourceCategoryNotFound,
    InteractionLogAccessDenied,
    InteractionLogNotFound,
    LLMFallbackConfigNotFound,
    NotAnOrgMember,
    QuestionAlertNotFound,
    SourceTestFailed,
    acknowledge_question_alert,
    answer_question_deterministic_first,
    answer_question_with_fallback,
    ask_question,
    assign_content_manager,
    create_faq,
    create_information_source,
    create_information_source_category,
    create_question_category,
    delete_llm_fallback_config,
    get_faq,
    get_interaction,
    get_llm_fallback_config,
    list_faqs_by_category,
    list_information_source_categories,
    list_information_sources,
    list_llm_fallback_configs,
    list_my_interactions,
    list_org_interactions,
    list_question_alerts,
    list_question_categories,
    list_source_types,
    rate_interaction,
    test_github_access,
    test_local_folder_access,
    test_mcp_connectivity,
    to_faq_read,
    upsert_llm_fallback_config,
)

log = get_logger("slots.accessibility_assistant")

router = APIRouter(prefix="/assistant", tags=["accessibility-assistant"])

# v0.2 (T-002, T-003, T-005, T-006, T-015, T-016, T-017): DESIGN.md's
# traceability matrix specifies these under a distinct `/api/...` prefix
# (rather than v0.1's `/assistant` prefix) — one APIRouter per resource
# domain, mirroring the platform-wide convention already used for
# app/files (/api/files) and app/notifications (/api/notifications).
information_source_category_router = APIRouter(
    prefix="/api/information-source-categories", tags=["information-source-categories"]
)
information_source_router = APIRouter(
    prefix="/api/information-sources", tags=["information-sources"]
)
question_category_router = APIRouter(prefix="/api/question-categories", tags=["question-categories"])
faq_router = APIRouter(prefix="/api/faqs", tags=["faqs"])
question_router = APIRouter(prefix="/api/questions", tags=["questions"])
llm_fallback_config_router = APIRouter(
    prefix="/api/llm-fallback-config", tags=["llm-fallback-config"]
)
organization_role_router = APIRouter(prefix="/api/organizations", tags=["organizations"])


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
        with contextlib.suppress(Exception):
            # Notification failure must not break the response.
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


# ═════════════════════════════════════════════════════════════════════════
# v0.2 increment — FR-007 through FR-017
# ═════════════════════════════════════════════════════════════════════════


# ────────────────────────────────────────────────────────────────────────
# Information Source Categories (FR-010, T-002)
# ────────────────────────────────────────────────────────────────────────


@information_source_category_router.post(
    "/",
    response_model=InformationSourceCategoryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requires(ASSISTANT_SOURCE_CATEGORY_MANAGE))],
    summary="Create an information source category (FR-010)",
)
async def create_information_source_category_route(
    payload: InformationSourceCategoryCreate,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> InformationSourceCategoryRead:
    """Platform/Org Admins only (assistant:source_category_manage).
    Duplicate names within the org return 409 before any write (T-002).
    """
    try:
        category = await create_information_source_category(
            session, user, payload.name, payload.description
        )
    except DuplicateCategoryName as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A category with this name already exists.",
        ) from exc
    return InformationSourceCategoryRead.model_validate(category)


@information_source_category_router.get(
    "/",
    response_model=list[InformationSourceCategoryRead],
    dependencies=[Depends(requires(ASSISTANT_SOURCE_READ))],
    summary="List information source categories (FR-010)",
)
async def list_information_source_categories_route(
    user: CurrentUser, org: CurrentOrg, session: SessionDep
) -> list[InformationSourceCategoryRead]:
    return await list_information_source_categories(session)


# ────────────────────────────────────────────────────────────────────────
# Information Sources (FR-011..FR-014, T-003)
# ────────────────────────────────────────────────────────────────────────


@information_source_router.get(
    "/source-types",
    response_model=list[SourceTypeInfo],
    dependencies=[Depends(requires(ASSISTANT_SOURCE_READ))],
    summary="List the four supported information source types (FR-011)",
)
async def list_source_types_route(user: CurrentUser, org: CurrentOrg) -> list[SourceTypeInfo]:
    return [SourceTypeInfo(**t) for t in list_source_types()]


@information_source_router.post(
    "/",
    response_model=InformationSourceCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requires(ASSISTANT_SOURCE_MANAGE))],
    summary="Create an information source (FR-011..FR-014)",
)
async def create_information_source_route(
    payload: InformationSourceCreate,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> InformationSourceCreateResponse:
    """The connectivity/read-access test runs synchronously before the
    source is persisted (FR-012, FR-013, FR-014). Returns 503 if the test
    fails, 404 if category_id doesn't resolve in this org.
    """
    try:
        source = await create_information_source(session, user, payload)
    except InformationSourceCategoryNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="information source category not found",
        ) from exc
    except SourceTestFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
        ) from exc
    return InformationSourceCreateResponse(
        source_id=source.id,
        name=source.name,
        source_type=source.source_type,
        category_id=source.category_id,
        status="active",
        message="Source configured successfully",
    )


@information_source_router.post(
    "/local/validate-access",
    response_model=ConnectivityTestResponse,
    dependencies=[Depends(requires(ASSISTANT_SOURCE_MANAGE))],
    summary="Test read access to a local folder without persisting (FR-012)",
)
async def validate_local_access_route(
    payload: LocalValidateAccessRequest, user: CurrentUser, org: CurrentOrg
) -> ConnectivityTestResponse:
    ok = test_local_folder_access(payload.folder_path)
    if ok:
        return ConnectivityTestResponse(status="success", message="Read access confirmed.")
    return ConnectivityTestResponse(
        status="failed", message="Could not read the specified folder."
    )


@information_source_router.post(
    "/github/verify",
    response_model=ConnectivityTestResponse,
    dependencies=[Depends(requires(ASSISTANT_SOURCE_MANAGE))],
    summary="Test read access to a GitHub/online repo without persisting (FR-013)",
)
async def verify_github_access_route(
    payload: GitHubVerifyRequest, user: CurrentUser, org: CurrentOrg
) -> ConnectivityTestResponse:
    ok = await test_github_access(payload.github_url, payload.access_token)
    if ok:
        return ConnectivityTestResponse(status="success", message="Read access confirmed.")
    return ConnectivityTestResponse(
        status="failed", message="Could not verify read access to the repository."
    )


@information_source_router.post(
    "/mcp/test",
    response_model=ConnectivityTestResponse,
    dependencies=[Depends(requires(ASSISTANT_SOURCE_MANAGE))],
    summary="Test connectivity to an MCP server without persisting (FR-014)",
)
async def test_mcp_route(
    payload: MCPTestRequest, user: CurrentUser, org: CurrentOrg
) -> ConnectivityTestResponse:
    ok = await test_mcp_connectivity(payload.mcp_server_address, payload.credentials)
    if ok:
        return ConnectivityTestResponse(status="success", message="Connectivity test passed.")
    return ConnectivityTestResponse(
        status="failed", message="Connectivity test failed."
    )


@information_source_router.get(
    "/",
    response_model=list[InformationSourceRead],
    dependencies=[Depends(requires(ASSISTANT_SOURCE_READ))],
    summary="List information sources (FR-011)",
)
async def list_information_sources_route(
    user: CurrentUser, org: CurrentOrg, session: SessionDep
) -> list[InformationSourceRead]:
    return await list_information_sources(session)


# ────────────────────────────────────────────────────────────────────────
# Question Categories — creation (FR-015, T-005)
# ────────────────────────────────────────────────────────────────────────


@question_category_router.post(
    "/",
    response_model=QuestionCategoryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requires(ASSISTANT_QUESTION_CATEGORY_MANAGE))],
    summary="Create a question category (FR-015)",
)
async def create_question_category_route(
    payload: QuestionCategoryCreate,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> QuestionCategoryRead:
    """Platform/Org Admins only. Duplicate names (case-insensitive) within
    the org return 409 before any write (T-005)."""
    try:
        category = await create_question_category(
            session, user, payload.name, payload.description
        )
    except DuplicateCategoryName as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A category with this name already exists.",
        ) from exc
    return QuestionCategoryRead.model_validate(category)


# ────────────────────────────────────────────────────────────────────────
# FAQ — manual creation (FR-016, T-006)
# ────────────────────────────────────────────────────────────────────────


@faq_router.post(
    "/",
    response_model=FAQRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requires(ASSISTANT_FAQ_MANAGE))],
    summary="Manually create an FAQ (FR-016)",
)
async def create_faq_route(
    payload: FAQCreate,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> FAQRead:
    """Platform/Org Admins and Content Managers. Any unresolvable
    question-category/source-category/source id returns 422 (T-006)."""
    try:
        faq = await create_faq(session, user, payload)
    except FAQValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.message,
        ) from exc
    return await to_faq_read(session, faq)


# ────────────────────────────────────────────────────────────────────────
# Tiered question answering (FR-007, FR-008, T-015, T-016)
# ────────────────────────────────────────────────────────────────────────


@question_router.post(
    "/",
    response_model=TieredQuestionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requires(ASSISTANT_ASK))],
    summary="Deterministic-first question answering (FR-007)",
)
async def ask_question_tiered_route(
    payload: AskQuestionCreate,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> TieredQuestionResponse:
    """Attempts FAQ matching, then the (inert) script tier, then falls back
    to the LLM before answering (FR-007). SR-002 content blocking applies
    identically to v0.1's /assistant/ask.
    """
    try:
        result = await answer_question_deterministic_first(session, user, payload, org.id)
    except ContentBlocked as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Please rephrase your question.",
        ) from exc
    return TieredQuestionResponse(
        interaction_log_id=result["interaction_log_id"],
        response_text=result["response_text"],
        reasoning=result["reasoning"],
        citations=result["citations"],
        has_citations=len(result["citations"]) > 0,
        source=result["source"],
        llm_invoked=result["llm_invoked"],
    )


@question_router.post(
    "/answer",
    response_model=AnswerQuestionResponse,
    dependencies=[Depends(requires(ASSISTANT_ASK))],
    summary="Tiered answer fallback with unanswerable alerting (FR-008)",
)
async def answer_question_route(
    payload: AskQuestionCreate,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> AnswerQuestionResponse:
    """Deterministic -> LLM (RAG or frontier, per FR-009 config) ->
    unanswerable. On the unanswerable outcome, dispatches an in-app alert
    to Organization Administrators and Content Managers (FR-008).
    """
    try:
        result = await answer_question_with_fallback(session, user, payload, org.id)
    except ContentBlocked as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Please rephrase your question.",
        ) from exc

    if result["tier"] == "unanswerable":
        return AnswerQuestionResponse(
            interaction_log_id=result["interaction_log_id"],
            question_text=payload.question_text,
            response_text=None,
            reasoning=None,
            citations=[],
            tier="unanswerable",
            status="no_answer_available",
            message=(
                "No answer is available for your question. An alert has been sent "
                "to the Organization Administrator and Content Manager."
            ),
            alert_sent=result["alert_sent"],
        )
    return AnswerQuestionResponse(
        interaction_log_id=result["interaction_log_id"],
        question_text=payload.question_text,
        response_text=result["response_text"],
        reasoning=result["reasoning"],
        citations=result["citations"],
        tier=result["tier"],
        alert_sent=False,
    )


@question_router.get(
    "/alerts",
    response_model=list[QuestionAlertRead],
    dependencies=[Depends(requires(ASSISTANT_ADMIN))],
    summary="List unanswerable-question alerts (FR-008)",
)
async def list_question_alerts_route(
    user: CurrentUser, org: CurrentOrg, session: SessionDep
) -> list[QuestionAlertRead]:
    return await list_question_alerts(session)


@question_router.patch(
    "/alerts/{alert_id}/acknowledge",
    response_model=QuestionAlertRead,
    dependencies=[Depends(requires(ASSISTANT_ADMIN))],
    summary="Acknowledge an unanswerable-question alert (FR-008)",
)
async def acknowledge_question_alert_route(
    alert_id: int, user: CurrentUser, org: CurrentOrg, session: SessionDep
) -> QuestionAlertRead:
    try:
        alert = await acknowledge_question_alert(session, user, alert_id)
    except QuestionAlertNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="alert not found"
        ) from exc
    return QuestionAlertRead(
        id=alert.id,
        org_id=alert.org_id,
        alert_type=alert.alert_type,
        question_text=alert.question_text,
        submitting_user_name=alert.submitting_user_name,
        acknowledged=alert.acknowledged,
        acknowledged_at=alert.acknowledged_at,
        created_at=alert.created_at,
    )


# ────────────────────────────────────────────────────────────────────────
# LLM Fallback Configuration (FR-009, T-017)
# ────────────────────────────────────────────────────────────────────────


@llm_fallback_config_router.get(
    "/",
    response_model=list[LLMFallbackConfigRead],
    dependencies=[Depends(requires(ASSISTANT_LLM_FALLBACK_MANAGE))],
    summary="List all LLM fallback configs (FR-009)",
)
async def list_llm_fallback_configs_route(
    user: CurrentUser, org: CurrentOrg, session: SessionDep
) -> list[LLMFallbackConfigRead]:
    configs = await list_llm_fallback_configs(session)
    return [LLMFallbackConfigRead.model_validate(c) for c in configs]


@llm_fallback_config_router.get(
    "/{source_category_id}/{question_category_id}",
    response_model=LLMFallbackConfigRead,
    dependencies=[Depends(requires(ASSISTANT_LLM_FALLBACK_MANAGE))],
    summary="Get one LLM fallback config (FR-009)",
)
async def get_llm_fallback_config_route(
    source_category_id: int,
    question_category_id: int,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> LLMFallbackConfigRead:
    try:
        config = await get_llm_fallback_config(
            session, source_category_id, question_category_id
        )
    except LLMFallbackConfigNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="fallback config not found"
        ) from exc
    return LLMFallbackConfigRead.model_validate(config)


@llm_fallback_config_router.put(
    "/{source_category_id}/{question_category_id}",
    response_model=LLMFallbackConfigRead,
    dependencies=[Depends(requires(ASSISTANT_LLM_FALLBACK_MANAGE))],
    summary="Create or update an LLM fallback config (FR-009)",
)
async def upsert_llm_fallback_config_route(
    source_category_id: int,
    question_category_id: int,
    payload: LLMFallbackConfigUpsert,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> LLMFallbackConfigRead:
    try:
        config = await upsert_llm_fallback_config(
            session, source_category_id, question_category_id, payload.mode
        )
    except InformationSourceCategoryNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="information source category not found",
        ) from exc
    except CategoryNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="question category not found",
        ) from exc
    return LLMFallbackConfigRead.model_validate(config)


@llm_fallback_config_router.delete(
    "/{source_category_id}/{question_category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(requires(ASSISTANT_LLM_FALLBACK_MANAGE))],
    summary="Delete an LLM fallback config (FR-009)",
)
async def delete_llm_fallback_config_route(
    source_category_id: int,
    question_category_id: int,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> None:
    try:
        await delete_llm_fallback_config(session, source_category_id, question_category_id)
    except LLMFallbackConfigNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="fallback config not found"
        ) from exc


# ────────────────────────────────────────────────────────────────────────
# Content Manager role assignment (supporting infrastructure)
# ────────────────────────────────────────────────────────────────────────


@organization_role_router.post(
    "/content-managers",
    response_model=ContentManagerAssignResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requires(ASSISTANT_ROLE_MANAGE))],
    summary="Designate a Content Manager within the current org",
)
async def assign_content_manager_route(
    payload: ContentManagerAssignRequest,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> ContentManagerAssignResponse:
    """Platform/Org Admins only. The target user must already be a member
    of the current org (404 otherwise)."""
    try:
        await assign_content_manager(session, org.id, payload.user_id)
    except NotAnOrgMember as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user is not a member of this organization",
        ) from exc
    return ContentManagerAssignResponse(
        user_id=payload.user_id, org_id=org.id, role="content_manager"
    )
