"""FISMA control check registry (FR-FISMAAUDIT-1..5).

Every check inspects ACTUAL runtime state — live settings values or
database rows — never documentation. Each returns exactly one of the four
outcomes in FismaAuditReport.OUTCOMES via the `CheckResult` tuple. A check
that cannot complete reports "check_error", never a silent pass
(FR-FISMAAUDIT-5) — the same fail-closed discipline Platform Health's scan
degradation uses.

The Moderate/Low policy constants checked here come directly from
specs/chassis-program/FISMA-CONTROL-DELTA-LOW-VS-MODERATE.md §7.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.logging import get_logger

log = get_logger("compliance.fisma_audit")

CheckResult = tuple[str, str]  # (outcome, detail)
CheckFn = Callable[[AsyncSession], Awaitable[CheckResult]]

# Moderate policy constants (chassis-program FISMA-CONTROL-DELTA §7).
_MODERATE = {
    "lockout_threshold": 3,
    "lockout_window_minutes": 15,
    "lockout_duration_minutes": 30,
    "password_min_length": 14,
    "session_ttl_minutes": 60,
    "audit_retention_days": 365,
}
_LOW = {
    "lockout_threshold": 5,
    "lockout_window_minutes": 15,
    "lockout_duration_minutes": 15,
    "password_min_length": 10,
    "session_ttl_minutes": 120,
    "audit_retention_days": 90,
}


def _expected(key: str) -> int:
    level = get_settings().fisma_level
    table = _MODERATE if level == "moderate" else _LOW
    return table[key]


@dataclass(frozen=True)
class Check:
    control_id: str
    title: str
    fn: CheckFn


async def _check_cookie_secure(_session: AsyncSession) -> CheckResult:
    """AC-8/SC-8: in production, session cookies MUST be marked Secure.
    Outside production this control isn't meaningfully verifiable (a local
    dev box has no TLS), so it's reported operator_responsibility there."""
    settings = get_settings()
    if settings.env != "prod":
        return (
            "operator_responsibility",
            f"env={settings.env!r} — verifiable only in production",
        )
    if settings.cookie_secure:
        return ("pass", "COOKIE_SECURE is true in production")
    return ("fail", "COOKIE_SECURE is false in production — cookies are not TLS-only")


async def _check_secrets_non_default(_session: AsyncSession) -> CheckResult:
    """SC-12: JWT signing secret and encryption keys must not be left at
    their in-code development defaults. The config layer's own boot-time
    validators already fail closed in prod (FR-351-style) — a prod process
    that booted at all has already proven this once at construction time.
    This check re-verifies the same invariant as a live, admin-visible
    runtime fact rather than silently trusting that boot succeeded for the
    reason we think it did. Outside prod, the dev-default secrets are
    expected and not a finding worth alarming an admin over — same
    env-scoping rationale as the AC-8/SC-8 cookie check."""
    settings = get_settings()
    if settings.env != "prod":
        return (
            "operator_responsibility",
            f"env={settings.env!r} — dev-default secrets are expected outside production",
        )

    from app.config import (
        _JWT_SECRET_DEV_DEFAULT,
        _LLM_ENC_KEY_DEV_DEFAULT,
        _MFA_ENC_KEY_DEV_DEFAULT,
    )

    # Exact-match against the chassis's own known in-code dev defaults
    # (each key's default is a distinct constant, not a shared placeholder
    # string) PLUS a substring check for common human-typed placeholder
    # markers, so a value like "our-change-me-later-secret" is also caught.
    placeholder_markers = ("change-me", "your-secret", "placeholder", "example")
    known_defaults = {
        "jwt_secret": _JWT_SECRET_DEV_DEFAULT,
        "llm_encryption_key": _LLM_ENC_KEY_DEV_DEFAULT,
        "mfa_encryption_key": _MFA_ENC_KEY_DEV_DEFAULT,
    }
    weak = [
        name
        for name, value in (
            ("jwt_secret", settings.jwt_secret),
            ("llm_encryption_key", settings.llm_encryption_key),
            ("mfa_encryption_key", settings.mfa_encryption_key),
        )
        if value == known_defaults[name] or any(m in value.lower() for m in placeholder_markers)
    ]
    if not weak:
        return ("pass", "jwt_secret, llm_encryption_key, mfa_encryption_key are non-default")
    return ("fail", f"still at development default: {', '.join(weak)}")


async def _check_mfa_enforced_for_privileged(session: AsyncSession) -> CheckResult:
    """IA-2(1): every privileged (platform-admin) account must have MFA
    enrolled. At FISMA Low this control is not mandated, so it is reported
    not_applicable there rather than checked."""
    if get_settings().fisma_level != "moderate":
        return ("not_applicable", "MFA is not mandated at the FISMA Low baseline")

    from app.auth.models import User
    from app.rbac.models import Role, user_roles

    stmt = (
        select(User)
        .join(user_roles, user_roles.c.user_id == User.id, isouter=True)
        .join(Role, Role.id == user_roles.c.role_id, isouter=True)
        .where((User.is_superuser.is_(True)) | (Role.name == "admin"))
        .distinct()
    )
    privileged = list((await session.execute(stmt)).scalars().all())
    if not privileged:
        return ("not_applicable", "no privileged accounts exist yet to verify")
    without_mfa = [u.email for u in privileged if not u.mfa_enabled]
    if not without_mfa:
        return ("pass", f"all {len(privileged)} privileged account(s) have MFA enrolled")
    return (
        "fail",
        f"{len(without_mfa)} of {len(privileged)} privileged account(s) lack MFA: "
        f"{', '.join(without_mfa)}",
    )


async def _check_lockout_policy(_session: AsyncSession) -> CheckResult:
    """AC-7: the configured lockout threshold/window/duration must match
    this package's FISMA level's policy constant, not just "some" lockout."""
    from app.auth.service import (
        LOCKOUT_DURATION_MINUTES,
        LOCKOUT_THRESHOLD_ATTEMPTS,
        LOCKOUT_WINDOW_MINUTES,
    )

    expected = (
        _expected("lockout_threshold"),
        _expected("lockout_window_minutes"),
        _expected("lockout_duration_minutes"),
    )
    actual = (LOCKOUT_THRESHOLD_ATTEMPTS, LOCKOUT_WINDOW_MINUTES, LOCKOUT_DURATION_MINUTES)
    if actual == expected:
        return (
            "pass",
            f"{actual[0]} attempts / {actual[1]}min window / {actual[2]}min lockout",
        )
    return (
        "fail",
        f"configured {actual}, expected {expected} for fisma_level="
        f"{get_settings().fisma_level!r}",
    )


async def _check_password_policy(_session: AsyncSession) -> CheckResult:
    """IA-5: password minimum length must match this package's FISMA
    level's policy constant."""
    from app.auth.schemas import PASSWORD_MIN_LENGTH

    expected = _expected("password_min_length")
    if expected == PASSWORD_MIN_LENGTH:
        return ("pass", f"PASSWORD_MIN_LENGTH={PASSWORD_MIN_LENGTH}")
    return ("fail", f"PASSWORD_MIN_LENGTH={PASSWORD_MIN_LENGTH}, expected {expected}")


async def _check_session_ttl(_session: AsyncSession) -> CheckResult:
    """AC-12: session (JWT) TTL must match this package's FISMA level's
    policy constant."""
    settings = get_settings()
    expected = _expected("session_ttl_minutes")
    if settings.jwt_access_token_ttl_minutes == expected:
        return ("pass", f"jwt_access_token_ttl_minutes={settings.jwt_access_token_ttl_minutes}")
    return (
        "fail",
        f"jwt_access_token_ttl_minutes={settings.jwt_access_token_ttl_minutes}, "
        f"expected {expected}",
    )


async def _check_audit_retention(_session: AsyncSession) -> CheckResult:
    """AU-11: configured audit retention must match this package's FISMA
    level's policy constant."""
    settings = get_settings()
    expected = _expected("audit_retention_days")
    if settings.audit_retention_days == expected:
        return ("pass", f"audit_retention_days={settings.audit_retention_days}")
    return (
        "fail",
        f"audit_retention_days={settings.audit_retention_days}, expected {expected}",
    )


async def _check_zero_cve(session: AsyncSession) -> CheckResult:
    """SI-2/SI-3 (chassis-program zero-CVE mandate): the most recent
    SUCCESSFUL Platform Health scan must report zero open vulnerabilities.
    No successful scan yet is a Fail, not a silent Pass — fail-closed,
    matching FR-FISMAAUDIT-5."""
    from app.compliance.inventory.service import get_latest_successful_scan

    scan = await get_latest_successful_scan(session)
    if scan is None:
        return ("fail", "no successful Platform Health scan has been run yet")
    if scan.vulnerability_count == 0:
        return ("pass", f"0 open vulnerabilities (scan #{scan.id}, {scan.started_at.isoformat()})")
    return (
        "fail",
        f"{scan.vulnerability_count} open vulnerabilities (scan #{scan.id}, "
        f"{scan.started_at.isoformat()})",
    )


async def _check_operator_responsibility_stub(_session: AsyncSession) -> CheckResult:
    """AU-6, AC-17, SC-7, SI-4, SI-7 and similar: organizational/
    environmental controls no chassis can verify from inside the running
    application. Listed as informational per FR-FISMAAUDIT-1, not run as
    a pass/fail check."""
    return ("operator_responsibility", "organizational/environmental control")


REGISTRY: list[Check] = [
    Check("AC-7", "Unsuccessful Logon Attempts (lockout policy)", _check_lockout_policy),
    Check("AC-8", "System Use Notification / cookie transport security", _check_cookie_secure),
    Check("AC-12", "Session Termination (JWT TTL)", _check_session_ttl),
    Check("AC-17", "Remote Access", _check_operator_responsibility_stub),
    Check("AU-6", "Audit Review/Analysis", _check_operator_responsibility_stub),
    Check("AU-11", "Audit Record Retention", _check_audit_retention),
    Check("IA-2(1)", "MFA for privileged accounts", _check_mfa_enforced_for_privileged),
    Check("IA-5", "Authenticator Management (password policy)", _check_password_policy),
    Check("SC-7", "Boundary Protection", _check_operator_responsibility_stub),
    Check("SC-12", "Key Management (secrets non-default)", _check_secrets_non_default),
    Check("SI-2/SI-3", "Flaw Remediation / zero-CVE mandate", _check_zero_cve),
    Check("SI-4/SI-7", "Monitoring / Integrity", _check_operator_responsibility_stub),
]
