---
template: python-tasks
version: "3.0"
document_type: TASKS.md
locked_section_aware: true
---

# {{PROJECT_NAME}} — Tasks
<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## Platform Chassis — AI-Executable Task Breakdown (Python 3.12 · FastAPI · SQLAlchemy 2.0 async)

**Project:** {{PROJECT_NAME}}
**Foundation:** autonomous-platform-chassis-python (FastAPI · SQLAlchemy 2.0 async · Pydantic v2 · Alembic · PostgreSQL · Redis · USWDS)
**Generated From:** DESIGN.md
**Purpose:** Deterministic, chunkable task plan for implementation.

This document serves the **App Builder** (the work-list to implement the domain slots on the chassis) and a **human developer** (the build order, with or without the chassis — see the Foundation section). It MUST be mechanical, traceable, and executable.

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## Chassis Foundation (what is already built)

**Intent.** The chassis is pre-built, tested, and shipped. Implementation tasks below cover ONLY the project-specific **slots** (`app/slots/<domain>/`) — never the foundation. This section states the baseline so a human understands what exists (and need not be re-built).

**Already implemented by the foundation (do NOT create tasks for these):** identity & authentication (`app/auth/`, including mandatory TOTP MFA for platform-wide administrators in `app/auth/mfa.py`), RBAC (permissions/roles + `requires(...)` dependency), multi-tenancy (auto-filter via the `do_orm_execute` ORM event, auto-stamp via `before_flush`, both in `app/db.py`, driven by the `TenantScoped` mixin), audit (`app/audit/decorator.py:@audited` + append-only `audit_logs`/`audit_logs_archive`), administration shell (`app/admin/` server-rendered pages), observability (`/healthz` `/readyz` `/version` + System Health page, structlog JSON/console logging), in-app docs, embedded LLM (`app/llm/` crypto + transport + service, provider-neutral LiteLLM-compatible egress) and MCP client (`app/mcp/`), file storage (`app/files/`), notifications (`app/notifications/`), rate limiting (`app/ratelimit/middleware.py` + Redis), reporting (`app/admin/reports_service.py`), transactional mail (`app/mail/service.py`, console/fastapi-mail SMTP), background jobs (`app/tasks/` — RQ queue + worker), server-rendered USWDS UI (Section 508 / WCAG 2.1 AA), canonical error messages (`app/error_messages.py`), typed config/secrets (`app/config.py`, pydantic-settings), additive-only Alembic migrations.

**Per-slot build order (each domain):** MODEL (SQLAlchemy 2.0 typed models in `models.py` — inherit `TenantScoped` for tenant-owned tables; Pydantic v2 schemas in `schemas.py`) → MIGRATION (a new additive Alembic revision under `migrations/versions/`) → SERVICE (async business logic in `service.py` via injected `AsyncSession`, `@audited` on mutations, no HTTP imports) → API (thin `APIRouter` in `routes.py` gated by `requires("<resource>:<action>")`, registered at the `app/main.py` slot-routers marker; permissions registered at the `app/rbac/permissions.py` slot-permissions marker) → TEST (`pytest` + `pytest-asyncio`: happy path, 401, 403, cross-tenant 404, 422). Run with `uv run pytest`; boot with `uvicorn app.main:app`; apply migrations with `alembic upgrade head`; lint/type-check with `ruff check .` and `mypy --strict app`.

**Building without the chassis.** A human developer would first stand up the equivalent foundation (auth/RBAC/tenancy/audit/observability in FastAPI + SQLAlchemy), then implement these same per-slot tasks against it.

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## 1. TASK GENERATION CONTRACT (HARD RULES)

The AI generating this document MUST:

1. Create ≥1 task for EVERY **descriptive** Design section. **Contract** sections — those governing how the Design document itself is produced or shaped (e.g. its Generation Contract and Output Contract) — take **no task**, and MUST appear in the traceability matrix as an explicit "no task — contract section" row stating the reason. Omitting them yields a matrix that looks complete.
2. Preserve logic ownership and execution location.
3. Separate FastAPI application tasks from persistence (SQLAlchemy / Alembic) tasks.
4. Ensure tasks are independently executable.
5. Ensure tasks can be completed in isolation.
6. NEVER invent logic, services, or integrations.
7. STOP if any Design section is missing.

This document is INVALID if traceability is incomplete.

**Why rules 2, 4 and 5 exist.** Each task becomes **one LLM call with limited context**, so a task
must be completable and provable with exactly the context it is given: too little and the model
invents the missing half, producing mismatched names, types and signatures across tasks; too much and
it loses the part that mattered. Rules 4 and 5 are that criterion. Rule 2 is what keeps it
achievable — a task forced to reason about a decision another component owns has an incomplete
context **by construction**, so it decides for itself and the task next door decides differently.
Get this wrong in either direction and the per-file code does not compile because the files
contradict each other.


All code MUST be Python 3.12 with full type hints (`mypy --strict`), FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, Alembic, and pytest/pytest-asyncio. Dependencies are pinned in `pyproject.toml`/`uv.lock` (installed via `uv sync` or `uv pip install -r requirements.txt`); no dependency outside the locked set (CONSTITUTION §1) may be added.

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## 2. TASK TYPES (FIXED ENUMERATION)

Each task MUST be one of the following types:

- **MODEL** – SQLAlchemy models, Pydantic schemas
- **API** – FastAPI routers, endpoints
- **PAGE** – Server-rendered Jinja2 pages (template + route)
- **SERVICE** – Application business orchestration
- **INTEGRATION** – External service calls (`httpx.AsyncClient`)
- **PERSISTENCE** – SQLAlchemy session/engine usage, query helpers
- **MIGRATION** – Alembic schema changes
- **SECURITY** – AuthZ policy + permission registration
- **CONFIG** – Environment & deployment config
- **TEST** – Automated tests
- **DEPLOY** – Build & deployment steps

---

<!-- @owned-by:  | @role: system | @system-derives-from: DESIGN.md#4. DATA MODELS (APPLICATION-OWNED ONLY), DESIGN.md#7. API CONTRACTS (FASTAPI) | @locked-by-chassis: false -->
## 3. APPLICATION TASKS (PYTHON / FASTAPI)

{{#APP_TASKS}}
### TASK-APP-{{ID}}: {{TITLE}}

**Task Type:** {{TASK_TYPE}}

**Source Design Section:** {{DESIGN_SECTION}}

**Source Requirement IDs:** {{REQUIREMENT_IDS}}

**Target Path:** app/slots/{{DOMAIN}}/routes.py | app/slots/{{DOMAIN}}/schemas.py | app/slots/{{DOMAIN}}/service.py | app/slots/{{DOMAIN}}/templates/*.html (+ one router registration at the `app/main.py` slot-routers marker)

**Description:**
{{DESCRIPTION}}

**Inputs:**
- {{INPUTS}}

**Outputs:**
- {{OUTPUTS}}

**Dependencies:**
- {{DEPENDENCIES}}

**Acceptance Criteria:**
- Pydantic v2 models validate request/response payloads
- FastAPI router wired via dependency injection (`Depends`) and registered at the slot-routers marker
- Endpoint/page gated by the correct `requires(...)` permission
- {{ACCEPTANCE_CRITERIA}}

**Estimated Complexity:** Low | Medium | High

---
{{/APP_TASKS}}

---

<!-- @owned-by:  | @role: system | @system-derives-from: DESIGN.md#5. PERSISTENCE & DATA ACCESS (SQLALCHEMY) | @locked-by-chassis: false -->
## 4. PERSISTENCE TASKS (SQLALCHEMY / ALEMBIC)

This section is REQUIRED if any persisted entities exist in DESIGN.md.

{{#PERSISTENCE_TASKS}}
### TASK-DB-{{ID}}: {{TITLE}}

**Task Type:** PERSISTENCE | MIGRATION

**Source Design Section:** {{DESIGN_SECTION}}

**Source Requirement IDs:** {{REQUIREMENT_IDS}}

**Persistence Asset Type:** SQLAlchemy Model | Service-Layer Query | Alembic Migration

**Target Path:** app/slots/{{DOMAIN}}/models.py | migrations/versions/{{REVISION}}.py  (the chassis owns the async engine/sessionmaker in `app/db.py` — do not recreate it; slots only add `models.Base` subclasses)

**Description:**
{{DESCRIPTION}}

**Inputs (Schema):**
- {{INPUT_SCHEMA}}

**Outputs (Schema):**
- {{OUTPUT_SCHEMA}}

**Dependencies:**
- {{DEPENDENCIES}}

**Acceptance Criteria:**
- SQLAlchemy 2.0 declarative models with typed `Mapped[...]` columns; tenant-owned models inherit `TenantScoped`
- Alembic migration applies cleanly (`alembic upgrade head`) and is additive (never edits a committed migration); ships both `upgrade()` and `downgrade()`
- {{ACCEPTANCE_CRITERIA}}

---
{{/PERSISTENCE_TASKS}}

---

<!-- @owned-by:  | @role: system | @system-derives-from: DESIGN.md#6. INTEGRATION LAYER (APPLICATION → EXTERNAL SERVICES) | @locked-by-chassis: false -->
## 5. INTEGRATION TASKS (APPLICATION → EXTERNAL SERVICES)

{{#INTEGRATION_TASKS}}
### TASK-INT-{{ID}}: {{TITLE}}

**Task Type:** INTEGRATION

**Source Design Section:** {{DESIGN_SECTION}}

**Provider:** External REST API | Message Queue | Third-Party SaaS

**Endpoint / API:** {{ENDPOINT}}

**Target Path:** app/slots/{{DOMAIN}}/integrations/{{CLIENT_NAME_SNAKE}}.py (`httpx.AsyncClient`)

**Description:**
{{DESCRIPTION}}

**Client Implementation:**
- Use `httpx.AsyncClient` (async, `async with` context) for all outbound calls
- Never instantiate a client per-call in a hot path; share a client via a FastAPI dependency where appropriate
- LLM-shaped integrations route through the chassis `app/llm/service.py` + `app/llm/transport.py` (LiteLLM-compatible), never a direct provider SDK

**Error Handling:**
- Retries:
- Timeouts (`httpx.Timeout`):
- Fallback Behavior:

**Acceptance Criteria:**
- {{ACCEPTANCE_CRITERIA}}

---
{{/INTEGRATION_TASKS}}

---

<!-- @owned-by: phase5b_security_requirements | @role: tech | @system-derives-from: DESIGN.md#5B. SECURITY DESIGN (APPLICATION-SPECIFIC), DESIGN.md#5A. AUTHORIZATION & PERSONA DESIGN | @locked-by-chassis: false -->
## 6. SECURITY TASKS (AUTHZ & PERMISSIONS)

{{#SECURITY_TASKS}}
### TASK-SEC-{{ID}}: {{TITLE}}

**Task Type:** SECURITY

**Source Design Section:** DESIGN §5A / §5B

**Source Requirement IDs:** {{REQUIREMENT_IDS}}

**Target Path:** app/rbac/permissions.py (slot-permissions marker) | app/slots/{{DOMAIN}}/service.py (`@audited` decorator, field encryption)

**Description:**
{{DESCRIPTION}}

**Acceptance Criteria:**
- Each new permission registered at the `app/rbac/permissions.py` slot-permissions marker and auto-seeded by `seed_chassis_rbac` (no migration required)
- Persona→role→permission grants match DESIGN §5A
- Application-specific security controls (field encryption, extra `@audited(...)` events) realized per DESIGN §5B
- {{ACCEPTANCE_CRITERIA}}

---
{{/SECURITY_TASKS}}

---

<!-- @owned-by:  | @role: system | @system-derives-from: TEST-SCENARIOS.md#3. APPLICATION TEST SCENARIOS (PYTEST) | @locked-by-chassis: false -->
## 7. TEST TASKS (MANDATORY)

{{#TEST_TASKS}}
### TASK-TEST-{{ID}}: {{TITLE}}

**Task Type:** TEST

**Source Requirement ID:** {{REQUIREMENT_ID}}

**Test Level:** Unit | Integration | End-to-End

**Target Component:** Router | Service | Model | Schema | External Client

**Target Path:** app/slots/{{DOMAIN}}/tests/test_{{MODULE}}.py

**Description:**
{{DESCRIPTION}}

**Test Implementation:**
- Use `pytest` + `pytest-asyncio` (auto mode) with an ASGI `httpx.AsyncClient` for endpoint tests — never call route handler functions directly
- Use fixtures for the async DB session, app instance, and seed data
- Mock external `httpx` calls (`respx` or a recorded cassette); never hit a live third party

**Expected Result:**
{{EXPECTED_RESULT}}

---
{{/TEST_TASKS}}

---

<!-- @owned-by:  | @role: system | @system-derives-from: TASKS.md#3. APPLICATION TASKS (PYTHON / FASTAPI), DESIGN.md#7. API CONTRACTS (FASTAPI), REQUIREMENTS.md#3. FUNCTIONAL REQUIREMENTS (FR) | @locked-by-chassis: false -->
## 8. TASK TRACEABILITY MATRIX (HARD REQUIREMENT)

| Task ID | Requirement ID(s) | Design Section | Type | Owner |
|--------|------------------|----------------|------|-------|

Every Requirement ID MUST map to ≥1 task.

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## 9. CODE GENERATION GUIDANCE

The AI generating code MUST:

- Execute tasks in dependency order.
- Generate Python 3.12 code with full type hints (`mypy --strict` clean) and `ruff check` clean for ALL tasks.
- Place ALL domain code under `app/slots/<domain>/` (`models.py`, `schemas.py`, `service.py`, `routes.py`, `templates/`, `tests/`); integrate with the foundation ONLY at the marked extension points (`app/main.py` slot-routers marker, `app/rbac/permissions.py` slot-permissions marker) — never edit other chassis files.
- Run tests with `uv run pytest`; boot the app with `uvicorn app.main:app`; apply migrations with `alembic upgrade head`.
- Halt if a task cannot be completed.
- Attach tests immediately after implementation.

---

*This document was generated by the SD-Agile Spec Builder from the project's Golden Record, on the autonomous-platform-chassis-python foundation.*
