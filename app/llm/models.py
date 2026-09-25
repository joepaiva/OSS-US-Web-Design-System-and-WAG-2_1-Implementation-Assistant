"""LLM provider-key + access-policy ORM models (chassis v0.9).

Two purely additive tables (so both `Base.metadata.create_all` in tests and
Alembic in prod create them without ALTERing existing tables):

  - `llm_provider_keys` — an encrypted provider API key. `organization_id`
    NULL means a platform-SHARED key; a set value means an ORG-scoped key.
  - `org_llm_access` — per-org policy row gating whether an org may fall
    back to the shared key. Absence of a row = deny (default-closed).

Rule-7 parity: `encrypted_key` is AES-256-GCM ciphertext (see crypto.py).
Plaintext provider keys never touch this table.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class LLMProviderKey(Base):
    """An encrypted LLM provider API key, org-scoped or platform-shared."""

    __tablename__ = "llm_provider_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    # NULL → platform-shared key; set → org-scoped key.
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="true"
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    @property
    def is_shared(self) -> bool:
        return self.organization_id is None

    def __repr__(self) -> str:
        scope = "shared" if self.is_shared else f"org={self.organization_id}"
        return f"LLMProviderKey(id={self.id!r}, provider={self.provider!r}, {scope})"


class OrgLLMAccess(Base):
    """Per-org policy: may this org fall back to the platform-shared key?"""

    __tablename__ = "org_llm_access"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_org_llm_access_org"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    allow_shared_key: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"OrgLLMAccess(org={self.organization_id!r}, "
            f"allow_shared_key={self.allow_shared_key!r})"
        )
