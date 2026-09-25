# Accessibility Assistant — Design

**Specification Version:** 1.6.0
**Generated:** 2026-09-25 16:46 EDT
**Approved By:** Joe Paiva, Alignment Authority

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## Platform Chassis — AI-Executable Design Specification (Python 3.12 · FastAPI · SQLAlchemy 2.0 async)

**Project:** Accessibility Assistant
**Foundation:** autonomous-platform-chassis-python (FastAPI · SQLAlchemy 2.0 async · Pydantic v2 · Alembic · PostgreSQL · Redis · USWDS)
**Generated From:** CONSTITUTION.md + REQUIREMENTS.md
**Alignment Authority:** Joe Paiva
**Purpose:** Deterministic blueprint for TASKS.md, TEST-SCENARIOS.md, and code generation.

This document serves two readers: the **App Builder** (generating slot code on the chassis — see the Foundation section for the architecture/contract it builds within) and a **human developer** (understanding the system in FastAPI / SQLAlchemy terms, with or without the chassis). It MUST be complete, traceable, and executable; it is not creative.

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## 1. DESIGN GENERATION CONTRACT (HARD RULES)

The AI generating this document MUST:

1. Create exactly one design section for EVERY Requirement ID.
2. Preserve logic ownership declared in REQUIREMENTS.md.
3. Define every persisted entity as a SQLAlchemy 2.0 declarative model (`Mapped[...]` / `mapped_column(...)`) AND expose its request/response shapes as immutable Pydantic v2 schemas — never expose ORM models directly over the API.
4. Express every HTTP endpoint as a FastAPI path operation on an `APIRouter`, with explicit Pydantic request/response models, dependency injection via `Depends`, and explicit status codes.
5. Use Python type hints on every function signature (`mypy --strict` clean); the only ORM permitted is SQLAlchemy 2.0 and the only migration tool is Alembic.
6. Declare all integration points to external services explicitly (async `httpx.AsyncClient`).
7. NEVER invent requirements, services, APIs, or rules.
8. STOP generation if required information is missing.

This document is INVALID if any requirement is not represented.

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## Chassis Architecture & Realization (Foundation)

**Intent.** The application is a set of domain **slots** running on the pre-built, hardened Python chassis. This section is the architectural baseline the project design builds on — concrete enough that a human developer understands the structure with or without the chassis, and the App Builder knows exactly what already exists (so it does not re-create it).

### Module layout
Chassis-owned modules (do not edit except at extension markers); domain code lives only under `app/slots/<domain>/`:
```
app/
  main.py              # app factory (create_app), middleware, router registration, lifespan, extension markers
  config.py            # Settings (pydantic-settings) + validators
  db.py                # Base, async engine + sessionmaker, SessionDep, TenantScoped mixin, tenancy event listeners, context vars
  deps.py              # get_current_user/CurrentUser, get_current_org/CurrentOrg, requires(perm), ACCESS_TOKEN_COOKIE
  deps_context.py      # current_org_id_var, current_user_id_var, current_client_ip_var (+ get/set)
  logging.py           # configure_logging (structlog: JSON prod / console dev), get_logger
  error_handlers.py error_messages.py frontend.py
  auth/  rbac/  orgs/  audit/  health/  mail/  tasks/  llm/  mcp/  files/  notifications/  ratelimit/  admin/
  templates/  static/
  slots/<domain>/      # ← models.py schemas.py service.py routes.py tests/   (the ONLY place project code goes)
migrations/versions/   # ordered, additive-only Alembic migrations (slot tables add new ones)
tests/                 # pytest + pytest-asyncio, ASGI httpx.AsyncClient
```
Per slot: `models.py` (SQLAlchemy 2.0 typed models), `schemas.py` (immutable Pydantic v2 request/response), `service.py` (business logic, **no HTTP imports**, injected `AsyncSession`), `routes.py` (thin `APIRouter`) and/or a slot `templates/` subtree for server-rendered pages.

### Chassis-provided data (slots reference, never redefine)
All timestamps are timezone-aware (`DateTime(timezone=True)`, server-defaulted to `now()`; `updated_at` uses `onupdate=now(UTC)`). Slot models that are tenant-owned inherit the `TenantScoped` mixin (`app/db.py`) — it adds an indexed, non-null `org_id` FK to `organizations`, auto-filtered on read and auto-stamped on write by SQLAlchemy event listeners (see §6.3 realization below). Chassis tables include: `users` (+ `mfa_backup_codes`), `permissions`/`roles`/`role_permissions`/`user_roles`, `organizations`/`memberships`, `audit_logs` (+ `audit_logs_archive`, append-only, UPDATE/DELETE revoked at the DB role), `llm_provider_keys`/`org_llm_access`, `mcp_server_connections`, `file_objects`, `notifications`. Slot models FK to `users`/`organizations` as needed; they do NOT re-create identity, tenancy, audit, files, or notifications.

### Chassis-provided endpoints (slots add to, never duplicate)
Health: `GET /healthz` `/readyz` `/version`. Auth: `POST /auth/register` `/auth/login` `/auth/logout`, `GET /auth/me`. Orgs: `POST|GET /orgs`, `GET|PUT /orgs/me`. Files: `/api/files` (list/upload/download/delete, org-scoped). Notifications: `/api/notifications` (list/unread-count/read/read-all). Admin HTML shell: `/admin/*` (users, orgs, system-health, platform-health, fisma-audit, reports, docs, llm, mcp). Frontend HTML: `/`, `/dashboard`, `/auth/login|register`, `/account`. Slot routers mount under their own prefixes via the `# --- slot routers ---` extension marker in `app/main.py`.

### Request lifecycle
Request-id + client-IP middleware (binds `X-Request-ID` to structlog contextvars, binds `current_client_ip_var` from `X-Forwarded-For`/peer) → optional rate-limit middleware (`app/ratelimit/middleware.py`, installed only when enabled) → CORS → exception handler (`error_handlers.py:prod_exception_handler`, SI-11: generic message + correlation id in prod, full detail always logged). Authenticated routes resolve `CurrentUser` via `deps.get_current_user` (decodes the JWT from the `Authorization` header or the `chassis_access_token` cookie, no DB lookup for the token itself, binds `current_user_id_var`) and, when tenant-scoped, `CurrentOrg` via `deps.get_current_org` (binds `current_org_id_var`, which drives the ORM-event tenancy filter/stamp). Each request runs its DB work through one request-scoped `AsyncSession` (`SessionDep`): commit on success, rollback on exception. Privileged mutations are wrapped with the `@audited` decorator (`app/audit/decorator.py`).

### How the project design builds on this
Sections below specify ONLY the project-specific slots: domain data models (tenant-owned → inherit `TenantScoped`), persistence/services (async SQLAlchemy 2.0 via `AsyncSession`), API contracts (FastAPI routers gated by `requires("<resource>:<action>")`), external integrations, and traceability. Authentication, RBAC, tenancy, audit, files, notifications, admin, and observability are inherited from the foundation — referenced here, not re-designed. A deliberate deviation from a chassis default is marked `(CHASSIS-OVERRIDE)` in REQUIREMENTS.md and realized here accordingly.

---

<!-- @owned-by:  | @role: system | @system-derives-from: REQUIREMENTS.md#3. FUNCTIONAL REQUIREMENTS (FR) | @locked-by-chassis: false -->
## 2. SYSTEM OVERVIEW
The SD-Agile Platform is a self-service question-answering system that combines deterministic FAQ matching with LLM-powered fallback reasoning to deliver traceable, cited answers to end users. The system operates across three primary user personas—End Users, Content/Platform Administrators, and Organization Administrators—each with distinct capabilities and access scopes.

### Core Architecture

The system implements a **two-tier answer retrieval strategy**:

1. **Deterministic Tier (FR-007):** Questions are first matched against pre-built FAQs and Python scripts executed against configured information sources. This tier operates without LLM invocation, ensuring fast, predictable responses for common questions.

2. **LLM Fallback Tier (FR-008):** When the deterministic tier cannot produce a sufficient response, the system invokes an LLM configured to operate either against retrieval-augmented information sources or frontier model general knowledge, depending on administrator configuration (FR-009).

If both tiers are exhausted, the system informs the user that no answer is available, sends an in-app alert to Organization Administrators and Content Managers, and notifies the user that the alert has been sent.

### User-Facing Interface

**End User Interaction (FR-001, FR-002, FR-005):**
- A responsive, resizable window accessible via desktop icon or embedded HTML link
- Authentication required; unauthenticated users are redirected to login
- Text input for questions (200-character limit, FR-002)
- Multi-turn conversational support within a single session, with context maintained across turns (FR-005)
- Category browsing and FAQ selection interface (FR-003)

**Response Presentation (FR-004):**
- Structured response containing: expository text, reasoning, source citations with working hyperlinks, and thumbs up/thumbs down rating controls
- When no sources are available, the response clearly indicates this rather than displaying broken links
- Rating submission is optional; unrated interactions record null in the rating field (FR-019)
- Ratings are immutable after submission (FR-019)

**Interaction Logging (FR-006):**
- Every user interaction is persistently logged with: date-time group, question text, question category, response provided, sources used, and rating
- Log write failures do not block response delivery to the user; failures are logged to the system error log without user-facing errors

### Administrator Configuration Interface

**Information Source Management (FR-010 through FR-014):**
- Administrators configure information source categories with unique names and descriptions (FR-010)
- Four information source types are supported: Local Code Repo, GitHub/Online Repo, Document Folder, and MCP Server (FR-011)
- Local Code Repo and Document Folder sources use folder pickers with read-access testing (FR-012)
- GitHub/Online Repo sources require URL and credential entry with read-access testing (FR-013)
- MCP Server sources require server address, credentials, and explicit 'Test MCP' action before save (FR-014)
- **Critical Security Control:** A strict no-execute rule is enforced at the code level; code in connected sources is never executed by the system (FR-012, FR-013)

**Question Category Management (FR-015):**
- Administrators configure question categories with unique names and descriptions
- Duplicate names are rejected with inline validation

**FAQ Management (FR-016 through FR-018):**
- Manual FAQ creation: administrators and Content Managers enter question text, select applicable question categories (multi-select), source categories (multi-select), and sources (multi-select), and provide a response (FR-016)
- Automated FAQ generation from interaction logs: LLM clusters similar questions and recommends categories, sources, and responses; user reviews and approves via checkboxes and free-text before explicit save (FR-017)
- Automated FAQ generation from information sources: LLM reviews source content and generates FAQ candidates; user reviews and approves before explicit save (FR-018)
- **Critical Requirement:** LLM-generated FAQs are never auto-saved; explicit human approval is mandatory

**LLM Fallback Configuration (FR-009):**
- Administrators configure, per information source category and question type, whether LLM fallback is grounded against configured sources (retrieval-augmented) or frontier model general knowledge
- End users cannot access this configuration

### Authorization and Multi-Tenancy

**Role-Based Access Control:**
- Platform Administrators: full system access across all organizations
- Organization Administrators: access limited to their own organization's data, except platform-level shared resources (read-only)
- Content Managers: access limited to their own organization's data, except platform-level shared resources (read-only); cannot create information source categories or question categories (FR-010, FR-015)
- End Users: access only to the question-answering interface; cannot access administrative configuration or interaction logs

**Platform-Level Sharing (FR-020, FR-027):**
- Platform Administrators may designate information sources, information source categories, and FAQs as platform-level shared
- Only resources originally created by a Platform Administrator may be designated as platform-level shared
- Platform-level shared resources are visible in read-only mode to all Organization Administrators and Content Managers
- Organization Administrators and Content Managers cannot edit or delete platform-level shared resources

**Cross-Organization Data Isolation (FR-025):**
- Organization Administrators and Content Managers cannot view, access, or act on data outside their own organization, except for platform-level shared resources

**Impersonation Prevention (FR-026):**
- Platform Administrators and Organization Administrators cannot assume or impersonate other users
- All administrative actions are performed under the administrator's own authenticated identity

### Security and Monitoring

**No-Execute Rule Enforcement (FR-022):**
- When the no-execute rule is triggered on a connected information source, an in-app alert is delivered to the Platform Administrator and a corresponding entry is logged to the audit log
- Audit log entries cannot be altered or deleted by any user

**Graceful Degradation (CON-004, CON-005, CON-006):**
- When the External LLM API is unavailable after exhausting retries, the system degrades to FAQ browse-only mode with failure-type-specific alerts to administrators
- GitHub/Online Repo and MCP Server integrations implement 3-retry logic (1-second delay before second attempt, 3-second delay before subsequent attempts) with 20-second timeouts and failure-type-specific messaging

### Data Model Scope

The system manages the following primary entities:
- **Users** (with role and organization scope)
- **Information Sources** (with type, credentials, and organization/platform scope)
- **Information Source Categories** (with organization/platform scope)
- **Question Categories** (with organization/platform scope)
- **FAQs** (with associated categories, sources, and organization/platform scope)
- **Interaction Logs** (with question, response, sources, rating, and organization scope)
- **Audit Logs** (for security events, platform-wide scope)
- **In-App Alerts** (for administrators, with organization/platform scope)
## 2A. TECHNICAL ARCHITECTURE (APPLICATION-SPECIFIC)

**[RECOMMENDED — Pending AA Approval]**

*No project-specific technical architecture data is available from the Golden Record. The following is a placeholder recommendation based on the project name and chassis defaults.*

**Slot decomposition (recommended):**
The Accessibility Assistant is expected to decompose into at least one domain slot: `app/slots/accessibility/`. If the project scope expands to include reporting, document scanning, or user-submitted content, additional slots (e.g., `app/slots/reports/`, `app/slots/documents/`) may be warranted. Final decomposition must be confirmed once functional requirements are elicited.

**Dependency graph between slots:** No cross-slot dependencies are anticipated at this stage. Each slot should be independently deployable and internally cohesive.

**Transaction boundaries:** Standard per-request `AsyncSession` boundary (commit on success, rollback on exception) is sufficient until multi-slot transactional requirements are identified.

**Concurrency/locking strategy:** No application-specific locking strategy beyond chassis defaults is anticipated at this stage.

**Caching strategy:** No Redis caching beyond the chassis rate-limit default is anticipated at this stage. If accessibility scan results are expensive to compute, a short-lived Redis cache keyed by input hash may be appropriate — to be confirmed with functional requirements.

**Background-job topology:** If accessibility scans are long-running, they should be enqueued via `app/tasks/queue.py:enqueue` on a dedicated `accessibility` RQ queue. To be confirmed once functional requirements are elicited.

**Architectural trade-offs:** None identified at this stage. This section must be revisited once REQUIREMENTS.md §4 and §5 are fully populated.

*Rationale: The Golden Record contains only the project name. All architecture decisions above are minimum-viable placeholders derived from the chassis defaults and the project name. They must be reviewed and approved before DESIGN.md is used to generate TASKS.md.*

---

## 3. LOGIC OWNERSHIP MAP (MANDATORY)

| Requirement ID | Ownership | Execution Location | Notes |
|---------------|-----------|--------------------|-------|

**[RECOMMENDED — Pending AA Approval]**

*No requirement IDs are available from the Golden Record (REQUIREMENTS.md §4–§5 are marked "Pending"). This table cannot be populated until functional, security, and non-functional requirements are elicited and assigned IDs. Every requirement MUST appear exactly once in this table per the Design Generation Contract (§1, Rule 1). Generation of a valid DESIGN.md is blocked until REQUIREMENTS.md is complete.*

*Rationale: Per §1 Rule 8, generation STOPS if required information is missing. This table is left structurally present but empty, with this note, to preserve the document structure while flagging the blocking gap.*

---

## 4. DATA MODELS (APPLICATION-OWNED ONLY)
### User

Represents an authenticated user of the platform, scoped to a persona and optionally an organization.


| Field | Type | Required | Unique | PII | Validation | Description |
|---|---|---|---|---|---|---|
| id | uuid | yes | no | no | — | — |
| name | string | yes | no | no | — | — |
| email | string | yes | no | no | — | — |
| role | enum (platform_admin, org_admin, content_manager, end_user) | yes | no | no | — | — |
| organization_id | uuid | no | no | no | — | — |
| created_at | timestamp | yes | no | no | — | — |
| updated_at | timestamp | yes | no | no | — | — |

### Organization

A tenant grouping that scopes users, information source categories, question categories, and information sources.


| Field | Type | Required | Unique | PII | Validation | Description |
|---|---|---|---|---|---|---|
| id | uuid | yes | no | no | — | — |
| name | string | yes | no | no | — | — |
| created_at | timestamp | yes | no | no | — | — |
| updated_at | timestamp | yes | no | no | — | — |

### InformationSourceCategory

A classification grouping for information sources, configurable at platform or organization level.


| Field | Type | Required | Unique | PII | Validation | Description |
|---|---|---|---|---|---|---|
| id | uuid | yes | no | no | — | — |
| name | string | yes | no | no | — | — |
| organization_id | uuid | no | no | no | — | — |
| created_by | uuid | yes | no | no | — | — |
| created_at | timestamp | yes | no | no | — | — |
| updated_at | timestamp | yes | no | no | — | — |

### InformationSource

A configured data source (e.g. GitHub repository, MCP Server) whose credentials are stored encrypted at rest. Tracks no-execute rule state for alerting.


| Field | Type | Required | Unique | PII | Validation | Description |
|---|---|---|---|---|---|---|
| id | uuid | yes | no | no | — | — |
| name | string | yes | no | no | — | — |
| category_id | uuid | yes | no | no | — | — |
| organization_id | uuid | no | no | no | — | — |
| source_type | enum (github, mcp_server, other) | yes | no | no | — | — |
| credentials_encrypted | blob | yes | no | no | — | — |
| no_execute_triggered | boolean | yes | no | no | — | — |
| created_by | uuid | yes | no | no | — | — |
| created_at | timestamp | yes | no | no | — | — |
| updated_at | timestamp | yes | no | no | — | — |

### QuestionCategory

A classification grouping for FAQ entries and user questions, configurable at platform or organization level.


| Field | Type | Required | Unique | PII | Validation | Description |
|---|---|---|---|---|---|---|
| id | uuid | yes | no | no | — | — |
| name | string | yes | no | no | — | — |
| organization_id | uuid | no | no | no | — | — |
| created_by | uuid | yes | no | no | — | — |
| created_at | timestamp | yes | no | no | — | — |
| updated_at | timestamp | yes | no | no | — | — |

### FAQ

A question-and-answer entry created manually by a content manager or generated automatically by the system.


| Field | Type | Required | Unique | PII | Validation | Description |
|---|---|---|---|---|---|---|
| id | uuid | yes | no | no | — | — |
| question | string | yes | no | no | — | — |
| answer | text | yes | no | no | — | — |
| question_category_id | uuid | no | no | no | — | — |
| organization_id | uuid | no | no | no | — | — |
| origin | enum (manual, automated) | yes | no | no | — | — |
| created_by | uuid | yes | no | no | — | — |
| created_at | timestamp | yes | no | no | — | — |
| updated_at | timestamp | yes | no | no | — | — |

### InteractionLog

A PII-classified record of a user's question session, including user identity and organization. Access is restricted by role; records are immutable after creation.


| Field | Type | Required | Unique | PII | Validation | Description |
|---|---|---|---|---|---|---|
| id | uuid | yes | no | no | — | — |
| user_id | uuid | yes | no | no | — | — |
| user_name | string | yes | no | no | — | — |
| organization_id | uuid | yes | no | no | — | — |
| question_text | text | yes | no | no | — | — |
| response_text | text | yes | no | no | — | — |
| information_source_ids | array<uuid> | no | no | no | — | — |
| created_at | timestamp | yes | no | no | — | — |

### AuditLog

An immutable system-level event record used to track security-relevant actions including no-execute rule triggers, credential changes, and administrative operations.


| Field | Type | Required | Unique | PII | Validation | Description |
|---|---|---|---|---|---|---|
| id | uuid | yes | no | no | — | — |
| event_type | string | yes | no | no | — | — |
| actor_user_id | uuid | no | no | no | — | — |
| target_entity_type | string | no | no | no | — | — |
| target_entity_id | uuid | no | no | no | — | — |
| organization_id | uuid | no | no | no | — | — |
| detail | json | no | no | no | — | — |
| created_at | timestamp | yes | no | no | — | — |

### InAppAlert

A notification delivered to the Platform Administrator when a no-execute rule is triggered on a connected information source.


| Field | Type | Required | Unique | PII | Validation | Description |
|---|---|---|---|---|---|---|
| id | uuid | yes | no | no | — | — |
| recipient_user_id | uuid | yes | no | no | — | — |
| information_source_id | uuid | yes | no | no | — | — |
| message | string | yes | no | no | — | — |
| read | boolean | yes | no | no | — | — |
| created_at | timestamp | yes | no | no | — | — |
## 5. PERSISTENCE & DATA ACCESS (SQLALCHEMY)
### 5.1 Data Model

The persistence layer is built on SQLAlchemy ORM and supports the following core entities:

| Entity | Purpose | Key Fields | Relationships |
|--------|---------|-----------|---------------|
| **User** | Authentication and authorization | user_id (PK), username, email, role (Platform Admin / Org Admin / Content Manager / End User), organization_id (FK), created_at, updated_at | Organization (N:1), InteractionLog (1:N), Alert (1:N) |
| **Organization** | Multi-tenant scope boundary | organization_id (PK), name, created_at, updated_at | User (1:N), InformationSourceCategory (1:N), InformationSource (1:N), QuestionCategory (1:N), FAQ (1:N), InteractionLog (1:N) |
| **InformationSourceCategory** | Grouping for information sources (FR-010) | category_id (PK), organization_id (FK), name, description, is_platform_shared (boolean), created_by_user_id (FK), created_at, updated_at | Organization (N:1), InformationSource (1:N), FAQ (N:M via FAQ_SourceCategory) |
| **InformationSource** | Connected data source (FR-011, FR-012, FR-013, FR-014) | source_id (PK), organization_id (FK), category_id (FK), source_type (enum: LocalCodeRepo, GitHubOnlineRepo, DocumentFolder, MCPServer), name, description, connection_config (JSON: folder_path, github_url, mcp_address, credentials), is_platform_shared (boolean), created_by_user_id (FK), created_at, updated_at, last_tested_at, test_status (enum: success, failed, pending) | Organization (N:1), InformationSourceCategory (N:1), FAQ (N:M via FAQ_Source), AuditLog (1:N) |
| **QuestionCategory** | User-facing question classification (FR-015) | question_category_id (PK), organization_id (FK), name, description, created_by_user_id (FK), created_at, updated_at | Organization (N:1), FAQ (N:M via FAQ_QuestionCategory), InteractionLog (N:1) |
| **FAQ** | Pre-built deterministic answer (FR-016, FR-017, FR-018) | faq_id (PK), organization_id (FK), question_text, response_text, created_by_user_id (FK), is_platform_shared (boolean), created_at, updated_at | Organization (N:1), QuestionCategory (N:M via FAQ_QuestionCategory), InformationSourceCategory (N:M via FAQ_SourceCategory), InformationSource (N:M via FAQ_Source), InteractionLog (1:N) |
| **FAQ_QuestionCategory** | Junction table for FAQ ↔ QuestionCategory (N:M) | faq_id (FK), question_category_id (FK) | FAQ (N:1), QuestionCategory (N:1) |
| **FAQ_SourceCategory** | Junction table for FAQ ↔ InformationSourceCategory (N:M) | faq_id (FK), category_id (FK) | FAQ (N:1), InformationSourceCategory (N:1) |
| **FAQ_Source** | Junction table for FAQ ↔ InformationSource (N:M) | faq_id (FK), source_id (FK) | FAQ (N:1), InformationSource (N:1) |
| **InteractionLog** | User interaction record (FR-006, FR-019, FR-021) | log_id (PK), user_id (FK), organization_id (FK), question_text, question_category_id (FK, nullable), response_text, faq_id (FK, nullable), rating (enum: null, thumbs_up, thumbs_down, immutable after submission), sources_used (JSON array of source_ids), created_at, updated_at | User (N:1), Organization (N:1), QuestionCategory (N:1), FAQ (N:1) |
| **Alert** | In-app notification for admins (FR-008, CON-004, CON-005, CON-006) | alert_id (PK), user_id (FK), alert_type (enum: UnansweredQuestion, LLMFailure, GitHubFailure, MCPFailure, SecurityViolation), message, question_text (nullable), submitting_user_name (nullable), submitted_at (nullable), is_read (boolean), created_at | User (N:1) |
| **AuditLog** | Security and compliance event log (FR-022) | audit_id (PK), event_type (enum: NoExecuteViolation, ResourceShared, ResourceModified), user_id (FK, nullable), source_id (FK, nullable), details (JSON), created_at, immutable after creation | User (N:1), InformationSource (N:1) |

### 5.2 Session & Conversational Context

- **Session Storage:** Multi-turn conversational context (FR-005) is maintained in-memory during an active user session. Session data includes:
  - Session ID (UUID)
  - User ID (FK to User)
  - Conversation history (list of {question, response, sources, timestamp} tuples)
  - Session start time and last activity time
  - Session timeout: 30 minutes of inactivity (configurable)
  
- **Session Lifecycle:**
  - Session is created when an authenticated user opens the assistant window (FR-001).
  - Conversational context is available only within the active session (FR-005).
  - When the user closes the window or session times out, the session is destroyed and context is discarded; no context carries over to a new session (FR-005).
  - Session data is NOT persisted to the database; it exists only in application memory (e.g., Redis or in-process cache).

### 5.3 Persistence Guarantees & Error Handling

- **InteractionLog Persistence (FR-006):**
  - Every completed user interaction must be logged to the InteractionLog table, including question text, response, sources, and rating (if submitted).
  - If the log write fails (database error, timeout, etc.), the response is still served to the end user; the failure is logged to the system error log; the end user is not shown a system error (FR-006).
  - Rating field is recorded as null if the user does not submit a rating (FR-006, FR-019).
  - Ratings are immutable after submission; no UPDATE or DELETE operations are permitted on the rating field once recorded (FR-019).

- **Alert Persistence (FR-008, CON-004, CON-005, CON-006):**
  - When an unanswered question occurs (both deterministic and LLM tiers exhausted), an Alert record is created with alert_type = 'UnansweredQuestion', message containing the question text, submitting user name, and timestamp (FR-008).
  - When an LLM API failure occurs (rate limit, auth failure, timeout) after retries, an Alert record is created with alert_type = 'LLMFailure' and failure-type-specific message (CON-004).
  - When a GitHub/Online Repo integration failure occurs after retries, an Alert record is created with alert_type = 'GitHubFailure' and failure-type-specific message (CON-005).
  - When an MCP Server integration failure occurs after retries, an Alert record is created with alert_type = 'MCPFailure' and failure-type-specific message (CON-006).
  - Alerts are delivered to the appropriate recipients (Organization Administrator, Platform Administrator, or both) based on alert type and user role.

- **AuditLog Immutability (FR-022):**
  - When a security control violation occurs (no-execute rule triggered), an AuditLog entry is created with event_type = 'NoExecuteViolation', source_id (FK to the offending source), and details (JSON with violation context).
  - AuditLog entries are immutable; no UPDATE or DELETE operations are permitted after creation (FR-022).
  - AuditLog entries are retained indefinitely for compliance and forensic purposes.

### 5.4 Multi-Tenancy & Authorization Scoping

- **Organization Isolation (FR-025):**
  - All data-bearing entities (InformationSourceCategory, InformationSource, QuestionCategory, FAQ, InteractionLog) include an organization_id (FK) field.
  - Queries for Organization Administrators and Content Managers must filter by their own organization_id; cross-organization data access is denied (FR-025).
  - Platform Administrators may query across all organizations.
  - Platform-level shared resources (InformationSourceCategory, InformationSource, FAQ with is_platform_shared = true) are visible to all Organization Administrators and Content Managers in read-only mode, but only if originally created by a Platform Administrator (FR-020, FR-027).

- **Creator Tracking (FR-020, FR-027):**
  - All shareable entities (InformationSourceCategory, InformationSource, FAQ) include a created_by_user_id (FK) field to track the creating user's role and organization.
  - A resource may only be designated as platform-level shared if created_by_user_id references a Platform Administrator user (FR-027).
  - Organization Administrators and Content Managers cannot edit or delete platform-level shared resources (FR-020).

### 5.5 Configuration & Connection State

- **InformationSource Connection Testing:**
  - Each InformationSource record includes test_status (enum: success, failed, pending) and last_tested_at (timestamp).
  - When a source is configured (FR-012, FR-013, FR-014), a connectivity/read-access test is performed before the record is persisted.
  - On test success, test_status = 'success' and the source is saved (FR-012, FR-013, FR-014).
  - On test failure, test_status = 'failed' and the user is prompted to correct credentials; the source is not saved until a successful test (FR-012, FR-013, FR-014).
  - For MCP Server sources, the 'Test MCP' action must be explicitly triggered and succeed before the source can be saved (FR-014).
  - connection_config (JSON) stores source-specific credentials and connection parameters (folder_path, github_url, mcp_address, etc.). Sensitive fields (tokens, passwords) must be encrypted at rest using a key management service (KMS) or equivalent.

### 5.6 FAQ Generation & Approval Workflow

- **Automated FAQ Generation (FR-017, FR-018):**
  - When an authorized user triggers automated FAQ generation, LLM-generated FAQ candidates are presented in a review UI with recommended question text, question categories, source categories, sources, and response text.
  - Candidates are NOT persisted to the FAQ table until the user explicitly confirms save via a "Save" button (FR-017, FR-018).
  - If the user closes the review session without confirming save, all candidates are discarded and no FAQ records are created (FR-017, FR-018).
  - Once confirmed, approved FAQ entries are inserted into the FAQ table with created_by_user_id set to the approving user's ID.

### 5.7 Indexing & Query Performance

- **Recommended Indexes:**
  - InteractionLog: (organization_id, created_at) for admin log queries (FR-021)
  - InteractionLog: (user_id, created_at) for per-user interaction history
  - FAQ: (organization_id, is_platform_shared) for FAQ list queries
  - InformationSource: (organization_id, category_id) for source browsing
  - Alert: (user_id, is_read, created_at) for alert retrieval
  - AuditLog: (event_type, created_at) for security event queries
## 5A. AUTHORIZATION & PERSONA DESIGN

**[RECOMMENDED — Pending AA Approval]**

*No persona or authorization data is available from the Golden Record (REQUIREMENTS.md §3.2 is "Pending"). The following is a minimum-viable placeholder.*

**Recommended permission set for the `accessibility` slot (subject to persona elicitation):**

| Permission | Description | Recommended Role Grant |
|---|---|---|
| `accessibility_checks:read` | View accessibility check records | `user`, `admin` |
| `accessibility_checks:write` | Submit new accessibility checks | `user`, `admin` |
| `accessibility_checks:admin` | Manage all checks, view all users' submissions | `admin` |

**Role-to-permission grant matrix:** To be completed once user personas are elicited in REQUIREMENTS.md §3.2. Each persona must map to a chassis role (or a new slot-registered role) and the corresponding `resource:action` permissions must be registered at the `app/rbac/permissions.py` slot-permissions marker.

**Route gating:** Every slot route MUST use `dependencies=[Depends(requires("<resource>:<action>"))]`. No route may be unauthenticated unless explicitly justified and annotated `(CHASSIS-OVERRIDE)`.

*Rationale: REQUIREMENTS.md §3.2 is marked "Pending — owned by phase4_user_personas." This section cannot be finalized until personas are defined. The placeholder permission set above is derived from the project name and the chassis's seeded `user`/`admin` roles.*

---

## 5B. SECURITY DESIGN (APPLICATION-SPECIFIC)

**[RECOMMENDED — Pending AA Approval]**

*No application-specific security requirements are available from the Golden Record (REQUIREMENTS.md §5.1 is "Pending"). The following is a minimum-viable placeholder based on chassis defaults and the project domain.*

**Field-level encryption:** No fields requiring encryption beyond chassis defaults (passwords, MFA secrets) have been identified at this stage. If the Accessibility Assistant stores sensitive document content or PII extracted from scanned resources, field-level AES-256-GCM encryption (following the `auth/mfa_crypto.py` pattern) must be applied. To be confirmed once functional requirements are elicited.

**Additional audit events:** At minimum, the following slot-level audit events are recommended beyond chassis defaults:
- `accessibility.check.create` — when a new accessibility check is submitted
- `accessibility.check.delete` — if deletion is permitted (to be confirmed)

**Data classification:** No data classification decisions can be made without functional requirements. If the assistant processes URLs or document content that may contain PII, a data classification review is required before production deployment.

**Compliance-regime controls:** The REQUIREMENTS.md references FISMA-Moderate alignment (inherited from chassis). No additional compliance-regime deltas (HIPAA, PCI, CJIS) have been identified. To be confirmed once functional requirements and organizational context are elicited.

**Tests:** Each security control must have a corresponding test scenario asserting the control is enforced (e.g., 401 on unauthenticated access, 403 on missing permission, audit row written on mutation).

*Rationale: REQUIREMENTS.md §5.1 is marked "Pending — owned by phase5b_security_requirements." This section must be revisited once security requirements are elicited.*

---

## 6. INTEGRATION LAYER (APPLICATION → EXTERNAL SERVICES)
#### Systems of Record

| Data Object | Authoritative System | Notes |
|---|---|---|
| Information Source Category | Accessibility Assistant | Net-new — no prior system of record exists |
| Information Source | Accessibility Assistant | Net-new — no prior system of record exists |
| Question Category | Accessibility Assistant | Net-new — no prior system of record exists |
| FAQ Entry | Accessibility Assistant | Net-new — no prior system of record exists |
| User Question and Response (Interaction Log) | Accessibility Assistant | Net-new — no prior system of record exists; previously exchanged informally via email and phone with no persistent storage |

#### Integrations

##### External LLM API

- **Purpose:** Sends sanitized user questions (with PII and source code removed) to an external large-language-model API and receives generated answers for the User Asks Questions process and automated FAQ generation.

##### GitHub

- **Purpose:** Connects to GitHub repositories as an information source using personal access tokens or OAuth tokens stored encrypted at rest; content is retrieved to support question answering and automated FAQ generation.

##### MCP Server

- **Purpose:** Connects to one or more MCP Servers as information sources using credentials stored encrypted at rest; the no-execute rule is monitored on this integration and triggers alerts and audit log entries when violated.

##### External LLM API (via LiteLLM)

- **Purpose:** Routes sanitized user questions (PII and source code removed) to an external large-language-model API for Tier 2 answer generation and automated FAQ candidate generation. All calls are routed through the chassis LiteLLM integration — no direct provider calls are permitted.
- **Operational contract:** timeout 20000ms, 3 retries, custom backoff
- **Fallback:** After 3 retries exhausted: display failure-type-specific user-friendly message to end user; send failure-type-specific in-app alert to Organization Administrator and Platform Administrator; degrade gracefully to FAQ browse-only mode.
- **TLS required:** yes
- **Error mapping:**
  - `auth_failure` → AUTH_FAILURE — alert message: 'authentication failure'
  - `rate_limit` → RATE_LIMIT_EXCEEDED — alert message: 'rate limit exceeded'
  - `server_error` → SERVICE_UNAVAILABLE — alert message: 'service unavailable'
  - `timeout` → SERVICE_TIMEOUT — alert message: 'service timeout'

##### GitHub / Online Repository

- **Purpose:** Connects to GitHub repositories as a configured information source using personal access tokens or OAuth credentials stored encrypted at rest (FIPS 140-2/140-3). Content is retrieved read-only to support question answering and automated FAQ generation. No-execute rule enforced.
- **Auth:** personal_access_token or oauth2
- **Secret store:** encrypted_at_rest_fips_validated
- **Operational contract:** timeout 20000ms, 3 retries, custom backoff
- **Fallback:** After 3 retries exhausted: display failure-type-specific user-friendly message to user; send failure-type-specific in-app alert to Organization Administrator and Platform Administrator.
- **TLS required:** yes
- **Error mapping:**
  - `auth_failure` → AUTH_FAILURE — alert message: 'authentication failure'
  - `server_error` → SERVICE_UNAVAILABLE — alert message: 'service unavailable'
  - `timeout` → SERVICE_TIMEOUT — alert message: 'service timeout'

##### MCP Server

- **Purpose:** Connects to one or more MCP Servers as configured information sources using credentials stored encrypted at rest (FIPS 140-2/140-3). Content is retrieved read-only. No-execute rule is monitored; violations trigger in-app alerts to Platform Administrator and audit log entries.
- **Secret store:** encrypted_at_rest_fips_validated
- **Operational contract:** timeout 20000ms, 3 retries, custom backoff
- **Fallback:** After 3 retries exhausted: display failure-type-specific user-friendly message to user; send failure-type-specific in-app alert to Organization Administrator and Platform Administrator.
- **TLS required:** yes
- **Error mapping:**
  - `auth_failure` → AUTH_FAILURE — alert message: 'authentication failure'
  - `server_error` → SERVICE_UNAVAILABLE — alert message: 'service unavailable'
  - `timeout` → SERVICE_TIMEOUT — alert message: 'service timeout'
## 7. API CONTRACTS (FASTAPI)
### Overview

The SD-Agile Platform exposes a FastAPI-based REST API to support all functional requirements defined in REQUIREMENTS.md. This section specifies the primary API contracts, organized by resource domain and operation type. All endpoints require authentication via JWT bearer token unless explicitly marked as public. Responses follow a consistent JSON structure with HTTP status codes per REST conventions.

---

### Authentication & Authorization

**Endpoint:** `POST /auth/login`
- **Description:** Authenticate a user and return a JWT bearer token.
- **Request Body:**
  ```
  {
    "username": string,
    "password": string
  }
  ```
- **Response (200):**
  ```
  {
    "access_token": string,
    "token_type": "bearer",
    "user_id": string,
    "role": string (enum: "end_user" | "content_manager" | "org_admin" | "platform_admin")
  }
  ```
- **Response (401):** Unauthorized — invalid credentials.
- **Related FR:** FR-001 (authentication prerequisite for assistant access).

**Endpoint:** `POST /auth/logout`
- **Description:** Invalidate the current JWT token.
- **Headers:** `Authorization: Bearer {token}`
- **Response (204):** No content.

---

### Question Submission & Response (User Asks Questions Process)

**Endpoint:** `POST /questions/ask`
- **Description:** Submit a user question and retrieve a structured response. Implements the two-tier answer strategy: deterministic FAQ matching (FR-007) followed by LLM fallback (FR-008).
- **Headers:** `Authorization: Bearer {token}`
- **Request Body:**
  ```
  {
    "question_text": string (max 200 characters, required),
    "question_category_id": string (optional),
    "session_id": string (required for multi-turn context per FR-005)
  }
  ```
- **Validation:**
  - Reject if `question_text` is empty or exceeds 200 characters (FR-002).
  - Return inline validation error message on rejection.
- **Response (200):**
  ```
  {
    "response_id": string,
    "question_text": string,
    "question_category_id": string (nullable),
    "response_text": string (expository response per FR-004),
    "reasoning": string (reasoning behind response per FR-004),
    "citations": [
      {
        "source_id": string,
        "source_name": string,
        "url": string (hyperlink per FR-004),
        "excerpt": string
      }
    ],
    "answer_tier": string (enum: "deterministic_faq" | "llm_retrieval_augmented" | "llm_general_knowledge"),
    "rating_control": {
      "thumbs_up_url": string,
      "thumbs_down_url": string
    }
  }
  ```
- **Response (200 - No Answer Available):**
  ```
  {
    "response_id": string,
    "question_text": string,
    "status": "no_answer_available",
    "message": "No answer is available for your question. An alert has been sent to the Organization Administrator and Content Manager.",
    "alert_sent": true,
    "alert_timestamp": ISO8601 datetime
  }
  ```
  - Alert includes: question text, submitting user name, time submitted (FR-008).
- **Response (400):** Validation error (empty or oversized question).
- **Response (401):** Unauthenticated user (FR-001).
- **Response (503):** LLM API unavailable after retries; FAQ browse-only mode available (CON-004).
- **Side Effects:**
  - Interaction log record persisted (FR-006) with date-time, question text, category, response, sources, rating (initially null).
  - If log write fails, response still served; error logged to system error log; user not shown error (FR-006).
  - Multi-turn context maintained within session via `session_id` (FR-005).

**Endpoint:** `GET /questions/{response_id}`
- **Description:** Retrieve a previously submitted question and response.
- **Headers:** `Authorization: Bearer {token}`
- **Response (200):** Same structure as `POST /questions/ask` response.
- **Response (404):** Response not found.

---

### Response Rating (FR-019)

**Endpoint:** `POST /responses/{response_id}/rate`
- **Description:** Submit a thumbs up or thumbs down rating for a response. Ratings are immutable after submission.
- **Headers:** `Authorization: Bearer {token}`
- **Request Body:**
  ```
  {
    "rating": string (enum: "thumbs_up" | "thumbs_down")
  }
  ```
- **Response (200):**
  ```
  {
    "response_id": string,
    "rating": string,
    "timestamp": ISO8601 datetime
  }
  ```
- **Response (400):** Invalid rating value.
- **Response (409):** Rating already submitted for this response (immutability enforcement per FR-019).
- **Side Effects:**
  - Rating associated with corresponding interaction log record (FR-006, FR-019).

**Endpoint:** `GET /responses/{response_id}/rating`
- **Description:** Retrieve the rating for a response (if submitted).
- **Headers:** `Authorization: Bearer {token}`
- **Response (200):**
  ```
  {
    "response_id": string,
    "rating": string (enum: "thumbs_up" | "thumbs_down") | null,
    "timestamp": ISO8601 datetime | null
  }
  ```

---

### FAQ Browse (FR-003)

**Endpoint:** `GET /question-categories`
- **Description:** List all question categories accessible to the authenticated user.
- **Headers:** `Authorization: Bearer {token}`
- **Response (200):**
  ```
  {
    "categories": [
      {
        "category_id": string,
        "name": string,
        "description": string,
        "faq_count": integer
      }
    ]
  }
  ```
- **Response (200 - Empty):** Empty categories list with message "No question categories have been configured" (FR-003).

**Endpoint:** `GET /question-categories/{category_id}/faqs`
- **Description:** List all FAQs within a specific question category.
- **Headers:** `Authorization: Bearer {token}`
- **Response (200):**
  ```
  {
    "category_id": string,
    "category_name": string,
    "faqs": [
      {
        "faq_id": string,
        "question_text": string,
        "answer_text": string (truncated for list view)
      }
    ]
  }
  ```
- **Response (200 - Empty):** Empty FAQs list with message "No FAQs exist yet in this category" (FR-003).

**Endpoint:** `GET /faqs/{faq_id}`
- **Description:** Retrieve the full answer for a specific FAQ.
- **Headers:** `Authorization: Bearer {token}`
- **Response (200):**
  ```
  {
    "faq_id": string,
    "question_text": string,
    "answer_text": string (full answer per FR-003),
    "question_categories": [
      {
        "category_id": string,
        "name": string
      }
    ],
    "source_categories": [
      {
        "source_category_id": string,
        "name": string
      }
    ],
    "sources": [
      {
        "source_id": string,
        "name": string,
        "type": string
      }
    ]
  }
  ```

---

### Information Source Configuration (FR-011, FR-012, FR-013, FR-014)

**Endpoint:** `GET /information-sources`
- **Description:** List all information sources accessible to the authenticated user.
- **Headers:** `Authorization: Bearer {token}`
- **Query Parameters:**
  - `source_category_id` (optional): Filter by source category.
  - `include_platform_shared` (optional, boolean): Include platform-level shared sources (FR-020).
- **Response (200):**
  ```
  {
    "sources": [
      {
        "source_id": string,
        "name": string,
        "type": string (enum: "local_code_repo" | "github_online_repo" | "document_folder" | "mcp_server"),
        "source_category_id": string,
        "is_platform_shared": boolean,
        "created_by": string (user ID),
        "created_at": ISO8601 datetime
      }
    ]
  }
  ```
- **Authorization:** End Users denied access (FR-011).

**Endpoint:** `POST /information-sources`
- **Description:** Create a new information source. Type-specific validation and connectivity testing applied per source type.
- **Headers:** `Authorization: Bearer {token}`
- **Request Body (Local Code Repo or Document Folder):**
  ```
  {
    "name": string,
    "type": string (enum: "local_code_repo" | "document_folder"),
    "source_category_id": string,
    "folder_path": string
  }
  ```
  - System tests read access without executing code (FR-012, no-execute rule).
- **Request Body (GitHub/Online Repo):**
  ```
  {
    "name": string,
    "type": "github_online_repo",
    "source_category_id": string,
    "github_url": string,
    "access_token": string (personal access token or OAuth)
  }
  ```
  - System tests read access without executing code (FR-013, no-execute rule).
- **Request Body (MCP Server):**
  ```
  {
    "name": string,
    "type": "mcp_server",
    "source_category_id": string,
    "mcp_server_address": string,
    "credentials": {
      "username": string (optional),
      "password": string (optional),
      "api_key": string (optional)
    }
  }
  ```
  - Requires successful `Test MCP` connectivity test before save (FR-014).
- **Response (201):**
  ```
  {
    "source_id": string,
    "name": string,
    "type": string,
    "source_category_id": string,
    "status": "active",
    "message": "Source configured successfully"
  }
  ```
- **Response (400):** Validation error (missing required fields, invalid folder path, invalid credentials).
- **Response (401):** Unauthenticated or unauthorized (FR-011).
- **Response (503):** Connectivity test failed (GitHub timeout, MCP timeout, etc.); user prompted to correct credentials (CON-005, CON-006).
- **Side Effects:**
  - If no-execute rule triggered during access test, in-app alert sent to Platform Administrator and audit log entry created (FR-022).

**Endpoint:** `POST /information-sources/test-connectivity`
- **Description:** Test connectivity to a GitHub/Online Repo or MCP Server without creating the source.
- **Headers:** `Authorization: Bearer {token}`
- **Request Body:**
  ```
  {
    "type": string (enum: "github_online_repo" | "mcp_server"),
    "github_url": string (if type == "github_online_repo"),
    "access_token": string (if type == "github_online_repo"),
    "mcp_server_address": string (if type == "mcp_server"),
    "credentials": object (if type == "mcp_server")
  }
  ```
- **Response (200):**
  ```
  {
    "status": "success",
    "message": "Connectivity test passed"
  }
  ```
- **Response (503):** Connectivity test failed with failure-type-specific message (CON-005, CON-006).

**Endpoint:** `GET /information-sources/{source_id}`
- **Description:** Retrieve details of a specific information source.
- **Headers:** `Authorization: Bearer {token}`
- **Response (200):** Source details including type, category, creation metadata.
- **Response (404):** Source not found.

**Endpoint:** `PUT /information-sources/{source_id}`
- **Description:** Update an information source (name, category, credentials).
- **Headers:** `Authorization: Bearer {token}`
- **Request Body:** Subset of creation fields (type immutable).
- **Response (200):** Updated source details.
- **Response (403):** Forbidden — user lacks permission or source is platform-level shared (FR-020, FR-027).
- **Response (404):** Source not found.

**Endpoint:** `DELETE /information-sources/{source_id}`
- **Description:** Delete an information source.
- **Headers:** `Authorization: Bearer {token}`
- **Response (204):** No content.
- **Response (403):** Forbidden — source is platform-level shared (FR-020).
- **Response (404):** Source not found.

---

### Information Source Categories (FR-010)

**Endpoint:** `GET /source-categories`
- **Description:** List all information source categories accessible to the authenticated user.
- **Headers:** `Authorization: Bearer {token}`
- **Query Parameters:**
  - `include_platform_shared` (optional, boolean): Include platform-level shared categories (FR-020).
- **Response (200):**
  ```
  {
    "categories": [
      {
        "source_category_id": string,
        "name": string,
        "description": string,
        "is_platform_shared": boolean,
        "created_by": string (user ID)
      }
    ]
  }
  ```

**Endpoint:** `POST /source-categories`
- **Description:** Create a new information source category.
- **Headers:** `Authorization: Bearer {token}`
- **Request Body:**
  ```
  {
    "name": string (required, unique within scope),
    "description": string
  }
  ```
- **Validation:**
  - Reject duplicate category names with inline message (FR-010).
  - Reject missing name with inline message (FR-010).
- **Response (201):**
  ```
  {
    "source_category_id": string,
    "name": string,
    "description": string
  }
  ```
- **Response (400):** Validation error (duplicate name, missing name).
- **Response (401):** Unauthenticated or unauthorized (FR-010 — End Users and Content Managers denied).

**Endpoint:** `PUT /source-categories/{source_category_id}`
- **Description:** Update an information source category.
- **Headers:** `Authorization: Bearer {token}`
- **Request Body:**
  ```
  {
    "name": string (optional, unique within scope if provided),
    "description": string (optional)
  }
  ```
- **Response (200):** Updated category details.
- **Response (400):** Validation error (duplicate name).
- **Response (403):** Forbidden — category is platform-level shared (FR-20).
- **Response (404):** Category not found.

**Endpoint:** `DELETE /source-categories/{source_category_id}`
- **Description:** Delete an information source category.
- **Headers:** `Authorization: Bearer {token}`
- **Response (204):** No content.
- **Response (403):** Forbidden — category is platform-level shared (FR-20).
- **Response (404):** Category not found.

---

### Question Categories (FR-015)
<!-- @sd-req: NFR-002 @rev: 4cd335bf @adopted -->
<!-- @sd-req: CON-003 @rev: 91e92119 @adopted -->
<!-- @sd-req: CON-002 @rev: 779a689a @adopted -->
<!-- @sd-req: CON-001 @rev: 2378496e @adopted -->
<!-- @sd-req: SR-007 @rev: f2e1f389 @adopted -->
<!-- @sd-req: SR-006 @rev: f46777a8 @adopted -->
<!-- @sd-req: NFR-001 @rev: 3086c5a4 @adopted -->
<!-- @sd-req: SR-005 @rev: 90d3e010 @adopted -->
<!-- @sd-req: SR-004 @rev: a0167166 @adopted -->
<!-- @sd-req: SR-003 @rev: 0e5d77e5 @adopted -->
<!-- @sd-req: SR-002 @rev: edffe5f9 @adopted -->
<!-- @sd-req: SR-001 @rev: 34f0722c @adopted -->
**Endpoint:** `GET /question-categories`
- **Description:** List all question categories accessible to the authenticated user.
- **Headers:** `Authorization: Bearer {token}`
- **Response (200):**
  ```
  {
    "categories": [
      {
        "question_category_id": string,
        "name": string,
        "description": string,
        "is_platform_shared": boolean,
        "created_by": string (user ID)
      }
    ]
  }
  ```

**Endpoint:** `POST /question-categories`
- **Description:** Create a new question category.
- **Headers:** `Authorization: Bearer {token}`
- **Request Body:**
  ```
  {
    "name": string (required, unique within scope),
    "description": string
  }
  ```
- **Validation:**
  - Reject duplicate category names with inline message (FR-015).
  - Reject missing name with inline message (FR-015).
- **Response (201):**
  ```
  {
    "question_category_id": string,
    "name": string,
    "description
## 7A. UI / UX DESIGN (JINJA2 + USWDS)
**[RECOMMENDED — Pending AA Approval]**

The Accessibility Assistant shall be rendered using **Jinja2 templating** for server-side HTML generation and **USWDS (U.S. Web Design System) v3.x** component library for all user-facing interfaces. This combination ensures compliance with WCAG 2.1 AA accessibility standards, responsive design across desktop and mobile viewports, and consistent visual language aligned with federal design best practices.

### Template Architecture

All screen designs shall be implemented as Jinja2 templates with the following structure:

- **Base template** (`base.html`): Defines the overall page layout, navigation structure, and common header/footer elements
- **Component templates**: Reusable Jinja2 macros for USWDS components (buttons, form fields, modals, tables, alerts)
- **Page templates**: Extend the base template and compose component macros for each screen (FAQ Browser, Conversational Assistant, admin configuration modals, etc.)

Jinja2 shall be configured to:
- Escape all user-supplied data by default to prevent XSS attacks
- Support conditional rendering of UI elements based on user role and authorization (e.g., hiding admin controls from End Users per FR-025, FR-026)
- Render server-side validation error messages inline adjacent to form fields (per scr-info-source-category-mgmt, scr-question-category-mgmt, scr-faq-manual-authoring input field specifications)

### USWDS Component Mapping

The following USWDS components shall be used for the specified screen elements:

| Screen / Element | USWDS Component | Notes |
|---|---|---|
| FAQ Browser (scr-faq-browser) left nav categories | `usa-nav` with `usa-accordion` | Keyboard-navigable; selected category announced via `aria-current="page"` |
| FAQ Browser right panel (FAQ list + detail) | `usa-accordion` | Multiple FAQs can expand simultaneously; answers expand inline |
| Conversational Assistant (scr-conversational-assistant) prompt input | `usa-input` with `usa-form-group` | Max 200 characters enforced; validation errors displayed inline |
| Submit button (all forms) | `usa-button` | Primary action; disabled state during loading (FR-002, FR-004) |
| Response display (citations, reasoning) | `usa-prose` wrapper with `usa-link` for citations | Hyperlinks to source material; reasoning section clearly labeled |
| Rating controls (thumbs up/down) | Custom USWDS-styled button pair or `usa-button-group` | Accessible labels; immutable after submission (FR-019) |
| Modal dialogs (admin config screens) | `usa-modal` | Focus trap; close button keyboard-accessible; `aria-modal="true"` and `aria-labelledby` |
| Form validation messages | `usa-alert` (alert role) or inline `usa-error-message` | Displayed adjacent to offending field; not auto-dismissed |
| Multi-select controls (FAQ authoring) | `usa-combo-box` or custom multi-select using USWDS styling | Keyboard-navigable; selected items announced to screen readers |
| Interaction log viewer (scr-interaction-log-viewer) table | `usa-table` | Read-only; no edit/delete controls per FR-021 |
| Empty-state messages | `usa-alert` (info role) | Displayed when no categories, FAQs, or logs exist |
| Loading indicator | USWDS spinner or progress indicator | Shown during LLM calls, access tests, MCP connectivity tests |
| In-app alerts (FR-008, FR-022, CON-004, CON-005, CON-006) | `usa-alert` (warning or error role) | Persistent until dismissed; role-specific messaging (e.g., "rate limit exceeded" for admins) |

### Responsive Design

All screens shall be responsive across the following breakpoints:

- **Desktop (≥ 1024px)**: Full layout with left nav sidebar (FAQ Browser) or full-width forms (admin config)
- **Tablet (640px–1023px)**: Left nav collapses to top dropdown or hamburger-triggered drawer; content area adjusts
- **Mobile (≤ 640px)**: Single-column layout; hamburger menu for navigation; prompt input and submit button pinned at top of Conversational Assistant; touch targets ≥ 44×44px for rating controls and buttons

Responsive behavior shall be achieved using USWDS grid system (`usa-grid`, `usa-grid-col`) and CSS media queries. No horizontal scrolling shall occur at any breakpoint (FR-001 acceptance criterion).

### Accessibility Requirements

All Jinja2-rendered HTML shall conform to WCAG 2.1 AA:

- **Keyboard navigation**: All interactive elements (buttons, links, form fields, accordions, modals) shall be keyboard-operable via Tab, Enter, Escape, and arrow keys
- **Screen reader support**: 
  - Form labels associated via `<label for="...">` or `aria-label`
  - Error messages linked to form fields via `aria-describedby`
  - Accordion expand/collapse announced via `aria-expanded`
  - Modal open/close announced via `aria-modal` and `aria-labelledby`
  - Conversation history updates announced via `aria-live="polite"` region (scr-conversational-assistant)
  - PII-containing data (user names, timestamps in interaction logs) not announced in bulk; individual row expansion keyboard-operable
  - Selected category in FAQ Browser announced via `aria-current="page"`
  - Disabled promotion controls (scr-platform-shared-resource-mgmt) carry accessible labels explaining ineligibility via `aria-describedby`
- **Color contrast**: All text and interactive elements shall meet WCAG AA contrast ratio (4.5:1 for normal text, 3:1 for large text)
- **Focus indicators**: Visible focus outline on all keyboard-navigable elements; USWDS provides default focus styling

### Form Validation & Error Handling

All forms (FAQ authoring, information source configuration, category management) shall:

- Display inline validation messages adjacent to the offending field using USWDS `usa-error-message` class
- Not submit the form if validation fails; modal remains open for correction
- Clear error messages when the user corrects the field
- For multi-select fields with no available options, display an empty-state message within the control (e.g., "No categories configured yet.")

### State Management & Conditional Rendering

Jinja2 templates shall conditionally render UI elements based on:

- **User role** (PERSONA-001, PERSONA-002, PERSONA-003, PERSONA-004): Admin controls hidden from End Users; platform-shared resource read-only indicators shown to non-creators
- **Data availability**: Empty-state messages when no categories, FAQs, sources, or logs exist
- **Loading state**: Submit/Save buttons disabled; loading indicator shown during async operations (LLM calls, access tests, MCP connectivity tests)
- **Session state** (Conversational Assistant): History area shows "Ask a question above to get started" when no questions have been asked; loading indicator during response generation
- **FAQ detail state** (FAQ Browser): Answers expand inline (accordion); category context remains visible in left nav

### Integration with Backend

Jinja2 templates shall:

- Receive context data from the Flask/backend application (user role, organization scope, FAQ list, category list, interaction logs, etc.)
- Use Jinja2 filters and tests to format data (e.g., date formatting, string truncation, role-based visibility)
- Submit form data via POST to backend endpoints; backend validates and returns error responses or success redirects
- Render server-side validation errors returned by the backend (e.g., "A category with this name already exists" per FR-010, FR-015)

### Security Considerations

- All user-supplied data rendered in templates shall be HTML-escaped by default (Jinja2 `autoescape=True`)
- CSRF tokens shall be included in all forms
- Credentials (GitHub tokens, MCP credentials) shall never be rendered in plaintext in templates; only masked or omitted representations displayed after initial save (scr-info-source-config state_deltas)
- PII-containing fields (user names, timestamps, question text) in interaction logs shall be marked with `sensitivity="pii"` and not announced in bulk to screen readers

---

*Rationale:* This recommendation is grounded in the captured screen designs (scr-faq-browser, scr-conversational-assistant, scr-info-source-config, scr-faq-manual-authoring, scr-interaction-log-viewer, etc.), the accessibility deltas specified for each screen, the responsive design requirements (mob-1, responsive_deltas fields), and the functional requirements for form validation (FR-002, FR-010, FR-015, FR-016), error handling (FR-008, CON-004, CON-005, CON-006), and role-based access control (FR-025, FR-026, FR-027). USWDS v3.x is the standard for U.S. federal digital services and provides out-of-the-box WCAG 2.1 AA compliance, responsive grid system, and accessible component patterns. Jinja2 is a mature, widely-adopted server-side templating engine that supports the conditional rendering, data escaping, and form handling required by the project's authorization and validation rules.
## 8. SEQUENCE FLOWS (MANDATORY FOR INTEGRATIONS)
### 8.1 User Asks Questions — Question Submission & Answer Retrieval

#### Overview
When an authenticated End User submits a question (FR-002), the system executes a two-tier answer retrieval pipeline: deterministic FAQ matching (FR-007) followed by LLM fallback (FR-008). The flow maintains conversational context across multiple turns within a session (FR-005) and logs all interactions persistently (FR-006).

#### Sequence: Question Submission → Deterministic Tier → LLM Fallback

```
End User → [Submit Question] → Input Validation
                                    ↓
                            [Empty or >200 chars?]
                                    ↓
                            YES → Reject + inline message
                            NO ↓
                        [Retrieve session context]
                                    ↓
                        [Deterministic FAQ Match]
                        (FR-007)
                                    ↓
                            [Match found?]
                                    ↓
                            YES → Return FAQ answer
                            NO ↓
                        [Invoke LLM Fallback]
                        (FR-008, via LiteLLM)
                                    ↓
                            [LLM succeeds?]
                                    ↓
                            YES → Return LLM response
                            NO ↓
                        [Both tiers exhausted]
                                    ↓
                        [Send no-answer alert to
                         Organization Administrator
                         & Content Manager]
                                    ↓
                        [Inform End User alert sent]
                                    ↓
                        [Log interaction record]
                        (FR-006)
                                    ↓
                        [Present rating control]
                        (FR-004, FR-019)
```

#### Deterministic Tier (FR-007)

1. **Question Intake:** System receives validated question text (1–200 characters) and optional question category selection (FR-003).
2. **FAQ Lookup:** System queries FAQ database for exact or semantic match against pre-built FAQ entries. Matching is performed deterministically without LLM invocation.
3. **Success Path:** If a matching FAQ is found, the system returns the FAQ answer directly, including:
   - Expository response text
   - Reasoning (if provided in FAQ)
   - Citations to applicable sources with hyperlinks (FR-004)
   - Thumbs up/down rating control (FR-004, FR-019)
4. **Fallthrough:** If no sufficient match is found, execution proceeds to LLM Fallback tier.

#### LLM Fallback Tier (FR-008)

1. **Configuration Check:** System determines whether LLM fallback is configured for the question's category and type:
   - **Retrieval-Augmented Mode:** LLM call is grounded against configured information sources (FR-009)
   - **Frontier Model Mode:** LLM call uses frontier model general knowledge (FR-009)

2. **Source Retrieval (if Retrieval-Augmented):**
   - System retrieves relevant content from configured information sources:
     - Local Code Repo or Document Folder (read-only, no-execute rule enforced)
     - GitHub/Online Repo via GitHub integration (timeout 20s, 3 retries, encrypted credentials)
     - MCP Server via MCP Server integration (timeout 20s, 3 retries, no-execute rule monitored)
   - Sanitization: PII and source code are removed before LLM invocation

3. **LLM Invocation (via LiteLLM):**
   - System sends sanitized question + retrieved context (if retrieval-augmented) to External LLM API
   - Operational contract: timeout 20000ms, 3 retries with custom backoff
   - LLM generates response containing:
     - Expository response text
     - Reasoning behind the response
     - Citations to applicable sources with hyperlinks
     - Structured format for presentation to End User

4. **LLM Failure Handling:**
   - **After 3 retries exhausted:** System degrades gracefully (CON-004)
     - End User receives failure-type-specific message (e.g., "AI assistant temporarily unavailable due to rate limiting")
     - Organization Administrator and Platform Administrator each receive in-app alert with specific error type (auth_failure, rate_limit, server_error, timeout)
     - FAQ browse-only mode remains available (FR-003)
   - **Error mapping:**
     - `auth_failure` → "authentication failure"
     - `rate_limit` → "rate limit exceeded"
     - `server_error` → "service unavailable"
     - `timeout` → "service timeout"

5. **No-Answer Path (Both Tiers Exhausted):**
   - System informs End User: "No answer is available for your question."
   - System sends in-app alert to Organization Administrator and Content Manager containing:
     - Question text
     - Submitting user's name
     - Time submitted
   - System informs End User that alert has been sent
   - Interaction is logged with null response field

#### Response Presentation (FR-004)

Regardless of tier (deterministic or LLM), the response presented to End User contains:
1. **Expository response text** — the answer itself
2. **Reasoning** — explanation of how the answer was derived
3. **Citations** — hyperlinks to source documents (or explicit statement if no sources available)
4. **Rating control** — thumbs up/down buttons (FR-019)

#### Multi-Turn Conversational Context (FR-005)

1. **Session Initialization:** When End User opens the assistant, a new session context is created (in-memory or session store).
2. **Context Accumulation:** Each question-response pair is added to the session context.
3. **Follow-Up Processing:** When End User submits a follow-up question:
   - System includes prior conversational context in the deterministic FAQ lookup and LLM fallback invocation
   - LLM receives full conversation history to ensure contextually coherent responses
4. **Session Termination:** When End User closes the window, session context is discarded. Next session starts fresh (no carryover from prior sessions).

#### Interaction Logging (FR-006)

After response is presented to End User (regardless of success or failure), system creates and persists a log record containing:
- **date-time group** — timestamp of question submission
- **question text** — verbatim user input
- **question category** — if selected by user (FR-003), otherwise null
- **response provided** — full response text (or null if no-answer path)
- **sources used** — list of information source IDs/names cited in response
- **thumbs up/down rating** — null until End User submits rating (FR-019)

**Failure Handling:** If log write operation fails (e.g., database error), response is still served to End User; failure is logged to system error log; End User is not shown a system error message.

#### Rating Submission (FR-019)

1. **Rating Control:** After response is displayed, End User may click thumbs up or thumbs down.
2. **Recording:** Rating is recorded and associated with the corresponding interaction log record.
3. **Immutability:** Once submitted, rating cannot be altered or deleted by End User or any administrator.
4. **Null Handling:** If End User does not submit a rating before closing the window, the rating field in the log record remains null.

---

### 8.2 Information Source Configuration — GitHub/Online Repo Integration

#### Overview
When an authorized user (Platform Administrator, Organization Administrator, or Content Manager) configures a GitHub/Online Repo information source (FR-013), the system validates connectivity and read access before persisting the configuration.

#### Sequence: GitHub Configuration → Credential Validation → Persistence

```
Authorized User → [Select GitHub/Online Repo] → [Configuration Form Opens]
                                                    ↓
                                        [Enter GitHub URL + Token/OAuth]
                                                    ↓
                                        [Submit Configuration]
                                                    ↓
                                    [Test Read Access]
                                    (timeout 20s, 3 retries)
                                                    ↓
                                        [Access succeeds?]
                                                    ↓
                                    YES → [Encrypt & store credentials]
                                          [Save source config]
                                          [Success notification]
                                          [Close window]
                                    NO ↓
                                    [Determine error type]
                                                    ↓
                                    [auth_failure?]
                                    [server_error?]
                                    [timeout?]
                                                    ↓
                                    [Display failure-type-specific message]
                                    [Send in-app alert to Org Admin & Platform Admin]
                                    [Prompt user to correct credentials]
```

#### Configuration Form Presentation (FR-013)

1. **Form Fields:**
   - GitHub repository URL (required)
   - Personal access token OR OAuth credentials (required)
2. **Validation:** All required fields must be populated before submission is allowed.

#### Read Access Test (FR-013)

1. **Test Invocation:** System initiates read access test against the GitHub repository using provided credentials.
2. **No-Execute Rule:** During the test, any executable code encountered in the repository is treated as read-only context; no code is executed under any circumstances.
3. **Operational Contract:**
   - Timeout: 20000ms
   - Retries: 3 (with 1-second delay before second attempt, 3-second delay before subsequent attempts)
   - Custom backoff applied
4. **Success Path:**
   - Read access is verified
   - Credentials are encrypted at rest (FIPS 140-2/140-3 validated)
   - Source configuration is persisted to database
   - User receives success notification
   - Configuration window closes
5. **Failure Path (after 3 retries exhausted):**
   - System determines error type and maps to specific alert message:
     - `auth_failure` → "authentication failure"
     - `server_error` → "service unavailable"
     - `timeout` → "service timeout"
   - User-facing message: failure-type-specific (e.g., "Authentication failed. Please check your token and try again.")
   - In-app alerts sent to Organization Administrator and Platform Administrator with specific error type
   - User is prompted to correct credentials and retry

#### Credential Storage (FR-013)

- Credentials (personal access token or OAuth token) are encrypted at rest using FIPS 140-2/140-3 validated encryption
- Encrypted credentials are stored in secure credential vault
- Credentials are never logged or displayed in plaintext in logs or UI

---

### 8.3 Information Source Configuration — MCP Server Integration

#### Overview
When an authorized user (Platform Administrator, Organization Administrator, or Content Manager) configures an MCP Server information source (FR-014), the system requires explicit connectivity test before allowing save.

#### Sequence: MCP Configuration → Connectivity Test → Persistence

```
Authorized User → [Select MCP Server] → [Configuration Form Opens]
                                            ↓
                                [Enter MCP Server Address + Credentials]
                                            ↓
                                [User triggers 'Test MCP']
                                            ↓
                                [Test Connectivity]
                                (timeout 20s, 3 retries)
                                            ↓
                                    [Connectivity succeeds?]
                                            ↓
                                YES → [Encrypt & store credentials]
                                      [Save source config]
                                      [Success notification]
                                      [Close window]
                                NO ↓
                                [Determine error type]
                                            ↓
                                [auth_failure?]
                                [server_error?]
                                [timeout?]
                                            ↓
                                [Display failure-type-specific message]
                                [Send in-app alert to Org Admin & Platform Admin]
                                [Prompt user to correct credentials]
                                [User may retry 'Test MCP']
```

#### Configuration Form Presentation (FR-014)

1. **Form Fields:**
   - MCP server address (required)
   - Credentials (required)
   - 'Test MCP' action button
2. **Save Gating:** User cannot save the configuration until 'Test MCP' has been successfully completed at least once.

#### Connectivity Test (FR-014)

1. **Test Invocation:** User clicks 'Test MCP' button; system initiates connectivity test against the MCP Server using provided credentials.
2. **No-Execute Rule Monitoring:** During the test and all subsequent operations, the no-execute rule is monitored. If a no-execute violation is detected:
   - In-app alert is delivered to Platform Administrator (FR-022)
   - Event is logged to audit log (FR-022)
   - User is notified of the violation
3. **Operational Contract:**
   - Timeout: 20000ms
   - Retries: 3 (with 1-second delay before second attempt, 3-second delay before subsequent attempts)
   - Custom backoff applied
4. **Success Path:**
   - Connectivity is verified
   - Credentials are encrypted at rest (FIPS 140-2/140-3 validated)
   - 'Test MCP' button state changes to indicate successful test
   - Save button becomes enabled
5. **Failure Path (after 3 retries exhausted):**
   - System determines error type and maps to specific alert message:
     - `auth_failure` → "authentication failure"
     - `server_error` → "service unavailable"
     - `timeout` → "service timeout"
   - User-facing message: failure-type-specific (e.g., "Connection timeout. Please check the server address and try again.")
   - In-app alerts sent to Organization Administrator and Platform Administrator with specific error type
   - User is prompted to correct credentials and retry 'Test MCP'
   - Save button remains disabled until test succeeds

#### Credential Storage (FR-014)

- Credentials are encrypted at rest using FIPS 140-2/140-3 validated encryption
- Encrypted credentials are stored in secure credential vault
- Credentials are never logged or displayed in plaintext in logs or UI

#### No-Execute Rule Violation Handling (FR-022)

If the no-execute rule is triggered on the MCP Server integration at any point (configuration test or runtime):
1. Violation is detected and logged
2. In-app alert is immediately delivered to Platform Administrator
3. Audit log entry is created with:
   - Timestamp of violation
   - MCP Server source identifier
   - Type of violation (attempted code execution)
   - User/context information
4. Audit log entries are immutable; no user may alter or delete them

---

### 8.4 Automated FAQ Generation — From Interaction Logs

#### Overview
When an authorized user (Platform Administrator, Organization Administrator, or Content Manager) triggers automated FAQ generation from interaction logs (FR-017), the system invokes an LLM to cluster similar questions and generate FAQ candidates. All candidates require explicit human approval before save.

#### Sequence: Trigger → LLM Review → Human Approval → Persistence

```
Authorized User → [Trigger Automated FAQ Generation]
                        ↓
                [System retrieves interaction logs]
                        ↓
                [Invoke LLM to cluster & generate]
                (via LiteLLM, timeout 20s, 3 retries)
                        ↓
                [LLM succeeds?]
                        ↓
            YES → [Present FAQ candidates to user]
                  [Each candidate shows:]
                  - Merged question text
                  - Recommended question categories
                  - Recommended source categories
                  - Recommended sources
                  - Recommended response
                  - Checkboxes for approval
                  - Free-text edit fields
                        ↓
            [User reviews candidates]
                        ↓
            [User approves/edits via checkboxes & free-text]
                        ↓
            [User confirms save]
                        ↓
            [Approved FAQs saved to database]
            (FR-016 validation applied)
                        ↓
            [Success notification]
            
            NO → [LLM failure handling]
                 [Display failure-type-specific message]
                 [Send in-app alert to Org Admin & Platform Admin]
                 [No FAQ candidates generated]
```

#### LLM Review Process (FR-017)

1. **Log Retrieval:** System retrieves all interaction log records within the specified scope (organization or platform-wide, depending on user role).
2. **Clustering:** LLM analyzes question text and clusters semantically similar questions.
3. **Candidate Generation:** For each cluster, LLM generates:
   - Merged question text (representative of the cluster)
   - Recommended question categories (multi-select options)
   - Recommended source categories (multi-select options)
   - Recommended sources (multi-select options)
   - Recommended response text
4. **Presentation:** System displays all candidates in a review interface with:
   - Checkboxes for
## 9. TRACEABILITY MATRIX (HARD REQUIREMENT)
| Requirement ID | Type | Upstream Source | Traceability Notes |
|---|---|---|---|
| **SR-001** | Security | DESIGN.md §7 API Contracts | Credential encryption at rest (AES-256-GCM); plaintext never persisted; FIPS compliance enforced; routes: `POST /api/information-sources/`, `PUT /api/information-sources/{source_id}/credential`, `GET /api/information-sources/` |
| **SR-002** | Security | DESIGN.md §7 API Contracts | PII and source-code blocking before LLM submission; `QuestionSanitizationService` evaluates text; blocked submissions return `422`; route: `POST /api/questions/` |
| **SR-003** | Security | DESIGN.md §7 API Contracts | Row-level access control for interaction logs; owner-only read for end users; admin read-only view; immutability enforced; cross-user access triggers alert dispatch; routes: `GET /api/interaction-logs/`, `GET /api/interaction-logs/{log_id}`, `GET /api/admin/interaction-logs/` |
| **SR-004** | Security | DESIGN.md §7 API Contracts | No-execute violation alert and audit log; persistent in-app alerts (no expiry); append-only audit rows; routes: `POST /api/internal/information-sources/{source_id}/no-execute-violation`, `GET /api/platform/alerts/`, `PATCH /api/platform/alerts/{alert_id}/read`, `GET /api/platform/audit-log/` |
| **SR-005** | Security | DESIGN.md §7 API Contracts | No-execute rule for connected source content; read-only ingestion pipeline; no subprocess/exec/eval in code path; payload sanitization strips injection vectors; routes: `POST /api/information-sources/{source_id}/ingest`, `GET /api/information-sources/{source_id}/context` |
| **SR-006** | Security | DESIGN.md §7 API Contracts | Sanitization of external LLM API payloads (PII and source code); mandatory pre-flight step in egress service; redaction placeholders used; routes: `POST /api/llm/tier2-fallback`, `POST /api/llm/faq-generation` |
| **SR-007** | Security | DESIGN.md §7 API Contracts | PII classification and access restriction for interaction logs; user-scoped queries via explicit `user_id` predicate; no mutation endpoints; routes: `GET /api/interaction-logs/`, `GET /api/interaction-logs/{log_id}`, `GET /api/admin/interaction-logs/` |
| **FR-001** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-001 | Self-service assistant interface (responsive, resizable window); desktop icon and embedded HTML link entry points; unauthenticated redirect to login; route: `GET /assistant/` |
| **FR-002** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-002 | Question submission with 200-character limit; empty submission rejection; server-side validation via Pydantic; route: `POST /api/assistant/questions` |
| **FR-003** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-003 | FAQ category browse and answer view; empty-state handling; routes: `GET /api/categories/`, `GET /api/categories/{category_id}/faqs/`, `GET /api/faqs/{faq_id}/` |
| **FR-004** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-004 | Structured response with expository text, reasoning, citations, and rating control; citations include hyperlinks; no-source fallback; rating scaffold; routes: `POST /api/questions/`, `POST /api/questions/{response_id}/rating` |
| **FR-005** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-005 | Multi-turn conversational context within session; Redis-backed message history; session isolation on termination; routes: `POST /api/sessions/{session_id}/turns`, `DELETE /api/sessions/{session_id}`, `POST /api/sessions/` |
| **FR-006** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-006 | Persistent interaction log capture; write-failure isolation (error logged, response still served); routes: `POST /api/interactions/`, `PATCH /api/interactions/{interaction_id}/rating` |
| **FR-007** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-007 | Deterministic-first question answering (FAQ/script tier before LLM); Tier 1 resolution via `DeterministicAnswerService`; fallback signal to FR-008; route: `POST /api/questions/` |
| **FR-008** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-008 | Tiered answer fallback (deterministic → LLM RAG/frontier → unanswerable); unanswerable alert dispatch to org admin and content manager; routes: `POST /api/questions/answer`, `GET /api/questions/alerts`, `PATCH /api/questions/alerts/{alert_id}/acknowledge` |
| **FR-009** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-009 | LLM fallback mode configuration per (category, question-type); `retrieval_augmented` vs `frontier_general_knowledge`; end-user denial; routes: `GET /api/llm-fallback-config/`, `GET /api/llm-fallback-config/{category}/{question_type}`, `PUT /api/llm-fallback-config/{category}/{question_type}`, `DELETE /api/llm-fallback-config/{category}/{question_type}` |
| **FR-010** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-010 | Information source category configuration; duplicate name rejection; route: `POST /api/information-source-categories/` |
| **FR-011** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-011 | Four information source types (local_code_repo, github_online_repo, document_folder, mcp_server); discriminated-union validation; route: `GET /api/information-sources/source-types`, `POST /api/information-sources/` |
| **FR-012** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-012 | Local code repo/document folder: folder picker, read-access test, no-execute enforcement; structural ban on subprocess/exec/eval; routes: `POST /api/information-sources/local/validate-access`, `POST /api/information-sources/local/` |
| **FR-013** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-013 | GitHub/online repo: form with URL and credential; read-access verification (no code execution); window-close signalling; routes: `POST /api/information-sources/github/verify`, `POST /api/information-sources/github/` |
| **FR-014** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-014 | MCP server: form with address and credential; connectivity test gate; save requires passed test; routes: `POST /api/information-sources/mcp/test`, `POST /api/information-sources/` (mcp_server type) |
| **FR-015** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-015 | Question category configuration; duplicate name rejection (case-insensitive); end-user/content-manager denial; route: `POST /api/question-categories/` |
| **FR-016** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-016 | Manual FAQ creation; multi-select categories/sources; all required fields validated; end-user denial; route: `POST /api/faqs/` |
| **FR-017** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-017 | Automated FAQ generation from interaction logs; LLM review and merge; human-approval gating; no auto-save; routes: `POST /api/faqs/generation-sessions/`, `GET /api/faqs/generation-sessions/{session_id}/candidates/`, `POST /api/faqs/generation-sessions/{session_id}/confirm/` |
| **FR-018** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-018 | Automated FAQ generation from information source; LLM review; human-approval gating; no auto-save; routes: `POST /api/faqs/generate`, `POST /api/faqs/generate/confirm` |
| **FR-019** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-019 | End-user response rating (thumbs up/down); immutability enforced (no update/delete endpoints); route: `POST /api/interactions/{interaction_id}/rating` |
| **FR-020** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-020 | Platform-level shared resource designation; read-only for org admin/content manager; routes: `PATCH /api/information-sources/{source_id}/sharing`, `PATCH /api/information-source-categories/{category_id}/sharing`, `PATCH /api/faqs/{faq_id}/sharing` |
| **FR-021** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-021 | Interaction log viewer (read-only, role-scoped); platform admin cross-org view; org admin org-scoped view; content manager/end-user denial; routes: `GET /api/admin/interaction-logs/` |
| **FR-022** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-022 | No-execute rule violation alert and audit log; persistent in-app alerts; append-only audit rows; routes: `POST /api/information-sources/violations/no-execute`, `GET /api/alerts/` |
| **FR-023** | Functional | DESIGN.md §7 API Contracts | Automated FAQ generation from interaction logs; LLM clustering and merging; candidate persistence; routes: `POST /api/faq/generate`, `GET /api/faq/candidates` |
| **FR-024** | Functional | DESIGN.md §7 API Contracts | LLM fallback answer generation (Tier 2); deterministic tier first; LLM call on insufficient result; route: `POST /api/query/answer` |
| **FR-025** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-025 | Organization-scoped data isolation with platform-shared exceptions; chassis `TenantScoped` mixin enforces isolation; `is_platform_shared` flag gates read-only visibility; write-protection for shared records; routes: `GET /api/faqs/`, `POST/PUT/DELETE /api/faqs/`, `GET /api/information-source-categories/`, `GET /api/information-sources/` |
| **FR-026** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-026 | No user impersonation by administrators; no "act-as" parameter; identity derived solely from `Depends(get_current_user)`; structural absence of impersonation surface |
| **FR-027** | Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-027 | Platform-level sharing eligibility restricted to platform-admin-created resources; `creator_role` stamped at creation; eligibility check before promotion; routes: `PATCH /api/information-sources/{source_id}/sharing`, `PATCH /api/information-source-categories/{category_id}/sharing`, `PATCH /api/faqs/{faq_id}/sharing` |
| **NFR-001** | Non-Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md FR-017, FR-018 | No auto-save of LLM-generated FAQ candidates without explicit human approval; candidates staged in `faq_candidates` table (status `pending`); only confirmation path writes to `faqs` table; routes: `POST /api/faqs/candidates/`, `POST /api/faqs/candidates/{session_id}/confirm`, `DELETE /api/faqs/candidates/{session_id}` |
| **NFR-002** | Non-Functional | DESIGN.md §7 API Contracts; REQUIREMENTS.md NFR-002 | LLM provider and API key selection via chassis configuration UI; no application-owned route; all LLM calls route through chassis LiteLLM integration (CON-001) |
| **CON-001** | Compliance | DESIGN.md §7 API Contracts | All LLM API calls routed via chassis LiteLLM integration; no provider SDK imported directly; provider selection via chassis configuration UI; route: `GET /api/compliance/llm-routing` (informational only) |
| **CON-002** | Compliance | DESIGN.md §7 API Contracts | FedRAMP and ITAR compliant hosting environment; no application constraint; deployment-layer concern; no HTTP endpoint defined |
| **CON-003** | Compliance | DESIGN.md §7 API Contracts | ITAR data residency (all data at rest and in transit within US); startup validation of configured endpoints; route: `GET /api/compliance/data-residency/status` |
| **CON-004** | Constraint | DESIGN.md §7 API Contracts; REQUIREMENTS.md CON-004 | Graceful degradation to FAQ browse-only mode on LLM unavailability; retry exhaustion (3 attempts, exponential backoff); failure-type-specific messaging and alerting; routes: `POST /api/llm/chat`, `GET /api/llm/status` |
| **CON-005** | Constraint | DESIGN.md §7 API Contracts; REQUIREMENTS.md CON-005 | GitHub/online repo integration retry exhaustion; 3 retries (1s, 3s delays); failure-type-specific messaging and alerting; routes: GitHub integration endpoints (§7.y.1, §7.y.2) |
| **CON-006** | Constraint | DESIGN.md §7 API Contracts; REQUIREMENTS.md CON-006 | MCP server integration retry exhaustion; 3 retries (1s, 3s delays); failure-type-specific messaging and alerting; routes: `POST /api/mcp/` and related MCP endpoints |
## 10. DESIGN OUTPUT CONTRACT

The AI generating TASKS.md MUST:
- Create ≥1 task per Design section.
- Reference Design section IDs.
- Identify an Alembic migration task for every new or changed data model.

The AI generating TEST-SCENARIOS.md MUST:
- Create ≥1 test per Requirement ID.
- Include external integration tests (httpx mocked via `respx` or a recorded cassette).

---

*This document was generated by the SD-Agile Spec Builder from the project's Golden Record, on the autonomous-platform-chassis-python foundation.*
