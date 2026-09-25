"""MFA (TOTP) service layer — async functions, no FastAPI imports (IA-2(1)).

Mirrors the layering discipline of app/auth/service.py: pure async
functions over an AsyncSession, no FastAPI imports, so this is callable
from RQ workers, CLI commands, and tests. Routes (app/auth/routes.py) are
the only HTTP-aware layer and translate these exceptions into
HTTPExceptions.

FISMA-Moderate mandate (chassis-program FISMA-CONTROL-DELTA-LOW-VS-MODERATE.md
§4, IA-2(1)): MFA is mandatory for privileged (admin) accounts on this
package. Enforcement of the *mandate* (blocking privileged actions until a
user enrolls) lives in app/deps.py's `requires()`; this module only
implements the enrollment/verification mechanism itself, which is available
to any user regardless of privilege level.

Enrollment flow (two-step, so a scanned-but-not-yet-confirmed secret never
silently activates MFA):
  1. `start_enrollment` — generates a new TOTP secret, stores it encrypted
     on the user row with `mfa_enabled` still False, returns the
     provisioning URI (for a QR code) + raw secret (for manual entry).
  2. `confirm_enrollment` — verifies a code against the pending secret; on
     success sets `mfa_enabled=True`, `mfa_enrolled_at=now`, and generates
     a fresh batch of backup codes (returned once, in plaintext).

Login flow (see app/auth/routes.py): password auth (app/auth/service.py)
happens first, unchanged. If the authenticated user has `mfa_enabled`, the
route does NOT issue a full access token — it issues a short-lived MFA
challenge token instead, requiring a second call to `verify_login_code`
before a real access token is issued.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import pyotp
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import mfa_crypto, password_hashing
from app.auth.models import MFABackupCode, User
from app.config import Settings, get_settings

# Backup codes use the SAME bcrypt discipline as passwords — a leaked DB
# should not let an attacker read usable backup codes.
_settings_at_import = get_settings()
_backup_bcrypt_rounds = _settings_at_import.bcrypt_rounds


class MFAError(Exception):
    """Raised for any MFA-layer failure. Route layer translates to 4xx."""


class MFANotEnrolled(MFAError):
    pass


class MFAAlreadyEnrolled(MFAError):
    pass


class MFAEnrollmentNotStarted(MFAError):
    """Raised by confirm_enrollment when start_enrollment was never called
    (no pending secret on the user row)."""


class InvalidMFACode(MFAError):
    pass


class InvalidChallengeToken(MFAError):
    pass


# ────────────────────────────────────────────────────────────────────────
# Enrollment
# ────────────────────────────────────────────────────────────────────────


def start_enrollment(user: User) -> tuple[str, str]:
    """Generate a new TOTP secret for `user`, store it encrypted (pending —
    `mfa_enabled` unchanged), and return (raw_secret, provisioning_uri).

    Calling this again before `confirm_enrollment` overwrites the pending
    secret — a user who abandons enrollment and restarts gets a fresh
    secret, not a stale one lingering from an earlier attempt.

    Raises MFAAlreadyEnrolled if the user already has MFA enabled — they
    must disable it first (or an admin resets it) before re-enrolling.
    """
    if user.mfa_enabled:
        raise MFAAlreadyEnrolled(user.email)

    settings = get_settings()
    raw_secret = pyotp.random_base32()
    user.mfa_secret = mfa_crypto.encrypt(raw_secret)

    totp = pyotp.TOTP(raw_secret)
    provisioning_uri = totp.provisioning_uri(
        name=user.email, issuer_name=settings.mfa_issuer_name
    )
    return raw_secret, provisioning_uri


async def confirm_enrollment(
    session: AsyncSession, user: User, code: str
) -> list[str]:
    """Verify `code` against the pending secret and, on success, enable MFA
    and generate a fresh batch of backup codes (returned once, plaintext).

    Raises:
        MFAEnrollmentNotStarted — no pending secret (start_enrollment was
            never called, or the user was already confirmed and this is a
            stale/replayed request).
        InvalidMFACode — code doesn't verify against the pending secret.
    """
    if user.mfa_secret is None:
        raise MFAEnrollmentNotStarted(user.email)

    raw_secret = mfa_crypto.decrypt(user.mfa_secret)
    totp = pyotp.TOTP(raw_secret)
    if not totp.verify(code, valid_window=1):
        raise InvalidMFACode()

    user.mfa_enabled = True
    user.mfa_enrolled_at = datetime.now(UTC)
    await session.flush()

    return await _regenerate_backup_codes(session, user)


async def disable_mfa(session: AsyncSession, user: User) -> None:
    """Turn MFA off for `user` and delete their secret + backup codes.

    Available to the user themselves (self-service disable) as well as
    admin reset (app/auth/routes.py exposes both; the admin path is
    additionally audited via @audited).
    """
    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_enrolled_at = None
    await session.execute(
        delete(MFABackupCode).where(MFABackupCode.user_id == user.id)
    )
    await session.flush()


async def regenerate_backup_codes(session: AsyncSession, user: User) -> list[str]:
    """Invalidate all existing backup codes and issue a fresh batch.

    Raises MFANotEnrolled if the user hasn't completed enrollment — backup
    codes only make sense as a fallback to an active TOTP enrollment.
    """
    if not user.mfa_enabled:
        raise MFANotEnrolled(user.email)
    return await _regenerate_backup_codes(session, user)


async def _regenerate_backup_codes(session: AsyncSession, user: User) -> list[str]:
    settings = get_settings()
    await session.execute(
        delete(MFABackupCode).where(MFABackupCode.user_id == user.id)
    )
    plaintext_codes: list[str] = []
    rows: list[MFABackupCode] = []
    for _ in range(settings.mfa_backup_codes_count):
        code = f"{secrets.randbelow(10**10):010d}"
        plaintext_codes.append(code)
        rows.append(
            MFABackupCode(
                user_id=user.id,
                code_hash=password_hashing.hash_secret(code, rounds=_backup_bcrypt_rounds),
            )
        )
    session.add_all(rows)
    await session.flush()
    return plaintext_codes


# ────────────────────────────────────────────────────────────────────────
# Login-time verification
# ────────────────────────────────────────────────────────────────────────


class MFAChallengePayload:
    """Fields carried in an MFA challenge JWT — distinct claim shape from
    the real access token so a challenge token can never be mistaken for
    (or replayed as) an authenticated session."""

    def __init__(self, sub: str, exp: int, iat: int, mfa_pending: bool) -> None:
        self.sub = sub
        self.exp = exp
        self.iat = iat
        self.mfa_pending = mfa_pending


def issue_challenge_token(user: User, settings: Settings | None = None) -> str:
    """Issue a short-lived challenge token after password auth succeeds for
    an MFA-enabled user. This token is NOT a valid access token — it only
    authorizes a call to `verify_login_code`."""
    import jwt  # local import: keep module import light for non-HTTP callers

    s = settings or get_settings()
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=s.mfa_challenge_token_ttl_minutes)
    payload = {
        "sub": str(user.id),
        "exp": int(expires_at.timestamp()),
        "iat": int(now.timestamp()),
        "mfa_pending": True,
    }
    encoded: str = jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)
    return encoded


def decode_challenge_token(token: str, settings: Settings | None = None) -> int:
    """Decode + verify an MFA challenge token, returning the pending user's
    id. Raises InvalidChallengeToken on any failure (bad sig, expired,
    malformed, or missing the mfa_pending marker — rejects a real access
    token being replayed here)."""
    import jwt

    s = settings or get_settings()
    try:
        decoded = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.exceptions.PyJWTError as exc:
        raise InvalidChallengeToken(str(exc)) from exc

    if not decoded.get("mfa_pending") or "sub" not in decoded:
        raise InvalidChallengeToken("not a valid MFA challenge token")
    return int(decoded["sub"])


async def verify_login_code(session: AsyncSession, user: User, code: str) -> bool:
    """Verify `code` as either a live TOTP code or an unused backup code.

    Returns True on success (and, for a backup code, marks it used).
    Raises MFANotEnrolled if the user has no active MFA enrollment, or
    InvalidMFACode if the code matches neither a live TOTP value nor an
    unused backup code.
    """
    if not user.mfa_enabled or user.mfa_secret is None:
        raise MFANotEnrolled(user.email)

    raw_secret = mfa_crypto.decrypt(user.mfa_secret)
    totp = pyotp.TOTP(raw_secret)
    if totp.verify(code, valid_window=1):
        return True

    # Not a valid TOTP code — try it as a backup code.
    result = await session.execute(
        select(MFABackupCode).where(
            MFABackupCode.user_id == user.id, MFABackupCode.used.is_(False)
        )
    )
    for backup in result.scalars().all():
        if password_hashing.verify_secret(code, backup.code_hash):
            backup.used = True
            backup.used_at = datetime.now(UTC)
            await session.flush()
            return True

    raise InvalidMFACode()
