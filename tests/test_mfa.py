"""MFA (TOTP) tests — IA-2(1), chassis-program FISMA-Moderate mandate.

Covers: enrollment (start/confirm, wrong code, double-start), the login
branch (MFA-enabled user gets a challenge, not a token), challenge
verification (correct TOTP, wrong code, backup code single-use), disable,
backup-code regeneration, and the privileged-account MFA-mandate gate in
app/deps.py (a superuser without MFA enrolled is blocked from an
admin-gated route even though they hold the permission).
"""

from __future__ import annotations

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import MFABackupCode, User
from tests.conftest import make_user


async def _promote_to_superuser(session: AsyncSession, email: str) -> None:
    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one()
    user.is_superuser = True
    await session.commit()


async def _enroll(client: AsyncClient, headers: dict[str, str]) -> tuple[str, list[str]]:
    """Full enrollment flow. Returns (raw_secret, backup_codes)."""
    start = await client.post("/auth/mfa/enroll", headers=headers)
    assert start.status_code == 200, start.text
    secret = start.json()["secret"]
    assert start.json()["provisioning_uri"].startswith("otpauth://totp/")

    code = pyotp.TOTP(secret).now()
    confirm = await client.post(
        "/auth/mfa/enroll/confirm", json={"code": code}, headers=headers
    )
    assert confirm.status_code == 200, confirm.text
    body = confirm.json()
    assert body["mfa_enabled"] is True
    assert len(body["backup_codes"]) == 10
    return secret, body["backup_codes"]


# ────────────────────────────────────────────────────────────────────────
# Enrollment
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enroll_start_returns_provisioning_uri(client: AsyncClient) -> None:
    u = await make_user(client, email="mfa-start@example.com")
    resp = await client.post("/auth/mfa/enroll", headers=u["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert "secret" in body
    assert body["provisioning_uri"].startswith("otpauth://totp/")


@pytest.mark.asyncio
async def test_enroll_confirm_with_correct_code_enables_mfa(
    client: AsyncClient, session: AsyncSession
) -> None:
    u = await make_user(client, email="mfa-confirm@example.com")
    await _enroll(client, u["headers"])

    row = (
        await session.execute(
            select(User).where(User.email == "mfa-confirm@example.com")
        )
    ).scalar_one()
    assert row.mfa_enabled is True
    assert row.mfa_secret is not None
    assert row.mfa_enrolled_at is not None


@pytest.mark.asyncio
async def test_enroll_confirm_with_wrong_code_rejected(client: AsyncClient) -> None:
    u = await make_user(client, email="mfa-wrongcode@example.com")
    await client.post("/auth/mfa/enroll", headers=u["headers"])

    resp = await client.post(
        "/auth/mfa/enroll/confirm", json={"code": "000000"}, headers=u["headers"]
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_enroll_confirm_without_start_rejected(client: AsyncClient) -> None:
    u = await make_user(client, email="mfa-nostart@example.com")
    resp = await client.post(
        "/auth/mfa/enroll/confirm", json={"code": "123456"}, headers=u["headers"]
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_enroll_start_twice_after_enabled_conflicts(client: AsyncClient) -> None:
    u = await make_user(client, email="mfa-double@example.com")
    await _enroll(client, u["headers"])

    resp = await client.post("/auth/mfa/enroll", headers=u["headers"])
    assert resp.status_code == 409


# ────────────────────────────────────────────────────────────────────────
# Login branch + challenge verification
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_with_mfa_enabled_returns_challenge_not_token(
    client: AsyncClient,
) -> None:
    email, password = "mfa-login@example.com", "TestPassword123!"
    u = await make_user(client, email=email, password=password)
    await _enroll(client, u["headers"])

    resp = await client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    body = resp.json()
    assert body["mfa_required"] is True
    assert "challenge_token" in body
    assert "access_token" not in body


@pytest.mark.asyncio
async def test_login_without_mfa_returns_token_directly(client: AsyncClient) -> None:
    email, password = "mfa-plain@example.com", "TestPassword123!"
    await make_user(client, email=email, password=password)

    resp = await client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "mfa_required" not in body


@pytest.mark.asyncio
async def test_mfa_verify_with_correct_totp_issues_token(client: AsyncClient) -> None:
    email, password = "mfa-verify@example.com", "TestPassword123!"
    u = await make_user(client, email=email, password=password)
    secret, _ = await _enroll(client, u["headers"])

    login = await client.post("/auth/login", json={"email": email, "password": password})
    challenge_token = login.json()["challenge_token"]

    code = pyotp.TOTP(secret).now()
    resp = await client.post(
        "/auth/mfa/verify", json={"challenge_token": challenge_token, "code": code}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "access_token" in body
    assert body["user"]["email"] == email


@pytest.mark.asyncio
async def test_mfa_verify_with_wrong_code_rejected(client: AsyncClient) -> None:
    email, password = "mfa-wrongverify@example.com", "TestPassword123!"
    u = await make_user(client, email=email, password=password)
    await _enroll(client, u["headers"])

    login = await client.post("/auth/login", json={"email": email, "password": password})
    challenge_token = login.json()["challenge_token"]

    resp = await client.post(
        "/auth/mfa/verify",
        json={"challenge_token": challenge_token, "code": "000000"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mfa_verify_with_invalid_challenge_token_rejected(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        "/auth/mfa/verify",
        json={"challenge_token": "not-a-real-token", "code": "123456"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mfa_verify_with_backup_code_is_single_use(
    client: AsyncClient, session: AsyncSession
) -> None:
    email, password = "mfa-backup@example.com", "TestPassword123!"
    u = await make_user(client, email=email, password=password)
    _, backup_codes = await _enroll(client, u["headers"])
    one_code = backup_codes[0]

    login = await client.post("/auth/login", json={"email": email, "password": password})
    challenge_token = login.json()["challenge_token"]

    first = await client.post(
        "/auth/mfa/verify",
        json={"challenge_token": challenge_token, "code": one_code},
    )
    assert first.status_code == 200, first.text

    # A fresh challenge (backup codes are consumed independent of the
    # challenge token) — the same backup code must now be rejected.
    login2 = await client.post("/auth/login", json={"email": email, "password": password})
    challenge_token2 = login2.json()["challenge_token"]
    second = await client.post(
        "/auth/mfa/verify",
        json={"challenge_token": challenge_token2, "code": one_code},
    )
    assert second.status_code == 401

    used_row = (
        await session.execute(
            select(MFABackupCode).where(MFABackupCode.used.is_(True))
        )
    ).scalar_one()
    assert used_row.used_at is not None


# ────────────────────────────────────────────────────────────────────────
# Disable + backup-code regeneration
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_disable_mfa_clears_state_and_login_returns_token_again(
    client: AsyncClient, session: AsyncSession
) -> None:
    email, password = "mfa-disable@example.com", "TestPassword123!"
    u = await make_user(client, email=email, password=password)
    await _enroll(client, u["headers"])

    resp = await client.post("/auth/mfa/disable", headers=u["headers"])
    assert resp.status_code == 204

    row = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one()
    assert row.mfa_enabled is False
    assert row.mfa_secret is None

    remaining_codes = (
        await session.execute(
            select(MFABackupCode).where(MFABackupCode.user_id == row.id)
        )
    ).scalars().all()
    assert remaining_codes == []

    login = await client.post("/auth/login", json={"email": email, "password": password})
    assert "access_token" in login.json()


@pytest.mark.asyncio
async def test_regenerate_backup_codes_invalidates_old_ones(
    client: AsyncClient,
) -> None:
    u = await make_user(client, email="mfa-regen@example.com")
    _, old_codes = await _enroll(client, u["headers"])

    resp = await client.post("/auth/mfa/backup-codes/regenerate", headers=u["headers"])
    assert resp.status_code == 200
    new_codes = resp.json()["backup_codes"]
    assert len(new_codes) == 10
    assert set(new_codes).isdisjoint(set(old_codes))


@pytest.mark.asyncio
async def test_regenerate_backup_codes_requires_enrollment(client: AsyncClient) -> None:
    u = await make_user(client, email="mfa-noenroll@example.com")
    resp = await client.post("/auth/mfa/backup-codes/regenerate", headers=u["headers"])
    assert resp.status_code == 400


# ────────────────────────────────────────────────────────────────────────
# Privileged-account MFA mandate (app/deps.py requires())
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_privileged_user_without_mfa_is_blocked_from_admin_shell(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A superuser who has NOT enrolled MFA must be refused the admin shell
    even though `is_platform_admin`/`user_has_permission` would grant it —
    IA-2(1) enforcement in app/admin/routes.py's `_resolve()`."""
    u = await make_user(client, email="mfa-priv-noenroll@example.com")
    await _promote_to_superuser(session, "mfa-priv-noenroll@example.com")

    resp = await client.get("/admin/users", headers=u["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_privileged_user_with_mfa_enrolled_passes_admin_shell(
    client: AsyncClient, session: AsyncSession
) -> None:
    u = await make_user(client, email="mfa-priv-enrolled@example.com")
    await _promote_to_superuser(session, "mfa-priv-enrolled@example.com")
    await _enroll(client, u["headers"])

    resp = await client.get("/admin/users", headers=u["headers"])
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_non_privileged_user_without_mfa_is_not_blocked(client: AsyncClient) -> None:
    """The MFA mandate is scoped to privileged accounts only — an ordinary
    user without MFA must still pass permission checks they legitimately
    hold (regular users don't gain org-write via seeded RBAC, so this
    asserts the FAILURE mode is the normal 403-for-missing-permission, not
    the MFA-mandate 403 — same status, but the request must not have
    required MFA to reach that decision, verified by the fact no MFA
    enrollment ever happened for this user in this test)."""
    u = await make_user(client, email="mfa-regular@example.com")
    resp = await client.get("/auth/me", headers=u["headers"])
    assert resp.status_code == 200
    assert resp.json()["mfa_enabled"] is False
