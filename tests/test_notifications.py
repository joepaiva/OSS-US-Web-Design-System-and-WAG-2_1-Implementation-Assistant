"""Notification tests (chassis v0.10) — service + REST API + user isolation."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.notifications import service
from tests.conftest import make_user


async def _user_id(session: AsyncSession, email: str) -> int:
    return (
        await session.execute(select(User.id).where(User.email == email))
    ).scalar_one()


# ─── Service ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_and_unread_count(session: AsyncSession, client: AsyncClient) -> None:
    await make_user(client, email="notif1@example.com")
    uid = await _user_id(session, "notif1@example.com")

    await service.notify(session, user_id=uid, title="Hello", body="world")
    await service.notify(session, user_id=uid, title="Second", level="warning")
    await session.commit()

    assert await service.unread_count(session, user_id=uid) == 2
    items = await service.list_for_user(session, user_id=uid)
    assert [n.title for n in items] == ["Second", "Hello"]  # newest first


@pytest.mark.asyncio
async def test_unknown_level_falls_back_to_info(session: AsyncSession, client: AsyncClient) -> None:
    await make_user(client, email="notif-lvl@example.com")
    uid = await _user_id(session, "notif-lvl@example.com")
    n = await service.notify(session, user_id=uid, title="X", level="bogus")
    assert n.level == "info"


@pytest.mark.asyncio
async def test_mark_read_and_mark_all(session: AsyncSession, client: AsyncClient) -> None:
    await make_user(client, email="notif2@example.com")
    uid = await _user_id(session, "notif2@example.com")
    a = await service.notify(session, user_id=uid, title="A")
    await service.notify(session, user_id=uid, title="B")
    await session.commit()

    await service.mark_read(session, notification_id=a.id, user_id=uid)
    await session.commit()
    assert await service.unread_count(session, user_id=uid) == 1

    count = await service.mark_all_read(session, user_id=uid)
    await session.commit()
    assert count == 1
    assert await service.unread_count(session, user_id=uid) == 0


@pytest.mark.asyncio
async def test_mark_read_foreign_user_returns_none(
    session: AsyncSession, client: AsyncClient
) -> None:
    await make_user(client, email="owner@example.com")
    await make_user(client, email="intruder@example.com")
    owner = await _user_id(session, "owner@example.com")
    intruder = await _user_id(session, "intruder@example.com")
    n = await service.notify(session, user_id=owner, title="private")
    await session.commit()

    # Intruder can't mark the owner's notification read.
    assert await service.mark_read(session, notification_id=n.id, user_id=intruder) is None


# ─── REST API ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_list_and_read_flow(
    session: AsyncSession, client: AsyncClient
) -> None:
    u = await make_user(client, email="notif-api@example.com")
    uid = await _user_id(session, "notif-api@example.com")
    n1 = await service.notify(session, user_id=uid, title="One")
    await service.notify(session, user_id=uid, title="Two")
    await session.commit()

    # Unread count.
    uc = await client.get("/api/notifications/unread-count", headers=u["headers"])
    assert uc.status_code == 200 and uc.json()["unread"] == 2

    # List (all).
    ls = await client.get("/api/notifications", headers=u["headers"])
    assert ls.status_code == 200 and len(ls.json()) == 2

    # Mark one read.
    r = await client.post(f"/api/notifications/{n1.id}/read", headers=u["headers"])
    assert r.status_code == 200 and r.json()["is_read"] is True

    # unread_only filter now returns 1.
    ls2 = await client.get(
        "/api/notifications?unread_only=true", headers=u["headers"]
    )
    assert len(ls2.json()) == 1

    # Read-all clears it.
    ra = await client.post("/api/notifications/read-all", headers=u["headers"])
    assert ra.status_code == 200 and ra.json()["unread"] == 0


@pytest.mark.asyncio
async def test_api_user_isolation(session: AsyncSession, client: AsyncClient) -> None:
    await make_user(client, email="iso-a@example.com")
    b = await make_user(client, email="iso-b@example.com")
    a_id = await _user_id(session, "iso-a@example.com")
    n = await service.notify(session, user_id=a_id, title="for-a")
    await session.commit()

    # B sees none of A's notifications and can't mark them read.
    assert (await client.get("/api/notifications", headers=b["headers"])).json() == []
    r = await client.post(f"/api/notifications/{n.id}/read", headers=b["headers"])
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_api_requires_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/notifications")).status_code == 401
