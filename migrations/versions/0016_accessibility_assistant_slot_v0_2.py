"""accessibility_assistant slot v0.2: information sources, FAQ multi-select,
LLM fallback config, question alerts

Revision ID: 0016
Revises: 0015

Additive-only (Rule 9): every statement below either creates a new table or
adds a new NULLABLE column to an existing table. No column is dropped,
renamed, or retyped, and 0015's own body is left untouched.

New tables (FR-010, FR-011..FR-014, FR-016, FR-009, FR-008):
  - aa_information_source_categories
  - aa_information_sources
  - aa_faq_question_categories / aa_faq_source_categories / aa_faq_sources
  - aa_llm_fallback_configs
  - aa_question_alerts

New columns on existing v0.1 tables (both nullable — existing rows unaffected):
  - aa_question_categories.created_by_user_id  (FR-015)
  - aa_faqs.created_by_user_id, aa_faqs.match_pattern  (FR-016, FR-007)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── New columns on existing v0.1 tables (additive, nullable) ──────────
    op.add_column(
        "aa_question_categories",
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "aa_faqs",
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "aa_faqs",
        sa.Column("match_pattern", sa.Text(), nullable=True),
    )

    # ── aa_information_source_categories (FR-010) ─────────────────────────
    op.create_table(
        "aa_information_source_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "org_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("org_id", "name", name="uq_aa_srccat_org_name"),
    )
    op.create_index(
        "ix_aa_information_source_categories_org_id",
        "aa_information_source_categories",
        ["org_id"],
    )

    # ── aa_information_sources (FR-011..FR-014) ───────────────────────────
    op.create_table(
        "aa_information_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "org_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("aa_information_source_categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("folder_path", sa.Text(), nullable=True),
        sa.Column("github_url", sa.Text(), nullable=True),
        sa.Column("mcp_server_address", sa.Text(), nullable=True),
        sa.Column("credentials_encrypted", sa.Text(), nullable=True),
        sa.Column(
            "test_status", sa.String(length=16), nullable=False, server_default="pending"
        ),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_aa_information_sources_org_id", "aa_information_sources", ["org_id"])
    op.create_index(
        "ix_aa_information_sources_category_id", "aa_information_sources", ["category_id"]
    )

    # ── FAQ multi-select junction tables (FR-016) ──────────────────────────
    op.create_table(
        "aa_faq_question_categories",
        sa.Column(
            "faq_id", sa.Integer(), sa.ForeignKey("aa_faqs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "question_category_id",
            sa.Integer(),
            sa.ForeignKey("aa_question_categories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "aa_faq_source_categories",
        sa.Column(
            "faq_id", sa.Integer(), sa.ForeignKey("aa_faqs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "source_category_id",
            sa.Integer(),
            sa.ForeignKey("aa_information_source_categories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "aa_faq_sources",
        sa.Column(
            "faq_id", sa.Integer(), sa.ForeignKey("aa_faqs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "source_id",
            sa.Integer(),
            sa.ForeignKey("aa_information_sources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # ── aa_llm_fallback_configs (FR-009) ───────────────────────────────────
    op.create_table(
        "aa_llm_fallback_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "org_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_category_id",
            sa.Integer(),
            sa.ForeignKey("aa_information_source_categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_category_id",
            sa.Integer(),
            sa.ForeignKey("aa_question_categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "org_id",
            "source_category_id",
            "question_category_id",
            name="uq_aa_llm_fallback_org_srccat_qcat",
        ),
    )
    op.create_index(
        "ix_aa_llm_fallback_configs_org_id", "aa_llm_fallback_configs", ["org_id"]
    )
    op.create_index(
        "ix_aa_llm_fallback_configs_source_category_id",
        "aa_llm_fallback_configs",
        ["source_category_id"],
    )
    op.create_index(
        "ix_aa_llm_fallback_configs_question_category_id",
        "aa_llm_fallback_configs",
        ["question_category_id"],
    )

    # ── aa_question_alerts (FR-008) ────────────────────────────────────────
    op.create_table(
        "aa_question_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "org_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "alert_type",
            sa.String(length=32),
            nullable=False,
            server_default="unanswerable_question",
        ),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column(
            "submitting_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "submitting_user_name", sa.String(length=255), nullable=False, server_default=""
        ),
        sa.Column(
            "acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "acknowledged_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_aa_question_alerts_org_id", "aa_question_alerts", ["org_id"])
    op.create_index(
        "ix_aa_question_alerts_created_at", "aa_question_alerts", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_aa_question_alerts_created_at", table_name="aa_question_alerts")
    op.drop_index("ix_aa_question_alerts_org_id", table_name="aa_question_alerts")
    op.drop_table("aa_question_alerts")

    op.drop_index(
        "ix_aa_llm_fallback_configs_question_category_id",
        table_name="aa_llm_fallback_configs",
    )
    op.drop_index(
        "ix_aa_llm_fallback_configs_source_category_id",
        table_name="aa_llm_fallback_configs",
    )
    op.drop_index("ix_aa_llm_fallback_configs_org_id", table_name="aa_llm_fallback_configs")
    op.drop_table("aa_llm_fallback_configs")

    op.drop_table("aa_faq_sources")
    op.drop_table("aa_faq_source_categories")
    op.drop_table("aa_faq_question_categories")

    op.drop_index(
        "ix_aa_information_sources_category_id", table_name="aa_information_sources"
    )
    op.drop_index("ix_aa_information_sources_org_id", table_name="aa_information_sources")
    op.drop_table("aa_information_sources")

    op.drop_index(
        "ix_aa_information_source_categories_org_id",
        table_name="aa_information_source_categories",
    )
    op.drop_table("aa_information_source_categories")

    op.drop_column("aa_faqs", "match_pattern")
    op.drop_column("aa_faqs", "created_by_user_id")
    op.drop_column("aa_question_categories", "created_by_user_id")
