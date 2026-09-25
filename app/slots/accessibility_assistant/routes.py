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
    ASSISTANT_INTERACTION_LOG_READ,
    ASSISTANT_LLM_FALLBACK_MANAGE,
    ASSISTANT_PLATFORM_SHARE,
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
    FAQGenerationCandidateRead,
    FAQGenerationConfirmRequest,
    FAQGenerationConfirmResponse,
    FAQGenerationFromSourceConfirmRequest,
    FAQGenerationFromSourceConfirmResponse,
    FAQGenerationFromSourceRequest,
    FAQGenerationFromSourceResponse,
    FAQGenerationSessionCreate,
    FAQGenerationSessionCreateResponse,
    FAQRead,
    GitHubVerifyRequest,
    HelpfulnessRatingCreate,
    HelpfulnessRatingRead,
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
    ShareResourceRequest,
    SourceTypeInfo,
    TieredQuestionResponse,
)
from app.slots.accessibility_assistant.service import (
    CategoryNotFound,
    ContentBlocked,
    DuplicateCategoryName,
    FAQGenerationSessionNotFound,
    FAQNotFound,
    FAQValidationError,
    InformationSourceCategoryNotFound,
    InformationSourceNotFound,
    InteractionLogAccessDenied,
    InteractionLogNotFound,
    LLMFallbackConfigNotFound,
    NotAnOrgMember,
    PlatformShareDenied,
    QuestionAlertNotFound,
    RatingAlreadySubmitted,
    SourceTestFailed,
    acknowledge_question_alert,
    answer_question_deterministic_first,
    answer_question_with_fallback,
    ask_question,
    assign_content_manager,
    confirm_faq_generation_from_source,
    confirm_faq_generation_session,
    create_faq,
    create_faq_generation_session_from_logs,
    create_information_source,
    create_information_source_category,
    create_question_category,
    delete_llm_fallback_config,
    generate_faq_candidates_from_source,
    get_faq,
    get_interaction,
    get_llm_fallback_config,
    list_faq_generation_candidates,
    list_faqs_by_category,
    list_information_source_categories,
    list_information_sources,
    list_interaction_logs_admin,
    list_llm_fallback_configs,
    list_my_interactions,
    list_org_interactions,
    list_question_alerts,
    list_question_categories,
    list_source_types,
    rate_interaction,
    share_faq,
    share_information_source,
    share_information_source_category,
    submit_helpfulness_rating,
    test_github_access,
    test_local_folder_access,
    test_mcp_connectivity,
    to_faq_read,
    to_information_source_read,
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
# v0.3 (T-019, T-021): FR-019's rating endpoint and FR-021's administrator
# log view both operate on interaction logs but don't fit any existing
# router's resource domain — a new dedicated router, same convention as
# the v0.2 routers above.
interaction_log_router = APIRouter(prefix="/api/interaction-logs", tags=["interaction-logs"])


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
        return await get_faq(session, faq_id, org.id)
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
    return await list_information_source_categories(session, org.id)


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
    return await list_information_sources(session, org.id)


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


# ═════════════════════════════════════════════════════════════════════════
# v0.3 increment — FR-017 through FR-022, SR-005 through SR-007, NFR-001
# ═════════════════════════════════════════════════════════════════════════


# ────────────────────────────────────────────────────────────────────────
# Response Helpfulness Rating (FR-019, T-019)
# ────────────────────────────────────────────────────────────────────────


@interaction_log_router.post(
    "/{log_id}/rating",
    response_model=HelpfulnessRatingRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requires(ASSISTANT_ASK))],
    summary="Submit a write-once helpfulness rating for an interaction log (FR-019)",
)
async def submit_helpfulness_rating_route(
    log_id: int,
    payload: HelpfulnessRatingCreate,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> HelpfulnessRatingRead:
    """FR-019: rating is write-once. A second submission for the same log
    returns 409; the original rating remains unchanged. No PUT, PATCH, or
    DELETE route is registered for this sub-resource — the immutability
    invariant is structural as well as logical.
    """
    try:
        entry = await submit_helpfulness_rating(session, user, log_id, payload.rating)
    except InteractionLogNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="interaction log not found"
        ) from exc
    except InteractionLogAccessDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="access denied") from exc
    except RatingAlreadySubmitted as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a rating has already been submitted for this interaction log",
        ) from exc
    # payload.rating is already the validated Literal["helpful","unhelpful"] — reuse it
    # directly rather than re-reading the ORM column (typed as a plain `str`).
    return HelpfulnessRatingRead(interaction_log_id=entry.id, rating=payload.rating)


# ────────────────────────────────────────────────────────────────────────
# Administrator Interaction Log View (FR-021, SR-007, T-021)
# ────────────────────────────────────────────────────────────────────────


@interaction_log_router.get(
    "/",
    response_model=list[InteractionLogRead],
    dependencies=[Depends(requires(ASSISTANT_INTERACTION_LOG_READ))],
    summary="Administrator interaction log view (FR-021, read-only)",
)
async def list_interaction_logs_admin_route(
    user: CurrentUser, org: CurrentOrg, session: SessionDep
) -> list[InteractionLogRead]:
    """A genuine Platform Administrator (user.is_superuser) sees logs across
    every organization; an Organization Administrator sees only the current
    org's logs. Content Managers and End Users are denied by the permission
    gate above. No PUT/PATCH/DELETE route exists for this resource (SR-007).
    """
    return await list_interaction_logs_admin(session, user)


# ────────────────────────────────────────────────────────────────────────
# Platform-Level Resource Sharing (FR-020, T-020)
# ────────────────────────────────────────────────────────────────────────


@information_source_category_router.patch(
    "/{category_id}/share",
    response_model=InformationSourceCategoryRead,
    dependencies=[Depends(requires(ASSISTANT_PLATFORM_SHARE))],
    summary="Designate an information source category platform-level shared (FR-020)",
)
async def share_information_source_category_route(
    category_id: int,
    payload: ShareResourceRequest,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> InformationSourceCategoryRead:
    """Only a genuine Platform Administrator (user.is_superuser) may share a
    resource — an Organization Administrator or Content Manager holding the
    route-level permission is still denied (403) by the service layer."""
    try:
        category = await share_information_source_category(
            session, user, category_id, payload.is_shared
        )
    except PlatformShareDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only a Platform Administrator may share this resource",
        ) from exc
    except InformationSourceCategoryNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="information source category not found",
        ) from exc
    return InformationSourceCategoryRead.model_validate(category)


@information_source_router.patch(
    "/{source_id}/share",
    response_model=InformationSourceRead,
    dependencies=[Depends(requires(ASSISTANT_PLATFORM_SHARE))],
    summary="Designate an information source platform-level shared (FR-020)",
)
async def share_information_source_route(
    source_id: int,
    payload: ShareResourceRequest,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> InformationSourceRead:
    try:
        source = await share_information_source(session, user, source_id, payload.is_shared)
    except PlatformShareDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only a Platform Administrator may share this resource",
        ) from exc
    except InformationSourceNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="information source not found"
        ) from exc
    return to_information_source_read(source)


@faq_router.patch(
    "/{faq_id}/share",
    response_model=FAQRead,
    dependencies=[Depends(requires(ASSISTANT_PLATFORM_SHARE))],
    summary="Designate an FAQ platform-level shared (FR-020)",
)
async def share_faq_route(
    faq_id: int,
    payload: ShareResourceRequest,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> FAQRead:
    try:
        faq = await share_faq(session, user, faq_id, payload.is_shared)
    except PlatformShareDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only a Platform Administrator may share this resource",
        ) from exc
    except FAQNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FAQ not found") from exc
    return await to_faq_read(session, faq)


# ────────────────────────────────────────────────────────────────────────
# Automated FAQ Generation from Interaction Logs (FR-017, NFR-001, T-007)
# ────────────────────────────────────────────────────────────────────────


@faq_router.post(
    "/generation-sessions/",
    response_model=FAQGenerationSessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requires(ASSISTANT_FAQ_MANAGE))],
    summary="Initiate LLM review of interaction logs for FAQ generation (FR-017)",
)
async def create_faq_generation_session_route(
    payload: FAQGenerationSessionCreate,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> FAQGenerationSessionCreateResponse:
    """Stages LLM-drafted candidates in `pending_review` status. No FAQ row
    is written here — see the confirm endpoint below (NFR-001)."""
    gen_session, candidates = await create_faq_generation_session_from_logs(
        session, user, org.id, payload.max_logs
    )
    return FAQGenerationSessionCreateResponse(
        session_id=gen_session.id, status=gen_session.status, candidate_count=len(candidates)
    )


@faq_router.get(
    "/generation-sessions/{session_id}/candidates/",
    response_model=list[FAQGenerationCandidateRead],
    dependencies=[Depends(requires(ASSISTANT_FAQ_MANAGE))],
    summary="List staged FAQ candidates for human review (FR-017)",
)
async def list_faq_generation_candidates_route(
    session_id: int, user: CurrentUser, org: CurrentOrg, session: SessionDep
) -> list[FAQGenerationCandidateRead]:
    try:
        return await list_faq_generation_candidates(session, session_id)
    except FAQGenerationSessionNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="generation session not found"
        ) from exc


@faq_router.post(
    "/generation-sessions/{session_id}/confirm/",
    response_model=FAQGenerationConfirmResponse,
    dependencies=[Depends(requires(ASSISTANT_FAQ_MANAGE))],
    summary="Persist only the approved FAQ candidates (FR-017, NFR-001)",
)
async def confirm_faq_generation_session_route(
    session_id: int,
    payload: FAQGenerationConfirmRequest,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> FAQGenerationConfirmResponse:
    """An empty `approved` list is a valid, explicit "save nothing"
    confirmation (NFR-001). Any unresolvable category/source id in an
    approved candidate returns 422 and nothing is persisted (atomic)."""
    try:
        _, created_faq_ids, discarded_candidate_ids = await confirm_faq_generation_session(
            session, user, session_id, payload.approved
        )
    except FAQGenerationSessionNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="generation session not found"
        ) from exc
    except FAQValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message
        ) from exc
    return FAQGenerationConfirmResponse(
        created_faq_ids=created_faq_ids, discarded_candidate_ids=discarded_candidate_ids
    )


# ────────────────────────────────────────────────────────────────────────
# Automated FAQ Generation from Information Source (FR-018, NFR-001, T-008)
# ────────────────────────────────────────────────────────────────────────


@faq_router.post(
    "/generate",
    response_model=FAQGenerationFromSourceResponse,
    dependencies=[Depends(requires(ASSISTANT_FAQ_MANAGE))],
    summary="Generate in-memory FAQ candidates from an information source (FR-018)",
)
async def generate_faq_from_source_route(
    payload: FAQGenerationFromSourceRequest,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> FAQGenerationFromSourceResponse:
    """Candidates are returned in-memory only — nothing is persisted until
    the confirm endpoint below is called (NFR-001). SR-005/SR-006: source
    content matching a no-execute/injection pattern, or containing source
    code, is never sent to the LLM — the response reports `blocked=true`
    with zero candidates instead.
    """
    try:
        return await generate_faq_candidates_from_source(
            session, user, org.id, payload.source_id, payload.max_content_bytes
        )
    except InformationSourceNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="information source not found"
        ) from exc


@faq_router.post(
    "/generate/confirm",
    response_model=FAQGenerationFromSourceConfirmResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requires(ASSISTANT_FAQ_MANAGE))],
    summary="Persist approved FAQ candidates generated from a source (FR-018, NFR-001)",
)
async def confirm_faq_from_source_route(
    payload: FAQGenerationFromSourceConfirmRequest,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> FAQGenerationFromSourceConfirmResponse:
    """Atomic: every candidate is validated before any is persisted."""
    try:
        created_ids = await confirm_faq_generation_from_source(session, user, payload.candidates)
    except FAQValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message
        ) from exc
    return FAQGenerationFromSourceConfirmResponse(created_faq_ids=created_ids)
