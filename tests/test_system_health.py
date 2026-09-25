"""System Health admin page tests (chassis v0.8).

Covers the platform-admin-only RBAC gate and that the page renders live
status (version, environment, database reachable). Redis is typically not
running in the test environment; the page must still render (degraded) and
never raise — that is asserted implicitly by the 200 response.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import __chassis_version__, __version__
from app.admin.health_service import gather_system_health
from app.auth.models import User
from tests.conftest import make_org, make_user


async def _promote_to_superuser(session: AsyncSession, email: str) -> None:
    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one()
    user.is_superuser = True
    # IA-2(1) (chassis-program v1.0.0): superusers are privileged accounts
    # and MUST have MFA enrolled to use any admin-gated route.
    user.mfa_enabled = True
    await session.commit()


@pytest.mark.asyncio
async def test_unauthenticated_redirects_to_login(client: AsyncClient) -> None:
    resp = await client.get("/admin/system-health")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/login"


@pytest.mark.asyncio
async def test_regular_user_is_forbidden(client: AsyncClient) -> None:
    u = await make_user(client, email="reg-sh@example.com")
    resp = await client.get("/admin/system-health", headers=u["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_org_admin_is_forbidden(client: AsyncClient) -> None:
    # Org admins manage users but NOT system health (platform-only).
    u = await make_user(client, email="orgadmin-sh@example.com")
    await make_org(client, u["headers"], name="ShOrg", slug="shorg")
    resp = await client.get("/admin/system-health", headers=u["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_platform_admin_sees_health(
    client: AsyncClient, session: AsyncSession
) -> None:
    u = await make_user(client, email="super-sh@example.com")
    await _promote_to_superuser(session, "super-sh@example.com")

    resp = await client.get("/admin/system-health", headers=u["headers"])
    assert resp.status_code == 200
    body = resp.text
    assert "System Health" in body
    assert __version__ in body
    # DB is up in tests → reported reachable.
    assert "database" in body
    assert "reachable" in body
    # Redis row is present regardless of reachability.
    assert "redis" in body.lower()


@pytest.mark.asyncio
async def test_gather_system_health_never_raises(session: AsyncSession) -> None:
    health = await gather_system_health(session)
    assert health.version == __version__
    # chassis_version is the chassis framework version (CHASSIS_VERSION file),
    # distinct from the app package version.
    assert health.chassis_version == __chassis_version__
    # NOTE: deliberately NOT also asserting a hardcoded version literal here.
    # The assertion above pins the response to __chassis_version__, which IS the
    # source of truth; adding "and that value happens to be 1.0.1" pins a
    # SNAPSHOT, which cannot detect anything the line above misses and fails on
    # every intended bump. It went stale twice in two days (the cross-tenant
    # security fix, then AB-FR-617) and the second time the failure was masked
    # because chassis-ci was already red at a later step. Same reasoning as
    # internal/database/chassis_version_testhelper_test.go's chassisVersionOnDisk.
    assert health.chassis_version != health.version
    names = {d.name for d in health.dependencies}
    assert {"database", "redis"} <= names
    # database should be ok in the test environment.
    db = next(d for d in health.dependencies if d.name == "database")
    assert db.ok is True


def test_redact_host_strips_credentials() -> None:
    from app.admin.health_service import _redact_host

    out = _redact_host("postgresql+asyncpg://user:secret@db.example.com:5432/appdb")
    assert "secret" not in out
    assert "user" not in out
    assert out == "db.example.com:5432/appdb"


# ─── chassis-program FR-SYSHEALTH: worker, LLM proxy, started_at, extension ──


@pytest.mark.asyncio
async def test_gather_system_health_includes_worker_and_llm_proxy(
    session: AsyncSession,
) -> None:
    """FR-SYSHEALTH-3/4: worker liveness and LLM-proxy reachability are
    always present in the dependency list for this LLM-delta package,
    regardless of whether either is actually reachable in the test env."""
    health = await gather_system_health(session)
    names = {d.name for d in health.dependencies}
    assert {"database", "redis", "worker", "llm_proxy"} <= names


@pytest.mark.asyncio
async def test_gather_system_health_never_raises_when_worker_down(
    session: AsyncSession,
) -> None:
    """No RQ worker is running in the test environment — the check must
    degrade to a reported-unhealthy DependencyStatus, never raise."""
    health = await gather_system_health(session)
    worker = next(d for d in health.dependencies if d.name == "worker")
    assert worker.ok is False


def test_check_llm_proxy_reports_down_when_unreachable() -> None:
    """FR-SYSHEALTH-4: pointed at a port nothing listens on, the LLM-proxy
    check must degrade to ok=False, never raise. (The dev machine this
    suite runs on may have a real LiteLLM proxy up on the configured port,
    so this test exercises the failure path directly against a guaranteed-
    closed port instead of asserting on ambient network state.)"""
    from app.admin.health_service import _check_llm_proxy
    from app.config import Settings, get_settings

    original = get_settings()
    unreachable = Settings(
        **{**original.model_dump(), "llm_proxy_url": "http://localhost:1"}
    )
    import app.admin.health_service as health_mod

    health_mod.get_settings = lambda: unreachable  # type: ignore[assignment]
    try:
        status_ = _check_llm_proxy()
        assert status_.ok is False
        assert status_.name == "llm_proxy"
    finally:
        health_mod.get_settings = get_settings  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_gather_system_health_never_raises_regardless_of_llm_proxy_reachability(
    session: AsyncSession,
) -> None:
    """The overall gather must never raise no matter what the LLM-proxy
    check reports — this is the actual FR-SYSHEALTH-6 contract, independent
    of whether a proxy happens to be reachable on this machine."""
    health = await gather_system_health(session)
    llm_proxy = next(d for d in health.dependencies if d.name == "llm_proxy")
    assert isinstance(llm_proxy.ok, bool)


@pytest.mark.asyncio
async def test_gather_system_health_reports_started_at_once_marked(
    session: AsyncSession,
) -> None:
    """FR-SYSHEALTH-5: once app.main's lifespan calls mark_started() (which
    the `client`/`app` fixtures in this suite don't exercise — they build
    the app directly without entering the lifespan context, so this test
    calls it directly, the same way app.main's lifespan does at real
    startup), started_at is populated and carried into the snapshot."""
    from app.admin.health_service import get_started_at, mark_started

    previous = get_started_at()
    mark_started()
    try:
        health = await gather_system_health(session)
        assert health.started_at is not None
    finally:
        import app.admin.health_service as health_mod

        health_mod._started_at = previous


@pytest.mark.asyncio
async def test_system_health_page_renders_started_at(
    client: AsyncClient, session: AsyncSession
) -> None:
    u = await make_user(client, email="super-sh-started@example.com")
    await _promote_to_superuser(session, "super-sh-started@example.com")
    resp = await client.get("/admin/system-health", headers=u["headers"])
    assert resp.status_code == 200
    assert "Started at" in resp.text


def test_register_health_check_extension_point() -> None:
    """FR-SYSHEALTH-8: a slot can register an additional check by name
    without editing this module, and re-registering the same name replaces
    the prior check (idempotent under module reload)."""
    from app.admin.health_service import DependencyStatus, register_health_check

    register_health_check("_test_probe", lambda: DependencyStatus("_test_probe", True, "ok"))
    register_health_check(
        "_test_probe", lambda: DependencyStatus("_test_probe", False, "replaced")
    )
    from app.admin.health_service import _extra_checks

    assert _extra_checks["_test_probe"]().ok is False
    del _extra_checks["_test_probe"]  # don't leak into other tests


@pytest.mark.asyncio
async def test_extension_check_failure_is_reported_not_raised(
    session: AsyncSession,
) -> None:
    """A broken extension check must degrade to an unhealthy dependency
    entry, never crash the whole System Health gather."""
    from app.admin.health_service import register_health_check

    def _broken() -> None:
        raise RuntimeError("boom")

    register_health_check("_test_broken", _broken)  # type: ignore[arg-type]
    try:
        health = await gather_system_health(session)
        broken = next(d for d in health.dependencies if d.name == "_test_broken")
        assert broken.ok is False
        assert "boom" in broken.detail
    finally:
        from app.admin.health_service import _extra_checks

        del _extra_checks["_test_broken"]
