"""AES-256-GCM encryption for MFA TOTP secrets at rest (IA-2(1)).

Mirrors `app/llm/crypto.py`'s wire format and fail-closed posture exactly,
with an independent wrap key (`settings.mfa_encryption_key`) — MFA secrets
and LLM provider keys are different secret classes with independent key
custody.

Wire format of an encrypted token: base64( nonce[12] || ciphertext+tag ).
GCM authenticates the ciphertext, so tampering (or a wrong key) raises on
decrypt rather than returning garbage.
"""

from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import _MFA_ENC_KEY_DEV_DEFAULT, get_settings

_NONCE_BYTES = 12  # GCM standard nonce length


class DecryptionError(Exception):
    """Raised when a stored secret can't be decrypted (tampered or wrong key)."""


class InsecureKeyError(Exception):
    """Raised when MFA encryption is attempted in prod with the dev-default
    wrap key — fail closed rather than wrap TOTP secrets with a key that is
    public in the source tree."""


def _load_key() -> bytes:
    """Return the 32-byte AES key from settings. Fail-closed in prod with
    the in-code default (mirrors app/llm/crypto.py's `_load_key`)."""
    settings = get_settings()
    if settings.is_prod and settings.mfa_encryption_key == _MFA_ENC_KEY_DEV_DEFAULT:
        raise InsecureKeyError(
            "Refusing to use the in-code default MFA_ENCRYPTION_KEY in "
            "env=prod. Supply a real 32-byte hex key via the "
            "MFA_ENCRYPTION_KEY env var: "
            '`python -c "import secrets; print(secrets.token_hex(32))"`.'
        )
    raw = bytes.fromhex(settings.mfa_encryption_key)
    if len(raw) != 32:
        raise ValueError("mfa_encryption_key must be 32 bytes (64 hex chars)")
    return raw


def encrypt(plaintext: str) -> str:
    """Encrypt a TOTP secret, returning a base64 token safe for DB storage."""
    key = _load_key()
    nonce = os.urandom(_NONCE_BYTES)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt(token: str) -> str:
    """Decrypt a token produced by `encrypt`. Raises DecryptionError on any
    failure (malformed token, tampered ciphertext, wrong key)."""
    try:
        blob = base64.b64decode(token.encode("ascii"))
        nonce, ct = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
        if len(nonce) != _NONCE_BYTES or not ct:
            raise DecryptionError("malformed ciphertext token")
        return AESGCM(_load_key()).decrypt(nonce, ct, None).decode("utf-8")
    except (InvalidTag, ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
        raise DecryptionError(str(exc)) from exc
