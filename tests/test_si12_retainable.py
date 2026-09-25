"""SI-12 RetainableFor mixin tests (chassis v0.6).

Verifies that the mixin can be composed with Base + TenantScoped on a
synthetic model, that the retained_until column exists with the right
type + nullability, and that NULL is the default (unscheduled retention).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, RetainableFor, TenantScoped


class _SyntheticInvoice(Base, TenantScoped, RetainableFor):
    """Test-only model exercising the SI-12 mixin pattern."""

    __tablename__ = "_test_si12_invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(64), nullable=False)


def test_retainable_for_column_exists_on_composed_model() -> None:
    """Mixin contributes a retained_until Mapped column."""
    cols = _SyntheticInvoice.__table__.columns
    assert "retained_until" in cols
    col = cols["retained_until"]
    assert isinstance(col.type, DateTime)
    # NIST 800-53 SI-12 doesn't require nullable=False — NULL means
    # "no scheduled retention" (subject to chassis-wide AU-11 only).
    assert col.nullable is True
    # Indexed for AU-11 archival job query performance.
    assert col.index is True


def test_retainable_for_column_default_is_none() -> None:
    """A newly-constructed instance has retained_until = None."""
    inv = _SyntheticInvoice(invoice_number="INV-001")
    assert inv.retained_until is None


def test_retainable_for_accepts_future_datetime() -> None:
    """retained_until can be set to a future timestamp by slot logic."""
    inv = _SyntheticInvoice(invoice_number="INV-002")
    future = datetime.now(UTC) + timedelta(days=365 * 7)
    inv.retained_until = future
    assert inv.retained_until == future


def test_tenant_scoped_org_id_still_works_alongside_retainable() -> None:
    """SI-12 mixin must compose cleanly with TenantScoped."""
    cols = _SyntheticInvoice.__table__.columns
    assert "org_id" in cols  # contributed by TenantScoped
    assert "retained_until" in cols  # contributed by RetainableFor
