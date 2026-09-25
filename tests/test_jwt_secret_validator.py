"""FR-351 chassis-side JWT_SECRET placeholder rejection (chassis v0.6.1).

The platform's app_deployer.go and local_adapter.go already generate
per-deploy random secrets for Go/Gin builds (platform-side FR-351). The
Python chassis is shipped as a customer ZIP that the customer deploys
themselves; until the FC-1 Deployment Module (Stage F) automates secret
generation for Python deploys, the chassis defends itself by refusing to
boot with placeholder values.

The validator lives in ``app/config.py:_reject_placeholder_jwt_secret``.

Tests:
  1. Documentation marker rejection (any env) — "change-me" in value.
  2. Documentation marker rejection (any env) — "your-secret".
  3. Documentation marker rejection (any env) — "placeholder".
  4. Documentation marker rejection (any env) — "<your-secret-here>".
  5. Dev default allowed in env=dev.
  6. Dev default allowed in env=test.
  7. Dev default REJECTED in env=prod.
  8. A genuine random secret (token_urlsafe(64)) accepted in env=prod.
  9. min_length=32 still enforced (regression guard on Field constraint).
"""

from __future__ import annotations

import secrets

import pytest
from pydantic import ValidationError

from app.config import _JWT_SECRET_DEV_DEFAULT, Settings


def _make_settings(jwt_secret: str | None = None, env: str = "dev") -> Settings:
    """Build a Settings instance from explicit kwargs (no .env file load).

    Settings() normally reads from process env + .env file; passing
    ``_env_file=None`` disables that so each test controls its inputs.
    """
    kwargs: dict[str, str] = {"env": env}
    if jwt_secret is not None:
        kwargs["jwt_secret"] = jwt_secret
    return Settings(_env_file=None, **kwargs)  # type: ignore[call-arg]


# ─── Marker rejection (env-independent) ─────────────────────────────────


@pytest.mark.parametrize("env", ["dev", "test", "prod"])
@pytest.mark.parametrize(
    "bad_value",
    [
        "change-me-now-with-thirty-two-extra-chars-padding",
        "your-secret-goes-here-padding-padding-padding-1234",
        "PLACEHOLDER-do-not-deploy-with-this-value-ever-ok",
        "<your-secret-here>-padding-padding-padding-padding",
        "TODO-fill-this-in-before-prod-padding-padding-1234",
        "FIXME-generate-real-secret-padding-padding-padding",
        "example-secret-for-docs-only-padding-padding-padding",
    ],
)
def test_placeholder_markers_rejected_in_every_env(
    env: str, bad_value: str
) -> None:
    """Any value containing a documentation marker is rejected everywhere."""
    with pytest.raises(ValidationError) as exc_info:
        _make_settings(jwt_secret=bad_value, env=env)
    # Pydantic wraps the ValueError; the FR-351 message is in the chain.
    assert "FR-351" in str(exc_info.value)


# ─── In-code dev default behavior ───────────────────────────────────────


@pytest.mark.parametrize("env", ["dev", "test"])
def test_dev_default_allowed_in_dev_and_test(env: str) -> None:
    """Existing chassis test suite + local dev work without forcing secret gen."""
    s = _make_settings(jwt_secret=_JWT_SECRET_DEV_DEFAULT, env=env)
    assert s.jwt_secret == _JWT_SECRET_DEV_DEFAULT


def test_dev_default_rejected_in_prod() -> None:
    """env=prod must refuse to boot with the dev default verbatim."""
    with pytest.raises(ValidationError) as exc_info:
        _make_settings(jwt_secret=_JWT_SECRET_DEV_DEFAULT, env="prod")
    assert "FR-351" in str(exc_info.value)
    assert "env=prod" in str(exc_info.value)


# ─── Happy path ─────────────────────────────────────────────────────────


def test_real_random_secret_accepted_in_prod() -> None:
    """A cryptographically-random secret passes the validator in prod."""
    real_secret = secrets.token_urlsafe(64)
    s = _make_settings(jwt_secret=real_secret, env="prod")
    assert s.jwt_secret == real_secret


def test_real_random_secret_accepted_in_dev() -> None:
    """Customer-supplied real secrets pass in dev too."""
    real_secret = secrets.token_urlsafe(64)
    s = _make_settings(jwt_secret=real_secret, env="dev")
    assert s.jwt_secret == real_secret


# ─── Regression guard on Field(min_length=32) ───────────────────────────


def test_min_length_still_enforced() -> None:
    """A short non-placeholder value still fails min_length=32."""
    with pytest.raises(ValidationError):
        _make_settings(jwt_secret="too-short", env="dev")
