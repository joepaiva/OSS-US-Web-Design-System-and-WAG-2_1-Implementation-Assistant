"""greeting slot: greeting_events + greeting_org_settings

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-02

Adds the two tables backing the CP-B.5 Greeting Service demo slot
(app/slots/greeting/models.py). Both are additive and org-scoped
(TenantScoped). greeting_events has no delete path anywhere in the
application (NFR-005) — this migration does not add one either.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "greeting_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "org_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("locale_used", sa.String(length=10), nullable=False),
        sa.Column("locale_requested", sa.String(length=10), nullable=False),
        sa.Column(
            "locale_fallback", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "translation_source",
            sa.String(length=10),
            nullable=False,
            server_default="static",
        ),
        sa.Column("name_supplied", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_greeting_events_org_id", "greeting_events", ["org_id"])
    op.create_index(
        "ix_greeting_events_actor_user_id", "greeting_events", ["actor_user_id"]
    )
    op.create_index(
        "ix_greeting_events_created_at", "greeting_events", ["created_at"]
    )
    op.create_index(
        "ix_greeting_events_org_created",
        "greeting_events",
        ["org_id", "created_at"],
    )
    op.create_index(
        "ix_greeting_events_org_locale_created",
        "greeting_events",
        ["org_id", "locale_used", "created_at"],
    )

    op.create_table(
        "greeting_org_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "org_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "default_locale",
            sa.String(length=10),
            nullable=False,
            server_default="en-US",
        ),
    )
    op.create_index(
        "ix_greeting_org_settings_org_id", "greeting_org_settings", ["org_id"]
    )
    op.create_unique_constraint(
        "uq_greeting_org_settings_org_id", "greeting_org_settings", ["org_id"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_greeting_org_settings_org_id", "greeting_org_settings", type_="unique"
    )
    op.drop_index("ix_greeting_org_settings_org_id", table_name="greeting_org_settings")
    op.drop_table("greeting_org_settings")

    op.drop_index("ix_greeting_events_org_locale_created", table_name="greeting_events")
    op.drop_index("ix_greeting_events_org_created", table_name="greeting_events")
    op.drop_index("ix_greeting_events_created_at", table_name="greeting_events")
    op.drop_index("ix_greeting_events_actor_user_id", table_name="greeting_events")
    op.drop_index("ix_greeting_events_org_id", table_name="greeting_events")
    op.drop_table("greeting_events")
