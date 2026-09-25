"""Async SQLAlchemy 2.0 engine + AsyncSession factory.

CANONICAL MODERN PATTERNS (ARCHITECTURE.md §2.2):
  - `from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession`
  - `async with session.begin(): ...` for transactional blocks
  - `(await session.execute(select(Model).where(...))).scalar_one_or_none()`

FORBIDDEN (legacy 1.4 sync):
  - `from sqlalchemy.orm import sessionmaker, Session`
  - `session.query(Model).filter(...)` — use `select(...)` instead
  - `engine = create_engine(...)` — use `create_async_engine(...)`
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextvars import ContextVar
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import DateTime, ForeignKey, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    with_loader_criteria,
)

from app.config import Settings, get_settings

# ────────────────────────────────────────────────────────────────────────
# Tenant context — per-request org_id, propagated through async tasks
# via contextvars.
# ────────────────────────────────────────────────────────────────────────

current_org_id_var: ContextVar[int | None] = ContextVar(
    "chassis_current_org_id", default=None
)


def set_current_org_id(org_id: int | None) -> None:
    """Bind the current request's org_id. Called by `current_org` dep."""
    current_org_id_var.set(org_id)


def get_current_org_id() -> int | None:
    """Return the currently-bound org_id, if any."""
    return current_org_id_var.get(None)


class Base(DeclarativeBase):
    """Declarative base for all ORM models.

    SQLAlchemy 2.0 typed form. Models declare columns via
    `id: Mapped[int] = mapped_column(primary_key=True)` — NOT the legacy
    `id = Column(Integer, primary_key=True)` form.
    """


class TenantScoped:
    """Mixin: declares `org_id` and signals to the chassis event listeners
    that this model is tenant-scoped.

    Inheriting models automatically get:
      - SELECT filtered with `WHERE org_id = :current_org_id`
      - INSERT auto-populated with `org_id = :current_org_id`

    Without this mixin, a model is NOT tenant-scoped (e.g. User itself
    sits ABOVE tenancy — a user can exist before joining any org).

    Slot example:

        from app.db import Base, TenantScoped

        class InventoryItem(Base, TenantScoped):
            __tablename__ = "inventory_items"
            id: Mapped[int] = mapped_column(primary_key=True)
            sku: Mapped[str] = mapped_column(String(64))
            # org_id added automatically by the mixin
    """

    org_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class RetainableFor:
    """SI-12 (chassis v0.6): Per-row retention metadata mixin.

    NIST 800-53 SI-12 (Information Management and Retention) requires that
    information be retained IAW org policy. The chassis ships TWO levels:

      1. CHASSIS-WIDE AU-11 retention: audit_logs older than
         `settings.audit_retention_days` are archived by the background job.

      2. PER-ROW SI-12 retention via THIS MIXIN: slot models that need
         row-level retention policies inherit this mixin. The
         `retained_until` column lets the slot author (or a per-org policy
         engine) set a per-row expiration. The AU-11 archival job queries
         `WHERE retained_until IS NOT NULL AND retained_until < now()` to
         pick up rows that have aged out under their slot-specific policy
         even if they're younger than the chassis-wide cutoff.

    Slot example — invoices retained 7 years from issue date:

        from datetime import UTC, datetime, timedelta
        from app.db import Base, TenantScoped, RetainableFor

        class Invoice(Base, TenantScoped, RetainableFor):
            __tablename__ = "billing_invoices"
            id: Mapped[int] = mapped_column(primary_key=True)
            issued_at: Mapped[datetime] = mapped_column(...)

            @validates("issued_at")
            def _set_retention(self, key, value):
                # Set 7-year retention at issue time.
                self.retained_until = value + timedelta(days=365 * 7)
                return value

    SOFT-DELETE NOTE: This is INTENTIONALLY NOT a soft-delete column.
    Per ARCHITECTURE.md §2.9, the chassis position on soft-delete is
    "opt-in per slot via a separate SoftDeletable mixin in the slot's
    own models.py" — NOT chassis-default. RetainableFor is about
    PLANNED future deletion (retention policy), not LOGICAL deletion.
    A row with `retained_until` in the past is still a valid live row
    until the archival job touches it.
    """

    retained_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment=(
            "SI-12: row expires after this timestamp; archival jobs use "
            "this column to select rows for offline archival. NULL = no "
            "scheduled expiration (subject to chassis-wide AU-11 only)."
        ),
    )


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """Lazy-init the async engine; reused across requests.

    Engine creation is expensive and pool state must be process-wide singleton.
    """
    global _engine
    if _engine is None:
        s = settings or get_settings()
        _engine = create_async_engine(
            s.database_url,
            echo=s.db_echo,
            pool_pre_ping=s.db_pool_pre_ping,
            pool_size=s.db_pool_size,
            max_overflow=s.db_max_overflow,
            pool_recycle=s.db_pool_recycle_seconds,
        )
    return _engine


def get_sessionmaker(
    settings: Settings | None = None,
) -> async_sessionmaker[AsyncSession]:
    """Lazy-init the AsyncSession factory bound to the engine."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(settings),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a per-request AsyncSession.

    Usage in routes:

        @router.get("/users/{user_id}")
        async def get_user(user_id: int, session: SessionDep) -> UserRead:
            ...

    The session is committed on success and rolled back on exception.
    """
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def reset_engine_for_tests() -> None:
    """Tear down the global engine + sessionmaker.

    Used by test fixtures to ensure each test gets a fresh engine bound
    to its own (possibly in-memory or per-test-database) DSN.
    """
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


# ────────────────────────────────────────────────────────────────────────
# Multi-tenancy event listeners.
#
# These fire for EVERY ORM execute and EVERY flush on the sync Session
# that AsyncSession wraps. They are the heart of chassis isolation:
# slot code never has to remember to filter by org_id.
#
# Both listeners no-op when `current_org_id_var` is unset (e.g. CLI/
# startup-task contexts where there's no logical tenant). This means
# chassis admin operations (seeding RBAC, creating the first user, etc.)
# can run without binding to an org.
# ────────────────────────────────────────────────────────────────────────


@event.listens_for(Session, "do_orm_execute")
def _filter_tenant_scoped_selects(orm_execute_state: Any) -> None:
    """Inject `WHERE org_id = :current_org_id` into every SELECT against
    TenantScoped subclasses.

    Uses `with_loader_criteria` (SQLAlchemy 2.0) which is alias-safe and
    composes correctly with eager-loading. Triggers on the canonical
    `do_orm_execute` ORM event — fires for `session.execute(select(...))`
    and any select that comes through ORM relationship loaders.
    """
    if not orm_execute_state.is_select:
        return
    org_id = current_org_id_var.get(None)
    if org_id is None:
        return

    orm_execute_state.statement = orm_execute_state.statement.options(
        with_loader_criteria(
            TenantScoped,
            lambda cls: cls.org_id == org_id,
            include_aliases=True,
        )
    )


@event.listens_for(Session, "before_flush")
def _inject_org_on_insert(
    session: Session, _flush_context: Any, _instances: Any
) -> None:
    """Auto-populate `org_id` on freshly added TenantScoped instances.

    Fires once per flush. Only mutates instances that:
      - Are in `session.new` (about to INSERT)
      - Inherit TenantScoped
      - Have not been explicitly assigned an org_id

    The "have not been explicitly assigned" condition means slot code MAY
    override the default by setting `obj.org_id = X` before flush; the
    listener won't clobber it. This is intentional — admin/cross-tenant
    operations need an escape hatch.
    """
    org_id = current_org_id_var.get(None)
    if org_id is None:
        return
    for obj in session.new:
        if isinstance(obj, TenantScoped) and getattr(obj, "org_id", None) is None:
            obj.org_id = org_id
