"""Platform Health tests (chassis-program FR-PLATHEALTH).

Every test that exercises `run_scan`/`propose_remediation` injects a fake
runner/verifier — never shells out to a real `pip-audit`/`pytest`
subprocess in the test suite itself (slow, and a real verifier would
recursively invoke pytest from inside a pytest run).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.compliance.inventory.service import (
    decide_remediation,
    get_latest_scan,
    get_latest_successful_scan,
    list_findings,
    list_inventory,
    list_remediations,
    list_scan_history,
    propose_remediation,
    run_scan,
)
from tests.conftest import make_org, make_user


async def _promote_to_superuser(session: AsyncSession, email: str) -> None:
    user = (await session.execute(select(User).where(User.email == email))).scalar_one()
    user.is_superuser = True
    user.mfa_enabled = True  # IA-2(1): privileged accounts must have MFA
    await session.commit()


_CLEAN_PAYLOAD = {
    "dependencies": [
        {"name": "fastapi", "version": "0.141.1", "vulns": []},
        {"name": "requests", "version": "2.34.2", "vulns": []},
    ],
    "fixes": [],
}

_VULNERABLE_PAYLOAD = {
    "dependencies": [
        {"name": "fastapi", "version": "0.141.1", "vulns": []},
        {
            "name": "old-thing",
            "version": "1.0.0",
            "vulns": [
                {
                    "id": "PYSEC-2099-0001",
                    "fix_versions": ["1.0.1"],
                    "description": "test vulnerability",
                }
            ],
        },
    ],
    "fixes": [],
}


async def _fake_runner(payload: dict | None):
    async def _inner():
        return payload

    return _inner


# ─── service: run_scan ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_scan_persists_clean_result(session: AsyncSession) -> None:
    run = await run_scan(session, _pip_audit_runner=await _fake_runner(_CLEAN_PAYLOAD))
    await session.commit()
    assert run.status == "ok"
    assert run.component_count == 2
    assert run.vulnerability_count == 0
    findings = await list_findings(session, run.id)
    assert findings == []


@pytest.mark.asyncio
async def test_run_scan_persists_vulnerability_findings(session: AsyncSession) -> None:
    run = await run_scan(session, _pip_audit_runner=await _fake_runner(_VULNERABLE_PAYLOAD))
    await session.commit()
    assert run.vulnerability_count == 1
    findings = await list_findings(session, run.id)
    assert len(findings) == 1
    assert findings[0].component_name == "old-thing"
    assert findings[0].advisory_id == "PYSEC-2099-0001"
    assert findings[0].fixed_version == "1.0.1"


@pytest.mark.asyncio
async def test_run_scan_fail_closed_when_pip_audit_unreachable(session: AsyncSession) -> None:
    """FR-PLATHEALTH-11: a runner returning None (unreachable/timeout) must
    persist a FAILED run with zero inventory/finding rows — never a
    silent "clean" result."""
    run = await run_scan(session, _pip_audit_runner=await _fake_runner(None))
    await session.commit()
    assert run.status == "failed"
    assert run.vulnerability_count == 0
    inventory = await list_inventory(session, run.id)
    assert inventory == []


@pytest.mark.asyncio
async def test_get_latest_successful_scan_skips_failed_runs(session: AsyncSession) -> None:
    """A failed run must never be returned by get_latest_successful_scan —
    callers displaying 'current status' must see the last GOOD result with
    a staleness indicator, never an empty/failed run mistaken for clean."""
    good = await run_scan(session, _pip_audit_runner=await _fake_runner(_CLEAN_PAYLOAD))
    await session.commit()
    await run_scan(session, _pip_audit_runner=await _fake_runner(None))
    await session.commit()

    latest = await get_latest_scan(session)
    latest_successful = await get_latest_successful_scan(session)
    assert latest is not None
    assert latest.status == "failed"
    assert latest_successful is not None
    assert latest_successful.id == good.id


@pytest.mark.asyncio
async def test_scan_history_ordered_newest_first(session: AsyncSession) -> None:
    r1 = await run_scan(session, _pip_audit_runner=await _fake_runner(_CLEAN_PAYLOAD))
    await session.commit()
    r2 = await run_scan(session, _pip_audit_runner=await _fake_runner(_CLEAN_PAYLOAD))
    await session.commit()
    history = await list_scan_history(session)
    assert history[0].id == r2.id
    assert history[1].id == r1.id


@pytest.mark.asyncio
async def test_direct_dependency_currency_checked_transitive_is_not(
    session: AsyncSession,
) -> None:
    """FR-PLATHEALTH-4: only direct dependencies get a currency check
    (is_current populated); transitive ones stay None (unknown), not
    incorrectly flagged stale."""
    payload = {
        "dependencies": [
            {"name": "fastapi", "version": "0.141.1", "vulns": []},  # direct
            {"name": "some-transitive-only-dep", "version": "9.9.9", "vulns": []},
        ],
        "fixes": [],
    }
    run = await run_scan(session, _pip_audit_runner=await _fake_runner(payload))
    await session.commit()
    inventory = await list_inventory(session, run.id)
    direct = next(i for i in inventory if i.name == "fastapi")
    transitive = next(i for i in inventory if i.name == "some-transitive-only-dep")
    assert direct.is_direct is True
    assert transitive.is_direct is False
    assert transitive.is_current is None


# ─── service: remediation ───────────────────────────────────────────────


async def _verifier(result: bool):
    async def _inner() -> bool:
        return result

    return _inner


@pytest.mark.asyncio
async def test_propose_remediation_auto_apply_off_by_default_holds(
    session: AsyncSession,
) -> None:
    """FR-PLATHEALTH-8: with the operator flag off (the default), even a
    verified patch bump is held for admin decision, never auto-applied."""
    proposal = await propose_remediation(
        session,
        component_name="requests",
        from_version="2.34.1",
        to_version="2.34.2",
        bump_kind="patch",
        verifier=await _verifier(True),
    )
    await session.commit()
    assert proposal.verification_status == "verified"
    assert proposal.decision == "held"


@pytest.mark.asyncio
async def test_propose_remediation_major_bump_always_held_even_if_flag_on(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-PLATHEALTH-8: a MAJOR bump always requires explicit approval,
    regardless of the auto-apply flag."""
    import app.compliance.inventory.service as svc

    monkeypatch.setattr(
        svc.get_settings(), "platform_health_auto_apply_enabled", True, raising=False
    )
    proposal = await propose_remediation(
        session,
        component_name="fastapi",
        from_version="0.140.0",
        to_version="1.0.0",
        bump_kind="major",
        verifier=await _verifier(True),
    )
    await session.commit()
    assert proposal.decision == "held"


@pytest.mark.asyncio
async def test_propose_remediation_failed_verification_always_held(
    session: AsyncSession,
) -> None:
    proposal = await propose_remediation(
        session,
        component_name="requests",
        from_version="2.34.1",
        to_version="2.34.2",
        bump_kind="patch",
        verifier=await _verifier(False),
    )
    await session.commit()
    assert proposal.verification_status == "failed"
    assert proposal.decision == "held"


@pytest.mark.asyncio
async def test_decide_remediation_approve_and_reject(session: AsyncSession) -> None:
    proposal = await propose_remediation(
        session,
        component_name="requests",
        from_version="2.34.1",
        to_version="2.34.2",
        bump_kind="patch",
        verifier=await _verifier(True),
    )
    await session.commit()

    decided = await decide_remediation(
        session, proposal=proposal, decision="approved", user_id=None
    )
    await session.commit()
    assert decided.decision == "approved"
    assert decided.decided_at is not None


@pytest.mark.asyncio
async def test_decide_remediation_rejects_invalid_decision(session: AsyncSession) -> None:
    proposal = await propose_remediation(
        session,
        component_name="requests",
        from_version="2.34.1",
        to_version="2.34.2",
        bump_kind="patch",
        verifier=await _verifier(True),
    )
    await session.commit()
    with pytest.raises(ValueError):
        await decide_remediation(
            session, proposal=proposal, decision="maybe", user_id=None
        )


@pytest.mark.asyncio
async def test_list_remediations(session: AsyncSession) -> None:
    await propose_remediation(
        session,
        component_name="a",
        from_version="1",
        to_version="2",
        bump_kind="patch",
        verifier=await _verifier(True),
    )
    await session.commit()
    rows = await list_remediations(session)
    assert len(rows) == 1


# ─── routes: RBAC + rendering ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_platform_health_unauthenticated_redirects(client: AsyncClient) -> None:
    resp = await client.get("/admin/platform-health")
    assert resp.status_code == 303


@pytest.mark.asyncio
async def test_platform_health_regular_user_forbidden(client: AsyncClient) -> None:
    u = await make_user(client, email="reg-ph@example.com")
    resp = await client.get("/admin/platform-health", headers=u["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_platform_health_org_admin_forbidden(client: AsyncClient) -> None:
    u = await make_user(client, email="orgadmin-ph@example.com")
    await make_org(client, u["headers"], name="PhOrg", slug="phorg")
    resp = await client.get("/admin/platform-health", headers=u["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_platform_health_page_renders_no_scan_yet(
    client: AsyncClient, session: AsyncSession
) -> None:
    u = await make_user(client, email="super-ph@example.com")
    await _promote_to_superuser(session, "super-ph@example.com")
    resp = await client.get("/admin/platform-health", headers=u["headers"])
    assert resp.status_code == 200
    assert "Platform Health" in resp.text
    assert "No successful scan yet" in resp.text


@pytest.mark.asyncio
async def test_platform_health_page_renders_after_scan(
    client: AsyncClient, session: AsyncSession
) -> None:
    u = await make_user(client, email="super-ph2@example.com")
    await _promote_to_superuser(session, "super-ph2@example.com")
    await run_scan(session, _pip_audit_runner=await _fake_runner(_CLEAN_PAYLOAD))
    await session.commit()
    resp = await client.get("/admin/platform-health", headers=u["headers"])
    assert resp.status_code == 200
    assert "Zero open vulnerabilities" in resp.text
