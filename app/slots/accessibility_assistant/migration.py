# ruff: noqa: F821
# mypy: ignore-errors
# F821 / mypy name-defined errors are suppressed file-wide: `op`/`sa` are
# injected by the Alembic migration runner into the real versions/ files
# this document mirrors (see the module docstring) and are deliberately
# not imported here, so this reference copy is not standalone-valid
# Python. Pre-existing from the v0.1 increment; silenced here (rather than
# left as noise) while touching this file for the v0.2 update.
"""Accessibility Assistant slot — Alembic migration body (cumulative).

This file is a readable, cumulative reference copy of the slot's full
schema-as-DDL — it is NOT imported or executed by Alembic (see
`migrations/versions/0015_accessibility_assistant_slot.py`,
`migrations/versions/0016_accessibility_assistant_slot_v0_2.py`, and
`migrations/versions/0017_accessibility_assistant_slot_v0_3.py`, which are
the real, independently-numbered, additive revisions Alembic runs).

v0.1 (migration 0015) created the three original slot tables:
  - aa_question_categories
  - aa_faqs
  - aa_interaction_logs

v0.2 (migration 0016) added, additively (see that file for the exact,
authoritative DDL):
  - two nullable columns on aa_question_categories / aa_faqs
  - aa_information_source_categories, aa_information_sources
  - aa_faq_question_categories, aa_faq_source_categories, aa_faq_sources
  - aa_llm_fallback_configs
  - aa_question_alerts

v0.3 (migration 0017) added, additively (see that file for the exact,
authoritative DDL):
  - aa_interaction_logs.helpfulness_rating (+ CHECK constraint) (FR-019)
  - aa_information_source_categories.is_platform_shared (FR-020)
  - aa_information_sources.is_platform_shared (FR-020)
  - aa_faqs.is_platform_shared (FR-020)
  - aa_faq_generation_sessions, aa_faq_generation_candidates (FR-017)

v0.4 (migration 0018) added, additively (see that file for the exact,
authoritative DDL):
  - aa_information_source_categories.creator_role_snapshot (FR-027)
  - aa_information_sources.creator_role_snapshot (FR-027)
  - aa_faqs.creator_role_snapshot (FR-027)

downgrade() drops everything in reverse dependency order.

Columns match models.py exactly. The `op` and `sa` names are injected
by the Alembic migration runner — do not import them here.
"""


def upgrade() -> None:
    # aa_question_categories
    op.create_table(
        "aa_question_categories",
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
        sa.UniqueConstraint("org_id", "name", name="uq_aa_qcat_org_name"),
    )
    op.create_index(
        "ix_aa_question_categories_org_id",
        "aa_question_categories",
        ["org_id"],
    )

    # aa_faqs
    op.create_table(
        "aa_faqs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "org_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_category_id",
            sa.Integer(),
            sa.ForeignKey("aa_question_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("reasoning", sa.Text(), nullable=False, server_default=""),
        sa.Column("citations_json", sa.Text(), nullable=False, server_default="[]"),
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
    op.create_index("ix_aa_faqs_org_id", "aa_faqs", ["org_id"])
    op.create_index(
        "ix_aa_faqs_question_category_id",
        "aa_faqs",
        ["question_category_id"],
    )

    # aa_interaction_logs
    op.create_table(
        "aa_interaction_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "org_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_category_id",
            sa.Integer(),
            sa.ForeignKey("aa_question_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("reasoning", sa.Text(), nullable=False, server_default=""),
        sa.Column("sources_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("rating", sa.Boolean(), nullable=True),
        sa.Column(
            "retained_until",
            sa.DateTime(timezone=True),
            nullable=True,
            comment=(
                "SI-12: row expires after this timestamp; archival jobs use "
                "this column to select rows for offline archival. NULL = no "
                "scheduled expiration (subject to chassis-wide AU-11 only)."
            ),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_aa_interaction_logs_org_id", "aa_interaction_logs", ["org_id"]
    )
    op.create_index(
        "ix_aa_interaction_logs_user_id", "aa_interaction_logs", ["user_id"]
    )
    op.create_index(
        "ix_aa_interaction_logs_question_category_id",
        "aa_interaction_logs",
        ["question_category_id"],
    )
    op.create_index(
        "ix_aa_interaction_logs_session_id",
        "aa_interaction_logs",
        ["session_id"],
    )
    op.create_index(
        "ix_aa_interaction_logs_created_at",
        "aa_interaction_logs",
        ["created_at"],
    )
    op.create_index(
        "ix_aa_interaction_logs_retained_until",
        "aa_interaction_logs",
        ["retained_until"],
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_index(
        "ix_aa_interaction_logs_retained_until",
        table_name="aa_interaction_logs",
    )
    op.drop_index(
        "ix_aa_interaction_logs_created_at",
        table_name="aa_interaction_logs",
    )
    op.drop_index(
        "ix_aa_interaction_logs_session_id",
        table_name="aa_interaction_logs",
    )
    op.drop_index(
        "ix_aa_interaction_logs_question_category_id",
        table_name="aa_interaction_logs",
    )
    op.drop_index(
        "ix_aa_interaction_logs_user_id",
        table_name="aa_interaction_logs",
    )
    op.drop_index(
        "ix_aa_interaction_logs_org_id",
        table_name="aa_interaction_logs",
    )
    op.drop_table("aa_interaction_logs")

    op.drop_index(
        "ix_aa_faqs_question_category_id",
        table_name="aa_faqs",
    )
    op.drop_index("ix_aa_faqs_org_id", table_name="aa_faqs")
    op.drop_table("aa_faqs")

    op.drop_index(
        "ix_aa_question_categories_org_id",
        table_name="aa_question_categories",
    )
    op.drop_table("aa_question_categories")
