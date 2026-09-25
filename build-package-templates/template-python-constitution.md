---
template: python-constitution
version: "3.0"
document_type: CONSTITUTION.md
locked_section_aware: true
---

# {{PROJECT_NAME}} — Constitution
<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## Platform Chassis — AI-Executable Constitution (Python 3.12 · FastAPI · SQLAlchemy 2.0 async)

**Project:** {{PROJECT_NAME}}
**Foundation:** autonomous-platform-chassis-python (FastAPI 0.115 · SQLAlchemy 2.0 async · Alembic · psycopg3/PostgreSQL · Redis · Jinja2 + USWDS)
**Generated Date:** {{DATE}}
**Status:** Immutable per project (rarely changes)

**Purpose.** This document fixes the *non-negotiable* architectural, technical, security, and behavioral constraints for {{PROJECT_NAME}}. Any AI model — or human developer — generating design, tasks, tests, or code **MUST** comply. No requirement, design choice, task, or code may override this Constitution. Where any other project document conflicts with this Constitution, **this document wins**.

This document serves two readers at once:
- **AI / App Builder (with the chassis):** the rules below are binding constraints on every generated artifact. The Platform-Provided Foundation is already implemented by the chassis; build only on top of it, at the documented extension points.
- **Human developer (without the chassis):** the rules below define the stack, invariants, and security baseline you must reproduce if you build this application outside the platform. They are sufficient, together with REQUIREMENTS/DESIGN, to build a compliant application from scratch.

---

<!-- @owned-by:  | @role: tech | @system-derives-from:  | @locked-by-chassis: true -->
## 1. IMMUTABLE TECHNOLOGY STACK (NON-NEGOTIABLE)

The following are **locked**. Changing any of them is a new major chassis version, not an edit. The App Builder treats anything outside this list as a forbidden dependency in slot code.

### 1.1 Language & runtime
- **Python 3.12** (`>=3.12,<3.13`). Toolchain/dependency manager: **uv**. `pyproject.toml` + `uv.lock` are the single source of dependency truth.

### 1.2 Core dependencies (exact pins — locked families)
| Concern | Package | Version |
|---|---|---|
| Web framework | `fastapi` | 0.115.6 |
| ASGI server | `uvicorn[standard]` | 0.32.1 |
| ORM (async) | `sqlalchemy[asyncio]` | 2.0.36 |
| Migrations | `alembic` | 1.14.0 |
| DB driver | `psycopg[binary,pool]` | 3.2.3 |
| Validation | `pydantic` | 2.10.4 |
| Settings | `pydantic-settings` | 2.7.0 |
| Tokens (JWT) | `pyjwt` | 2.13.0 |
| Password hashing | `bcrypt` | 5.0.0 (called directly via `app/auth/password_hashing.py` — no `passlib` layer) |
| MCP client | `mcp` | 2.2.0 (client role only) |
| Structured logging | `structlog` | 24.4.0 |
| Metrics | `prometheus-fastapi-instrumentator` | 7.0.2 |
| Background jobs | `rq` | 2.0.0 |
| Redis client | `redis` | 5.2.1 |
| Templates | `jinja2` | 3.1.4 |
| Form parsing | `python-multipart` | 0.0.20 |
| Transactional email | `fastapi-mail` | 1.4.2 |
| Crypto (AES-256-GCM, TLS) | `cryptography` | >=48.0.0 |

**Dev-only:** `pytest` 8.3.4, `pytest-asyncio` 0.24.0, `pytest-cov` 6.0.0, `httpx` 0.28.1, `factory-boy` 3.3.1, `mypy` 1.13.0, `ruff` 0.8.4, `pre-commit` 4.0.1.

**No dependency may be added without amending this section.**

### 1.3 Datastore & cache
- **PostgreSQL** as the single relational datastore (async via `psycopg3`). **Redis** for the background job queue (`rq`) and rate-limit counters. No second relational store.

### 1.4 Frontend
- **Server-rendered Jinja2 templates + vendored USWDS 3.x** (U.S. Web Design System), themed via a single hand-authored override stylesheet of USWDS design tokens. **No** SPA framework (React/Vue/Angular), **no** bundler (webpack/vite), **no** Sass/transpile step in the serve path. USWDS's progressive-enhancement script is permitted as a vendored/CDN asset; app interactivity stays vanilla JavaScript. **Section 508 / WCAG 2.1 AA** is mandatory.

### 1.5 LLM egress
- **All** model calls route through a single OpenAI-compatible endpoint (LiteLLM proxy) via `httpx.AsyncClient`. No provider SDK (Anthropic/OpenAI/Gemini) may be imported directly. Provider API keys live AES-256-GCM-encrypted in the datastore and are injected per request.

---

<!-- @owned-by:  | @role: tech | @system-derives-from:  | @locked-by-chassis: true -->
## 2. SUPPORTED APPLICATION MODES

Every project **MUST** declare one (or both) modes in `REQUIREMENTS.md`:

### 2.1 Standalone Full-Stack Mode
- The application owns business logic, data persistence (SQLAlchemy 2.0 async / PostgreSQL), and transactions. The database is authoritative. External services are optional.

### 2.2 Service-Integrated Mode
- The application acts as front-end / API façade / middleware. Core business logic MAY reside in external authoritative systems (enterprise APIs, analytics platforms, SaaS). The application MUST NOT duplicate externally-owned logic; it owns orchestration, validation, and presentation only.

Projects MAY use **hybrid mode** (both 2.1 and 2.2).

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## 3. LOGIC OWNERSHIP RULES (CRITICAL)

All business logic **MUST** be classified as exactly one of:

### 3.1 Application-Owned Logic
- Implemented in Python slot services under `app/slots/<domain>/`, executing in the app runtime against PostgreSQL via SQLAlchemy 2.0 async. Examples: request orchestration, input validation, domain workflows, lightweight aggregations.

### 3.2 Chassis-Provided Logic
- Satisfied by the Platform-Provided Foundation (§5). Met by configuration/use, not new code.

### 3.3 External-Integration-Owned Logic
- Delegated to an external system the app calls over an API. The app treats the result as authoritative and owns only orchestration, validation, and presentation.

**Rule:** logic MAY NOT be implemented in two places. A deliberate deviation from a chassis default is annotated `(CHASSIS-OVERRIDE)` in REQUIREMENTS.md.

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## 4. ARCHITECTURAL INVARIANTS

1. **Async-only.** Every I/O path uses `async`/`await`. The data layer is SQLAlchemy 2.0 async (`select(...).where(...)` + `AsyncSession`). Synchronous DB sessions/engines (`sessionmaker`, `create_engine`, sync `.commit()`) are forbidden in request/service code.
2. **Layered separation.** Per concern module: `app/<concern>/` holds `models.py` (SQLAlchemy `Mapped[...]` entities), `schemas.py` (Pydantic v2 DTOs), `service.py` (business logic, **no** framework/`Request`/`Depends` imports beyond typed input), `routes.py` (thin FastAPI routes that call services). ORM models are NEVER returned directly over the API — map to Pydantic v2 schemas.
3. **Time is timezone-aware UTC.** All timestamps use `datetime.now(UTC)`; naive `datetime.utcnow()`/`datetime.now()` is forbidden. Persisted as `timestamptz`.
4. **Multi-tenancy is automatic.** Tenant-owned models inherit the chassis `TenantScoped` mixin; SQLAlchemy event listeners auto-filter `SELECT`s and auto-stamp `INSERT`s from the bound current-org context var. Slot code never hand-filters by `org_id` for normal reads/writes.
5. **Audit is declarative.** Privileged mutations are wrapped with the chassis `@audited(...)` decorator, which sources actor/org/IP from context vars and writes one append-only row on success.
6. **Server-side enforcement only.** All authentication, validation, and access control are server-side. Client state is never trusted for security or correctness decisions.
7. **Dependency injection via FastAPI `Depends`.** Services are resolved through typed dependency functions and constructor parameters. No service locator, no mutable module-level global state (beyond the chassis-managed engine/session factory).
8. **Per-request transaction.** The request-scoped `AsyncSession` commits on success; an unhandled exception rolls back (no partial commit). Multi-step mutations use an explicit transaction scope (`async with session.begin():`).
9. **Additive-only migrations.** `migrations/versions/NNNN_*.py` (Alembic) is append-only; committed migrations are never edited. `Base.metadata.create_all` is for tests only; production runs `alembic upgrade head`.
10. **LiteLLM for all model calls.** No direct provider HTTP/SDK calls anywhere.
11. **Secrets live outside source.** Signing/wrapping keys come from the environment; provider API keys live AES-256-GCM-encrypted in the datastore. Nothing secret is committed.
12. **Extension points are the only chassis-edit surface.** Slots register only at the marked extension markers (§7); no other chassis file is edited by slot/app authors.

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## 5. PLATFORM-PROVIDED FOUNDATION (do not re-build)

These capabilities are already implemented, secured, tested, and multi-tenant in the chassis. Build only project-specific slots on top of them.

- **Identity & Authentication** — register/login/logout/me; stateless signed JWT (default 60-min TTL, `pyjwt`) in `Authorization: Bearer` header or `HttpOnly`/`Secure`/`SameSite=lax` cookie; direct `bcrypt` (cost ≥12, no `passlib`); lockout (3 failures / 15 min → 30-min lock); uniform anti-enumeration failures; real, chassis-core TOTP MFA is **mandatory** for every account holding platform-wide administrative privilege at this FISMA-Moderate level.
- **Authorization (RBAC)** — `resource:action` permissions grouped into roles; seeded `admin` and `user`; superuser short-circuit; system-wide or per-org grants; a declarative route dependency returns 403 on missing permission.
- **Multi-Tenancy** — organizations + memberships; deterministic current-org resolution; automatic isolation (SQLAlchemy event-listener filter/stamp); cross-tenant access returns "not found".
- **Audit & Accountability** — append-only audit row per privileged mutation (actor, org, entity, details, IP, UTC); DB-enforced immutability (runtime role denied UPDATE/DELETE); retention/archival job.
- **Administration Shell** — server-rendered admin pages (Jinja2): user and org management (scoped to platform/org admins, audited).
- **Observability & Health** — liveness/readiness/version endpoints; per-request correlation id; `structlog` structured logging; admin System Health page.
- **In-App Documentation** — whitelisted in-app docs rendering; path traversal structurally impossible.
- **Embedded LLM Capability** — AES-256-GCM-encrypted provider keys (`cryptography`, org + platform scopes); resolution chain org-key → shared-key-if-permitted → reject; single OpenAI-compatible egress via `httpx.AsyncClient`; keys never in config/logs.
- **MCP Client** — org-scoped connections to external MCP servers (`app/mcp/`; credentials AES-256-GCM-encrypted with the LLM wrapping mechanism, disabled by default, CRUD audited); the tools of enabled connections are advertised to the LLM through the existing chat-completion path.
- **File Storage** — org-scoped upload/list/download/delete; metadata + integrity hash + size cap; opaque storage ids; cross-org access returns "not found".
- **Notifications** — per-user in-app notifications (title, body, severity, read state); producer + consumer API.
- **Rate Limiting** — per-client limiting (Redis-backed), configurable, default-off, fail-open; health/version/static exempt.
- **Reporting** — read-only admin counts page, platform- or org-scoped.
- **Transactional Email & Background Jobs** — `fastapi-mail` send service (console dev / SMTP prod) with delivery logging; `rq` queue + worker (Redis-backed) for async work; a backend outage never breaks foreground requests.
- **Frontend & Accessibility** — Jinja2 + vendored USWDS; base layout slots extend; Section 508 / WCAG 2.1 AA; mobile-first responsive; reusable loading/empty/error partials; configurable system-use banner.
- **Error Handling & Messaging** — production errors return a generic message + correlation id (no internals leaked; full error logged); user-facing messages from a single canonical catalog (`app/error_messages.py`).
- **Configuration, Secrets, Retention, Database** — typed `pydantic-settings` settings from the environment; signing secret rejects placeholders/default in prod; additive-only Alembic migrations; per-request transaction.

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## 6. LAYERED ARCHITECTURE (MANDATORY)

```
HTTP (FastAPI route)                              ← transport only, thin
        ↓
Service Layer (Python domain logic, DI-injected)  ← business rules; no framework/HTTP imports
        ↓
Persistence (SQLAlchemy 2.0 async ORM)            ← async select()/where(), typed Mapped[...] models
        ↓
Integration Layer (httpx.AsyncClient)             ← the ONLY place external APIs are called
```

**Rules:** Routes MUST NOT contain business logic. Services MUST NOT call external APIs directly. The integration layer (`httpx.AsyncClient`) is the only place allowed to reach external systems.

---

<!-- @owned-by:  | @role: tech | @system-derives-from:  | @locked-by-chassis: true -->
## 7. EXTENSION-POINT CONTRACT

Slots integrate **only** at these marked points. Each is a small additive registration. These are the ONLY chassis files a slot/app author may touch, and only at the marked lines.

| File | Marker | Use |
|---|---|---|
| `app/main.py` | `# ─── CHASSIS-EXTENSION-POINT: slot-routers (imports)` and `(registration)` | One import + one `app.include_router(...)` per slot |
| `app/rbac/permissions.py` | `# ─── CHASSIS-EXTENSION-POINT: slot-permissions` | `register("<resource>:<action>", "<desc>")` per slot permission |
| `app/auth/providers/__init__.py` | `# ─── CHASSIS-EXTENSION-POINT: auth-providers` | Additional auth providers (SSO/OAuth) |
| `app/admin/routes.py` | `# ─── CHASSIS-EXTENSION-POINT: admin-pages` | Slot admin pages, gated via the same `_resolve(...)` helper |
| `migrations/versions/` | (auto-discovered) | New additive Alembic migrations for slot tables |

Everything else under `app/` (except `app/slots/`) is chassis-owned. Domain code lives only under `app/slots/<domain>/`.

---

<!-- @owned-by: phase5b_security_requirements | @role: tech | @system-derives-from:  | @locked-by-chassis: true -->
## 8. SECURITY (MANDATORY)

Binding controls (FISMA-Moderate-aligned: AC/AU/IA/SC/SI families):

- **IA-5 password policy:** ≥14 chars, ≥4 character classes, enforced at registration.
- **SC-13 secret storage:** `bcrypt` (cost ≥12, configurable), called directly (no `passlib`). Never store/log plaintext.
- **Sessions:** signed JWT (HS256/384/512 via `pyjwt`), default 60-min TTL; cookie `HttpOnly`, `Secure` in prod, `SameSite=lax`.
- **AC-7 lockout:** 3 failures / 15-min window → 30-min lock, checked before password verify.
- **IA-6 anti-enumeration:** uniform failure across unknown/inactive/wrong/locked.
- **Secret hardening:** the JWT signing secret (`jwt_secret`) and the MFA wrapping key (`mfa_encryption_key`) reject placeholder markers and the in-code default in prod; min length 32.
- **LLM wrapping key:** the AES-256-GCM key (`llm_encryption_key`) is 32 bytes (hex); production fails closed at use time if left at the in-code default.
- **AU-3 audit content:** actor + org + IP + action + entity + details + UTC timestamp.
- **AU-9 audit immutability:** the application runtime DB role is denied UPDATE/DELETE on the audit table (migration-enforced).
- **SI-11 error handling:** prod responses are generic + correlation id; full error logged internally only.
- **Tenant isolation:** cross-tenant access returns "not found", never another tenant's data.
- **SC-5 rate limiting:** available, opt-in, fail-open.

Authentication is required for all routes unless explicitly public. Authorization is role-based and server-side. No credentials in source code.

<!-- @owned-by: phase5b_security_requirements | @role: business | @system-derives-from:  | @locked-by-chassis: false -->
### 8.1 Application-Specific Security Principles (project-editable)

*Editable. Add project-specific security obligations beyond the inherited baseline — domain compliance regimes (HIPAA, PCI-DSS, CJIS, IRS Pub 1075), data-classification handling rules, field-level encryption requirements, additional audit events, or stricter session policy. State each as an enforceable rule with its enforcement location. Items here MUST NOT weaken any §8 baseline; they may only add or tighten.*

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## 9. CODING STANDARDS

- **Naming:** `PascalCase` for types (Pydantic schemas, SQLAlchemy models), `snake_case` for functions/modules/variables/DB columns, `UPPER_SNAKE` for constants.
- **Typing:** all chassis code is type-annotated; **slot code is `mypy --strict`** (`disallow_untyped_defs`, `disallow_any_generics`, `warn_return_any`).
- **Linting/formatting:** `ruff` with rule sets `E,F,W,I,B,UP,ASYNC,SIM`; line length 100; target `py312`.
- **Logging:** `structlog` with contextual event names (e.g., `auth.login.success`); never `print`. Correlation id auto-bound to every log line.
- **Errors:** raise `HTTPException` with messages drawn from the canonical catalog (`app/error_messages.py`); never leak internals to clients.
- **Validation:** all request bodies are Pydantic v2 schemas (`model_config = ConfigDict(...)`) with binding constraints, validated server-side.
- **Models vs DTOs:** SQLAlchemy `Mapped[...]` entities are never serialized directly; request/response shapes are separate Pydantic v2 schemas.
- **Tests:** `pytest` + `pytest-asyncio` (auto mode); each capability covers happy-path, auth gate (401), permission gate (403), cross-tenant isolation ("not found"), and validation (422).

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## 10. FORBIDDEN / PROHIBITED PATTERNS (AI HARD STOPS)

AI models — and human developers — MUST NOT introduce any of the following into `app/slots/` (statically enforced by `mypy --strict`, `ruff` `UP` rules, and a post-generation AST scan):

```
@validator(                               # Pydantic v1 → @field_validator
class Config:                             # Pydantic v1 → model_config = ConfigDict(...)
Field(env=                                # Pydantic v1 settings form
from pydantic import BaseSettings         # → pydantic_settings.BaseSettings
Optional[                                 # → X | None
from typing import List|Dict              # → builtin generics (list[...], dict[...])
session.query(                            # SQLAlchemy 1.4 → select(...).where(...)
from sqlalchemy.orm import sessionmaker   # sync → async_sessionmaker
create_engine(                            # sync → create_async_engine
session.commit()  (sync form)             # → await session.commit()
from passlib.context import CryptContext  # forbidden — use app/auth/password_hashing.py (direct bcrypt)
datetime.utcnow( / datetime.now()         # naive → datetime.now(UTC)
sqlmodel / import sqlmodel                # not a chassis dependency
```

In addition, AI models — and human developers — MUST NOT:
- Reference a provider SDK directly (Anthropic/OpenAI/Gemini) — all LLM calls go through the LiteLLM `httpx.AsyncClient`.
- Introduce a SPA framework, a bundler, or a Sass/transpile step into the serve path.
- Use synchronous SQLAlchemy APIs (sync `Session`, `sessionmaker`, `create_engine`) in request/service code — async only.
- Hand-filter or hand-stamp `org_id` for normal tenant reads/writes (the chassis `TenantScoped` mixin + event listeners own this).
- Expose SQLAlchemy ORM models directly over the API — map to Pydantic v2 schemas.
- Edit chassis files outside the §7 extension markers.
- Add a dependency outside §1.
- Store secrets in source, config files, or logs.
- Invent business rules, duplicate externally-owned logic, bypass the integration layer, change the tech stack, or skip requirements.

If required information is missing, generation MUST STOP and request clarification.

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## 11. DOCUMENT AUTHORITY

This Constitution overrides REQUIREMENTS.md, DESIGN.md, TASKS.md, TEST-SCENARIOS.md, SPECIFICATION.md, and SOLICITATION.md. In case of conflict, **this document wins**.

---

*This document was generated by the SD-Agile Spec Builder from the project's Golden Record, on the autonomous-platform-chassis-python foundation.*
