"""MCP server connection service tests (chassis v1.1.0, FR-MCPCLIENT).

TS-MCP-MODEL/TS-MCP-CRYPTO, TS-MCP-SVC, TS-MCP-DEGRADE (specs/TEST-SCENARIOS.md).
Every "real server" scenario runs against the in-process fixture server
(tests/fixtures/mcp_fixture_server.py) on a real local port -- never a live
third party.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.mcp import service
from app.orgs.models import Organization
from tests.fixtures.mcp_fixture_server import (
    run_auth_protected_fixture_server,
    run_fixture_server,
)


async def _make_org(session: AsyncSession, slug: str) -> Organization:
    org = Organization(name=slug.title(), slug=slug)
    session.add(org)
    await session.flush()
    return org


# ─── TS-MCP-MODEL / TS-MCP-CRYPTO ───────────────────────────────────────


@pytest.mark.asyncio
async def test_connection_defaults_to_disabled(session: AsyncSession) -> None:
    org = await _make_org(session, "mcpmodel1")
    conn = await service.create_connection(
        session,
        org_id=org.id,
        name="internal",
        url="http://example.com/mcp",
        credential=None,
        created_by_user_id=None,
    )
    await session.commit()
    assert conn.enabled is False


@pytest.mark.asyncio
async def test_credential_stored_encrypted_not_plaintext(session: AsyncSession) -> None:
    org = await _make_org(session, "mcpmodel2")
    conn = await service.create_connection(
        session,
        org_id=org.id,
        name="internal",
        url="http://example.com/mcp",
        credential="super-secret-token-123",
        created_by_user_id=None,
    )
    await session.commit()

    # Read the raw column directly -- bypassing the ORM's own decrypt path
    # entirely, per the task's acceptance criterion.
    raw = (
        await session.execute(
            text("SELECT encrypted_credential FROM mcp_server_connections WHERE id = :id"),
            {"id": conn.id},
        )
    ).scalar_one()
    assert raw is not None
    assert raw != "super-secret-token-123"
    assert "super-secret-token-123" not in raw


@pytest.mark.asyncio
async def test_no_credential_is_valid_config(session: AsyncSession) -> None:
    org = await _make_org(session, "mcpmodel3")
    conn = await service.create_connection(
        session,
        org_id=org.id,
        name="unauth",
        url="http://example.com/mcp",
        credential=None,
        created_by_user_id=None,
    )
    await session.commit()
    assert conn.encrypted_credential is None
    views = await service.list_connections(session, org_id=org.id)
    assert views[0].has_credential is False
    assert views[0].masked_credential is None


# ─── TS-MCP-SVC ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_discover_tools_against_real_fixture_server(session: AsyncSession) -> None:
    org = await _make_org(session, "mcpsvc1")
    async with run_fixture_server(port=8801) as url:
        conn = await service.create_connection(
            session,
            org_id=org.id,
            name="fixture",
            url=url,
            credential=None,
            created_by_user_id=None,
        )
        await service.enable_connection(session, conn)
        await session.commit()

        tools = await service.discover_tools(session, org.id)
        names = {t["function"]["name"] for t in tools}
        assert names == {"fixture.echo", "fixture.lookup"}


@pytest.mark.asyncio
async def test_disabled_connection_not_discovered(session: AsyncSession) -> None:
    org = await _make_org(session, "mcpsvc2")
    async with run_fixture_server(port=8802) as url:
        await service.create_connection(
            session,
            org_id=org.id,
            name="fixture",
            url=url,
            credential=None,
            created_by_user_id=None,
        )
        await session.commit()  # left disabled (default) -- never enabled

        tools = await service.discover_tools(session, org.id)
        assert tools == []


@pytest.mark.asyncio
async def test_zero_connections_returns_empty(session: AsyncSession) -> None:
    org = await _make_org(session, "mcpsvc3")
    await session.commit()
    assert await service.discover_tools(session, org.id) == []


@pytest.mark.asyncio
async def test_discovery_and_invocation_are_org_scoped(session: AsyncSession) -> None:
    org_a = await _make_org(session, "mcpsvc4a")
    org_b = await _make_org(session, "mcpsvc4b")
    async with run_fixture_server(port=8803) as url:
        conn = await service.create_connection(
            session,
            org_id=org_a.id,
            name="fixture",
            url=url,
            credential=None,
            created_by_user_id=None,
        )
        await service.enable_connection(session, conn)
        await session.commit()

        # org_b never sees org_a's enabled connection.
        assert await service.discover_tools(session, org_b.id) == []
        # org_b invoking org_a's qualified tool name resolves to an error,
        # never org_a's live connection (FR-MCPCLIENT-8).
        result = await service.invoke_tool(session, org_b.id, "fixture.echo", {"text": "hi"})
        assert "error" in result
        # org_a itself still resolves it fine.
        ok = await service.invoke_tool(session, org_a.id, "fixture.echo", {"text": "hi"})
        assert ok == {"result": "hi"}


@pytest.mark.asyncio
async def test_invoke_echo_returns_real_fixture_result(session: AsyncSession) -> None:
    org = await _make_org(session, "mcpsvc5")
    async with run_fixture_server(port=8804) as url:
        conn = await service.create_connection(
            session,
            org_id=org.id,
            name="fixture",
            url=url,
            credential=None,
            created_by_user_id=None,
        )
        await service.enable_connection(session, conn)
        await session.commit()

        result = await service.invoke_tool(
            session, org.id, "fixture.echo", {"text": "hello there"}
        )
        assert result == {"result": "hello there"}


@pytest.mark.asyncio
async def test_invoke_lookup_known_and_unknown_key(session: AsyncSession) -> None:
    org = await _make_org(session, "mcpsvc6")
    async with run_fixture_server(port=8805) as url:
        conn = await service.create_connection(
            session,
            org_id=org.id,
            name="fixture",
            url=url,
            credential=None,
            created_by_user_id=None,
        )
        await service.enable_connection(session, conn)
        await session.commit()

        ok = await service.invoke_tool(
            session, org.id, "fixture.lookup", {"key": "greeting_style"}
        )
        assert ok == {"result": "formal"}

        bad = await service.invoke_tool(session, org.id, "fixture.lookup", {"key": "nope"})
        assert "error" in bad


# ─── TS-MCP-DEGRADE ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unreachable_connection_excluded_others_still_discovered(
    session: AsyncSession,
) -> None:
    org = await _make_org(session, "mcpdeg1")
    async with run_fixture_server(port=8806) as url:
        good = await service.create_connection(
            session,
            org_id=org.id,
            name="good",
            url=url,
            credential=None,
            created_by_user_id=None,
        )
        await service.enable_connection(session, good)
        bad = await service.create_connection(
            session,
            org_id=org.id,
            name="bad",
            url="http://127.0.0.1:1/mcp",
            credential=None,
            created_by_user_id=None,
        )
        await service.enable_connection(session, bad)
        await session.commit()

        tools = await service.discover_tools(session, org.id)
        names = {t["function"]["name"] for t in tools}
        assert names == {"good.echo", "good.lookup"}


@pytest.mark.asyncio
async def test_invoke_unreachable_server_returns_error_not_raise(
    session: AsyncSession,
) -> None:
    org = await _make_org(session, "mcpdeg2")
    conn = await service.create_connection(
        session,
        org_id=org.id,
        name="bad",
        url="http://127.0.0.1:1/mcp",
        credential=None,
        created_by_user_id=None,
    )
    await service.enable_connection(session, conn)
    await session.commit()

    result = await service.invoke_tool(session, org.id, "bad.echo", {"text": "x"})
    assert "error" in result


@pytest.mark.asyncio
async def test_auth_failure_surfaces_as_error_not_exception(session: AsyncSession) -> None:
    org = await _make_org(session, "mcpdeg3")
    async with run_auth_protected_fixture_server(
        port=8807, required_token="right-token"
    ) as url:
        conn = await service.create_connection(
            session,
            org_id=org.id,
            name="protected",
            url=url,
            credential="wrong-token",
            created_by_user_id=None,
        )
        await service.enable_connection(session, conn)
        await session.commit()

        # discovery: excluded, no raise (FR-MCPCLIENT-9).
        tools = await service.discover_tools(session, org.id)
        assert tools == []

        # invocation: error payload, no raise (FR-MCPCLIENT-10).
        result = await service.invoke_tool(session, org.id, "protected.echo", {"text": "x"})
        assert "error" in result


@pytest.mark.asyncio
async def test_correct_credential_succeeds_against_protected_server(
    session: AsyncSession,
) -> None:
    org = await _make_org(session, "mcpdeg4")
    async with run_auth_protected_fixture_server(
        port=8808, required_token="right-token"
    ) as url:
        conn = await service.create_connection(
            session,
            org_id=org.id,
            name="protected",
            url=url,
            credential="right-token",
            created_by_user_id=None,
        )
        await service.enable_connection(session, conn)
        await session.commit()

        tools = await service.discover_tools(session, org.id)
        names = {t["function"]["name"] for t in tools}
        assert names == {"protected.echo", "protected.lookup"}


@pytest.mark.asyncio
async def test_tool_execution_error_returns_error_not_raise(session: AsyncSession) -> None:
    org = await _make_org(session, "mcpdeg5")
    async with run_fixture_server(port=8809) as url:
        conn = await service.create_connection(
            session,
            org_id=org.id,
            name="fixture",
            url=url,
            credential=None,
            created_by_user_id=None,
        )
        await service.enable_connection(session, conn)
        await session.commit()

        result = await service.invoke_tool(session, org.id, "fixture.lookup", {"key": "missing"})
        assert "error" in result


@pytest.mark.asyncio
async def test_audit_row_written_never_carries_credential(session: AsyncSession) -> None:
    org = await _make_org(session, "mcpaudit1")
    await service.create_connection(
        session,
        org_id=org.id,
        name="audited",
        url="http://example.com/mcp",
        credential="top-secret-value",
        created_by_user_id=None,
    )
    await session.commit()

    rows = (
        await session.execute(
            select(AuditLog).where(AuditLog.action == "mcp.connection_created")
        )
    ).scalars().all()
    assert len(rows) == 1
    assert "top-secret-value" not in str(rows[0].details)
    assert rows[0].details.get("name") == "audited"
