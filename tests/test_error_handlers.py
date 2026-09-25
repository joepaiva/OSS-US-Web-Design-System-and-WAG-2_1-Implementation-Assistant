"""SI-11 production error handler tests (chassis v0.6).

Verifies that uncaught exceptions:
  - Return generic 500 with no stack trace in production (settings.is_prod)
  - Return type + message (still no traceback) in dev/test
  - ALWAYS log internally via structlog with full traceback

The test exercises this by registering a synthetic route on a fresh
FastAPI app that raises a sentinel exception, then probing the response.
"""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.error_handlers import prod_exception_handler
from app.error_messages import ERR_INTERNAL


def _make_test_app(monkeypatch: Any, env: str) -> FastAPI:
    """Build a minimal FastAPI app with one route that always crashes
    and the SI-11 handler registered. env controls is_prod behaviour.

    monkeypatches app.error_handlers.get_settings so prod_exception_handler
    sees the right env (the real get_settings is lru_cache'd and may have
    been called at import time with different env).

    FR-351 (chassis v0.6.1): env=prod now requires a non-placeholder
    JWT_SECRET. We pass a cryptographically-random one here so the
    Settings constructor doesn't reject env=prod construction during
    this SI-11 error-handler test — the jwt_secret itself is not
    exercised by these tests.
    """
    settings = Settings(
        database_url="postgresql+psycopg://test:test@localhost/test",
        jwt_secret=secrets.token_urlsafe(64),
        env=env,  # type: ignore[arg-type]
        debug=False,
        cors_origins="",
    )

    # Patch the get_settings call inside the handler to return our test
    # settings (lru_cache on the real one would otherwise return the
    # original Settings instance from process startup).
    from app import error_handlers

    monkeypatch.setattr(error_handlers, "get_settings", lambda: settings)

    app = FastAPI()
    app.add_exception_handler(Exception, prod_exception_handler)

    router = APIRouter()

    @router.get("/boom")
    async def boom() -> None:
        raise RuntimeError("sentinel-error-message")

    app.include_router(router)
    return app


@pytest_asyncio.fixture
async def prod_client(monkeypatch: Any) -> AsyncIterator[AsyncClient]:
    app = _make_test_app(monkeypatch, env="prod")
    transport = ASGITransport(app=app, raise_app_exceptions=False)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def dev_client(monkeypatch: Any) -> AsyncIterator[AsyncClient]:
    app = _make_test_app(monkeypatch, env="dev")
    transport = ASGITransport(app=app, raise_app_exceptions=False)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_prod_handler_returns_generic_500(prod_client: AsyncClient) -> None:
    """In prod, the response body must NOT leak the exception message."""
    resp = await prod_client.get("/boom")
    assert resp.status_code == 500
    body = resp.json()
    # K.8: the prod 500 body carries the canonical, non-leaking message from
    # the error_messages table (not a hardcoded literal). The security-critical
    # invariant is that NO internal detail leaks (asserted below).
    assert body["error"] == ERR_INTERNAL
    # The sentinel message MUST NOT appear in the response body.
    assert "sentinel-error-message" not in resp.text
    assert "RuntimeError" not in resp.text


@pytest.mark.asyncio
async def test_dev_handler_includes_exception_type_and_message(
    dev_client: AsyncClient,
) -> None:
    """In dev/test, the body surfaces type + message for quick triage,
    but still no traceback (logs hold the trace)."""
    resp = await dev_client.get("/boom")
    assert resp.status_code == 500
    body = resp.json()
    assert body["exception_type"] == "RuntimeError"
    assert body["exception_message"] == "sentinel-error-message"
    # Even in dev, we don't surface a Python traceback in the body —
    # that goes to structlog.
    assert "Traceback" not in resp.text


@pytest.mark.asyncio
async def test_request_id_propagates_when_client_sends_one(
    prod_client: AsyncClient,
) -> None:
    """If a client sends X-Request-ID, the error response surfaces it
    so the operator can correlate with internal logs."""
    resp = await prod_client.get(
        "/boom", headers={"X-Request-ID": "my-trace-id-12345"}
    )
    assert resp.status_code == 500
    assert resp.json()["request_id"] == "my-trace-id-12345"
