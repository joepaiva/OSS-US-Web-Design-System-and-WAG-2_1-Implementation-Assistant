"""Slot-local fixtures for the Greeting slot. Mirrors app/slots/example's
conftest.py pattern (see that file's extensive docstring for why this
layer exists).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pyotp
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.orgs.models import Membership
from app.rbac.models import Role
from tests.conftest import make_org, make_user  # noqa: F401


@pytest_asyncio.fixture
async def greeting_admin_token(client: AsyncClient) -> AsyncIterator[dict[str, object]]:
    """First user in a fresh org — the chassis auto-grants per-org 'admin'
    (Membership.role_id) to an org's creator. NOT MFA-enrolled — use this
    fixture to test "admin without MFA → 403" (FR-004)."""
    auth = await make_user(
        client, email="greeter-admin@example.com", password="TestPassword123!"
    )
    org = await make_org(
        client, cast(dict[str, str], auth["headers"]), name="Greeting Co", slug="greeting-co"
    )
    yield {
        "token": auth["token"],
        "headers": auth["headers"],
        "user": auth["user"],
        "org": org,
    }


@pytest_asyncio.fixture
async def greeting_admin_mfa_token(
    client: AsyncClient, greeting_admin_token: dict[str, object]
) -> AsyncIterator[dict[str, object]]:
    """Same admin as `greeting_admin_token`, but MFA-enrolled + confirmed.

    Reuses the SAME access token/headers deliberately: the greeting slot's
    MFA gate (routes.py) reads the live `user.mfa_enabled` DB column via
    CurrentUser on every request — it is not a token claim — so the
    original registration token reflects the new MFA state immediately
    with no re-login required.
    """
    headers = cast(dict[str, str], greeting_admin_token["headers"])

    start = await client.post("/auth/mfa/enroll", headers=headers)
    assert start.status_code == 200, start.text
    secret = start.json()["secret"]

    code = pyotp.TOTP(secret).now()
    confirm = await client.post(
        "/auth/mfa/enroll/confirm", json={"code": code}, headers=headers
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["mfa_enabled"] is True

    yield greeting_admin_token


@pytest_asyncio.fixture
async def greeting_nonadmin_token(
    client: AsyncClient,
    greeting_admin_token: dict[str, object],
    session: object,
) -> AsyncIterator[dict[str, object]]:
    """A SECOND user in the SAME org as `greeting_admin_token`, with the
    'user' (non-admin) role. Same-org multi-persona membership isn't
    reachable via the public API yet (no invite flow shipped), so this
    fixture creates the Membership row directly via the `session` fixture
    — the pattern app/slots/example's own conftest.py points to."""
    from sqlalchemy.ext.asyncio import AsyncSession

    db_session = cast(AsyncSession, session)

    org = cast(dict[str, object], greeting_admin_token["org"])
    org_id = cast(int, org["id"])

    viewer = await make_user(
        client, email="greeter-viewer@example.com", password="TestPassword123!"
    )
    viewer_user_id = cast(int, cast(dict[str, object], viewer["user"])["id"])

    user_role = (
        await db_session.execute(select(Role).where(Role.name == "user"))
    ).scalar_one()

    db_session.add(
        Membership(
            user_id=viewer_user_id,
            org_id=org_id,
            role_id=user_role.id,
            is_default=True,
        )
    )
    await db_session.commit()

    yield {
        "token": viewer["token"],
        "headers": viewer["headers"],
        "user": viewer["user"],
        "org": org,
    }


@pytest_asyncio.fixture
async def seeded_greeting(
    client: AsyncClient, greeting_admin_token: dict[str, object]
) -> dict[str, object]:
    """Create one greeting (static locale, en-US) as the admin. Returns
    the POST response body."""
    headers = cast(dict[str, str], greeting_admin_token["headers"])
    resp = await client.post(
        "/api/greetings",
        json={"name": "Ada", "locale": "en-US", "use_llm": False},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return cast(dict[str, object], resp.json())
