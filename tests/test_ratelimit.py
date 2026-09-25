"""Rate-limit middleware tests (chassis v0.10).

Rate limiting is opt-in (off by default), so the shared suite is unaffected.
Here we build a dedicated app with the limiter enabled, a low limit, and a
fake Redis so the real limiter path is exercised hermetically (no running
Redis required).
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

import app.tasks.queue as queue_mod
from app.config import get_settings
from app.main import create_app


class _FakeRedis:
    """Minimal INCR/EXPIRE/TTL counter backing the limiter in tests."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key: str, seconds: int) -> bool:
        return True

    def ttl(self, key: str) -> int:
        return 42


def _dev_app(**overrides):
    base = get_settings()
    dev = base.model_copy(update={"rate_limit_enabled": True, **overrides})
    return create_app(dev)


@pytest.mark.asyncio
async def test_limiter_off_by_default() -> None:
    # The default suite app (rate_limit_enabled=False) must NOT install it.
    from app.ratelimit.middleware import RateLimitMiddleware

    app = create_app(get_settings())
    assert not any(
        getattr(m, "cls", None) is RateLimitMiddleware for m in app.user_middleware
    )


@pytest.mark.asyncio
async def test_requests_over_limit_get_429(monkeypatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(queue_mod, "get_redis", lambda: fake)

    app = _dev_app(rate_limit_requests=3, rate_limit_window_seconds=60)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # First 3 allowed (landing redirects to login → 303).
        for _ in range(3):
            r = await c.get("/auth/login")
            assert r.status_code == 200
        # 4th exceeds the window limit.
        r = await c.get("/auth/login")
        assert r.status_code == 429
        assert int(r.headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_health_endpoints_exempt(monkeypatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(queue_mod, "get_redis", lambda: fake)
    app = _dev_app(rate_limit_requests=1, rate_limit_window_seconds=60)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for _ in range(5):
            r = await c.get("/healthz")
            assert r.status_code == 200  # never limited


@pytest.mark.asyncio
async def test_fail_open_when_redis_down(monkeypatch) -> None:
    def _boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(queue_mod, "get_redis", _boom)
    app = _dev_app(rate_limit_requests=1, rate_limit_window_seconds=60)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for _ in range(5):
            r = await c.get("/auth/login")
            assert r.status_code == 200  # limiter fails open, never 429
