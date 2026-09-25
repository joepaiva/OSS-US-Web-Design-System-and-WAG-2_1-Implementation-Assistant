"""Greeting slot ORM models — TenantScoped, per DESIGN.md §4.

GreetingEvent: one row per greeting request (FR-001..003, BR-001, BR-003).
No delete method exists anywhere in this slot — NFR-005 forbids any
application deletion path, and the absence is the design decision (mirrors
the draft's DESIGN.md §4 exactly).

GreetingOrgSettings: the slot-owned home for BR-004 ("every organization
MUST have exactly one default locale"). The draft's design assumes a
"tenant's configured default locale" exists but doesn't model where it
lives — the chassis's own Organization model is a chassis-owned entity
this slot must not modify (see app/slots/example's own note: "Chassis-owned
entities... are not modelled here"). One row per org, lazily created with
`en-US` on first access (app/slots/greeting/repository.py), keeps BR-004
true without touching chassis-owned files outside the two marked
extension points.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TenantScoped


class GreetingEvent(Base, TenantScoped):
    """FR-001/002/005, BR-001/003, NFR-002/005."""

    __tablename__ = "greeting_events"
    __table_args__ = (
        # Org-leading composite indexes — a non-org-leading index would
        # permit a query plan that scans across tenants (BR-001), per the
        # draft DESIGN.md §4.
        Index("ix_greeting_events_org_created", "org_id", "created_at"),
        Index(
            "ix_greeting_events_org_locale_created",
            "org_id",
            "locale_used",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    locale_used: Mapped[str] = mapped_column(String(10), nullable=False)
    locale_requested: Mapped[str] = mapped_column(String(10), nullable=False)
    locale_fallback: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # LLM-delta addition (not in the draft): which provider actually served
    # this greeting's text. "static" is the draft's original, deterministic
    # TranslationProvider; "llm" is this package's opt-in addition. Lets the
    # demo (and the greeting history admin view) visibly show which path
    # served each request.
    translation_source: Mapped[str] = mapped_column(
        String(10), nullable=False, default="static", server_default="static"
    )
    name_supplied: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return f"GreetingEvent(id={self.id!r}, org_id={self.org_id!r}, locale_used={self.locale_used!r})"


class GreetingOrgSettings(Base, TenantScoped):
    """BR-004 — exactly one default locale per organization. Slot-owned,
    not a modification of the chassis Organization model."""

    __tablename__ = "greeting_org_settings"
    __table_args__ = (
        UniqueConstraint("org_id", name="uq_greeting_org_settings_org_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    default_locale: Mapped[str] = mapped_column(
        String(10), nullable=False, default="en-US", server_default="en-US"
    )

    def __repr__(self) -> str:
        return f"GreetingOrgSettings(org_id={self.org_id!r}, default_locale={self.default_locale!r})"
