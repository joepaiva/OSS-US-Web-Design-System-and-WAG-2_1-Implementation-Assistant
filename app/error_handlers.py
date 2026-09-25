"""Production error handlers — SI-11 (chassis v0.6).

In production (settings.env == "prod"), uncaught exceptions return a
GENERIC 500 response that reveals NOTHING about the internal failure:

    {"error": "Internal server error", "request_id": "<uuid>"}

In dev/test environments, full traceback is returned so developers can
debug. structlog ALWAYS logs the full exception with traceback so the
operator can correlate the response request_id with internal logs even
in production.

This implements NIST 800-53 SI-11 (Error Handling): "The information
system: handles error conditions by — Generating error messages that
provide information necessary for corrective actions without revealing
information that could be exploited by adversaries."

Registered in app/main.py:create_app() via app.add_exception_handler.

HTTPException is intentionally NOT handled here — FastAPI's default
HTTPException handler is correct (it returns the operator-controlled
status code and detail). This handler catches the residual case where
slot code (or a chassis bug) raises an uncaught Exception.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.error_messages import ERR_INTERNAL
from app.logging import get_logger

log = get_logger("chassis.errors")


def _current_request_id(request: Request) -> str | None:
    """Extract the request_id stamped by request_id_middleware (main.py).

    The middleware writes it to response.headers + structlog contextvars.
    For the EXCEPTION path the response object doesn't exist yet, so we
    pull from the request scope where it was originally placed. As a
    safety net, the empty string maps to None so the JSON omits the key.
    """
    # The middleware passes via structlog contextvars but we can also
    # surface it via request.scope which is set by FastAPI.
    rid = request.headers.get("X-Request-ID")
    if rid:
        return rid
    # Fall back to whatever structlog has bound for this request.
    try:
        import structlog

        bound = structlog.contextvars.get_contextvars()
        return bound.get("request_id")
    except Exception:
        return None


async def prod_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Generic 500 handler — strips stack trace in production.

    SI-11 rationale: returning the raw stack trace exposes file paths,
    library versions, and code structure that an adversary can use to
    fingerprint the application or plan further attacks. In production
    we return a minimal opaque response and rely on the request_id +
    internal structlog logs to correlate for triage.
    """
    settings: Settings = get_settings()
    rid = _current_request_id(request)

    # ALWAYS log the full exception internally — operator must be able
    # to triage. structlog includes traceback automatically when
    # exc_info=True is passed.
    log.error(
        "chassis.unhandled_exception",
        request_id=rid,
        path=request.url.path,
        method=request.method,
        exc_info=exc,
    )

    if settings.is_prod:
        # K.8: pull the user-facing string from the canonical table so
        # every chassis-deployed app says the same thing for 500s and
        # so the message stays tone-consistent with 401/403/etc.
        body: dict[str, object] = {"error": ERR_INTERNAL}
        if rid:
            body["request_id"] = rid
        return JSONResponse(status_code=500, content=body)

    # Non-prod: surface the type + message (but NOT full traceback in the
    # response — structlog already logged the trace). This gives devs a
    # quick visual cue while keeping the body compact.
    body = {
        "error": ERR_INTERNAL + " (dev)",
        "exception_type": type(exc).__name__,
        "exception_message": str(exc),
    }
    if rid:
        body["request_id"] = rid
    return JSONResponse(status_code=500, content=body)
