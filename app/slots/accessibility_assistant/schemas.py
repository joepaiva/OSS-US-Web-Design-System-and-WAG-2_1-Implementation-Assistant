# ─────────────────────────────────────────────────────────────────
# Control Annotations — NIST 800-53 (chassis v0.6)
# ─────────────────────────────────────────────────────────────────
# SI-10: Pydantic v2 field validation gates all inputs before ORM writes
# PT-1:  InteractionLog schemas handle PII fields (user_id, question_text)
# ─────────────────────────────────────────────────────────────────
"""Pydantic v2 schemas for the Accessibility Assistant slot.

Scope: v0.1 — FR-001 through FR-006, SR-001 through SR-004.

Schema groups:
  QuestionCategory — Read (browsing, FR-003)
  FAQ              — Read (browsing, FR-003, FR-004)
  Citation         — embedded in FAQ and InteractionLog responses
  AskQuestion      — Create (submit a question, FR-002, FR-004, FR-005)
  RateInteraction  — Update (thumbs up/down, FR-006)
  InteractionLog   — Read (FR-006, SR-003)
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# ────────────────────────────────────────────────────────────────────────
# Citation (embedded value object)
# ────────────────────────────────────────────────────────────────────────


class Citation(BaseModel):
    """A single source citation with a display name and hyperlink (FR-004)."""

    model_config = ConfigDict(extra="forbid")

    source_name: str
    hyperlink: str


# ────────────────────────────────────────────────────────────────────────
# QuestionCategory
# ────────────────────────────────────────────────────────────────────────


class QuestionCategoryRead(BaseModel):
    """QuestionCategory representation in responses (FR-003)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    org_id: int
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


# ────────────────────────────────────────────────────────────────────────
# FAQ
# ────────────────────────────────────────────────────────────────────────


class FAQRead(BaseModel):
    """FAQ representation in responses (FR-003, FR-004).

    `citations` is deserialised from `citations_json` by the service layer
    before returning; this schema receives the parsed list.
    """

    model_config = ConfigDict(extra="forbid")

    id: int
    org_id: int
    question_category_id: int | None
    question: str
    answer: str
    reasoning: str
    citations: list[Citation]
    created_at: datetime
    updated_at: datetime
    # v0.2 (FR-016): full multi-select associations. For FAQs created
    # before v0.2 (no M:N rows), question_category_ids falls back to
    # [question_category_id] when set, and the other two lists are empty.
    question_category_ids: list[int] = Field(default_factory=list)
    source_category_ids: list[int] = Field(default_factory=list)
    source_ids: list[int] = Field(default_factory=list)
    # v0.3 (FR-020): platform-level shared resources are visible read-only
    # to every org's Organization Administrators/Content Managers.
    is_platform_shared: bool = False


# ────────────────────────────────────────────────────────────────────────
# Ask a question (FR-002, FR-004, FR-005)
# ────────────────────────────────────────────────────────────────────────


class AskQuestionCreate(BaseModel):
    """Body for POST /assistant/ask.

    FR-002: question_text is required and limited to 200 characters.
    FR-005: session_id groups multi-turn conversation turns.
    FR-003: question_category_id is optional (user may browse or free-type).

    SR-002: PII / source-code detection is performed in the service layer
            before any LLM call; this schema only enforces structural
            constraints.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question_text: str = Field(
        min_length=1,
        max_length=200,
        description="The user's question. Max 200 characters (FR-002).",
    )
    question_category_id: int | None = Field(
        default=None,
        description="Optional category the user browsed to (FR-003).",
    )
    session_id: str | None = Field(
        default=None,
        max_length=128,
        description="Caller-supplied session identifier for multi-turn context (FR-005).",
    )


# ────────────────────────────────────────────────────────────────────────
# Rate an interaction (FR-006, FR-004)
# ────────────────────────────────────────────────────────────────────────


class RateInteractionUpdate(BaseModel):
    """Body for PATCH /assistant/interactions/{id}/rate.

    FR-006: rating is nullable — True=thumbs-up, False=thumbs-down.
    Sending null explicitly clears a previously submitted rating.
    """

    model_config = ConfigDict(extra="forbid")

    rating: bool | None = Field(
        description="True = thumbs up, False = thumbs down, null = clear rating."
    )


# ────────────────────────────────────────────────────────────────────────
# InteractionLog (FR-006, SR-003)
# ────────────────────────────────────────────────────────────────────────


class InteractionLogRead(BaseModel):
    """Interaction log record in responses (FR-006, SR-003).

    PT-1: contains PII (user_id, question_text). Access is restricted
    by RBAC in routes.py — end users see only their own records;
    org admins see org-scoped records; platform admins see all.
    """

    model_config = ConfigDict(extra="forbid")

    id: int
    org_id: int
    user_id: int
    question_category_id: int | None
    session_id: str | None
    question_text: str
    response_text: str
    reasoning: str
    sources: list[Citation]
    rating: bool | None
    created_at: datetime


# ────────────────────────────────────────────────────────────────────────
# Response to a submitted question (FR-004)
# ────────────────────────────────────────────────────────────────────────


class QuestionResponse(BaseModel):
    """Structured response returned to the end user after asking a question.

    FR-004: must contain (1) expository response text, (2) reasoning,
    (3) citations with hyperlinks, (4) a rating control (represented
    here by the interaction_log_id so the client can submit a rating).
    """

    model_config = ConfigDict(extra="forbid")

    interaction_log_id: int
    response_text: str
    reasoning: str
    citations: list[Citation]
    # Indicates whether any citations were found (FR-004 AC: no broken links)
    has_citations: bool


# ═════════════════════════════════════════════════════════════════════════
# v0.2 increment — FR-007 through FR-017
# ═════════════════════════════════════════════════════════════════════════


# ────────────────────────────────────────────────────────────────────────
# Information Source Categories (FR-010, T-002)
# ────────────────────────────────────────────────────────────────────────


class InformationSourceCategoryCreate(BaseModel):
    """Body for POST /api/information-source-categories/ (FR-010)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None)


class InformationSourceCategoryRead(BaseModel):
    """InformationSourceCategory representation in responses (FR-010)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    org_id: int
    name: str
    description: str | None
    created_by_user_id: int | None
    is_platform_shared: bool = False
    created_at: datetime
    updated_at: datetime


# ────────────────────────────────────────────────────────────────────────
# Information Sources (FR-011..FR-014, T-003)
# ────────────────────────────────────────────────────────────────────────


class SourceTypeInfo(BaseModel):
    """One entry of GET /api/information-sources/source-types (FR-011)."""

    model_config = ConfigDict(extra="forbid")

    source_type: str
    label: str
    form_variant: str


class MCPCredentials(BaseModel):
    """Optional MCP server credential fields (FR-014)."""

    model_config = ConfigDict(extra="forbid")

    username: str | None = None
    password: str | None = None
    api_key: str | None = None


class LocalCodeRepoSourceCreate(BaseModel):
    """POST /api/information-sources/ body for a Local Code Repo source (FR-012)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_type: Literal["local_code_repo"]
    name: str = Field(min_length=1, max_length=255)
    category_id: int
    folder_path: str = Field(min_length=1)


class DocumentFolderSourceCreate(BaseModel):
    """POST /api/information-sources/ body for a Document Folder source (FR-012)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_type: Literal["document_folder"]
    name: str = Field(min_length=1, max_length=255)
    category_id: int
    folder_path: str = Field(min_length=1)


class GitHubOnlineRepoSourceCreate(BaseModel):
    """POST /api/information-sources/ body for a GitHub/Online Repo source (FR-013)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_type: Literal["github_online_repo"]
    name: str = Field(min_length=1, max_length=255)
    category_id: int
    github_url: str = Field(min_length=1)
    access_token: str | None = None


class MCPServerSourceCreate(BaseModel):
    """POST /api/information-sources/ body for an MCP Server source (FR-014)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_type: Literal["mcp_server"]
    name: str = Field(min_length=1, max_length=255)
    category_id: int
    mcp_server_address: str = Field(min_length=1)
    credentials: MCPCredentials | None = None


InformationSourceCreate = Annotated[
    LocalCodeRepoSourceCreate
    | DocumentFolderSourceCreate
    | GitHubOnlineRepoSourceCreate
    | MCPServerSourceCreate,
    Field(discriminator="source_type"),
]


class InformationSourceRead(BaseModel):
    """InformationSource representation in responses (FR-011..FR-014).

    Never carries `credentials_encrypted` or any decrypted secret — only a
    `credential_set` indicator (SR-001: no plaintext credential is ever
    returned in API responses).
    """

    model_config = ConfigDict(extra="forbid")

    id: int
    org_id: int
    category_id: int
    name: str
    source_type: str
    folder_path: str | None
    github_url: str | None
    mcp_server_address: str | None
    credential_set: bool
    test_status: str
    last_tested_at: datetime | None
    created_by_user_id: int | None
    is_platform_shared: bool = False
    created_at: datetime
    updated_at: datetime


class InformationSourceCreateResponse(BaseModel):
    """201 response for POST /api/information-sources/."""

    model_config = ConfigDict(extra="forbid")

    source_id: int
    name: str
    source_type: str
    category_id: int
    status: str
    message: str


class LocalValidateAccessRequest(BaseModel):
    """Body for POST /api/information-sources/local/validate-access (FR-012)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    folder_path: str = Field(min_length=1)


class GitHubVerifyRequest(BaseModel):
    """Body for POST /api/information-sources/github/verify (FR-013)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    github_url: str = Field(min_length=1)
    access_token: str | None = None


class MCPTestRequest(BaseModel):
    """Body for POST /api/information-sources/mcp/test (FR-014)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mcp_server_address: str = Field(min_length=1)
    credentials: MCPCredentials | None = None


class ConnectivityTestResponse(BaseModel):
    """Shared response shape for the three standalone connectivity-test
    endpoints (they never persist a row)."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "failed"]
    message: str


# ────────────────────────────────────────────────────────────────────────
# Question Categories — creation (FR-015, T-005)
# ────────────────────────────────────────────────────────────────────────


class QuestionCategoryCreate(BaseModel):
    """Body for POST /api/question-categories/ (FR-015)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None)


# ────────────────────────────────────────────────────────────────────────
# FAQ — manual creation (FR-016, T-006)
# ────────────────────────────────────────────────────────────────────────


class FAQCreate(BaseModel):
    """Body for POST /api/faqs/ (FR-016).

    All four collections are required and must be non-empty per T-006's
    acceptance criteria ("at least one question category, at least one
    source category, at least one source").
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    question_category_ids: list[int] = Field(min_length=1)
    source_category_ids: list[int] = Field(min_length=1)
    source_ids: list[int] = Field(min_length=1)


# ────────────────────────────────────────────────────────────────────────
# Tiered question answering (FR-007, FR-008, T-015, T-016)
# ────────────────────────────────────────────────────────────────────────


class TieredQuestionResponse(BaseModel):
    """Response for POST /api/questions/ (FR-007, T-015).

    `source` identifies which tier produced the answer.
    """

    model_config = ConfigDict(extra="forbid")

    interaction_log_id: int
    response_text: str
    reasoning: str
    citations: list[Citation]
    has_citations: bool
    source: Literal["faq", "script", "llm"]
    llm_invoked: bool


class AnswerQuestionResponse(BaseModel):
    """Response for POST /api/questions/answer (FR-008, T-016).

    Either a normal answer (status=None, response_text populated) or an
    "unanswerable" outcome (status="no_answer_available", alert_sent=True).
    """

    model_config = ConfigDict(extra="forbid")

    interaction_log_id: int | None
    question_text: str
    response_text: str | None
    reasoning: str | None
    citations: list[Citation]
    tier: Literal[
        "faq", "script", "llm_retrieval_augmented", "llm_frontier", "unanswerable"
    ]
    status: str | None = None
    message: str | None = None
    alert_sent: bool = False


class QuestionAlertRead(BaseModel):
    """Alert representation for GET /api/questions/alerts (FR-008)."""

    model_config = ConfigDict(extra="forbid")

    id: int
    org_id: int
    alert_type: str
    question_text: str
    submitting_user_name: str
    acknowledged: bool
    acknowledged_at: datetime | None
    created_at: datetime


# ────────────────────────────────────────────────────────────────────────
# LLM Fallback Configuration (FR-009, T-017)
# ────────────────────────────────────────────────────────────────────────


class LLMFallbackConfigUpsert(BaseModel):
    """Body for PUT /api/llm-fallback-config/{source_category_id}/{question_category_id}."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["retrieval_augmented", "frontier_general_knowledge"]


class LLMFallbackConfigRead(BaseModel):
    """LLMFallbackConfig representation in responses (FR-009)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    org_id: int
    source_category_id: int
    question_category_id: int
    mode: str
    created_at: datetime
    updated_at: datetime


# ────────────────────────────────────────────────────────────────────────
# Content Manager role assignment (supporting infrastructure for
# FR-011..FR-014, FR-016 — see app/slots/accessibility_assistant/__init__.py)
# ────────────────────────────────────────────────────────────────────────


class ContentManagerAssignRequest(BaseModel):
    """Body for POST /api/organizations/content-managers (assign)."""

    model_config = ConfigDict(extra="forbid")

    user_id: int


class ContentManagerAssignResponse(BaseModel):
    """Response confirming a Content Manager designation."""

    model_config = ConfigDict(extra="forbid")

    user_id: int
    org_id: int
    role: str


# ═════════════════════════════════════════════════════════════════════════
# v0.3 increment — FR-017 through FR-022, SR-005 through SR-007, NFR-001
# ═════════════════════════════════════════════════════════════════════════


# ────────────────────────────────────────────────────────────────────────
# Response Helpfulness Rating (FR-019, T-019)
# ────────────────────────────────────────────────────────────────────────


class HelpfulnessRatingCreate(BaseModel):
    """Body for POST /api/interaction-logs/{log_id}/rating (FR-019).

    Deliberately a strict discriminated literal — any other value is
    rejected by the framework with 422 before the service is called.
    """

    model_config = ConfigDict(extra="forbid")

    rating: Literal["helpful", "unhelpful"]


class HelpfulnessRatingRead(BaseModel):
    """Response for a successful helpfulness-rating submission (FR-019)."""

    model_config = ConfigDict(extra="forbid")

    interaction_log_id: int
    rating: Literal["helpful", "unhelpful"]


# ────────────────────────────────────────────────────────────────────────
# Administrator Interaction Log View (FR-021, T-021)
# ────────────────────────────────────────────────────────────────────────
#
# Reuses the existing InteractionLogRead schema above (no new shape needed);
# see routes.py's new interaction_log_router.


# ────────────────────────────────────────────────────────────────────────
# Platform-Level Resource Sharing (FR-020, T-020)
# ────────────────────────────────────────────────────────────────────────


class ShareResourceRequest(BaseModel):
    """Body for PATCH .../{id}/share on information sources, information
    source categories, and FAQs (FR-020). `is_shared=False` lets a Platform
    Administrator un-share a resource they previously shared."""

    model_config = ConfigDict(extra="forbid")

    is_shared: bool = True


# ────────────────────────────────────────────────────────────────────────
# Automated FAQ Generation from Interaction Logs (FR-017, NFR-001, T-007)
# ────────────────────────────────────────────────────────────────────────


class FAQGenerationSessionCreate(BaseModel):
    """Body for POST /api/faqs/generation-sessions/ (FR-017)."""

    model_config = ConfigDict(extra="forbid")

    max_logs: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum number of recent interaction logs to review.",
    )


class FAQGenerationSessionCreateResponse(BaseModel):
    """Response for POST /api/faqs/generation-sessions/ (FR-017)."""

    model_config = ConfigDict(extra="forbid")

    session_id: int
    status: str
    candidate_count: int


class FAQGenerationCandidateRead(BaseModel):
    """One staged candidate returned by GET .../candidates/ (FR-017)."""

    model_config = ConfigDict(extra="forbid")

    id: int
    question: str
    answer: str
    question_category_ids: list[int] = Field(default_factory=list)
    source_category_ids: list[int] = Field(default_factory=list)
    source_ids: list[int] = Field(default_factory=list)
    status: str


class FAQGenerationApprovedCandidate(FAQCreate):
    """One approved (and possibly human-edited) candidate submitted back to
    POST .../confirm/ (FR-017). Extends FAQCreate's own required-field /
    non-empty-list validation with a reference back to the staged candidate
    it originated from."""

    candidate_id: int


class FAQGenerationConfirmRequest(BaseModel):
    """Body for POST /api/faqs/generation-sessions/{session_id}/confirm/
    (FR-017, NFR-001). An empty (or omitted) `approved` list is a valid,
    explicit "save nothing" confirmation — NFR-001's approval gate means a
    missing confirmation is always treated as rejection, never as implicit
    approval."""

    model_config = ConfigDict(extra="forbid")

    approved: list[FAQGenerationApprovedCandidate] = Field(default_factory=list)


class FAQGenerationConfirmResponse(BaseModel):
    """Response for the FR-017 confirm endpoint."""

    model_config = ConfigDict(extra="forbid")

    created_faq_ids: list[int]
    discarded_candidate_ids: list[int]


# ────────────────────────────────────────────────────────────────────────
# Automated FAQ Generation from Information Source (FR-018, NFR-001, T-008)
# ────────────────────────────────────────────────────────────────────────


class FAQGenerationFromSourceRequest(BaseModel):
    """Body for POST /api/faqs/generate (FR-018)."""

    model_config = ConfigDict(extra="forbid")

    source_id: int
    max_content_bytes: int = Field(default=20_000, ge=1_000, le=200_000)


class FAQGenerationCandidateOut(BaseModel):
    """One in-memory candidate returned by POST /api/faqs/generate (FR-018).
    Never persisted — see T-008's own "no staging table" implementation
    note."""

    model_config = ConfigDict(extra="forbid")

    question: str
    answer: str
    question_category_ids: list[int] = Field(default_factory=list)
    source_category_ids: list[int] = Field(default_factory=list)
    source_ids: list[int] = Field(default_factory=list)


class FAQGenerationFromSourceResponse(BaseModel):
    """Response for POST /api/faqs/generate (FR-018).

    `blocked=True` means SR-005/SR-006 determined the source content could
    not be safely or cleanly sent to the LLM (see service.py's
    generate_faq_candidates_from_source) — `candidates` is then always
    empty and no LLM call was made.
    """

    model_config = ConfigDict(extra="forbid")

    source_id: int
    candidates: list[FAQGenerationCandidateOut] = Field(default_factory=list)
    blocked: bool = False
    blocked_reason: str | None = None


class FAQGenerationFromSourceConfirmRequest(BaseModel):
    """Body for POST /api/faqs/generate/confirm (FR-018). Reuses FAQCreate
    directly — the client resubmits the (possibly edited) approved
    candidates in full; there is no server-side session to reference."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[FAQCreate] = Field(min_length=1)


class FAQGenerationFromSourceConfirmResponse(BaseModel):
    """Response for the FR-018 confirm endpoint."""

    model_config = ConfigDict(extra="forbid")

    created_faq_ids: list[int]
