"""User ORM model — SQLAlchemy 2.0 typed async.

CANONICAL PATTERN (ARCHITECTURE.md §2.2):
    class User(Base):
        id: Mapped[int] = mapped_column(primary_key=True)
        email: Mapped[str] = mapped_column(String(255), unique=True)
        # ...

FORBIDDEN (legacy 1.4):
    class User(Base):
        id = Column(Integer, primary_key=True)
        email = Column(String(255), unique=True)
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    """A chassis user.

    Authenticates via email + bcrypt-hashed password. JWT is issued on login
    and round-tripped via an HTTP-only cookie.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # AC-7 (chassis v0.6): account lockout state. After 3 consecutive
    # InvalidCredentials within a 15-minute window, locked_until is set
    # 30 minutes in the future. While locked_until > now(), authenticate
    # raises AccountLockedError without checking the password (denial
    # path is fast — no bcrypt round-trip — to limit brute-force throughput).
    # Successful login resets failed_login_attempts to 0 and clears
    # locked_until. failed_login_attempts also resets at first failure
    # outside the 15-minute window (re-arms the lockout clock).
    failed_login_attempts: Mapped[int] = mapped_column(
        default=0, nullable=False, server_default="0"
    )
    last_failed_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # IA-2(1) (chassis-program v1.0.0, FISMA Moderate): MFA/TOTP state.
    # `mfa_secret` is AES-256-GCM ciphertext (app/auth/mfa_crypto.py), never
    # plaintext. `mfa_enabled` flips True only after enrollment is confirmed
    # with a valid TOTP code (app/auth/mfa.py:confirm_enrollment) — a secret
    # can exist mid-enrollment with mfa_enabled still False.
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mfa_enrolled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, email={self.email!r})"


class MFABackupCode(Base):
    """A single-use MFA backup/recovery code (IA-2(1)).

    Codes are generated in a batch at enrollment confirmation (and on
    regeneration), shown to the user exactly once in plaintext, and stored
    here only as a bcrypt hash — the same hashing discipline as passwords.
    A code is consumed (used=True, used_at set) the first time it verifies
    successfully; a used code never verifies again.
    """

    __tablename__ = "mfa_backup_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"MFABackupCode(id={self.id!r}, user_id={self.user_id!r}, used={self.used!r})"
