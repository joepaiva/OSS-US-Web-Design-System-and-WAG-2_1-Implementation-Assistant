"""Direct-bcrypt password/secret hashing helper (SC-13).

Replaces passlib's `CryptContext` (chassis-program CP-B.3, zero-CVE/
latest-stable remediation, 2026-09-02). passlib 1.7.4 is the latest
release on PyPI and its bcrypt-backend version probe is documented as
incompatible with bcrypt>=4.1 (see chassis/python-fastapi's own
ARCHITECTURE.md §8 note, inherited by this package before this fix) --
passlib itself has no newer release to pick up a fix, so pinning
bcrypt below 4.1 forever was the only way to keep passlib working. That
is not a viable "latest-stable" position under this package's zero-CVE
mandate (chassis-program-CONSTITUTION.md §5), so this package drops
passlib entirely and calls the `bcrypt` package directly -- the same
underlying primitive, one fewer (unmaintained) abstraction layer, and
no ceiling on the bcrypt version we can run.
"""

from __future__ import annotations

import bcrypt

# bcrypt silently truncates input past 72 bytes -- passlib's bcrypt backend
# has the identical limit (it's inherent to the algorithm, not a passlib
# choice), so this preserves prior behavior exactly.
_MAX_PASSWORD_BYTES = 72


def hash_secret(plain: str, *, rounds: int) -> str:
    """Hash `plain` (a password or backup code) with bcrypt at the given
    cost factor. Returns the encoded hash as a str (bcrypt.hashpw returns
    bytes; passlib's CryptContext.hash also returned a str, so callers are
    unaffected by this swap)."""
    encoded = plain.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    salt = bcrypt.gensalt(rounds=rounds)
    return bcrypt.hashpw(encoded, salt).decode("ascii")


def verify_secret(plain: str, hashed: str) -> bool:
    """Verify `plain` against a bcrypt hash produced by `hash_secret`.
    Returns False (never raises) on a malformed/foreign hash, matching
    passlib's CryptContext.verify behavior for an unrecognized hash."""
    try:
        encoded = plain.encode("utf-8")[:_MAX_PASSWORD_BYTES]
        return bcrypt.checkpw(encoded, hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False
