"""Auth routes — register / login / logout / me.

JWTs are issued on register and login. The token is returned in the JSON body
AND set as an HTTP-only cookie. Browsers automatically round-trip the cookie;
non-browser clients (CLIs, mobile) use the Bearer header.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from app.auth import mfa
from app.auth.mfa import (
    InvalidChallengeToken,
    InvalidMFACode,
    MFAAlreadyEnrolled,
    MFAEnrollmentNotStarted,
    MFANotEnrolled,
)
from app.auth.schemas import (
    MFABackupCodesResponse,
    MFAChallengeResponse,
    MFAEnrollConfirmRequest,
    MFAEnrollConfirmResponse,
    MFAEnrollStartResponse,
    MFAVerifyRequest,
    TokenResponse,
    UserLogin,
    UserRead,
    UserRegister,
)
from app.auth.service import (
    AccountLocked,
    EmailAlreadyRegistered,
    InvalidCredentials,
    authenticate,
    get_user_by_id,
    issue_access_token,
    register_user,
)
from app.config import get_settings
from app.db import SessionDep
from app.deps import ACCESS_TOKEN_COOKIE, CurrentUser
from app.logging import get_logger

log = get_logger("auth")

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: UserRegister,
    session: SessionDep,
    response: Response,
) -> TokenResponse:
    """Create a new user and issue an access token.

    Returns 409 if the email is already registered.
    """
    try:
        user = await register_user(session, payload)
    except EmailAlreadyRegistered as exc:
        log.info("auth.register.duplicate_email", email=payload.email)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="email already registered",
        ) from exc

    token = issue_access_token(user)
    _set_token_cookie(response, token)
    log.info("auth.register.success", user_id=user.id, email=user.email)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserRead.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse | MFAChallengeResponse)
async def login(
    payload: UserLogin,
    session: SessionDep,
    response: Response,
) -> TokenResponse | MFAChallengeResponse:
    """Verify credentials and issue an access token — or, for an MFA-enabled
    user (IA-2(1)), an MFA challenge instead.

    Returns 401 for any password-auth failure (no such user, wrong
    password, inactive user). Identical error keeps registered-email
    enumeration hard.

    When `user.mfa_enabled` is True, this endpoint does NOT issue a usable
    access token — it returns `MFAChallengeResponse` with a short-lived
    challenge token, and the caller must complete POST /auth/mfa/verify
    before receiving a real token. This is the enforcement point for the
    FISMA-Moderate MFA mandate on privileged accounts (app/deps.py blocks
    privileged actions for any mfa_enabled=False privileged user, so in
    practice every admin account ends up enrolled and taking this path).
    """
    try:
        user = await authenticate(session, payload.email, payload.password)
    except AccountLocked as exc:
        # AC-7 (chassis v0.6): account locked due to too many failures.
        # Same 401 status as InvalidCredentials to prevent attackers from
        # distinguishing "locked account" from "wrong password", but we
        # surface Retry-After so legit users see a useful response.
        log.info(
            "auth.login.account_locked",
            email=payload.email,
            retry_after_seconds=exc.retry_after_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except InvalidCredentials as exc:
        log.info("auth.login.invalid_credentials", email=payload.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        ) from exc

    if user.mfa_enabled:
        challenge_token = mfa.issue_challenge_token(user)
        log.info("auth.login.mfa_challenge_issued", user_id=user.id)
        return MFAChallengeResponse(challenge_token=challenge_token)

    token = issue_access_token(user)
    _set_token_cookie(response, token)
    log.info("auth.login.success", user_id=user.id)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserRead.model_validate(user),
    )


# ────────────────────────────────────────────────────────────────────────
# MFA — enrollment, login verification, disable, backup codes
# ────────────────────────────────────────────────────────────────────────


@router.post("/mfa/enroll", response_model=MFAEnrollStartResponse)
async def mfa_enroll_start(
    user: CurrentUser,
    session: SessionDep,
) -> MFAEnrollStartResponse:
    """Start MFA enrollment for the current user. Returns a provisioning
    URI (render as a QR code) and the raw secret (for manual entry).
    MFA is NOT enabled yet — call /auth/mfa/enroll/confirm with a valid
    code from the authenticator app to activate it."""
    try:
        secret, uri = mfa.start_enrollment(user)
    except MFAAlreadyEnrolled as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="MFA is already enabled for this account",
        ) from exc
    await session.flush()
    log.info("auth.mfa.enroll_started", user_id=user.id)
    return MFAEnrollStartResponse(secret=secret, provisioning_uri=uri)


@router.post("/mfa/enroll/confirm", response_model=MFAEnrollConfirmResponse)
async def mfa_enroll_confirm(
    payload: MFAEnrollConfirmRequest,
    user: CurrentUser,
    session: SessionDep,
) -> MFAEnrollConfirmResponse:
    """Confirm MFA enrollment with a code from the authenticator app.
    On success, MFA is enabled and a batch of backup codes is returned —
    exactly once, in plaintext. The caller MUST display these to the user
    now; the chassis stores only bcrypt hashes and cannot show them again.
    """
    try:
        backup_codes = await mfa.confirm_enrollment(session, user, payload.code)
    except MFAEnrollmentNotStarted as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="call /auth/mfa/enroll first",
        ) from exc
    except InvalidMFACode as exc:
        log.info("auth.mfa.enroll_confirm_invalid_code", user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid code",
        ) from exc
    log.info("auth.mfa.enrolled", user_id=user.id)
    return MFAEnrollConfirmResponse(backup_codes=backup_codes)


@router.post("/mfa/verify", response_model=TokenResponse)
async def mfa_verify(
    payload: MFAVerifyRequest,
    session: SessionDep,
    response: Response,
) -> TokenResponse:
    """Complete login for an MFA-enabled user: exchange a challenge token +
    a valid TOTP (or backup) code for a real access token.

    Returns 401 for an invalid/expired challenge token or an invalid code —
    identical status for both, matching the password-login anti-enumeration
    posture (a caller shouldn't be able to distinguish "your challenge
    token expired" from "your code was wrong" via status code alone; the
    detail message differs for legitimate-user usability but the status
    doesn't leak more than that).
    """
    try:
        user_id = mfa.decode_challenge_token(payload.challenge_token)
    except InvalidChallengeToken as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired MFA challenge",
        ) from exc

    user = await get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired MFA challenge",
        )

    try:
        await mfa.verify_login_code(session, user, payload.code)
    except (MFANotEnrolled, InvalidMFACode) as exc:
        log.info("auth.mfa.verify_failed", user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid code",
        ) from exc

    token = issue_access_token(user)
    _set_token_cookie(response, token)
    log.info("auth.mfa.verify_success", user_id=user.id)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserRead.model_validate(user),
    )


@router.post("/mfa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def mfa_disable(user: CurrentUser, session: SessionDep) -> Response:
    """Self-service MFA disable for the current user."""
    await mfa.disable_mfa(session, user)
    log.info("auth.mfa.disabled", user_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/mfa/backup-codes/regenerate", response_model=MFABackupCodesResponse)
async def mfa_regenerate_backup_codes(
    user: CurrentUser, session: SessionDep
) -> MFABackupCodesResponse:
    """Invalidate all existing backup codes and issue a fresh batch,
    returned once, in plaintext."""
    try:
        codes = await mfa.regenerate_backup_codes(session, user)
    except MFANotEnrolled as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled for this account",
        ) from exc
    log.info("auth.mfa.backup_codes_regenerated", user_id=user.id)
    return MFABackupCodesResponse(backup_codes=codes)


@router.post("/logout")
async def logout() -> Response:
    """Clear the auth cookie.

    Stateless logout: there is no server-side session to invalidate. The
    JWT remains technically valid until its `exp`; revocation lists are
    a v1.x feature.

    Returns 204. FastAPI 0.115 rejects the `status_code=204` decorator combo
    with a `response: Response` parameter, so we return a fresh Response and
    delete the cookie on it directly.
    """
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(ACCESS_TOKEN_COOKIE)
    return response


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> UserRead:
    """Return the authenticated user. 401 if not logged in."""
    return UserRead.model_validate(user)


# ────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────


def _set_token_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        max_age=s.jwt_access_token_ttl_minutes * 60,
        httponly=True,
        secure=s.cookie_secure,
        samesite=s.cookie_samesite,
        domain=s.cookie_domain or None,
        path="/",
    )
