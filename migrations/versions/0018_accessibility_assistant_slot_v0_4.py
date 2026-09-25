"""accessibility_assistant slot v0.4: platform-sharing eligibility snapshot

Revision ID: 0018
Revises: 0017

Additive-only (Rule 9): adds one new NULLABLE column to each of the three
platform-shareable tables. No column is dropped, renamed, or retyped, and
0015/0016/0017's own bodies are left untouched.

New column on three existing tables (FR-027):
  - aa_information_source_categories.creator_role_snapshot
  - aa_information_sources.creator_role_snapshot
  - aa_faqs.creator_role_snapshot

`creator_role_snapshot` records, once at INSERT time and never updated
thereafter, whether the resource's creator held the Platform Administrator
role at creation ("platform_admin") or not ("other"). NULL means the row
predates this column (or was inserted directly via ORM/fixture, bypassing
the service layer) and is therefore never eligible for platform-level
sharing — a safe, fail-closed default for existing data. See service.py's
`_share_resource` for the enforcement and TASKS.md T-XXX (FR-027) for the
full rationale.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "aa_information_source_categories",
        sa.Column("creator_role_snapshot", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "aa_information_sources",
        sa.Column("creator_role_snapshot", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "aa_faqs",
        sa.Column("creator_role_snapshot", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("aa_faqs", "creator_role_snapshot")
    op.drop_column("aa_information_sources", "creator_role_snapshot")
    op.drop_column("aa_information_source_categories", "creator_role_snapshot")
