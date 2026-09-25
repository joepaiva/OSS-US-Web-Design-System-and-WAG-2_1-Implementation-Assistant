"""Background tasks via RQ (Redis Queue).

Single worker process for v0.1.0 chassis. Multi-queue setup is a v1.x
expansion when slot workloads demand it.

Public API:
  from app.tasks import enqueue
  enqueue(my_task_func, *args, **kwargs)
"""

from app.tasks.queue import enqueue  # re-export for convenience

__all__ = ["enqueue"]
