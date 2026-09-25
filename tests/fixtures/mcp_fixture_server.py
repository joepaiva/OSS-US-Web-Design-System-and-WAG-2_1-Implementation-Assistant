"""In-process MCP fixture server for tests (chassis v1.1.0, FR-MCPCLIENT,
DESIGN.md §6.14).

Exposes exactly two tools, per the task's acceptance criterion:
  - `echo(text: str) -> str` — returns its input, proves argument passing.
  - `lookup(key: str) -> str` — returns a fixed value for a known key, else
    raises (the SDK converts an uncaught tool exception into a
    `CallToolResult(is_error=True, ...)` automatically — confirmed by
    direct execution against the installed `mcp==2.2.0` package), proving
    the tool-reported-error path a test can assert on.

Never imported by the shipped app — `tests/` only.

Served by a real (if test-local) `uvicorn.Server` on a fixed local port.
An `httpx.ASGITransport`-only harness was tried first and found
insufficient: `MCPServer.streamable_http_app()`'s session-manager task
group is only initialized inside the ASGI `lifespan` protocol, which
`httpx.ASGITransport` does not drive — every request raised `RuntimeError:
Task group is not initialized. Make sure to use run().` A real uvicorn
server (which does run the lifespan) is the confirmed-working shape.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from mcp.server.mcpserver import MCPServer

#: fixed key -> value map for the `lookup` tool's happy path.
LOOKUP_TABLE: dict[str, str] = {
    "greeting_style": "formal",
    "regional_convention": "a warm handshake and direct eye contact",
}


def build_fixture_server() -> MCPServer:
    """Construct a fresh `MCPServer` with the two fixture tools. A fresh
    instance per call avoids the SDK's duplicate-tool-registration warning
    when multiple tests each build their own server."""
    server: MCPServer = MCPServer(name="fixture")

    @server.tool()
    def echo(text: str) -> str:
        """Echo back the given text."""
        return text

    @server.tool()
    def lookup(key: str) -> str:
        """Look up a fixed key. Raises on an unknown key -- the SDK turns
        this into a tool-reported CallToolResult(is_error=True), proving
        the tool-reported-error path (FR-MCPCLIENT-11)."""
        if key not in LOOKUP_TABLE:
            raise ValueError(f"unknown key: {key!r}")
        return LOOKUP_TABLE[key]

    return server


class _BearerGate:
    """Minimal ASGI middleware simulating an MCP server that requires
    authentication: any HTTP request whose `Authorization` header isn't
    exactly `Bearer {required_token}` gets a 401. Used to exercise
    FR-MCPCLIENT-10's auth-failure degradation path against a real (if
    fake-auth) server rather than mocking the SDK.

    Passes the `lifespan` scope through untouched so the wrapped
    `MCPServer` app's session-manager task group still initializes.
    """

    def __init__(self, app: object, required_token: str) -> None:
        self._app = app
        self._required = f"Bearer {required_token}".encode("latin-1")

    async def __call__(self, scope: dict, receive: object, send: object) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)  # type: ignore[operator]
            return
        headers = dict(scope.get("headers") or [])
        if headers.get(b"authorization") != self._required:
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
            return
        await self._app(scope, receive, send)  # type: ignore[operator]


@asynccontextmanager
async def run_fixture_server(*, port: int) -> AsyncIterator[str]:
    """Start the (unauthenticated) fixture server on `127.0.0.1:{port}` for
    the duration of the `async with` block; yields its base MCP endpoint
    URL (`http://127.0.0.1:{port}/mcp`). Torn down on exit."""
    app = build_fixture_server().streamable_http_app()
    async with _serve(app, port=port) as url:
        yield url


@asynccontextmanager
async def run_auth_protected_fixture_server(
    *, port: int, required_token: str
) -> AsyncIterator[str]:
    """Same fixture tools, gated by `_BearerGate` — a request without
    exactly `Bearer {required_token}` gets a 401 (FR-MCPCLIENT-10)."""
    app = _BearerGate(build_fixture_server().streamable_http_app(), required_token)
    async with _serve(app, port=port) as url:
        yield url


@asynccontextmanager
async def _serve(app: object, *, port: int) -> AsyncIterator[str]:
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")  # type: ignore[arg-type]
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    try:
        # uvicorn.Server.started is a plain bool with no async-native
        # equivalent to await (no public asyncio.Event) -- polling at a
        # short, bounded interval is the standard idiom for this exact
        # wait in test harnesses. noqa: this chassis's ASYNC lint rule set
        # otherwise forbids exactly this shape.
        while not server.started:  # noqa: ASYNC110
            await asyncio.sleep(0.02)
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        await task
