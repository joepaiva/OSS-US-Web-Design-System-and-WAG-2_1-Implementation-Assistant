"""RQ queue setup + enqueue helper.

NOTE: RQ tasks are sync functions (RQ predates Python's asyncio). For async
work, wrap with `asyncio.run(...)` inside the task body. The chassis ships
no built-in tasks in v0.1.0; slots register their own.

LLM-generated slots define tasks as regular module-level functions:

    # app/slots/inventory/tasks.py
    def reindex_inventory(org_id: int) -> None:
        # sync body; for DB access, open a sync session via the chassis
        # sync-engine helper (not provided in v0.1.0 — slots use httpx for
        # everything in the meantime).
        ...

And enqueue them:

    from app.tasks import enqueue
    from app.slots.inventory.tasks import reindex_inventory
    enqueue(reindex_inventory, org_id=42)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from redis import Redis
from rq import Queue

from app.config import get_settings
from app.logging import get_logger

log = get_logger("tasks")

_redis: Redis | None = None
_queue: Queue | None = None

QUEUE_NAME = "default"


def get_redis() -> Redis:
    """Lazy-init the shared Redis connection used by RQ."""
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url)
    return _redis


def get_queue() -> Queue:
    """Lazy-init the default RQ queue. One queue is sufficient for v0.1.0."""
    global _queue
    if _queue is None:
        _queue = Queue(QUEUE_NAME, connection=get_redis())
    return _queue


def enqueue(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Enqueue `fn(*args, **kwargs)` for background execution.

    Returns the RQ Job object so callers can hold a handle for status checks.
    """
    job = get_queue().enqueue(fn, *args, **kwargs)
    log.info("tasks.enqueued", fn=fn.__qualname__, job_id=job.id)
    return job
