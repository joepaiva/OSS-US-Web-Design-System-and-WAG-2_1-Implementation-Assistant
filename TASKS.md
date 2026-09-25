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
