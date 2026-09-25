# Accessibility Assistant — Tasks

**Specification Version:** 1.6.0
**Generated:** 2026-09-25 16:46 EDT
**Approved By:** Joe Paiva, Alignment Authority

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

