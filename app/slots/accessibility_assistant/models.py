# ─────────────────────────────────────────────────────────────────
# Control Annotations — NIST 800-53 (chassis v0.6)
# ─────────────────────────────────────────────────────────────────
# AC-3: TenantScoped mixin enforces org_id boundary on all reads/writes
# AC-6: interaction_log user_id FK ensures users can only own their own records
# AU-2: @audited decorator applied to state-mutating service functions
# SC-28: credential_encrypted column stores only ciphertext (AES-256-GCM)
# PT-1: InteractionLog contains PII (user_id, question_text); access restricted
# SI-10: Pydantic v2 schemas validate all inputs before ORM writes
# ─────────────────────────────────────────────────────────────────
"""Accessibility Assistant ORM models — SQLAlchemy 2.0 async.

Scope: v0.1 increment — FR-001, FR-002, FR-003, FR-004, FR-005, FR-006,
       SR-001, SR-002, SR-003, SR-004.
Scope: v0.2 increment — FR-007 through FR-017 (see bottom of file).
Scope: v0.3 increment — FR-017 through FR-022, SR-005 through SR-007,
       NFR-001 (see bottom of file).

Tables defined here (v0.1):
  - aa_question_categories   (FR-003: browse FAQs by category)
  - aa_faqs                  (FR-003: FAQ entries with answers)
  - aa_interaction_logs      (FR-006: persistent interaction records; PT-1 PII)

Tables added in v0.2 (see bottom of file for the models + full rationale):
  - aa_information_source_categories  (FR-010)
  - aa_information_sources            (FR-011..FR-014)
  - aa_faq_question_categories        (FR-016: FAQ <-> QuestionCategory M:N)
  - aa_faq_source_categories          (FR-016: FAQ <-> InformationSourceCategory M:N)
  - aa_faq_sources                    (FR-016: FAQ <-> InformationSource M:N)
  - aa_llm_fallback_configs           (FR-009)
  - aa_question_alerts                (FR-008: unanswerable-question alerts)

Tables added in v0.3 (see bottom of file for the models + full rationale):
  - aa_faq_generation_sessions        (FR-017: staging sessions for LLM FAQ review)
  - aa_faq_generation_candidates      (FR-017: staged, human-reviewable FAQ candidates)

Columns added in v0.3 (both nullable/defaulted — existing rows unaffected):
  - aa_interaction_logs.helpfulness_rating         (FR-019)
  - aa_information_source_categories.is_platform_shared (FR-020)
  - aa_information_sources.is_platform_shared           (FR-020)
  - aa_faqs.is_platform_shared                          (FR-020)

Columns added in v0.4 (nullable — existing rows unaffected; see FR-027):
  - aa_information_source_categories.creator_role_snapshot (FR-027)
  - aa_information_sources.creator_role_snapshot           (FR-027)
  - aa_faqs.creator_role_snapshot                          (FR-027)

All tables inherit (Base, TenantScoped) for automatic org_id isolation.
Interaction logs are append-only by application convention (no UPDATE/DELETE
routes exposed); the column set captures all fields required by FR-006 and
SR-003. PT-1/SR-007: InteractionLog is PII-classified (user_id, question_text,
response_text, and organization all constitute PII per SR-007's own
classification) — `pii_classified = True` is recorded here as a durable
docstring-level marker (T-021/SR-007 implementation note) so future
data-handling tooling (retention, export, anonymization, per PROC-006) has a
single place to discover this. No mutation route (UPDATE/DELETE) is exposed
for any interaction-log field except the two explicitly-scoped, immutable-
once-set rating mechanisms (FR-006's legacy boolean `rating`, FR-019's new
`helpfulness_rating`) — see service.py for the enforcement.

Soft-delete: NOT used in this slot (ARCHITECTURE.md §2.9 — opt-in only).
Retention: interaction logs carry retained_until via RetainableFor mixin
           to support future SI-12 archival jobs.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, RetainableFor, TenantScoped


class QuestionCategory(Base, TenantScoped):
    """A named category used to organise FAQs (FR-003, FR-010 out-of-scope
    but the model is needed for FR-003 browsing in v0.1).

    Uniqueness of `name` is enforced per-org via the composite unique
    constraint on (org_id, name).
    """

    __tablename__ = "aa_question_categories"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_aa_qcat_org_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # v0.2 (FR-015): tracks who created the category. Nullable because
    # v0.1 rows predate this column (additive migration 0016).
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"QuestionCategory(id={self.id!r}, name={self.name!r})"


class FAQ(Base, TenantScoped):
    """A FAQ entry with a question and a standard answer (FR-003, FR-004).

    `question_category_id` links to QuestionCategory so end users can
    browse FAQs by category (FR-003).

    `answer` stores the full expository response text.
    `reasoning` stores the reasoning behind the response (FR-004).
    `citations_json` stores a JSON-serialised list of
    {source_name, hyperlink} dicts (FR-004 — stored as Text/JSON string
    to avoid a separate citations table in v0.1).
    """

    __tablename__ = "aa_faqs"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_category_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("aa_question_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reasoning: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # JSON string: [{"source_name": "...", "hyperlink": "..."}]
    citations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # v0.2 (FR-016): tracks who created the FAQ (manual or automated origin).
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # v0.2 (FR-007): optional regex pattern for the third deterministic-match
    # tier (exact-slug -> keyword-set -> regex). NULL means this FAQ does not
    # participate in the regex tier. Content managers may set this when
    # authoring an FAQ that should match a family of phrasings; it is never
    # required (T-006's acceptance criteria does not mandate it).
    match_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    # v0.3 (FR-020): platform-level shared resources are visible read-only to
    # every org's Organization Administrators/Content Managers. Only a real
    # Platform Administrator (user.is_superuser) may set this — see
    # service.py's share_faq/_share_resource.
    is_platform_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # v0.4 (FR-027): a durable, write-once-at-creation snapshot of the
    # creator's role ("platform_admin" or "other"), so eligibility for
    # platform-level sharing can never drift if the creator's role changes
    # later. NULL means "created before this column existed" (or inserted
    # directly via ORM bypassing the service layer) — such rows are simply
    # never eligible for promotion (fail closed) until recreated through the
    # real creation path. See service.py's _share_resource.
    creator_role_snapshot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"FAQ(id={self.id!r}, question={self.question[:40]!r})"


class InteractionLog(Base, TenantScoped, RetainableFor):
    """Persistent record of every user interaction (FR-006, SR-003, PT-1).

    pii_classified = True (SR-007): user_id, question_text, response_text
    and the owning organization all constitute PII per SR-007's own
    classification. Access is restricted by application-layer RBAC:
      - End users may only read their own records (filtered by user_id).
      - Org admins may read all records in their org (TenantScoped).
      - Platform admins may read across all orgs (FR-021, via is_superuser).
      - No UPDATE or DELETE routes are exposed (append-only) for any field
        except the two explicitly-scoped, write-once rating mechanisms
        below.

    `session_id` groups multi-turn exchanges (FR-005). It is a
    caller-supplied opaque string (UUID recommended) that the client
    generates at session start and sends with every turn.

    `rating` is nullable — null means the user did not submit a rating
    (FR-006 AC: rating field recorded as null or unrated).
    True = thumbs up, False = thumbs down. This is the ORIGINAL v0.1/FR-006
    rating mechanism and remains fully mutable (a second PATCH may change
    or clear it) — a real, test-verified v0.1 behavior
    (`test_rate_interaction_null_clears_rating`) that this increment does
    NOT alter.

    `helpfulness_rating` (v0.3, FR-019) is a SEPARATE, additive,
    write-once field: `'helpful'` / `'unhelpful'` / NULL, enforced
    immutable once set by the service layer (RatingAlreadySubmitted -> 409)
    and structurally (no PUT/PATCH/DELETE route exists for it). FR-019
    requires immutability, which genuinely conflicts with the legacy
    `rating` field's existing, tested mutability — so FR-019 is realized as
    its own column + its own endpoint rather than retrofitting `rating`.
    See TASKS.md T-019 and the v0.3 completion report for the full
    rationale.

    `sources_json` stores a JSON-serialised list of source identifiers
    used when generating the response (FR-006).
    """

    __tablename__ = "aa_interaction_logs"
    __table_args__ = (
        CheckConstraint(
            "helpfulness_rating IN ('helpful', 'unhelpful') OR helpfulness_rating IS NULL",
            name="ck_aa_interaction_logs_helpfulness_rating",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable FK — category may not be selected for free-text questions
    question_category_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("aa_question_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Groups multi-turn conversation turns (FR-005)
    session_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reasoning: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # JSON string: [{"source_name": "...", "hyperlink": "..."}]
    sources_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # Nullable: True=thumbs-up, False=thumbs-down, None=not rated
    rating: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # v0.3 (FR-019): write-once helpfulness rating, distinct from the legacy
    # `rating` boolean above (see class docstring for why). CHECK-constrained
    # to 'helpful' / 'unhelpful' / NULL at the DB level.
    helpfulness_rating: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"InteractionLog(id={self.id!r}, user_id={self.user_id!r}, "
            f"session_id={self.session_id!r})"
        )


# ═════════════════════════════════════════════════════════════════════════
# v0.2 increment — FR-007 through FR-017
# ═════════════════════════════════════════════════════════════════════════
#
# New tables added by migration 0016 (additive-only — see Rule 9):
#   - aa_information_source_categories
#   - aa_information_sources
#   - aa_faq_question_categories / aa_faq_source_categories / aa_faq_sources
#   - aa_llm_fallback_configs
#   - aa_question_alerts
#
# Two new columns are also added to existing v0.1 tables (both nullable,
# so existing rows remain valid):
#   - aa_question_categories.created_by_user_id  (FR-015)
#   - aa_faqs.created_by_user_id, aa_faqs.match_pattern  (FR-016, FR-007)


class InformationSourceType(enum.StrEnum):
    """The four supported information source types (FR-011)."""

    LOCAL_CODE_REPO = "local_code_repo"
    GITHUB_ONLINE_REPO = "github_online_repo"
    DOCUMENT_FOLDER = "document_folder"
    MCP_SERVER = "mcp_server"


class InformationSourceTestStatus(enum.StrEnum):
    """Connectivity/read-access test outcome for an InformationSource."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class InformationSourceCategory(Base, TenantScoped):
    """A named grouping for information sources (FR-010).

    Uniqueness of `name` is enforced per-org via a composite unique
    constraint — mirrors QuestionCategory's own pattern from v0.1.
    """

    __tablename__ = "aa_information_source_categories"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_aa_srccat_org_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # v0.3 (FR-020): see FAQ.is_platform_shared above for the full rationale.
    is_platform_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # v0.4 (FR-027): see FAQ.creator_role_snapshot above for the full rationale.
    creator_role_snapshot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"InformationSourceCategory(id={self.id!r}, name={self.name!r})"


class InformationSource(Base, TenantScoped):
    """A configured, type-specific information source (FR-011..FR-014).

    Non-secret, type-specific configuration is stored in dedicated nullable
    columns (`folder_path`, `github_url`, `mcp_server_address`) rather than a
    single opaque JSON blob, so the no-execute/read-only invariant is easy to
    verify by inspection. Secret material (a GitHub access token, or MCP
    username/password/api_key) is JSON-encoded and then AES-256-GCM
    encrypted via `CredentialEncryptionService` (SR-001) into
    `credentials_encrypted`; the plaintext is never stored, logged, or
    returned by any route.
    """

    __tablename__ = "aa_information_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("aa_information_source_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(
        Enum(
            InformationSourceType,
            name="aa_information_source_type",
            native_enum=False,
            length=32,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    # local_code_repo / document_folder
    folder_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    # github_online_repo
    github_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # mcp_server
    mcp_server_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    # AES-256-GCM ciphertext of a JSON blob of secret fields (SR-001).
    # NULL when the source type carries no secret (local_code_repo/document_folder
    # with no credentials supplied).
    credentials_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_status: Mapped[str] = mapped_column(
        Enum(
            InformationSourceTestStatus,
            name="aa_information_source_test_status",
            native_enum=False,
            length=16,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=InformationSourceTestStatus.PENDING.value,
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # v0.3 (FR-020): see FAQ.is_platform_shared above for the full rationale.
    is_platform_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # v0.4 (FR-027): see FAQ.creator_role_snapshot above for the full rationale.
    creator_role_snapshot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"InformationSource(id={self.id!r}, name={self.name!r}, type={self.source_type!r})"


class FAQQuestionCategory(Base):
    """M:N junction: FAQ <-> QuestionCategory (FR-016 multi-select).

    Not TenantScoped — membership is implied by the two FKs, which are
    themselves org-scoped rows; a junction row can never cross tenants
    because both sides are always looked up within the current org.
    """

    __tablename__ = "aa_faq_question_categories"

    faq_id: Mapped[int] = mapped_column(
        ForeignKey("aa_faqs.id", ondelete="CASCADE"), primary_key=True
    )
    question_category_id: Mapped[int] = mapped_column(
        ForeignKey("aa_question_categories.id", ondelete="CASCADE"), primary_key=True
    )


class FAQSourceCategory(Base):
    """M:N junction: FAQ <-> InformationSourceCategory (FR-016 multi-select)."""

    __tablename__ = "aa_faq_source_categories"

    faq_id: Mapped[int] = mapped_column(
        ForeignKey("aa_faqs.id", ondelete="CASCADE"), primary_key=True
    )
    source_category_id: Mapped[int] = mapped_column(
        ForeignKey("aa_information_source_categories.id", ondelete="CASCADE"),
        primary_key=True,
    )


class FAQSource(Base):
    """M:N junction: FAQ <-> InformationSource (FR-016 multi-select)."""

    __tablename__ = "aa_faq_sources"

    faq_id: Mapped[int] = mapped_column(
        ForeignKey("aa_faqs.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("aa_information_sources.id", ondelete="CASCADE"), primary_key=True
    )


class LLMFallbackMode(enum.StrEnum):
    """The two LLM fallback modes an admin may select per (source category,
    question category) pair (FR-009)."""

    RETRIEVAL_AUGMENTED = "retrieval_augmented"
    FRONTIER_GENERAL_KNOWLEDGE = "frontier_general_knowledge"


class LLMFallbackConfig(Base, TenantScoped):
    """Per-(information source category, question category) LLM fallback
    mode configuration (FR-009).

    DESIGN.md describes this as keyed by "information source category and
    question type"; this slot has no separate "question type" entity, so
    QuestionCategory (the existing FR-003/FR-015 classification entity) is
    used as the "question type" axis — the closest existing analog and the
    natural reading of FR-009 alongside FR-015.
    """

    __tablename__ = "aa_llm_fallback_configs"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "source_category_id",
            "question_category_id",
            name="uq_aa_llm_fallback_org_srccat_qcat",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("aa_information_source_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("aa_question_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mode: Mapped[str] = mapped_column(
        Enum(
            LLMFallbackMode,
            name="aa_llm_fallback_mode",
            native_enum=False,
            length=32,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"LLMFallbackConfig(id={self.id!r}, source_category_id={self.source_category_id!r}, "
            f"question_category_id={self.question_category_id!r}, mode={self.mode!r})"
        )


class QuestionAlert(Base, TenantScoped):
    """An in-app alert dispatched when both the deterministic and LLM
    fallback tiers fail to answer a question (FR-008).

    Recipients (Organization Administrators and Content Managers) are
    resolved and notified at dispatch time via the chassis notification
    producer (`app.notifications.service.notify`); this row is the
    durable, queryable record backing `GET /api/questions/alerts` and the
    acknowledge action.
    """

    __tablename__ = "aa_question_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unanswerable_question"
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    submitting_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    submitting_user_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    acknowledged_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return f"QuestionAlert(id={self.id!r}, acknowledged={self.acknowledged!r})"


# ═════════════════════════════════════════════════════════════════════════
# v0.3 increment — FR-017 through FR-022, SR-005 through SR-007, NFR-001
# ═════════════════════════════════════════════════════════════════════════
#
# New tables added by migration 0017 (additive-only — see Rule 9):
#   - aa_faq_generation_sessions    (FR-017: only the interaction-log-review
#     flow, T-007, stages candidates server-side; FR-018's information-source
#     flow, T-008, is entirely in-memory per its own acceptance criteria and
#     needs no staging table).
#   - aa_faq_generation_candidates
#
# New columns on existing tables (all nullable/defaulted — see the class
# docstrings above for the ones on aa_faqs / aa_information_sources /
# aa_information_source_categories / aa_interaction_logs).


class FAQGenerationStatus(enum.StrEnum):
    """Lifecycle of a T-007/FR-017 FAQ generation session.

    NFR-001's approval gate is what this enum exists to make explicit:
    a session sits in PENDING_REVIEW (candidates staged, nothing in `aa_faqs`
    yet) until an authorized user calls the confirm endpoint, which is the
    ONLY path that ever transitions a session to CONFIRMED and the ONLY path
    that ever writes to `aa_faqs` for LLM-generated content.
    """

    PENDING_REVIEW = "pending_review"
    CONFIRMED = "confirmed"


class FAQGenerationCandidateStatus(enum.StrEnum):
    """Per-candidate outcome once its parent session is confirmed."""

    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class FAQGenerationSession(Base, TenantScoped):
    """A staged, human-reviewable FAQ-generation session (FR-017, T-007).

    Exists ONLY for the interaction-log-review flow — FR-018's
    information-source flow (T-008) is explicitly in-memory-only per its own
    acceptance criteria and never creates a row here. `source_type` is
    therefore always `"interaction_logs"` today; the column is kept (rather
    than hardcoded) so a future session-backed generation flow does not need
    a schema change to plug in.
    """

    __tablename__ = "aa_faq_generation_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="interaction_logs"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=FAQGenerationStatus.PENDING_REVIEW.value
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return f"FAQGenerationSession(id={self.id!r}, status={self.status!r})"


class FAQGenerationCandidate(Base, TenantScoped):
    """One LLM-drafted FAQ candidate staged for human review (FR-017,
    NFR-001, T-007).

    Never a source of truth on its own: it is written to `aa_faqs` (via a
    real, validated `FAQ` + junction rows) ONLY when its parent session is
    explicitly confirmed with this candidate's id in the approved set.
    `recommended_*_ids_json` mirror the JSON-string convention already used
    by `FAQ.citations_json`/`InteractionLog.sources_json` elsewhere in this
    slot, rather than a fourth set of M:N junction tables for what is, until
    confirmed, disposable draft data.
    """

    __tablename__ = "aa_faq_generation_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("aa_faq_generation_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # JSON string: [1, 2, 3] — LLM-recommended ids, advisory only; validated
    # for real at confirm time (service.py's _resolve_ids_in_org).
    recommended_question_category_ids_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]"
    )
    recommended_source_category_ids_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]"
    )
    recommended_source_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=FAQGenerationCandidateStatus.PENDING_REVIEW.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"FAQGenerationCandidate(id={self.id!r}, session_id={self.session_id!r})"
