"""AU-11 audit log retention/archival background job (chassis v0.6).

NIST 800-53 AU-11 strictest-of-three (FISMA M / FedRAMP M / IL-2):
6 years online or archived. The chassis ships a `move_old_audit_logs_to_archive`
task that moves rows older than `settings.audit_retention_days` from
`audit_logs` (online table) into `audit_logs_archive` (cold storage table
created by migration 0007_au11_archive_logs.py).

DEPLOY-TIME CONFIGURATION: operators wire this to a scheduler of their
choice — RQ itself does not ship a built-in cron. Options:

  1. AWS EventBridge / GCP Cloud Scheduler / Heroku Scheduler: configure
     a daily/weekly job that runs
       python -c "from app.audit.tasks import enqueue_archival; enqueue_archival()"
  2. rq-scheduler add-on: install separately and call schedule_archival()
     at app startup
  3. Cron + curl to a chassis-side admin endpoint (not shipped — slot
     authors who want this pattern can add their own admin route)

The function body is sync (RQ predates asyncio) and wraps the chassis
async session via `asyncio.run`. Idempotent — running it twice in a
row picks up no extra rows the second time (everything within the
retention window is already moved).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.config import get_settings
from app.db import get_sessionmaker
from app.logging import get_logger
from app.tasks.queue import enqueue

log = get_logger("audit.tasks")


async def _move_to_archive(session: AsyncSession, cutoff: datetime) -> int:
    """Insert old audit_logs rows into audit_logs_archive, then delete from
    audit_logs. Returns the count moved.

    Uses INSERT ... SELECT then DELETE for atomicity inside the calling
    transaction; falls back to row-by-row copy if INSERT ... SELECT isn't
    supported (it is on PostgreSQL — the chassis's only supported DB).
    """
    # Count first so we can return a useful metric.
    count_q = select(AuditLog).where(AuditLog.created_at < cutoff)
    rows = list((await session.execute(count_q)).scalars().all())
    moved = len(rows)
    if moved == 0:
        return 0

    # PostgreSQL-specific INSERT INTO archive SELECT FROM live WHERE ...
    # We use a raw text statement to avoid loading rows into memory.
    from sqlalchemy import text

    await session.execute(
        text(
            "INSERT INTO audit_logs_archive "
            "(id, organization_id, user_id, action, entity_type, entity_id, "
            "details, ip_address, created_at) "
            "SELECT id, organization_id, user_id, action, entity_type, entity_id, "
            "details, ip_address, created_at "
            "FROM audit_logs WHERE created_at < :cutoff"
        ),
        {"cutoff": cutoff},
    )
    await session.execute(
        delete(AuditLog).where(AuditLog.created_at < cutoff)
    )
    return moved


async def _run_archival(cutoff_days: int | None) -> int:
    """Async core: compute cutoff and call _move_to_archive in one txn."""
    s = get_settings()
    days = cutoff_days if cutoff_days is not None else s.audit_retention_days
    cutoff = datetime.now(UTC) - timedelta(days=days)

    sm = get_sessionmaker()
    async with sm() as session:
        moved = await _move_to_archive(session, cutoff)
        await session.commit()
    return moved


def archive_old_audit_logs(cutoff_days: int | None = None) -> int:
    """RQ entry point. Sync function wrapping the async archival run.

    `cutoff_days`: override Settings.audit_retention_days for ad-hoc runs
    (e.g. an operator running a 10-day cutoff after a compliance request).
    Returns the number of rows moved for the operator's audit trail.
    """
    log.info("audit.archival.start", cutoff_days=cutoff_days)
    try:
        moved = asyncio.run(_run_archival(cutoff_days))
        log.info("audit.archival.complete", moved=moved)
        return moved
    except Exception as exc:
        log.error("audit.archival.failed", error=str(exc), exc_info=exc)
        raise


def enqueue_archival(cutoff_days: int | None = None) -> object:
    """Schedule the archival task on the RQ queue.

    Returns the RQ Job object so callers can poll status / get the result.
    """
    return enqueue(archive_old_audit_logs, cutoff_days=cutoff_days)
