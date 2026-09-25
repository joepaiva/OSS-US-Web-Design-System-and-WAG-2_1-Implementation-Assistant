# python-fastapi-mt-fisma-moderate-llm — DESIGN

**Version:** 1.2.1
**Date:** 2026-09-21
**Status:** Authoritative
**Chassis version:** 1.1.0
**Realizes:** [`REQUIREMENTS.md`](REQUIREMENTS.md) under [`CONSTITUTION.md`](CONSTITUTION.md).

> This document is the **technology-specific** realization of this package's own REQUIREMENTS: module layout, every data model, the full endpoint catalog, middleware and request lifecycle, the mechanisms behind each capability, configuration, migrations, and an FR→design traceability map. It is regeneration-grade. Inherited in full from `chassis/python-fastapi/specs/DESIGN.md` v1.0.1 except where §7a (MFA) and §7b–§7d (the three new shared capabilities) add package-specific design not present in the reference chassis. §6.14/§3.5a/§4.6 add the MCP Client capability (FR-MCPCLIENT), realized per `chassis-program-DESIGN.md` §6.

---

## 1. Architecture Overview

```
Browser / API client
   │  (Bearer header or chassis_access_token cookie)
   ▼
ASGI app (FastAPI, app/main.py: create_app)
   ├─ Middleware (outer→inner): request-id+client-IP  →  [rate-limit, opt-in]  →  CORS
   ├─ Exception handler (SI-11 prod/dev)
   ├─ Routers: health, auth, orgs, admin, files, notifications, frontend(+static), slots
   ├─ Dependencies: get_current_user → CurrentUser; get_current_org → CurrentOrg; requires(perm)
   ├─ Services (async, no HTTP imports)  →  SQLAlchemy 2.0 async  →  PostgreSQL
   └─ Redis  ←  RQ jobs (worker process) + rate-limit counters
```

- **App factory:** `create_app(settings) -> FastAPI` (testable with injected `Settings`). Module-level `app = create_app()` for `uvicorn app.main:app`.
- **Lifespan:** on startup, opens a session and runs `seed_chassis_rbac` (idempotent permission+role seed). Logs `chassis.startup` / `chassis.shutdown`.
- **Context vars** (`app/db.py`, `app/deps_context.py`): `current_org_id_var`, `current_user_id_var`, `current_client_ip_var` — bound per request, read by tenancy listeners + the audit decorator, propagate through async tasks.

---

## 2. Module Layout

```
app/
  main.py            # app factory, middleware, router registration, lifespan, extension markers
  config.py          # Settings (pydantic-settings) + validators
  db.py              # Base, async engine/sessionmaker, SessionDep, TenantScoped, RetainableFor, tenancy listeners, context vars
  deps.py            # get_current_user/CurrentUser, get_current_org/CurrentOrg, requires(perm), ACCESS_TOKEN_COOKIE
  deps_context.py    # current_user_id_var, current_client_ip_var (+ get/set)
  logging.py         # configure_logging (structlog: JSON prod / console dev), get_logger
  error_handlers.py  # prod_exception_handler (SI-11)
  error_messages.py  # STANDARD_MESSAGES{} + ERR_* aliases + message_for_status
  frontend.py        # Jinja2 templates instance, _common_context, optional_current_user, HTML routes, mount_static
  auth/      models.py schemas.py service.py routes.py providers/__init__.py
  rbac/      models.py permissions.py service.py
  orgs/      models.py schemas.py service.py routes.py
  audit/     models.py decorator.py tasks.py
  health/    routes.py
  mail/      service.py
  tasks/     queue.py worker.py
  llm/       crypto.py models.py transport.py service.py schemas.py
  mcp/       models.py service.py client.py __init__.py   # FR-MCPCLIENT — routes live in admin/routes.py, not a separate routes.py
  files/     models.py service.py schemas.py routes.py
  notifications/  models.py service.py schemas.py routes.py
  ratelimit/ middleware.py
  admin/     routes.py service.py health_service.py docs_service.py reports_service.py
  templates/ base.html error.html auth/* dashboard/* admin/* components/*
  static/    css/stripe-overrides.css
  slots/     example/ example_with_states/  (reference slots)
migrations/versions/  0001..0014
tests/                33 test modules under tests/ + 4 under app/slots/*/tests/ (351 tests total, `uv run pytest -q`)
```

---

## 3. Data Models (all tables)

> All timestamps are `DateTime(timezone=True)`, server-defaulted to `now()`; `updated_at` columns use `onupdate=now(UTC)`.

### 3.1 `users` (`app/auth/models.py`) — FR-AUTH, AC-2, AC-7, IA-2(1)
`id` PK · `email` String(255) unique+index · `password_hash` String(255) · `full_name` String(255) null · `is_active` Bool=true · `is_superuser` Bool=false · `failed_login_attempts` Int=0 · `last_failed_login_at` DateTime null · `locked_until` DateTime null index · `created_at` · `updated_at` · **`mfa_enabled` Bool=false** (this package only — IA-2(1)) · **`mfa_secret` String(255) null** (AES-256-GCM ciphertext, never plaintext) · **`mfa_enrolled_at` DateTime null**.

### 3.1a `mfa_backup_codes` (`app/auth/models.py`) — FR-AUTH-15, IA-2(1) (this package only)
`id` PK · `user_id` FK users CASCADE index · `code_hash` String(255) (hashed, same discipline as password storage — never the plaintext code) · `used` Bool=false · `used_at` DateTime null · `created_at`. Ten rows generated per enrollment/regeneration; a code is deleted (or flagged used, implementation-consistent with `mfa.py`) on successful redemption so it cannot be replayed. Migration `0011_mfa`.

### 3.2 RBAC (`app/rbac/models.py`) — FR-RBAC
- `permissions`: `id` PK · `name` String(128) unique(uq_permissions_name)+index · `description` String(255) null · `created_at`. Rel: `roles` (M:N, lazy selectin).
- `roles`: `id` PK · `name` String(64) unique(uq_roles_name)+index · `description` String(255) null · `created_at` · `updated_at`. Rel: `permissions` (M:N, lazy selectin).
- `role_permissions` (assoc): PK (`role_id`,`permission_id`), both FK CASCADE.
- `user_roles` (assoc): PK (`user_id`,`role_id`), both FK CASCADE — **system-wide** grants.

### 3.3 Orgs (`app/orgs/models.py`) — FR-TEN
- `organizations`: `id` PK · `name` String(255) · `slug` String(64) unique(uq_organizations_slug)+index · `created_at` · `updated_at`.
- `memberships`: `id` PK · `user_id` FK users CASCADE index · `org_id` FK organizations CASCADE index · `role_id` FK roles SET NULL null (per-org role override) · `is_default` Bool=false · `created_at`. Unique(`user_id`,`org_id`)=uq_memberships_user_org.

### 3.4 `audit_logs` (`app/audit/models.py`) — FR-AUD, AU-3
`id` PK · `organization_id` FK orgs SET NULL null index · `user_id` FK users SET NULL null index · `action` String(128) index · `entity_type` String(64) null · `entity_id` Int null · `details` JSON not-null default{} · `ip_address` String(64) null · `created_at` index. Companion `audit_logs_archive` (same shape) created by migration 0007; AU-9 REVOKE UPDATE/DELETE by migration 0008.

### 3.5 LLM (`app/llm/models.py`) — FR-LLM
- `llm_provider_keys`: `id` PK · `organization_id` FK orgs CASCADE null index (NULL = platform-shared) · `provider` String(64) index · `encrypted_key` Text (AES-256-GCM ciphertext) · `is_active` Bool=true · `created_by_user_id` FK users SET NULL null · `created_at` · `updated_at`. Helper `is_shared = organization_id is None`.
- `org_llm_access`: `id` PK · `organization_id` FK orgs CASCADE unique(uq_org_llm_access_org)+index · `allow_shared_key` Bool=false · `updated_at`.

### 3.5a `mcp_server_connections` (`app/mcp/models.py`) — FR-MCPCLIENT
`id` PK · `organization_id` FK orgs CASCADE **not-null** index (always org-scoped — no platform-shared variant, unlike `llm_provider_keys.organization_id`) · `name` String(255) · `url` String(2048) · `encrypted_credential` Text null (AES-256-GCM ciphertext via `llm/crypto.py`'s `encrypt`/`decrypt`/`mask` — reused directly, not reimplemented; NULL = unauthenticated server, a valid config) · `enabled` Bool=false server_default `"false"` (registering ≠ exposing) · `created_by_user_id` FK users SET NULL null · `created_at` · `updated_at`.

### 3.6 `file_objects` (`app/files/models.py`) — FR-FILE
`id` PK · `organization_id` FK orgs CASCADE index · `owner_user_id` FK users SET NULL null · `filename` String(255) · `content_type` String(127) default `application/octet-stream` · `size_bytes` BigInteger · `sha256` String(64) · `storage_key` String(64) unique(uq_file_objects_storage_key) · `created_at`.

### 3.7 `notifications` (`app/notifications/models.py`) — FR-NOTE
`id` PK · `user_id` FK users CASCADE index · `organization_id` FK orgs CASCADE null · `title` String(255) · `body` Text default "" · `level` String(16)=info (one of info/success/warning/error) · `is_read` Bool=false index · `created_at` · `read_at` DateTime null.

### 3.8 Mixins (`app/db.py`)
- `TenantScoped`: adds `org_id` FK orgs CASCADE not-null index; signals tenancy listeners.
- `RetainableFor` (SI-12): adds `retained_until` DateTime null index for per-row retention.

---

## 4. Endpoint Catalog

### 4.1 Health (`app/health/routes.py`) — FR-OBS
| Method | Path | Auth | Response | Codes |
|---|---|---|---|---|
| GET | `/healthz` | none | `{status:"ok"}` | 200 |
| GET | `/readyz` | none | `{status:"ready"|"degraded", checks:{database:...}}` | 200 / 503 |
| GET | `/version` | none | `{version, chassis}` | 200 |

`version` is the **app** package version (`app.__version__`, semver from `pyproject.toml`); `chassis` is the **chassis framework** version read from the `CHASSIS_VERSION` file at import time (`app.__chassis_version__`, kept in lockstep with the platform's Go seed pin). The two are distinct values — a generated app carries its own app version while reporting the chassis it was built on. `__chassis_version__` falls back to `__version__` only if `CHASSIS_VERSION` is unreadable.

### 4.2 Auth (`app/auth/routes.py`) — FR-AUTH
| Method | Path | Auth | Body | Response | Codes |
|---|---|---|---|---|---|
| POST | `/auth/register` | none | `UserRegister{email,password,full_name?}` | `TokenResponse` + cookie | 201 / 409 / 422 |
| POST | `/auth/login` | none | `UserLogin{email,password}` | `TokenResponse` **or** `MFAChallengeResponse` (if `mfa_enabled`) + cookie | 200 / 401 |
| POST | `/auth/logout` | none | — | deletes cookie | 204 |
| GET | `/auth/me` | CurrentUser | — | `UserRead` | 200 / 401 |
| POST | `/auth/mfa/enroll` | CurrentUser | — | `MFAEnrollStartResponse{secret, provisioning_uri}` | 200 / 409 (already enrolled) |
| POST | `/auth/mfa/enroll/confirm` | CurrentUser | `{code}` | `MFAEnrollConfirmResponse{backup_codes}` | 200 / 400 (bad code) |
| POST | `/auth/mfa/verify` | Challenge token (from login) | `{challenge_token, code}` | `TokenResponse` + cookie | 200 / 401 |
| POST | `/auth/mfa/disable` | CurrentUser | — | — | 204 |
| POST | `/auth/mfa/backup-codes/regenerate` | CurrentUser | — | `MFABackupCodesResponse{backup_codes}` | 200 |

### 4.3 Orgs (`app/orgs/routes.py`) — FR-TEN
| Method | Path | Auth | Body | Codes |
|---|---|---|---|---|
| POST | `/orgs` | CurrentUser | `OrgCreate{name,slug}` | 201 / 409 |
| GET | `/orgs` | CurrentUser | — | 200 (member orgs) |
| GET | `/orgs/me` | CurrentUser | — | 200 (`OrgRead|null`) |
| PUT | `/orgs/me` | CurrentUser | `SwitchOrgRequest{org_id}` | 200 / 403 |

### 4.4 Files (`app/files/routes.py`, prefix `/api/files`) — FR-FILE; CurrentUser+CurrentOrg
| Method | Path | Codes |
|---|---|---|
| GET | `` | 200 list (org-scoped) |
| POST | `` (multipart `file`) | 201 / 413 (too large) / 400 |
| GET | `/{file_id}/download` | 200 (+`X-Content-SHA256`, content-disposition) / 404 / 410 |
| DELETE | `/{file_id}` | 204 / 404 |

### 4.5 Notifications (`app/notifications/routes.py`, prefix `/api/notifications`) — FR-NOTE; CurrentUser
| Method | Path | Codes |
|---|---|---|
| GET | `?unread_only=` | 200 list |
| GET | `/unread-count` | 200 `{unread}` |
| POST | `/{id}/read` | 200 / 404 |
| POST | `/read-all` | 200 `{unread:0}` |

### 4.6 Admin shell (`app/admin/routes.py`, prefix `/admin`, HTML) — FR-ADM/OBS/DOC/REP/LLM
Gate via `_resolve(request, session, require_platform, permission)`: anonymous→303 login; unauthorized→403 page.
| Method | Path | Gate |
|---|---|---|
| GET | `/admin` | users:write |
| GET/POST | `/admin/users`, `/admin/users/{id}/deactivate|reactivate` | users:write (platform=all, org-admin=members; no self-deactivate) |

**Where the org-admin=members constraint is enforced, and why it is a required argument.** `set_user_active(session, user_id, active, *, platform, org_id)` takes the caller's resolved scope as REQUIRED keyword arguments and resolves a non-platform caller's target through `Membership(user_id, org_id)` before touching `is_active`. It previously took neither and resolved by primary key alone, so this table's `org-admin=members` constraint was documented but not implemented — an org administrator could deactivate or reactivate any user on the platform by id (proven by execution 2026-09-17; FR-ADM-2 was silent on write scope, which is how the divergence survived review). The arguments are required rather than defaulted so a new call site cannot silently reintroduce the gap. A cross-org target raises `AdminError("user not found")` → 404, per FR-TEN-7's not-found convention, and the check precedes the mutation so a refused call leaves the target unchanged.
| GET/POST | `/admin/orgs` | platform only |
| GET | `/admin/system-health` | platform only |
| GET | `/admin/reports` | users:write (platform=global, org=scoped) |
| GET | `/admin/docs`, `/admin/docs/{slug}` | users:write (whitelist; 404 unknown) |
| GET/POST | `/admin/llm`, `/admin/llm/keys`, `/admin/llm/keys/{id}/deactivate`, `/admin/llm/access` | llm:write (shared keys + access policy = platform only) |
| GET | `/admin/mcp` | mcp:write (org-scoped list + registration form) |
| POST | `/admin/mcp/servers` | mcp:write |
| POST | `/admin/mcp/servers/{id}/enable`, `/admin/mcp/servers/{id}/disable` | mcp:write (own org's connection only — 403 cross-org) |
| POST | `/admin/mcp/servers/{id}/delete` | mcp:write (own org's connection only — 403 cross-org) |

### 4.7 Frontend (`app/frontend.py`, HTML) — FR-UI
`GET /` (→/dashboard or /auth/login) · `GET /dashboard` · `GET|POST /auth/login` · `GET|POST /auth/register` · `POST /auth/logout` · `GET /account`. Static mounted at `/static`.

---

## 5. Request Lifecycle & Middleware

**Order (outermost first):**
1. **request-id + client-IP** (`@app.middleware("http")`): assigns/honors `X-Request-ID`, binds it to structlog contextvars, binds `current_client_ip_var` from `X-Forwarded-For[0]` or peer; echoes `X-Request-ID`.
2. **Rate limit** (opt-in, `app/ratelimit/middleware.py`): installed only if `rate_limit_enabled`; see §9.
3. **CORS**: enabled when `cors_origins_list` non-empty; `allow_credentials=True`.
4. **Exception handler** (`prod_exception_handler`): catches non-HTTPException; prod → generic `{error, request_id}`; dev → adds type/message; always logs full `exc_info`.

**Dependency chain for a protected slot route:** `get_current_user` (decodes token from header/cookie, loads active user, binds `current_user_id_var`) → `get_current_org` (resolves default org, binds `current_org_id_var`) → `requires(perm)` (calls `user_has_permission`, 403 on miss). Session via `SessionDep` (commit on success / rollback on error).

---

## 6. Mechanism Designs (FR realization)

### 6.1 Authentication (FR-AUTH)
`auth/service.py`: `hash_password`/`verify_password` (direct `bcrypt` calls via `auth/password_hashing.py`, cost=`bcrypt_rounds`); `issue_access_token` (JWT claims `sub,exp,iat,email`; alg=`jwt_algorithm`; TTL=`jwt_access_token_ttl_minutes`); `decode_token` (verify sig+exp). `authenticate()` implements **AC-7**: locked→`AccountLocked` before verify; wrong secret→increment within 15-min window (reset if stale), lock at 3 for 30 min; success clears counters. If the user has `mfa_enabled`, `authenticate()` returns an MFA-pending result instead of a full session (see §6.13) — the password check still ran and still gates lockout, but no session token issues until the second factor verifies. `register_user` rejects duplicate email. Routes set the `chassis_access_token` cookie (HttpOnly, Secure=`cookie_secure`, SameSite=lax, max-age=TTL×60). IA-5 complexity in `auth/schemas.py:validate_password_complexity` (14 chars, 4 classes), re-exported for the HTML form.

### 6.2 Authorization (FR-RBAC)
`rbac/service.py:user_has_permission`: superuser→True; else match via system-wide `user_roles`→`role_permissions`→`permissions.name`; else (if `current_org_id_var` bound) via `memberships`→`role_permissions`. `seed_chassis_rbac` (startup): upsert all `CorePermissions`, ensure `admin`/`user` roles, grant **all** to admin, grant `{users:read, orgs:read}` to user. `deps.requires(perm)` depends on `CurrentOrg` first so per-org grants are visible. Core permissions: `users:read|write`, `orgs:read|write`, `audit:read`, `llm:read|write`. Slots add via `permissions.register(...)`.

### 6.3 Multi-tenancy (FR-TEN)
`db.py` SQLAlchemy event listeners: `do_orm_execute` injects `with_loader_criteria(TenantScoped, cls.org_id == current_org_id)` on SELECT when the org var is bound; `before_flush` stamps `org_id` on new TenantScoped rows when unset. Unbound context = no-op (CLI/admin escape hatch). `orgs/service.py`: `create_org` (creator→admin membership, default if first), `get_default_org_for_user` (is_default desc, then id), `switch_default_org` (member-checked, audited). Cross-tenant fetch returns None → routes 404.

### 6.4 Audit (FR-AUD)
`audit/decorator.py:@audited(action, entity_type=, capture_details=)`: finds the `AsyncSession` arg; on success builds `AuditLog` with action, `entity_id=getattr(result,"id",None)`, `details=capture_details(result)`, and context-var actor/org/IP; `add`+`flush`. Skips with a warning if no session. `audit/tasks.py:archive_old_audit_logs(cutoff_days?)` moves `created_at < now-retention` rows to `audit_logs_archive` (single transaction, idempotent), default window `audit_retention_days`=365; runnable via RQ.

### 6.5 Observability + System Health (FR-OBS)
`health/routes.py` as §4.1 (`/readyz` does `SELECT 1`). `logging.py:configure_logging` → structlog JSON (prod/`log_json`) or console (dev), shared processors merge contextvars. `admin/health_service.py:gather_system_health` returns version/chassis/env/debug + best-effort DB (`SELECT 1`) and Redis (`ping`, 0.5s connect/read timeout) checks (the `chassis_version` field is sourced from `app.__chassis_version__` / the `CHASSIS_VERSION` file, distinct from the app `version`); `_redact_host` strips credentials from any DSN; never raises. Rendered by `templates/admin/system-health.html`.

### 6.6 In-app Docs (FR-DOC)
`admin/docs_service.py`: `_DOC_REGISTRY` whitelists slugs→(title, summary, relative path) for `how-it-works`, `user-manual`, `security-self-audit`, `readme`; `get_doc(slug)` returns None for unknown (no path built from input). `render_markdown` HTML-escapes source then re-introduces a fixed safe subset (headings, lists, tables, fenced/inline code, blockquotes, bold/italic, links restricted to http/https/mailto/relative/anchor). Templates `admin/docs.html` (index) + `admin/doc.html` (single, `{{ doc_html|safe }}`).

### 6.7 Embedded LLM (FR-LLM)
- `llm/crypto.py`: AES-256-GCM; token = base64(nonce[12] ‖ ct+tag); `_load_key()` reads `llm_encryption_key`, and in `is_prod` raises `InsecureKeyError` if it equals the in-code default (**use-time** fail-closed); `encrypt`/`decrypt` (decrypt raises `DecryptionError` on tamper/wrong key); `mask` (last 4 chars).
- `llm/service.py`: `resolve_api_key(provider, org_id)` = org active key → shared active key iff `org_allows_shared(org_id)` (or org_id None) → `LLMKeyUnavailable`. `set_key` deactivates prior active for the (scope,provider) then inserts (`@audited`). `deactivate_key`, `list_keys` (decrypt→mask; "(unreadable)" on failure), `set_org_shared_access` (`@audited`), `list_org_access`, `complete(...)` (resolve → transport).
- `llm/transport.py`: `LLMTransport` protocol; `HTTPTransport.chat` POSTs `{llm_proxy_url}/chat/completions` with OpenAI body + `api_key` (LiteLLM clientside auth) + Bearer header, `llm_request_timeout_seconds`; raises `LLMError`. `get_transport`/`set_transport` (singleton; tests inject a fake).
- Admin: `/admin/llm` per §4.6.

### 6.8 Files (FR-FILE)
`files/service.py`: `store_file` (size cap → `FileTooLarge`; sha256; write to `file_storage_dir/<uuid hex>`; `@audited`), `get_file` (org-scoped), `list_files`, `read_bytes`, `delete_file` (row delete + best-effort unlink; `@audited`), `org_usage`. Routes per §4.4; org isolation via CurrentOrg.

### 6.9 Notifications (FR-NOTE)
`notifications/service.py`: `notify` (level fallback→info; not audited — high volume), `list_for_user(unread_only?)`, `unread_count`, `mark_read` (user-scoped → None if foreign), `mark_all_read` (bulk update). Routes per §4.5.

### 6.10 Rate limiting (FR-RL)
`ratelimit/middleware.py:RateLimitMiddleware` bound to the app's `Settings`: per-client key `ratelimit:{ip}:{window-bucket}`; Redis `INCR`+`EXPIRE(window)`; over `rate_limit_requests` → 429 + `Retry-After`; exempt `/healthz,/readyz,/version,/static,/metrics`; Redis error → fail open. `install_rate_limiting(app, settings)` adds it only when `rate_limit_enabled`.

### 6.11 Reporting (FR-REP)
`admin/reports_service.py:gather_report(org_id, platform)` → `PlatformReport` (users total/active, orgs total [platform], audit total + top-5 actions, files count+bytes, notifications total+unread, active LLM keys); platform=global, else filtered by org. Rendered by `templates/admin/reports.html`.

### 6.12 Mail / Jobs / Errors
- `mail/service.py:send_email` → console (dev) or fastapi-mail SMTP (prod); returns delivery dict.
- `tasks/queue.py`: `get_redis`/`get_queue`/`enqueue`; `tasks/worker.py:main` runs the RQ worker.
- `error_handlers.py:prod_exception_handler` (SI-11); `error_messages.py:STANDARD_MESSAGES` (400–504) + `ERR_*` aliases + `message_for_status`.

### 6.13 MFA / TOTP (FR-AUTH-15, IA-2(1)) — this package only, not in the reference chassis
`auth/mfa_crypto.py`: AES-256-GCM wrap/unwrap for the TOTP secret at rest, same primitive and use-time fail-closed discipline as `llm/crypto.py` (§6.7) — a second, independent instance rather than a shared module, since this package vendors its own copy of every capability per `chassis-program-CONSTITUTION.md` §2.

`auth/mfa.py`:
- `start_enrollment(user)` → generates a random TOTP secret, returns `(secret, provisioning_uri)` for QR rendering; raises `MFAAlreadyEnrolled` if `mfa_enabled` is already true. The secret is not yet persisted as active — it's returned to the client for confirmation.
- `confirm_enrollment(session, user, secret, code)` → verifies the submitted TOTP code against the just-generated secret; on success, encrypts and stores the secret, sets `mfa_enabled=True`, `mfa_enrolled_at=now()`, and generates 10 single-use backup codes (`_regenerate_backup_codes`, hashed like passwords, never stored plaintext). Raises `InvalidMFACode` on mismatch — enrollment does not complete on a bad code.
- `disable_mfa(session, user)` → self-service: clears `mfa_enabled`/`mfa_secret`/`mfa_enrolled_at`, deletes backup codes.
- `regenerate_backup_codes(session, user)` → invalidates the old set, issues 10 new ones. Raises `MFANotEnrolled` if MFA isn't active.
- **Two-step login flow:** `authenticate()` (§6.1), on a successful password check for an MFA-enabled user, does not issue a full session — it calls `issue_challenge_token(user)` (a short-lived, purpose-scoped JWT carrying `mfa_pending=True`, decoded by `decode_challenge_token`) and the `/auth/login` route returns `MFAChallengeResponse{challenge_token}` instead of `TokenResponse`. The client then calls `/auth/mfa/verify` with `{challenge_token, code}`; `verify_login_code(session, user, code)` accepts either a live TOTP code or an unused backup code (marking it used on redemption), and only then does the route issue the real session token + cookie. A challenge token cannot be used as a session token — it carries no permission claims and is rejected by the ordinary auth dependency.
- **Privileged-account gate:** the FISMA-Moderate mandate (`REQUIREMENTS.md` FR-AUTH-15) requires MFA for **platform-wide** administrative privilege specifically — `deps.py`'s `requires_platform_admin`-style dependency (or equivalent gate used by `admin/routes.py`) additionally checks `user.mfa_enabled` and rejects (403, not merely "reduced access") a platform-admin-privileged caller who hasn't enrolled, distinct from the ordinary RBAC permission check. An org-scoped "admin" role (granted automatically to whoever creates an organization, per `orgs/service.py:create_org`) does **not** trigger this gate — see `CONSTITUTION.md` §3's note on why that scope distinction matters (forcing MFA onto ordinary multi-tenant org-creation would be a usability regression unrelated to the actual privileged-account risk this control targets).
- Data model: §3.1 (`users.mfa_enabled/mfa_secret/mfa_enrolled_at`) and §3.1a (`mfa_backup_codes`). Migration `0011_mfa`.
- Design-reference precedent (not code reuse — different language/module): the platform's own License Server module has an approved TOTP implementation (`github.com/pquerna/otp`, FR-491) with the same enrollment/verify/backup-code shape; this module follows that pattern's architecture, reimplemented natively in Python for this chassis.

### 6.14 MCP Client (FR-MCPCLIENT) — this package only, not in the reference chassis

Realizes `specs/chassis-program/shared-capabilities/MCP-CLIENT-REQUIREMENTS.md` per the concrete mechanism confirmed in `chassis-program-DESIGN.md` §6 for this exact package. SDK: `mcp` (official Python MCP SDK, `modelcontextprotocol/python-sdk`), pinned at the latest-stable version recorded in `pyproject.toml`'s `[project] dependencies` (re-verified at each dependency-currency pass, same discipline as every other pin — see the comment block there). Only the SDK's **client** surface is used — `mcp.Client` (the modern high-level streamable-HTTP client) and, for tests only, `mcp.server.mcpserver.MCPServer` (the SDK's low-ceremony server-authoring API — note: in `mcp` 2.x this class replaced the 1.x `mcp.server.fastmcp.FastMCP` name; importing `mcp.server.fastmcp` under 2.x raises `ModuleNotFoundError` with a migration pointer, confirmed by direct inspection of the installed package). No inbound MCP server capability is ever built or shipped in the app itself.

- `mcp/models.py`: `MCPServerConnection` — see §3.5a. No `TenantScoped` mixin (that mixin's column is `org_id`; this row follows `llm_provider_keys`'s own hand-rolled `organization_id` naming for consistency with the sibling FR-LLM table it reuses encryption from). Migration `0014_mcp_client` (see §8).
- `mcp/client.py`: a thin wrapper around the SDK, isolating every SDK call behind two functions so `service.py` never imports `mcp` directly:
  - `list_tools(*, url, credential, timeout_seconds) -> list[mcp_types.Tool]` — builds an `httpx.AsyncClient` with `Authorization: Bearer <credential>` (only when a credential is set) and `timeout=timeout_seconds`, opens `mcp.Client(streamable_http_client(url, http_client=that_client), read_timeout_seconds=timeout_seconds)` as an async context manager, calls `.list_tools()`, returns `.tools`. Any exception (unreachable server, protocol error, timeout) is caught and re-raised as this module's own `MCPClientError` — never a raw SDK/httpx exception crosses into `service.py`.
  - `call_tool(*, url, credential, tool_name, arguments, timeout_seconds) -> mcp_types.CallToolResult` — same connection shape, calls `.call_tool(tool_name, arguments, read_timeout_seconds=timeout_seconds)`. The SDK itself distinguishes a normal tool-reported error (`CallToolResult.is_error=True`, e.g. the fixture server's `lookup` on an unknown key) from a transport/connection failure (raises); `call_tool` lets the former return normally and converts the latter to `MCPClientError`, matching FR-MCPCLIENT-10/11's shape.
- `mcp/service.py`:
  - CRUD — `create_connection`, `list_connections` (masked credential, `llm/crypto.py:mask` reused directly), `update_connection`, `delete_connection`, `enable_connection`/`disable_connection` — every mutation decorated `@audited("mcp.connection_<verb>", entity_type="mcp_server_connection", capture_details=lambda c: {"name": c.name, "url": c.url, "id": c.id, "enabled": c.enabled})`; the lambda never includes `encrypted_credential` or a decrypted value (FR-MCPCLIENT-5).
  - `discover_tools(session, org_id) -> list[dict]` — selects the org's `enabled` connections only (`WHERE organization_id = :org_id AND enabled IS TRUE`, the same org-leading-predicate discipline as FR-TEN), and for each calls `mcp.client.list_tools` with its decrypted credential (`llm/crypto.py:decrypt`, reused — never a second implementation) and `settings.mcp_request_timeout_seconds`. Each returned `Tool` is mapped to an OpenAI-format entry: `{"type": "function", "function": {"name": f"{connection.name}.{tool.name}", "description": tool.description, "parameters": tool.input_schema}}`. A connection that raises `MCPClientError` is logged (`mcp.discover.connection_failed`, connection id/name only — never the credential) and skipped; discovery never raises for a single bad connection (FR-MCPCLIENT-9). An org with zero enabled connections short-circuits before any SDK call — `discover_tools` returns `[]` without opening a connection, so **no import or call into `mcp/client.py` happens at all** on that path (NFR-MCPCLIENT-1).
  - `invoke_tool(session, org_id, qualified_name, arguments) -> dict` — splits `qualified_name` on the first `.` into `(connection_name, tool_name)`; resolves that connection **scoped to `org_id`** (never another org's row, even if the name collides — FR-MCPCLIENT-8); on no match, malformed qualified name, or an `MCPClientError` from `mcp.client.call_tool`, returns `{"error": "<message>"}` — never raises. On a normal `CallToolResult`, returns `{"error": "..."}` if `is_error` else `{"result": <joined text content>}`. The bounded timeout (FR-MCPCLIENT-12) is `settings.mcp_request_timeout_seconds`, threaded through to both the connecting `httpx.AsyncClient`'s `timeout` and the SDK client's `read_timeout_seconds`.
- Admin: `/admin/mcp` per §4.6 — `admin/routes.py`, same `_resolve(...)` gate shape as `/admin/llm`, permission `mcp:write` (added to `CorePermissions`, `rbac/permissions.py` — no new permission *model*, just two more registry entries, per FR-MCPCLIENT-3). Template `admin/mcp.html`, a structural copy of `admin/llm.html` (USWDS table + form-POST create, breadcrumb, `{% extends "base.html" %}`) with name/URL/credential/enabled fields instead of provider/key/scope. A link from `admin/dashboard.html`'s card grid, alongside the LLM Provider Keys card.
- **Tool-calling integration — the load-bearing mechanism.** `llm/transport.py:HTTPTransport.chat` already accepts `**extra: Any` and merges it into the request body (`body.update(extra)`) — LiteLLM's OpenAI-compatible proxy passes an OpenAI-shaped `tools` array through to the upstream provider unmodified, so **no change to `transport.py` is required.** The extension lands entirely in `app/slots/greeting/providers/translation.py`'s `_try_llm_translate()` (the package's sole `llm.service.complete()` caller): before calling `complete()`, it calls `mcp.service.discover_tools(session, org_id)`; when non-empty, `tools=<discovered list>` is passed as one of `complete()`'s `**extra` kwargs (already plumbed per the point above). If the response carries `choices[0].message.tool_calls` (standard OpenAI shape), a new loop — bounded to `_MCP_MAX_TOOL_ITERATIONS = 3` — runs `mcp.service.invoke_tool()` for each call, appends a `{"role": "tool", "tool_call_id": ..., "content": <json of the result-or-error dict>}` message, and re-invokes `complete()`, until a response with no `tool_calls` is returned or the cap is hit (the cap's exhaustion is not an error — the loop simply returns the last response as-is, per FR-MCPCLIENT-7's "or a bounded iteration cap is reached"). An org with zero enabled connections takes `discover_tools()` → `[]` → no `tools` kwarg → the exact single `complete()` call that existed before this capability (NFR-MCPCLIENT-1, verified by a test asserting `tools` is absent from a mocked `complete()`'s call args, not merely "not mentioned"). **Demo visibility:** the fixture/demo MCP server (§6.14's test fixture, mirrored in a small always-available demo connection an operator can point at their own registered server) exposes a `lookup(key)` tool the translation prompt can plausibly invoke for a "regional greeting convention" fact — with an enabled connection registered, an unsupported-locale translation can visibly fold a real tool result into its LLM-generated text, distinguishable from the same request with MCP disabled. `GreetingResponse` gains `tools_used: list[str]` (qualified tool names actually invoked, `[]` when none) and `greeting.html`'s existing meta line (`Locale: ... · Source: ...`) is extended with `· Tools used: <name, name>` only when non-empty — no layout change on the common path.
- **Failure handling (mandatory, FR-MCPCLIENT-9..12):** every failure mode below degrades to "skip/report, never crash" — enforced by `mcp/client.py`'s catch-and-convert boundary plus `service.py`'s per-connection try/except in `discover_tools` and the always-non-raising contract of `invoke_tool`. Unreachable server at discovery → connection excluded, other connections' tools still returned. Auth failure on invocation → `{"error": "..."}` tool-result, conversation continues. Tool-execution failure/timeout/malformed result → same `{"error": "..."}` shape. All network calls (discovery + invocation) bounded by `settings.mcp_request_timeout_seconds` (default matches the existing `llm_request_timeout_seconds` class of setting, §7).
- Data model: §3.5a. Migration: `0014_mcp_client` (§8). Fixture server for tests: `tests/fixtures/mcp_fixture_server.py` — `MCPServer(name="fixture")` with `@tool()`-decorated `echo(text: str) -> str` and `lookup(key: str) -> str` (fixed key→value map, `ValueError` on an unknown key — the SDK converts this to `CallToolResult(is_error=True, ...)` automatically, confirmed by direct execution against the installed SDK), served via `uvicorn.Server` on a test-local port started/stopped by a pytest fixture (`streamable_http_app()`'s session-manager task group requires a real ASGI lifespan — an `httpx.ASGITransport`-only harness was tried and found insufficient: `RuntimeError: Task group is not initialized. Make sure to use run().` — a real (if test-local) uvicorn server is the confirmed-working shape, not a guess). Never imported by the shipped app.

---

## 7. Configuration (`app/config.py`) — FR-CFG

`Settings(BaseSettings)` (`env_file=".env"`, case-insensitive, extra ignored). Key fields (default): `env`(dev) · `debug`(True) · `log_level`(INFO) · `log_json`(False) · `app_host/port`(0.0.0.0/8000) · `database_url`(postgres dsn; validator normalizes `postgres://`/`postgresql://`→`postgresql+psycopg://`) · pool tuning · `redis_url`(:6479/0) · `jwt_secret`(dev default; **FR-351** validators: reject placeholder markers any-env, reject in-code default in prod, min_length 32) · `jwt_algorithm`(HS256) · `jwt_access_token_ttl_minutes`(60) · `cookie_secure`(False)/`cookie_samesite`(lax)/`cookie_domain`("") · `bcrypt_rounds`(12) · mail_* · `system_use_notification`("") · `audit_retention_days`(365) · `llm_encryption_key`(hex; validator: 64 hex/32 bytes) · `llm_proxy_url`(:4000) · `llm_request_timeout_seconds`(30) · `mcp_request_timeout_seconds`(10, FR-MCPCLIENT-12) · `rate_limit_enabled`(False)/`rate_limit_requests`(240)/`rate_limit_window_seconds`(60) · `file_storage_dir`(./data/files)/`max_upload_bytes`(10 MiB) · `cors_origins`. Properties: `is_prod`, `is_test`, `cors_origins_list`.

---

## 8. Migrations (`migrations/versions/`) — FR-DB

`0001_users` · `0002_rbac` (roles/permissions/role_permissions/user_roles) · `0003_orgs` (organizations/memberships) · `0004_audit_logs` · `0005_example_notes` · `0006_ac7_lockout` (users lockout columns) · `0007_au11_archive_logs` (audit_logs_archive) · `0008_au9_audit_log_permissions` (REVOKE UPDATE/DELETE) · `0009_llm_keys` (llm_provider_keys, org_llm_access) · `0010_a4_files_notifications` (file_objects, notifications) · **`0011_mfa`** (adds `users.mfa_enabled/mfa_secret/mfa_enrolled_at`, creates `mfa_backup_codes` — this package only, IA-2(1)) · `0012_platform_health_and_fisma_audit` · `0013_greeting_slot` · **`0014_mcp_client`** (creates `mcp_server_connections` — FR-MCPCLIENT, §3.5a). Additive-only; each ships an `upgrade`+`downgrade`. Tests build schema via `Base.metadata.create_all`; production runs `alembic upgrade head`.

**Planned, not yet landed in this file (built in a subsequent phase of this same task):** System Health/Platform Health/FISMA-self-audit capability migrations (`012x` range) and the Greeting Service demo-slot tables — see `chassis-program-TASKS.md` CP-B.4/CP-B.5. This DESIGN.md will be amended again, spec-first, when those land.

---

## 9. FR → Design Traceability

| Requirement | Realization |
|---|---|
| FR-AUTH-* | `auth/` (§6.1), `users` table (§3.1), `deps.get_current_user` |
| FR-AUTH-15 (IA-2(1) MFA, this package only) | `auth/mfa.py` + `auth/mfa_crypto.py` (§6.13), `mfa_backup_codes` (§3.1a), `/auth/mfa/*` (§4.2), migration `0011_mfa` |
| FR-RBAC-* | `rbac/` (§6.2), permission registry, `deps.requires` |
| FR-TEN-* | `orgs/` + `db.py` tenancy listeners + `TenantScoped` (§6.3) |
| FR-AUD-* | `audit/` `@audited` + archival (§6.4), `audit_logs` |
| FR-ADM-* | `admin/routes.py` `_resolve` + admin templates (§4.6) |
| FR-OBS-* | `health/`, `logging.py`, request-id middleware, `admin/health_service` (§6.5) |
| FR-DOC-* | `admin/docs_service.py` + docs templates (§6.6) |
| FR-LLM-* | `llm/` crypto+service+transport + `/admin/llm` (§6.7) |
| FR-MCPCLIENT-* | `mcp/` models+service+client + `/admin/mcp` + `slots/greeting/providers/translation.py` tool-calling loop (§6.14) |
| FR-FILE-* | `files/` (§6.8) |
| FR-NOTE-* | `notifications/` (§6.9) |
| FR-RL-* | `ratelimit/middleware.py` (§6.10) |
| FR-REP-* | `admin/reports_service.py` (§6.11) |
| FR-MAIL/JOB/ERR-* | `mail/`, `tasks/`, `error_handlers.py`+`error_messages.py` (§6.12) |
| FR-UI-* | `frontend.py`, `templates/`, `static/`, USWDS (§4.7) |
| FR-EXT-* | extension markers (CONSTITUTION §6), `slots/example*` |
| FR-CFG-* | `config.py` (§7) |
| FR-RET-* | `RetainableFor` + archival (§3.8, §6.4) |
| FR-DB-* | `db.py`, `migrations/` (§8) |
| NFR-* | docs/NFR-BASELINES.md, docs/RESPONSIVE-DESIGN.md, docs/STATE-HANDLING.md, docs/SECURITY-SELF-AUDIT.md |

---

## CHANGELOG

### 1.2.1 — 2026-09-21

- `auth/service.py` description corrected: password hashing calls `bcrypt` directly via `auth/password_hashing.py` (not passlib), matching the shipped code (Task Log 2026-09-21-253, D12).

**v1.2.0 (2026-09-17)** — MINOR: §4.6 records where the table's existing `org-admin=members` constraint on user deactivate/reactivate is actually enforced, after the code was found to have diverged from it (cross-tenant privilege escalation, proven by execution; see `CHANGELOG.md` [1.1.1]).

### 1.1.0 — 2026-09-10
- Adds the MCP Client capability (FR-MCPCLIENT): §3.5a (`mcp_server_connections`), §4.6 (`/admin/mcp` endpoint catalog), §6.14 (mechanism design — SDK selection/verification, `mcp/` module shape, the tool-calling loop extension to `slots/greeting/providers/translation.py`, mandatory failure handling, the fixture test server), migration `0014_mcp_client`, and the FR-MCPCLIENT traceability row. Also corrects §8's migration list, which had `0012_platform_health_and_fisma_audit`/`0013_greeting_slot` marked "planned, not yet landed" even though both were already implemented — a pre-existing drift fixed in passing while amending this same section. Realizes `specs/chassis-program/shared-capabilities/MCP-CLIENT-REQUIREMENTS.md` per `chassis-program-DESIGN.md` §6, operator-approved per `MCP-PROTOCOL-OPTIONS-ANALYSIS.md` §5. Task Log: `specs/platform/Task Logs/2026-09-10-003-mcp-client-support.md`.

### 1.0.0 — 2026-09-02
- Initial DESIGN for this package, forked from `chassis/python-fastapi` DESIGN v1.0.1. Adds §3.1a (`mfa_backup_codes`), the `/auth/mfa/*` endpoint catalog (§4.2), §6.13 (MFA/TOTP mechanism design — enrollment, two-step login, backup codes, the platform-wide-privilege-only gate), migration `0011_mfa`, and the FR-AUTH-15 traceability row. System Health / Platform Health / FISMA-self-audit-report design sections are added in a subsequent amendment within this same Phase B build (CP-B.4), spec-first, once those capabilities are implemented.

### Prior history (inherited from the reference chassis, retained for context)

### 1.0.1 — 2026-06-25
- Clarified §4.1 (`/version`) and §6.5 (System Health) that the `chassis` / `chassis_version` field is sourced from the `CHASSIS_VERSION` file (`app.__chassis_version__`) and is distinct from the app package `version` (`app.__version__`). Documents the bug fix where both fields previously reported the app version.

### 1.0.0 — 2026-06-22
- Initial DESIGN for the python-fastapi chassis at v0.10.0: architecture overview, module layout, all 11 tables, full endpoint catalog, request lifecycle/middleware order, per-capability mechanism designs, configuration catalog, migration list, and FR→design traceability.
