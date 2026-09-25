"""Approval Request ORM model — the reference state-machine TenantScoped model.

Highlights for LLM slot authors:
  - Inherits (Base, TenantScoped) — same chassis multi-tenancy invariant
    as slots/example/ Notes.
  - Status column is a typed PostgreSQL enum (server-side validation).
  - submitted_at / decided_at timestamps track state-transition history
    without a separate audit table — the chassis @audited decorator
    handles audit log entries via service-layer side effects.

The Status enum is in this file (not service.py) because models.py is
imported first at chassis startup; keeping the enum here means service.py
and routes.py can import it cleanly.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TenantScoped


class ApprovalStatus(enum.StrEnum):
    """Lifecycle states for an approval request.

    Inherits enum.StrEnum (Python 3.11+) so Pydantic v2 serializes the
    value, not the repr -- the modern-idiom replacement for the
    `class X(str, enum.Enum)` pattern (ruff UP042).

    Transitions (see service.py:ALLOWED_TRANSITIONS for the enforced map):
        DRAFT     → SUBMITTED (the requester submits for approval)
        SUBMITTED → APPROVED  (approver accepts)
        SUBMITTED → REJECTED  (approver declines)
        APPROVED, REJECTED are TERMINAL — no transitions out.
    """

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalRequest(Base, TenantScoped):
    """An approval request — title + body + lifecycle state.

    Standard chassis conventions:
      - `org_id` provided by TenantScoped — DO NOT redeclare it.
      - `requester_id` references the User who created the request;
        survives org removal via the chassis CASCADE on org_id.
      - `approver_id` is nullable until a transition out of SUBMITTED.
    """

    __tablename__ = "example_approval_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    requester_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Lifecycle. PostgreSQL enum gives us server-side validation in
    # addition to the application-level state machine in service.py.
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="example_approval_status"),
        nullable=False,
        default=ApprovalStatus.DRAFT,
        index=True,
    )

    # Transition timestamps. Nullable because not all rows reach all states.
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approver_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

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
            f"ApprovalRequest(id={self.id!r}, org_id={self.org_id!r}, "
            f"status={self.status!r}, title={self.title!r})"
        )
