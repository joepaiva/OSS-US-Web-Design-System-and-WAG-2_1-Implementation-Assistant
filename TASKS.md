# Accessibility Assistant — Tasks

## Platform Chassis — AI-Executable Task Breakdown (Python 3.12 · FastAPI · SQLAlchemy 2.0 async)

**Project:** Accessibility Assistant
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
### T-002 — Information Source Category Creation (FR-010)
<!-- @sd-req: FR-010 @rev: bdb6e278 @adopted -->
**Objective:** Enable administrators to create and manage information source categories with tenant-scoped uniqueness enforcement.

**Acceptance Criteria:**
- Platform Administrators and Organization Administrators can create categories via `POST /api/information-source-categories/`.
- Category names must be unique within the current organization.
- Duplicate names are rejected with `409 Conflict` before any database write.
- End Users and Content Managers receive `403 Forbidden`.

**Implementation Notes:**
- Service layer performs a scoped uniqueness check before insert via SQLAlchemy async query.
- The `TenantScoped` mixin auto-stamps `org_id` on the new row; no manual filtering is required.
- Route is decorated with `@audited("information_source_category:create")`.

---
### T-003 — Information Source Configuration (FR-011, FR-012, FR-013, FR-014)
<!-- @sd-req: FR-014 @rev: 9610143d @adopted -->
<!-- @sd-req: FR-013 @rev: 12300dc5 @adopted -->
<!-- @sd-req: FR-012 @rev: cbc98595 @adopted -->
<!-- @sd-req: FR-011 @rev: a3c6350a @adopted -->
**Objective:** Support configuration of four information source types (local code repo, GitHub/online repo, document folder, MCP Server) with type-specific validation and credential encryption.

**Acceptance Criteria:**
- `GET /api/information-sources/source-types` returns exactly four source types with form-variant hints.
- `POST /api/information-sources/` accepts source-type-specific payloads via Pydantic discriminated union.
- Local and document folder sources are validated for read access via `POST /api/information-sources/local/validate-access`.
- GitHub/online repo sources are verified via `POST /api/information-sources/github/verify`.
- MCP Server sources are tested via `POST /api/information-sources/mcp/test`.
- All credentials are encrypted at rest using AES-256-GCM per SR-001.
- No plaintext credential is ever logged or returned in API responses.

**Implementation Notes:**
- Pydantic v2 discriminated-union validation selects the correct schema per `source_type` at the framework boundary.
- Credential encryption delegates to `CredentialEncryptionService.encrypt()` before any ORM write.
- Read-access tests are performed twice: once before user confirmation and again at save time to prevent TOCTOU gaps.
- The no-execute rule is enforced structurally for local sources: `subprocess`, `exec`, `eval`, and shell primitives are forbidden imports.

---
### T-005 — Question Category Configuration (FR-015)
<!-- @sd-req: FR-015 @rev: 0bb00a61 @adopted -->
**Objective:** Enable administrators to create and manage question categories with tenant-scoped uniqueness enforcement.

**Acceptance Criteria:**
- Platform Administrators and Organization Administrators can create categories via `POST /api/question-categories/`.
- Category names must be unique within the current organization (case-insensitive check).
- Duplicate names are rejected with `409 Conflict`.
- End Users receive `403 Forbidden`.

**Implementation Notes:**
- Service layer performs a case-insensitive uniqueness check: `SELECT 1 FROM question_categories WHERE lower(name) = lower(:name) AND org_id = :current_org LIMIT 1`.
- The `TenantScoped` mixin auto-stamps `org_id`; no manual filtering is required.
- Route is decorated with `@audited("question_category:create")`.

---
### T-006 — Manual FAQ Creation (FR-016)
<!-- @sd-req: FR-016 @rev: 48c70502 @adopted -->
**Objective:** Allow Content Managers and Administrators to manually create FAQ entries with multi-select category and source associations.

**Acceptance Criteria:**
- `POST /api/faqs/` accepts question text, response text, and arrays of question category IDs, source category IDs, and source IDs.
- All required fields must be non-empty after stripping whitespace.
- All referenced UUIDs must exist within the current tenant's scope.
- Many-to-many associations are persisted in a single transaction.
- End Users receive `403 Forbidden`.

**Implementation Notes:**
- Pydantic v2 schema validates field presence and non-emptiness before the service is reached.
- Service layer resolves all UUIDs against the current tenant and raises `FAQValidationError` if any are unresolvable.
- The `TenantScoped` mixin auto-stamps `org_id` on the new FAQ row.
- Route is decorated with `@audited("faq:create")`.

---
### T-015 — Deterministic-First Question Answering (FR-007)
<!-- @sd-req: FR-007 @rev: dbf7d071 @adopted -->
**Objective:** Attempt FAQ matching and script execution before invoking the LLM.

**Acceptance Criteria:**
- `POST /api/questions/` first attempts FAQ matching via exact-match slug, keyword set, or regex pattern.
- If no FAQ match is found, applicable Python scripts are executed against configured information sources.
- If neither tier produces a sufficient answer, the LLM fallback tier is entered.
- The response includes a `source` field identifying the resolution tier (`faq`, `script`, or `llm`).

**Implementation Notes:**
- FAQ matching is performed in priority order: exact-match slug, keyword set, regex pattern.
- Script execution is sandboxed, async, and timeout-bounded per CONSTITUTION §Secrets.
- The `llm_invoked` field is set to `False` for deterministic answers and `True` for LLM-generated answers.
- Route is decorated with `@audited("question:resolve")`.

---
### T-016 — Tiered Answer Fallback with LLM RAG and Unanswerable Alert (FR-008)
<!-- @sd-req: FR-008 @rev: 2ecd247d @adopted -->
**Objective:** Orchestrate deterministic → LLM RAG/frontier → unanswerable resolution with in-app alert dispatch for unanswerable questions.

**Acceptance Criteria:**
- `POST /api/questions/answer` attempts deterministic resolution, falls back to LLM (RAG or frontier mode), and — if all tiers fail — dispatches an in-app alert to Organization Administrators and Content Managers.
- The response includes a `tier` field identifying the resolution tier.
- Unanswerable responses include `alert_sent: true` and a user-facing message.
- `GET /api/questions/alerts` returns unanswerable-question alerts for administrators.
- `PATCH /api/questions/alerts/{alert_id}/acknowledge` marks an alert as acknowledged.

**Implementation Notes:**
- The orchestration service invokes tiers in order: deterministic, LLM RAG/frontier, unanswerable.
- LLM calls route through the chassis single-egress endpoint.
- In-app alert dispatch is performed by `AlertDispatchService`, which creates alert records and enqueues RQ notification jobs.
- Routes are decorated with `@audited(...)`.

---
### T-017 — LLM Fallback Mode Configuration (FR-009)
<!-- @sd-req: FR-009 @rev: 1131754c @adopted -->
**Objective:** Enable administrators to configure per-(information source category, question type) LLM fallback modes (retrieval-augmented vs. frontier).

**Acceptance Criteria:**
- `GET /api/llm-fallback-config/` returns all configured fallback modes for the current tenant.
- `GET /api/llm-fallback-config/{category}/{question_type}` retrieves a single configuration.
- `PUT /api/llm-fallback-config/{category}/{question_type}` creates or updates a configuration.
- `DELETE /api/llm-fallback-config/{category}/{question_type}` removes a configuration.
- End Users receive `403 Forbidden` on write operations.

**Implementation Notes:**
- Configurations are persisted to a tenant-scoped `LLMFallbackConfig` table.
