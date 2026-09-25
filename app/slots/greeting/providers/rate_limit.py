"""RateLimiter — sole owner of rate-limit evaluation (Constitution §3),
enforcing BR-002: 1,000 requests per rolling 60-minute window, per
organization.

"The policy value is the application's; the mechanism is the chassis's"
(DESIGN.md §6) — this binds BR-002's numbers to the same Redis-backed
counting facility app/ratelimit/middleware.py already uses (fixed-window
INCR+EXPIRE), rather than re-implementing counting. The chassis's own
limiter middleware documents the same fixed-window-vs-true-sliding-window
tradeoff as "acceptable for SC-5 edge protection"; this slot makes the
identical tradeoff for BR-002's per-org policy rather than introducing a
second counting strategy the chassis doesn't otherwise use.

Per-organization isolation: the Redis key is scoped by org_id, so one
tenant's consumption never affects another's.
"""

from __future__ import annotations

import contextlib
import time

from app.logging import get_logger

log = get_logger("slots.greeting.rate_limit")

WINDOW_SECONDS = 60 * 60  # BR-002: 60-minute window
CEILING = 1000  # BR-002: 1,000 requests


class RateLimited(Exception):
    """Raised when an organization is over BR-002's ceiling. Carries the
    seconds until the caller may retry."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"rate limited, retry after {retry_after_seconds}s")


def check(org_id: int) -> None:
    """Raise RateLimited if `org_id` is over BR-002's ceiling; otherwise
    record this request. Fail-open on a Redis outage — a limiter outage
    must not block the whole app (same discipline as the chassis's own
    ratelimit middleware)."""
    bucket = int(time.time()) // WINDOW_SECONDS
    key = f"greeting_ratelimit:{org_id}:{bucket}"

    try:
        from app.tasks.queue import get_redis

        redis = get_redis()
        count = redis.incr(key)
        if count == 1:
            redis.expire(key, WINDOW_SECONDS)
    except Exception as exc:  # noqa: BLE001 — fail-open, mirrors app/ratelimit/middleware.py
        log.warning("greeting.ratelimit_redis_unavailable", error=str(exc))
        return

    if count > CEILING:
        ttl = WINDOW_SECONDS
        with contextlib.suppress(Exception):
            ttl = max(1, int(redis.ttl(key)))
        log.info("greeting.ratelimit_exceeded", org_id=org_id)
        raise RateLimited(retry_after_seconds=ttl)
