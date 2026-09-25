"""AES-256-GCM encryption for LLM provider API keys at rest (chassis v0.9).

Rule-7 parity with the SD-Agile platform's `GlobalAPIKeyService`: provider
keys are never stored in plaintext, never in env vars, never in config —
only as ciphertext in the `llm_provider_keys` table. The wrap key comes from
`settings.llm_encryption_key` (32 bytes, hex-encoded).

Wire format of an encrypted token: base64( nonce[12] || ciphertext+tag ).
GCM authenticates the ciphertext, so tampering (or a wrong key) raises on
decrypt rather than returning garbage.
"""

from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import _LLM_ENC_KEY_DEV_DEFAULT, get_settings

_NONCE_BYTES = 12  # GCM standard nonce length


class DecryptionError(Exception):
    """Raised when a stored key can't be decrypted (tampered or wrong key)."""


class InsecureKeyError(Exception):
    """Raised when LLM encryption is attempted in prod with the dev-default
    wrap key — fail closed rather than wrap provider keys with a key that is
    public in the source tree."""


def _load_key() -> bytes:
    """Return the 32-byte AES key from settings. Raises on an invalid or
    insecure (prod + in-code default) key — fail closed.

    Settings validation enforces 64-hex/32-byte at boot; the prod-default
    rejection lives here (use time) so apps that never use the embedded-LLM
    subsystem still boot in prod with the default.
    """
    settings = get_settings()
    if settings.is_prod and settings.llm_encryption_key == _LLM_ENC_KEY_DEV_DEFAULT:
        raise InsecureKeyError(
            "Refusing to use the in-code default LLM_ENCRYPTION_KEY in "
            "env=prod. Supply a real 32-byte hex key via the "
            "LLM_ENCRYPTION_KEY env var: "
            '`python -c "import secrets; print(secrets.token_hex(32))"`.'
        )
    raw = bytes.fromhex(settings.llm_encryption_key)
    if len(raw) != 32:
        raise ValueError("llm_encryption_key must be 32 bytes (64 hex chars)")
    return raw


def encrypt(plaintext: str) -> str:
    """Encrypt a provider key, returning a base64 token safe for DB storage."""
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


def mask(plaintext: str) -> str:
    """Return a non-reversible display form of a key (last 4 chars shown).

    Used by the admin UI so a key is recognizable without being exposed.
    """
    if len(plaintext) <= 4:
        return "••••"
    return "••••" + plaintext[-4:]
