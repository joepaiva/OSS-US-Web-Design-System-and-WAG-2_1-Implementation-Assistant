"""au-11: audit_logs_archive table (chassis v0.6)

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-05

NIST 800-53 AU-11 retention strictest-of-three (FISMA M / FedRAMP M / IL-2):
6 years online or archived. The chassis splits storage into two tables:

  audit_logs           — online; queried by app endpoints; rows older than
                         Settings.audit_retention_days (default 365) get
                         moved to the archive by app/audit/tasks.py
  audit_logs_archive   — cold storage; same shape as audit_logs but without
                         the FK constraints that would block bulk-load.

Operators who need stricter "online only" retention can drop the archival
job entirely and let audit_logs grow indefinitely. Operators in IL-2 deploys
can mount audit_logs_archive on cheaper storage (e.g. an S3-backed
foreign table) for the 6-year retention requirement.

This migration creates the archive table. The migration does NOT
populate it — the archival job populates rows as audit_logs ages.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_logs_archive",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_audit_logs_archive_organization_id",
        "audit_logs_archive",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_archive_user_id",
        "audit_logs_archive",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_archive_action",
        "audit_logs_archive",
        ["action"],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_archive_created_at",
        "audit_logs_archive",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_archive_created_at", table_name="audit_logs_archive")
    op.drop_index("ix_audit_logs_archive_action", table_name="audit_logs_archive")
    op.drop_index("ix_audit_logs_archive_user_id", table_name="audit_logs_archive")
    op.drop_index("ix_audit_logs_archive_organization_id", table_name="audit_logs_archive")
    op.drop_table("audit_logs_archive")
