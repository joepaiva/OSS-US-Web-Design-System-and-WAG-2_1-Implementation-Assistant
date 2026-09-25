"""accessibility_assistant slot v0.3: helpfulness rating, platform sharing,
FAQ generation staging tables

Revision ID: 0017
Revises: 0016

Additive-only (Rule 9): every statement below either creates a new table,
adds a new NULLABLE/DEFAULTED column to an existing table, or adds a new
CHECK constraint on a new column. No column is dropped, renamed, or
retyped, and 0015/0016's own bodies are left untouched.

New columns on existing tables (FR-019, FR-020):
  - aa_interaction_logs.helpfulness_rating (+ CHECK constraint)
  - aa_information_source_categories.is_platform_shared
  - aa_information_sources.is_platform_shared
  - aa_faqs.is_platform_shared

New tables (FR-017):
  - aa_faq_generation_sessions
  - aa_faq_generation_candidates
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── FR-019: write-once helpfulness rating on aa_interaction_logs ──────
    op.add_column(
        "aa_interaction_logs",
        sa.Column("helpfulness_rating", sa.String(length=16), nullable=True),
    )
    op.create_check_constraint(
        "ck_aa_interaction_logs_helpfulness_rating",
        "aa_interaction_logs",
        "helpfulness_rating IN ('helpful', 'unhelpful') OR helpfulness_rating IS NULL",
    )

    # ── FR-020: platform-level sharing flag on the three shareable types ──
    op.add_column(
        "aa_information_source_categories",
        sa.Column(
            "is_platform_shared", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "aa_information_sources",
        sa.Column(
            "is_platform_shared", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "aa_faqs",
        sa.Column(
            "is_platform_shared", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )

    # ── FR-017: FAQ generation staging tables (interaction-log flow only) ─
    op.create_table(
        "aa_faq_generation_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "org_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_type", sa.String(length=32), nullable=False, server_default="interaction_logs"
        ),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="pending_review"
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
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_aa_faq_generation_sessions_org_id", "aa_faq_generation_sessions", ["org_id"]
    )
    op.create_index(
        "ix_aa_faq_generation_sessions_created_at",
        "aa_faq_generation_sessions",
        ["created_at"],
    )

    op.create_table(
        "aa_faq_generation_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "org_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("aa_faq_generation_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "recommended_question_category_ids_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "recommended_source_category_ids_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "recommended_source_ids_json", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="pending_review"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_aa_faq_generation_candidates_org_id", "aa_faq_generation_candidates", ["org_id"]
    )
    op.create_index(
        "ix_aa_faq_generation_candidates_session_id",
        "aa_faq_generation_candidates",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_aa_faq_generation_candidates_session_id", table_name="aa_faq_generation_candidates"
    )
    op.drop_index(
        "ix_aa_faq_generation_candidates_org_id", table_name="aa_faq_generation_candidates"
    )
    op.drop_table("aa_faq_generation_candidates")

    op.drop_index(
        "ix_aa_faq_generation_sessions_created_at", table_name="aa_faq_generation_sessions"
    )
    op.drop_index(
        "ix_aa_faq_generation_sessions_org_id", table_name="aa_faq_generation_sessions"
    )
    op.drop_table("aa_faq_generation_sessions")

    op.drop_column("aa_faqs", "is_platform_shared")
    op.drop_column("aa_information_sources", "is_platform_shared")
    op.drop_column("aa_information_source_categories", "is_platform_shared")

    op.drop_constraint(
        "ck_aa_interaction_logs_helpfulness_rating", "aa_interaction_logs", type_="check"
    )
    op.drop_column("aa_interaction_logs", "helpfulness_rating")
