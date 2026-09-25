"""@audited decorator — write an AuditLog row on successful return.

Design constraints:
  - MUST work on async service functions only (sync version not provided —
    chassis is async-only).
  - MUST use the same AsyncSession passed to the wrapped function.
  - MUST NOT write on exception — chassis logs failures separately and
    audit rows imply success.
  - MUST be cheap: one INSERT, no extra round-trips.

Usage:

    from app.audit.decorator import audited

    @audited("orgs.created", entity_type="organization")
    async def create_org(session: AsyncSession, user: User, ...) -> Organization:
        ...

The decorator inspects positional + keyword args for an AsyncSession
instance. If none is found, the audit write is skipped (with a WARN log)
rather than crashing the wrapped call — the chassis prefers a missed
audit over a broken business operation.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.db import current_org_id_var
from app.deps_context import current_client_ip_var, current_user_id_var
from app.logging import get_logger

log = get_logger("audit")

T = TypeVar("T")


def audited(
    action: str,
    *,
    entity_type: str | None = None,
    capture_details: Callable[[Any], dict[str, Any]] | None = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Wrap an async service function with audit-log emission.

    Args:
        action: canonical action name (e.g. "orgs.created").
        entity_type: optional entity-type tag (e.g. "organization").
        capture_details: optional callable invoked with the wrapped
            function's return value; returns a dict written into the
            audit row's `details` column. Use for structured context
            (e.g. {"name": result.name, "slug": result.slug}). Default:
            empty dict.
    """

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapper(*args: object, **kwargs: object) -> T:
            result: T = await fn(*args, **kwargs)

            session = _find_session(args, kwargs)
            if session is None:
                log.warning(
                    "audit.session_not_found",
                    action=action,
                    wrapped=fn.__qualname__,
                )
                return result

            details: dict[str, Any] = {}
            if capture_details is not None:
                try:
                    details = capture_details(result) or {}
                except Exception as exc:
                    log.warning(
                        "audit.capture_details_failed",
                        action=action,
                        error=str(exc),
                    )

            audit_row = AuditLog(
                organization_id=current_org_id_var.get(None),
                user_id=current_user_id_var.get(None),
                action=action,
                entity_type=entity_type,
                entity_id=getattr(result, "id", None),
                details=details,
                # AU-3 (chassis v0.6): source IP address from
                # request_id_middleware. None when no FastAPI request
                # context (CLI, RQ worker invocation).
                ip_address=current_client_ip_var.get(None),
            )
            session.add(audit_row)
            await session.flush()
            return result

        return wrapper

    return decorator


def _find_session(args: tuple[object, ...], kwargs: dict[str, object]) -> AsyncSession | None:
    """Return the first AsyncSession found in args/kwargs.

    Service functions in this chassis conventionally take session as the
    first positional argument, but we accept it anywhere for flexibility.
    """
    for v in args:
        if isinstance(v, AsyncSession):
            return v
    for v in kwargs.values():
        if isinstance(v, AsyncSession):
            return v
    return None
