# Accessibility Assistant — Constitution

**Specification Version:** 1.6.0
**Generated:** 2026-09-25 16:46 EDT
**Approved By:** Joe Paiva, Alignment Authority

**Chassis:** Python — Multi-Tenant, FISMA Moderate + LLM (Chassis Program) v1.3.3
**Status:** Immutable — chassis-locked. Read-only in the Spec Builder.

The sections below are defined by the chassis and ship as the immutable foundation for this project. They cannot be modified during specification. Any deviation from these defaults MUST be expressed as a custom requirement in `REQUIREMENTS.md` with the `(CHASSIS-OVERRIDE)` annotation; the build engine recognizes the marker and deviates from the chassis baseline accordingly.

Customer-specific business logic, data models, workflows, and UI/UX choices live in `REQUIREMENTS.md`, `DESIGN.md`, `TASKS.md`, and `TEST-SCENARIOS.md` — NOT here.

---

### Foundation Overview
This application is built on the **Python/FastAPI chassis** (a Chassis Program package; its version is the package's `CHASSIS_VERSION`): a pre-built, security-hardened, multi-tenant application foundation. Identity, access control, tenancy, audit, an administration shell, observability, and a set of cross-cutting capabilities are provided by the foundation; application authors add only domain logic.

**How to read this Constitution (it serves two audiences):**
- **Generating on the chassis (AI/App Builder):** the foundation is already implemented. Treat the rules below as binding and integrate domain code only at the documented extension points; do not re-implement the foundation.
- **Building without the chassis (human developer):** each section states the *intent* and the *concrete rules, data shapes, thresholds, and algorithms* needed to implement the same capability from scratch in any comparable stack. Where a section references a chassis symbol (e.g. `app/deps.py`), that names *the chassis realization*; the surrounding prose states the underlying requirement so it can be reproduced independently.

This foundation is **immutable** within a project: its rules cannot be edited during specification. A genuine, deliberate deviation MUST be expressed as a custom requirement in `REQUIREMENTS.md` annotated `(CHASSIS-OVERRIDE)`, stating the new behavior and its enforcement; the build engine recognizes the marker and deviates accordingly.

---

### Technology Stack
**Intent.** A single, locked, modern stack so every generated application is consistent, secure-by-default, and maintainable. A human developer rebuilding this without the chassis MAY substitute equivalent technologies, but MUST preserve the *properties* each choice provides (async I/O, typed ORM, validated settings, server-rendered accessible UI, single LLM egress).

**How this application implements it (locked stack).**
- **Language/runtime:** Python 3.12 (`>=3.12,<3.13`); dependency manager **uv**.
- **Web framework:** FastAPI 0.141.x on Uvicorn (ASGI).
- **ORM:** SQLAlchemy 2.0 async (`Mapped[...]` + `mapped_column`, `AsyncSession`); migrations via Alembic.
- **Datastore/cache:** PostgreSQL (async psycopg3) as the single relational store; Redis for the job queue and rate-limit counters.
- **Validation/settings:** Pydantic v2 (`model_config = ConfigDict(...)`); `pydantic-settings.BaseSettings` for config.
- **Auth primitives:** JWT (HS256) via PyJWT; password hashing via `bcrypt` 5.0.0 called directly (`app/auth/password_hashing.py`); TOTP MFA via `pyotp`. **`python-jose` and `passlib` are forbidden** (removed for open CVEs / a bcrypt version cap).
- **Frontend:** server-rendered Jinja2 + USWDS 3.x (U.S. Web Design System); no SPA framework, no bundler, no transpile in the serve path.
- **Logging/metrics:** structlog (JSON in prod); prometheus-fastapi-instrumentator. **Jobs:** RQ on Redis. **Mail:** fastapi-mail. **Crypto:** `cryptography` (AES-256-GCM).

Exact version pins and the full dependency table are in the chassis CONSTITUTION (`chassis/python-fastapi/specs/CONSTITUTION.md` §1). **No dependency outside that list may be used in application/slot code** — the App Builder treats anything else as a forbidden import.

**Building with the chassis.** The stack is fixed; do not change framework, ORM, validation library, or add dependencies. If a domain genuinely needs a new library, capture it as a `(CHASSIS-OVERRIDE)` requirement for review.

---

### Architectural Invariants
**Intent.** A small set of non-negotiable structural rules that keep every application correct, secure, and testable. A human developer MUST uphold these regardless of stack.

**How this application implements it (binding invariants).**
1. **Async-only.** Every I/O path uses async/await; the data layer is async (no synchronous DB sessions/engines in request or service code).
2. **Typed, validated models.** ORM models use the typed form; request/response bodies and settings are validated schemas — no untyped dicts crossing boundaries.
3. **One concern per module.** Each concern lives in its own module set (`models`, `schemas`, `service`, `routes`). **Services hold business logic and contain no HTTP/framework imports; routes are thin** and call services.
4. **Multi-tenancy is automatic** (see Multi-Tenancy): tenant reads are auto-filtered and writes auto-stamped by the bound organization; application code never hand-filters by org for normal access.
5. **Audit is declarative** (see Audit): privileged mutations are wrapped by one annotation, not audited ad-hoc per call site.
6. **Server-side enforcement only.** All auth, validation, and access control happen server-side; client state is never trusted.
7. **Single LLM egress.** All model calls route through one provider-neutral endpoint; no provider SDK is imported directly.
8. **Secrets live outside source.** Signing/wrapping keys come from the environment; provider API keys live encrypted in the datastore; nothing secret is committed.
9. **Additive-only migrations.** Migrations are append-only and never edited after commit; schema-sync is for tests only, production uses ordered migrations.
10. **Per-request transaction.** The request-scoped DB session commits on success and rolls back on exception.
11. **Extension points are the only edit surface.** Domain code integrates only at the marked extension points (see Extension Model); no other foundation file is edited.

**Building with the chassis.** These are already enforced by the foundation (async sessions, `TenantScoped` mixin + event listeners, `@audited`, additive Alembic migrations, per-request session). Slot code that violates them (e.g. a sync DB call, a hand-rolled org filter) is rejected by the build-time gates.

---

### Security Invariants (binding)
**Intent.** A FISMA-Moderate-aligned security baseline every application inherits, stated concretely so it can be verified or reproduced. These are not optional.

**How this application implements it (concrete rules + thresholds).**
- **Password complexity (IA-5):** at registration, secrets MUST be ≥ 14 characters with ≥ 4 character classes (upper, lower, digit, special); violations are rejected naming what's missing. Enforced at registration, not login.
- **Secret storage (SC-13):** passwords stored with an adaptive salted one-way hash (bcrypt, cost ≥ 12, configurable). Plaintext is never stored or logged.
- **Sessions:** signed JWT (HS256), default 60-minute TTL; browser cookie is `HttpOnly`, `Secure` in production, `SameSite=lax`; token accepted from the `Authorization: Bearer` header or the cookie (header preferred).
- **Account lockout (AC-7):** 3 failed attempts within a 15-minute window → 30-minute lock; while locked, authentication is refused **before** the password is verified.
- **Anti-enumeration (IA-6):** unknown identifier, inactive account, wrong secret, and locked account all return an **identical** failure — never revealing which.
- **Active-state (AC-2):** users have an explicit active/inactive flag; inactive users cannot authenticate.
- **Audit content + immutability (AU-3/AU-9):** every privileged mutation records actor + org + client IP + action + entity + details + UTC timestamp; the application runtime DB role is denied UPDATE/DELETE on the audit table (append-only, migration-enforced).
- **Tenant isolation:** a resource that exists but belongs to another tenant is indistinguishable from "not found".
- **Error handling (SI-11):** production responses are generic + a correlation id; full detail is logged internally only.
- **Secret hardening (SC-12):** the session-signing secret rejects placeholder values in any environment and refuses to boot in production with the in-code default (min length 32); the LLM wrapping key fails closed at use time if left default.
- **Rate limiting (SC-5):** available, opt-in, fail-open.

**Building with the chassis.** All of the above ship in the foundation (`app/auth`, `app/deps.py`, `app/audit`, migrations). Slot code MUST NOT weaken them; per-route overrides MUST be annotated `(CHASSIS-OVERRIDE)` with the control id and the replacement enforcement path. The full control-by-control posture is in the chassis `docs/SECURITY-SELF-AUDIT.md`.

**Chassis Program addendum — this package is Multi-Tenant, FISMA Moderate + LLM (variant 3 of 5).**
- **MFA (IA-2(1)) is mandatory, not optional, and is chassis-core.** TOTP-based multi-factor authentication (enrollment, backup codes, two-step login, self-service disable, admin reset) is built into the foundation auth service and enforced for platform-wide privileged accounts and for slot code that opts into the privileged gate (see Authentication below). This supersedes the shared chassis's "documented extension point, not yet built" MFA language — in this package it is real.
- **Zero-CVE / latest-stable (SI-2, SI-3) is a release gate, not an operator responsibility.** Every embedded dependency is held at its latest stable release with zero open, unpatched CVEs, verified by CI before any version tag and re-verified continuously at runtime by the Platform Health capability (`specs/chassis-program/shared-capabilities/PLATFORM-HEALTH-REQUIREMENTS.md`). Full baseline: `FISMA-CONTROL-DELTA-LOW-VS-MODERATE.md` §6.
- **Live FISMA self-audit.** In addition to this static Constitution text, the running application exposes an on-demand, admin-only FISMA Controls self-audit and report that checks these controls against ACTUAL runtime state (is MFA actually enforced, is the dependency inventory actually clean, is the lockout threshold actually 3/15min/30min) — not against documentation. A passing report is a self-assessment, not an independent audit or an ATO.

---

### Coding Standards
**Intent.** Uniform, statically-verifiable code so generated and hand-written code read alike and stay maintainable.

**How this application implements it.**
- **Naming:** `PascalCase` types, `snake_case` functions/modules/columns, `UPPER_SNAKE` constants.
- **Typing:** application/slot code is strictly typed (`mypy --strict`: no untyped defs, no implicit `Any` generics).
- **Linting/formatting:** `ruff` (rule sets E,F,W,I,B,UP,ASYNC,SIM), line length 100, target py312.
- **Logging:** structured logger with contextual event names (e.g. `auth.login.success`); never `print`; the request correlation id is auto-bound.
- **Errors:** raise typed HTTP errors with messages from the canonical catalog (see Standard Error Messages); never leak internals to clients.
- **Validation:** every request body is a validated schema with binding constraints.
- **Tests:** each capability covers happy-path, auth gate (401), permission gate (403), cross-tenant isolation (404), and validation (422).

**Building with the chassis.** The foundation ships the `mypy`/`ruff` config and the test conventions; slot code is held to them by the build-time quality gates.

---

### Authentication
**Intent.** Let an anonymous visitor register and an existing user log in, then carry that identity on every subsequent request via a stateless, signed, expiring token — securely, and resistant to brute-force and account-enumeration attacks.

**How this application implements it (reproducible without the chassis).**
- **Register:** unique email + password (+ optional display name). Password is validated for complexity (≥14 chars, ≥4 character classes), then stored as a bcrypt hash (cost ≥12); registration establishes a session on success.
- **Login:** email + password; on success issue a signed JWT (HS256) carrying the subject id and an expiry (default 60 min). The token is returned in the JSON body AND set as an `HttpOnly` cookie (`Secure` in prod, `SameSite=lax`).
- **Session resolution:** each request resolves the current user from the `Authorization: Bearer` header OR the cookie (header preferred); the token is verified by signature + expiry with **no DB lookup**.
- **Profile / logout:** the authenticated user can fetch their own profile; logout clears the cookie (the JWT remains technically valid until `exp` — revocation lists are a future feature).
- **Hardening:** inactive users and unknown emails return the **same** 401 as a wrong password or a locked account (anti-enumeration, IA-6); after 3 failures in 15 minutes the account locks for 30 minutes and is refused **before** the password is checked (AC-7); inactive users cannot authenticate (AC-2).

**Building with the chassis.** Authentication is implemented in `app/auth` (`service.py`, `routes.py`, `models.py`). Slot code MUST obtain the authenticated user via `from app.deps import CurrentUser` (a FastAPI dependency) and MUST NOT call `app.auth.service` or re-implement token/password handling. Additional providers (SSO/OAuth) attach at the auth-providers extension point — chassis auth code is not edited.

**Chassis Program addendum — real TOTP MFA.** This package builds actual multi-factor authentication into the foundation auth service (not a documented-but-unbuilt extension point): TOTP enrollment (secret + QR provisioning), 10 single-use backup codes, a two-step login flow (password → MFA challenge token → code verification), self-service disable/regeneration, and an admin reset path. Secrets are stored AES-256-GCM encrypted, matching the existing LLM-provider-key encryption pattern. MFA is mandatory (`requires()` enforces it) for platform-wide privileged accounts per FISMA-Moderate's IA-2(1); slot code MAY additionally gate its own privileged routes on `user.mfa_enabled` (the Greeting Service demo's paginated-history endpoint does exactly this).

---

### Role-Based Access Control
**Intent.** Govern every action by named permissions grouped into roles, enforced server-side, extensible by domain code without schema changes.

**How this application implements it (reproducible without the chassis).**
- **Permissions** are `resource:action` strings (e.g. `users:read`, `orgs:write`). **Roles** group permissions; users hold roles; roles grant permissions.
- **Two seeded roles** ship: `admin` (all permissions) and `user` (read-only on the foundation's read permissions). A **superuser** flag short-circuits all checks to granted.
- **Dual grant paths:** a role may be held **system-wide** OR **per-organization** (via membership). A permission check passes if **either** path grants it (when an org context is bound).
- **Idempotent seeding:** all foundation permissions/roles are (re)seeded in code at startup, so a fresh DB and an upgraded DB converge with no manual steps.
- **Declarative gate:** a single reusable route guard returns 403 when the caller lacks a named permission; all decisions are server-side.
- **Extensible registry:** domain code registers new permissions that auto-seed on next startup — **no migration needed to add a permission**.

**Building with the chassis.** RBAC lives in `app/rbac` (`permissions.py`, `models.py`). Slot routes gate writes with `dependencies=[Depends(requires("<resource>:write"))]` and reads with the analogous `:read` permission; `requires(...)` is the chassis gate factory and `user_has_permission` consults both `user_roles` and per-org `memberships.role_id`. New slot permissions are registered at the slot-permissions extension point via `register("<resource>:<action>", "<description>")`.

---

### Multi-Tenancy
**Intent.** Every application is multi-tenant by default: data belongs to exactly one organization, and cross-tenant leakage must be structurally impossible — not dependent on each developer remembering to filter by tenant.

**How this application implements it (reproducible without the chassis).**
- **Organizations** (tenants) have a name + unique URL-safe slug. A user may belong to zero or more orgs via **memberships** (each with an optional per-org role and a default-context flag).
- **Current org** is resolved deterministically per request (explicit default first, else earliest membership); a user with no org receives a clear client error.
- **Isolation invariant:** every tenant-scoped row carries an `org_id`. Reads are **automatically filtered** to the current org and writes **automatically stamped** with it, centrally — so domain code cannot accidentally read or write across tenants.
- **Cross-tenant policy:** a resource that exists but belongs to another org is returned as **"not found"** (never confirming existence).
- **Escape hatch:** an explicit, audited mechanism exists for legitimate cross-tenant work (admin, background jobs) — never the default.

*A human implementing this without the chassis* would centralize tenant filtering/stamping in the data layer (e.g. a query interceptor + an insert hook bound to a request-scoped "current org" context var), not sprinkle `WHERE org_id = ?` through handlers.

**Building with the chassis.** Tenant-owned models MUST inherit `(Base, TenantScoped)` (`app/db.py`). A SQLAlchemy `do_orm_execute` hook + `with_loader_criteria` auto-injects `WHERE org_id = <current>` on SELECT; a `before_flush` listener auto-populates `org_id` on INSERT; `current_org` (`app/deps.py`) binds the context per request. Slot code MUST NOT hand-filter by `org_id` for normal reads, and MUST NOT set `obj.org_id` manually (both are automatic).

---

### Audit Log
**Intent.** Every privileged state change is accountable and tamper-evident, via one declarative mechanism so audit can never be forgotten per call site.

**How this application implements it (reproducible without the chassis).**
- **Append-only** audit store: NEVER UPDATE, NEVER DELETE. The application's own DB role is denied UPDATE/DELETE on the table (migration-enforced, AU-9).
- **One declarative wrapper** decorates state-mutating service methods; on **successful** return it writes exactly one record. On exception, no record is written (an audit row implies the action happened).
- **Record content (AU-3):** action name, acting user id (nullable for system actions), org context (nullable for cross-tenant/system), optional entity type + id, a structured details payload, the client IP, and a UTC timestamp.
- **Degradation:** a missing session/context at an audit site logs a warning and skips the audit — it never breaks the underlying operation.
- **Reads are NOT audited** (signal-to-noise). A dedicated permission authorizes reading the audit log; a retention job archives records older than a configurable window (default 365 days).

**Building with the chassis.** Audit lives in `app/audit`. Slot service-layer functions that mutate state MUST be decorated with `@audited(action, entity_type, capture_details=...)`; actor/org/IP are sourced from context vars automatically. Do not write audit rows by hand and do not audit reads.

---

### Observability & Health
**Intent.** Operators can tell whether the app is alive, ready to serve, and what version is running; every log line is correlatable to a single request.

**How this application implements it (reproducible without the chassis).**
- **Liveness** endpoint: returns success whenever the process serves requests, with no dependency checks.
- **Readiness** endpoint: checks downstream dependencies (at minimum the datastore) and returns failure when any is unreachable, so an orchestrator routes traffic away.
- **Version** endpoint: reports the application version and the foundation version it was built against.
- **Request correlation:** every request is stamped with a correlation id (honoring a client-supplied one), returned in a response header AND bound to every log line for that request.
- **Structured logging:** machine-parseable in production, human-readable in development; correlation id (and user/org when bound) auto-included.
- **System Health page** (admin-only): shows app + foundation version, environment, and live reachability of each dependency; each check is best-effort with a bounded timeout (a down dependency renders as a status, never an error page); any connection string is shown with credentials redacted.

**Building with the chassis.** Endpoints are `/healthz` (liveness), `/readyz` (DB ping → 503 on failure), `/version`; `/docs` + `/redoc` are auto-generated. structlog + a request-id middleware (`X-Request-ID`, UUID4) are provided. Slot code MUST obtain a logger via `from app.logging import get_logger`; it MUST NOT call `print()` or use the stdlib `logging` module directly.

**Chassis Program addendum — System Health and Platform Health.** Beyond the shared chassis's basic health route, this package adds two admin-only capabilities: **System Health** (`FR-SYSHEALTH`) — DB/cache/worker/LLM-proxy status at a glance, with a slot extension point for additional checks — and **Platform Health** (`FR-PLATHEALTH`) — an on-demand and daily-scheduled component inventory, currency report, vulnerability scan, and gated remediation flow scoped to this package's own dependency tree, which also serves as the runtime enforcement arm of the zero-CVE mandate above. Full specs: `specs/chassis-program/shared-capabilities/{SYSTEM-HEALTH,PLATFORM-HEALTH}-REQUIREMENTS.md`.

---

### Frontend Responsive Design
**Intent.** The UI is server-rendered, mobile-first, and accessible (Section 508 / WCAG 2.1 AA) — no SPA framework, no bundler, no transpile in the serve path. The rules below are the concrete contract; a human developer can reproduce them on any server-rendered, accessible UI stack.

**How this application implements it (and how slot templates must conform):**

- `<meta name="viewport" content="width=device-width, initial-scale=1">` in every page via `base.html`.
- USWDS 3.7 grid: mobile-first breakpoints at 480 / 640 / 880 / 1024 / 1200 / 1400 px.
- Minimum 44 × 44 px touch targets on all interactive components (WCAG 2.1 SC 2.5.5).
- `<usa-header>` collapses to a hamburger menu automatically at < 640 px.
- Form inputs ship at 16 px font-size on mobile (prevents iOS Safari auto-zoom).
- Body text scales fluidly via USWDS typography tokens.

LLM-generated slot templates MUST extend `base.html` and use USWDS grid classes (`grid-row`, `grid-col-12 tablet:grid-col-6 desktop:grid-col-4`, etc.) for multi-column layouts. Slot code MUST NOT override the viewport meta, build custom hamburger nav, shrink touch targets below 44 px on mobile, or force font-size below 16 px on form inputs. Documented exceptions must be annotated with `# CHASSIS-OVERRIDE: responsive-design` + reference to the FR-ID; the chassis CI gate (`tests/test_responsive.py`) enforces this.

See `docs/RESPONSIVE-DESIGN.md` for the full policy + test viewport matrix.

---

### Standard Error Messages
**Intent.** Every user-facing error is consistent, blame-free, jargon-free, and screen-reader-friendly, drawn from one canonical catalog rather than ad-hoc per-route strings. In production, internal detail is never leaked (generic message + correlation id; full error logged internally only). A human developer reproduces this with a single keyed message catalog + a production error handler.

**How this application implements it (and how slot code must conform):**

- `app/error_messages.py` defines canonical, plain-English, screen-reader-friendly user-facing strings for HTTP 400, 401, 403, 404, 409, 410, 413, 415, 422, 423, 429, 500, 501, 502, 503, 504.
- `app/error_handlers.py` (prod 500 handler) reads from this table.
- `app/deps.py` raises HTTPException with these canonical strings on auth (401), permission (403), and orgless (400) failures.
- Tone: first-person plural ("We couldn't…"), no technical jargon (no "token" / "JWT" / "401"), screen-reader-friendly (≤ 80 chars, ends in period).
- Triage context: when slot code needs to differentiate failure modes (e.g., token-expired vs invalid), bind the specific reason on the structlog log line — the USER-facing string stays canonical.

LLM-generated slot code MUST use `from app.error_messages import message_for_status, ERR_FORBIDDEN` (etc.) when raising HTTPException, rather than inlining custom strings. Documented per-route overrides MUST be annotated with `# CHASSIS-OVERRIDE: error-messages` + reference to the FR-ID for traceability.

See `app/error_messages.py` for the full canonical table.

---

### Page State Handling (Loading / Empty / Error)
**Intent.** Every data-driven page handles its loading, empty, and error states consistently and accessibly, so users are never left staring at a blank screen or a raw exception. A human developer reproduces this with three reusable, ARIA-correct state components.

**How this application implements it (and how slot code must conform):**

- `app/templates/components/_states.html` ships three reusable Jinja macros: `state_loading()`, `state_empty(message, cta_url, cta_label)`, `state_error(message, retry_url, retry_label)`.
- Loading: USWDS plaintext indicator with `role="status"` + `aria-live="polite"` so screen readers announce without interrupting the user's focus. Pair with `hx-indicator` for HTMX-driven fragments.
- Empty: `usa-alert--info` variant (no-icon) with an optional single-action CTA slot. Empty is not an error — DO NOT use the error variant for empty states.
- Error: `usa-alert--error` variant with `role="alert"` so assistive tech interrupts the user. Recovery path required (retry button or known-safe navigation link). Message strings MUST come from `app/error_messages.py` (`message_for_status(status_code)`) — never display raw exceptions, stack traces, or internal IDs.

LLM-generated slot code MUST use the chassis macros instead of hand-rolling state HTML. Slot code MUST NOT inline its own user-facing 4xx / 5xx wording — read from `message_for_status` instead. Documented per-page overrides (e.g., a long-running report page that needs a progress bar) MUST be annotated with `# CHASSIS-OVERRIDE: state-handling` + reference to the FR-ID for traceability.

See `docs/STATE-HANDLING.md` for the full policy + USWDS class contract.

---

### NFR Baselines (Page Load / API Response / Availability / Concurrent Users / Data Integrity)
**Intent.** The application inherits proven non-functional baselines so these targets are met by construction and need not be re-elicited per project. The numbers below are the contract; a human developer treats them as the performance/availability/integrity budget to design against.

**How this application implements it (baselines + enforcement paths):**

- **Page Load:** ≤ 2.5 s p95 on 3G Slow (Lighthouse mobile profile); ≤ 1.0 s p95 on broadband. USWDS 3.7 CDN + HTMX-only fragment swaps make this the no-cost default.
- **API Response:** ≤ 250 ms p95 for reads (GET); ≤ 800 ms p95 for writes (POST/PUT/DELETE). SQLAlchemy 2.0 async + `@audited` decorator overhead measured at this threshold.
- **Availability:** 99.5 % monthly on a single-region Azure Container Apps deploy (per-deploy-target override expected). `/readyz` DB-ping gate + additive-only migrations enable zero-downtime deploys.
- **Concurrent Users:** 100 concurrent active sessions per single Azure Container Apps instance (gunicorn 4 workers × 2 threads + async I/O). Horizontal scale via `az containerapp update --max-replicas N`.
- **Data Integrity:** SQLAlchemy transactional boundary on every `@audited` service method (commit on success, rollback on exception). Nightly `pg_dump` retention 30 days. AU-9 DB-level REVOKE prevents app code from mutating `audit_logs` rows.

LLM-generated slot code MUST NOT capture FRs for these five baselines unless overriding. The chassis ships them; the spec stays silent; the build engine generates code that meets the baseline by construction. Overrides MUST be annotated `(CHASSIS-OVERRIDE)` in the FR and MUST state the override's measurement + enforcement path. Override marker: `# CHASSIS-OVERRIDE: nfr-<topic>`.

See `docs/NFR-BASELINES.md` for the full policy + enforcement paths per baseline.

---

### Forbidden Patterns (statically enforced)
**Intent.** Generated and hand-written application code must use the modern, async, secure idioms of the stack — legacy/deprecated patterns are rejected before they reach the codebase.

**How this application implements it.** The following are statically forbidden in application/slot code (rejected by `mypy --strict`, `ruff` `UP` rules, and a post-generation AST scan):
- Pydantic v1: `@validator(`, `class Config:`, `Field(env=`, `BaseSettings` imported from `pydantic` → use `@field_validator`, `model_config = ConfigDict(...)`, `pydantic_settings.BaseSettings`.
- Legacy typing: `Optional[...]`, `from typing import List|Dict` → use `X | None` and builtin generics.
- SQLAlchemy 1.4 / sync: `session.query(`, `create_engine(`, `sessionmaker`, sync `session.commit()` → use `select(...).where(...)`, `create_async_engine`, `async_sessionmaker`, `await session.commit()`.
- `from passlib.context import CryptContext`, `from jose import ...` → forbidden (`passlib`/`python-jose` are removed); use the foundation's `app/auth/password_hashing.py` and PyJWT.
- Naive time: `datetime.utcnow(` / `datetime.now()` → `datetime.now(UTC)`.
- `sqlmodel` / `import sqlmodel` / `from sqlmodel` → not a dependency; use SQLAlchemy 2.0 + Pydantic v2.

**Building with the chassis.** These map to the chassis CONSTITUTION §5 forbidden list and are enforced by the App Builder's quality gate on `app/slots/*`. A human developer without the chassis should treat this list as the project's lint policy.

---

### Extension Model & Ownership Boundary
**Intent.** Domain code is added as isolated, additive registrations — never by editing the hardened foundation — so the security/tenancy/audit guarantees can never be accidentally broken, and the foundation can be upgraded independently.

**How this application implements it (reproducible without the chassis).** Application-specific code lives in **slots** (`app/slots/<domain>/` with its own `models`, `schemas`, `service`, `routes`, `tests`). A slot integrates only at a small set of **marked extension points**:
- **Routes:** register one router per slot (`app/main.py` slot-routers marker).
- **Permissions:** register `"<resource>:<action>"` per slot permission (`app/rbac/permissions.py` marker).
- **Auth providers:** add SSO/OAuth providers (`app/auth/providers/__init__.py` marker).
- **Admin pages:** add slot admin pages under the same authorization model (`app/admin/routes.py` marker).
- **Migrations:** add new additive migrations for slot tables.

Everything else under `app/` (auth, rbac, orgs, audit, health, mail, tasks, llm, files, notifications, ratelimit, admin, db/config/deps/logging/error handling, chassis templates + static) is **foundation-owned** and is not edited; only `app/slots/<domain>/` is slot-owned.

**Building with the chassis.** These markers are the ONLY foundation lines a slot author touches. A human developer without the chassis should preserve the same boundary: a stable, audited core + an additive plugin surface for domain features.

**Extending the technology stack (application dependencies).** The **Application Dependencies** section below is application-owned and editable. Every entry in it MUST satisfy all six of the following. These rules are part of this foundation-owned section and are not editable.
1. **Additions only.** An entry may not replace, shadow, override a pin of, or downgrade anything in the Technology Stack section.
2. **No second implementation of a foundation concern.** No second ORM, web framework, router, auth or session library, password-hashing or crypto provider, migration tool, or HTTP client used to reach a model. Where the foundation already owns the concern, its implementation is the one.
3. **Exact pins.** A floating version, or a version absent from the lockfile, is not a valid entry.
4. **The same vulnerability and currency obligation as the foundation's own pins.** An application library is in scope for the same scans and the same remediation SLA, so that a locally-added library cannot become the weakest point in this application's compliance posture.
5. **No new egress.** A library that opens a network path the foundation does not already open is not an application dependency; it is an architecture change and requires a foundation amendment.
6. **Approval per addition**, recorded in the table with the approver and the date.

An entry that cannot satisfy all six is not an extension. It is either a foundation amendment, or it does not happen.

---

### Application Dependencies
**Intent.** Libraries this application needs that the foundation does not provide — PDF generation, spreadsheet export, a domain-specific format. This is the ONLY part of the technology stack the application may extend; the foundation's own pins are immutable and live in the Technology Stack section above.

**This table is yours to fill in.** It starts empty. Adding a row is an *extension*, not a foundation amendment: it does not change or re-version the foundation. The rules governing what may be added are in the **Extension Model** section, which is foundation-owned and not editable — deliberately, so the rules cannot be edited out by the application they bind.

| Library | Exact version | What it is for | Approved by | Date |
|---|---|---|---|---|
| _(none yet)_ | | | | |

**Pinning.** Declared in `pyproject.toml` `[project.dependencies]` with an exact `==` pin, and present in the committed `uv.lock`. A dependency absent from the lockfile is not pinned, whatever `pyproject.toml` says.

**Reproducible without the foundation.** A human developer should read this as: the platform's own dependency set is fixed and audited; application libraries are declared explicitly, pinned exactly, scanned on the same schedule, and approved individually — not added ad hoc to a manifest.

---

*Assembled by SpecDocumentMaterializer (FR-281) from Python — Multi-Tenant, FISMA Moderate + LLM (Chassis Program) v1.3.3 baseline content. The chassis baselines are the source of truth; this document is a derived snapshot.*
