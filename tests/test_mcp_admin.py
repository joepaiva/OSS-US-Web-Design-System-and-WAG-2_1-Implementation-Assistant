"""MCP admin page tests (chassis v1.1.0, FR-MCPCLIENT) — RBAC gates + CRUD
flow. TS-MCP-ADMIN (specs/TEST-SCENARIOS.md). Mirrors tests/test_llm_admin.py's
shape -- `/admin/mcp` follows the exact same interaction pattern as `/admin/llm`.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.db import get_sessionmaker
from app.mcp.models import MCPServerConnection
from tests.conftest import make_org, make_user


async def _fetch_connections(name: str) -> list[MCPServerConnection]:
    """Read connections in a short-lived session so we never hold a
    transaction open across `client` requests."""
    async with get_sessionmaker()() as s:
        return list(
            (
                await s.execute(
                    select(MCPServerConnection).where(MCPServerConnection.name == name)
                )
            )
            .scalars()
            .all()
        )


@pytest.mark.asyncio
async def test_unauthenticated_redirects_to_login(client: AsyncClient) -> None:
    resp = await client.get("/admin/mcp")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/login"


@pytest.mark.asyncio
async def test_regular_user_is_forbidden(client: AsyncClient) -> None:
    u = await make_user(client, email="reg-mcp@example.com")
    resp = await client.get("/admin/mcp", headers=u["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_org_admin_can_register_enable_disable_delete(
    client: AsyncClient, session: AsyncSession
) -> None:
    u = await make_user(client, email="orgadmin-mcp@example.com")
    await make_org(client, u["headers"], name="McpOrg", slug="mcporg")

    # Page loads.
    page = await client.get("/admin/mcp", headers=u["headers"])
    assert page.status_code == 200
    assert "MCP Server Connections" in page.text

    # Register a connection.
    resp = await client.post(
        "/admin/mcp/servers",
        data={
            "name": "ticketing",
            "url": "https://mcp.example.com/mcp",
            "credential": "sk-mcp-abcd1234",
        },
        headers=u["headers"],
    )
    assert resp.status_code in (200, 303)

    connections = await _fetch_connections("ticketing")
    assert len(connections) == 1
    conn = connections[0]
    assert conn.enabled is False  # FR-MCPCLIENT-4 — default disabled
    assert conn.encrypted_credential != "sk-mcp-abcd1234"
    conn_id = conn.id

    # Masked credential shown, plaintext never present.
    page = await client.get("/admin/mcp", headers=u["headers"])
    assert "••••1234" in page.text
    assert "sk-mcp-abcd1234" not in page.text
    assert "disabled" in page.text

    # Enable it.
    resp = await client.post(f"/admin/mcp/servers/{conn_id}/enable", headers=u["headers"])
    assert resp.status_code in (200, 303)
    connections = await _fetch_connections("ticketing")
    assert connections[0].enabled is True

    # Disable it.
    resp = await client.post(f"/admin/mcp/servers/{conn_id}/disable", headers=u["headers"])
    assert resp.status_code in (200, 303)
    connections = await _fetch_connections("ticketing")
    assert connections[0].enabled is False

    # Delete it.
    resp = await client.post(f"/admin/mcp/servers/{conn_id}/delete", headers=u["headers"])
    assert resp.status_code in (200, 303)
    connections = await _fetch_connections("ticketing")
    assert connections == []


@pytest.mark.asyncio
async def test_unauthenticated_server_no_credential_is_valid(
    client: AsyncClient,
) -> None:
    u = await make_user(client, email="orgadmin-nocred@example.com")
    await make_org(client, u["headers"], name="NoCred", slug="nocred")

    resp = await client.post(
        "/admin/mcp/servers",
        data={"name": "internal", "url": "https://internal.example.com/mcp", "credential": ""},
        headers=u["headers"],
    )
    assert resp.status_code in (200, 303)

    connections = await _fetch_connections("internal")
    assert len(connections) == 1
    assert connections[0].encrypted_credential is None

    page = await client.get("/admin/mcp", headers=u["headers"])
    assert "(none" in page.text


@pytest.mark.asyncio
async def test_org_admin_cannot_modify_another_orgs_connection(
    client: AsyncClient, session: AsyncSession
) -> None:
    owner = await make_user(client, email="mcp-owner@example.com")
    await make_org(client, owner["headers"], name="Owner", slug="mcpowner")
    resp = await client.post(
        "/admin/mcp/servers",
        data={"name": "ownedserver", "url": "https://owned.example.com/mcp", "credential": ""},
        headers=owner["headers"],
    )
    assert resp.status_code in (200, 303)
    connections = await _fetch_connections("ownedserver")
    conn_id = connections[0].id

    intruder = await make_user(client, email="mcp-intruder@example.com")
    await make_org(client, intruder["headers"], name="Intruder", slug="mcpintruder")

    resp = await client.post(f"/admin/mcp/servers/{conn_id}/enable", headers=intruder["headers"])
    assert resp.status_code == 403

    resp = await client.post(f"/admin/mcp/servers/{conn_id}/delete", headers=intruder["headers"])
    assert resp.status_code == 403

    # Still exists, still disabled, unaffected by the intruder's attempts.
    connections = await _fetch_connections("ownedserver")
    assert len(connections) == 1
    assert connections[0].enabled is False


@pytest.mark.asyncio
async def test_mutations_audited_and_never_carry_credential(
    client: AsyncClient, session: AsyncSession
) -> None:
    u = await make_user(client, email="mcp-audit@example.com")
    await make_org(client, u["headers"], name="AuditOrg", slug="mcpauditorg")
    resp = await client.post(
        "/admin/mcp/servers",
        data={
            "name": "auditedconn",
            "url": "https://audited.example.com/mcp",
            "credential": "sk-should-never-leak",
        },
        headers=u["headers"],
    )
    assert resp.status_code in (200, 303)

    async with get_sessionmaker()() as s:
        rows = (
            await s.execute(
                select(AuditLog).where(AuditLog.action == "mcp.connection_created")
            )
        ).scalars().all()
    assert len(rows) == 1
    assert "sk-should-never-leak" not in str(rows[0].details)
