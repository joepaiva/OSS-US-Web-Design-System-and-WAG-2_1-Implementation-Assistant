"""System Health gathering for the admin shell (chassis-program FR-SYSHEALTH,
chassis v1.1.0-mt-fisma-moderate-llm).

Collects human-readable operational status for the `/admin/system-health`
page: app + chassis version, process start time, environment, and live
reachability of the database, Redis, the background-worker pool, and (this
package carries the LLM delta, FR-SYSHEALTH-4) the configured LLM proxy.
Every check is best-effort and NEVER raises — a failed dependency is
reported as a status string, not an exception, so the page always renders
even when something is down (that is precisely when an operator needs it).
Total check time is bounded (FR-SYSHEALTH-6) via short per-check timeouts.

Secrets discipline: we report the database HOST and NAME only, never the
full DSN (which carries credentials), and we never echo the Redis URL's
password component. The LLM-proxy check is a bare reachability probe
(FR-SYSHEALTH-4) — it NEVER performs a real, billed chat completion.

Extension point (FR-SYSHEALTH-8): slots register additional dependency
checks via `register_health_check()` below without modifying this module.
"""

from __future__ import annotations

import contextlib
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __chassis_version__, __version__
from app.config import get_settings
from app.logging import get_logger

log = get_logger("admin.health")

# ─── Process start time (FR-SYSHEALTH-5) ───────────────────────────────
# Set once by app.main's lifespan startup hook. Read-only from here.
_started_at: datetime | None = None


def mark_started() -> None:
    """Record the process start timestamp. Called once from app startup."""
    global _started_at
    _started_at = datetime.now(UTC)


def get_started_at() -> datetime | None:
    """Return the process start timestamp, or None before startup completes."""
    return _started_at


@dataclass(frozen=True)
class DependencyStatus:
    """One downstream dependency's reachability."""

    name: str
    ok: bool
    detail: str  # "reachable", or a short error/redacted message


@dataclass(frozen=True)
class SystemHealth:
    """Aggregate health snapshot rendered by the system-health page."""

    version: str
    chassis_version: str
    env: str
    debug: bool
    dependencies: list[DependencyStatus]
    started_at: datetime | None = None

    @property
    def all_ok(self) -> bool:
        return all(d.ok for d in self.dependencies)

    @property
    def overall(self) -> str:
        return "healthy" if self.all_ok else "degraded"


# ─── CHASSIS-EXTENSION-POINT: system-health-checks (FR-SYSHEALTH-8) ──────
# Slots register additional dependency checks here without editing this
# file. A check is any zero-arg callable — sync or async — returning a
# DependencyStatus. Registration is idempotent by name (re-registering the
# same name replaces the prior check, so a slot module can be re-imported
# safely, e.g. under test reload).
#
# Example:
#     from app.admin.health_service import register_health_check, DependencyStatus
#     def _check_inventory_api() -> DependencyStatus:
#         ...
#         return DependencyStatus("inventory_api", True, "reachable")
#     register_health_check("inventory_api", _check_inventory_api)
# ───────────────────────────────────────────────────────────────────────

_ExtraCheck = Callable[[], "DependencyStatus | Awaitable[DependencyStatus]"]
_extra_checks: dict[str, _ExtraCheck] = {}


def register_health_check(name: str, check: _ExtraCheck) -> None:
    """Register (or replace) an additional System Health dependency check."""
    _extra_checks[name] = check


async def _run_extra_checks() -> list[DependencyStatus]:
    """Run every registered extension check. Never raises — a broken check
    is reported as an unhealthy dependency, not allowed to crash the page.
    """
    results: list[DependencyStatus] = []
    for name, check in _extra_checks.items():
        try:
            outcome = check()
            if inspect.isawaitable(outcome):
                outcome = await outcome
            results.append(outcome)
        except Exception as exc:  # noqa: BLE001 — extension checks are untrusted
            log.warning("system_health.extension_check_failed", name=name, error=str(exc))
            results.append(DependencyStatus(name, False, f"check raised: {exc}"))
    return results


def _redact_host(url: str) -> str:
    """Return 'host:port/path' for a DSN, dropping any credentials.

    Best-effort: on any parse failure return a generic placeholder rather
    than risk echoing a secret.
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "?"
        port = f":{parsed.port}" if parsed.port else ""
        path = parsed.path or ""
        return f"{host}{port}{path}"
    except Exception:
        return "(unparseable)"


async def _check_database(session: AsyncSession) -> DependencyStatus:
    settings = get_settings()
    location = _redact_host(settings.database_url)
    try:
        result = await session.execute(text("SELECT 1"))
        result.scalar_one()
        return DependencyStatus("database", True, f"reachable — {location}")
    except Exception as exc:
        log.warning("system_health.database_check_failed", error=str(exc))
        return DependencyStatus("database", False, f"unreachable — {location}")


def _check_redis() -> DependencyStatus:
    """Ping Redis with a short timeout so a down Redis can't hang the page.

    We build a throwaway client with explicit connect/read timeouts instead
    of reusing the shared (timeout-less) RQ connection.
    """
    settings = get_settings()
    location = _redact_host(settings.redis_url)
    try:
        from redis import Redis

        client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        try:
            client.ping()
            return DependencyStatus("redis", True, f"reachable — {location}")
        finally:
            with contextlib.suppress(Exception):
                client.close()
    except Exception as exc:
        log.warning("system_health.redis_check_failed", error=str(exc))
        return DependencyStatus("redis", False, f"unreachable — {location}")


def _check_worker() -> DependencyStatus:
    """RQ background-worker liveness (FR-SYSHEALTH-3).

    Reports how many RQ workers are currently registered against the
    chassis queue and, if any, how long since the most recently active
    worker's last heartbeat. Zero registered workers is reported as a
    (non-crashing) unhealthy status — an operator running this chassis
    with background jobs enabled needs to know no worker is consuming
    the queue, same rationale as DB/Redis reachability.
    """
    try:
        from rq import Worker

        from app.tasks.queue import get_redis

        conn = get_redis()
        workers = Worker.all(connection=conn)
        if not workers:
            return DependencyStatus("worker", False, "no workers registered")
        newest = max((w.last_heartbeat for w in workers if w.last_heartbeat), default=None)
        if newest is None:
            return DependencyStatus(
                "worker", True, f"{len(workers)} registered, no heartbeat yet"
            )
        age_s = (datetime.now(UTC) - newest.replace(tzinfo=UTC)).total_seconds()
        return DependencyStatus(
            "worker", True, f"{len(workers)} registered, last heartbeat {age_s:.0f}s ago"
        )
    except Exception as exc:
        log.warning("system_health.worker_check_failed", error=str(exc))
        return DependencyStatus("worker", False, f"unreachable — {exc}")


def _check_llm_proxy() -> DependencyStatus:
    """LLM proxy reachability (FR-SYSHEALTH-4, LLM-delta packages only).

    A bare TCP/HTTP reachability probe against the configured LiteLLM
    proxy base URL. Deliberately NEVER issues a real chat completion —
    that would be a billed call just to render a health page. A short
    timeout keeps this from hanging the whole System Health page if the
    proxy is down.
    """
    settings = get_settings()
    location = _redact_host(settings.llm_proxy_url)
    try:
        import httpx

        with httpx.Client(timeout=0.75) as http_client:
            resp = http_client.get(f"{settings.llm_proxy_url}/health/liveliness")
            if resp.status_code < 500:
                return DependencyStatus("llm_proxy", True, f"reachable — {location}")
            return DependencyStatus(
                "llm_proxy", False, f"HTTP {resp.status_code} — {location}"
            )
    except Exception as exc:
        log.warning("system_health.llm_proxy_check_failed", error=str(exc))
        return DependencyStatus("llm_proxy", False, f"unreachable — {location}")


async def gather_system_health(session: AsyncSession) -> SystemHealth:
    """Collect the full health snapshot. Never raises."""
    settings = get_settings()
    db = await _check_database(session)
    redis = _check_redis()
    worker = _check_worker()
    # FR-SYSHEALTH-4: LLM-delta packages only. This package carries the LLM
    # delta (chassis-program variant 3), so the check always runs here.
    llm_proxy = _check_llm_proxy()
    extra = await _run_extra_checks()
    return SystemHealth(
        version=__version__,
        chassis_version=__chassis_version__,
        env=settings.env,
        debug=settings.debug,
        dependencies=[db, redis, worker, llm_proxy, *extra],
        started_at=get_started_at(),
    )
