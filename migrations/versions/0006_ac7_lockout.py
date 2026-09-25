"""ac-7: account lockout state on users (chassis v0.6)

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-05

NIST 800-53 AC-7 (Unsuccessful Logon Attempts) compliance — adds
state-tracking columns to the users table so app/auth/service.py can
implement the strictest-of-three (FISMA M / FedRAMP M / IL-2) policy:
3 attempts within 15-minute window → 30-minute lockout.

Columns added:
  failed_login_attempts  — int, default 0 (count within current window)
  last_failed_login_at   — timestamptz, nullable (used to detect window
                           expiry; on next failure outside window, reset
                           counter to 1 instead of incrementing)
  locked_until           — timestamptz, nullable + indexed (lookups in
                           authenticate() check `locked_until > now()`
                           before the bcrypt verify — keeps the lock
                           path fast so the lockout actually rate-limits
                           brute-force attempts)

Downgrade restores the v0.5 state (columns dropped).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "failed_login_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "last_failed_login_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "locked_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_users_locked_until",
        "users",
        ["locked_until"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_users_locked_until", table_name="users")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "last_failed_login_at")
    op.drop_column("users", "failed_login_attempts")
