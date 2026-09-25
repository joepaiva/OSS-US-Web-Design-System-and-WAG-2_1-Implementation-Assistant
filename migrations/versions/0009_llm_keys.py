"""llm: provider keys + per-org shared-access policy (chassis v0.9)

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_provider_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("encrypted_key", sa.Text(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
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
        "ix_llm_provider_keys_organization_id",
        "llm_provider_keys",
        ["organization_id"],
    )
    op.create_index(
        "ix_llm_provider_keys_provider", "llm_provider_keys", ["provider"]
    )

    op.create_table(
        "org_llm_access",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "allow_shared_key",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("organization_id", name="uq_org_llm_access_org"),
    )
    op.create_index(
        "ix_org_llm_access_organization_id", "org_llm_access", ["organization_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_org_llm_access_organization_id", table_name="org_llm_access")
    op.drop_table("org_llm_access")
    op.drop_index("ix_llm_provider_keys_provider", table_name="llm_provider_keys")
    op.drop_index(
        "ix_llm_provider_keys_organization_id", table_name="llm_provider_keys"
    )
    op.drop_table("llm_provider_keys")
