"""Notification API routes (chassis v0.10) — user-scoped.

Every route is scoped to `CurrentUser`: a caller only ever sees or mutates
their own notifications. No org context required (notifications are personal).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.db import SessionDep
from app.deps import CurrentUser
from app.notifications.schemas import NotificationRead, UnreadCount
from app.notifications.service import (
    list_for_user,
    mark_all_read,
    mark_read,
    unread_count,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationRead])
async def list_(
    user: CurrentUser,
    session: SessionDep,
    unread_only: bool = Query(False),
) -> list[NotificationRead]:
    items = await list_for_user(session, user_id=user.id, unread_only=unread_only)
    return [NotificationRead.model_validate(n) for n in items]


@router.get("/unread-count", response_model=UnreadCount)
async def unread(user: CurrentUser, session: SessionDep) -> UnreadCount:
    return UnreadCount(unread=await unread_count(session, user_id=user.id))


@router.post("/{notification_id}/read", response_model=NotificationRead)
async def read_one(
    notification_id: int, user: CurrentUser, session: SessionDep
) -> NotificationRead:
    n = await mark_read(session, notification_id=notification_id, user_id=user.id)
    if n is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found."
        )
    return NotificationRead.model_validate(n)


@router.post("/read-all", response_model=UnreadCount)
async def read_all(user: CurrentUser, session: SessionDep) -> UnreadCount:
    await mark_all_read(session, user_id=user.id)
    return UnreadCount(unread=await unread_count(session, user_id=user.id))
