"""ia-2(1): mfa/totp state on users + backup codes (chassis-program v1.0.0)

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-02

NIST 800-53 IA-2(1) (Network Access to Privileged Accounts — MFA)
compliance, mandatory for this package's FISMA-Moderate baseline
(chassis-program FISMA-CONTROL-DELTA-LOW-VS-MODERATE.md §4). Adds:

  users.mfa_enabled       — bool, default false
  users.mfa_secret        — AES-256-GCM ciphertext (app/auth/mfa_crypto.py),
                             nullable (null until enrollment starts)
  users.mfa_enrolled_at   — timestamptz, nullable (set on confirm_enrollment)

  mfa_backup_codes        — new table, one row per single-use backup code,
                             bcrypt-hashed (same discipline as passwords),
                             FK to users with ON DELETE CASCADE.

Downgrade drops the table and the three columns, restoring pre-MFA state.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "mfa_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("mfa_secret", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("mfa_enrolled_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "mfa_backup_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "used", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_mfa_backup_codes_user_id", "mfa_backup_codes", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_mfa_backup_codes_user_id", table_name="mfa_backup_codes")
    op.drop_table("mfa_backup_codes")
    op.drop_column("users", "mfa_enrolled_at")
    op.drop_column("users", "mfa_secret")
    op.drop_column("users", "mfa_enabled")
