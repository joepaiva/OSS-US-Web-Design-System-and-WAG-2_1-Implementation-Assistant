"""Thin wrapper around the `mcp` SDK's client API (chassis v1.1.0, FR-MCPCLIENT).

Isolates every SDK/transport call behind two functions so `app/mcp/service.py`
never imports `mcp` directly and never has to reason about the SDK's own
exception types. Any failure -- unreachable server, protocol error, auth
rejection, timeout -- is caught here and re-raised as `MCPClientError`; the
caller (`service.py`) decides what "graceful degradation" means for that
failure (skip a connection at discovery time, or report `{"error": ...}` at
invocation time). This module itself always either returns a result or
raises `MCPClientError` -- it never lets a raw SDK/httpx exception escape.

API surface confirmed by direct inspection of the installed `mcp==2.2.0`
package (chassis-program-DESIGN.md §6.1's mandate -- a web-fetched doc
snippet is not a substitute for reading the installed package):
  - `mcp.Client` is the modern high-level streamable-HTTP client. Passing a
    bare URL string builds a default transport with no custom headers;
    auth headers / timeout are configured by building the transport
    ourselves via `mcp.client.streamable_http.streamable_http_client(url,
    http_client=<client>)` and passing that transport as the `server=`
    argument instead.
  - The SDK's own HTTP client dependency is `httpx2` (its own vendored
    successor to `httpx`, a SEPARATE PyPI distribution from this chassis's
    `httpx` pin -- `streamable_http_client`'s `http_client` parameter is
    typed `httpx2.AsyncClient | None`, confirmed by mypy rejecting a plain
    `httpx.AsyncClient` here even though the two share an near-identical
    API surface). This module builds an `httpx2.AsyncClient`, never the
    chassis's own `httpx`, specifically for this SDK boundary.
  - `Client.list_tools()` returns `ListToolsResult` (`.tools: list[Tool]`,
    each with `.name`/`.description`/`.input_schema`).
  - `Client.call_tool(name, arguments, read_timeout_seconds=...)` returns
    `CallToolResult` (`.content`, `.is_error`) for a normal tool-reported
    outcome (including a tool-reported error -- e.g. the fixture server's
    `lookup` on an unknown key); it *raises* only for a transport/protocol
    failure, which this module converts to `MCPClientError`.
"""

from __future__ import annotations

from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_types import CallToolResult, Tool


class MCPClientError(Exception):
    """Raised for any MCP client-side failure: unreachable server, auth
    rejection at the transport level, protocol error, or timeout. Never a
    tool-reported error (that comes back as a normal `CallToolResult` with
    `is_error=True`)."""


def _headers(credential: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {credential}"} if credential else {}


async def list_tools(
    *, url: str, credential: str | None, timeout_seconds: float
) -> list[Tool]:
    """Connect to `url`, list its tools, return the SDK's `Tool` objects.

    Raises `MCPClientError` on any connection/protocol failure -- callers
    (`service.discover_tools`) catch this per-connection so one unreachable
    server never fails the whole discovery pass (FR-MCPCLIENT-9).
    """
    try:
        async with httpx2.AsyncClient(
            headers=_headers(credential), timeout=timeout_seconds
        ) as http_client, Client(
            streamable_http_client(url, http_client=http_client),
            read_timeout_seconds=timeout_seconds,
        ) as client:
            result = await client.list_tools()
            return list(result.tools)
    except MCPClientError:
        raise
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: SDK/httpx/anyio
        # exception shapes are not part of this chassis's stable surface; every
        # one of them must degrade to the same typed failure (FR-MCPCLIENT-9).
        raise MCPClientError(str(exc)) from exc


async def call_tool(
    *,
    url: str,
    credential: str | None,
    tool_name: str,
    arguments: dict[str, Any],
    timeout_seconds: float,
) -> CallToolResult:
    """Invoke `tool_name` on the server at `url`. Returns the raw
    `CallToolResult` (`.is_error` distinguishes a tool-reported failure from
    success -- both are normal, non-raising outcomes).

    Raises `MCPClientError` only for a connection/protocol/auth failure at
    the transport level (FR-MCPCLIENT-10/11) -- callers
    (`service.invoke_tool`) convert that into a `{"error": ...}` payload,
    never an unhandled exception.
    """
    try:
        async with httpx2.AsyncClient(
            headers=_headers(credential), timeout=timeout_seconds
        ) as http_client, Client(
            streamable_http_client(url, http_client=http_client),
            read_timeout_seconds=timeout_seconds,
        ) as client:
            return await client.call_tool(
                tool_name, arguments, read_timeout_seconds=timeout_seconds
            )
    except MCPClientError:
        raise
    except Exception as exc:  # noqa: BLE001 -- see list_tools's note above.
        raise MCPClientError(str(exc)) from exc
