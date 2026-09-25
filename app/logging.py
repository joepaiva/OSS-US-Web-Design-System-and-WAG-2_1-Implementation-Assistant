"""Structured logging via structlog.

Pretty colored output in dev (env=dev), JSON in prod (env=prod). Always
attaches request_id / user_id / org_id when bound via context vars.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from app.config import Settings


def _add_log_level_upper(_: object, method_name: str, event_dict: EventDict) -> EventDict:
    event_dict["level"] = method_name.upper()
    return event_dict


def configure_logging(settings: Settings) -> None:
    """Wire up structlog + stdlib logging.

    Call once at app startup. Idempotent — safe to call multiple times in
    tests; subsequent calls overwrite the first configuration.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stdout,
        force=True,
    )

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        _add_log_level_upper,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Processor
    if settings.log_json or settings.is_prod:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    """Convenience accessor mirroring structlog.get_logger.

    Using Any for the return type because structlog's stub erases the
    bound-logger type after `make_filtering_bound_logger`; pinning it
    here would force every call-site to import structlog types.
    """
    return structlog.get_logger(name) if name else structlog.get_logger()
