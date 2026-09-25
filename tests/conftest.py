"""Pytest fixtures — shared across the chassis test suite.

Key fixtures:
  - `app`        — FastAPI app instance for the test process (session-scope)
  - `client`     — httpx.AsyncClient bound to `app` (function-scope, fresh per test)
  - `session`    — AsyncSession bound to the chassis test DB (function-scope)
  - `clean_db`   — autouse: TRUNCATEs every chassis table before each test
  - `seed_rbac`  — runs seed_chassis_rbac once per session

Convenience builders (NOT factory-boy — chassis test code is small enough
that explicit constructors are clearer than declarative factories):
  - `make_user(email, password) -> dict[token, user_id]` — registers + returns token
  - `make_org(token, slug)`     — POSTs /orgs, returns org dict

Tests can also use `client_as(token)` to fix a user's auth header for the
remainder of a test's HTTP calls.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import Base, get_engine, get_sessionmaker, reset_engine_for_tests
from app.main import create_app
from app.rbac.service import seed_chassis_rbac

# Tables to truncate between tests. Order matters: dependents first (FK
# constraints with CASCADE handle most of it, but listing in reverse
# topological order avoids per-test surprises).
_CHASSIS_TABLES = [
    "audit_logs",
    "file_objects",
    "notifications",
    "llm_provider_keys",
    "org_llm_access",
    "mcp_server_connections",
    "example_notes",
    "mfa_backup_codes",
    "remediation_proposals",
    "vulnerability_findings",
    "component_inventory",
    "scan_runs",
    "fisma_audit_reports",
    "greeting_events",
    "greeting_org_settings",
    "memberships",
    "user_roles",
    "role_permissions",
    "permissions",
    "roles",
    "organizations",
    "users",
]


@pytest.fixture(scope="session")
def app() -> Iterator:
    """One FastAPI app instance per test session. Idempotent on import."""
    instance = create_app(get_settings())
    yield instance


@pytest_asyncio.fixture(scope="session")
async def _ensure_schema_and_seed() -> AsyncIterator[None]:
    """Once per session: ensure all chassis tables exist, then seed RBAC.

    Uses Base.metadata.create_all rather than running Alembic — that keeps
    pytest invocation simple. Production deploys run alembic.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # AU-11 archive table (audit_logs_archive) is created by Alembic
        # migration 0007, NOT by an ORM model, so Base.metadata.create_all
        # doesn't make it. Mirror the migration DDL here so a fresh test DB
        # (e.g. CI) has it; production still gets it via alembic. Without this
        # the test_au11_archival suite fails on any DB that hasn't run alembic.
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS audit_logs_archive (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER,
                    user_id INTEGER,
                    action VARCHAR(128) NOT NULL,
                    entity_type VARCHAR(64),
                    entity_id INTEGER,
                    details JSON NOT NULL DEFAULT '{}'::json,
                    ip_address VARCHAR(64),
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
        )

    sm = get_sessionmaker()
    async with sm() as session:
        await seed_chassis_rbac(session)
        await session.commit()

    yield

    await reset_engine_for_tests()


@pytest_asyncio.fixture(autouse=True)
async def clean_db(_ensure_schema_and_seed: None) -> AsyncIterator[None]:
    """TRUNCATE chassis tables before each test, then re-seed RBAC.

    autouse=True means every test gets a clean state without having to ask.
    The cost: ~10ms per test against local Postgres; negligible.
    """
    sm = get_sessionmaker()
    async with sm() as session:
        # TRUNCATE ... RESTART IDENTITY CASCADE drops sequences and chains
        # cascades — safer than DELETE for FK-heavy schemas.
        tables_csv = ", ".join(_CHASSIS_TABLES)
        await session.execute(text(f"TRUNCATE {tables_csv} RESTART IDENTITY CASCADE"))
        await session.commit()

        # Re-seed RBAC so permissions + roles are always present.
        await seed_chassis_rbac(session)
        await session.commit()

    yield


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """A per-test AsyncSession. Used by direct ORM assertions in tests."""
    sm = get_sessionmaker()
    async with sm() as s:
        yield s


@pytest_asyncio.fixture
async def client(app: object) -> AsyncIterator[AsyncClient]:
    """httpx.AsyncClient hitting the ASGI app directly (no real socket)."""
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ────────────────────────────────────────────────────────────────────────
# Convenience builders
# ────────────────────────────────────────────────────────────────────────


async def make_user(
    client: AsyncClient,
    email: str = "u@example.com",
    password: str = "TestPassword123!",
    full_name: str | None = None,
) -> dict[str, object]:
    """Register a user. Returns {token, user, headers}."""
    body: dict[str, object] = {"email": email, "password": password}
    if full_name:
        body["full_name"] = full_name
    resp = await client.post("/auth/register", json=body)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return {
        "token": data["access_token"],
        "user": data["user"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


async def make_org(
    client: AsyncClient,
    headers: dict[str, str],
    name: str = "Acme",
    slug: str = "acme",
) -> dict[str, object]:
    """POST /orgs as the user behind `headers`. Returns the org dict."""
    resp = await client.post(
        "/orgs", json={"name": name, "slug": slug}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
