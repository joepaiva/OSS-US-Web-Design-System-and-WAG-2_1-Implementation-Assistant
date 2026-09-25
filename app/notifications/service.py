"""Notification service (chassis v0.10).

`notify(...)` is the chassis-facing producer used by slots and chassis
subsystems. The rest are user-scoped reads/updates backing the REST API.
Mutations are never cross-user: every read/update filters by `user_id`.

No `@audited` on notify: notifications are high-volume, system-generated
signals, not security-relevant mutations. Slots that need an audit trail
should audit the originating action, not the notification.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import NOTIFICATION_LEVELS, Notification


async def notify(
    session: AsyncSession,
    *,
    user_id: int,
    title: str,
    body: str = "",
    level: str = "info",
    org_id: int | None = None,
) -> Notification:
    """Create a notification for a user. Unknown levels fall back to 'info'."""
    if not title.strip():
        raise ValueError("notification title is required")
    if level not in NOTIFICATION_LEVELS:
        level = "info"
    n = Notification(
        user_id=user_id,
        organization_id=org_id,
        title=title.strip()[:255],
        body=body,
        level=level,
    )
    session.add(n)
    await session.flush()
    return n


async def list_for_user(
    session: AsyncSession, *, user_id: int, unread_only: bool = False, limit: int = 100
) -> list[Notification]:
    stmt = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    stmt = stmt.order_by(Notification.id.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def unread_count(session: AsyncSession, *, user_id: int) -> int:
    stmt = select(func.count(Notification.id)).where(
        Notification.user_id == user_id, Notification.is_read.is_(False)
    )
    return int((await session.execute(stmt)).scalar_one())


async def mark_read(
    session: AsyncSession, *, notification_id: int, user_id: int
) -> Notification | None:
    """Mark one notification read. Returns None if absent or not the user's."""
    stmt = select(Notification).where(
        Notification.id == notification_id, Notification.user_id == user_id
    )
    n = (await session.execute(stmt)).scalar_one_or_none()
    if n is None:
        return None
    if not n.is_read:
        n.is_read = True
        n.read_at = datetime.now(UTC)
        await session.flush()
    return n


async def mark_all_read(session: AsyncSession, *, user_id: int) -> int:
    """Mark all of a user's unread notifications read. Returns the count."""
    stmt = (
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True, read_at=datetime.now(UTC))
    )
    result = await session.execute(stmt)
    # An UPDATE always returns a CursorResult at runtime; Result[Any]'s own
    # base stub doesn't expose .rowcount (only CursorResult does).
    assert isinstance(result, CursorResult)
    return int(result.rowcount or 0)
