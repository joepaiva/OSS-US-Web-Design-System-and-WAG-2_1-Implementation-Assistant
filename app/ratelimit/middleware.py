"""Fixed-window per-client rate-limit middleware (chassis v0.10).

Algorithm: for each (client, window) we INCR a Redis counter keyed by the
client identity + the current window bucket, setting a TTL on first hit.
When the counter exceeds `rate_limit_requests`, return 429 with a
`Retry-After` header. This is the simplest correct limiter; it admits small
bursts at window boundaries, which is acceptable for SC-5 edge protection.

Design choices:
  - **Bound to the app's Settings**, not the global `get_settings()`, so a
    test app constructed with custom limits is honored independently of the
    process-global settings.
  - **Opt-in** (`rate_limit_enabled`, default off): the shared ASGI test
    transport reuses one client identity, so a global counter left on would
    trip 429s across unrelated tests. Operators enable it in prod; the
    dedicated rate-limit test enables it explicitly on its own app.
  - **Fail-open**: if Redis is unreachable we log and allow the request —
    a limiter outage must not take the whole app down.
  - **Exempt paths**: health/version/static are never limited.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import Settings
from app.logging import get_logger

log = get_logger("ratelimit")

_EXEMPT_PREFIXES = ("/healthz", "/readyz", "/version", "/static", "/metrics")


def _client_id(request: Request) -> str:
    """Identify the caller. Prefer X-Forwarded-For[0] (behind a proxy),
    else the socket peer, else a constant fallback."""
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        s = self._settings
        window = max(1, s.rate_limit_window_seconds)
        bucket = int(time.time()) // window
        key = f"ratelimit:{_client_id(request)}:{bucket}"

        try:
            from app.tasks.queue import get_redis

            redis = get_redis()
            count = redis.incr(key)
            if count == 1:
                redis.expire(key, window)
        except Exception as exc:  # fail-open: a limiter outage must not 500
            log.warning("ratelimit.redis_unavailable", error=str(exc))
            return await call_next(request)

        if count > s.rate_limit_requests:
            ttl = window
            with contextlib.suppress(Exception):
                ttl = max(1, int(redis.ttl(key)))
            log.info("ratelimit.exceeded", client=_client_id(request), path=path)
            return JSONResponse(
                {"detail": "Rate limit exceeded. Please retry later."},
                status_code=429,
                headers={"Retry-After": str(ttl)},
            )

        return await call_next(request)


def install_rate_limiting(app: FastAPI, settings: Settings) -> None:
    """Add the limiter when `rate_limit_enabled` is set (opt-in)."""
    if not settings.rate_limit_enabled:
        return
    app.add_middleware(RateLimitMiddleware, settings=settings)
