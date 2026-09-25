"""MCP server connection service — CRUD, tool discovery, tool invocation
(chassis v1.1.0, FR-MCPCLIENT).

Mirrors `app/llm/service.py`'s shape: CRUD mutations are `@audited`, list
views return masked credentials, and the credential value itself never
appears in an audit record, log line, or error message (FR-MCPCLIENT-5).

`discover_tools`/`invoke_tool` are this module's load-bearing pair:
  - `discover_tools` is scoped to the calling org's own *enabled*
    connections only (FR-MCPCLIENT-6/8) and NEVER raises — a connection
    that fails to connect is logged and skipped, never failing the whole
    discovery pass (FR-MCPCLIENT-9). Zero enabled connections short-circuits
    before any `mcp/client.py` call (NFR-MCPCLIENT-1).
  - `invoke_tool` NEVER raises for a normal operational failure (unreachable
    server, auth failure, tool-execution error, malformed result, timeout)
    — it always returns `{"error": "..."}` in that case (FR-MCPCLIENT-10/11).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.decorator import audited
from app.config import get_settings
from app.llm.crypto import DecryptionError, decrypt, encrypt, mask
from app.logging import get_logger
from app.mcp.client import MCPClientError
from app.mcp.client import call_tool as _sdk_call_tool
from app.mcp.client import list_tools as _sdk_list_tools
from app.mcp.models import MCPServerConnection

log = get_logger("mcp.service")


@dataclass(frozen=True)
class ConnectionView:
    """Admin-display row for a stored connection (never carries the
    plaintext/ciphertext credential)."""

    id: int
    name: str
    url: str
    enabled: bool
    has_credential: bool
    masked_credential: str | None


def _capture_details(c: MCPServerConnection) -> dict[str, Any]:
    """Shared `capture_details` for every CRUD mutation below — the
    credential value (plaintext or ciphertext) NEVER appears here
    (FR-MCPCLIENT-5)."""
    return {"id": c.id, "name": c.name, "url": c.url, "enabled": c.enabled}


# ─── CRUD ────────────────────────────────────────────────────────────────


@audited(
    "mcp.connection_created",
    entity_type="mcp_server_connection",
    capture_details=_capture_details,
)
async def create_connection(
    session: AsyncSession,
    *,
    org_id: int,
    name: str,
    url: str,
    credential: str | None,
    created_by_user_id: int | None,
) -> MCPServerConnection:
    """Register a new connection. Defaults `enabled=False` (FR-MCPCLIENT-4)."""
    name = name.strip()
    url = url.strip()
    if not name:
        raise ValueError("name is required")
    if not url:
        raise ValueError("url is required")

    connection = MCPServerConnection(
        organization_id=org_id,
        name=name,
        url=url,
        encrypted_credential=encrypt(credential.strip()) if credential and credential.strip() else None,
        enabled=False,
        created_by_user_id=created_by_user_id,
    )
    session.add(connection)
    await session.flush()
    return connection


async def get_connection(
    session: AsyncSession, *, org_id: int, connection_id: int
) -> MCPServerConnection | None:
    """Org-scoped fetch — never returns another org's row (FR-MCPCLIENT-8)."""
    stmt = select(MCPServerConnection).where(
        MCPServerConnection.id == connection_id,
        MCPServerConnection.organization_id == org_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_connections(session: AsyncSession, *, org_id: int) -> list[ConnectionView]:
    """Org-scoped display rows, credential masked per FR-LLM's `mask()`
    convention (never the plaintext or ciphertext)."""
    stmt = (
        select(MCPServerConnection)
        .where(MCPServerConnection.organization_id == org_id)
        .order_by(MCPServerConnection.id)
    )
    rows = (await session.execute(stmt)).scalars().all()
    views: list[ConnectionView] = []
    for c in rows:
        masked: str | None = None
        if c.encrypted_credential:
            try:
                masked = mask(decrypt(c.encrypted_credential))
            except DecryptionError:
                masked = "(unreadable — wrong key?)"
        views.append(
            ConnectionView(
                id=c.id,
                name=c.name,
                url=c.url,
                enabled=c.enabled,
                has_credential=c.encrypted_credential is not None,
                masked_credential=masked,
            )
        )
    return views


@audited(
    "mcp.connection_enabled",
    entity_type="mcp_server_connection",
    capture_details=_capture_details,
)
async def enable_connection(
    session: AsyncSession, connection: MCPServerConnection
) -> MCPServerConnection:
    connection.enabled = True
    await session.flush()
    return connection


@audited(
    "mcp.connection_disabled",
    entity_type="mcp_server_connection",
    capture_details=_capture_details,
)
async def disable_connection(
    session: AsyncSession, connection: MCPServerConnection
) -> MCPServerConnection:
    connection.enabled = False
    await session.flush()
    return connection


@audited(
    "mcp.connection_deleted",
    entity_type="mcp_server_connection",
    capture_details=_capture_details,
)
async def delete_connection(
    session: AsyncSession, connection: MCPServerConnection
) -> MCPServerConnection:
    """Returns the (now-detached) row so `@audited` can still read its id
    for the audit record, matching the decorator's `getattr(result, "id")`
    contract; the caller is responsible for the actual delete."""
    await session.delete(connection)
    await session.flush()
    return connection


# ─── Discovery + invocation ─────────────────────────────────────────────


def _qualified_name(connection_name: str, tool_name: str) -> str:
    return f"{connection_name}.{tool_name}"


async def discover_tools(session: AsyncSession, org_id: int) -> list[dict[str, Any]]:
    """OpenAI-format tool specs for every tool across the org's *enabled*
    connections, qualified `<connection-name>.<tool-name>`.

    Zero enabled connections returns `[]` without opening any connection —
    the caller (translation.py) uses that to skip the `tools` kwarg
    entirely, so an org with MCP off takes the exact prior code path
    (NFR-MCPCLIENT-1).
    """
    stmt = select(MCPServerConnection).where(
        MCPServerConnection.organization_id == org_id,
        MCPServerConnection.enabled.is_(True),
    )
    connections = (await session.execute(stmt)).scalars().all()
    if not connections:
        return []

    settings = get_settings()
    specs: list[dict[str, Any]] = []
    for connection in connections:
        try:
            credential = (
                decrypt(connection.encrypted_credential)
                if connection.encrypted_credential
                else None
            )
            tools = await _sdk_list_tools(
                url=connection.url,
                credential=credential,
                timeout_seconds=settings.mcp_request_timeout_seconds,
            )
        except (MCPClientError, DecryptionError) as exc:
            # FR-MCPCLIENT-9: one bad connection is logged + skipped, never
            # fails the whole discovery pass. Never the credential.
            log.warning(
                "mcp.discover.connection_failed",
                connection_id=connection.id,
                connection_name=connection.name,
                error=str(exc),
            )
            continue

        for tool in tools:
            specs.append(
                {
                    "type": "function",
                    "function": {
                        "name": _qualified_name(connection.name, tool.name),
                        "description": tool.description or "",
                        "parameters": tool.input_schema,
                    },
                }
            )
    return specs


async def invoke_tool(
    session: AsyncSession, org_id: int, qualified_name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Invoke a previously-discovered tool. NEVER raises for a normal
    operational failure — always returns `{"error": "..."}` in that case
    (FR-MCPCLIENT-10/11), and `{"result": "..."}` on success.
    """
    if "." not in qualified_name:
        return {"error": f"malformed tool name: {qualified_name!r}"}
    connection_name, tool_name = qualified_name.split(".", 1)

    stmt = select(MCPServerConnection).where(
        MCPServerConnection.organization_id == org_id,
        MCPServerConnection.name == connection_name,
        MCPServerConnection.enabled.is_(True),
    )
    connection = (await session.execute(stmt)).scalar_one_or_none()
    if connection is None:
        # Either no such connection in THIS org (FR-MCPCLIENT-8 — never
        # resolves another org's connection even on a name collision), or
        # it has since been disabled/deleted.
        return {"error": f"no enabled MCP connection named {connection_name!r}"}

    settings = get_settings()
    try:
        credential = (
            decrypt(connection.encrypted_credential)
            if connection.encrypted_credential
            else None
        )
        result = await _sdk_call_tool(
            url=connection.url,
            credential=credential,
            tool_name=tool_name,
            arguments=arguments,
            timeout_seconds=settings.mcp_request_timeout_seconds,
        )
    except (MCPClientError, DecryptionError) as exc:
        log.info(
            "mcp.invoke.failed",
            connection_id=connection.id,
            connection_name=connection.name,
            tool_name=tool_name,
            error=str(exc),
        )
        return {"error": str(exc)}

    if result.is_error:
        text = "; ".join(getattr(part, "text", "") for part in result.content) or "tool error"
        return {"error": text}

    text = "\n".join(getattr(part, "text", "") for part in result.content)
    return {"result": text}
