# python-fastapi-mt-fisma-moderate-llm — CONSTITUTION

**Version:** 1.2.1
**Date:** 2026-09-21
**Status:** Supreme & Immutable
**Chassis version governed:** 1.1.0
**Governs:** `chassis/python-fastapi-mt-fisma-moderate-llm/`
**Variant:** Multi-Tenant, FISMA Moderate, with embedded LLM (Chassis Program variant 3 — the pilot package)
**Program supremacy:** `specs/chassis-program/chassis-program-CONSTITUTION.md` is supreme for this package's program-level taxonomy membership, naming, independence, and the zero-CVE mandate. This document is supreme for this package's own technology stack and package-specific invariants; where the two are silent toward each other, each governs its own scope.

> **This document is supreme for this package.** It fixes the immutable technology stack, architectural invariants, security rules, and coding standards. Where any other document in this package conflicts with this CONSTITUTION, the CONSTITUTION wins. It is the technology-specific counterpart to the technology-neutral [`REQUIREMENTS.md`](REQUIREMENTS.md): REQUIREMENTS says *what*; this says *with what, and under what non-negotiable rules*.
>
> **Provenance:** forked from `chassis/python-fastapi/` (chassis v0.10.0) on 2026-09-02. The reference chassis remains untouched and is not a runtime dependency of this package (`chassis-program-CONSTITUTION.md` §2, package independence). This package's own `CHASSIS_VERSION` lineage starts fresh at `1.0.0`, tracked via `StackTemplate.ParentID` pointing at the reference chassis's own row (`specs/chassis-program/STACKTEMPLATE-PROJECTCLASS-REGISTRATION-PLAN.md`).

## 0. What differs from the reference `chassis/python-fastapi`

This package is **not** a drop-in copy — it is the reference chassis with three deliberate deltas, all IMMUTABLE for this package:

1. **Real, mandatory MFA (TOTP)** for platform-wide administrative privilege (FR-AUTH-15) — the reference chassis leaves this as an unbuilt, documented-only extension point (`app/auth/providers/__init__.py`'s "v1.3: 2FA (TOTP)"); this package builds it as chassis-core, in `app/auth/mfa/`.
2. **FISMA-Moderate policy constants** (session TTL 60min, password 14/4, lockout 3/15/30, audit retention 365 days) — identical to the reference chassis's current defaults, but now stated as this package's own immutable, FISMA-Moderate-delta-sourced values rather than incidental defaults (see `specs/chassis-program/deltas/fisma-moderate.md`).
3. **Three new admin capabilities** — System Health, Platform Health, and the FISMA self-audit + report generator — as chassis-core modules, not present in the reference chassis. See §12 below and `DESIGN.md` §7–§9.
4. **MCP client capability** (`app/mcp/`, added 2026-09-10) — lets the embedded-LLM chat-completion call path discover and invoke tools on admin-registered external MCP servers (client role only; no inbound MCP server is ever built). Not present in the reference chassis, and not part of any other Chassis Program package's own independent implementation (`chassis-program-CONSTITUTION.md` §2 — implemented four times, once per LLM-enabled package, never shared). See `REQUIREMENTS.md` §25, `DESIGN.md` §6.14.

The LLM capability (`app/llm/`) and multi-tenancy (`app/orgs/`) are carried forward from the reference chassis unchanged in mechanism, restated as this package's own immutable invariants below for self-containment.

---

## 1. Immutable Technology Stack

The following are **locked**. Changing any of them is a new major chassis version, not an edit.

### 1.1 Language & runtime
- **Python 3.12** (`>=3.12,<3.13`). Toolchain/dependency manager: **uv**.

### 1.2 Core dependencies (exact pins)
| Concern | Package | Version |
|---|---|---|
| Web framework | `fastapi` | 0.141.1 |
| ASGI server | `uvicorn[standard]` | 0.52.4 |
| ORM (async) | `sqlalchemy[asyncio]` | 2.0.52 |
| Migrations | `alembic` | 1.19.2 |
| DB driver | `psycopg[binary,pool]` | 3.3.5 |
| Validation | `pydantic` | 2.13.5 |
| Settings | `pydantic-settings` | 2.15.0 |
| Password hashing | `bcrypt` | 5.0.0 (called directly via `app/auth/password_hashing.py` — no `passlib` layer) |
| Structured logging | `structlog` | 26.1.0 |
| Metrics | `prometheus-fastapi-instrumentator` | 8.1.0 |
| Background jobs | `rq` | 2.12.0 |
| Redis client | `redis` | 8.1.0 |
| Templates | `jinja2` | 3.1.6 |
| Form parsing | `python-multipart` | 0.0.32 |
| Transactional email | `fastapi-mail` | 1.6.8 |
| Crypto (AES-256-GCM, TLS) | `cryptography` | >=50.0.1 |
| MCP client SDK (FR-MCPCLIENT, this package's own delta — see §0 point 4) | `mcp` | 2.2.0 (client surface only — `mcp.Client`; the SDK's server-authoring API is a test-only dependency, never shipped in the running app) |

**Dev-only:** `pytest` 9.1.1, `pytest-asyncio` 1.4.0, `pytest-cov` 7.1.0, `httpx` 0.28.1, `factory-boy` 3.3.3, `mypy` 2.3.1, `ruff` 0.16.5, `pre-commit` 4.0.1.

**`python-jose` and `passlib` are explicitly forbidden in this package** (CP-B.3, 2026-09-02; stated here 2026-09-21): `python-jose` carried 5 open CVEs with no further fix release; `passlib` 1.7.4 is version-probe-incompatible with `bcrypt>=4.1`. JWT uses `pyjwt` directly (HS256/384/512 only — no ECDSA, so no `ecdsa` transitive dependency); password hashing calls `bcrypt` directly. This section previously listed both libraries as the locked stack, contradicting this package's own `pyproject.toml`.

**No dependency may be added without updating this section.** The App Builder treats anything outside this list as a forbidden import in slot code.

### 1.3 Datastore & cache
- **PostgreSQL** as the single relational datastore (async via psycopg3). **Redis** for the job queue and rate-limit counters.

### 1.4 Frontend
- **Server-rendered Jinja2 + USWDS 3.x** (U.S. Web Design System), themed via a single hand-authored override stylesheet. **No** SPA framework, **no** bundler, **no** transpile step in the serve path. USWDS's progressive-enhancement script is permitted as a vendored/CDN asset; app interactivity stays vanilla.

### 1.5 LLM egress
- **All** model calls route through a single OpenAI-compatible endpoint (LiteLLM proxy by configuration). No provider SDK may be imported directly.

---

## 2. Architectural Invariants

1. **Async-only.** Every I/O path uses `async`/`await`. The data layer is SQLAlchemy 2.0 async (`select(...).where(...)` + `AsyncSession`). Synchronous DB sessions/engines are forbidden in request/service code.
2. **Pydantic v2 only.** Models use `model_config = ConfigDict(...)`; settings subclass `pydantic_settings.BaseSettings`. Pydantic v1 idioms are forbidden (§5).
3. **Typed ORM.** Models use the SQLAlchemy 2.0 typed form (`Mapped[...]` + `mapped_column(...)`), inheriting the chassis `Base`.
4. **One concern per module.** `app/<concern>/` holds `models.py`, `schemas.py`, `service.py`, `routes.py` as applicable. Services contain business logic and **no** framework (HTTP) imports; routes are thin and call services.
5. **Multi-tenancy is automatic.** Tenant-scoped models inherit the `TenantScoped` mixin; event listeners auto-filter SELECTs and auto-stamp INSERTs by the bound current-org context var. Slot code never hand-filters by `org_id` for normal reads/writes.
6. **Audit is declarative.** Privileged mutations are wrapped with the `@audited(...)` decorator; it sources actor/org/IP from context vars and writes one row on success.
7. **Server-side enforcement only.** All auth, validation, and access control are server-side. Client state is never trusted.
8. **LiteLLM for all model calls.** No direct provider HTTP/SDK calls anywhere.
9. **Secrets live outside source.** Signing/wrapping keys come from the environment; provider API keys live AES-256-GCM-encrypted in the datastore. Nothing secret is committed.
10. **Additive-only migrations.** `migrations/versions/NNNN_*.py` are append-only; committed migrations are never edited. Schema sync (`create_all`) is for tests only; production runs Alembic.
11. **Per-request transaction.** The request-scoped session commits on success and rolls back on exception.
12. **Extension points are the only chassis-edit surface.** Slots register only at the marked markers (§6); no other chassis file is edited by slot/app authors.

---

## 3. Security Invariants (binding)

These implement the controls enumerated in REQUIREMENTS §3–§6, §10, §18, §20 and `docs/SECURITY-SELF-AUDIT.md`. They are not optional.

- **IA-5 password policy:** ≥14 chars, 4 character classes, enforced at registration.
- **SC-13 secret storage:** bcrypt (cost ≥12, configurable), called directly (no `passlib`). Never store/log plaintext.
- **Sessions:** signed JWT (HS256/384/512), default 60-min TTL; cookie is `HttpOnly`, `Secure` in prod, `SameSite=lax`.
- **AC-7 lockout:** 3 failures / 15-min window → 30-min lock, checked before password verify.
- **IA-6 anti-enumeration:** uniform failure response across unknown/inactive/wrong/locked.
- **FR-351 secret hardening:** `jwt_secret` rejects placeholder markers in any env and the in-code default in prod; `min_length` 32.
- **LLM wrapping key:** `llm_encryption_key` is 32 bytes (hex); production **fails closed at use time** if left at the in-code default.
- **AU-3 audit content:** actor + org + IP + action + entity + details + UTC timestamp.
- **AU-9 audit immutability:** the application runtime role is denied UPDATE/DELETE on the audit table (migration-enforced).
- **SI-11 error handling:** prod responses are generic + correlation id; full error logged internally only.
- **Tenant isolation:** cross-tenant access returns "not found", never another tenant's data.
- **Rate limiting (SC-5):** available, opt-in, fail-open.
- **IA-2(1) MFA (this package's own delta — see §0):** TOTP-based, chassis-core, `app/auth/mfa/`. Mandatory for every account holding **platform-wide** administrative privilege before it can reach any privileged action; org-scoped "admin" role (granted to an organization's creator) does NOT trigger the requirement. Secrets AES-256-GCM at rest. Backup codes single-use, invalidated on use. This is IMPLEMENTED, not operator-responsibility, for this package.
- **SI-2/SI-3 zero-CVE mandate (`chassis-program-CONSTITUTION.md` §5):** this package's own dependency set MUST be at latest stable with zero open CVEs at every tagged release, verified by the same scanner class the Platform Health capability (§0 point 3, `DESIGN.md` §8) uses at runtime. This is a build-quality bar, enforced in this package's own CI, independent of the FISMA level chosen.

---

## 4. Coding Standards

- **Naming:** `PascalCase` types, `snake_case` functions/modules/columns, `UPPER_SNAKE` constants.
- **Typing:** chassis code is type-annotated; **slot code is `mypy --strict`** (`disallow_untyped_defs`, `disallow_any_generics`, `warn_return_any`).
- **Linting/formatting:** `ruff` with rule sets `E,F,W,I,B,UP,ASYNC,SIM`; line length 100; target `py312`.
- **Logging:** `structlog` with contextual event names (e.g., `auth.login.success`); never `print`. Request correlation id auto-bound.
- **Errors:** raise `HTTPException` with messages drawn from the canonical catalog (`app/error_messages.py`); never leak internals to clients.
- **Validation:** all request bodies are Pydantic v2 schemas with binding constraints.
- **Tests:** `pytest` + `pytest-asyncio` (auto mode); each capability covers happy-path, auth gate (401), permission gate (403), cross-tenant isolation (404), and validation (422).

---

## 5. Forbidden Patterns (statically enforced in `app/slots/`)

The App Builder rejects generated slot code containing any of these (Pydantic v1, SQLAlchemy 1.4, legacy typing, sync DB, naive time, wrong ORM lib):

```
@validator(                         # Pydantic v1 → @field_validator
class Config:                       # Pydantic v1 → model_config = ConfigDict(...)
Field(env=                          # Pydantic v1 settings form
BaseSettings (from pydantic)        # → pydantic_settings.BaseSettings
Optional[                           # → X | None
from typing import List|Dict        # → builtin generics
session.query(                      # SQLAlchemy 1.4 → select(...).where(...)
from sqlalchemy.orm import sessionmaker   # sync → async_sessionmaker
create_engine(                      # sync → create_async_engine
session.commit() (sync form)        # → await session.commit()
from passlib.context import CryptContext  # forbidden in this package -- use app/auth/password_hashing.py
datetime.utcnow( / datetime.now()   # naive → datetime.now(UTC)
sqlmodel / import sqlmodel          # not a chassis dependency
```

Enforced by `mypy --strict` on `app/slots/*`, `ruff` `UP` rules, and a post-generation AST scan.

> **Enforcement note (2026-06-25):** the platform's chassis forbidden-pattern scanner now actively enforces the Pydantic v1 idioms `Field(env=` and `from pydantic import BaseSettings` listed above (previously documented-but-unenforced). Generated slot code containing either is rejected at scan time.

---

## 6. Extension-Point Contract

Slots integrate **only** at these marked points (exact marker text in the named file). Each is a small additive registration.

| File | Marker | Use |
|---|---|---|
| `app/main.py` | `# ─── CHASSIS-EXTENSION-POINT: slot-routers (imports)` and `(registration)` | One import + one `app.include_router(...)` per slot |
| `app/rbac/permissions.py` | `# ─── CHASSIS-EXTENSION-POINT: slot-permissions` | `register("<resource>:<action>", "<desc>")` per slot permission |
| `app/auth/providers/__init__.py` | `# ─── CHASSIS-EXTENSION-POINT: auth-providers` | Additional auth providers (SSO/OAuth) |
| `app/admin/routes.py` | `# ─── CHASSIS-EXTENSION-POINT: admin-pages` | Slot admin pages, gated via the same `_resolve(...)` helper |
| `migrations/versions/` | (auto-discovered) | New additive migrations for slot tables |
| Tokens (JWT) | `pyjwt` | 2.13.0 |
| TOTP MFA | `pyotp` | 2.10.0 |
| Dependency CVE audit (CI gate) | `pip-audit` | >=2.10.1 |

**These are the ONLY chassis files a slot/app author may touch, and only at the marked lines.** Everything else under `app/` (except `app/slots/`) is chassis-owned.


### 6.1 Application dependencies — the ONLY extensible part of §1 (AB-FR-617)

§1's pins are **floor**. They are chassis-owned, and changing one is a chassis amendment under §8 —
not something an application may do. But a real application legitimately needs libraries this
chassis never anticipated: PDF generation, spreadsheet export, a domain-specific format. Those are
declared in the generated application constitution's `application_dependencies` section, and that
section is the **only** part of the technology stack an application may extend.

**This is extension, not amendment.** Adding a library there does not change this chassis, does not
bump `CHASSIS_VERSION`, and does not pass through §8. It is recorded in the application's own build
package, against the application's own version.

**The rules below are chassis-owned and live in a locked section** (`extension_model` in the
generated constitution). That placement is deliberate and load-bearing: rules written *inside* the
extensible section could be edited out by the very customer they bind.

1. **Additions only.** An entry may not replace, shadow, override a pin of, or downgrade anything in
   §1.2.
2. **No second implementation of a chassis concern.** No second ORM, web framework, router, auth or
   session library, password-hashing or crypto provider, migration tool, or HTTP client used to
   reach a model. Where this chassis already owns the concern, its implementation is the one.
3. **Exact pins, same discipline as §1.2.** A floating version, or a version absent from `uv.lock`, is not a valid entry.
4. **The same zero-CVE and currency obligation as §1.2** (§3 / SI-2 / SI-3). An application
   library is in scope for the same scans and the same SLA — a customer addition must not become the
   soft spot in this package's FISMA posture.
5. **No new egress.** A library that opens a network path this chassis does not already open is not
   an application dependency; it is an architecture change and goes through §8.
6. **Org-admin approval per addition**, recorded with the approver and the date.

An entry that cannot satisfy all six is not an extension. It is either a chassis amendment under §8,
or it does not happen.

**Why only this section is extensible today, stated so the limit is not mistaken for an oversight.**
The enforcement mechanism that exists is a locked / not-locked gate; *add-only* enforcement does not
exist yet. So "extensible" currently means "freely editable", and only a section that starts empty —
with no mandate inside it to weaken — is safe under that. `observability` and `state_handling` are
additive in principle and are the right next candidates, but they stay **floor** until add-only
enforcement lands. Promoting them sooner would be a regression dressed as a feature.

**Where it lands.** Declared in `pyproject.toml` `[project.dependencies]` and present in the committed `uv.lock`; the chassis's own pins stay in §1.2.

---

## 7. Ownership Boundary

- **Chassis-owned (do not edit except at §6 markers):** `app/auth`, `app/rbac`, `app/orgs`, `app/audit`, `app/health`, `app/mail`, `app/tasks`, `app/llm`, `app/mcp`, `app/files`, `app/notifications`, `app/ratelimit`, `app/admin`, `app/frontend.py`, `app/db.py`, `app/config.py`, `app/deps.py`, `app/deps_context.py`, `app/logging.py`, `app/error_handlers.py`, `app/error_messages.py`, `app/main.py`, `app/templates/` (chassis pages), `app/static/`.
- **Slot-owned (free to create):** `app/slots/<domain>/` and its `tests/`.

---

## 8. Amendment Procedure

1. Amend the spec first: update REQUIREMENTS.md (if the *capability/policy* changes) and/or this CONSTITUTION (if the *stack/standard* changes), bumping versions + CHANGELOG.
2. Implement → run the full test suite → bump `CHASSIS_VERSION` and the platform's Go seed pin together (CI enforces equality).
3. A change to §1 (stack) or §2 (invariants) is a **major** chassis version.
4. An application adding a library under **§6.1** is an **extension, not an amendment**: it does not bump `CHASSIS_VERSION` and does not pass through this procedure. Only a change to a chassis-owned section does. Conflating the two is how a floor quietly becomes negotiable.

---

## CHANGELOG

### 1.2.1 — 2026-09-21

- §1.2 dependency table regenerated from this package's own `pyproject.toml` (Task Log 2026-09-21-253, D12): the table is the list the App Builder treats as the only importable libraries, so stale pins were wrong instructions. Spec brought into line with the shipped code by operator approval; no code change and no chassis version change.

### 1.2.0 — 2026-09-18

- **Added §6.1 Application dependencies (AB-FR-617)** — the single extensible part of §1, and the
  first extension surface this chassis has declared. §1's pins stay floor; an application's own
  libraries are declared in the generated constitution's application-dependencies section under six
  chassis-owned rules (additions only; no second implementation of a chassis concern; exact pins;
  the same zero-CVE and currency obligation; no new egress; org-admin approval per addition). Those
  rules deliberately live in a **locked** section, because rules inside an extensible section could
  be edited out by the customer they bind.
- **§8 gains a fourth clause** distinguishing an extension from an amendment, so an application
  adding a library does not bump `CHASSIS_VERSION`.
- `observability` and `state_handling` were evaluated and deliberately **left floor**: with only a
  locked/not-locked gate available, "extensible" means freely editable, and those two carry mandates
  that could therefore be deleted rather than extended.
- Motivated by a real refusal: an application needed `gopdf` and `excelize` and the chassis correctly
  refused, because dependency pins are locked. The need was real and so was the refusal — which is
  exactly what an extension surface is for.

### 1.1.0 — 2026-09-10
- Adds §0 point 4 (MCP client capability delta), the `mcp` SDK to §1.2's dependency table (client surface only — `mcp.Client`; the server-authoring API is test-only), and `app/mcp` to §7's chassis-owned ownership boundary. A capability addition per this package's own `CHANGELOG.md` versioning convention ("MINOR bumps add capabilities") — not a change to an *existing* locked pin, so not the §8.3 "major chassis version" case. Realizes `REQUIREMENTS.md` §25 / `DESIGN.md` §6.14. Task Log: `specs/platform/Task Logs/2026-09-10-003-mcp-client-support.md`.

### 1.0.0 — 2026-09-02
- Initial CONSTITUTION for this package, forked from `chassis/python-fastapi` CONSTITUTION v1.0.1 (chassis v0.10.0). Restates program supremacy relationship with `chassis-program-CONSTITUTION.md`. Adds §0 (deltas from the reference chassis: MFA, FISMA-Moderate constants, three new admin capabilities), the IA-2(1) MFA security invariant, and the SI-2/SI-3 zero-CVE mandate invariant. `CHASSIS_VERSION` lineage restarts at 1.0.0 per `chassis-program-CONSTITUTION.md` §2.

### Prior history (inherited from the reference chassis, retained for context)

### 1.0.1 — 2026-06-25
- §5 (C9): Added an enforcement note recording that the platform's chassis forbidden-pattern scanner now actively enforces the Pydantic v1 idioms `Field(env=` and `from pydantic import BaseSettings` (previously documented-but-unenforced). No change to the §5 forbidden-pattern list itself.

### 1.0.0 — 2026-06-22
- Initial CONSTITUTION for the python-fastapi chassis, retrofit from the implemented chassis at v0.10.0: locked stack (Python 3.12, FastAPI/SQLAlchemy-2.0-async/Pydantic-v2/Postgres/Redis/USWDS, exact pins), 12 architectural invariants, binding security invariants, coding standards, the statically-enforced forbidden-pattern list, the four extension-point markers, and the chassis/slot ownership boundary.
