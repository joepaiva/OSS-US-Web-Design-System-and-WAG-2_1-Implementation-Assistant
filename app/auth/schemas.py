"""Pydantic v2 schemas for auth endpoints.

PATTERN (ARCHITECTURE.md §2.1):
    class UserRead(BaseModel):
        model_config = ConfigDict(from_attributes=True)
        id: int
        email: EmailStr

FORBIDDEN (v1):
    class UserRead(BaseModel):
        class Config:
            orm_mode = True
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# IA-5 (chassis v0.6): password complexity policy — 14-char minimum +
# 4 character classes (uppercase, lowercase, digit, special). Strictest
# of FISMA Moderate / FedRAMP Moderate / DISA IL-2 baselines per
# compliance/controls.json.
PASSWORD_MIN_LENGTH = 14
PASSWORD_MAX_LENGTH = 128
PASSWORD_SPECIAL_CHARS = r"""!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?`~"""
_PASSWORD_HAS_UPPER = re.compile(r"[A-Z]")
_PASSWORD_HAS_LOWER = re.compile(r"[a-z]")
_PASSWORD_HAS_DIGIT = re.compile(r"\d")
_PASSWORD_HAS_SPECIAL = re.compile(f"[{PASSWORD_SPECIAL_CHARS}]")


def validate_password_complexity(password: str) -> str:
    """IA-5 password complexity check.

    Raises ValueError with a human-readable message if the password fails
    any of the four character-class requirements. The length check is
    handled by Pydantic Field(min_length=...) so this function focuses
    on character-class coverage.

    Exposed as a module-level function (not just a Pydantic validator) so
    the HTML admin shell at app/frontend.py can call it directly to
    produce identical error messages between the JSON API and the form.
    """
    missing: list[str] = []
    if not _PASSWORD_HAS_UPPER.search(password):
        missing.append("uppercase letter")
    if not _PASSWORD_HAS_LOWER.search(password):
        missing.append("lowercase letter")
    if not _PASSWORD_HAS_DIGIT.search(password):
        missing.append("digit")
    if not _PASSWORD_HAS_SPECIAL.search(password):
        missing.append(f"special character ({PASSWORD_SPECIAL_CHARS[:8]}...)")
    if missing:
        joined = ", ".join(missing)
        raise ValueError(
            f"Password must contain at least one {joined}. "
            f"This application enforces NIST 800-53 IA-5 complexity "
            f"(14+ characters with upper, lower, digit, and special)."
        )
    return password


class UserRegister(BaseModel):
    """Registration request body.

    IA-5: password must be >= 14 chars and contain at least one each of:
    uppercase, lowercase, digit, special. See validate_password_complexity().
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    full_name: str | None = Field(default=None, max_length=255)

    @field_validator("password", mode="after")
    @classmethod
    def _password_complexity(cls, v: str) -> str:
        return validate_password_complexity(v)


class UserLogin(BaseModel):
    """Login request body."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserRead(BaseModel):
    """User representation in responses. NEVER includes password_hash."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_superuser: bool
    mfa_enabled: bool
    created_at: datetime


class TokenResponse(BaseModel):
    """Login success response. Token is ALSO set as an HTTP-only cookie."""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "bearer"
    user: UserRead


class MFAChallengeResponse(BaseModel):
    """Returned by POST /auth/login instead of TokenResponse when the
    authenticated user has MFA enabled — no access token is issued yet."""

    model_config = ConfigDict(extra="forbid")

    mfa_required: bool = True
    challenge_token: str


class MFAEnrollStartResponse(BaseModel):
    """Returned by POST /auth/mfa/enroll. The secret is shown once here for
    manual entry; the provisioning_uri is what a QR-code renderer encodes."""

    model_config = ConfigDict(extra="forbid")

    secret: str
    provisioning_uri: str


class MFAEnrollConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(min_length=6, max_length=10)


class MFAEnrollConfirmResponse(BaseModel):
    """Backup codes are returned exactly once, here, in plaintext. The
    chassis never displays or transmits them again after this response."""

    model_config = ConfigDict(extra="forbid")

    mfa_enabled: bool = True
    backup_codes: list[str]


class MFAVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    challenge_token: str
    code: str = Field(min_length=6, max_length=10)


class MFABackupCodesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backup_codes: list[str]
