"""MCP server connection ORM model (chassis v1.1.0, FR-MCPCLIENT).

One purely additive table so both `Base.metadata.create_all` (tests) and
Alembic (prod) create it without ALTERing existing tables.

Unlike `LLMProviderKey` (`app/llm/models.py`), there is no platform-shared
variant here -- `organization_id` is always NOT NULL. An MCP server is
inherently a specific external integration one org owns; the shared-key
concept that makes sense for an LLM provider does not apply
(MCP-CLIENT-REQUIREMENTS.md §3). No `TenantScoped` mixin is used -- that
mixin's column is `org_id`; this table follows `llm_provider_keys`'s own
hand-rolled `organization_id` naming instead, matching the sibling table
whose encryption this one reuses.

Rule-7 parity: `encrypted_credential` is AES-256-GCM ciphertext produced by
`app/llm/crypto.py`'s `encrypt()` -- reused directly, never reimplemented.
Plaintext credentials never touch this table.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MCPServerConnection(Base):
    """An admin-registered connection to an external MCP server.

    `enabled` defaults to False (server_default "false") -- registering a
    connection does not, by itself, expose its tools to the LLM
    (FR-MCPCLIENT-4). `encrypted_credential` is nullable: a server with no
    credential (an unauthenticated internal MCP server) is a valid,
    supported configuration (FR-MCPCLIENT-2).
    """

    __tablename__ = "mcp_server_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    encrypted_credential: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false"
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

    def __repr__(self) -> str:
        return (
            f"MCPServerConnection(id={self.id!r}, org_id={self.organization_id!r}, "
            f"name={self.name!r}, enabled={self.enabled!r})"
        )
