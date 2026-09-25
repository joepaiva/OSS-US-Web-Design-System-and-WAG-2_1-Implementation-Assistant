"""AuditLog ORM model — append-only.

By chassis convention, audit rows are NEVER updated and NEVER deleted.
Schema-level enforcement (revoke UPDATE/DELETE on the role) is a deploy-time
concern handled in DEPLOYMENT.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AuditLog(Base):
    """A single audit event.

    Nullable columns model real-world cases:
      - organization_id NULL → chassis-admin action (cross-tenant)
      - user_id NULL → system action (RQ worker, startup seeder, etc.)
      - entity_id NULL → action that doesn't target a specific row
                         (e.g. failed login attempt)

    `details` is JSONB-shaped at the dialect layer (Postgres) and falls
    back to JSON on dialects without JSONB. Keep it small and structured;
    NEVER dump PII raw.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return f"AuditLog(id={self.id!r}, action={self.action!r}, user_id={self.user_id!r})"
