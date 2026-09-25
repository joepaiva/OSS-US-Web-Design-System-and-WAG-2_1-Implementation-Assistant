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
### T-001 — User Authentication and Session Management

**Objective:** Establish and maintain secure user sessions for all authenticated interactions with the platform.

**Acceptance Criteria:**
- Users can authenticate via the chassis-provided authentication mechanism.
- Session tokens are validated on every request via `Depends(get_current_user)`.
- Unauthenticated requests to protected routes receive a `302` redirect to `/login`.
- Session context includes user identity, role, and organization membership.

**Implementation Notes:**
- Leverage the chassis `get_current_user` dependency for all authentication gates.
- No custom authentication logic is implemented in slot code; all auth is delegated to the chassis.
- Session state is managed by the chassis; application code reads `current_user` from the dependency context.

---

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
### T-004 — Information Source Credential Management (SR-001)

**Objective:** Persist and manage encrypted credentials for connected information sources with FIPS 140-2/140-3 compliance.

**Acceptance Criteria:**
- Credentials are encrypted using AES-256-GCM via the chassis-provided `cryptography` library.
- Only ciphertext is stored in the database; no plaintext credential column exists.
- Credential values are never logged at any log level.
- FIPS compliance is validated at encryption time; non-compliant algorithms raise `FIPSComplianceError` and abort the operation.
- Credential updates follow the same encryption path as creation.
- Credential retrieval routes exclude the ciphertext column from the query; a `credential_set: bool` indicator is returned instead.

**Implementation Notes:**
- `CredentialEncryptionService` is the sole encryption/decryption interface; no direct `cryptography` library calls are made in routes.
- The encryption key is sourced from the environment (never from the database or source code).
- Routes are decorated with `@audited(...)` for credential creation and updates.

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
### T-007 — Automated FAQ Generation from Interaction Logs (FR-017)
<!-- @sd-req: FR-017 @rev: da007aee @adopted -->
**Objective:** Enable administrators to trigger LLM-driven FAQ generation from interaction logs with human-approval gating.

**Acceptance Criteria:**
- `POST /api/faqs/generation-sessions/` initiates LLM review of interaction logs and persists candidates in `pending_review` status.
- `GET /api/faqs/generation-sessions/{session_id}/candidates/` returns candidates for human review with editable fields.
- `POST /api/faqs/generation-sessions/{session_id}/confirm/` persists only approved candidates to the `faqs` table.
- No FAQ row is written without an explicit confirmation payload.
- End Users receive `403 Forbidden`.

**Implementation Notes:**
- Candidates are staged in a transient `faq_generation_session` table; no approved FAQ entry is created until confirmation.
- The LLM call routes through the chassis single-egress endpoint per CONSTITUTION §Single LLM Egress.
- Confirmation is atomic: all approved candidates are inserted in a single transaction, or none are committed.
- Routes are decorated with `@audited(...)` for session creation and confirmation.

---
### T-008 — Automated FAQ Generation from Information Source (FR-018)
<!-- @sd-req: FR-018 @rev: b20ec7d5 @adopted -->
**Objective:** Enable administrators to trigger LLM-driven FAQ generation from a selected information source with human-approval gating.

**Acceptance Criteria:**
- `POST /api/faqs/generate` accepts an information source ID and returns LLM-generated FAQ candidates in-memory only (no persistence).
- `POST /api/faqs/generate/confirm` accepts approved candidates and persists them to the `faqs` table.
- No FAQ row is written without an explicit confirmation payload.
- End Users receive `403 Forbidden`.

**Implementation Notes:**
- The LLM call routes through the chassis single-egress endpoint.
- Candidates are returned in-memory; no staging table is used for this flow.
- Confirmation validates that all submitted candidates are structurally sound before bulk insertion.
- Routes are decorated with `@audited(...)` for generation and confirmation.

---
### T-009 — Self-Service Assistant Interface (FR-001)
<!-- @sd-req: FR-001 @rev: a85aa2ab @adopted -->
**Objective:** Serve a responsive, resizable assistant window to authenticated users via both desktop icon and embedded HTML link entry points.

**Acceptance Criteria:**
- `GET /assistant/` loads the assistant interface for authenticated users.
- Unauthenticated requests receive a `302` redirect to `/login`.
- The interface is responsive and resizable without horizontal scrolling.
- Both desktop icon and embedded HTML link entry points resolve to the same route.

**Implementation Notes:**
- The route calls `AssistantSessionService.get_or_create_session(user_id, org_id)` to establish or resume a session.
- The template is rendered via Jinja2 with USWDS 3.x grid and responsive utility classes.
- The route is read-only and is not decorated with `@audited`.

---
### T-010 — End-User Question Submission (FR-002)
<!-- @sd-req: FR-002 @rev: 6b45c791 @adopted -->
**Objective:** Accept end-user questions with a 200-character maximum and initiate the answer retrieval process.

**Acceptance Criteria:**
- `POST /api/assistant/questions` accepts a question of 1–200 characters (inclusive).
- Empty submissions or questions exceeding 200 characters are rejected with `422` before any retrieval or LLM call.
- Leading/trailing whitespace is stripped before length evaluation.
- The question is never logged in full.

**Implementation Notes:**
- Pydantic v2 schema enforces `min_length=1, max_length=200` on the `question` field.
- Validation errors are handled by FastAPI's default validation-error handler.
- Route is decorated with `@audited("assistant:question_submitted")`.

---
### T-011 — FAQ Category Browse and Answer View (FR-003)
<!-- @sd-req: FR-003 @rev: 78c83e3d @adopted -->
**Objective:** Enable end users to browse question categories and view FAQ answers.

**Acceptance Criteria:**
- `GET /api/categories/` returns all question categories for the current tenant.
- `GET /api/categories/{category_id}/faqs/` returns FAQs within a category.
- `GET /api/faqs/{faq_id}/` returns the full FAQ with complete answer text.
- Empty-state cases (no categories, no FAQs in a category) return `200` with empty lists.

**Implementation Notes:**
- All queries are tenant-scoped via the `TenantScoped` mixin.
- Results are ordered by display order or creation timestamp as defined in the data model.
- Routes are read-only and are not decorated with `@audited`.

---
### T-012 — Structured Question Response with Citations and Rating (FR-004)
<!-- @sd-req: FR-004 @rev: 4f9685ad @adopted -->
**Objective:** Return fully structured responses containing expository text, reasoning, source citations with hyperlinks, and a rating control scaffold.

**Acceptance Criteria:**
- `POST /api/questions/` returns a `QuestionResponse` with `answer`, `reasoning`, `citations`, and `rating` fields.
- Citations include `title`, `url` (absolute hyperlink), and optional `excerpt`.
- When no sources are found, `citations` is an empty array and `citations_available` is `false`.
- The `rating` scaffold contains `response_id`, `options: ["thumbs_up", "thumbs_down"]`, and `submitted: null`.
- `POST /api/questions/{response_id}/rating` records the user's rating.

**Implementation Notes:**
- The service assembles the response from LLM output and retrieval results before the route serialises it.
- Citation hyperlinks are constructed in the service layer, not the route.
- The response is persisted before the route returns so that `response_id` is stable for subsequent rating submission.
- Routes are decorated with `@audited(...)`.

---
### T-013 — Multi-Turn Conversational Context (FR-005)
<!-- @sd-req: FR-005 @rev: d9292930 @adopted -->
**Objective:** Maintain conversational context within a session and forward the full history to the LLM on each turn.

**Acceptance Criteria:**
- `POST /api/sessions/{session_id}/turns` accepts a user message, retrieves the accumulated context from Redis, forwards the full history to the LLM, and returns the assistant response.
- `DELETE /api/sessions/{session_id}` terminates a session and purges all conversational context.
- `POST /api/sessions/` creates a new session with an empty history.
- No cross-session context is ever loaded.

**Implementation Notes:**
- Session context is stored in Redis with a key pattern `conversation:{session_id}:history`.
- The history is passed as the `messages` array on every LLM call through the single LLM egress endpoint.
- Session termination deletes the Redis key unconditionally.
- Routes are decorated with `@audited(...)`.

---
### T-014 — Persistent Interaction Log Record Capture (FR-006)
<!-- @sd-req: FR-006 @rev: a99055fa @adopted -->
**Objective:** Persist structured log records for completed user interactions without surfacing write failures to the end user.

**Acceptance Criteria:**
- `POST /api/interactions/` accepts interaction details and persists them to the `interaction_logs` table.
- `datetime_group` is stamped server-side; client-supplied values are ignored.
- `question_category` and `rating` are stored as `NULL` when absent; no sentinel values are substituted.
- Database write failures are caught, logged, and not re-raised; the end user receives no error.
- `PATCH /api/interactions/{interaction_id}/rating` updates the rating field.

**Implementation Notes:**
- The service wraps the database write in a `try/except` block; exceptions are logged but not re-raised.
- The route is decorated with `@audited("interaction:log_created")` only on successful writes.
- Write-failure isolation is enforced: a `500` response is never returned for log-write failures.

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
### T-NNN — Question Submission PII and Source Code Sanitization (SR-002)
<!-- @sd-req: SR-002 @rev: edffe5f9 -->
<!-- @sd-req: SR-002 @rev: pending @adopted -->
**Objective:** Prevent PII and source code from reaching any external LLM API by intercepting and blocking non-compliant question submissions before any outbound payload is constructed or transmitted.

**Acceptance Criteria:**
- A question containing no PII and no source code is forwarded to the external LLM API and the user receives a normal response; the outbound payload is confirmed to contain neither PII nor source code.
- A question containing PII (e.g., a name, email address, phone number, or government identifier) is blocked before any LLM API call is initiated; the user receives an inline message instructing them to rephrase their question.
- A question containing source code (e.g., function definitions, code blocks, or language-specific syntax patterns) is blocked before any LLM API call is initiated; the user receives an inline message instructing them to rephrase their question.
- Ambiguous content flagged as potential PII by the sanitization filter is blocked and the user is prompted to rephrase; the filter errs on the side of caution.
- No partial or sanitized version of a blocked submission is forwarded to the LLM API; the block is total.
- Blocked submissions are never logged with their raw content in any structured log field that could be exported externally.

**Implementation Notes:**
- A `QuestionSanitizationService` in `app/slots/<domain>/service.py` performs PII and source code detection synchronously before the LLM egress call is constructed; it raises a domain exception (e.g., `SubmissionBlockedError`) on detection, which the route translates to an appropriate HTTP response without invoking `httpx.AsyncClient`.
- PII detection uses pattern-based heuristics (regex for email, phone, SSN, and similar patterns) plus any chassis-provided sanitization utilities; no external detection API is called, keeping the check in-process and latency-free.
- Source code detection uses structural heuristics (e.g., presence of keywords such as `def`, `class`, `function`, `import`, `{`, `;` in combination with indentation or bracket patterns) tuned to minimize false negatives.
- The filter is applied at the service boundary, not in the route, so it is enforced regardless of the call path (API or server-rendered form submission).
- The inline user-facing message is rendered via the existing Jinja2 template layer for server-rendered flows and as a structured error body for API flows; it does not disclose which specific pattern triggered the block.
- This requirement is application-owned; no chassis override is required. Logic lives exclusively in slot service code per the one-concern-per-module invariant.
- Linked to PERSONA-004 and PROC-006.

---
### T-XXX — Interaction Log PII Access Control and Cross-User Access Alerting (SR-003)
<!-- @sd-req: SR-003 @rev: 0e5d77e5 -->
<!-- @sd-req: SR-003 @rev: pending @adopted -->
**Objective:** Enforce PII-aware access control on interaction logs so that each user sees only their own records, administrators have read-only visibility across all organizations, all other roles are denied, and any cross-user access attempt triggers an in-app alert to the relevant Organization Administrator and Platform Administrator.

**Acceptance Criteria:**
- An authenticated End User requesting their own interaction logs receives only records whose `user_id` matches their own identity; no other user's records are disclosed.
- An authenticated End User who manipulates a record ID or `user_id` parameter to target another user's log receives a `403 Forbidden` response, zero records belonging to the target user, and an in-app alert dispatched to both the requesting user's Organization Administrator and the Platform Administrator.
- A Platform Administrator viewing the interaction logs section sees all logs across all organizations in read-only mode; no create, edit, delete, or alter controls are present in the UI or accepted by the API.
- A Content Manager (or any role without explicit log-read permission) attempting to access the administrator log view receives `403 Forbidden` and no log data.
- Any attempt by any role to modify or delete an interaction log entry — via UI or API — is rejected with `403 Forbidden`; the underlying log record remains byte-for-byte unchanged.

**Implementation Notes:**
- The service layer enforces ownership by comparing the requested `user_id` (or the `user_id` on the fetched record) against `current_user.id` from `Depends(get_current_user)` before returning any data; this check is not delegated to the ORM filter alone.
- Cross-user access attempts are detected in the service layer; on detection, `NotificationsService.send(...)` is called twice — once targeting the Organization Administrator of the requesting user's current org and once targeting the Platform Administrator — before the `403` is raised, so the alert is guaranteed even though no data is returned.
- Administrator read routes are gated with `Depends(require_permission("interaction_logs:read_all"))` and expose no mutation endpoints; `POST`, `PUT`, `PATCH`, and `DELETE` verbs on log resources return `405 Method Not Allowed` at the router level, making the read-only constraint structural rather than conditional.
- End User read routes are gated with `Depends(require_permission("interaction_logs:read_own"))`; the service applies a mandatory `WHERE user_id = :current_user_id` predicate in addition to the chassis `TenantScoped` auto-filter, preventing IDOR via record-ID manipulation.
- No log mutation service method exists in slot code; the absence of a write path is the primary control, supplemented by DB-role permissions that mirror the chassis append-only pattern for audit rows.
- All cross-user access attempts are themselves recorded via `@audited("interaction_log:unauthorized_access_attempt")` so the event appears in the platform audit trail.
- Interaction log records are classified as PII in inline model docstrings (`# PII: contains user_name, user_id, org_id`) to signal handling requirements to future maintainers.

---
### T-NNN — No-Execute Violation Alerting and Audit Integrity (SR-004)
<!-- @sd-req: SR-004 @rev: a0167166 -->
<!-- @sd-req: SR-004 @rev: pending @adopted -->
**Objective:** Ensure that every no-execute rule violation on a connected information source produces a durable, non-expiring in-app alert for the Platform Administrator and an immutable audit log entry, while enforcing strict access controls over that log.

**Acceptance Criteria:**
- When a no-execute rule violation is detected on a connected information source, an in-app alert is delivered to the Platform Administrator and a corresponding audit log entry is written in the same operation.
- The in-app alert persists indefinitely until explicitly read by the Platform Administrator; it does not expire and is present on subsequent logins if unread.
- Organization Administrators receive `403 Forbidden` when attempting to access the platform-level audit log; no audit log data is disclosed.
- Any attempt by any user to alter or delete an audit log entry for a no-execute event is rejected with an authorization error; the entry remains unchanged (enforced at the DB role level — no `UPDATE`/`DELETE` is permitted on `audit_logs` by the application role).

**Implementation Notes:**
- Violation detection in the information source slot service calls `NotificationService.create_alert(recipient_role="platform_admin", ...)` and the chassis `@audited("information_source:no_execute_violation")` decorator in the same transactional boundary; if either write fails the transaction rolls back entirely.
- Alert persistence delegates to the chassis `notifications` table (no TTL column set); the unread-count endpoint already surfaces unread alerts on login, satisfying the "present on subsequent login" criterion with no additional code.
- Platform-level audit log access is gated by `Depends(require_permission("audit_log:read_platform"))`; this permission is seeded only for the `platform_admin` role. Organization Administrator roles do not receive this permission, so the chassis RBAC dependency returns `403` automatically.
- Audit log immutability is a chassis-enforced DB invariant (`UPDATE`/`DELETE` revoked at the DB role on `audit_logs`); no additional slot code is required to satisfy the tamper-rejection criterion — this block documents reliance on that chassis guarantee rather than implementing a parallel control.
- Per PROC-002 and PERSONA-001, the alert payload must include: source identifier, timestamp of violation, and the specific rule triggered, so the Platform Administrator has sufficient context without consulting the audit log separately.

---
### T-019 — Response Helpfulness Rating (FR-019)
<!-- @sd-req: FR-019 @rev: 3be21550 -->
**Objective:** Allow authenticated end users to submit a single, immutable thumbs-up or thumbs-down rating against a received response, recorded on the corresponding interaction log record.

**Acceptance Criteria:**
- An authenticated End User can submit a rating via `POST /api/interaction-logs/{log_id}/rating` with a payload of `{"rating": "helpful"}` or `{"rating": "unhelpful"}`.
- The submitted rating is persisted and associated with the correct interaction log record for the requesting user's organization.
- A rating field that has not yet been set is stored and returned as `null`.
- Any attempt to submit a second rating for the same interaction log record — by any user or administrator, via the UI or API — is rejected with `409 Conflict`; the original rating remains unchanged.
- Any attempt to update or delete a submitted rating via any route is rejected with `409 Conflict` or `405 Method Not Allowed` as appropriate; no `PUT`, `PATCH`, or `DELETE` handler is exposed for the rating sub-resource.
- Unauthenticated requests receive `401 Unauthorized`; requests from users without the required permission receive `403 Forbidden`.

**Implementation Notes:**
- The `InteractionLog` model (or equivalent slot model) gains a `rating` column: `Mapped[Optional[str]]` with a DB-level `CHECK` constraint restricting values to `'helpful'`, `'unhelpful'`, and `NULL`; default is `NULL`.
- The service method checks whether `rating` is already non-null before any write; if non-null, it raises a domain exception that the route translates to `409 Conflict`. No UPDATE path for the rating field is exposed anywhere in the service layer.
- Immutability is enforced at two levels: (1) service-layer guard as above, and (2) no `PUT`/`PATCH`/`DELETE` route is registered for the rating sub-resource, making the constraint structural as well as logical.
- The `TenantScoped` mixin on the parent `InteractionLog` model ensures the `log_id` lookup is automatically filtered to the current organization; a record belonging to a different org returns `404 Not Found`, not `403`.
- The route is decorated with `@audited("interaction_log:rate")` to satisfy the chassis audit requirement for privileged mutations.
- The Pydantic request schema is a strict discriminated literal: `rating: Literal["helpful", "unhelpful"]`; any other value is rejected by the framework with `422 Unprocessable Entity` before the service is called.
- The response schema returns the updated interaction log summary including the now-set `rating` field; no separate rating resource is exposed.

---
### T-0XX — Platform-Level Resource Sharing (FR-020)
<!-- @sd-req: FR-020 @rev: 30daf8ec -->
<!-- @sd-req: FR-020 @rev: pending @adopted -->
**Objective:** Allow Platform Administrators to designate information sources, information source categories, and FAQs as platform-level shared resources that are visible in read-only mode to all Organization Administrators and Content Managers, with no edit or delete access granted to non-platform roles.

**Acceptance Criteria:**
- A Platform Administrator can mark any information source, information source category, or FAQ they created as platform-level shared via a dedicated endpoint (e.g., `PATCH /api/information-sources/{id}/share`, `PATCH /api/information-source-categories/{id}/share`, `PATCH /api/faqs/{id}/share`).
- Once marked shared, the resource is returned in list and detail responses for all Organization Administrators and Content Managers across every tenant, in read-only form.
- Attempts by an Organization Administrator or Content Manager to invoke any mutating operation (PUT, PATCH, DELETE) on a platform-level shared resource are rejected with `403 Forbidden`; the resource remains unchanged.
- Content Managers receive no edit or delete controls in server-rendered views for platform-level shared resources.
- Platform Administrators retain full edit and delete capability over resources they have shared.
- The `is_platform_shared` flag is reflected in all relevant list and detail response schemas so UI layers can suppress mutation controls client-side (server-side enforcement remains authoritative).

**Implementation Notes:**
- Add a non-null `is_platform_shared: Mapped[bool]` column (default `False`) to the ORM models for information sources, information source categories, and FAQs; deliver via an additive Alembic migration.
- Service layer `get` / `list` queries for Organization Administrator and Content Manager callers must include a `OR is_platform_shared = TRUE` predicate in addition to the normal `TenantScoped` auto-filter, so cross-tenant shared rows are surfaced without disabling the chassis tenancy event listeners for normal rows.
- A dedicated `platform_resource:share` permission is registered at the slot extension marker and granted only to the Platform Administrator role; the share endpoints are gated with `Depends(require_permission("platform_resource:share"))`.
- Mutation service methods (update, delete) for all three resource types must check `is_platform_shared` before proceeding; if `True` and the caller is not a Platform Administrator, raise `HTTP 403` before any ORM write.
- Share and unshare actions are decorated with `@audited("platform_resource:share")` and `@audited("platform_resource:unshare")` respectively.
- Because shared resources span tenants, the share endpoints must explicitly bypass the `TenantScoped` auto-filter when looking up the resource by ID; this is the only permitted deviation from automatic tenant isolation for this feature and must be isolated to the share service method with a clear inline comment.
- No plaintext cross-tenant data is exposed beyond the fields already present in the existing read schemas; no new PII surface is introduced.

---
### T-XXX — Administrator Interaction Log View (FR-021)
<!-- @sd-req: FR-021 @rev: c98ec3b0 -->
<!-- @sd-req: FR-021 @rev: pending @adopted -->
**Objective:** Provide Platform Administrators and Organization Administrators with a read-only view of interaction logs, scoped appropriately to their authority level, while denying access entirely to Content Managers and End Users.

**Acceptance Criteria:**
- `GET /api/interaction-logs/` is accessible only to Platform Administrators and Organization Administrators; all other roles receive `403 Forbidden`.
- Platform Administrators receive logs spanning all organizations (no `org_id` filter applied).
- Organization Administrators receive only logs whose `org_id` matches their current organization; cross-tenant rows are never returned.
- The response payload and any server-rendered view expose no edit or delete controls; the endpoint supports only `GET` (no `PUT`, `PATCH`, or `DELETE` siblings on this resource).
- Content Managers attempting to reach the interaction log view receive `403 Forbidden`.
- End Users attempting to reach the interaction log view receive `403 Forbidden`.

**Implementation Notes:**
- Route is gated with `Depends(require_permission("interaction_log:read"))`; the permission is seeded only for the Platform Administrator and Organization Administrator roles.
- Service method `InteractionLogService.list_logs()` accepts an optional `org_id` argument: when the caller is an Organization Administrator the current org context is passed; when the caller is a Platform Administrator the argument is omitted and the chassis `TenantScoped` auto-filter is bypassed via the established cross-tenant escape hatch (superuser short-circuit per §2.2 of REQUIREMENTS.md).
- No mutation methods (`create`, `update`, `delete`) are implemented on this service for this route; the router registers only the `GET` path operation.
- Server-rendered pages (Jinja2) for this view must not render edit/delete form elements or action buttons regardless of template context; the constraint is structural, not conditional.
- Linked to PROC-006; the log records surfaced here are those produced by PROC-006-related interactions.

---
### T-XXX — No-Execute Invariant for Connected Source Content (SR-005)
<!-- @sd-req: SR-005 @rev: 90d3e010 -->
<!-- @sd-req: SR-005 @rev: pending @adopted -->
**Objective:** Enforce a strict, unconditional no-execute rule at the code level so that content read from any connected information source is treated exclusively as read-only text context and is never executed, interpreted, or passed to any runtime, shell, or code-evaluation primitive — including under adversarial injection conditions.

**Acceptance Criteria:**
- Given a connected source containing executable code (Python scripts, shell commands, JavaScript, or any other executable form), when the system reads that source to answer a user question, the content is used as plain-text context only; no code interpreter, runtime, shell, or execution environment is invoked and no code from the source is executed.
- Given a connected source containing content crafted to trigger execution via injection (shell commands, `eval` expressions, script tags, or LLM prompt injections instructing the system to run code), when the system processes that content, the system reads it as plain text only; no execution occurs and no side effects from the injected payload are observable in the system or its outputs.
- Given any user role, API call, or system process that attempts to cause the system to execute code found in a connected source, when the attempt is made, the system does not execute the code under any circumstances; the no-execute invariant cannot be overridden by configuration, user input, or LLM output.
- Given an automated test that submits connected sources containing known executable payloads across multiple injection vectors (shell commands, `eval` expressions, script tags, prompt injections), when the system processes each payload, in every case the system returns a read-only context response with no execution side effects and all injection vectors are blocked.
- The no-execute rule applies to all four connected source types: Local Code Repo, GitHub/Online Repo, Document Folder, and MCP Server.

**Implementation Notes:**
- The no-execute rule is enforced structurally at the import level: `subprocess`, `exec`, `eval`, `os.system`, `os.popen`, `pty`, `shlex`, `shell=True` kwargs, and all equivalent shell-invocation primitives are forbidden imports in any module that reads or processes source content; the linter/CI gate treats their presence as a build failure.
- Source content is passed to the LLM layer exclusively as a string value inside a structured prompt context variable; it is never interpolated as code, never written to a file that is subsequently executed, and never passed to any function that accepts a callable or a code object.
- The LLM egress layer (single egress point per the chassis architectural invariant) must not relay source content in a position that instructs the model to produce or execute code on the system's behalf; prompt templates are reviewed and locked to enforce this.
- Prompt-injection resistance is addressed by clearly delimiting source content with structural markers (e.g., XML-style content tags) in every prompt template so the model can distinguish user instructions from source material; this is a defense-in-depth measure and does not substitute for the structural import-level enforcement above.
- Automated injection-vector tests (covering all four source types and all acceptance-criteria vectors) are included in the test suite and must pass in CI; any failure blocks merge.
- This requirement is linked to PERSONA-001, PERSONA-002, PERSONA-003, and PROC-002; no role or process may bypass the invariant.

---
### T-NFR-001 — LLM-Generated FAQ Explicit Approval Gate (NFR-001)
<!-- @sd-req: NFR-001 @rev: 3086c5a4 -->
<!-- @sd-req: NFR-001 @rev: pending @adopted -->
**Objective:** Ensure that no LLM-generated FAQ candidate is persisted to the database without an explicit, affirmative human confirmation action, regardless of how the review session ends.

**Acceptance Criteria:**
- If a review session ends (timeout, navigation away, explicit cancel, or any other termination path) without the user submitting an explicit save confirmation, zero FAQ entries are written to the database; all candidates remain in a transient pending state or are discarded entirely.
- Only after an authorized user explicitly submits a save confirmation are approved FAQ entries written to the `faq` table; unapproved candidates in the same session are not written.
- The pending/candidate state is never treated as an implicit approval; a missing or absent confirmation is always treated as rejection.
- All three linked personas (PERSONA-001, PERSONA-002, PERSONA-003) are subject to this gate; no role bypasses it.
- The gate applies to candidates generated from both interaction-log review (PROC-004) and information-source-derived generation (PROC-005).

**Implementation Notes:**
- Candidate FAQ entries are held in a transient server-side structure (e.g., a short-lived Redis key scoped to the session and org) and are never written to the primary `faq` ORM table until the explicit confirmation endpoint is called.
- The confirmation endpoint (`POST /api/faqs/candidates/{session_id}/approve`) is the sole write path to the `faq` table for LLM-generated content; the service layer raises a hard error if called without a valid, non-expired candidate session.
- Session expiry (TTL on the Redis key) results in candidate discard, not auto-save; the TTL is configurable via application settings and defaults to a value that covers a reasonable review window without persisting indefinitely.
- The service method that writes approved entries is decorated with `@audited("faq:create_from_llm_candidate")` so every approval action is recorded with actor, org, and the set of approved entry IDs.
- No background job, scheduled task, or RQ worker may promote candidate entries to confirmed entries; promotion is exclusively synchronous and user-initiated.

---
### T-XXX — LLM Payload Sanitization for External API Calls (SR-006)
<!-- @sd-req: SR-006 @rev: f46777a8 -->
<!-- @sd-req: SR-006 @rev: pending @adopted -->
**Objective:** Ensure that no PII (names, email addresses, user IDs) and no source code is ever included in request payloads dispatched to external Tier 2 LLM fallback APIs or automated FAQ generation LLM calls, so that sensitive data never crosses the system boundary.

**Acceptance Criteria:**
- When the system assembles a Tier 2 LLM fallback request payload, the payload contains no PII (names, email addresses, user IDs) and no source code before the request is dispatched.
- When the system assembles an automated FAQ generation LLM request payload, the payload contains no PII and no source code before the request is dispatched.
- When a sanitization check identifies PII or source code in an assembled payload, the offending content is stripped or the outbound call is blocked entirely before any data leaves the system boundary.
- Blocked or stripped calls are recorded in the structured application log (structlog JSON) with sufficient context to audit the event without logging the offending content itself.
- No plaintext PII or source code fragment appears in any log line, error response, or audit row produced during or after sanitization.

**Implementation Notes:**
- A `LLMPayloadSanitizer` service class (application-owned, `app/slots/llm_orchestration/service.py` or equivalent) is invoked as a mandatory step in the Tier 2 fallback and FAQ generation call paths before the payload is handed to the single LLM egress point (`app/llm/`); it is never bypassed.
- PII detection covers at minimum: RFC-5322 email addresses (regex), UUID-shaped user IDs, and display-name fields sourced from ORM user objects; source-code detection covers at minimum: file-path patterns and content drawn directly from information-source records.
- The sanitizer returns a typed result (`SanitizedPayload | SanitizationBlocked`); callers must handle both branches — there is no implicit pass-through.
- All LLM egress continues to route through the single chassis provider-neutral endpoint (`app/llm/`); the sanitizer operates on the assembled prompt/context dict before that handoff, not inside the chassis egress layer.
- Because `subprocess`, `exec`, `eval`, and shell primitives are forbidden imports in slot code (see T-003), no dynamic code execution may be used to implement detection logic.
- The sanitizer is covered by unit tests with fixtures that assert both the strip path and the block path for each category (PII, source code) across both call sites (Tier 2 fallback, FAQ generation).

---
### T-0XX — Interaction Log PII Classification and Access Control (SR-007)
<!-- @sd-req: SR-007 @rev: f2e1f389 -->
<!-- @sd-req: SR-007 @rev: pending @adopted -->
**Objective:** Enforce PII-aware access control on interaction logs so that each user sees only their own records, no user may mutate log content, and administrators are restricted to read-only views.

**Acceptance Criteria:**
- An authenticated End User requesting their own interaction logs receives only records whose `user_id` matches their identity; no other user's records are disclosed, regardless of query parameters supplied.
- Any attempt by any authenticated user to modify or delete an interaction log entry via the API (e.g., `PUT`, `PATCH`, `DELETE` against an interaction log resource) is rejected with `403 Forbidden`; the underlying log record remains unchanged.
- Platform Administrators and Organization Administrators may retrieve interaction logs in read-only mode; the API exposes no mutation endpoints for log records to any role, and the server-rendered UI renders no edit, delete, or alter controls for log entries regardless of the viewer's role.
- Requests from unauthenticated callers to any interaction log endpoint receive `401 Unauthorized`.
- Cross-user access attempts (e.g., an End User supplying another user's ID as a path or query parameter) return `403 Forbidden` or `404 Not Found`; no data belonging to the target user is disclosed.

**Implementation Notes:**
- The interaction log service layer enforces `user_id = current_user.id` as a mandatory, non-overridable filter on all read queries; it is not derived from request input.
- No `UPDATE` or `DELETE` route is defined for interaction log records in slot code; the absence of the route is the enforcement mechanism. The DB role for the application user must not hold `UPDATE`/`DELETE` privileges on the interaction log table, consistent with the append-only pattern used for `audit_logs`.
- Role-gated read access is enforced via `Depends(require_permission("interaction_log:read"))`; the permission is granted to the `admin` role (read-only) and to the `user` role scoped to own records only.
- Interaction log records are classified as PII in the data model (`pii_classified = True` annotation in the model docstring or a schema-level marker) to ensure future data-handling tooling (retention, export, anonymization) treats them accordingly, per PROC-006.
- The Jinja2 templates for administrator log views must not render edit or delete controls; template context must not pass any mutation URL for log entries.
- Service methods that return log data are decorated with `@audited("interaction_log:read")` only for administrator-initiated access, not for a user reading their own records, to avoid circular or excessive audit volume — confirm this distinction with the alignment authority before code generation if policy is ambiguous.
- Linked personas: PERSONA-001, PERSONA-002, PERSONA-003, PERSONA-004. Linked process: PROC-006.

---
### T-NNN — No-Execute Violation Alerting and Audit (FR-022)
<!-- @sd-req: FR-022 @rev: 1228e957 -->
<!-- @sd-req: FR-022 @rev: pending @adopted -->
**Objective:** Ensure that every no-execute rule violation on a connected information source immediately produces a durable, tamper-proof audit log entry and delivers a persistent in-app alert to the Platform Administrator, even when the administrator is offline at the time of the event.

**Acceptance Criteria:**
- When the no-execute rule is triggered on a connected information source, an in-app alert is created and routed to every Platform Administrator account within the current organization.
- The alert is persisted (via the chassis notifications subsystem) so it remains visible upon the Platform Administrator's next login; it does not expire before it is explicitly acknowledged.
- A corresponding audit log entry is written atomically with the alert; the entry records the event type, the affected source identifier, the actor context, the org, the client IP, and a UTC timestamp.
- If the Platform Administrator is not logged in when the violation occurs, the alert and audit log entry are both present and intact when the administrator subsequently authenticates.
- Any attempt by any user to alter or delete the audit log entry for a no-execute violation is rejected by the database role with an authorization error; the entry remains unchanged.
- `403 Forbidden` (or equivalent DB-level rejection) is returned to any caller attempting an UPDATE or DELETE against the `audit_logs` table for a no-execute event row.

**Implementation Notes:**
- Violation detection occurs inside the no-execute enforcement layer (see T-003); on detection, the service raises a structured `NoExecuteViolationError` that is caught by a dedicated handler in `service.py` — no HTTP imports enter the service layer.
- The handler calls `NotificationService.create_for_role(role="platform_admin", ...)` (chassis notifications subsystem) to fan out the alert to all Platform Administrator accounts in the org; no custom notification table is created.
- The audit entry is written via the chassis `@audited("information_source:no_execute_violation")` decorator (or an explicit `AuditService.record(...)` call if the violation path is not a normal route mutation), ensuring it lands in the append-only `audit_logs` table.
- Append-only enforcement is chassis-provided (DB role has UPDATE/DELETE revoked on `audit_logs`); no additional application-layer guard is required, but the service MUST NOT expose any delete or update path for these rows.
- The notification and audit write are performed within the same request-scoped async transaction where possible; if the violation is detected outside a normal request context (e.g., a background RQ job), the service opens its own `AsyncSession` and commits both writes before returning.
- Alert persistence (no expiry until acknowledged) is achieved by setting no TTL on the chassis notification record; the Platform Administrator's unread-count endpoint will reflect the alert on next login.
- Logic ownership: **Application-owned** (violation detection and fan-out orchestration in `app/slots/information_sources/service.py`); audit append-only enforcement is **Chassis-provided**.

---
### T-CON-001 — LLM API Routing via Chassis LiteLLM Integration (CON-001)
<!-- @sd-req: CON-001 @rev: 2378496e -->
**Objective:** Ensure all LLM invocations made by the application (Tier 2 fallback, automated FAQ generation, or any other purpose) are routed exclusively through the chassis LiteLLM integration, with no direct LLM provider API calls originating from application slot code.

**Acceptance Criteria:**
- When the system invokes an LLM for any purpose, the request is routed through the chassis LiteLLM integration; no direct call to an LLM provider endpoint is made by application code.
- Inspection of outbound network calls during any LLM operation reveals no direct provider API calls; all traffic passes through the LiteLLM proxy.
- When a Platform Administrator configures the LLM provider and API key in the chassis API configuration UI, subsequent LiteLLM-routed calls use that provider and key without any application code change.
- Any slot code that attempts a direct LLM provider import or HTTP call is treated as a build-time violation.

**Implementation Notes:**
- All LLM calls in slot code delegate to the chassis `app/llm/` integration; no provider SDK (e.g. `openai`, `anthropic`, `cohere`) is imported in any slot module.
- Provider identity and API key are resolved entirely from chassis-managed configuration (`llm_provider_keys` / `org_llm_access` tables); slot code passes only the prompt and call parameters.
- This requirement is an architectural invariant ("Single LLM egress") enforced by the chassis Constitution; no `(CHASSIS-OVERRIDE)` is present, so no deviation is permitted.
- Automated linting or import-guard tooling should flag any direct import of an LLM provider library as a forbidden import, consistent with the chassis forbidden-imports policy.

---
### T-CON-002 — Hosting Environment Compliance Constraints (CON-002)
<!-- @sd-req: CON-002 @rev: 779a689a -->
<!-- @sd-req: CON-002 @adopted -->
**Objective:** Ensure that the application imposes no constraints that would prevent deployment to a FedRAMP- and ITAR-compliant hosting environment, while deferring the selection of a specific hosting platform to deployment configuration.

**Acceptance Criteria:**
- When a hosting environment is evaluated, it must satisfy both FedRAMP and ITAR compliance requirements before the deployment is considered valid.
- The application itself does not hard-code or assume a specific hosting platform; all environment-specific configuration is supplied externally (environment variables, deployment manifests, or equivalent).
- A proposed deployment configuration that cannot satisfy FedRAMP or ITAR requirements is rejected at the configuration-review stage; no application code change is required to enforce this gate.
- Hosting platform selection remains a deployment-time decision and is fully deferred to the operator responsible for that environment.

**Implementation Notes:**
- No application slot code is added or modified by this requirement; compliance is a deployment-configuration concern, not an application-logic concern.
- The application's use of `pydantic-settings.BaseSettings` and environment-variable-driven configuration (per the chassis `config.py` contract) already ensures no platform is assumed at the code level — this requirement confirms that posture is sufficient and must not be weakened.
- Deployment reviewers (mapped to PERSONA-001) are responsible for verifying that the chosen hosting platform holds the necessary FedRAMP authorization and satisfies ITAR data-residency and access controls before approving a deployment configuration.
- This requirement produces no new routes, models, schemas, or tasks; it is a compliance constraint on the operational boundary of the application.

---
### T-CON-003 — ITAR Data Residency (CON-003)
<!-- @sd-req: CON-003 @rev: 91e92119 -->
<!-- @sd-req: CON-003 @adopted -->
**Objective:** Ensure all application data — interaction logs, configured credentials, FAQ content, and user data — remains within the United States both at rest and in transit to satisfy ITAR data residency requirements.

**Acceptance Criteria:**
- All persisted application data (interaction logs, configured credentials, FAQ content, and user data) is stored on infrastructure physically located within the United States.
- Data in transit between system components (e.g., application server to database, application to LLM API) does not traverse network paths or infrastructure located outside the United States.
- Any deployment configuration that routes data storage or transit outside the United States is rejected as non-compliant with ITAR data residency requirements.

**Implementation Notes:**
- This requirement is satisfied at the infrastructure and deployment-configuration level, not by application slot code; no new slot code is required to implement it.
- The application layer enforces the constraint indirectly: all external service calls (LLM provider, MCP servers, object storage) must be verified at deployment time to terminate on US-based endpoints; the `httpx.AsyncClient` base URLs for these integrations must be validated against approved US-region endpoints in the deployment configuration review process.
- Deployment configurations (environment variables, cloud region settings, and provider endpoint URLs) must be reviewed and approved before go-live; a configuration that specifies a non-US region or non-US endpoint is grounds for rejecting the deployment as non-compliant.
- No application data may be written to a cache, queue (Redis), object store, or database instance whose physical location is outside the United States; infrastructure provisioning documentation must attest to US-only placement.
- Audit log entries (chassis-provided, append-only) are subject to the same residency constraint; the PostgreSQL instance hosting `audit_logs` must reside in a US region.

---
### T-NFR-002 — LLM Provider Selection and Routing Delegation (NFR-002)
<!-- @sd-req: NFR-002 @rev: 4cd335bf -->
<!-- @sd-req: NFR-002 @adopted -->
**Objective:** Ensure that LLM provider selection, endpoint configuration, and API key management are entirely at the Platform Administrator's discretion via the chassis API configuration UI, with the application imposing no additional constraints on which provider or endpoint is used.

**Acceptance Criteria:**
- A Platform Administrator can select any LLM provider and enter an API key through the chassis API configuration UI without requiring any application code change.
- All subsequent LiteLLM-routed calls use the provider and key configured in the chassis UI immediately after configuration.
- The application makes no direct provider API calls; all LLM calls are routed exclusively through the chassis LiteLLM integration.
- No application-layer allow-list, deny-list, or validation logic restricts which LLM provider or endpoint may be selected.

**Implementation Notes:**
- This requirement is **chassis-provided**: the chassis `app/llm/` module owns all LiteLLM routing, provider key storage (`llm_provider_keys` table), and org-level access control (`org_llm_access` table). Application slot code has no involvement in provider selection or key management.
- Slot code that needs an LLM completion calls the chassis-provided LLM service interface; it does not import any provider SDK directly (enforced by the "Single LLM egress" architectural invariant in CONSTITUTION.md).
- No slot model, schema, service, or route is created for this requirement; it is satisfied entirely by chassis configuration and use.

---
### T-0XX — Tenant Data Isolation Enforcement (FR-025)
<!-- @sd-req: FR-025 @rev: ef39f336 -->
<!-- @sd-req: FR-025 @rev: pending @adopted -->
**Objective:** Ensure that Organization Administrators and Content Managers can never view, access, or act on data belonging to another organization, with the sole exception of platform-level shared resources (Information Source Categories, Information Sources, and FAQs) explicitly designated as shared by a Platform Administrator.

**Acceptance Criteria:**
- Any authenticated Organization Administrator or Content Manager who attempts to access a resource belonging to a different organization receives a `404 Not Found` (cross-tenant "not found" per chassis isolation contract); no cross-org data is disclosed in the response body or error detail.
- Platform-shared Information Source Categories, Information Sources, and FAQs designated as shared by a Platform Administrator are visible in read-only mode to Organization Administrators and Content Managers across all organizations.
- No edit, delete, or mutation controls are presented or accepted for platform-shared resources when the requesting user belongs to a different organization than the owning tenant; `PUT`, `PATCH`, and `DELETE` requests against shared-but-not-owned resources return `403 Forbidden`.
- All tenant-scoped list endpoints return only records belonging to the current organization; shared platform resources are appended or unioned into results without exposing their owning org's other data.
- Automated tests confirm that a token issued for Org A cannot retrieve, mutate, or enumerate records created under Org B, even when the record ID is known.

**Implementation Notes:**
- Primary isolation is enforced automatically by the chassis `TenantScoped` mixin and its SQLAlchemy event listeners; no hand-filtering by `org_id` is required or permitted in slot service code for tenant-owned resources.
- Platform-shared resources are distinguished by a `is_platform_shared: Mapped[bool]` flag (default `False`) set exclusively via a Platform Administrator action; service-layer queries union the org-scoped rows with rows where `is_platform_shared IS TRUE` using a single `or_()` clause, preserving the auto-filter for all other conditions.
- Write paths for shared resources check `current_user.org_id == record.org_id` (or equivalent ownership assertion) in the service layer before any mutation; a failed check raises `PermissionDeniedError`, which the error handler maps to `403 Forbidden`.
- Response schemas for shared resources include a read-only `is_platform_shared` boolean field; the frontend uses this flag to suppress edit and delete controls without relying on client-side role checks.
- No new bypass of the chassis tenancy context var is introduced; the shared-resource union is the only sanctioned exception to automatic org-scoping, and it is implemented in a single shared utility query helper to avoid per-route drift.
- Routes that surface shared resources are decorated with `@audited("shared_resource:read_cross_org")` only when a cross-org shared record is returned, to maintain an accountability trail without flooding the audit log with routine same-org reads.

---
### T-NEW-FR026 — Prohibition of User Impersonation by Administrators (FR-026)
<!-- @sd-req: FR-026 @rev: ff1ef144 -->
<!-- @sd-req: FR-026 @rev: pending @adopted -->
**Objective:** Ensure that Platform Administrators and Organization Administrators cannot assume, impersonate, or act under another user's identity; all administrative actions must be traceable exclusively to the authenticated administrator's own session.

**Acceptance Criteria:**
- No API endpoint or UI surface exposes an "act as user," "switch identity," or session-transfer capability to any role, including Platform Administrators and Organization Administrators.
- Any request that attempts to substitute or override the authenticated identity (e.g., passing a surrogate user ID in a header, query parameter, or request body to elevate or shift actor context) is rejected with `403 Forbidden`.
- The audit record for every administrative action carries the administrator's own `user_id`; no mechanism allows a different `user_id` to be written as the actor.
- Authenticated requests from Platform Administrators (`PERSONA-001`) and Organization Administrators (`PERSONA-002`) that attempt impersonation receive an authorization error with no partial side-effects.

**Implementation Notes:**
- No impersonation endpoint is introduced in any slot router; the requirement is satisfied structurally by the chassis `get_current_user` dependency, which resolves actor identity exclusively from the validated JWT — there is no supported path to override it from request payload.
- The `@audited(...)` decorator sources the actor from the chassis `current_user_id_var` context variable, which is set once per request by the authentication middleware and is never writable by slot code; this makes audit-actor substitution impossible without a `(CHASSIS-OVERRIDE)`.
- Slot service methods must not accept a `user_id` parameter intended to represent "the acting user"; if a target `user_id` is needed (e.g., to look up a subject), it must be named and typed unambiguously as a subject identifier, never as an actor override.
- No `(CHASSIS-OVERRIDE)` is permitted for this requirement; any future proposal to add impersonation capability must be treated as a new, separately reviewed security requirement.

---
### T-XXX — Platform-Level Sharing Eligibility Enforcement (FR-027)
<!-- @sd-req: FR-027 @rev: 101c5a23 -->
<!-- @sd-req: FR-027 @rev: pending @adopted -->
**Objective:** Ensure that only resources originally created by a Platform Administrator may be designated as platform-level shared, and that resources created by Organization Administrators or Content Managers can never be promoted to platform-level shared status by any user.

**Acceptance Criteria:**
- When a Platform Administrator attempts to designate as platform-level shared any information source, information source category, or FAQ whose `created_by` user does not hold the Platform Administrator role, the request is rejected with `403 Forbidden`; the resource's sharing status and `org_id` scoping remain unchanged.
- When a Platform Administrator designates a resource whose `created_by` user holds the Platform Administrator role as platform-level shared, the operation succeeds; the resource becomes visible in read-only mode to all Organization Administrators and Content Managers across all tenants.
- No other role (Organization Administrator, Content Manager, End User) may invoke the platform-level sharing designation endpoint; such requests receive `403 Forbidden`.
- The eligibility check is enforced server-side in the service layer on every promotion request; client-supplied claims about creator role are never trusted.
- Resources created by an Organization Administrator or Content Manager are permanently ineligible for platform-level sharing; no subsequent role change of the creator retroactively alters eligibility.

**Implementation Notes:**
- Each eligible model (`InformationSource`, `InformationSourceCategory`, `FAQ`) stores a non-null `created_by_user_id` FK to `users`; the service layer resolves the creator's platform role via the chassis RBAC query before any promotion write.
- The service method (e.g., `promote_to_platform_shared(resource_id, current_user)`) performs two sequential checks: (1) `current_user` holds the Platform Administrator role; (2) the resource's `created_by_user_id` resolves to a user who held Platform Administrator role at creation time — recorded in a non-nullable `creator_role_snapshot` column (`VARCHAR`, set once on insert, never updated) to avoid retroactive eligibility drift.
- If either check fails, the service raises `PermissionDeniedError`, which the exception handler maps to `403 Forbidden`; no partial write occurs.
- The promotion route is decorated with `@audited("resource:promote_platform_shared")` so every attempt — successful or rejected — produces an append-only audit row containing the resource type, resource id, actor, and outcome.
- Read-only visibility to all tenants is implemented by a nullable `platform_shared` boolean column (default `False`) on each eligible model; chassis tenant-scoping event listeners are bypassed for reads when `platform_shared IS TRUE`, using an explicit ORM query path that does not apply the `org_id` filter — this is the sole, narrowly scoped deviation from automatic tenant isolation and must be documented as such in `DESIGN.md`.
- No UI control for the promotion action is rendered for resources whose `creator_role_snapshot` is not `platform_admin`; this is a progressive-disclosure convenience only and does not substitute for server-side enforcement.

---
### T-0XX — LLM Unavailability Graceful Degradation and Role-Specific Alerting (CON-004)
<!-- @sd-req: CON-004 @rev: bfe0c28e -->
<!-- @sd-req: CON-004 @rev: pending @adopted -->
**Objective:** Ensure the system degrades gracefully to FAQ browse-only mode when the External LLM API is unavailable after all retries are exhausted, and delivers failure-type-specific in-app alerts to End Users, Organization Administrators, and Platform Administrators.

**Acceptance Criteria:**
- When the External LLM API returns a rate-limit error and all 3 retries are exhausted, the End User receives an in-app message stating the AI assistant is temporarily unavailable due to rate limiting; Organization Administrators and Platform Administrators each receive an in-app alert specifying `"rate limit exceeded"`; FAQ browse-only mode remains accessible.
- When the External LLM API returns an authentication failure (on any attempt), the End User receives an in-app message indicating a configuration issue with the AI assistant; Organization Administrators and Platform Administrators each receive an in-app alert specifying `"authentication failure"`; FAQ browse-only mode remains accessible.
- When the External LLM API times out after 20 seconds and all 3 retries are exhausted, the End User receives an in-app message stating the AI assistant is temporarily unavailable; Organization Administrators and Platform Administrators each receive an in-app alert specifying `"service timeout"`; FAQ browse-only mode remains accessible.
- No LLM-dependent feature is presented as available to any role while the API is in a degraded state.
- Alert messages are distinct per failure type; a generic fallback message is never substituted when a specific failure type is known.

**Implementation Notes:**
- The LLM egress layer (routed through the chassis single LLM egress point per CONSTITUTION.md) raises typed exceptions — e.g., `LLMRateLimitError`, `LLMAuthenticationError`, `LLMTimeoutError` — that the orchestration service catches and maps to the appropriate degradation path.
- Retry logic (3 attempts, 20-second per-attempt timeout) is owned by the application orchestration layer wrapping the chassis LLM client; it must not be duplicated inside the chassis egress module.
- On final failure, the service calls the chassis `notifications` subsystem to fan out in-app alerts: one scoped to the requesting user (End User message) and one broadcast to all Organization Administrator and Platform Administrator roles within the current org (admin alert with the specific failure-type label).
- The failure-type label passed to the notification payload must be one of the enumerated strings: `"rate limit exceeded"`, `"authentication failure"`, `"service timeout"`; the service maps exception type to label before dispatch.
- FAQ browse-only mode is activated by returning a degraded-state response flag from the service layer; the route layer and Jinja2 template suppress AI assistant UI affordances and render the FAQ browse view when this flag is set.
- This task is linked to `PROC-006`; the degradation path must be exercised as part of that process flow's error branch.
- No retry is performed for `LLMAuthenticationError`; it is treated as immediately terminal and triggers the alert and degradation path on first occurrence.

---
### T-CON-005 — GitHub / Online Repository Retry Exhaustion Alerts (CON-005)
<!-- @sd-req: CON-005 @rev: 42daa086 -->
<!-- @sd-req: CON-005 @rev: pending @adopted -->
**Objective:** Ensure that when the GitHub / Online Repository integration exhausts all retry attempts due to timeout or error, the system surfaces a failure-type-specific message to the requesting user and dispatches failure-type-specific in-app alerts to both the Organization Administrator and Platform Administrator.

**Acceptance Criteria:**
- The retry policy makes exactly 3 attempts with a 1-second delay before the second attempt and a 3-second delay before each subsequent attempt; no further attempts are made after the third.
- A 20-second per-attempt timeout is enforced; expiry of that timeout on the final attempt is treated as a terminal timeout failure.
- On terminal timeout failure, the requesting user receives a timeout-specific error message (distinct from other failure messages); in-app alerts with the description `"service timeout"` are dispatched to every user holding the Organization Administrator role in the current org and every user holding the Platform Administrator role.
- On terminal authentication failure, the requesting user receives an auth-failure-specific error message; in-app alerts with the description `"authentication failure"` are dispatched to the same administrator audiences.
- Each failure type maps to a distinct, non-generic user-facing message; no failure type may fall through to a generic catch-all message.
- In-app alerts are delivered via the chassis notifications system and appear in the recipient's unread notification count.
- No credential material, raw exception stack trace, or internal URL is included in any user-facing message or notification payload.

**Implementation Notes:**
- Retry orchestration is implemented in the GitHub integration service layer (`app/slots/information_sources/service.py`) using `httpx.AsyncClient` with `timeout=httpx.Timeout(20.0)` and a manual retry loop (no third-party retry library, per the locked dependency list); `asyncio.sleep` provides the inter-attempt delays.
- A `GitHubIntegrationError` exception hierarchy distinguishes `GitHubTimeoutError` and `GitHubAuthError` (and any other typed subclasses); the route layer catches the base type and re-raises after the service layer has already dispatched notifications, keeping route handlers thin.
- After the final failed attempt the service calls the chassis `NotificationService` (or equivalent chassis notification dispatch utility) once per target administrator, passing the failure-type-specific `title` and `body`; administrator recipients are resolved by querying memberships for the current org filtered to the `org_admin` role plus the platform-level `admin` role — this query is performed inside the service, not the route.
- User-facing error messages are defined as named constants in a `messages.py` module within the slot to prevent ad-hoc string literals and to facilitate future i18n.
- The retry loop, delay values, timeout threshold, and maximum attempt count are sourced from application settings (`pydantic-settings`) so they can be adjusted without code changes; the values stated in CON-005 are the required defaults.
- This logic is covered by process PROC-002; the route is decorated with `@audited("information_source:github_verify_failed")` so terminal failures are recorded in the audit log with the failure type captured in the structured `details` field.

---
### T-0XX — MCP Server Integration Failure Handling and Alerting (CON-006)
<!-- @sd-req: CON-006 @rev: 0d24c41c -->
<!-- @sd-req: CON-006 @rev: pending @adopted -->
**Objective:** Ensure that when an MCP Server integration exhausts its retry budget (3 attempts, with a 1-second delay before the second attempt and a 3-second delay before subsequent attempts) due to timeout or error, the system surfaces a failure-type-specific message to the requesting user and dispatches failure-type-specific in-app alerts to both the Organization Administrator and Platform Administrator.

**Acceptance Criteria:**
- The MCP Server integration client retries up to 3 total attempts, with a 1-second delay before the second attempt and a 3-second delay before any subsequent attempt.
- A 20-second per-attempt timeout is enforced; exhausting all retries under timeout conditions triggers a `service timeout` failure path.
- An authentication failure returned by the MCP Server (on any attempt) triggers an `authentication failure` failure path immediately without consuming remaining retries.
- On the `service timeout` path, the user receives a timeout-specific error message distinct from all other failure messages.
- On the `authentication failure` path, the user receives an auth-failure-specific error message distinct from all other failure messages.
- On either failure path, an in-app alert is dispatched to every user holding the Organization Administrator role within the current organization, and to every user holding the Platform Administrator role, with the alert body specifying the exact failure type (`service timeout` or `authentication failure`).
- No generic or untyped error message is shown to the user when a typed failure path is available.
- In-app alerts are delivered via the chassis notifications subsystem (`app/notifications/`); no custom notification transport is introduced.

**Implementation Notes:**
- Retry orchestration and delay logic live in `app/slots/mcp_integration/service.py`; the route layer receives only the final typed result or raises a typed exception — it contains no retry logic.
- Failure types are represented as a Python `enum` (e.g., `MCPFailureType.SERVICE_TIMEOUT`, `MCPFailureType.AUTH_FAILURE`) so that message selection and alert body construction are driven by a single dispatch rather than ad-hoc string comparisons.
- The `httpx.AsyncClient` call is wrapped with `asyncio.wait_for` (or equivalent) to enforce the 20-second per-attempt timeout; a caught `asyncio.TimeoutError` increments the attempt counter and applies the appropriate inter-attempt delay via `asyncio.sleep`.
- Authentication failure is detected from the MCP Server HTTP response status (e.g., `401`/`403`) or a typed error payload; the service raises `MCPAuthFailureError` immediately on first detection without further retries.
- Alert dispatch is performed after the final failure is determined, before the response is returned to the caller, using the chassis `NotificationService` (or equivalent chassis-provided async helper); the call is fire-and-forget wrapped in a background task so alert latency does not extend the user-facing response time.
- Alert recipients are resolved by querying the chassis RBAC tables for users holding `platform_admin` (system-wide) and `org_admin` (current-org-scoped) roles at dispatch time; no hardcoded user list is used.
- The route returns an appropriate `4xx`/`5xx` HTTP status alongside the typed message: `504 Gateway Timeout` for `SERVICE_TIMEOUT`, `502 Bad Gateway` for `AUTH_FAILURE` (or as specified in the broader API contract; align with the existing error-handler conventions in `app/error_handlers.py`).
- Structured log entries (via `structlog`) are emitted at `ERROR` level for each failed attempt and at `CRITICAL` level on final exhaustion, including attempt number, failure type, and (redacted) MCP Server identifier; no credentials or tokens are logged.
- This task is linked to `PROC-002`.

---

