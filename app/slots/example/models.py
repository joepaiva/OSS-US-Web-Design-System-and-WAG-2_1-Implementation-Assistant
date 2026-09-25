"""Note ORM model — the reference TenantScoped model.

LLMs mirror this pattern EXACTLY for new slots:
  - Inherits (Base, TenantScoped) — org_id auto-filter + auto-inject
  - Mapped[T] = mapped_column(...) — SQLAlchemy 2.0 typed form
  - All datetime columns are timezone-aware
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TenantScoped


class Note(Base, TenantScoped):
    """A note belonging to an org and authored by a user.

    `org_id` is provided by TenantScoped — DO NOT redeclare it.
    `author_id` is the User who created the note; survives org removal
    via the chassis CASCADE on org_id, so we don't need ondelete here.
    """

    __tablename__ = "example_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
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
        return f"Note(id={self.id!r}, org_id={self.org_id!r}, title={self.title!r})"
