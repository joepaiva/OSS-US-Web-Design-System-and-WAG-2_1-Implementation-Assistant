"""FastAPI application factory.

Chassis-owned. Slots register via the EXTENSION POINT marker below — LLMs
add ONE `app.include_router(...)` line per slot at the marker location.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app import __version__

# v0.7 — admin shell (User + Org management). Imported after frontend because
# app.admin.routes reuses frontend.templates / _common_context.
from app.admin.routes import admin_router
from app.auth.routes import router as auth_router
from app.config import Settings, get_settings
from app.deps_context import current_client_ip_var
from app.error_handlers import prod_exception_handler

# v0.10 — embedded files + notifications APIs (chassis-owned).
from app.files.routes import router as files_router

# v0.5 — admin shell frontend (USWDS 3.x + Stripe aesthetic).
from app.frontend import frontend_router, mount_static
from app.health.routes import router as health_router
from app.logging import configure_logging, get_logger
from app.notifications.routes import router as notifications_router
from app.orgs.routes import router as orgs_router

# ─── CHASSIS-EXTENSION-POINT: slot-routers (imports) ───────────────────
from app.slots.accessibility_assistant.routes import router as accessibility_assistant_router
# LLM-generated slots register their imports here.
from app.slots.example.routes import router as example_router
from app.slots.example_with_states.routes import (
    router as example_with_states_router,
)
from app.slots.greeting.routes import page_router as greeting_page_router
from app.slots.greeting.routes import router as greeting_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup + shutdown hooks.

    Startup runs `seed_chassis_rbac` so every chassis permission +
    admin/user role exists in the DB before the first request lands.
    Idempotent — safe across reboots and across schema migrations that
    add new permissions.
    """
    log = get_logger("main")
    log.info("chassis.startup", version=__version__)

    # FR-SYSHEALTH-5: record process start time for the System Health page.
    from app.admin.health_service import mark_started

    mark_started()

    # Seed RBAC: permissions + admin/user roles. Idempotent.
    from app.db import get_sessionmaker
    from app.rbac.service import seed_chassis_rbac

    sm = get_sessionmaker()
    async with sm() as session:
        try:
            await seed_chassis_rbac(session)
            await session.commit()
            log.info("chassis.rbac.seeded")
        except Exception as exc:
            await session.rollback()
            log.error("chassis.rbac.seed_failed", error=str(exc))
            raise

    yield
    log.info("chassis.shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Factory — configurable for tests.

    Tests construct an app with overridden settings via
    `create_app(Settings(database_url=..., env="test", ...))` so they
    don't have to monkeypatch env vars at import time.
    """
    s = settings or get_settings()
    configure_logging(s)

    app = FastAPI(
        title="autonomous-platform-chassis-python",
        description="Stack Template #1 for the SD-Agile Platform.",
        version=__version__,
        debug=s.debug,
        lifespan=lifespan,
    )

    # ─── CORS ─────────────────────────────────────────────────────────
    if s.cors_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=s.cors_origins_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # ─── Request-ID + AU-3 client-IP middleware ──────────────────────
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Stamp every request with a UUID4 request_id.

        Surfaces in `X-Request-ID` response header AND in every structlog
        log line emitted during the request. Honors a client-supplied
        request_id when present (e.g. for distributed tracing).

        AU-3 (chassis v0.6): also binds current_client_ip_var so the
        @audited decorator can read it and populate AuditLog.ip_address.
        We prefer X-Forwarded-For[0] when present (deployment behind a
        load balancer) and fall back to request.client.host. None when
        the client info isn't available (CLI tests, websockets).
        """
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)

        # AU-3: bind client IP for the audit decorator.
        client_ip: str | None = None
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            # First IP in the comma-separated list is the original client.
            client_ip = xff.split(",")[0].strip()
        elif request.client is not None:
            client_ip = request.client.host
        current_client_ip_var.set(client_ip)

        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    # ─── SC-5 rate limiting (chassis v0.10) ──────────────────────────
    # Redis fixed-window per-client limiter. No-op when disabled or in
    # env=test. Added before the error handler so 429s short-circuit early.
    from app.ratelimit.middleware import install_rate_limiting

    install_rate_limiting(app, s)

    # ─── SI-11 production error handler (chassis v0.6) ───────────────
    # Catches all uncaught Exception subclasses (NOT HTTPException —
    # FastAPI's default handler covers those). In prod, strips stack
    # traces; in dev/test, surfaces exception type + message. structlog
    # ALWAYS logs the full exception internally regardless of env.
    app.add_exception_handler(Exception, prod_exception_handler)

    # ─── Chassis-owned routers ────────────────────────────────────────
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(orgs_router)
    app.include_router(admin_router)
    app.include_router(files_router)
    app.include_router(notifications_router)

    # v0.5 — admin shell frontend. Mounts /static/ and registers HTML
    # routes (/, /dashboard, /auth/login, /auth/register, /auth/logout,
    # /account). Pure-API deployments can comment these two lines out.
    mount_static(app)
    app.include_router(frontend_router)

    # ─── CHASSIS-EXTENSION-POINT: slot-routers (registration) ─────────
    app.include_router(accessibility_assistant_router)
    # LLM-generated slots register here. One include_router call per slot.
    app.include_router(example_router)
    app.include_router(example_with_states_router)
    app.include_router(greeting_router)
    app.include_router(greeting_page_router)

    return app


# Module-level `app` for `uvicorn app.main:app`.
app = create_app()
