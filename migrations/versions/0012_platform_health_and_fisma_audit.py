"""fr-platheath / fr-fismaaudit: platform health + fisma self-audit tables
(chassis-program v1.0.0)

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-02

Adds the tables backing the two chassis-program shared capabilities:
PLATFORM-HEALTH-REQUIREMENTS.md §3 (scan_runs, component_inventory,
vulnerability_findings, remediation_proposals) and
FISMA-SELF-AUDIT-REPORT-REQUIREMENTS.md (fisma_audit_reports). All five
tables are purely additive; none are org-scoped (this inventories the
package's own dependency tree / control set, not tenant data).

Downgrade drops all five tables in FK-safe order.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scan_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ok"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tool_version", sa.String(length=64), nullable=True),
        sa.Column("component_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vulnerability_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stale_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "triggered_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_scan_runs_kind", "scan_runs", ["kind"])
    op.create_index("ix_scan_runs_started_at", "scan_runs", ["started_at"])

    op.create_table(
        "component_inventory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "scan_run_id",
            sa.Integer(),
            sa.ForeignKey("scan_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("ecosystem", sa.String(length=32), nullable=False, server_default="pypi"),
        sa.Column("installed_version", sa.String(length=128), nullable=False),
        sa.Column("is_direct", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("latest_stable_version", sa.String(length=128), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=True),
    )
    op.create_index("ix_component_inventory_scan_run_id", "component_inventory", ["scan_run_id"])
    op.create_index("ix_component_inventory_name", "component_inventory", ["name"])

    op.create_table(
        "vulnerability_findings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "scan_run_id",
            sa.Integer(),
            sa.ForeignKey("scan_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("component_name", sa.String(length=255), nullable=False),
        sa.Column("installed_version", sa.String(length=128), nullable=False),
        sa.Column("advisory_id", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("fixed_version", sa.String(length=128), nullable=True),
        sa.Column(
            "install_status", sa.String(length=16), nullable=False, server_default="vulnerable"
        ),
    )
    op.create_index(
        "ix_vulnerability_findings_scan_run_id", "vulnerability_findings", ["scan_run_id"]
    )
    op.create_index(
        "ix_vulnerability_findings_component_name", "vulnerability_findings", ["component_name"]
    )

    op.create_table(
        "remediation_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("component_name", sa.String(length=255), nullable=False),
        sa.Column("from_version", sa.String(length=128), nullable=False),
        sa.Column("to_version", sa.String(length=128), nullable=False),
        sa.Column("bump_kind", sa.String(length=16), nullable=False),
        sa.Column(
            "verification_status", sa.String(length=16), nullable=False, server_default="pending"
        ),
        sa.Column("decision", sa.String(length=16), nullable=False, server_default="proposed"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "decided_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_remediation_proposals_component_name", "remediation_proposals", ["component_name"]
    )
    op.create_index("ix_remediation_proposals_decision", "remediation_proposals", ["decision"])

    op.create_table(
        "fisma_audit_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fisma_level", sa.String(length=16), nullable=False),
        sa.Column(
            "ran_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("findings", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("pass_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fail_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("not_applicable_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "operator_responsibility_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "triggered_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_fisma_audit_reports_ran_at", "fisma_audit_reports", ["ran_at"])


def downgrade() -> None:
    op.drop_index("ix_fisma_audit_reports_ran_at", table_name="fisma_audit_reports")
    op.drop_table("fisma_audit_reports")

    op.drop_index("ix_remediation_proposals_decision", table_name="remediation_proposals")
    op.drop_index(
        "ix_remediation_proposals_component_name", table_name="remediation_proposals"
    )
    op.drop_table("remediation_proposals")

    op.drop_index(
        "ix_vulnerability_findings_component_name", table_name="vulnerability_findings"
    )
    op.drop_index("ix_vulnerability_findings_scan_run_id", table_name="vulnerability_findings")
    op.drop_table("vulnerability_findings")

    op.drop_index("ix_component_inventory_name", table_name="component_inventory")
    op.drop_index("ix_component_inventory_scan_run_id", table_name="component_inventory")
    op.drop_table("component_inventory")

    op.drop_index("ix_scan_runs_started_at", table_name="scan_runs")
    op.drop_index("ix_scan_runs_kind", table_name="scan_runs")
    op.drop_table("scan_runs")
