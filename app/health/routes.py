"""Health, readiness, version endpoints.

Three distinct concerns:
  - /healthz  — process is up. Always 200 if the app is serving requests.
  - /readyz   — process is up AND downstream dependencies (DB, Redis) are
                reachable. Returns 503 if any check fails. Used by orchestrators
                to gate traffic.
  - /version  — chassis version + git sha for ops visibility.

Pydantic v2 response models: ConfigDict, not class Config. See
ARCHITECTURE.md §2.1.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from app import __chassis_version__, __version__
from app.db import SessionDep
from app.logging import get_logger

log = get_logger("health")

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "degraded"]
    checks: dict[str, str]


class VersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    chassis: str


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    """Liveness: 'is the process serving requests?'

    Trivial; never reaches further than the application layer. Use /readyz
    for dependency checks.
    """
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=ReadinessResponse)
async def readyz(session: SessionDep, response: Response) -> ReadinessResponse:
    """Readiness: 'are all downstream dependencies reachable?'

    Pings Postgres via `SELECT 1`. Future expansion: Redis ping, S3 head, etc.
    Returns 503 when any check fails so load balancers route traffic away.
    """
    checks: dict[str, str] = {}
    degraded = False

    try:
        result = await session.execute(text("SELECT 1"))
        result.scalar_one()
        checks["database"] = "ok"
    except Exception as exc:
        log.warning("readyz.database_check_failed", error=str(exc))
        checks["database"] = f"error: {exc}"
        degraded = True

    if degraded:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="degraded" if degraded else "ready",
        checks=checks,
    )


@router.get("/version", response_model=VersionResponse)
async def version() -> VersionResponse:
    """Version metadata for ops visibility.

    `version` is the app package version (semver from pyproject); `chassis`
    is the chassis framework version read from the `CHASSIS_VERSION` file at
    import time. These differ: an app carries its own version while reporting
    the chassis it was generated against.
    """
    return VersionResponse(version=__version__, chassis=__chassis_version__)
