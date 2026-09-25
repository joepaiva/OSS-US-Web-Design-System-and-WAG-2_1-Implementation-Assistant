---
template: python-requirements
version: "3.0"
document_type: REQUIREMENTS.md
locked_section_aware: true
---

# {{PROJECT_NAME}} — Requirements
<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## Platform Chassis — AI-Executable Requirements Specification (Python 3.12 · FastAPI · SQLAlchemy 2.0 async)

**Project:** {{PROJECT_NAME}}
**Foundation:** autonomous-platform-chassis-python (FastAPI 0.115 · SQLAlchemy 2.0 async · Alembic · psycopg3/PostgreSQL · Redis · Jinja2 + USWDS)
**Generated Date:** {{DATE}}

**Purpose.** This document defines the complete requirements for the application. It serves two readers at once:
- **AI / App Builder (with the chassis):** the requirements below are the input — together with `CONSTITUTION.md` — for generating `DESIGN.md` and the application slot code on the chassis. The **Platform-Provided Foundation** (§2) is already implemented by the chassis; do not re-specify or re-build it — build only the project-specific requirements in §3–§5 on top of it.
- **Human developer (without the chassis):** §2 states *what the platform provides and why* in concrete terms so you understand the baseline you are building on (or must reproduce in Python/FastAPI); §3–§5 are this project's specific requirements. Together they are sufficient for a reasonably skilled Python developer to understand and implement the application.

No project requirement may be skipped, merged, or reinterpreted.

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## 1. GLOBAL REQUIREMENT RULES (NON-NEGOTIABLE)

1. Every project requirement MUST map to ≥1 Design section, ≥1 Task, and ≥1 Test Scenario (see §6 Traceability).
2. Every requirement MUST declare its **logic ownership** as exactly one of:
   - **Application-owned** — domain logic implemented in this application's slot code (`app/slots/<domain>/`), executing in the app runtime against PostgreSQL via SQLAlchemy 2.0 async.
   - **Chassis-provided** — satisfied by the Platform-Provided Foundation (§2); met by configuration/use, not new code.
   - **External-integration-owned** — delegated to an external system the app calls over an API (`httpx.AsyncClient`); the app treats the result as authoritative and owns only orchestration, validation, and presentation.
3. Requirements MUST NOT contain implementation guesses; ambiguity causes generation to STOP and request clarification.
4. A requirement already covered by the Platform-Provided Foundation MUST NOT be re-specified as application-owned unless it is an explicit, justified deviation annotated `(CHASSIS-OVERRIDE)` (which then states the new behavior and its enforcement).

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## 2. PLATFORM-PROVIDED FOUNDATION (Chassis)

These capabilities are **already implemented, secured, tested, and multi-tenant** in the Python chassis. The application inherits them with no new code. Each entry states the **intent** (what & why) and the **concrete contract** (so a human can understand or reproduce it without the chassis in FastAPI / SQLAlchemy terms), then how the application builds on it. Numbers below are chassis-locked baselines; deviate only via a `(CHASSIS-OVERRIDE)` requirement.

### 2.1 Identity & Authentication
Register (unique email + complexity-checked password), log in, log out, fetch own profile. Sessions are stateless signed JWTs (`pyjwt`, default 60-min TTL) carried in the `Authorization: Bearer` header or an `HttpOnly`/`Secure`/`SameSite=lax` cookie. Passwords: ≥14 chars, ≥4 character classes, hashed with `bcrypt`, called directly (cost ≥12; no `passlib`). Lockout after 3 failures / 15 min for 30 min; uniform anti-enumeration failures; inactive users cannot log in. Real chassis-core TOTP MFA (enrollment, two-step login, single-use backup codes, self-service disable, admin reset) is **mandatory** for every account holding platform-wide administrative privilege at this FISMA-Moderate level; an org-scoped `admin` role does not trigger it. *Application use:* receive the current user via the chassis FastAPI dependency (`Depends(get_current_user)`); do not re-implement auth.

### 2.2 Authorization (RBAC)
`resource:action` permissions grouped into roles; seeded `admin` (all) and `user` (read-only) roles; superuser short-circuit; grants resolve system-wide OR per-organization. Server-side enforcement only; a declarative FastAPI route dependency (`Depends(require_permission("<resource>:<action>"))`) returns 403 on missing permission; slots register new permissions at the extension marker (auto-seeded, no migration). *Application use:* gate each slot route with the appropriate `:read`/`:write` permission dependency.

### 2.3 Multi-Tenancy
Organizations (tenants) with name + unique slug; users belong via memberships (optional per-org role + default flag); deterministic current-org resolution. **Isolation is automatic:** tenant reads are auto-filtered and writes auto-stamped (SQLAlchemy event listeners keyed off a bound current-org context var) by the current organization; cross-tenant access returns "not found". *Application use:* tenant-owned models inherit the chassis `TenantScoped` mixin; never hand-filter or hand-stamp `org_id`.

### 2.4 Audit & Accountability
One declarative wrapper (the `@audited(...)` decorator) records an append-only audit row on each successful privileged mutation: action, actor, org, optional entity type+id, structured details, client IP, UTC timestamp. Append-only is DB-enforced (no UPDATE/DELETE by the app role); reads are not audited; a retention job (`rq` scheduled task) archives rows older than a configurable window (default 365 days). *Application use:* decorate state-mutating slot service methods with the chassis audit decorator.

### 2.5 Administration Shell
Server-rendered admin UI (Jinja2) gated to administrators: user management (list/create/deactivate/reactivate; platform admins see all, org admins see their org; cannot self-deactivate; duplicates rejected; all audited) and organization management (platform admins only). Slots add admin pages at the admin extension point (`app/admin/routes.py`).

### 2.6 Observability & Health
Liveness, readiness (DB-ping via `AsyncSession`), and version endpoints; per-request correlation id (response header + bound to every `structlog` line); structured logging; an admin **System Health** page (versions, environment, dependency reachability — best-effort, credentials redacted).

### 2.7 In-App Documentation
Admin **Documentation** section renders a whitelisted set of the platform's own docs in-app (overview, user manual, security self-audit); path traversal is structurally impossible; safe Jinja2 rendering (autoescape on).

### 2.8 Embedded LLM Capability
Provider API keys stored AES-256-GCM-encrypted at rest (`cryptography`; per-org and platform-shared scopes); resolution chain org-key → shared-key-if-permitted → reject (shared defaults denied); a single provider-neutral (OpenAI-compatible) egress via `httpx.AsyncClient` with the resolved key injected per request; keys never in config or logs, shown masked; key mutations audited; fails closed in prod if the wrapping key is default (checked at use time). *Application use:* call the chassis LLM client; never embed keys or import a provider SDK directly.

**MCP client.** Org-scoped connections to external MCP servers (a name, a URL and an optional credential), disabled by default on creation; a stored credential is encrypted with the same mechanism as the provider keys and never appears in an audit record, log line or error message; connection CRUD is audited. The tools of an org's enabled connections are advertised to the LLM through the existing chat-completion path. *Application use:* register connections through the admin MCP page; do not build a parallel tool-calling path.

### 2.9 File Storage
Org-scoped upload/list/download/delete; metadata + integrity hash (SHA-256) + size; configurable size cap; opaque system-generated storage ids (no user path component); cross-org access returns "not found"; file mutations audited.

### 2.10 Notifications
Per-user in-app notifications (title, body, severity level, read state); a producer function for slots/subsystems; consumer API (list, unread count, mark one/all read); strictly per-user scoped.

### 2.11 Rate Limiting
Per-client edge rate limiting (Redis-backed counters); configurable and **default-off**; returns "too many requests" + retry-after when exceeded; health/version/static exempt; fail-open if Redis is unreachable.

### 2.12 Reporting
Read-only admin Reports page: user/org/audit/file/notification/LLM-key counts; platform-scoped for platform admins, org-scoped for org admins.

### 2.13 Transactional Messaging & Background Jobs
Email send service (`fastapi-mail`) with console (dev) and SMTP (prod) backends, each logging a delivery record. An `rq` queue + worker (Redis-backed) for async work; slots enqueue via a helper; a backend outage never breaks foreground requests.

### 2.14 Frontend & Accessibility
Server-rendered Jinja2 + vendored USWDS 3.x; consistent base layout (`base.html`) slots extend; **Section 508 / WCAG 2.1 AA** (semantic controls, labelled inputs, skip-link, ARIA live regions, accessible dialogs, ≥44×44px touch targets, no mobile auto-zoom); mobile-first responsive; reusable loading/empty/error partials; configurable system-use banner; optional government banner.

### 2.15 Error Handling & Messaging
Production errors return a generic message + correlation id (no internals; full error logged internally) via a FastAPI exception handler; user-facing messages come from a single canonical, blame-free, screen-reader-friendly catalog (`app/error_messages.py`) keyed by condition.

### 2.16 Configuration, Secrets, Retention, Database
Typed `pydantic-settings` settings from the environment (documented `.env` for local); JWT signing secret rejects placeholders and refuses the in-code default in prod; no secrets in source; managed-platform DB URLs normalized. Bounded, explicit data retention (audit archival + a per-record mechanism slots can adopt). Single relational datastore (PostgreSQL) with SQLAlchemy 2.0 async access, per-request transactions (commit on success / rollback on error), and **additive-only Alembic migrations** (committed migrations never edited).

### 2.17 Non-Functional Baselines (inherited)
Page load ≤2.5s p95 (slow mobile) / ≤1.0s p95 (broadband); API ≤250ms p95 reads / ≤800ms p95 writes; availability ≥99.5% monthly (readiness-gated, additive migrations enable zero-downtime); ≥100 concurrent sessions/instance (scale horizontally); every audited mutation is transactional; FISMA-Moderate-aligned security baseline (AC/AU/IA/SC/SI families); Section 508 / WCAG 2.1 AA. A project overrides one only via an explicit `(CHASSIS-OVERRIDE)` requirement in §5.

---

<!-- @owned-by: phase3_to_be_imagineering | @role: business | @system-derives-from:  | @locked-by-chassis: false -->
## 3. BUSINESS CONTEXT & PROCESSES (TO-BE)

*Project-specific business context: the future-state (TO-BE) processes the application enables, the workflows it automates, and the operational outcomes it must deliver. Document each process as a named flow (trigger → steps → outcome), the actors involved, and the value it delivers. The AS-IS baseline that motivated each process is captured here for traceability.*

<!-- @owned-by: phase2_as_is_discovery | @role: business | @system-derives-from:  | @locked-by-chassis: false -->
### 3.1 Current State (AS-IS) Baseline

*The existing processes, systems, data sources, and pain points this application replaces or augments. Each item links to the TO-BE process that resolves it.*

<!-- @owned-by: phase4_user_personas | @role: business | @system-derives-from:  | @locked-by-chassis: false -->
### 3.2 User Personas & Actor Classes

*Each user class: name, goals, responsibilities, expected volume, the permissions (RBAC `resource:action` grants) and roles they map to, and the key journeys they perform. These personas drive the authorization design in DESIGN.md §authorization and the persona-specific UI flows.*

---

<!-- @owned-by: phase5_requirements_enumeration, phase4_user_personas | @role: business | @system-derives-from:  | @locked-by-chassis: false -->
## 4. FUNCTIONAL REQUIREMENTS (FR)

*Project-specific functional requirements (the domain features built as slots on the foundation). Each carries an ID (e.g. FR-001), priority (MUST/SHOULD/MAY), actor (a §3.2 persona), the behavior, and acceptance criteria (happy path, invalid input → 422, authorization failure → 401/403, cross-tenant → "not found", edge case). Requirements satisfied by the Platform-Provided Foundation (§2) are NOT repeated here.*

<!-- @owned-by: phase5_requirements_enumeration | @role: business | @system-derives-from:  | @locked-by-chassis: false -->
### 4.1 Business Rules (BR)

*Project-specific business rules: calculations, decisions, and constraints, each with its condition, formula/constraint, logic ownership (§1.2), and failure behavior (HTTP status + message from the canonical catalog).*

---

<!-- @owned-by: phase5b_security_requirements, phase5_requirements_enumeration | @role: business | @system-derives-from:  | @locked-by-chassis: false -->
## 5. SECURITY & NON-FUNCTIONAL REQUIREMENTS

<!-- @owned-by: phase5b_security_requirements | @role: business | @system-derives-from:  | @locked-by-chassis: false -->
### 5.1 Application-Specific Security Requirements

*Security requirements BEYOND the inherited §2 baseline: domain compliance regimes (HIPAA/PCI-DSS/CJIS/IRS-1075), data-classification handling, field-level encryption, additional audit events, stricter session/lockout policy, additional permissions and their grant matrix. Each states the control, its enforcement location (chassis dependency, slot service, DB constraint), and the test that proves it. Items here may only add or tighten the §8 CONSTITUTION baseline; weakening requires a `(CHASSIS-OVERRIDE)` with justification.*

<!-- @owned-by: phase5d_ui_ux_design | @role: business | @system-derives-from:  | @locked-by-chassis: false -->
### 5.2 UI / UX Requirements

*Project-specific UI/UX: the pages/screens (Jinja2 templates), navigation flow, form fields and their validation messages, status badges, empty/loading/error states, accessibility specifics beyond the WCAG 2.1 AA baseline, and responsive behavior. Each maps to a persona journey from §3.2 and to FRs in §4.*

<!-- @owned-by: phase5_requirements_enumeration, phase5c_technical_architecture | @role: tech | @system-derives-from:  | @locked-by-chassis: false -->
### 5.3 Other Non-Functional Requirements (deltas only)

*Project-specific NFRs BEYOND the inherited baselines in §2.17. Record only deltas/additions (e.g. a stricter latency target, a domain compliance regime, a data-residency rule, an integration SLA). Each NFR states category, metric, target, measurement method, and enforcement location. Overrides of an inherited baseline MUST be annotated `(CHASSIS-OVERRIDE)`.*

---

<!-- @owned-by: phase6_specification_finalization | @role: system | @system-derives-from: REQUIREMENTS.md#4. FUNCTIONAL REQUIREMENTS (FR), DESIGN.md, TASKS.md, TEST-SCENARIOS.md | @locked-by-chassis: false -->
## 6. REQUIREMENT TRACEABILITY (MANDATORY)

Every project requirement maps to its realizing design section(s), task(s), test scenario(s), and (where relevant) the user personas and processes it serves.

| Requirement ID | Personas | Processes | Design | Tasks | Tests |
|---|---|---|---|---|---|

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## 7. AI GENERATION CONTRACT

When generating `DESIGN.md` and slot code, the AI MUST:
- Create a design section for EVERY project requirement ID in §3–§5.
- Build on the Platform-Provided Foundation (§2) — use the chassis capabilities; do NOT re-implement them.
- Implement domain logic only in `app/slots/<domain>/` and integrate only at the documented extension points (CONSTITUTION §7).
- Respect the chassis stack, invariants, security rules, and forbidden patterns from `CONSTITUTION.md`.
- NOT invent external services or APIs; STOP if an external integration's details are missing.

---

*This document was generated by the SD-Agile Spec Builder from the project's Golden Record, on the autonomous-platform-chassis-python foundation.*
