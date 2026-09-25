"""GreetingRepository — the only component permitted to query
GreetingEvent / GreetingOrgSettings (Constitution §5, DESIGN.md §5).

No method accepts an org_id override — scoping comes entirely from the
chassis TenantScoped mixin's auto-filter/auto-inject, bound to the
request's current_org_id_var by app/deps.py's `get_current_org`. Exactly
the three GreetingEvent methods the draft specifies, plus one settings
helper this package adds for BR-004 (see models.py's GreetingOrgSettings
docstring for why it's a separate slot-owned table).

No delete, purge, or truncate method exists (NFR-005).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.slots.greeting.models import GreetingEvent, GreetingOrgSettings

PAGE_SIZE = 20  # FR-004 — exactly 20 per page


async def record(session: AsyncSession, event: GreetingEvent) -> GreetingEvent:
    """Persist one GreetingEvent. org_id auto-injected by the chassis
    before_flush listener."""
    session.add(event)
    await session.flush()
    return event


async def page(session: AsyncSession, page_number: int) -> tuple[list[GreetingEvent], int]:
    """FR-004 — up to 20 rows, most recent first, plus the total count."""
    total = (
        await session.execute(select(func.count()).select_from(GreetingEvent))
    ).scalar_one()
    offset = (page_number - 1) * PAGE_SIZE
    rows = (
        await session.execute(
            select(GreetingEvent)
            .order_by(GreetingEvent.created_at.desc(), GreetingEvent.id.desc())
            .offset(offset)
            .limit(PAGE_SIZE)
        )
    ).scalars().all()
    return list(rows), int(total)


async def page_by_locale(
    session: AsyncSession, locale: str, page_number: int
) -> tuple[list[GreetingEvent], int]:
    """FR-005 — same pagination as `page`, filtered to one locale."""
    total = (
        await session.execute(
            select(func.count())
            .select_from(GreetingEvent)
            .where(GreetingEvent.locale_used == locale)
        )
    ).scalar_one()
    offset = (page_number - 1) * PAGE_SIZE
    rows = (
        await session.execute(
            select(GreetingEvent)
            .where(GreetingEvent.locale_used == locale)
            .order_by(GreetingEvent.created_at.desc(), GreetingEvent.id.desc())
            .offset(offset)
            .limit(PAGE_SIZE)
        )
    ).scalars().all()
    return list(rows), int(total)


async def get_or_create_org_settings(session: AsyncSession) -> GreetingOrgSettings:
    """BR-004 — lazily create the org's settings row (default_locale
    'en-US') on first access, satisfying "every organization MUST have
    exactly one default locale" without hooking into chassis org-creation
    code (a chassis-owned file this slot must not edit)."""
    existing = (
        await session.execute(select(GreetingOrgSettings))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    settings_row = GreetingOrgSettings()
    session.add(settings_row)
    await session.flush()
    return settings_row
