"""FISMA self-audit report ORM model (FR-FISMAAUDIT-6/7).

One additive table. Each run's per-control findings are stored as a JSON
list on the report row (small, bounded cardinality — one entry per control
in the registry, not per-request data) rather than a child table, since
findings are never queried independently of their parent report.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

OUTCOMES = ("pass", "fail", "not_applicable", "operator_responsibility", "check_error")


class FismaAuditReport(Base):
    """One FISMA self-audit run (FR-FISMAAUDIT-6/7)."""

    __tablename__ = "fisma_audit_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    fisma_level: Mapped[str] = mapped_column(String(16), nullable=False)  # "moderate" | "low"
    ran_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    pass_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    not_applicable_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    operator_responsibility_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    triggered_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    @property
    def has_failures(self) -> bool:
        return self.fail_count > 0
