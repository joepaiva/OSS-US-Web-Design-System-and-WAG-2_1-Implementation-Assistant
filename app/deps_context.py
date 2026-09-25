"""Per-request context vars shared across chassis subsystems.

This module is import-cycle-safe: it only declares ContextVars and helper
setters/getters. It does NOT import from `app.deps`, `app.auth`, or any
service layer, so audit/RBAC/multi-tenancy can read context without pulling
in the FastAPI request stack.
"""

from __future__ import annotations

from contextvars import ContextVar

# Bound by `app.deps.get_current_user` once auth resolves. None when no
# authenticated user (CLI, RQ worker, anonymous endpoint).
current_user_id_var: ContextVar[int | None] = ContextVar(
    "chassis_current_user_id", default=None
)


def set_current_user_id(user_id: int | None) -> None:
    current_user_id_var.set(user_id)


def get_current_user_id() -> int | None:
    return current_user_id_var.get(None)


# AU-3 (chassis v0.6): bound by request_id_middleware (app/main.py) from
# request.client.host. Read by the @audited decorator in audit/decorator.py
# to populate AuditLog.ip_address. None when no FastAPI request context
# (CLI, RQ worker invocation).
current_client_ip_var: ContextVar[str | None] = ContextVar(
    "chassis_current_client_ip", default=None
)


def set_current_client_ip(ip: str | None) -> None:
    current_client_ip_var.set(ip)


def get_current_client_ip() -> str | None:
    return current_client_ip_var.get(None)
