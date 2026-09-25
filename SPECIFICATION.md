---
template: python-specification
version: "3.0"
document_type: SPECIFICATION.md
locked_section_aware: true
---

# Accessibility Assistant — Software Requirements Specification (SRS)
<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## Standalone IEEE/ISO-Style Specification (Python 3.12 · FastAPI · SQLAlchemy 2.0 · PostgreSQL)

**Project:** Accessibility Assistant
**Foundation:** autonomous-platform-chassis-python (FastAPI 0.115 on Uvicorn · async SQLAlchemy 2.0 / Alembic · Pydantic v2 · PostgreSQL · Redis · server-rendered Jinja2 + USWDS)
**Generated From:** REQUIREMENTS.md + DESIGN.md + CONSTITUTION.md + the Golden Record
**Generated Date:** 2026-09-21
**Document Status:** Derived (system-synthesized at finalization)

**Purpose.** This is the **human-readable, standalone Software Requirements Specification** for Accessibility Assistant, structured per ISO/IEC/IEEE 29148. It consolidates the project's requirements, design, and constraints into one self-contained narrative document. It is sufficient on its own for a stakeholder to understand the system, for an architect to validate it, and for a developer to implement it — with or without the SD-Agile platform or the Python chassis. It does NOT introduce new requirements: every statement is synthesized from REQUIREMENTS.md, DESIGN.md, CONSTITUTION.md, and the Golden Record, and traces back to them.

---

<!-- @owned-by:  | @role: system | @system-derives-from: REQUIREMENTS.md, DESIGN.md, CONSTITUTION.md | @locked-by-chassis: false -->
## 1. Introduction
*Pending — system-derived from REQUIREMENTS.md, DESIGN.md, CONSTITUTION.md*

## 2. Overall Description
*Pending — system-derived from Golden Record (Business Context & Processes — AS-IS/TO-BE, Org Context), DESIGN.md#2. SYSTEM OVERVIEW*

## 3. System Architecture Overview
*Pending — system-derived from DESIGN.md, Golden Record (User Personas & Actor Classes)*

## 4. Specific Requirements — Functional
### FR-001 — Self-Service Question-Answering Interface

The system shall provide a responsive, resizable assistant window accessible via desktop icon or embedded HTML link. Unauthenticated users are redirected to the login page before any assistant content is rendered.

**Acceptance Criteria:**
- A responsive, resizable window opens when accessed via desktop icon or embedded HTML link, with all core interface elements visible without horizontal scrolling.
- Unauthenticated users are redirected to the login page; no assistant content is displayed.

**Implementation:** Route `GET /assistant/` serves the responsive Jinja2 template using USWDS 3.x grid utilities. The `Depends(get_current_user)` dependency enforces authentication; unauthenticated requests receive a `302 Found` redirect to `/login`. The same HTML response is returned regardless of entry point (desktop icon or embedded link); the embedding context is handled entirely client-side.

---

### FR-002 — End-User Question Submission with Character Limit

The system shall allow end users to submit questions via a text prompt, limited to 200 characters. Empty submissions and submissions exceeding 200 characters are rejected with inline validation messages before any retrieval or LLM call is initiated.

**Acceptance Criteria:**
- Valid questions (1–200 characters) are accepted and initiate the answer retrieval process.
- Empty submissions are rejected with an inline validation message; no retrieval or LLM call is made.
- Questions exceeding 200 characters are rejected with an inline message stating the limit; no retrieval or LLM call is made.

**Implementation:** Pydantic v2 schema `QuestionRequest` declares `question: str = Field(min_length=1, max_length=200)`. FastAPI's default validation-error handler converts schema violations to `422` responses before any service method is invoked. The route is decorated with `@audited("assistant:question_submitted")` only after successful validation.

---

### FR-003 — End-User FAQ Category Browse and Answer View

The system shall allow end users to select a question category and browse FAQs within that category, then select an FAQ to view its full answer. Empty-state messages are displayed when no categories exist or when a category contains no FAQs.

**Acceptance Criteria:**
- When at least one category with at least one FAQ exists, selecting the category displays the FAQ list.
- Selecting an FAQ displays the full answer.
- When a category exists but contains no FAQs, an empty-state message is displayed.
- When no categories have been configured, an empty-state message is displayed.

**Implementation:** Three endpoints support this flow:
- `GET /api/categories/` returns all question categories for the current tenant; returns empty list when none exist.
- `GET /api/categories/{category_id}/faqs/` returns FAQs for a specific category; returns empty list when the category exists but has no FAQs.
- `GET /api/faqs/{faq_id}/` returns the complete FAQ record with full answer text.

All queries are tenant-scoped via the chassis `TenantScoped` mixin. The client is responsible for rendering empty-state messages based on empty response arrays.

---

### FR-004 — Structured Question Response with Citations and Rating Control

The system shall present a structured response to every question containing: (1) expository response text, (2) reasoning behind the response, (3) citations to applicable sources with hyperlinks, and (4) a thumbs up / thumbs down rating control.

**Acceptance Criteria:**
- Responses contain expository text, reasoning, at least one citation with a working hyperlink, and a rating control.
- Citation hyperlinks navigate to the cited source document or location.
- When no relevant sources are found, the response includes expository text and reasoning, and clearly indicates that no source citations are available rather than displaying broken links.

**Implementation:** Route `POST /api/questions/` invokes the retrieval and LLM pipeline, assembling a `QuestionResponse` object containing:
- `answer`: expository response text
- `reasoning`: LLM-provided reasoning
- `citations`: array of `Citation` objects (each with `title`, `url`, `excerpt`)
- `citations_available`: boolean flag indicating whether citations are present
- `rating`: scaffold object for user feedback submission

When retrieval returns zero documents, `citations` is set to an empty array and `citations_available` is `false`; no broken links are emitted. The response is persisted before the route returns, ensuring the `response_id` is stable for subsequent rating submission.

---

### FR-005 — Multi-Turn Conversational Context Within a Session

The system shall support multi-turn follow-up questions within a session, maintaining conversational context across turns. Session context is not carried over when a new session is opened.

**Acceptance Criteria:**
- Follow-up questions use prior conversational context when generating responses.
- Follow-up questions referencing prior answers are contextually coherent with the prior exchange.
- When a session ends and a new session is opened, no conversational context from the prior session is carried over.

**Implementation:** Session context is stored in Redis, keyed by session ID. Each turn appends the user message and assistant response to the history as `{"role": "user", "content": ...}` and `{"role": "assistant", "content": ...}` entries. The full history is passed to the LLM egress endpoint on every call. Session termination via `DELETE /api/sessions/{session_id}` purges the Redis key, ensuring new sessions start with empty history. The Redis key TTL is reset on every successful turn.

---

### FR-006 — Persistent Interaction Log Record Capture

The system shall capture and persistently store a log record for every user interaction containing: date-time group, question text, question category, response provided, sources used, and thumbs up/down rating.

**Acceptance Criteria:**
- Log records are persisted containing all required fields.
- When a user does not submit a rating, the rating field is recorded as null, not defaulted to a value.
- When the log write operation fails, the response is still served to the End User; the failure is logged to the system error log; the End User is not shown a system error.

**Implementation:** Route `POST /api/interactions/` accepts the completed interaction payload and delegates to `InteractionLogService.record()`. The service wraps the database write in a try/except block; if the write fails, the exception is caught, logged via `structlog` at `ERROR` level with a correlation ID, and not re-raised. The response to the End User is unaffected. The `rating` field is stored as `NULL` when not provided; no sentinel or default value is substituted.

---

### FR-007 — Deterministic-First Question Answering (FAQ / Script Tier Before LLM)

The system shall first attempt to answer every user question deterministically using pre-built FAQs and/or Python scripts executed against configured information sources, without invoking an LLM.

**Acceptance Criteria:**
- The system first attempts to match the question against pre-built FAQs before invoking any LLM call.
- When a pre-built FAQ matches the user's question, the FAQ answer is returned directly without making an LLM API call.
- When no matching FAQ exists, the system falls through to the LLM fallback tier (FR-008).

**Implementation:** Route `POST /api/questions/` delegates to `QuestionResolutionService.resolve()`, which executes three ordered steps:
1. **FAQ matching:** Query the tenant-scoped FAQ store for a match (exact-match slug, keyword set, or regex pattern). If found, return immediately with `source="faq"` and `llm_invoked=false`.
2. **Script execution:** If no FAQ match, execute applicable Python scripts via `ScriptExecutorService.run()` (sandboxed, async, timeout-bounded). If a script returns a non-empty answer, return with `source="script"` and `llm_invoked=false`.
3. **Fallback signal:** If neither step produces a sufficient answer, return `fallback_required=true` and delegate to the LLM fallback tier (FR-008).

---

### FR-008 — Tiered Answer Fallback with LLM Retrieval-Augmented Generation and Unanswerable Alert

If the deterministic answer tier cannot produce a sufficient response, the system shall fall back to an LLM call operating against configured information sources (retrieval-augmented) or against frontier model general knowledge based on the question type and information category. If neither tier can produce a sufficient response, the system shall inform the user that no answer is available, send an in-app alert to the Organization Administrator and Content Manager containing the question text, the submitting user's name, and the time submitted, and inform the user that this alert has been sent.

**Acceptance Criteria:**
- When the deterministic tier cannot produce a sufficient response, the LLM fallback is invoked against configured information sources, returning an expository response with reasoning and citations.
- When neither tier can produce a sufficient response, the system informs the user that no answer is available, sends an in-app alert to the Organization Administrator and Content Manager containing the question text, submitting user's name, and time submitted, and informs the user that this alert has been sent.
- When the LLM fallback is configured to use frontier model general knowledge for a given question type, the system queries the frontier model rather than configured information sources.

**Implementation:** Route `POST /api/questions/answer` delegates to `AnswerOrchestrationService.resolve()`, which executes ordered logic:
1. **Deterministic tier:** Invoke `DeterministicAnswerService.attempt()`. If sufficient, return with `tier: "deterministic"`.
2. **LLM fallback — mode selection:** Inspect `question_type` and `information_category` to select `rag` (retrieval-augmented) or `frontier` (general knowledge) mode.
3. **LLM response evaluation:** If the LLM fallback returns a sufficient response, return with `tier: "llm_rag"` or `tier: "llm_frontier"` as appropriate, including `reasoning` and `citations` (citations omitted for frontier mode).
4. **Unanswerable path:** If neither tier produces a sufficient response, call `AlertDispatchService.send_unanswerable_alert()` to create in-app alert records for all Organization Administrators and Content Managers within the current tenant, then return `tier: "unanswerable"` with a user-facing message and `alert_sent: true`.

---

### FR-009 — LLM Fallback Mode Configuration per Information Source Category and Question Type

The system shall allow administrators to configure, per information source category and per question type, whether the LLM fallback call is grounded against configured information sources (retrieval-augmented) or against frontier model general knowledge.

**Acceptance Criteria:**
- Platform Administrators and Organization Administrators can select either retrieval-augmented or frontier model general knowledge as the fallback mode for a given category and question type.
- When the fallback mode is set to retrieval-augmented, the LLM call is grounded against the configured information sources for that category.
- When the fallback mode is set to frontier model general knowledge, the LLM call uses frontier model general knowledge rather than configured sources.
- End Users attempting to access the LLM fallback configuration receive an authorization error.

**Implementation:** Routes `GET /api/llm-fallback-config/`, `GET /api/llm-fallback-config/{category}/{question_type}`, `PUT /api/llm-fallback-config/{category}/{question_type}`, and `DELETE /api/llm-fallback-config/{category}/{question_type}` manage per-(category, question-type) fallback mode records. The `PUT` endpoint validates that at least one information source is configured for the given category when `fallback_mode` is `retrieval_augmented`. The `LLMFallbackDispatchService` reads the stored mode at query time and branches between retrieval-augmented and frontier-model-general-knowledge call paths. End Users lacking `llm_fallback_config:write` receive `403 Forbidden`.

---

### FR-010 — Configure Information Source Categories

The system shall allow administrators to configure information source categories by providing a category name and description. Duplicate category names must be rejected.

**Acceptance Criteria:**
- Platform Administrators and Organization Administrators can submit a new information source category with a unique name and description; the category is saved and appears in the category list.
- When a category name already exists within the applicable scope, the submission is rejected with an inline validation message; no duplicate category is created.
- When a category is submitted with a missing name, the submission is rejected with an inline validation message indicating name is required.
- End Users and Content Managers attempting to create an information source category receive an authorization error.

**Implementation:** Route `POST /api/information-source-categories/` accepts a new category (name + description) and delegates to `InformationSourceCategoryService.create()`. The service validates that `name` is non-empty; if absent or blank, it raises `ValidationError` before any DB interaction. Before insert, the service queries for an existing category row with the same `name` within the current tenant (auto-filtered by the chassis `TenantScoped` mixin). If a match is found, it raises `DuplicateCategoryNameError`; no row is inserted. The route is decorated with `@audited("information_source_category:create")`. End Users and Content Managers lacking `information_source_categories:write` receive `403 Forbidden`.

---

### FR-011 — Four Information Source Types for Configuration

The system shall support four information source types for configuration: Local Code Repo, GitHub/Online Repo, Document Folder, and MCP Server.

**Acceptance Criteria:**
- Exactly four source types are available: Local Code Repo, GitHub/Online Repo, Document Folder, and MCP Server.
- The UI presents the correct input form for each source type: folder picker for Local Code Repo and Document Folder; URL and credential form for GitHub/Online Repo; server address and credential form for MCP Server.
- End Users attempting to access information source configuration receive an authorization error.

**Implementation:** Route `GET /api/information-sources/source-types` returns a static list of exactly four entries: `local_code_repo`, `github_online_repo`, `document_folder`, `mcp_server`. Each entry includes a `form_variant` hint (`folder_picker`, `url_and_credential`, or `server_address_and_credential`) that the UI uses to select the correct input form. Route `POST /api/information-sources/` uses Pydantic v2 discriminated-union validation (discriminator field: `source_type`) to select the appropriate request schema; an unrecognised `source_type` value is rejected before the service layer is reached. End Users lacking `information_sources:read` receive `403 Forbidden`.

---

### FR-012 — Local Code Repo / Document Folder Information Source: Folder Picker, Read-Access Test, and No-Execute Enforcement

When configuring a Local Code Repo or Document Folder information source, the system shall present a folder picker. Upon selection, the system shall test read access to the folder contents. The system must enforce a strict no-execute rule at the code level — code in connected sources must never be executed by the system. On success, the user shall receive a success notification and the window shall close. On failure, the user shall be notified and prompted to provide credentials.

**Acceptance Criteria:**
- A folder picker is presented for Local Code Repo or Document Folder source types.
- The system verifies read access to the folder contents without executing any code found within.
- The user receives a success notification and the configuration window closes with the source saved on successful access test.
- The user is notified of failure and prompted to provide or correct credentials on failed access test.
- Code found in a connected source is treated as read-only context; no code is executed under any circumstances.

**Implementation:** Route `POST /api/information-sources/local/validate-access` tests read access to a candidate folder path via `LocalSourceAccessService.test_read_access()`. The service resolves the path with `pathlib.Path.resolve()` and attempts to list immediate directory entries (`iterdir()`) — a read-only operation. No file content is opened, parsed, interpreted, or executed. The no-execute constraint is structural: `subprocess`, `exec`, `eval`, `compile`, `importlib`, and shell-invocation primitives are forbidden imports in all modules under `app/slots/information_sources/`; the CI linter enforces this via a banned-import rule. Route `POST /api/information-sources/local/` persists a validated local information source configuration after a successful access test. The route calls `LocalSourceAccessService.test_read_access()` a second time before committing, ensuring the stored path is still accessible at save time. Any credential values are encrypted at rest via `CredentialEncryptionService` (AES-256-GCM) before the ORM write; only ciphertext is persisted.

---

### FR-013 — GitHub/Online Repo Information Source Configuration Form with Read-Access Verification

When configuring a GitHub/Online Repo information source, the system shall present a form for entering a GitHub URL and personal access token or OAuth credentials. The system shall test read access with a strict no-execute rule enforced at the code level. On success, the user shall receive a success notification and the window shall close. On failure, the user shall be notified and prompted to correct credentials.

**Acceptance Criteria:**
- A form
## 5. Specific Requirements — Business Rules
*Pending — system-derived from REQUIREMENTS.md#4. BUSINESS RULES (BR)*

## 6. External Interface Requirements
*Pending — system-derived from Golden Record (UI/UX notes, persona journeys), REQUIREMENTS.md#2.14 Frontend & Accessibility (Platform-Provided Foundation), DESIGN.md#7. API CONTRACTS (FASTAPI)*

## 7. Non-Functional Requirements
*Pending — system-derived from REQUIREMENTS.md#5. NON-FUNCTIONAL REQUIREMENTS (NFR) (deltas only), REQUIREMENTS.md#2.17 Non-Functional Baselines (inherited)*

## 8. Data Requirements
The SD-Agile Platform manages the following application-owned data entities, all persisted via SQLAlchemy 2.0 `AsyncSession` and migrated through Alembic.

### Core Data Entities

#### User
Represents an authenticated user of the platform, scoped to a persona and optionally an organization.

| Field | Type | Required | Unique | PII | Description |
|---|---|---|---|---|---|
| id | uuid | yes | no | no | Unique user identifier |
| name | string | yes | no | no | User display name |
| email | string | yes | no | no | User email address |
| role | enum (platform_admin, org_admin, content_manager, end_user) | yes | no | no | User role determining access level |
| organization_id | uuid | no | no | no | Associated organization; null for platform admins |
| created_at | timestamp | yes | no | no | Record creation timestamp |
| updated_at | timestamp | yes | no | no | Record last modification timestamp |

#### Organization
A tenant grouping that scopes users, information source categories, question categories, and information sources.

| Field | Type | Required | Unique | PII | Description |
|---|---|---|---|---|---|
| id | uuid | yes | no | no | Unique organization identifier |
| name | string | yes | no | no | Organization display name |
| created_at | timestamp | yes | no | no | Record creation timestamp |
| updated_at | timestamp | yes | no | no | Record last modification timestamp |

#### InformationSourceCategory
A classification grouping for information sources, configurable at platform or organization level.

| Field | Type | Required | Unique | PII | Description |
|---|---|---|---|---|---|
| id | uuid | yes | no | no | Unique category identifier |
| name | string | yes | no | no | Category display name |
| organization_id | uuid | no | no | no | Associated organization; null for platform-level categories |
| created_by | uuid | yes | no | no | User ID of creator |
| created_at | timestamp | yes | no | no | Record creation timestamp |
| updated_at | timestamp | yes | no | no | Record last modification timestamp |

#### InformationSource
A configured data source (e.g., GitHub repository, MCP Server) whose credentials are stored encrypted at rest. Tracks no-execute rule state for alerting.

| Field | Type | Required | Unique | PII | Description |
|---|---|---|---|---|---|
| id | uuid | yes | no | no | Unique source identifier |
| name | string | yes | no | no | Source display name |
| category_id | uuid | yes | no | no | Associated InformationSourceCategory |
| organization_id | uuid | no | no | no | Associated organization; null for platform-level sources |
| source_type | enum (github, mcp_server, other) | yes | no | no | Type of information source |
| credentials_encrypted | blob | yes | no | no | Encrypted credential material |
| no_execute_triggered | boolean | yes | no | no | Flag indicating if no-execute rule has been triggered |
| created_by | uuid | yes | no | no | User ID of creator |
| created_at | timestamp | yes | no | no | Record creation timestamp |
| updated_at | timestamp | yes | no | no | Record last modification timestamp |

#### QuestionCategory
A classification grouping for FAQ entries and user questions, configurable at platform or organization level.

| Field | Type | Required | Unique | PII | Description |
|---|---|---|---|---|---|
| id | uuid | yes | no | no | Unique category identifier |
| name | string | yes | no | no | Category display name |
| organization_id | uuid | no | no | no | Associated organization; null for platform-level categories |
| created_by | uuid | yes | no | no | User ID of creator |
| created_at | timestamp | yes | no | no | Record creation timestamp |
| updated_at | timestamp | yes | no | no | Record last modification timestamp |

#### FAQ
A question-and-answer entry created manually by a content manager or generated automatically by the system.

| Field | Type | Required | Unique | PII | Description |
|---|---|---|---|---|---|
| id | uuid | yes | no | no | Unique FAQ entry identifier |
| question | string | yes | no | no | Question text |
| answer | text | yes | no | no | Answer text |
| question_category_id | uuid | no | no | no | Associated QuestionCategory |
| organization_id | uuid | no | no | no | Associated organization; null for platform-level FAQs |
| origin | enum (manual, automated) | yes | no | no | Source of FAQ entry (user-created or system-generated) |
| created_by | uuid | yes | no | no | User ID of creator |
| created_at | timestamp | yes | no | no | Record creation timestamp |
| updated_at | timestamp | yes | no | no | Record last modification timestamp |

#### InteractionLog
A record of a user's question session, including user identity and organization. Access is restricted by role; records are immutable after creation.

| Field | Type | Required | Unique | PII | Description |
|---|---|---|---|---|---|
| id | uuid | yes | no | no | Unique log entry identifier |
| user_id | uuid | yes | no | no | Associated User |
| user_name | string | yes | no | no | User name at time of interaction |
| organization_id | uuid | yes | no | no | Associated Organization |
| question_text | text | yes | no | no | User's question text |
| response_text | text | yes | no | no | System response text |
| information_source_ids | array<uuid> | no | no | no | InformationSource IDs consulted for response |
| created_at | timestamp | yes | no | no | Record creation timestamp (immutable) |

#### AuditLog
An immutable system-level event record used to track security-relevant actions including no-execute rule triggers, credential changes, and administrative operations.

| Field | Type | Required | Unique | PII | Description |
|---|---|---|---|---|---|
| id | uuid | yes | no | no | Unique audit entry identifier |
| event_type | string | yes | no | no | Type of event (e.g., "no_execute_triggered", "credential_updated") |
| actor_user_id | uuid | no | no | no | User ID of actor; null for system-initiated events |
| target_entity_type | string | no | no | no | Type of entity affected by event |
| target_entity_id | uuid | no | no | no | ID of entity affected by event |
| organization_id | uuid | no | no | no | Associated Organization |
| detail | json | no | no | no | Event-specific metadata |
| created_at | timestamp | yes | no | no | Record creation timestamp (immutable) |

#### InAppAlert
A notification delivered to the Platform Administrator when a no-execute rule is triggered on a connected information source.

| Field | Type | Required | Unique | PII | Description |
|---|---|---|---|---|---|
| id | uuid | yes | no | no | Unique alert identifier |
| recipient_user_id | uuid | yes | no | no | Platform Administrator User ID |
| information_source_id | uuid | yes | no | no | Associated InformationSource |
| message | string | yes | no | no | Alert message text |
| read | boolean | yes | no | no | Flag indicating if alert has been read |
| created_at | timestamp | yes | no | no | Record creation timestamp |

### Data Access & Persistence

All data entities are persisted through SQLAlchemy 2.0 `AsyncSession` objects. Schema changes are managed via Alembic migrations (ordered, additive-only revisions under `migrations/versions/`). All data access must use async patterns; synchronous `Session` objects and 1.x-style `Query` APIs are forbidden.

Service classes (e.g., `UserService`, `InformationSourceService`) implement CRUD and query operations via `AsyncSession`, with organization-scoping applied where applicable. Sensitive fields (e.g., `credentials_encrypted`) are encrypted at rest. Immutable records (InteractionLog, AuditLog) are write-once and never updated.
## 9. Verification & Acceptance
*Pending — system-derived from TEST-SCENARIOS.md, REQUIREMENTS.md#3. FUNCTIONAL REQUIREMENTS (FR)*

## 10. Requirements Traceability Matrix
This section synthesizes the Requirements Traceability Matrix from REQUIREMENTS.md §6 and DESIGN.md §9, providing a unified view of how each requirement flows from personas and processes through design decisions to implementation tasks and test coverage.

### Matrix Overview

The following table maps all 40 requirements across five dimensions:

1. **Requirement ID & Statement**: Unique identifier and brief description
2. **Personas & Processes**: Who uses this feature and in which workflow
3. **Design Realization**: Architectural component or API contract (cross-referenced to DESIGN.md §7)
4. **Implementation Tasks**: Task ID(s) from TASKS.md
5. **Test Coverage**: Test scenario ID(s) from test suite

| Req ID | Statement | Personas | Processes | Design Component | Tasks | Tests |
|---|---|---|---|---|---|---|
| **SR-001** | Encrypt all information source credentials (AES-256-GCM, FIPS) | Platform Admin, Org Admin, Content Manager | Configure Information Sources | Credential encryption at rest; routes: `POST /api/information-sources/`, `PUT /api/information-sources/{source_id}/credential` | T-004 | TS-003, TS-004 |
| **SR-002** | Block user questions containing PII or source code before LLM submission | End User | User Asks Questions | `QuestionSanitizationService` evaluates text; `422` rejection; route: `POST /api/questions/` | T-010 | TS-001, TS-002, TS-012, TS-SR002 |
| **SR-003** | Classify interaction logs as PII; enforce row-level access control | Platform Admin, Org Admin, Content Manager, End User | User Asks Questions | Owner-only read for end users; admin read-only view; immutability enforced; routes: `GET /api/interaction-logs/`, `GET /api/admin/interaction-logs/` | T-014 | TS-005, TS-006, TS-007, TS-008, TS-013, TS-SR003 |
| **SR-004** | Alert and audit-log when no-execute rule is triggered on connected source | Platform Admin | Configure Information Sources | No-execute violation alert dispatch; persistent in-app alerts; append-only audit rows; routes: `POST /api/internal/information-sources/{source_id}/no-execute-violation`, `GET /api/platform/alerts/` | T-004 | TS-009, TS-010, TS-011, TS-SR004 |
| **SR-005** | Enforce strict no-execute rule at code level; no subprocess/exec/eval in ingestion | Platform Admin, Org Admin, Content Manager | Configure Information Sources | Read-only ingestion pipeline; payload sanitization strips injection vectors; route: `POST /api/information-sources/{source_id}/ingest` | T-003 | TS-SR005 |
| **SR-006** | Sanitize all content sent to external LLM APIs (PII and source code redaction) | End User | User Asks Questions | Mandatory pre-flight sanitization in egress service; redaction placeholders; routes: `POST /api/llm/tier2-fallback`, `POST /api/llm/faq-generation` | T-016 | TS-SR006, TS-SR006-1, TS-SR006-2, TS-SR006-3, TS-SR006-tier2 |
| **SR-007** | Classify interaction logs as PII; restrict access via explicit `user_id` predicate | Platform Admin, Org Admin, Content Manager, End User | User Asks Questions | User-scoped queries; no mutation endpoints; routes: `GET /api/interaction-logs/`, `GET /api/admin/interaction-logs/` | T-014 | TS-SR007, TS-SR007-1, TS-SR007-2, TS-SR007-3 |
| **FR-001** | Provide self-service question-answering interface (responsive, resizable) | End User | User Asks Questions | Desktop icon and embedded HTML entry points; unauthenticated redirect to login; route: `GET /assistant/` | T-009 | TS-FR001, TS-FR001-1, TS-FR001-2, TS-FR001-3 |
| **FR-002** | Allow end users to submit questions via text input (200-char limit) | End User | User Asks Questions | Server-side validation via Pydantic; empty submission rejection; route: `POST /api/assistant/questions` | T-010 | TS-FR002, TS-FR002-1, TS-FR002-2, TS-FR002-3 |
| **FR-003** | Allow end users to select category and browse FAQ list | End User | User Asks Questions | Empty-state handling; routes: `GET /api/categories/`, `GET /api/categories/{category_id}/faqs/`, `GET /api/faqs/{faq_id}/` | T-011 | TS-FR003, TS-FR003-1, TS-FR003-2, TS-FR003-3 |
| **FR-004** | Present structured response (expository text, reasoning, citations, rating control) | End User | User Asks Questions | Citations include hyperlinks; no-source fallback; rating scaffold; routes: `POST /api/questions/`, `POST /api/questions/{response_id}/rating` | T-012 | TS-FR004-1, TS-FR004-2 |
| **FR-005** | Support multi-turn follow-up questions within session with context maintenance | End User | User Asks Questions | Redis-backed message history; session isolation on termination; routes: `POST /api/sessions/{session_id}/turns`, `DELETE /api/sessions/{session_id}` | T-013 | TS-FR005-1, TS-FR005-2 |
| **FR-006** | Capture and persistently store log record for every user interaction | End User | User Asks Questions | Write-failure isolation (error logged, response still served); routes: `POST /api/interactions/`, `PATCH /api/interactions/{interaction_id}/rating` | T-014 | TS-FR006-1, TS-FR006-2 |
| **FR-007** | Attempt deterministic answer first (FAQ/script tier before LLM) | End User | User Asks Questions | `DeterministicAnswerService` resolves Tier 1; fallback signal to FR-008; route: `POST /api/questions/` | T-015 | TS-FR007-1, TS-FR007-2 |
| **FR-008** | Fallback to LLM RAG/frontier if deterministic tier insufficient; alert on unanswerable | End User, Org Admin, Content Manager | User Asks Questions | Tiered answer fallback (deterministic → LLM RAG/frontier → unanswerable); alert dispatch to org admin and content manager; routes: `POST /api/questions/answer`, `GET /api/questions/alerts` | T-016 | TS-FR008-1, TS-FR008-2 |
| **FR-009** | Configure LLM fallback mode per (category, question-type) | Platform Admin, Org Admin | User Asks Questions | `retrieval_augmented` vs `frontier_general_knowledge` modes; end-user denial; routes: `GET /api/llm-fallback-config/`, `PUT /api/llm-fallback-config/{category}/{question_type}` | T-017 | TS-FR009-1, TS-FR009-2 |
| **FR-010** | Configure information source categories; reject duplicate names | Platform Admin, Org Admin | Configure Information Source Categories | Duplicate name rejection; route: `POST /api/information-source-categories/` | T-002 | TS-FR010-1, TS-FR010-2, TS-FR010-3 |
| **FR-011** | Support four information source types (local_code_repo, github_online_repo, document_folder, mcp_server) | Platform Admin, Org Admin, Content Manager | Configure Information Sources | Discriminated-union validation; route: `GET /api/information-sources/source-types`, `POST /api/information-sources/` | T-003 | TS-FR011-1, TS-FR011-2 |
| **FR-012** | Local code repo/document folder: folder picker, read-access test, no-execute enforcement | Platform Admin, Org Admin, Content Manager | Configure Information Sources | Structural ban on subprocess/exec/eval; routes: `POST /api/information-sources/local/validate-access`, `POST /api/information-sources/local/` | T-003 | TS-FR012-1, TS-FR012-2, TS-FR012-3, TS-FR012-4 |
| **FR-013** | GitHub/online repo: form with URL and credential; read-access verification | Platform Admin, Org Admin, Content Manager | Configure Information Sources | No code execution; window-close signalling; routes: `POST /api/information-sources/github/verify`, `POST /api/information-sources/github/` | T-003 | TS-FR013-1, TS-FR013-2, TS-FR013-3, TS-FR013-4 |
| **FR-014** | MCP server: form with address and credential; connectivity test gate | Platform Admin, Org Admin, Content Manager | Configure Information Sources | Save requires passed test; routes: `POST /api/information-sources/mcp/test`, `POST /api/information-sources/` (mcp_server type) | T-003 | TS-FR014-1, TS-FR014-2, TS-FR014-3, TS-FR014-4 |
| **FR-015** | Configure question categories; reject duplicate names (case-insensitive) | Platform Admin, Org Admin | Configure Question Categories | End-user/content-manager denial; route: `POST /api/question-categories/` | T-005 | TS-FR015-1, TS-FR015-2, TS-FR015-3 |
| **FR-016** | Manually create FAQ entries; multi-select categories/sources; all fields validated | Platform Admin, Org Admin, Content Manager | CRUD FAQ — Manual | End-user denial; route: `POST /api/faqs/` | T-006 | TS-FR016, TS-FR016-1, TS-FR016-2, TS-FR016-3 |
| **FR-017** | Trigger automated FAQ generation from interaction logs; LLM review and merge; human-approval gating | Platform Admin, Org Admin, Content Manager | CRUD FAQ — Automated | No auto-save; routes: `POST /api/faqs/generation-sessions/`, `GET /api/faqs/generation-sessions/{session_id}/candidates/`, `POST /api/faqs/generation-sessions/{session_id}/confirm/` | T-007 | TS-FR017, TS-FR017-1, TS-FR017-2, TS-FR017-3 |
| **FR-018** | Trigger automated FAQ generation from information source; LLM review; human-approval gating | Platform Admin, Org Admin, Content Manager | CRUD FAQ — Automated | No auto-save; routes: `POST /api/faqs/generate`, `POST /api/faqs/generate/confirm` | T-008 | TS-FR018, TS-FR018-1, TS-FR018-2, TS-FR018-3 |
| **FR-019** | Allow authenticated end user to rate response as helpful/unhelpful; immutability enforced | End User | User Asks Questions | Thumbs up/down; no update/delete endpoints; route: `POST /api/interactions/{interaction_id}/rating` | T-019 | TS-FR019, TS-FR019-1, TS-FR019-2, TS-FR019-3 |
| **FR-020** | Designate any information source as platform-level shared resource (read-only for org admin/content manager) | Platform Admin, Org Admin, Content Manager | Configure Information Sources | Routes: `PATCH /api/information-sources/{source_id}/sharing`, `PATCH /api/information-source-categories/{category_id}/sharing`, `PATCH /api/faqs/{faq_id}/sharing` | T-020 | TS-FR020, TS-FR020-1, TS-FR020-2, TS-FR020-3 |
| **FR-021** | Interaction log viewer (read-only, role-scoped); platform admin cross-org view; org admin org-scoped view | Platform Admin, Org Admin, Content Manager, End User | User Asks Questions | Content manager/end-user denial; routes: `GET /api/admin/interaction-logs/` | T-021 | TS-FR021, TS-FR021-1, TS-FR021-2, TS-FR021-3, TS-FR021-4 |
| **FR-022** | Alert and audit-log when no-execute rule violation occurs | Platform Admin | Configure Information Sources | Persistent in-app alerts; append-only audit rows; routes: `POST /api/information-sources/violations/no-execute`, `GET /api/alerts/` | T-022 | TS-FR022, TS-FR022-1, TS-FR022-2, TS-FR022-3 |
| **FR-025** | Organization-scoped data isolation with platform-shared exceptions; `is_platform_shared` flag gates read-only visibility | Org Admin, Content Manager | User Asks Questions | Chassis `TenantScoped` mixin enforces isolation; write-protection for shared records; routes: `GET /api/faqs/`, `POST/PUT/DELETE /api/faqs/`, `GET /api/information-source-categories/` | T-023 | TS-014, TS-015 |
| **FR-026** | No user impersonation by administrators; no "act-as" parameter | Platform Admin, Org Admin | User Asks Questions | Identity derived solely from `Depends(get_current_user)`; structural absence of impersonation surface | T-024 | TS-016, TS-017 |
| **FR-027** | Platform-level sharing eligibility restricted to platform-admin-created resources; `creator_role` stamped at creation | Platform Admin | Configure Information Sources | Eligibility check before promotion; routes: `PATCH /api/information-sources/{source_id}/sharing`, `PATCH /api/information-source-categories/{category_id}/sharing`, `PATCH /api/faqs/{faq_id}/sharing` | T-025 | TS-018, TS-019 |
| **NFR-001** | No auto-save of LLM-generated FAQs without explicit human approval | Platform Admin, Org Admin, Content Manager | CRUD FAQ — Manual, CRUD FAQ — Automated | Candidates staged in `faq_candidates` table (status `pending`); only confirmation path writes to `faqs` table; routes: `POST /api/faqs/candidates/`, `POST /api/faqs/candidates/{session_id}/confirm` | T-007, T-008 | TS-NFR001, TS-NFR001-1, TS-NFR001-2 |
| **NFR-002** | LLM provider and API key selection via chassis configuration UI | Platform Admin | Configure Information Sources | No application-owned route; all LLM calls route through chassis LiteLLM integration (CON-001) | T-026 | TS-NFR002 |
| **CON-001** | All LLM API calls routed via chassis LiteLLM integration | Platform Admin | User Asks Questions | No provider SDK imported directly; provider selection via chassis configuration UI; route: `GET /api/compliance/llm-routing` (informational only) | T-027 | TS-CON001, TS-CON001-1, TS-CON001-2, TS-CON001-3 |
| **CON-002** | FedRAMP and ITAR compliant hosting environment | Platform Admin | Configure Information Sources | No application constraint; deployment-layer concern; no HTTP endpoint defined | T-028 | TS-CON002, TS-CON002-1, TS-CON002-2 |
| **CON-003** | ITAR data residency (all data at rest and in transit within US) | Platform Admin | User Asks Questions | Startup validation of configured endpoints; route: `GET /api/compliance/data-residency/status` | T-029 | TS-CON003 |
| **CON-004** | Graceful degradation to FAQ browse-only mode on LLM unavailability; 3 retries with exponential backoff | End User | User Asks Questions | Failure-type-specific messaging
## 11. Appendices
### A. Glossary of Terms

| Term | Definition |
|------|-----------|
| SD-Agile Platform | The guided wizard system for specification synthesis and document management. |
| Specification Document | A structured markdown file containing requirements, design, and implementation guidance. |
| Upstream Context | Previously defined sections or requirements that inform the current section's content. |
| Persona | A representative user archetype used to define stakeholder needs and use cases. |
| Functional Requirement (FR) | A specific capability or behavior the system must provide. |
| Non-Functional Requirement (NFR) | A quality attribute or constraint on system performance, security, or usability. |
| User Story | A brief narrative describing a feature from the user's perspective, typically in the format "As a [persona], I want [capability] so that [benefit]." |
| Acceptance Criteria | Specific, testable conditions that must be met for a user story or requirement to be considered complete. |
| Task (T-NNN) | An atomic unit of work with a unique identifier, assigned to a sprint or backlog. |
| Design Pattern | A reusable solution to a common problem in system architecture or implementation. |
| Data Model | The structure and relationships of data entities within the system. |
| API Endpoint | A specific URL or service interface through which external systems interact with the platform. |
| Sprint | A fixed time-boxed iteration (typically 1–4 weeks) for development and delivery. |
| Backlog | A prioritized list of features, enhancements, and fixes awaiting implementation. |

### B. Document Structure Reference

The SD-Agile Platform specification follows a standard multi-section format:

- **REQUIREMENTS.md** – Functional and non-functional requirements, personas, and user stories.
- **DESIGN.md** – System architecture, data models, API specifications, and design patterns.
- **TASKS.md** – Sprint planning, task breakdown, and work assignments.
- **SPECIFICATION.md** – Consolidated specification with appendices and cross-references.

### C. Cross-Reference Index

All requirements, tasks, and design elements are identified by unique codes:

- **FR-NNN** – Functional Requirement identifier
- **NFR-NNN** – Non-Functional Requirement identifier
- **T-NNN** – Task identifier
- **API-NNN** – API Endpoint identifier
- **DM-NNN** – Data Model identifier

### D. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | TBD | Platform Team | Initial specification synthesis |

### E. Related Documents

- Product Roadmap
- Architecture Decision Records (ADRs)
- API Documentation
- User Guide and Training Materials
- Security and Compliance Policies
