"""RQ queue tests.

Functional smoke for the chassis enqueue helper. Doesn't exercise an actual
worker process — that's tested implicitly by the docker-compose `worker`
service in Phase 1.10 deploy.

Uses `os.getpid` (a real module-level callable) as the test function so RQ
accepts it.
"""

from __future__ import annotations

import os

from app.tasks import enqueue
from app.tasks.queue import get_queue


def test_enqueue_returns_job_with_id() -> None:
    job = enqueue(os.getpid)
    assert job.id
    assert job.func_name == "posix.getpid"


def test_enqueue_persists_to_redis_queue() -> None:
    initial_len = len(get_queue())
    enqueue(os.getpid)
    assert len(get_queue()) == initial_len + 1


def test_enqueue_passes_args_through() -> None:
    job = enqueue(os.path.join, "a", "b", "c")
    assert job.args == ("a", "b", "c")


def test_enqueue_passes_kwargs_through() -> None:
    # os.getenv is a module-level pickle-friendly callable that accepts
    # both args and kwargs.
    job = enqueue(os.getenv, "PATH", default="")
    assert job.args == ("PATH",)
    assert job.kwargs == {"default": ""}
