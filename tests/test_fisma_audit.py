"""FISMA self-audit + report tests (chassis-program FR-FISMAAUDIT)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.compliance.fisma_audit.checks import REGISTRY
from app.compliance.fisma_audit.service import get_latest_report, list_report_history, run_audit
from app.compliance.inventory.service import run_scan
from tests.conftest import make_org, make_user


async def _promote_to_superuser(session: AsyncSession, email: str) -> None:
    user = (await session.execute(select(User).where(User.email == email))).scalar_one()
    user.is_superuser = True
    user.mfa_enabled = True
    await session.commit()


async def _fake_pip_audit_runner(payload: dict | None):
    async def _inner():
        return payload

    return _inner


# ─── check registry: outcomes are one of the four allowed values ────────


def test_registry_has_expected_controls() -> None:
    control_ids = {c.control_id for c in REGISTRY}
    assert {"AC-7", "IA-2(1)", "IA-5", "AC-12", "AU-11", "SC-12", "SI-2/SI-3"} <= control_ids


@pytest.mark.asyncio
async def test_lockout_policy_check_passes_at_moderate_defaults(session: AsyncSession) -> None:
    check = next(c for c in REGISTRY if c.control_id == "AC-7")
    outcome, detail = await check.fn(session)
    assert outcome == "pass"
    assert "3" in detail


@pytest.mark.asyncio
async def test_password_policy_check_passes_at_moderate_defaults(session: AsyncSession) -> None:
    check = next(c for c in REGISTRY if c.control_id == "IA-5")
    outcome, _detail = await check.fn(session)
    assert outcome == "pass"


@pytest.mark.asyncio
async def test_session_ttl_check_passes_at_moderate_defaults(session: AsyncSession) -> None:
    check = next(c for c in REGISTRY if c.control_id == "AC-12")
    outcome, _detail = await check.fn(session)
    assert outcome == "pass"


@pytest.mark.asyncio
async def test_audit_retention_check_passes_at_moderate_defaults(session: AsyncSession) -> None:
    check = next(c for c in REGISTRY if c.control_id == "AU-11")
    outcome, _detail = await check.fn(session)
    assert outcome == "pass"


@pytest.mark.asyncio
async def test_secrets_non_default_check_operator_responsibility_outside_prod(
    session: AsyncSession,
) -> None:
    """Outside prod (dev/test, this suite's real ambient env), the chassis
    legitimately runs on its in-code dev-default secrets — that's expected,
    not a finding, so this must report operator_responsibility, not fail."""
    check = next(c for c in REGISTRY if c.control_id == "SC-12")
    outcome, detail = await check.fn(session)
    assert outcome == "operator_responsibility"
    assert "production" in detail


@pytest.mark.asyncio
async def test_secrets_non_default_check_fails_in_prod_with_default_secret(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In prod, a still-default secret must FAIL — this is the real,
    meaningful branch of the check."""
    import secrets as _secrets

    import app.compliance.fisma_audit.checks as checks_mod
    from app.config import Settings

    prod_with_default = Settings(
        env="prod",
        jwt_secret="x" * 48,  # non-placeholder JWT secret, real prod-shaped
        llm_encryption_key=_secrets.token_hex(32),
        # mfa_encryption_key left at its in-code dev default -> should fail
    )
    monkeypatch.setattr(checks_mod, "get_settings", lambda: prod_with_default)
    check = next(c for c in REGISTRY if c.control_id == "SC-12")
    outcome, detail = await check.fn(session)
    assert outcome == "fail"
    assert "mfa_encryption_key" in detail


@pytest.mark.asyncio
async def test_secrets_non_default_check_passes_in_prod_with_real_secrets(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    import secrets as _secrets

    import app.compliance.fisma_audit.checks as checks_mod
    from app.config import Settings

    prod_hardened = Settings(
        env="prod",
        jwt_secret=_secrets.token_urlsafe(64),
        llm_encryption_key=_secrets.token_hex(32),
        mfa_encryption_key=_secrets.token_hex(32),
    )
    monkeypatch.setattr(checks_mod, "get_settings", lambda: prod_hardened)
    check = next(c for c in REGISTRY if c.control_id == "SC-12")
    outcome, _detail = await check.fn(session)
    assert outcome == "pass"


@pytest.mark.asyncio
async def test_mfa_check_not_applicable_with_no_privileged_users(session: AsyncSession) -> None:
    check = next(c for c in REGISTRY if c.control_id == "IA-2(1)")
    outcome, detail = await check.fn(session)
    assert outcome == "not_applicable"
    assert "no privileged accounts" in detail


@pytest.mark.asyncio
async def test_mfa_check_passes_when_privileged_user_has_mfa(
    client: AsyncClient, session: AsyncSession
) -> None:
    await make_user(client, email="mfa-ok@example.com")
    await _promote_to_superuser(session, "mfa-ok@example.com")  # sets mfa_enabled=True
    check = next(c for c in REGISTRY if c.control_id == "IA-2(1)")
    outcome, detail = await check.fn(session)
    assert outcome == "pass"
    assert "1 privileged" in detail


@pytest.mark.asyncio
async def test_mfa_check_fails_when_privileged_user_lacks_mfa(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A real, meaningful runtime check — not documentation: a superuser
    account WITHOUT MFA enrolled must fail this control, even though the
    admin shell's own live route gate would separately block that user
    from reaching anything (this check inspects the DB fact directly,
    independent of whether the route gate happens to be exercised)."""
    await make_user(client, email="mfa-missing@example.com")
    user = (
        await session.execute(select(User).where(User.email == "mfa-missing@example.com"))
    ).scalar_one()
    user.is_superuser = True
    # deliberately NOT setting mfa_enabled
    await session.commit()

    check = next(c for c in REGISTRY if c.control_id == "IA-2(1)")
    outcome, detail = await check.fn(session)
    assert outcome == "fail"
    assert "mfa-missing@example.com" in detail


@pytest.mark.asyncio
async def test_zero_cve_check_fails_with_no_scan_yet(session: AsyncSession) -> None:
    """Fail-closed (FR-FISMAAUDIT-5): no successful Platform Health scan
    yet must be a FAIL, never a default pass."""
    check = next(c for c in REGISTRY if c.control_id == "SI-2/SI-3")
    outcome, detail = await check.fn(session)
    assert outcome == "fail"
    assert "no successful" in detail


@pytest.mark.asyncio
async def test_zero_cve_check_passes_after_clean_scan(session: AsyncSession) -> None:
    await run_scan(
        session,
        _pip_audit_runner=await _fake_pip_audit_runner(
            {"dependencies": [{"name": "fastapi", "version": "0.141.1", "vulns": []}], "fixes": []}
        ),
    )
    await session.commit()
    check = next(c for c in REGISTRY if c.control_id == "SI-2/SI-3")
    outcome, _detail = await check.fn(session)
    assert outcome == "pass"


@pytest.mark.asyncio
async def test_zero_cve_check_fails_after_vulnerable_scan(session: AsyncSession) -> None:
    await run_scan(
        session,
        _pip_audit_runner=await _fake_pip_audit_runner(
            {
                "dependencies": [
                    {
                        "name": "old-thing",
                        "version": "1.0.0",
                        "vulns": [{"id": "PYSEC-2099-0001", "fix_versions": [], "description": ""}],
                    }
                ],
                "fixes": [],
            }
        ),
    )
    await session.commit()
    check = next(c for c in REGISTRY if c.control_id == "SI-2/SI-3")
    outcome, _detail = await check.fn(session)
    assert outcome == "fail"


# ─── service: run_audit + report history ────────────────────────────────


@pytest.mark.asyncio
async def test_run_audit_persists_report_with_all_registry_findings(
    session: AsyncSession,
) -> None:
    report = await run_audit(session)
    await session.commit()
    assert len(report.findings) == len(REGISTRY)
    assert report.fisma_level == "moderate"
    assert report.pass_count + report.fail_count + report.not_applicable_count + report.operator_responsibility_count == len(REGISTRY)


@pytest.mark.asyncio
async def test_get_latest_report_and_history(session: AsyncSession) -> None:
    r1 = await run_audit(session)
    await session.commit()
    r2 = await run_audit(session)
    await session.commit()

    latest = await get_latest_report(session)
    assert latest is not None
    assert latest.id == r2.id

    history = await list_report_history(session)
    assert [r.id for r in history] == [r2.id, r1.id]


@pytest.mark.asyncio
async def test_run_audit_never_raises_when_a_check_errors(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-FISMAAUDIT-5: a check that raises must surface as check_error
    finding, not crash the whole audit run."""
    import app.compliance.fisma_audit.checks as checks_mod

    async def _boom(_session):
        raise RuntimeError("simulated check failure")

    broken_registry = [
        checks_mod.Check("TEST-BROKEN", "Simulated broken check", _boom),
        *checks_mod.REGISTRY,
    ]
    monkeypatch.setattr(checks_mod, "REGISTRY", broken_registry)
    import app.compliance.fisma_audit.service as service_mod

    monkeypatch.setattr(service_mod, "REGISTRY", broken_registry)

    report = await run_audit(session)
    await session.commit()
    broken_finding = next(f for f in report.findings if f["control_id"] == "TEST-BROKEN")
    assert broken_finding["outcome"] == "check_error"
    assert "simulated check failure" in broken_finding["detail"]


# ─── routes: RBAC + rendering ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fisma_audit_unauthenticated_redirects(client: AsyncClient) -> None:
    resp = await client.get("/admin/fisma-audit")
    assert resp.status_code == 303


@pytest.mark.asyncio
async def test_fisma_audit_regular_user_forbidden(client: AsyncClient) -> None:
    u = await make_user(client, email="reg-fa@example.com")
    resp = await client.get("/admin/fisma-audit", headers=u["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_fisma_audit_org_admin_forbidden(client: AsyncClient) -> None:
    u = await make_user(client, email="orgadmin-fa@example.com")
    await make_org(client, u["headers"], name="FaOrg", slug="faorg")
    resp = await client.get("/admin/fisma-audit", headers=u["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_fisma_audit_page_renders_no_report_yet(
    client: AsyncClient, session: AsyncSession
) -> None:
    u = await make_user(client, email="super-fa@example.com")
    await _promote_to_superuser(session, "super-fa@example.com")
    resp = await client.get("/admin/fisma-audit", headers=u["headers"])
    assert resp.status_code == 200
    assert "No audit has been run yet" in resp.text


@pytest.mark.asyncio
async def test_fisma_audit_run_then_page_renders_findings(
    client: AsyncClient, session: AsyncSession
) -> None:
    u = await make_user(client, email="super-fa2@example.com")
    await _promote_to_superuser(session, "super-fa2@example.com")
    resp = await client.post("/admin/fisma-audit/run", headers=u["headers"])
    assert resp.status_code == 303
    resp2 = await client.get("/admin/fisma-audit", headers=u["headers"])
    assert resp2.status_code == 200
    assert "AC-7" in resp2.text
    assert "not an independent audit" in resp2.text
