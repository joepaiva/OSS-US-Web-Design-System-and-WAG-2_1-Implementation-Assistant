"""Auth service layer — async functions, no FastAPI imports.

Why no FastAPI imports here: keeps the service callable from RQ workers,
CLI commands, and tests. Routes (the only HTTP-aware layer) translate
exceptions into HTTPExceptions.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TypedDict

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import password_hashing
from app.auth.models import User
from app.auth.schemas import UserRegister
from app.config import Settings, get_settings

# bcrypt cost is read from settings at module import time. Tests that need a
# lower cost (faster) override via monkeypatching `_bcrypt_rounds` directly.
_settings_at_import = get_settings()
_bcrypt_rounds = _settings_at_import.bcrypt_rounds


class AuthError(Exception):
    """Raised for any auth-layer failure. Route layer translates to 401/403."""


class EmailAlreadyRegistered(AuthError):
    pass


class InvalidCredentials(AuthError):
    pass


class AccountLocked(AuthError):
    """AC-7 (chassis v0.6): raised when the user has exceeded the failed
    login threshold and is currently within the lockout window. Routes
    translate to 401 with a Retry-After header (or 423 Locked — operator
    choice; chassis default is 401 to align with the same code as the
    'wrong password' path and prevent enumeration of locked accounts).

    Carries `retry_after_seconds` for the route layer to populate the
    Retry-After header if desired.
    """

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"account locked; retry after {retry_after_seconds} seconds"
        )


# AC-7 (chassis v0.6): account lockout policy. Strictest-of-three
# (FISMA M, FedRAMP M, IL-2) per compliance/controls.json: 3 attempts
# within 15-minute window → 30-minute lockout.
LOCKOUT_THRESHOLD_ATTEMPTS = 3
LOCKOUT_WINDOW_MINUTES = 15
LOCKOUT_DURATION_MINUTES = 30


class JWTPayload(TypedDict):
    """JWT body fields.

    `sub` is canonical JWT subject — user_id as a string.
    `exp` is the unix timestamp expiry.
    `iat` is issued-at.
    `email` is included for cheap RBAC decisions without a DB hit.
    """

    sub: str
    exp: int
    iat: int
    email: str


# ────────────────────────────────────────────────────────────────────────
# Password hashing
# ────────────────────────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    return password_hashing.hash_secret(plain, rounds=_bcrypt_rounds)


def verify_password(plain: str, hashed: str) -> bool:
    return password_hashing.verify_secret(plain, hashed)


# ────────────────────────────────────────────────────────────────────────
# JWT
# ────────────────────────────────────────────────────────────────────────


def issue_access_token(user: User, settings: Settings | None = None) -> str:
    """Issue a short-lived JWT access token for `user`."""
    s = settings or get_settings()
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=s.jwt_access_token_ttl_minutes)
    payload: JWTPayload = {
        "sub": str(user.id),
        "exp": int(expires_at.timestamp()),
        "iat": int(now.timestamp()),
        "email": user.email,
    }
    # PyJWT's encode returns str. dict(payload) satisfies its dict[str, Any]
    # stub -- a TypedDict isn't accepted positionally due to dict's mutating
    # methods being invariant, even though its shape is compatible.
    encoded: str = jwt.encode(dict(payload), s.jwt_secret, algorithm=s.jwt_algorithm)
    return encoded


def decode_token(token: str, settings: Settings | None = None) -> JWTPayload:
    """Decode + verify a JWT. Raises AuthError on any failure (bad sig, expired, malformed)."""
    s = settings or get_settings()
    try:
        decoded = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.exceptions.PyJWTError as exc:
        raise AuthError(f"invalid token: {exc}") from exc

    # PyJWT returns a plain dict; we trust it because the signature checked out.
    if "sub" not in decoded or "exp" not in decoded:
        raise AuthError("token missing required fields")
    return JWTPayload(
        sub=decoded["sub"],
        exp=int(decoded["exp"]),
        iat=int(decoded.get("iat", 0)),
        email=decoded.get("email", ""),
    )


# ────────────────────────────────────────────────────────────────────────
# Service methods — async, take AsyncSession, return ORM objects
# ────────────────────────────────────────────────────────────────────────


async def register_user(session: AsyncSession, payload: UserRegister) -> User:
    """Create a new user. Raises EmailAlreadyRegistered if email is taken."""
    existing = await get_user_by_email(session, payload.email)
    if existing is not None:
        raise EmailAlreadyRegistered(payload.email)

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        is_active=True,
        is_superuser=False,
    )
    session.add(user)
    await session.flush()  # populate user.id without forcing the outer transaction to commit
    return user


async def authenticate(
    session: AsyncSession, email: str, password: str
) -> User:
    """Look up the user by email and verify the password.

    AC-7 (chassis v0.6): tracks failed attempts on the User row.
    Raises:
        InvalidCredentials — on bad email / inactive user / wrong password
        AccountLocked — when the user is currently in the lockout window
                        (raised BEFORE the password verify so bcrypt cost
                         isn't paid during lockout — anti-brute-force)
    """
    user = await get_user_by_email(session, email)
    if user is None or not user.is_active:
        # Same error for "no such user" and "inactive user" to avoid
        # leaking which emails are registered. We can't update lockout
        # state for nonexistent users (no row); attackers iterating
        # through emails see uniform timing for nonexistent + locked
        # accounts (both reject without bcrypt).
        raise InvalidCredentials()

    now = datetime.now(UTC)

    # AC-7: lockout check. If we're still inside the lockout window,
    # reject without bcrypt-verifying — keeps the lockout cheap and
    # raises the time cost of brute-force enumeration.
    if user.locked_until is not None and user.locked_until > now:
        retry_after = int((user.locked_until - now).total_seconds())
        raise AccountLocked(retry_after_seconds=retry_after)

    if not verify_password(password, user.password_hash):
        # AC-7: failed attempt. Decide whether this attempt RESETS the
        # counter (because the prior failure was outside the 15-min
        # window — fresh start) or INCREMENTS it (within window).
        window_start = now - timedelta(minutes=LOCKOUT_WINDOW_MINUTES)
        if (
            user.last_failed_login_at is None
            or user.last_failed_login_at < window_start
        ):
            # Outside the window — fresh start.
            user.failed_login_attempts = 1
        else:
            user.failed_login_attempts += 1
        user.last_failed_login_at = now

        # Threshold reached → lock the account.
        if user.failed_login_attempts >= LOCKOUT_THRESHOLD_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            await session.flush()
            raise AccountLocked(
                retry_after_seconds=LOCKOUT_DURATION_MINUTES * 60
            )

        await session.flush()
        raise InvalidCredentials()

    # Successful login: reset lockout state.
    if user.failed_login_attempts != 0 or user.locked_until is not None:
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_failed_login_at = None
        await session.flush()
    return user


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    """Canonical lookup. Modern 2.0 form: select(...).where(...) NOT session.query()."""
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
