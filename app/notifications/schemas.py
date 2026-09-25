"""Notification API schemas (chassis v0.10) — Pydantic v2."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    level: str
    is_read: bool
    created_at: datetime
    read_at: datetime | None


class UnreadCount(BaseModel):
    unread: int
