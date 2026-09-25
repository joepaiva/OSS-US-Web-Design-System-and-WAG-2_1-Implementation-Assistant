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

All tables inherit (Base, TenantScoped) for automatic org_id isolation.
Interaction logs are append-only by application convention (no UPDATE/DELETE
routes exposed); the column set captures all fields required by FR-006 and
SR-003.

Soft-delete: NOT used in this slot (ARCHITECTURE.md §2.9 — opt-in only).
Retention: interaction logs carry retained_until via RetainableFor mixin
           to support future SI-12 archival jobs.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
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

    PII fields: user_id (FK), question_text (may contain user phrasing).
    Access is restricted by application-layer RBAC (SR-003):
      - End users may only read their own records (filtered by user_id).
      - Org admins may read all records in their org (TenantScoped).
      - Platform admins may read across all orgs.
      - No UPDATE or DELETE routes are exposed (append-only).

    `session_id` groups multi-turn exchanges (FR-005). It is a
    caller-supplied opaque string (UUID recommended) that the client
    generates at session start and sends with every turn.

    `rating` is nullable — null means the user did not submit a rating
    (FR-006 AC: rating field recorded as null or unrated).
    True = thumbs up, False = thumbs down.

    `sources_json` stores a JSON-serialised list of source identifiers
    used when generating the response (FR-006).
    """

    __tablename__ = "aa_interaction_logs"

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
