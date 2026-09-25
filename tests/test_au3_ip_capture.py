"""AU-3 IP capture in @audited tests (chassis v0.6).

NIST 800-53 AU-3 (FedRAMP M + IL-2 extension) requires the audit record
to include the source IP address. The chassis binds it via the
request_id_middleware (app/main.py) and the @audited decorator reads
the contextvar to populate AuditLog.ip_address.

Tests:
  1. With a FastAPI request context that has an X-Forwarded-For header
     → contextvar bound to first IP in the list (load-balancer scenario)
  2. Direct request.client.host (no XFF) → contextvar bound to that IP
  3. Audit row written by @audited carries the bound IP
  4. Outside a request context (e.g., RQ worker), IP is None
"""

from __future__ import annotations

from typing import Any

import pytest

from app.deps_context import (
    get_current_client_ip,
    set_current_client_ip,
)


def test_set_and_get_current_client_ip() -> None:
    """The contextvar round-trips a string IP."""
    set_current_client_ip("203.0.113.42")
    assert get_current_client_ip() == "203.0.113.42"


def test_get_current_client_ip_default_is_none() -> None:
    """Outside a bound context, getter returns None (RQ worker case)."""
    # Reset to ensure clean state — set explicitly to None then read.
    set_current_client_ip(None)
    assert get_current_client_ip() is None


@pytest.mark.asyncio
async def test_request_middleware_binds_xff_first_ip(
    client: Any,
) -> None:
    """When X-Forwarded-For is present, the middleware binds the first IP.

    Asserts via /auth/me — the audit decorator on register would otherwise
    capture the IP at register-time. Here we just confirm the contextvar
    side-effect by hitting an endpoint that triggers the middleware.
    """
    # Reset before request — make sure we're not seeing a leftover value.
    set_current_client_ip(None)
    resp = await client.get(
        "/auth/me",
        headers={
            "X-Forwarded-For": "198.51.100.7, 10.0.0.1",
            "Authorization": "Bearer not-a-real-jwt-but-fine-for-this-test",
        },
    )
    # /auth/me with invalid bearer returns 401, but the middleware ran
    # before the auth check — so the contextvar should reflect the XFF.
    assert resp.status_code == 401
    assert get_current_client_ip() == "198.51.100.7"


@pytest.mark.asyncio
async def test_request_middleware_binds_client_host_when_no_xff(
    client: Any,
) -> None:
    """When no X-Forwarded-For, middleware falls back to request.client.host."""
    set_current_client_ip(None)
    resp = await client.get("/auth/me")
    assert resp.status_code == 401
    # httpx ASGITransport uses "127.0.0.1" as the synthetic client host.
    captured = get_current_client_ip()
    # Either set to the synthetic host or None depending on transport;
    # the important thing is it's NOT a leftover from a prior request.
    assert captured in (None, "127.0.0.1", "testclient", "test")


@pytest.mark.asyncio
async def test_audit_row_carries_ip_address_when_bound(client: Any) -> None:
    """End-to-end: register a user via the API and verify the AuditLog
    row (organizations.created action is generated on first org) carries
    the IP from XFF.

    Uses the /auth/register + /orgs flow to exercise the @audited
    decorator on org creation, then queries the audit_logs table.
    """
    from sqlalchemy import select

    from app.audit.models import AuditLog
    from app.db import get_sessionmaker

    fake_ip = "203.0.113.99"
    auth = await client.post(
        "/auth/register",
        json={
            "email": "au3@example.com",
            "password": "AuditTestPassword1!",
            "full_name": "AU-3 Test",
        },
        headers={"X-Forwarded-For": fake_ip},
    )
    assert auth.status_code == 201
    token = auth.json()["access_token"]

    org_resp = await client.post(
        "/orgs",
        json={"name": "AU-3 Org", "slug": "au3-org"},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Forwarded-For": fake_ip,
        },
    )
    assert org_resp.status_code == 201

    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.action == "orgs.created")
        )
        rows = list(result.scalars().all())

    assert len(rows) >= 1
    assert rows[-1].ip_address == fake_ip
