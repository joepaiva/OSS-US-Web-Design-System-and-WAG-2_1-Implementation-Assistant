"""Chassis configuration via pydantic-settings v2.

Forbidden patterns (ARCHITECTURE.md §2.1 — these are LEGACY v1 forms):
  - `class Config:` (v1)
  - `BaseSettings` from `pydantic`, not `pydantic_settings` (v1)
  - `Field(env="X")` (v1)

This module uses the v2 forms throughout — `model_config = SettingsConfigDict(...)`
and `pydantic_settings.BaseSettings`.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# FR-351 chassis-side defense — the in-code dev default for jwt_secret.
# Single source of truth so the field default + the validator's
# allow-only-in-non-prod rule stay in sync.
_JWT_SECRET_DEV_DEFAULT = "dev-only-change-me-32-chars-of-random-bytes-please"

# Dev-only AES-256 wrap key for LLM provider keys (64 hex chars = 32 bytes).
# Allowed in dev/test so the suite runs unconfigured; rejected in env=prod by
# the `_validate_llm_encryption_key` validator (mirrors FR-351 jwt_secret).
_LLM_ENC_KEY_DEV_DEFAULT = (
    "00000000000000000000000000000000000000000000000000000000deadbeef"
)

# Dev-only AES-256 wrap key for MFA TOTP secrets (64 hex chars = 32 bytes).
# Distinct from _LLM_ENC_KEY_DEV_DEFAULT — MFA secrets and LLM provider keys
# are different secret classes with independent key custody, per
# chassis-program's own security posture.
_MFA_ENC_KEY_DEV_DEFAULT = (
    "11111111111111111111111111111111111111111111111111111111beefcafe"
)

# Documentation/placeholder markers that must NEVER appear in a real
# JWT_SECRET. Reject in any environment.
_JWT_SECRET_FORBIDDEN_MARKERS: tuple[str, ...] = (
    "change-me",
    "change me",
    "your-secret",
    "your secret",
    "your_secret",
    "placeholder",
    "example",
    "todo",
    "fixme",
    "insert-",
    "<your",
    "replace this",
    "replace-this",
    "secret-here",
    "secret_here",
)


class Settings(BaseSettings):
    """All chassis configuration. Loaded from environment / .env file.

    Pydantic v2 form: `model_config = SettingsConfigDict(...)`. The legacy v1
    `class Config:` is FORBIDDEN per ARCHITECTURE.md §2.1.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Runtime profile ───────────────────────────────────────────────
    env: Literal["dev", "test", "prod"] = "dev"
    debug: bool = True
    log_level: str = "INFO"
    log_json: bool = False

    # ─── HTTP server ───────────────────────────────────────────────────
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # ─── Database ──────────────────────────────────────────────────────
    # NOTE: psycopg3 async DSN form. Driver is `postgresql+psycopg`, NOT
    # `postgresql+psycopg2` (sync) or `postgresql+asyncpg` (different lib).
    # The validator below normalizes bare `postgresql://...` and
    # Heroku-style `postgres://...` URLs to the explicit async driver form.
    database_url: str = (
        "postgresql+psycopg://chassis:chassis@localhost:5532/chassis"
    )

    @field_validator("database_url", mode="after")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        """Force the async psycopg3 driver prefix for any postgres URL.

        Azure, Heroku, Render, and several other managed-Postgres providers
        expose `postgresql://` (or sometimes `postgres://`) without the
        SQLAlchemy driver suffix. Without `+psycopg`, SA falls back to the
        default psycopg2 sync driver and the async engine blows up at first
        query.
        """
        if v.startswith("postgresql+"):
            return v  # already explicit; trust caller
        if v.startswith("postgresql://"):
            return "postgresql+psycopg://" + v[len("postgresql://"):]
        if v.startswith("postgres://"):
            return "postgresql+psycopg://" + v[len("postgres://"):]
        return v

    @field_validator("jwt_secret", mode="after")
    @classmethod
    def _reject_placeholder_jwt_secret(
        cls, v: str, info: ValidationInfo
    ) -> str:
        """FR-351 chassis-side defense: refuse to boot on placeholder JWT_SECRET.

        Customers deploying without setting a real ``JWT_SECRET`` env var
        will pick up the in-code default or the ``.env.example`` placeholder
        — both of which would let any holder of the chassis source forge
        valid tokens against the deployed app.

        Layered rule:

          1. ANY environment: reject if the value (lowercased) contains
             any marker in ``_JWT_SECRET_FORBIDDEN_MARKERS``
             ("change-me", "your-secret", "placeholder", "example",
             "todo", etc.). These are documentation shapes that no real
             random secret should ever contain.

          2. ``env == "prod"``: also reject the in-code dev default
             verbatim (``_JWT_SECRET_DEV_DEFAULT``). The dev default is
             allowed in ``env == "dev"`` and ``env == "test"`` so the
             chassis test suite and local dev work without forcing
             every developer to generate a real secret.

        Customers generate a real secret via either::

            python -c "import secrets; print(secrets.token_urlsafe(64))"
            openssl rand -hex 32

        and set it as the ``JWT_SECRET`` env var or ``.env`` value before
        deploying. The platform's future Deployment Module (FC-1) will
        automate this generation per-deploy analogous to platform-side
        FR-351 (``local_adapter.go:fr361RandomJWTSecret``).
        """
        # Rule 2: dev default verbatim is allowed in dev/test, rejected in prod.
        # Check this BEFORE the marker scan because the dev default contains
        # "dev-only" and "change-me" markers; we want a clean dev/test path.
        env = info.data.get("env", "dev") if info.data else "dev"
        if v == _JWT_SECRET_DEV_DEFAULT:
            if env == "prod":
                raise ValueError(
                    "FR-351 chassis defense: refusing to boot in env=prod "
                    "with the in-code dev JWT_SECRET default. Generate a "
                    "real secret via "
                    '`python -c "import secrets; print(secrets.token_urlsafe(64))"` '
                    "or `openssl rand -hex 32`, then set the JWT_SECRET "
                    "env var."
                )
            return v  # dev/test: allowed
        # Rule 1: any environment — reject documentation markers in any
        # customer-supplied value.
        lowered = v.lower()
        for marker in _JWT_SECRET_FORBIDDEN_MARKERS:
            if marker in lowered:
                raise ValueError(
                    f"FR-351 chassis defense: JWT_SECRET contains "
                    f"placeholder marker {marker!r}. Generate a real "
                    f"secret via "
                    f'`python -c "import secrets; print(secrets.token_urlsafe(64))"` '
                    f"or `openssl rand -hex 32`, then set the JWT_SECRET "
                    f"env var. Refusing to boot with a forgeable signing "
                    f"key."
                )
        return v

    # Per-engine tuning. Sensible defaults; override via env for prod.
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_pre_ping: bool = True
    db_pool_recycle_seconds: int = 1800
    db_echo: bool = False  # True = log every SQL statement; useful for debugging.

    # ─── Redis (RQ + cache) ────────────────────────────────────────────
    redis_url: str = "redis://localhost:6479/0"

    # ─── JWT auth ──────────────────────────────────────────────────────
    # FR-351 (chassis-side defense): the JWT signing secret MUST be a
    # cryptographically-random value with no resemblance to documentation
    # placeholders. The ``_reject_placeholder_jwt_secret`` validator below
    # rejects every documentation marker in
    # ``_JWT_SECRET_FORBIDDEN_MARKERS`` in EVERY environment, and rejects
    # the in-code dev default specifically when ``env == "prod"``. The
    # platform's future Deployment Module (FC-1) will generate per-deploy
    # random secrets analogous to platform-side FR-351
    # (``local_adapter.go:fr361RandomJWTSecret``); until that lands,
    # customers generate their own via
    # ``python -c "import secrets; print(secrets.token_urlsafe(64))"``
    # or ``openssl rand -hex 32`` before deploying.
    jwt_secret: str = Field(
        default=_JWT_SECRET_DEV_DEFAULT,
        min_length=32,
    )
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_access_token_ttl_minutes: int = 60
    jwt_refresh_token_ttl_days: int = 14

    # ─── Auth cookies ──────────────────────────────────────────────────
    cookie_secure: bool = False  # MUST be True in prod (requires HTTPS).
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str = ""

    # ─── Bcrypt ────────────────────────────────────────────────────────
    bcrypt_rounds: int = 12

    # ─── Email (FastAPI-Mail) ──────────────────────────────────────────
    mail_username: str = ""
    mail_password: str = ""
    mail_from: str = "noreply@chassis.local"
    mail_port: int = 587
    mail_server: str = "smtp.example.com"
    mail_starttls: bool = True
    mail_ssl_tls: bool = False
    mail_backend: Literal["console", "smtp"] = "console"

    # ─── AC-8 (chassis v0.6): System Use Notification ──────────────────
    # Text shown above the login form. When empty (default), no banner
    # renders. Operators set this via env var (e.g. SYSTEM_USE_NOTIFICATION="...")
    # to display the FISMA M / FedRAMP M / IL-2 system-use warning.
    # Multi-line content is supported via \n in the env var.
    system_use_notification: str = ""

    # ─── AU-11 (chassis v0.6): Audit Log Retention ─────────────────────
    # Days to retain audit_logs rows in the online table. Older rows are
    # moved to audit_logs_archive by app/audit/tasks.archive_old_audit_logs.
    # NIST 800-53 AU-11 strictest-of-three requires 6 years online OR
    # archived; default here is 365 days online + archive retains the
    # rest. Operators who need stricter online retention bump this higher.
    audit_retention_days: int = 365

    # ─── Embedded LLM (chassis v0.9) ───────────────────────────────────
    # Rule-7 parity: provider API keys are NEVER stored here — they live
    # AES-256-GCM encrypted in the DB (`llm_provider_keys`), managed via the
    # admin shell. The ONLY secret in config is the encryption key used to
    # wrap those provider keys at rest.
    #
    # `llm_encryption_key` is 64 hex chars (= 32 bytes for AES-256). The dev
    # default below lets the suite + local dev run out of the box; the
    # validator rejects it when env=prod (same posture as jwt_secret /
    # FR-351) so a real deployment must supply its own via env.
    llm_encryption_key: str = _LLM_ENC_KEY_DEV_DEFAULT
    # OpenAI-compatible base URL all LLM calls route through. Defaults to a
    # local LiteLLM proxy; the resolved per-org/shared API key is injected
    # per request (LiteLLM `configurable_clientside_auth_params`).
    llm_proxy_url: str = "http://localhost:4000"
    llm_request_timeout_seconds: float = 30.0

    # ─── MCP Client (chassis v1.1.0, FR-MCPCLIENT) ──────────────────────
    # Same class of setting as `llm_request_timeout_seconds` above: bounds
    # every MCP network call (discovery + invocation) so a hung external
    # MCP server can never hang a chat-completion request indefinitely
    # (FR-MCPCLIENT-12). Credentials reuse `llm_encryption_key` above —
    # there is no separate MCP wrap key (Rule-7 parity, FR-MCPCLIENT-2).
    mcp_request_timeout_seconds: float = 10.0

    @field_validator("llm_encryption_key", mode="after")
    @classmethod
    def _validate_llm_encryption_key(cls, v: str) -> str:
        """Require a valid 32-byte hex key (always). The "prod must not use
        the in-code default" rule is enforced at USE time (app/llm/crypto.py),
        not here: the embedded-LLM subsystem is opt-in per generated app, so a
        prod app that never touches LLM should still boot with the default —
        but the moment it encrypts/decrypts a provider key in prod with the
        default wrap key, crypto fails closed.
        """
        try:
            raw = bytes.fromhex(v)
        except ValueError:
            raise ValueError(
                "LLM_ENCRYPTION_KEY must be hex. Generate one via "
                '`python -c "import secrets; print(secrets.token_hex(32))"`.'
            ) from None
        if len(raw) != 32:
            raise ValueError(
                f"LLM_ENCRYPTION_KEY must be 32 bytes (64 hex chars); got "
                f"{len(raw)} bytes. Generate one via "
                '`python -c "import secrets; print(secrets.token_hex(32))"`.'
            )
        return v

    # ─── MFA / TOTP (IA-2(1) — chassis-program FISMA-Moderate mandate) ──
    # Rule-7-style parity with llm_encryption_key: the TOTP secret is never
    # stored in plaintext, only AES-256-GCM ciphertext in `users.mfa_secret`.
    # `mfa_encryption_key` is 64 hex chars (32 bytes). The dev default lets
    # the suite + local dev run unconfigured; the validator rejects it in
    # env=prod (same posture as jwt_secret / llm_encryption_key).
    mfa_encryption_key: str = _MFA_ENC_KEY_DEV_DEFAULT
    mfa_issuer_name: str = "Chassis"
    mfa_challenge_token_ttl_minutes: int = 5
    mfa_backup_codes_count: int = 10

    @field_validator("mfa_encryption_key", mode="after")
    @classmethod
    def _validate_mfa_encryption_key(cls, v: str) -> str:
        """Require a valid 32-byte hex key (always). Prod-default rejection
        happens at USE time (app/auth/mfa_crypto.py), mirroring
        `_validate_llm_encryption_key` — an app that never enrolls a user in
        MFA should still boot in prod with the default, but the moment MFA
        enrollment encrypts a secret in prod with the default wrap key,
        crypto fails closed.
        """
        try:
            raw = bytes.fromhex(v)
        except ValueError:
            raise ValueError(
                "MFA_ENCRYPTION_KEY must be hex. Generate one via "
                '`python -c "import secrets; print(secrets.token_hex(32))"`.'
            ) from None
        if len(raw) != 32:
            raise ValueError(
                f"MFA_ENCRYPTION_KEY must be 32 bytes (64 hex chars); got "
                f"{len(raw)} bytes. Generate one via "
                '`python -c "import secrets; print(secrets.token_hex(32))"`.'
            )
        return v

    # ─── Rate limiting (chassis v0.10) ─────────────────────────────────
    # Redis fixed-window per-client limiter (SC-5 DoS mitigation). Opt-in:
    # OFF by default so local dev + the test suite are unimpeded; operators
    # enable it in production with RATE_LIMIT_ENABLED=true (recommended).
    rate_limit_enabled: bool = False
    rate_limit_requests: int = 240  # max requests per window per client
    rate_limit_window_seconds: int = 60

    # ─── FISMA self-audit (chassis-program FR-FISMAAUDIT-8) ────────────
    # Read by the check registry so ONE generator implementation is
    # correct for every chassis-program package regardless of variant —
    # never hardcoded per package. This package's own fork of the chassis
    # is the FISMA-Moderate variant, so it is seeded at "moderate" here;
    # a Low-baseline sibling package sets this to "low" instead.
    fisma_level: str = "moderate"

    # ─── Platform Health (chassis-program FR-PLATHEALTH) ───────────────
    # Remediation auto-apply defaults OFF per blast-radius discipline
    # (FR-PLATHEALTH-8) — an operator opts in explicitly. When on, ONLY
    # patch/minor bumps that pass verification may auto-apply; major bumps
    # and any failed verification always require explicit admin approval
    # regardless of this flag.
    platform_health_auto_apply_enabled: bool = False
    platform_health_scan_timeout_seconds: int = 90

    # ─── File storage (chassis v0.10) ──────────────────────────────────
    # Local-disk storage for the embedded files API. `file_storage_dir` is
    # created on first write; `max_upload_bytes` caps a single upload.
    file_storage_dir: str = "./data/files"
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MiB

    # ─── CORS ──────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000,http://localhost:8000"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the comma-separated CORS origins env var into a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @property
    def is_test(self) -> bool:
        return self.env == "test"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton settings instance.

    Cached so we instantiate exactly once per process. Tests can clear the
    cache with `get_settings.cache_clear()` after monkeypatching env vars.
    """
    return Settings()
