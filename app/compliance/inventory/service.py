"""Platform Health service — component inventory, currency, vulnerability
scan, and gated remediation (FR-PLATHEALTH), scoped to this package's own
dependency tree.

Determinism (FR-PLATHEALTH-2): inventory + vulnerability data come ONLY
from `pip-audit` (this package's actual installed environment, matching
its committed `uv.lock`) — never website scraping. Currency data comes
from PyPI's own JSON API (the authoritative registry for this ecosystem),
queried only for DIRECT dependencies (parsed from pyproject.toml) to keep
scan time bounded.

Fail-closed (FR-PLATHEALTH-11): if pip-audit itself cannot run (offline,
timeout, crash), the scan run is persisted with status "failed"/"offline"
and NO inventory/vulnerability rows are written for it — callers MUST
consult `get_latest_successful_scan()` for a "last known good, dated"
result rather than treating an empty/missing latest run as "clean".
"""

from __future__ import annotations

import asyncio
import json
import tomllib
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.decorator import audited
from app.compliance.inventory.models import (
    ComponentInventoryItem,
    RemediationProposal,
    ScanRun,
    VulnerabilityFinding,
)
from app.config import get_settings
from app.logging import get_logger

log = get_logger("compliance.inventory")

_PYPROJECT_PATH = Path(__file__).resolve().parents[3] / "pyproject.toml"


def _parse_direct_dependency_names() -> set[str]:
    """Return the lowercased, specifier-stripped names of this package's
    direct (top-level) dependencies, from its own pyproject.toml. Used to
    scope the (comparatively slow, network-bound) currency check to the
    dependencies an operator can actually act on directly — bumping a
    transitive dependency independently of its parent is rarely valid.
    """
    try:
        data = tomllib.loads(_PYPROJECT_PATH.read_text())
    except Exception as exc:  # noqa: BLE001 — best-effort, never crash a scan
        log.warning("platform_health.pyproject_parse_failed", error=str(exc))
        return set()
    raw = data.get("project", {}).get("dependencies", [])
    names: set[str] = set()
    for entry in raw:
        # "fastapi==0.141.1" / "uvicorn[standard]==0.52.4" -> "fastapi" / "uvicorn"
        name = entry.split("[")[0].split("=")[0].split(">")[0].split("<")[0].strip()
        if name:
            names.add(name.lower())
    return names


async def _run_pip_audit(*, timeout_seconds: int) -> dict[str, Any] | None:
    """Run `uv run pip-audit --format json` as a subprocess. Returns the
    parsed JSON payload, or None on any failure (unreachable, timeout,
    non-zero exit with unparseable output). Never raises.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "uv",
            "run",
            "pip-audit",
            "--format",
            "json",
            cwd=str(_PYPROJECT_PATH.parent),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_seconds
            )
        except TimeoutError:
            proc.kill()
            log.warning("platform_health.pip_audit_timeout", timeout=timeout_seconds)
            return None
        if not stdout:
            log.warning(
                "platform_health.pip_audit_empty_output",
                stderr=stderr.decode(errors="replace")[:500],
            )
            return None
        return json.loads(stdout)  # type: ignore[no-any-return]
    except Exception as exc:  # noqa: BLE001 — subprocess/parse failure is data, not a crash
        log.warning("platform_health.pip_audit_failed", error=str(exc))
        return None


async def _fetch_latest_stable(name: str, client: httpx.AsyncClient) -> str | None:
    """Best-effort PyPI JSON API lookup of a package's latest stable
    release. Returns None on any failure — callers treat None as "currency
    unknown", never as "not current"."""
    try:
        resp = await client.get(f"https://pypi.org/pypi/{name}/json", timeout=3.0)
        if resp.status_code != 200:
            return None
        return resp.json().get("info", {}).get("version")  # type: ignore[no-any-return]
    except Exception:  # noqa: BLE001 — network is inherently unreliable here
        return None


@audited("platform_health.scan_run", entity_type="scan_run")
async def run_scan(
    session: AsyncSession,
    *,
    triggered_by_user_id: int | None = None,
    _pip_audit_runner: Callable[..., Coroutine[Any, Any, dict[str, Any] | None]]
    | None = None,
) -> ScanRun:
    """Run a full Platform Health scan: inventory + vulnerability (via
    pip-audit) plus currency (via PyPI) for direct dependencies. Persists
    exactly one ScanRun row plus its inventory/finding rows, and returns it.

    `_pip_audit_runner` is a test-only injection point (defaults to the
    real subprocess call) so unit tests can exercise the offline/failure
    path deterministically without depending on network or process spawn.
    """
    settings = get_settings()
    runner = _pip_audit_runner or (
        lambda: _run_pip_audit(timeout_seconds=settings.platform_health_scan_timeout_seconds)
    )
    payload = await runner()

    if payload is None:
        run = ScanRun(
            kind="full",
            status="failed",
            finished_at=datetime.now(UTC),
            detail="pip-audit did not complete (unreachable, timed out, or crashed)",
            triggered_by_user_id=triggered_by_user_id,
        )
        session.add(run)
        await session.flush()
        return run

    dependencies = payload.get("dependencies", [])
    direct_names = _parse_direct_dependency_names()

    run = ScanRun(
        kind="full",
        status="ok",
        finished_at=datetime.now(UTC),
        tool_version="pip-audit",
        component_count=len(dependencies),
        triggered_by_user_id=triggered_by_user_id,
    )
    session.add(run)
    await session.flush()  # populate run.id

    vuln_count = 0
    stale_count = 0
    currency_degraded = False

    async with httpx.AsyncClient() as client:
        for dep in dependencies:
            name = dep.get("name", "")
            version = dep.get("version", "")
            is_direct = name.lower() in direct_names

            latest: str | None = None
            is_current: bool | None = None
            if is_direct:
                latest = await _fetch_latest_stable(name, client)
                if latest is None:
                    currency_degraded = True
                else:
                    is_current = latest == version
                    if not is_current:
                        stale_count += 1

            session.add(
                ComponentInventoryItem(
                    scan_run_id=run.id,
                    name=name,
                    installed_version=version,
                    is_direct=is_direct,
                    latest_stable_version=latest,
                    is_current=is_current,
                )
            )

            for vuln in dep.get("vulns", []):
                vuln_count += 1
                fix_versions = vuln.get("fix_versions") or []
                session.add(
                    VulnerabilityFinding(
                        scan_run_id=run.id,
                        component_name=name,
                        installed_version=version,
                        advisory_id=vuln.get("id", "unknown"),
                        description=vuln.get("description"),
                        fixed_version=fix_versions[0] if fix_versions else None,
                        install_status="vulnerable",
                    )
                )

    run.vulnerability_count = vuln_count
    run.stale_count = stale_count
    if currency_degraded:
        run.status = "partial"
        run.detail = "vulnerability scan complete; currency check partially unreachable"

    await session.flush()
    return run


async def get_latest_scan(session: AsyncSession) -> ScanRun | None:
    """Most recent scan run, regardless of status."""
    stmt = select(ScanRun).order_by(ScanRun.started_at.desc()).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_latest_successful_scan(session: AsyncSession) -> ScanRun | None:
    """FR-PLATHEALTH-11: most recent scan that actually completed (status
    ok or partial — NOT failed). A caller rendering "current status" MUST
    use this, not get_latest_scan(), so an offline/failed scan degrades to
    a "stale, last successful on <date>" display rather than an empty page
    that could be misread as "clean"."""
    stmt = (
        select(ScanRun)
        .where(ScanRun.status.in_(("ok", "partial")))
        .order_by(ScanRun.started_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_scan_history(session: AsyncSession, *, limit: int = 20) -> list[ScanRun]:
    stmt = select(ScanRun).order_by(ScanRun.started_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def list_findings(session: AsyncSession, scan_run_id: int) -> list[VulnerabilityFinding]:
    stmt = select(VulnerabilityFinding).where(VulnerabilityFinding.scan_run_id == scan_run_id)
    return list((await session.execute(stmt)).scalars().all())


async def list_inventory(session: AsyncSession, scan_run_id: int) -> list[ComponentInventoryItem]:
    stmt = (
        select(ComponentInventoryItem)
        .where(ComponentInventoryItem.scan_run_id == scan_run_id)
        .order_by(ComponentInventoryItem.name)
    )
    return list((await session.execute(stmt)).scalars().all())


# ─── Remediation (FR-PLATHEALTH-7/8/9) ─────────────────────────────────


class RemediationVerificationRunner:
    """Protocol-like callable: runs this package's own build+test suite
    and returns True iff it passes. The real implementation shells out to
    `uv run pytest -q`; tests inject a fake for speed/determinism.
    """

    async def __call__(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "uv",
                "run",
                "pytest",
                "-q",
                cwd=str(_PYPROJECT_PATH.parent),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, _ = await asyncio.wait_for(proc.communicate(), timeout=600)
            return proc.returncode == 0
        except Exception as exc:  # noqa: BLE001
            log.warning("platform_health.verification_failed", error=str(exc))
            return False


@audited("platform_health.remediation_proposed", entity_type="remediation_proposal")
async def propose_remediation(
    session: AsyncSession,
    *,
    component_name: str,
    from_version: str,
    to_version: str,
    bump_kind: str,
    reason: str | None = None,
    verifier: Callable[[], Coroutine[Any, Any, bool]] | None = None,
) -> RemediationProposal:
    """Create a remediation proposal and run its verification gate
    (FR-PLATHEALTH-7). Auto-apply (FR-PLATHEALTH-8) only ever happens here
    when ALL of: the operator flag is on, the bump is patch/minor, AND
    verification passed. A major bump or a failed verification is always
    left in a state requiring explicit admin decision.
    """
    settings = get_settings()
    run_verifier = verifier or RemediationVerificationRunner()

    proposal = RemediationProposal(
        component_name=component_name,
        from_version=from_version,
        to_version=to_version,
        bump_kind=bump_kind,
        reason=reason,
    )
    session.add(proposal)
    await session.flush()

    verified = await run_verifier()
    proposal.verification_status = "verified" if verified else "failed"

    if (
        settings.platform_health_auto_apply_enabled
        and bump_kind in ("patch", "minor")
        and verified
    ):
        proposal.decision = "auto_applied"
        proposal.decided_at = datetime.now(UTC)
    else:
        proposal.decision = "held"

    await session.flush()
    return proposal


@audited("platform_health.remediation_decided", entity_type="remediation_proposal")
async def decide_remediation(
    session: AsyncSession,
    *,
    proposal: RemediationProposal,
    decision: str,
    user_id: int | None,
) -> RemediationProposal:
    """Admin approve/reject on a held remediation proposal."""
    if decision not in ("approved", "rejected"):
        raise ValueError(f"invalid decision: {decision!r}")
    proposal.decision = decision
    proposal.decided_by_user_id = user_id
    proposal.decided_at = datetime.now(UTC)
    await session.flush()
    return proposal


async def list_remediations(session: AsyncSession, *, limit: int = 50) -> list[RemediationProposal]:
    stmt = select(RemediationProposal).order_by(RemediationProposal.created_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())
