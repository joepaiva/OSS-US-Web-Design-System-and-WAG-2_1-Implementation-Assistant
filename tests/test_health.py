"""Health endpoint tests."""

from __future__ import annotations

from httpx import AsyncClient

from app import __chassis_version__, __version__


async def test_healthz_returns_ok(client: AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_readyz_returns_ready_when_db_ok(client: AsyncClient) -> None:
    resp = await client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"


async def test_version_returns_semver(client: AsyncClient) -> None:
    resp = await client.get("/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"]
    assert body["chassis"]
    # `version` is the app package version; `chassis` is the chassis framework
    # version read from the CHASSIS_VERSION file — these are distinct.
    assert body["version"] == __version__
    assert body["chassis"] == __chassis_version__
    # NOTE: deliberately NOT also asserting a hardcoded version literal here.
    # The assertion above pins the response to __chassis_version__, which IS the
    # source of truth; adding "and that value happens to be 1.0.1" pins a
    # SNAPSHOT, which cannot detect anything the line above misses and fails on
    # every intended bump. It went stale twice in two days (the cross-tenant
    # security fix, then AB-FR-617) and the second time the failure was masked
    # because chassis-ci was already red at a later step. Same reasoning as
    # internal/database/chassis_version_testhelper_test.go's chassisVersionOnDisk.
    assert body["version"] != body["chassis"]
