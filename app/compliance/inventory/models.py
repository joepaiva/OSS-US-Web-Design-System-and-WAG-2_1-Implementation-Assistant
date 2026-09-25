"""Platform Health ORM models (FR-PLATHEALTH §3 data model).

Four purely additive tables:

  - `scan_runs`            — one row per scan execution (inventory /
                              vulnerability / full), with status and
                              tool-version metadata for reproducibility.
  - `component_inventory`  — one row per (scan_run, dependency) snapshot.
  - `vulnerability_findings` — one row per (scan_run, dependency, advisory).
  - `remediation_proposals` — one row per proposed dependency version bump.

Chassis-owned; not org-scoped (Multi-tenant N/A — this inventories the
package's own code, not tenant data), matching the platform's own
`component_inventory`/`security_scan_report` precedent (FR-453 DESIGN §6.42.1).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

SCAN_KINDS = ("inventory", "currency", "vulnerability", "full")
SCAN_STATUSES = ("ok", "partial", "offline", "failed")
INSTALL_STATUSES = ("vulnerable", "patched", "not_applicable")
BUMP_KINDS = ("patch", "minor", "major")
REMEDIATION_DECISIONS = ("proposed", "auto_applied", "approved", "rejected", "held")


class ScanRun(Base):
    """One Platform Health scan execution."""

    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tool_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    component_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vulnerability_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stale_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ComponentInventoryItem(Base):
    """One dependency, as observed in a given scan run."""

    __tablename__ = "component_inventory"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_run_id: Mapped[int] = mapped_column(
        ForeignKey("scan_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ecosystem: Mapped[str] = mapped_column(String(32), nullable=False, default="pypi")
    installed_version: Mapped[str] = mapped_column(String(128), nullable=False)
    is_direct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    latest_stable_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_current: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )  # None = currency unknown (e.g. offline scan)


class VulnerabilityFinding(Base):
    """One (dependency, advisory) vulnerability finding for a scan run."""

    __tablename__ = "vulnerability_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_run_id: Mapped[int] = mapped_column(
        ForeignKey("scan_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    component_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    installed_version: Mapped[str] = mapped_column(String(128), nullable=False)
    advisory_id: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    fixed_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    install_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="vulnerable"
    )


class RemediationProposal(Base):
    """A proposed dependency version bump, gated by build+test verification."""

    __tablename__ = "remediation_proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    component_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    from_version: Mapped[str] = mapped_column(String(128), nullable=False)
    to_version: Mapped[str] = mapped_column(String(128), nullable=False)
    bump_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )  # pending | verified | failed
    decision: Mapped[str] = mapped_column(
        String(16), nullable=False, default="proposed", index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    decided_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
