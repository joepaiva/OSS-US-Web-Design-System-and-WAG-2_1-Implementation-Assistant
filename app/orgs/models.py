"""Organization + Membership ORM models — SQLAlchemy 2.0 typed.

Org represents a tenant. Every business table in `app/slots/` that should
be tenant-scoped inherits `TenantScoped` (defined in `app.db`).

Membership is the M:N user ↔ org join, carrying a per-org role and an
`is_default` flag so a user with multiple orgs has a deterministic default
context.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Organization(Base):
    """A tenant. `slug` is the URL-safe lowercase identifier."""

    __tablename__ = "organizations"
    __table_args__ = (UniqueConstraint("slug", name="uq_organizations_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
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
        return f"Organization(id={self.id!r}, slug={self.slug!r})"


class Membership(Base):
    """User ↔ Org join with a per-org role and a default-context flag.

    A user can be in 0..N orgs. Their `is_default=True` membership wins
    when resolving current_org; if none flagged, the lowest membership id
    wins (chassis convention; can be overridden by the route layer).
    """

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_memberships_user_org"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    org_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Optional per-org role override. NULL means "use global RBAC role".
    role_id: Mapped[int | None] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"Membership(user_id={self.user_id!r}, org_id={self.org_id!r})"
