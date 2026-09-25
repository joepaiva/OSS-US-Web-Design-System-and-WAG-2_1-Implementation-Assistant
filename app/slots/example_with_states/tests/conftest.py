"""Slot-local pytest fixtures for the example_with_states (Approval Request) slot.

Mirrors the shape of app/slots/example/tests/conftest.py — the canonical
helper-fixture pattern reference. Adds slot-local personas for the
Approval Request domain.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pytest_asyncio
from httpx import AsyncClient

from tests.conftest import make_org, make_user  # noqa: F401


@pytest_asyncio.fixture
async def requester_token(client: AsyncClient) -> AsyncIterator[dict[str, object]]:
    """A user with approval-requests:write — the persona who creates and
    submits approval requests. Chassis assigns admin role to first org
    member, which has the write permission seeded.
    """
    auth = await make_user(
        client, email="requester@example.com", password="TestPassword123!"
    )
    org = await make_org(
        client,
        cast(dict[str, str], auth["headers"]),
        name="Requester Co",
        slug="requester-co",
    )
    yield {
        "token": auth["token"],
        "headers": auth["headers"],
        "user": auth["user"],
        "org": org,
    }


@pytest_asyncio.fixture
async def approver_token(client: AsyncClient) -> AsyncIterator[dict[str, object]]:
    """A SECOND user in a DIFFERENT org (same constraint as the example
    slot's note_viewer_token — invite-into-existing-org isn't shipped
    until chassis v1.x). Used to test cross-org isolation on the
    approval-requests endpoints.
    """
    auth = await make_user(
        client, email="approver@example.com", password="TestPassword123!"
    )
    org = await make_org(
        client,
        cast(dict[str, str], auth["headers"]),
        name="Approver Co",
        slug="approver-co",
    )
    yield {
        "token": auth["token"],
        "headers": auth["headers"],
        "user": auth["user"],
        "org": org,
    }


@pytest_asyncio.fixture
async def seeded_draft(
    client: AsyncClient, requester_token: dict[str, object]
) -> dict[str, object]:
    """One pre-existing approval request in DRAFT status owned by
    requester_token. Useful for transition / update / get tests.
    """
    headers = cast(dict[str, str], requester_token["headers"])
    resp = await client.post(
        "/approval-requests",
        json={"title": "Budget request", "body": "Q3 budget request"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return cast(dict[str, object], resp.json())


@pytest_asyncio.fixture
async def seeded_submitted(
    client: AsyncClient,
    requester_token: dict[str, object],
    seeded_draft: dict[str, object],
) -> dict[str, object]:
    """A request already advanced to SUBMITTED status. Used for tests
    that exercise the submitted→approved or submitted→rejected paths.
    """
    headers = cast(dict[str, str], requester_token["headers"])
    request_id = seeded_draft["id"]
    resp = await client.post(
        f"/approval-requests/{request_id}/transitions",
        json={"target_status": "submitted"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return cast(dict[str, object], resp.json())
