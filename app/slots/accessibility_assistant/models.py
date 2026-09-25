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

Tables defined here:
  - aa_question_categories   (FR-003: browse FAQs by category)
  - aa_faqs                  (FR-003: FAQ entries with answers)
  - aa_interaction_logs      (FR-006: persistent interaction records; PT-1 PII)

All tables inherit (Base, TenantScoped) for automatic org_id isolation.
Interaction logs are append-only by application convention (no UPDATE/DELETE
routes exposed); the column set captures all fields required by FR-006 and
SR-003.

Soft-delete: NOT used in this slot (ARCHITECTURE.md §2.9 — opt-in only).
Retention: interaction logs carry retained_until via RetainableFor mixin
           to support future SI-12 archival jobs.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
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
