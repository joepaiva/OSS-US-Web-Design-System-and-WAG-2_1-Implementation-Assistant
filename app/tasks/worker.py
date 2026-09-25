"""RQ worker entry point.

Run via:
    python -m app.tasks.worker

Or, in docker-compose, the `worker` service uses this as its CMD.
"""

from __future__ import annotations

from rq import Worker

from app.config import get_settings
from app.logging import configure_logging, get_logger
from app.tasks.queue import QUEUE_NAME, get_queue, get_redis


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    log = get_logger("worker")
    log.info("worker.starting", queue=QUEUE_NAME)

    worker = Worker(
        queues=[get_queue()],
        connection=get_redis(),
    )
    # work() blocks until a SIGINT/SIGTERM.
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
