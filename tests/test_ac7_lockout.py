"""AC-7 Account Lockout tests (chassis v0.6).

NIST 800-53 AC-7 strictest-of-three (FISMA M / FedRAMP M / IL-2): 3
consecutive failed login attempts within a 15-minute window → 30-minute
account lockout.

Tests:
  1. 1-2 failures → InvalidCredentials, no lockout yet
  2. 3rd failure → AccountLocked raised, locked_until set in DB
  3. Within lockout window → AccountLocked even with correct password
  4. After lockout expires → InvalidCredentials path resumes (testing
     by manually expiring locked_until)
  5. Successful login resets failed_login_attempts + locked_until
  6. Failures separated by > 15 minutes do NOT compound (counter resets)
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.auth.models import User
from app.auth.service import (
    LOCKOUT_DURATION_MINUTES,
    LOCKOUT_THRESHOLD_ATTEMPTS,
    LOCKOUT_WINDOW_MINUTES,
    AccountLocked,
    InvalidCredentials,
    authenticate,
)
from app.db import get_sessionmaker
from tests.conftest import make_user


@pytest.mark.asyncio
async def test_two_failures_do_not_lock(client: AsyncClient) -> None:
    """2 consecutive failed attempts → still InvalidCredentials, not locked."""
    await make_user(client, email="lock1@example.com", password="CorrectPassword1!")
    sm = get_sessionmaker()
    async with sm() as session:
        for _ in range(LOCKOUT_THRESHOLD_ATTEMPTS - 1):
            with pytest.raises(InvalidCredentials):
                await authenticate(session, "lock1@example.com", "WrongPassword1!")
        await session.commit()

        user = (
            await session.execute(select(User).where(User.email == "lock1@example.com"))
        ).scalar_one()
        assert user.failed_login_attempts == LOCKOUT_THRESHOLD_ATTEMPTS - 1
        assert user.locked_until is None


@pytest.mark.asyncio
async def test_third_failure_triggers_lockout(client: AsyncClient) -> None:
    """3rd failed attempt → AccountLocked raised, locked_until populated."""
    await make_user(client, email="lock2@example.com", password="CorrectPassword1!")
    sm = get_sessionmaker()
    async with sm() as session:
        for _ in range(LOCKOUT_THRESHOLD_ATTEMPTS - 1):
            with pytest.raises(InvalidCredentials):
                await authenticate(session, "lock2@example.com", "WrongPassword1!")
        # The threshold-hitting attempt raises AccountLocked.
        with pytest.raises(AccountLocked) as exc_info:
            await authenticate(session, "lock2@example.com", "WrongPassword1!")
        # retry_after_seconds is the configured duration in seconds.
        assert exc_info.value.retry_after_seconds == LOCKOUT_DURATION_MINUTES * 60
        await session.commit()

        user = (
            await session.execute(select(User).where(User.email == "lock2@example.com"))
        ).scalar_one()
        assert user.locked_until is not None
        assert user.locked_until > datetime.now(UTC)


@pytest.mark.asyncio
async def test_locked_account_rejects_correct_password(
    client: AsyncClient,
) -> None:
    """While locked, even the correct password raises AccountLocked.

    This is the anti-brute-force property: an attacker who eventually
    guesses the right password is still blocked during the lockout window.
    """
    await make_user(client, email="lock3@example.com", password="CorrectPassword1!")
    sm = get_sessionmaker()
    async with sm() as session:
        # Trigger lockout.
        for _ in range(LOCKOUT_THRESHOLD_ATTEMPTS):
            with contextlib.suppress(InvalidCredentials, AccountLocked):
                await authenticate(session, "lock3@example.com", "WrongPassword1!")
        await session.commit()

        # Correct password during lockout → still AccountLocked.
        with pytest.raises(AccountLocked):
            await authenticate(session, "lock3@example.com", "CorrectPassword1!")


@pytest.mark.asyncio
async def test_expired_lockout_resumes_normal_path(
    client: AsyncClient,
) -> None:
    """When locked_until is in the past, authenticate proceeds normally."""
    await make_user(client, email="lock4@example.com", password="CorrectPassword1!")
    sm = get_sessionmaker()
    async with sm() as session:
        # Trigger lockout.
        for _ in range(LOCKOUT_THRESHOLD_ATTEMPTS):
            with contextlib.suppress(InvalidCredentials, AccountLocked):
                await authenticate(session, "lock4@example.com", "WrongPassword1!")
        # Manually expire the lockout (simulate time passage).
        user = (
            await session.execute(select(User).where(User.email == "lock4@example.com"))
        ).scalar_one()
        user.locked_until = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

        # Correct password now succeeds AND resets state.
        u = await authenticate(session, "lock4@example.com", "CorrectPassword1!")
        assert u.email == "lock4@example.com"
        # State should be reset.
        await session.refresh(u)
        assert u.failed_login_attempts == 0
        assert u.locked_until is None


@pytest.mark.asyncio
async def test_successful_login_resets_counter(client: AsyncClient) -> None:
    """A single failure followed by success resets the counter to 0."""
    await make_user(client, email="lock5@example.com", password="CorrectPassword1!")
    sm = get_sessionmaker()
    async with sm() as session:
        with pytest.raises(InvalidCredentials):
            await authenticate(session, "lock5@example.com", "WrongPassword1!")
        await session.commit()
        user = (
            await session.execute(select(User).where(User.email == "lock5@example.com"))
        ).scalar_one()
        assert user.failed_login_attempts == 1

        # Now a successful login.
        await authenticate(session, "lock5@example.com", "CorrectPassword1!")
        await session.commit()
        await session.refresh(user)
        assert user.failed_login_attempts == 0
        assert user.last_failed_login_at is None


@pytest.mark.asyncio
async def test_failures_outside_window_reset_counter(
    client: AsyncClient,
) -> None:
    """Failures separated by more than 15 minutes don't compound — the
    next failure starts a fresh window."""
    await make_user(client, email="lock6@example.com", password="CorrectPassword1!")
    sm = get_sessionmaker()
    async with sm() as session:
        with pytest.raises(InvalidCredentials):
            await authenticate(session, "lock6@example.com", "WrongPassword1!")
        await session.commit()
        user = (
            await session.execute(select(User).where(User.email == "lock6@example.com"))
        ).scalar_one()
        # Simulate time passage: push last_failed_login_at outside the window.
        user.last_failed_login_at = datetime.now(UTC) - timedelta(
            minutes=LOCKOUT_WINDOW_MINUTES + 5
        )
        user.failed_login_attempts = 2  # "carried over" from a long-ago window
        await session.commit()

        # Next failure should RESET to 1, not increment to 3.
        with pytest.raises(InvalidCredentials):
            await authenticate(session, "lock6@example.com", "WrongPassword1!")
        await session.commit()
        await session.refresh(user)
        assert user.failed_login_attempts == 1
        assert user.locked_until is None
