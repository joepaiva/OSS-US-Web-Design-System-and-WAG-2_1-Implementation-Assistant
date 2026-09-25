# ─────────────────────────────────────────────────────────────────
# Control Annotations — NIST 800-53 (chassis v0.6)
# ─────────────────────────────────────────────────────────────────
# SC-28: information-source credentials are encrypted at rest (AES-256-GCM)
# SC-13: uses a FIPS-approved AEAD cipher (AES-GCM) exclusively
# ─────────────────────────────────────────────────────────────────
"""Credential encryption for the Accessibility Assistant slot (SR-001).

`CredentialEncryptionService` is the SOLE encryption/decryption interface
for information-source credentials (GitHub access tokens, MCP server
usernames/passwords/api keys). No route or service function in this slot
calls a `cryptography` primitive directly (T-004's implementation note).

Rather than re-implementing AES-256-GCM a second time in this slot (the
CONSTITUTION's Extension Model forbids "a second implementation of a
foundation concern"), this module delegates to the chassis's own
`app.llm.crypto` — the same AES-256-GCM AEAD helper `app/mcp/service.py`
already reuses for MCP server connection credentials. That module's
`encrypt`/`decrypt` already implement the wire format (base64(nonce ||
ciphertext+tag)), the prod fail-closed check on the dev-default wrap key,
and tamper detection via the GCM tag — reusing it is strictly safer than a
second copy of the same crypto code.
"""

from __future__ import annotations

import json
from typing import Any

from app.llm.crypto import DecryptionError
from app.llm.crypto import decrypt as _chassis_decrypt
from app.llm.crypto import encrypt as _chassis_encrypt

__all__ = ["CredentialEncryptionService", "FIPSComplianceError", "DecryptionError"]


class FIPSComplianceError(Exception):
    """Raised if a non-FIPS-compliant encryption path is ever requested.

    AES-256-GCM (the only algorithm this service uses, via app.llm.crypto)
    is FIPS 140-2/140-3 approved, so this is never raised today. It exists
    so a future addition to this service cannot silently introduce a
    non-compliant algorithm without an explicit, named failure mode.
    """


class CredentialEncryptionService:
    """Encrypts/decrypts information-source credential material.

    Credentials are always encrypted as a JSON object (e.g.
    `{"access_token": "..."}` or `{"username": "...", "password": "...",
    "api_key": "..."}`) so a single ciphertext column
    (`InformationSource.credentials_encrypted`) can hold any of the
    per-source-type credential shapes.
    """

    @staticmethod
    def encrypt(credentials: dict[str, Any]) -> str:
        """Serialise `credentials` to JSON and AES-256-GCM encrypt it.

        Returns a base64 ciphertext token safe for DB storage. Never logs
        or returns the plaintext.
        """
        plaintext = json.dumps(credentials, sort_keys=True)
        return _chassis_encrypt(plaintext)

    @staticmethod
    def decrypt(ciphertext: str) -> dict[str, Any]:
        """Decrypt a token produced by `encrypt` back into the credential dict.

        Raises DecryptionError on tampered ciphertext or a wrong/rotated key.
        """
        plaintext = _chassis_decrypt(ciphertext)
        result: dict[str, Any] = json.loads(plaintext)
        return result
