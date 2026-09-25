"""LLM key encryption + config validation tests (chassis v0.9)."""

from __future__ import annotations

import pytest

from app.config import _LLM_ENC_KEY_DEV_DEFAULT, Settings
from app.llm import crypto as crypto_mod
from app.llm.crypto import (
    DecryptionError,
    InsecureKeyError,
    decrypt,
    encrypt,
    mask,
)


def test_encrypt_decrypt_roundtrip() -> None:
    secret = "sk-ant-abc123-very-secret-key"
    token = encrypt(secret)
    assert token != secret
    assert decrypt(token) == secret


def test_ciphertext_is_nondeterministic() -> None:
    # Fresh nonce each call → same plaintext yields different ciphertext.
    assert encrypt("same") != encrypt("same")


def test_tampered_token_raises() -> None:
    token = encrypt("secret")
    # Flip a character in the middle of the base64 body.
    tampered = token[:10] + ("A" if token[10] != "A" else "B") + token[11:]
    with pytest.raises(DecryptionError):
        decrypt(tampered)


def test_malformed_token_raises() -> None:
    with pytest.raises(DecryptionError):
        decrypt("not-base64-!!!")


def test_mask_hides_key() -> None:
    assert mask("sk-ant-abcd1234") == "••••1234"
    assert mask("xy") == "••••"


def test_prod_with_default_key_fails_closed_at_use_time(monkeypatch) -> None:
    # Boot is fine (LLM is opt-in); using crypto in prod with the in-code
    # default wrap key must fail closed.
    prod = Settings(env="prod", jwt_secret="x" * 48)  # default llm key
    monkeypatch.setattr(crypto_mod, "get_settings", lambda: prod)
    with pytest.raises(InsecureKeyError):
        encrypt("secret")


def test_prod_with_real_key_encrypts(monkeypatch) -> None:
    real = "a1" * 32  # 64 hex chars
    prod = Settings(env="prod", jwt_secret="x" * 48, llm_encryption_key=real)
    monkeypatch.setattr(crypto_mod, "get_settings", lambda: prod)
    token = encrypt("secret")
    assert decrypt(token) == "secret"


def test_prod_settings_with_default_key_still_boots() -> None:
    # The field validator does NOT reject the default at construction time.
    s = Settings(env="prod", jwt_secret="x" * 48)
    assert s.llm_encryption_key == _LLM_ENC_KEY_DEV_DEFAULT


def test_non_hex_encryption_key_rejected() -> None:
    with pytest.raises(ValueError, match="hex"):
        Settings(env="dev", llm_encryption_key="zz" * 32)


def test_wrong_length_encryption_key_rejected() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        Settings(env="dev", llm_encryption_key="ab" * 16)  # 16 bytes
