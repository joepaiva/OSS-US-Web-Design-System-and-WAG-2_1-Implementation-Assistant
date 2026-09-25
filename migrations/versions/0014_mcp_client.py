"""mcp client: mcp_server_connections

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-10

Adds the single additive table backing the MCP client capability
(FR-MCPCLIENT, app/mcp/models.py). Org-scoped (organization_id NOT NULL --
unlike llm_provider_keys, there is no platform-shared variant); enabled
defaults to false (registering a connection does not, by itself, expose
its tools).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_server_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("encrypted_credential", sa.Text(), nullable=True),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_mcp_server_connections_organization_id",
        "mcp_server_connections",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mcp_server_connections_organization_id",
        table_name="mcp_server_connections",
    )
    op.drop_table("mcp_server_connections")
