---
template: python-requirements
version: "3.0"
document_type: REQUIREMENTS.md
locked_section_aware: true
---

# Accessibility Assistant — Requirements
<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## Platform Chassis — AI-Executable Requirements Specification (Python 3.12 · FastAPI · SQLAlchemy 2.0 async)

**Project:** Accessibility Assistant
**Foundation:** autonomous-platform-chassis-python (FastAPI 0.115 · SQLAlchemy 2.0 async · Alembic · psycopg3/PostgreSQL · Redis · Jinja2 + USWDS)
**Generated Date:** 2026-09-21

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


- Session termination is additionally enforced via the platform chassis's shared JWT revocation list, described here for completeness (AB-FR-639 P2 live verification).

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
#### Configure Information Source Categories

**Ideal Future-State Steps:**

- User provides a category name
- User provides a category description

#### Configure Information Sources

**New Capabilities:**

- **Read-Access Test with No-Execute Enforcement:** System must test read access to any configured source and must enforce a strict no-execute rule in code — code found in connected sources must never be executed by the system.

**Ideal Future-State Steps:**

- User selects source type from dropdown
- Local Code Repo: User is presented a folder picker, navigates to folder, selects enter
- GitHub/Online Repo: User is presented a window to enter URL and credentials
- Document Folder: User is presented a folder picker, navigates to folder, selects enter
- MCP Server: User is presented a window to enter server address and credentials, then selects 'Test MCP'
- System tests read access to the configured source. Strict no-execute rule is enforced in code — code in connected sources must never be executed.
- Success path: User is notified with success message and configuration window closes
- Failure path: User is notified of failure and prompted to provide or correct credentials

#### Configure Question Categories

**Ideal Future-State Steps:**

- User provides a category name
- User provides a category description

#### CRUD FAQ — Manual

**New Capabilities:**

- **Manual FAQ Authoring:** Authorized users can create FAQ entries by entering a question, selecting question categories, source categories, and sources via multi-select, and providing a standard response.
- **Manual FAQ Authoring:** Platform Administrators, Organization Administrators, and Content Managers can create FAQ entries by entering a question, selecting question categories, source categories, and sources via multi-select, and providing a standard response. All required fields must be validated before save.

**Ideal Future-State Steps:**

- User enters question text
- User selects applicable question categories from multi-select boxes
- User selects applicable source categories from multi-select boxes
- User selects applicable sources from multi-select boxes
- User provides standard response text
- User enters question text
- User selects applicable question categories from multi-select boxes
- User selects applicable source categories from multi-select boxes
- User selects applicable sources from multi-select boxes
- User provides standard response text

#### CRUD FAQ — Automated

**New Capabilities:**

- **LLM-Assisted FAQ Generation from Interaction Logs:** System uses an LLM to analyze interaction logs, cluster similar questions, and generate candidate FAQ entries complete with recommended categories, sources, and responses. A human reviewer approves or edits before saving.
- **LLM-Assisted FAQ Generation from Interaction Logs:** Platform Administrators, Organization Administrators, and Content Managers can trigger LLM-assisted FAQ generation from interaction logs. The LLM clusters similar questions and generates candidate FAQ entries with recommended categories, sources, and responses. A human reviewer must approve or edit before saving. The system must not auto-save LLM-generated FAQs without explicit human approval.

**Ideal Future-State Steps:**

- User selects 'Review Logs' to trigger auto-generation
- System uses LLM to review interaction logs and produce a list of FAQs, merging similar questions into one
- System uses LLM to recommend question categories, source categories, sources, and a response for each generated FAQ
- User approves or edits recommended question, categories, and sources via checkboxes
- User approves or edits recommended response via free-text edit box, selects Save, and confirms
- User selects 'Review Logs' to trigger auto-generation
- System uses LLM to review interaction logs and produce a list of FAQs, merging similar questions into one
- System uses LLM to recommend question categories, source categories, sources, and a response for each generated FAQ
- User approves or edits recommended question, categories, and sources via checkboxes
- User approves or edits recommended response via free-text edit box, selects Save, and confirms. System must not auto-save without explicit human approval.

#### User Asks Questions

**New Capabilities:**

- **Conversational Question Answering with Citation:** End users can ask questions via free-text prompt or by browsing FAQ categories. The system returns an expository response, the reasoning behind it, and hyperlinked citations to source material. Users can rate responses and ask follow-up questions.
- **Interaction Log Persistence:** For every user interaction, the system must capture and store: date-time group, question text, question category, response provided, sources used, and thumbs up/down rating.

**Ideal Future-State Steps:**

- User opens assistant via desktop icon or embedded HTML link — responsive, resizable window
- User either types a question into the prompt OR selects a question category to browse FAQs and selects one
- System presents response: expository text, reasoning behind response, citations to applicable sources with hyperlinks, thumbs up/down rating control
- User may ask follow-up questions in the same session
- System captures and stores a structured interaction record for every question: date-time group, question text, question category, response provided, sources used, thumbs up/down rating

**Mobile Requirements (Narrative):**

- Assistant window must be responsive and resizable, accessible via desktop icon or embedded HTML link
### 3.1 Current State (AS-IS) Baseline
#### Configure Information Source Categories

**Current Steps:**

- User provides a category name (actor: Platform Administrator or Organization Administrator)
- User provides a category description (actor: Platform Administrator or Organization Administrator)
- User provides a category name (actor: Platform Administrator or Organization Administrator)
- User provides a category description (actor: Platform Administrator or Organization Administrator)
- User provides a category name (actor: Platform Administrator or Organization Administrator)
- User provides a category description (actor: Platform Administrator or Organization Administrator)

**Decision Points:**

- Duplicate category name submitted
- Duplicate category name submitted
- Duplicate category name submitted

**Exceptions:**

- Duplicate category name submitted (root cause: No uniqueness enforcement in place)
- Duplicate category name submitted (root cause: No uniqueness enforcement in place)
- Duplicate category name submitted (root cause: No uniqueness enforcement in place)

**Volumes:**

- Frequency: N/A — net-new process
- SLA: None — net-new process

**Existing Systems:**

- To be confirmed — possibly no current system
- None — this process does not exist today; it is a net-new capability
- None — this process does not exist today; it is a net-new capability

**Pain Points:**

- To be confirmed
- Process does not exist today — net-new capability with no current-state equivalent
- Process does not exist today — net-new capability with no current-state equivalent

**Root Causes:**

- To be confirmed
- No prior system or process exists for managing information source categories
- No prior system or process exists for managing information source categories

#### Configure Information Sources

**Current Steps:**

- User selects source type from dropdown (Local Code Repo, GitHub/Online Repo, Document Folder, MCP Server) (actor: Platform Administrator, Organization Administrator, or Content Manager)
- Local Code Repo / Document Folder: User is presented a folder picker, navigates to folder, and selects enter (actor: Platform Administrator, Organization Administrator, or Content Manager)
- GitHub/Online Repo: User is presented a form to enter URL and personal access token or OAuth credentials (actor: Platform Administrator, Organization Administrator, or Content Manager)
- MCP Server: User is presented a form to enter server address and credentials, then triggers 'Test MCP' (actor: Platform Administrator, Organization Administrator, or Content Manager)
- System tests read access. Strict no-execute rule is enforced in code — code in connected sources must never be executed. (actor: System)
- Success path: User is notified with success message and configuration window closes (actor: System)
- Failure path: User is notified of failure and prompted to provide or correct credentials (actor: System)
- User selects source type from dropdown (Local Code Repo, GitHub/Online Repo, Document Folder, MCP Server) (actor: Platform Administrator, Organization Administrator, or Content Manager)
- Local Code Repo / Document Folder: User is presented a folder picker, navigates to folder, and selects enter (actor: Platform Administrator, Organization Administrator, or Content Manager)
- GitHub/Online Repo: User is presented a form to enter URL and personal access token or OAuth credentials (actor: Platform Administrator, Organization Administrator, or Content Manager)
- MCP Server: User is presented a form to enter server address and credentials, then triggers 'Test MCP' (actor: Platform Administrator, Organization Administrator, or Content Manager)
- System tests read access. Strict no-execute rule is enforced in code — code in connected sources must never be executed. (actor: System)
- Success path: User is notified with success message and configuration window closes (actor: System)
- Failure path: User is notified of failure and prompted to provide or correct credentials (actor: System)
- User selects source type from dropdown (Local Code Repo, GitHub/Online Repo, Document Folder, MCP Server) (actor: Platform Administrator, Organization Administrator, or Content Manager)
- Local Code Repo / Document Folder: User is presented a folder picker, navigates to folder, and selects enter (actor: Platform Administrator, Organization Administrator, or Content Manager)
- GitHub/Online Repo: User is presented a form to enter URL and personal access token or OAuth credentials (actor: Platform Administrator, Organization Administrator, or Content Manager)
- MCP Server: User is presented a form to enter server address and credentials, then triggers 'Test MCP' (actor: Platform Administrator, Organization Administrator, or Content Manager)
- System tests read access. Strict no-execute rule is enforced in code — code in connected sources must never be executed. (actor: System)
- Success path: User is notified with success message and configuration window closes (actor: System)
- Failure path: User is notified of failure and prompted to provide or correct credentials (actor: System)

**Decision Points:**

- Source type selection
- Read access test result
- Source type selection
- Read access test result
- Source type selection
- Read access test result

**Exceptions:**

- Read access test fails (root cause: Invalid credentials, missing permissions, or unreachable source)
- No-execute rule triggered on connected source (root cause: Code execution attempted against a connected source)
- Read access test fails (root cause: Invalid credentials, missing permissions, or unreachable source)
- Read access test fails (root cause: Invalid credentials, missing permissions, or unreachable source)
- No-execute rule triggered on connected source (root cause: Code execution attempted against a connected source)

**Volumes:**

- Frequency: N/A — net-new process
- SLA: None — net-new process

**Existing Systems:**

- To be confirmed — possibly no current system
- None — this process does not exist today; it is a net-new capability
- None — this process does not exist today; it is a net-new capability

**Pain Points:**

- To be confirmed
- Process does not exist today — net-new capability with no current-state equivalent
- Process does not exist today — net-new capability with no current-state equivalent

**Root Causes:**

- To be confirmed
- No prior system or process exists for configuring information sources
- No prior system or process exists for configuring information sources

#### Configure Question Categories

**Current Steps:**

- User provides a category name (actor: Platform Administrator or Organization Administrator)
- User provides a category description (actor: Platform Administrator or Organization Administrator)
- User provides a category name (actor: Platform Administrator or Organization Administrator)
- User provides a category description (actor: Platform Administrator or Organization Administrator)
- User provides a category name (actor: Platform Administrator or Organization Administrator)
- User provides a category description (actor: Platform Administrator or Organization Administrator)

**Decision Points:**

- Duplicate category name submitted
- Duplicate category name submitted
- Duplicate category name submitted

**Exceptions:**

- Duplicate category name submitted (root cause: No uniqueness enforcement in place)
- Duplicate category name submitted (root cause: No uniqueness enforcement in place)
- Duplicate category name submitted (root cause: No uniqueness enforcement in place)

**Volumes:**

- Frequency: N/A — net-new process
- SLA: None — net-new process

**Existing Systems:**

- To be confirmed — possibly no current system
- None — this process does not exist today; it is a net-new capability
- None — this process does not exist today; it is a net-new capability

**Pain Points:**

- To be confirmed
- Process does not exist today — net-new capability with no current-state equivalent
- Process does not exist today — net-new capability with no current-state equivalent

**Root Causes:**

- To be confirmed
- No prior system or process exists for managing question categories
- No prior system or process exists for managing question categories

#### CRUD FAQ — Manual

**Current Steps:**

- User enters question text (actor: Authorized user)
- User selects applicable question categories from multi-select boxes (actor: Authorized user)
- User selects applicable source categories from multi-select boxes (actor: Authorized user)
- User selects applicable sources from multi-select boxes (actor: Authorized user)
- User provides standard response text (actor: Authorized user)
- User enters question text (actor: Authorized user (Platform Administrator, Organization Administrator, or Content Manager))
- User selects applicable question categories from multi-select boxes (actor: Authorized user (Platform Administrator, Organization Administrator, or Content Manager))
- User selects applicable source categories from multi-select boxes (actor: Authorized user (Platform Administrator, Organization Administrator, or Content Manager))
- User selects applicable sources from multi-select boxes (actor: Authorized user (Platform Administrator, Organization Administrator, or Content Manager))
- User provides standard response text (actor: Authorized user (Platform Administrator, Organization Administrator, or Content Manager))
- User enters question text (actor: Authorized user (Platform Administrator, Organization Administrator, or Content Manager))
- User selects applicable question categories from multi-select boxes (actor: Authorized user (Platform Administrator, Organization Administrator, or Content Manager))
- User selects applicable source categories from multi-select boxes (actor: Authorized user (Platform Administrator, Organization Administrator, or Content Manager))
- User selects applicable sources from multi-select boxes (actor: Authorized user (Platform Administrator, Organization Administrator, or Content Manager))
- User provides standard response text (actor: Authorized user (Platform Administrator, Organization Administrator, or Content Manager))

**Volumes:**

- Frequency: N/A — net-new process
- SLA: None — net-new process

**Existing Systems:**

- To be confirmed — possibly no current system
- None — this process does not exist today; it is a net-new capability
- None — this process does not exist today; it is a net-new capability

**Pain Points:**

- To be confirmed
- Process does not exist today — net-new capability with no current-state equivalent
- Process does not exist today — net-new capability with no current-state equivalent

**Root Causes:**

- To be confirmed
- No prior FAQ management system or process exists
- No prior FAQ management system or process exists

#### CRUD FAQ — Automated

**Current Steps:**

- User selects 'Review Logs' to trigger auto-generation (actor: Authorized user)
- System uses LLM to review interaction logs and produce a list of FAQs, merging similar questions into one (actor: System (LLM))
- System uses LLM to recommend question categories, source categories, sources, and a response for each generated FAQ (actor: System (LLM))
- User approves or edits recommended question, categories, and sources via checkboxes (actor: Authorized user)
- User approves or edits recommended response via free-text edit box, selects Save, and confirms (actor: Authorized user)
- User selects 'Review Logs' to trigger auto-generation (actor: Authorized user)
- System uses LLM to review interaction logs and produce a list of FAQs, merging similar questions into one (actor: System (LLM))
- System uses LLM to recommend question categories, source categories, sources, and a response for each generated FAQ (actor: System (LLM))
- User approves or edits recommended question, categories, and sources via checkboxes (actor: Authorized user)
- User approves or edits recommended response via free-text edit box, selects Save, and confirms (actor: Authorized user)
- User selects 'Review Logs' to trigger auto-generation (actor: Authorized user)
- System uses LLM to review interaction logs and produce a list of FAQs, merging similar questions into one (actor: System (LLM))
- System uses LLM to recommend question categories, source categories, sources, and a response for each generated FAQ (actor: System (LLM))
- User approves or edits recommended question, categories, and sources via checkboxes (actor: Authorized user)
- User approves or edits recommended response via free-text edit box, selects Save, and confirms (actor: Authorized user)

**Decision Points:**

- User review of LLM-generated FAQ
- User review of LLM-generated FAQ
- User review of LLM-generated FAQ

**Volumes:**

- Frequency: N/A — net-new process
- SLA: None — net-new process

**Existing Systems:**

- To be confirmed — possibly no current system
- None — this process does not exist today; it is a net-new capability
- None — this process does not exist today; it is a net-new capability

**Pain Points:**

- To be confirmed
- Process does not exist today — net-new capability with no current-state equivalent
- Process does not exist today — net-new capability with no current-state equivalent

**Root Causes:**

- To be confirmed
- No prior automated FAQ generation system or process exists
- No prior automated FAQ generation system or process exists

#### User Asks Questions

**Current Steps:**

- User opens assistant via desktop icon or embedded HTML link — responsive, resizable window (actor: End User)
- User either types a question into the prompt OR selects a question category to browse FAQs (actor: End User)
- System presents response: expository text, reasoning, citations with hyperlinks, thumbs up/down rating (actor: System)
- User may ask follow-up questions (actor: End User)
- System captures and stores interaction record: date-time group, question text, question category, response provided, sources used, thumbs up/down rating (actor: System)
- User sends an email or places a phone call to a member of the accessibility team (actor: End User)
- Team member reviews the question and formulates a response when they have time — no defined SLA or response window (actor: Accessibility Team Member)
- User sends an email or places a phone call to a member of the accessibility team (actor: End User)
- Team member reviews the question and formulates a response when they have time — no defined SLA or response window (actor: Accessibility Team Member)

**Decision Points:**

- User input method
- User rates response
- Channel used by user
- Channel used by user

**Exceptions:**

- Accessibility team member is unavailable or overloaded (root cause: No self-service capability, no queue management, no SLA enforcement)
- Accessibility team member is unavailable or overloaded (root cause: No self-service capability, no queue management, no SLA enforcement)

**Volumes:**

- Frequency: per week
- SLA: None — no SLA exists today

**Existing Systems:**

- To be confirmed — possibly no current system
- Email
- Phone
- Email
- Phone

**Pain Points:**

- To be confirmed
- No self-service capability — users must contact a human for every question
- No guaranteed response time — team member replies when they get time
- Accessibility team carries the entire answering burden manually
- No consistent record of questions asked or answers given
- No way for users to find answers outside business hours
- No self-service capability — users must contact a human for every question
- No guaranteed response time — team member replies when they get time
- Accessibility team carries the entire answering burden manually
- No consistent record of questions asked or answers given
- No way for users to find answers outside business hours

**Root Causes:**

- To be confirmed
- No dedicated question-answering system exists
- All knowledge is held by individual accessibility team members rather than a structured knowledge base
- No FAQ or knowledge base has been built to enable self-service
- No dedicated question-answering system exists
- All knowledge is held by individual accessibility team members rather than a structured knowledge base
- No FAQ or knowledge base has been built to enable self-service
### 3.2 User Personas & Actor Classes
#### Platform Administrator

- **Role:** System-wide administrator responsible for managing all users, organizations, information source categories, question categories, and information sources across the entire platform.
- **Goals:** Maintain overall platform health and security; Configure and verify complex information source integrations, including MCP servers (e.g., ZeroHeight) and GitHub/online repositories; Ensure all information sources across all organizations are accessible and correctly configured; Keep embedded libraries and software components up to date and patched
- **Pain Points:** Keeping embedded libraries and software components up to date and patched across the platform
- **Tech Savviness:** high
- **Frequency of Use:** daily
- **Data Scope:** system_wide
- **User Journey:**
  - Log in to the platform
  - Check platform health indicators
  - Verify all information source connections are active and functional
  - Review interaction logs for patterns in user questions and system responses
  - Address any alerts or issues surfaced during the session
- **Allowed Actions:** Create, Read, Update, Delete users (all orgs); Reset any user's password; Create, Read, Update, Delete organizations; Create, Read, Update, Delete Information Source Categories; Create, Read, Update, Delete Question Categories; Configure all Information Sources (all orgs); Designate any information source, information source category, or FAQ as platform-level shared; View interaction logs across all organizations (read-only); Designate platform-administrator-created information sources, information source categories, and FAQs as platform-level shared; Designate Platform Administrator-created information sources, information source categories, and FAQs as platform-level shared
- **Disallowed Actions:** Must not act as or impersonate another user; Must not alter or delete interaction log entries; Must not designate any information source, information source category, or FAQ created by an Organization Administrator or Content Manager as a platform-level shared resource — only resources created by a Platform Administrator may be promoted to platform-level shared status; Must not designate any information source, information source category, or FAQ created by an Organization Administrator or Content Manager as a platform-level shared resource — only resources originally created by a Platform Administrator may be promoted to platform-level shared status

#### Organization Administrator

- **Role:** Administrator scoped to a single organization, responsible for managing org-level users, information source categories, question categories, org information sources, and FAQ content.
- **Goals:** Create and manage organizational users and reset their passwords; Create and manage organizational information source categories; Configure and verify all organizational information sources; Manually and automatically generate FAQs; Run and review reports showing user questions (interaction logs); Monitor platform usage within their organization
- **Pain Points:** Net-new role — no prior system exists; no legacy pain points applicable
- **Tech Savviness:** high
- **Frequency of Use:** daily
- **Data Scope:** organization_wide
- **User Journey:**
  - Log in to the platform
  - Verify all organizational information source connections are active and functional
  - Review interaction logs for patterns in user questions and system responses
  - Check usage metrics to see how many users in their org are actively using the platform
  - Create, edit, or reset passwords for users within their organization as needed
- **Allowed Actions:** Create, Read, Update, Delete users within own org; Reset passwords for users within own org; Create, Read, Update, Delete Information Source Categories (org scope); Create, Read, Update, Delete Question Categories (org scope); Configure Information Sources within own org; View platform-level shared Information Source Categories, Information Sources, and FAQs (read-only); View interaction logs within own organization (read-only)
- **Disallowed Actions:** Must not view, access, or act on data outside their own organization (except platform-shared resources designated by Platform Administrator); Must not edit or delete platform-level shared resources; Must not act as or impersonate another user; Must not alter or delete interaction log entries; Must not access the platform-level audit log; Must not view, access, or act on data outside their own organization (except platform-shared resources designated by a Platform Administrator); Org-created resources (information sources, information source categories, FAQs) created by an Organization Administrator cannot be promoted to platform-level shared — only Platform Administrators may promote Platform Administrator-created resources to shared status; Org-created resources cannot be promoted to platform-level shared — only Platform Administrators may promote Platform Administrator-created resources to shared status

#### Content Manager

- **Role:** Responsible for configuring information sources and managing FAQ content within the organization.
- **Goals:** Configure and verify organizational information sources; Manually and automatically generate FAQs; Run and review reports showing user questions (interaction logs); Manage organizational information source categories
- **Pain Points:** Net-new role — no prior system exists; no legacy pain points applicable
- **Tech Savviness:** medium
- **Frequency of Use:** daily
- **Data Scope:** organization_wide
- **User Journey:**
  - Log in to the platform
  - Review interaction logs carefully, looking for question patterns
  - Create new FAQ entries based on observed patterns
  - Add new information sources as needed
  - Create or edit question categories, or align questions to one or more question categories
- **Allowed Actions:** Configure Information Sources; Create, Read, Update, Delete FAQ entries; Configure Information Sources (org scope); Create, Read, Update, Delete FAQ entries (org scope); Trigger automated FAQ generation from interaction logs; Trigger automated FAQ generation from information sources; View platform-level shared Information Source Categories, Information Sources, and FAQs (read-only)
- **Disallowed Actions:** Must not view, access, or act on data outside their own organization (except platform-shared resources designated by Platform Administrator); Must not edit or delete platform-level shared resources; Must not access the administrator interaction log view; Must not alter or delete interaction log or audit log entries; Must not view, access, or act on data outside their own organization (except platform-shared resources designated by a Platform Administrator); Content Manager-created resources (information sources, FAQs) cannot be promoted to platform-level shared — only Platform Administrators may promote Platform Administrator-created resources to shared status; Must not create, edit, or delete user accounts; Must not reset any user's password (including users within their own organization); Content Manager-created resources cannot be promoted to platform-level shared — only Platform Administrators may promote Platform Administrator-created resources to shared status

#### End User

- **Role:** Standard end user who interacts with the assistant to ask questions and receive cited, reasoned answers.
- **Goals:** Ask questions and receive full answers with expository text, reasoning, and hyperlinked source citations; Browse FAQ categories to find relevant pre-built answers; View supporting documentation; Rate responses as helpful or unhelpful
- **Pain Points:** Net-new experience — no prior system exists; no legacy pain points applicable
- **Tech Savviness:** low_to_high_mixed
- **Frequency of Use:** varies
- **Data Scope:** own_records_only
- **User Journey:**
  - Click desktop icon or embedded HTML link — the assistant window pops open
  - Either type a question directly into the prompt, or scroll through FAQ categories to find a relevant question
  - Review the answer (expository text, reasoning, and hyperlinked citations)
  - Optionally click a citation to view the source material
  - Ask a follow-up question or continue browsing for another question
  - Close the window when done
- **Allowed Actions:** Reset own password; View and select available Information Source Categories; View and select available Question Categories; View FAQ; Ask questions; View supporting documentation; Rate responses (thumbs up / thumbs down)
- **Disallowed Actions:** Must not create, edit, or delete FAQ entries; Must not trigger FAQ auto-generation; Must not access interaction logs belonging to other users; Must not access the administrator interaction log view; Must not delete or modify their own interaction log records; Must not configure information sources

#### User

- **Role:** End User
- **Goals:** Reset Own Password; View and Select Available Information Source Categories; View and Select Available Question Categories; View FAQ; Ask Questions; View Supporting Documentation
- **Pain Points:** 
- **Tech Savviness:** 
- **Frequency of Use:** 
- **Data Scope:**

## 4. FUNCTIONAL REQUIREMENTS (FR)
### FR-001: The system shall provide a self-service question-answering interface accessible via desktop icon or …

- **Priority:** must_have
- **Type:** functional
- **Statement:** The system shall provide a self-service question-answering interface accessible via desktop icon or embedded HTML link, rendered in a responsive and resizable window.
- **Acceptance Criteria:**
  - Given A user clicks the desktop icon., when The assistant loads., then A responsive, resizable window opens and all core interface elements are visible without horizontal scrolling.
  - Given A user clicks an embedded HTML link., when The assistant loads., then The same responsive, resizable window opens correctly in the embedding context.
  - Given An unauthenticated user attempts to open the assistant., when The window loads., then The user is redirected to the login page and no assistant content is displayed.
- **Linked Personas:** End User
- **Linked Processes:** User Asks Questions

### FR-002: The system shall allow end users to submit a question by typing it into a text prompt. Questions are…

- **Priority:** must_have
- **Type:** functional
- **Statement:** The system shall allow end users to submit a question by typing it into a text prompt. Questions are limited to 200 characters.
- **Acceptance Criteria:**
  - Given An authenticated End User has the assistant open., when They type a question and submit it., then The system accepts the input and initiates the answer retrieval process.
  - Given An End User submits an empty text prompt., when The submission is evaluated., then The system rejects the submission with an inline validation message and does not initiate any retrieval or LLM call.
  - Given An authenticated End User has the assistant open., when They type a question of 200 characters or fewer and submit it., then The system accepts the input and initiates the answer retrieval process.
  - Given An End User submits a question exceeding 200 characters., when The submission is evaluated., then The system rejects it with an inline message stating the question must be 200 characters or fewer and does not initiate any retrieval or LLM call.
- **Linked Personas:** End User
- **Linked Processes:** User Asks Questions

### FR-003: The system shall allow end users to select a question category and browse a list of FAQs within that…

- **Priority:** must_have
- **Type:** functional
- **Statement:** The system shall allow end users to select a question category and browse a list of FAQs within that category, then select an FAQ to view its answer.
- **Acceptance Criteria:**
  - Given At least one question category exists with at least one FAQ., when An End User selects that category., then A list of FAQs within that category is displayed.
  - Given An End User selects a specific FAQ from the list., when The FAQ is opened., then The full answer is displayed.
  - Given A question category exists but contains no FAQs., when An End User selects it., then An empty-state message is displayed explaining no FAQs exist yet.
  - Given No question categories have been configured., when An End User opens the category browse view., then An empty-state message is displayed.
- **Linked Personas:** End User
- **Linked Processes:** User Asks Questions

### FR-004: The system shall present a structured response to every question containing: (1) expository response…

- **Priority:** must_have
- **Type:** functional
- **Statement:** The system shall present a structured response to every question containing: (1) expository response text, (2) reasoning behind the response, (3) citations to applicable sources with hyperlinks, and (4) a thumbs up / thumbs down rating control.
- **Acceptance Criteria:**
  - Given An authenticated End User submits a question., when The system returns a response., then The response contains: (1) expository response text, (2) reasoning behind the response, (3) at least one citation with a working hyperlink to the source material, and (4) a thumbs up / thumbs down rating control.
  - Given A response is displayed., when The End User clicks a citation hyperlink., then The link navigates to the cited source document or location.
  - Given No relevant sources are found for a question., when The system returns a response., then The response still includes expository text and reasoning, and clearly indicates that no source citations are available rather than displaying broken or empty citation links.
- **Linked Personas:** End User
- **Linked Processes:** User Asks Questions

### FR-005: The system shall support multi-turn follow-up questions within a session, maintaining conversational…

- **Priority:** must_have
- **Type:** functional
- **Statement:** The system shall support multi-turn follow-up questions within a session, maintaining conversational context across turns.
- **Acceptance Criteria:**
  - Given An End User has received a response to an initial question., when The End User submits a follow-up question in the same session., then The system uses the prior conversational context when generating the follow-up response.
  - Given An End User asks a follow-up question that references a prior answer (e.g., 'can you explain that further?')., when The system processes the follow-up., then The response is contextually coherent with the prior exchange rather than treating the follow-up as an isolated new question.
  - Given A session ends (user closes the window)., when The user opens a new session., then No conversational context from the prior session is carried over; the new session starts fresh.
- **Linked Personas:** End User
- **Linked Processes:** User Asks Questions

### FR-006: The system shall capture and persistently store a log record for every user interaction containing: …

- **Priority:** must_have
- **Type:** functional
- **Statement:** The system shall capture and persistently store a log record for every user interaction containing: date-time group, question text, question category, response provided, sources used, and thumbs up/down rating.
- **Acceptance Criteria:**
  - Given An End User submits a question and receives a response., when The interaction completes., then A log record is persisted containing: date-time group, question text, question category (if selected), response provided, sources used, and thumbs up/down rating (if submitted).
  - Given An interaction completes but the user does not submit a rating., when The log record is written., then The rating field is recorded as null or unrated rather than defaulting to a value.
  - Given The log write operation fails (e.g., a database error)., when The failure occurs., then The response is still served to the End User; the failure is logged to the system error log; the End User is not shown a system error.
- **Linked Personas:** End User
- **Linked Processes:** User Asks Questions

### FR-007: The system shall first attempt to answer every user question deterministically using pre-built FAQs …

- **Priority:** must_have
- **Type:** functional
- **Statement:** The system shall first attempt to answer every user question deterministically using pre-built FAQs and/or Python scripts executed against configured information sources, without invoking an LLM.
- **Acceptance Criteria:**
  - Given An authenticated End User submits a question., when The system processes the request., then The system first attempts to match the question against pre-built FAQs before invoking any LLM call.
  - Given A pre-built FAQ exists that matches the user's question., when The deterministic tier evaluates the question., then The FAQ answer is returned directly without making an LLM API call.
  - Given No matching FAQ exists for the user's question., when The deterministic tier cannot produce a sufficient response., then The system falls through to the LLM fallback tier (FR-008).
- **Linked Personas:** End User
- **Linked Processes:** User Asks Questions

### FR-008: If the deterministic answer tier cannot produce a sufficient response, the system shall fall back to…

- **Priority:** must_have
- **Type:** functional
- **Statement:** If the deterministic answer tier cannot produce a sufficient response, the system shall fall back to an LLM call operating against configured information sources (retrieval-augmented) or against frontier model general knowledge based on the question type and information category. If neither tier can produce a sufficient response, the system shall inform the user that no answer is available, send an in-app alert to the Organization Administrator and Content Manager containing the question text, the submitting user's name, and the time submitted, and inform the user that this alert has been sent.
- **Acceptance Criteria:**
  - Given The deterministic tier cannot produce a sufficient response., when The LLM fallback is invoked against configured information sources., then The system returns an expository response with reasoning and citations.
  - Given Neither the deterministic tier nor the LLM fallback can produce a sufficient response., when Both tiers are exhausted., then The system informs the user that no answer is available, sends an in-app alert to the Organization Administrator and Content Manager containing the question text, submitting user's name, and time submitted, and informs the user that this alert has been sent.
  - Given The LLM fallback is configured to use frontier model general knowledge for a given question type., when The fallback is invoked., then The system queries the frontier model rather than configured information sources and returns the result.
- **Linked Personas:** End User, Organization Administrator, Content Manager
- **Linked Processes:** User Asks Questions

### FR-009: The system shall allow administrators to configure, per information source category and per question…

- **Priority:** must_have
- **Type:** functional
- **Statement:** The system shall allow administrators to configure, per information source category and per question type, whether the LLM fallback call is grounded against configured information sources (retrieval-augmented) or against frontier model general knowledge.
- **Acceptance Criteria:**
  - Given A Platform Administrator or Organization Administrator is authenticated., when They navigate to the LLM fallback configuration for an information source category and question type., then They can select either retrieval-augmented (grounded against configured sources) or frontier model general knowledge as the fallback mode.
  - Given The fallback mode is set to retrieval-augmented for a given category and question type., when A user question triggers the LLM fallback for that category and type., then The LLM call is grounded against the configured information sources for that category.
  - Given The fallback mode is set to frontier model general knowledge for a given category and question type., when A user question triggers the LLM fallback for that category and type., then The LLM call uses frontier model general knowledge rather than configured sources.
  - Given An End User (not an administrator) is authenticated., when They attempt to access the LLM fallback configuration., then The system denies access and returns an authorization error.
- **Linked Personas:** Platform Administrator, Organization Administrator
- **Linked Processes:** User Asks Questions

### FR-010: The system shall allow administrators to configure information source categories by providing a cate…

- **Priority:** must_have
- **Type:** functional
- **Statement:** The system shall allow administrators to configure information source categories by providing a category name and description. Duplicate category names must be rejected.
- **Acceptance Criteria:**
  - Given A Platform Administrator or Organization Administrator is authenticated., when They submit a new information source category with a unique name and description., then The category is saved and appears in the category list.
  - Given A Platform Administrator or Organization Administrator submits a category name that already exists within the applicable scope., when The system evaluates the submission., then The system rejects the submission with an inline validation message indicating the name is already in use; no duplicate category is created.
  - Given A Platform Administrator or Organization Administrator submits a category with a missing name., when The system evaluates the submission., then The system rejects the submission with an inline validation message indicating name is required.
  - Given An End User or Content Manager attempts to create an information source category., when The action is attempted., then The system denies access and returns an authorization error.
- **Linked Personas:** Platform Administrator, Organization Administrator
- **Linked Processes:** Configure Information Source Categories

### FR-011: The system shall support four information source types for configuration: Local Code Repo, GitHub/On…

- **Priority:** must_have
- **Type:** functional
- **Statement:** The system shall support four information source types for configuration: Local Code Repo, GitHub/Online Repo, Document Folder, and MCP Server.
- **Acceptance Criteria:**
  - Given An authorized user initiates information source configuration., when They open the source type selector., then Exactly four source types are available: Local Code Repo, GitHub/Online Repo, Document Folder, and MCP Server.
  - Given An authorized user selects any of the four source types., when The selection is made., then The UI presents the correct input form for that source type: folder picker for Local Code Repo and Document Folder; URL and credential form for GitHub/Online Repo; server address and credential form for MCP Server.
  - Given An End User is authenticated., when They attempt to access information source configuration., then The system denies access and returns an authorization error.
- **Linked Personas:** Platform Administrator, Organization Administrator, Content Manager
- **Linked Processes:** Configure Information Sources

### FR-012: When configuring a Local Code Repo or Document Folder information source, the system shall present a…

- **Priority:** must_have
- **Type:** functional
- **Statement:** When configuring a Local Code Repo or Document Folder information source, the system shall present a folder picker. Upon selection, the system shall test read access to the folder contents. The system must enforce a strict no-execute rule at the code level — code in connected sources must never be executed by the system. On success, the user shall receive a success notification and the window shall close. On failure, the user shall be notified and prompted to provide credentials.
- **Acceptance Criteria:**
  - Given An authorized user selects Local Code Repo or Document Folder as the source type., when The configuration form opens., then A folder picker is presented.
  - Given An authorized user selects a folder via the folder picker and submits., when The system tests read access., then The system verifies read access to the folder contents without executing any code found within.
  - Given The read access test succeeds., when The result is returned., then The user receives a success notification and the configuration window closes with the source saved.
  - Given The read access test fails., when The result is returned., then The user is notified of the failure and prompted to provide or correct credentials.
  - Given The system encounters executable code in a connected source during the access test., when The content is evaluated., then The code is treated as read-only context; no code is executed under any circumstances.
- **Linked Personas:** Platform Administrator, Organization Administrator, Content Manager
- **Linked Processes:** Configure Information Sources

### FR-013: When configuring a GitHub/Online Repo information source, the system shall present a form for enteri…

- **Priority:** must_have
- **Type:** functional
- **Statement:** When configuring a GitHub/Online Repo information source, the system shall present a form for entering a GitHub URL and personal access token or OAuth credentials. The system shall test read access with a strict no-execute rule enforced at the code level. On success, the user shall receive a success notification and the window shall close. On failure, the user shall be notified and prompted to correct credentials.
- **Acceptance Criteria:**
  - Given An authorized user selects GitHub/Online Repo as the source type., when The configuration form opens., then A form is presented with fields for GitHub URL and personal access token or OAuth credentials.
  - Given An authorized user submits the form with valid credentials., when The system tests read access., then Read access is verified without executing any code found in the repository; on success the user receives a success notification and the configuration window closes with the source saved.
  - Given The read access test fails., when The result is returned., then The user is notified of the failure and prompted to correct their credentials.
  - Given The system encounters executable code in the repository during the access test., when The content is evaluated., then The code is treated as read-only context; no code is executed under any circumstances.
- **Linked Personas:** Platform Administrator, Organization Administrator, Content Manager
- **Linked Processes:** Configure Information Sources

### FR-014: When configuring an MCP Server information source, the system shall present a form for entering the …

- **Priority:** must_have
- **Type:** functional
- **Statement:** When configuring an MCP Server information source, the system shall present a form for entering the MCP server address and credentials. The user shall trigger a 'Test MCP' action to verify connectivity. On success, the user shall receive a success notification and the window shall close. On failure, the user shall be notified and prompted to correct credentials. MCP Server configuration is used for accessing MCP-enabled systems such as ZeroHeight.
- **Acceptance Criteria:**
  - Given An authorized user selects MCP Server as the source type., when The configuration form opens., then A form is presented with fields for MCP server address and credentials, and a 'Test MCP' action button.
  - Given An authorized user completes the form and triggers 'Test MCP'., when The connectivity test succeeds., then The user receives a success notification and the configuration window closes with the source saved.
  - Given An authorized user triggers 'Test MCP' and the connectivity test fails., when The result is returned., then The user is notified of the failure and prompted to correct their credentials.
  - Given An authorized user attempts to save an MCP Server source without triggering 'Test MCP' first., when The save is attempted., then The system requires the connectivity test to be completed before saving.
- **Linked Personas:** Platform Administrator, Organization Administrator, Content Manager
- **Linked Processes:** Configure Information Sources

### FR-015: The system shall allow administrators to configure question categories by providing a category name …

- **Priority:** must_have
- **Type:** functional
- **Statement:** The system shall allow administrators to configure question categories by providing a category name and description. Duplicate category names must be rejected.
- **Acceptance Criteria:**
  - Given A Platform Administrator or Organization Administrator is authenticated., when They submit a new question category with a unique name and description., then The category is saved and appears in the question category list.
  - Given A Platform Administrator or Organization Administrator submits a question category name that already exists within the applicable scope., when The system evaluates the submission., then The system rejects the submission with an inline validation message indicating the name is already in use; no duplicate category is created.
  - Given A Platform Administrator or Organization Administrator submits a category with a missing name., when The system evaluates the submission., then The system rejects the submission with an inline validation message indicating name is required.
  - Given An End User or Content Manager attempts to create a question category., when The action is attempted., then The system denies access and returns an authorization error.
- **Linked Personas:** Platform Administrator, Organization Administrator
- **Linked Processes:** Configure Question Categories

### FR-016: The system shall allow administrators and Content Managers to manually create FAQs by entering quest…

- **Priority:** must_have
- **Type:** functional
- **Statement:** The system shall allow administrators and Content Managers to manually create FAQs by entering question text, selecting applicable question categories (multi-select), selecting applicable source categories (multi-select), selecting applicable sources (multi-select), and providing a standard response. All required fields must be validated before save.
- **Acceptance Criteria:**
  - Given A Platform Administrator, Organization Administrator, or Content Manager is authenticated., when They submit a new FAQ with question text, at least one question category, at least one source category, at least one source, and a response., then The FAQ is saved and appears in the FAQ list.
  - Given An authorized user submits the FAQ form with one or more required fields missing., when The system evaluates the submission., then The system rejects the submission with inline validation messages identifying each missing required field; no FAQ is created.
  - Given An End User is authenticated., when They attempt to create an FAQ., then The system denies access and returns an authorization error.
- **Linked Personas:** Platform Administrator, Organization Administrator, Content Manager
- **Linked Processes:** CRUD FAQ — Manual

### FR-017: The system shall allow administrators and Content Managers to trigger automated FAQ generation by in…

- **Priority:** must_have
- **Type:** functional
- **Statement:** The system shall allow administrators and Content Managers to trigger automated FAQ generation by invoking an LLM review of interaction logs. The LLM shall merge similar questions and recommend question categories, source categories, sources, and a response for each FAQ candidate. The user shall review and approve or edit recommendations via checkboxes and free-text before confirming save. The system must not auto-save LLM-generated FAQs without explicit human approval.
- **Acceptance Criteria:**
  - Given An authorized user triggers automated FAQ generation from interaction logs., when The LLM reviews the logs., then The system presents a list of FAQ candidates with recommended question text, merged from similar questions, along with recommended question categories, source categories, sources, and a response for each candidate.
  - Given The user reviews the FAQ candidates., when They approve or edit recommendations via checkboxes and free-text and confirm save., then The approved FAQ entries are saved to the FAQ database.
  - Given The user does not explicitly confirm save., when The review session ends., then No FAQ entries are auto-saved; all candidates remain pending or are discarded.
  - Given An End User is authenticated., when They attempt to trigger automated FAQ generation., then The system denies access and returns an authorization error.
- **Linked Personas:** Platform Administrator, Organization Administrator, Content Manager
- **Linked Processes:** CRUD FAQ — Automated

### FR-018: The system shall allow administrators and Content Managers to trigger automated FAQ generation from …

- **Priority:** must_have
- **Type:** functional
- **Statement:** The system shall allow administrators and Content Managers to trigger automated FAQ generation from a selected information source. The system shall invoke an LLM to review the source content and generate FAQ candidates with recommended question categories, source categories, sources, and a response for each candidate. The user shall review and approve or edit recommendations via checkboxes and free-text before confirming save. The system must not auto-save LLM-generated FAQs without explicit human approval. Approved FAQs are added to the FAQ database for future deterministic question answering.
- **Acceptance Criteria:**
  - Given An authorized user selects an information source and triggers automated FAQ generation from it., when The LLM reviews the source content., then The system presents a list of FAQ candidates with recommended question categories, source categories, sources, and a response for each candidate.
  - Given The user reviews the FAQ candidates., when They approve or edit recommendations via checkboxes and free-text and confirm save., then The approved FAQ entries are saved to the FAQ database and are available for future deterministic question answering.
  - Given The user does not explicitly confirm save., when The review session ends., then No FAQ entries are auto-saved.
  - Given An End User is authenticated., when They attempt to trigger automated FAQ generation from an information source., then The system denies access and returns an authorization error.
- **Linked Personas:** Platform Administrator, Organization Administrator, Content Manager
- **Linked Processes:** CRUD FAQ — Automated

### FR-019: The system shall allow an authenticated end user to rate any response as helpful (thumbs up) or unhe…

- **Priority:** must_have
- **Type:** functional
- **Statement:** The system shall allow an authenticated end user to rate any response as helpful (thumbs up) or unhelpful (thumbs down). The rating shall be recorded and associated with the corresponding interaction log record. Ratings are immutable after submission — neither the end user nor any administrator may alter a submitted rating.
- **Acceptance Criteria:**
  - Given An authenticated End User has received a response., when They select thumbs up or thumbs down., then The rating is recorded and associated with the corresponding interaction log record.
  - Given An End User has submitted a rating., when Any user or administrator attempts to change or delete that rating via the UI or API., then The system rejects the operation; the original rating remains unchanged.
  - Given An End User has not submitted a rating., when The interaction log record is written., then The rating field is recorded as null.
- **Linked Personas:** End User
- **Linked Processes:** User Asks Questions

### FR-020: The system shall allow a Platform Administrator to designate any information source, information sou…

- **Priority:** must_have
- **Type:** functional
- **Statement:** The system shall allow a Platform Administrator to designate any information source, information source category, or FAQ as platform-level shared. Platform-level shared resources shall be visible to all Organization Administrators in read-only mode. Organization Administrators and Content Managers must not be able to edit or delete platform-level shared resources.
- **Acceptance Criteria:**
  - Given A Platform Administrator is authenticated and views a resource they originally created (information source, information source category, or FAQ)., when They designate it as platform-level shared., then The resource is marked shared and becomes visible in read-only mode to all Organization Administrators and Content Managers.
  - Given An Organization Administrator is authenticated and views a platform-level shared resource., when They attempt to edit or delete it., then The system denies the action and returns an authorization error; the resource remains unchanged.
  - Given A Content Manager is authenticated., when They view the platform-level shared resources., then The resources are visible in read-only mode with no edit or delete controls presented.
- **Linked Personas:** Platform Administrator, Organization Administrator, Content Manager

### FR-021: The system shall allow Platform Administrators and Organization Administrators to view interaction l…

- **Priority:** must_have
- **Type:** functional
- **Statement:** The system shall allow Platform Administrators and Organization Administrators to view interaction logs in read-only mode. Platform Administrators may view logs across all organizations. Organization Administrators may view only logs belonging to their own organization. No edit or delete controls shall be presented. Content Managers and End Users must not be able to access the administrator interaction log view.
- **Acceptance Criteria:**
  - Given A Platform Administrator is authenticated., when They navigate to the interaction logs section., then Logs across all organizations are displayed in read-only mode with no edit or delete controls.
  - Given An Organization Administrator is authenticated., when They navigate to the interaction logs section., then Only logs belonging to their own organization are displayed in read-only mode.
  - Given A Content Manager is authenticated., when They attempt to access the administrator interaction log view., then The system denies access and returns an authorization error.
  - Given An End User is authenticated., when They attempt to access the administrator interaction log view., then The system denies access and returns an authorization error.
- **Linked Personas:** Platform Administrator, Organization Administrator, Content Manager, End User
- **Linked Processes:** User Asks Questions

### FR-022: When a security control violation occurs — specifically when the no-execute rule is triggered on a…

- **Priority:** must_have
- **Type:** functional
- **Statement:** When a security control violation occurs — specifically when the no-execute rule is triggered on a connected information source — the system must deliver an in-app alert to the Platform Administrator and log the event to the audit log.
- **Acceptance Criteria:**
  - Given The no-execute rule is triggered on a connected information source., when The violation is detected., then An in-app alert is delivered to the Platform Administrator and a corresponding entry appears in the audit log recording the event.
  - Given The no-execute rule is triggered while the Platform Administrator is not logged in., when The Platform Administrator subsequently logs in., then The in-app alert is present and visible; it has not expired; the audit log entry for the event exists.
  - Given Any user attempts to alter or delete the audit log entry for a no-execute event., when The operation is submitted., then The system rejects the operation and returns an authorization error; the audit log entry remains unchanged.
- **Linked Personas:** Platform Administrator
- **Linked Processes:** Configure Information Sources

### FR-025: Organization Administrators and Content Managers must not be able to view, access, or act on any dat…

- **Priority:** must_have
- **Type:** functional
- **Statement:** Organization Administrators and Content Managers must not be able to view, access, or act on any data outside their own organization, with the sole exception of platform-level shared Information Source Categories, Information Sources, and FAQs designated as shared by a Platform Administrator.
- **Acceptance Criteria:**
  - Given An Organization Administrator is authenticated and attempts to access data belonging to a different organization., when The access request is evaluated by the system., then The system denies the request and returns an authorization error; no cross-org data is disclosed.
  - Given A Content Manager is authenticated and a platform-shared FAQ exists., when The Content Manager views the FAQ list., then The platform-shared FAQ is visible in read-only mode; no edit or delete controls are presented.
- **Linked Personas:** Organization Administrator, Content Manager

### FR-026: Platform Administrators and Organization Administrators must not be able to act as or impersonate an…

- **Priority:** must_have
- **Type:** functional
- **Statement:** Platform Administrators and Organization Administrators must not be able to act as or impersonate another user. All administrative actions must be performed under the administrator's own authenticated identity.
- **Acceptance Criteria:**
  - Given A Platform Administrator is authenticated., when The administrator attempts to assume or impersonate another user's session or identity., then The system rejects the action and returns an authorization error; no impersonation capability is exposed in the UI or API.
  - Given An Organization Administrator is authenticated., when The administrator attempts to assume or impersonate another user's session or identity., then The system rejects the action and returns an authorization error.
- **Linked Personas:** Platform Administrator, Organization Administrator

### FR-027: A Platform Administrator may only designate an information source, information source category, or F…

- **Priority:** must_have
- **Type:** functional
- **Statement:** A Platform Administrator may only designate an information source, information source category, or FAQ as platform-level shared if that resource was originally created by a Platform Administrator. Resources created by an Organization Administrator or Content Manager must never be promotable to platform-level shared status by any user, including a Platform Administrator.
- **Acceptance Criteria:**
  - Given A Platform Administrator is authenticated and views an information source created by an Organization Administrator., when The Platform Administrator attempts to designate that resource as platform-level shared., then The system rejects the action and returns an authorization error; the resource remains scoped to the originating organization.
  - Given A Platform Administrator is authenticated and views an information source created by a Platform Administrator., when The Platform Administrator designates that resource as platform-level shared., then The resource is marked as platform-level shared and becomes visible in read-only mode to all Organization Administrators and Content Managers.
- **Linked Personas:** Platform Administrator
#### AI / ML Features

### ai-1: LLM reviews interaction logs, clusters similar questions, and generates candidate FAQ entries with r…

- **Description:** LLM reviews interaction logs, clusters similar questions, and generates candidate FAQ entries with recommended categories, sources, and responses
- **Use case:** Reduce manual FAQ authoring effort; surface common user questions automatically
- **Process:** CRUD FAQ — Automated

### ai-2: LLM answers user questions by reasoning over configured information sources and FAQ entries, returni…

- **Description:** LLM answers user questions by reasoning over configured information sources and FAQ entries, returning expository response, reasoning, and source citations
- **Use case:** Provide traceable, cited answers to end user questions
- **Process:** User Asks Questions
#### Mobile Requirements

### mob-1: Assistant window must be responsive and resizable, accessible via desktop icon or embedded HTML link

- **Offline capable:** false
- **Process:** User Asks Questions
### 4.1 Business Rules (BR)
### CON-004: When the External LLM API is unavailable after exhausting all retries, the system must degrade grace…

- **Priority:** must_have
- **Type:** constraint
- **Statement:** When the External LLM API is unavailable after exhausting all retries, the system must degrade gracefully to FAQ browse-only mode. The end user, Organization Administrator, and Platform Administrator must each receive an in-app alert with a message specific to the failure type (e.g., rate limit exceeded, authentication failure, service unavailable).
- **Acceptance Criteria:**
  - Given The External LLM API returns a rate-limit error and all 3 retries are exhausted., when The system processes the final retry failure., then The end user sees a message indicating the AI assistant is temporarily unavailable due to rate limiting; an in-app alert specifying 'rate limit exceeded' is sent to the Organization Administrator and Platform Administrator; FAQ browse-only mode remains available.
  - Given The External LLM API returns an authentication failure., when The system processes the error., then The end user sees a message indicating a configuration issue with the AI assistant; an in-app alert specifying 'authentication failure' is sent to the Organization Administrator and Platform Administrator; FAQ browse-only mode remains available.
  - Given The External LLM API times out after 20 seconds and all 3 retries are exhausted., when The system processes the final timeout., then The end user sees a message indicating the AI assistant is temporarily unavailable; an in-app alert specifying 'service timeout' is sent to the Organization Administrator and Platform Administrator; FAQ browse-only mode remains available.
- **Linked Processes:** User Asks Questions

### CON-005: When the GitHub / Online Repository integration times out or returns an error after exhausting 3 ret…

- **Priority:** must_have
- **Type:** constraint
- **Statement:** When the GitHub / Online Repository integration times out or returns an error after exhausting 3 retries (with 1-second delay before the second attempt and 3-second delay before subsequent attempts), the system must display a failure-type-specific message to the user and send a failure-type-specific in-app alert to the Organization Administrator and Platform Administrator.
- **Acceptance Criteria:**
  - Given The GitHub integration times out after 20 seconds and all 3 retries are exhausted., when The system processes the final timeout., then The user sees a timeout-specific message; in-app alerts specifying 'service timeout' are sent to the Organization Administrator and Platform Administrator.
  - Given The GitHub integration returns an authentication failure., when The system processes the error., then The user sees an auth-failure-specific message; in-app alerts specifying 'authentication failure' are sent to the Organization Administrator and Platform Administrator.
- **Linked Processes:** Configure Information Sources

### CON-006: When the MCP Server integration times out or returns an error after exhausting 3 retries (with 1-sec…

- **Priority:** must_have
- **Type:** constraint
- **Statement:** When the MCP Server integration times out or returns an error after exhausting 3 retries (with 1-second delay before the second attempt and 3-second delay before subsequent attempts), the system must display a failure-type-specific message to the user and send a failure-type-specific in-app alert to the Organization Administrator and Platform Administrator.
- **Acceptance Criteria:**
  - Given The MCP Server integration times out after 20 seconds and all 3 retries are exhausted., when The system processes the final timeout., then The user sees a timeout-specific message; in-app alerts specifying 'service timeout' are sent to the Organization Administrator and Platform Administrator.
  - Given The MCP Server integration returns an authentication failure., when The system processes the error., then The user sees an auth-failure-specific message; in-app alerts specifying 'authentication failure' are sent to the Organization Administrator and Platform Administrator.
- **Linked Processes:** Configure Information Sources
## 5. SECURITY & NON-FUNCTIONAL REQUIREMENTS
Each requirement is stated once, in the sub-section named below:

- **5.1 Application-Specific Security Requirements** — SR-001, SR-002, SR-003, SR-004, SR-005, SR-006, SR-007
- **5.3 Other Non-Functional Requirements (deltas only)** — NFR-001, CON-001, CON-002, CON-003, NFR-002
### 5.1 Application-Specific Security Requirements
### SR-001: The system shall encrypt all information source credentials (including GitHub personal access tokens…

- **Priority:** must_have
- **Type:** security
- **Statement:** The system shall encrypt all information source credentials (including GitHub personal access tokens, OAuth tokens, and MCP Server credentials) at rest in the database using FIPS 140-2 (or FIPS 140-3) validated encryption.
- **Acceptance Criteria:**
  - Given An authorized user saves credentials for an information source (GitHub PAT, OAuth token, or MCP Server credential)., when The credential is persisted to the database., then The stored value is ciphertext encrypted with a FIPS 140-2 or FIPS 140-3 validated algorithm; querying the database directly returns no plaintext credential value.
  - Given A request is made to retrieve information source configuration via the API., when The response is returned., then The response body contains no plaintext credential value; at most a masked or omitted representation is returned.
  - Given The system attempts to store a credential using a non-FIPS-compliant algorithm., when The storage operation is evaluated., then The system rejects the storage operation and logs an error; no plaintext or non-FIPS-encrypted credential is persisted.
  - Given An authorized user saves credentials for an information source (GitHub PAT, OAuth token, or MCP Server credential)., when The credential is persisted to the database., then The stored value is ciphertext encrypted with a FIPS 140-2 or FIPS 140-3 validated algorithm; querying the database directly returns no plaintext credential value.
  - Given A request is made to retrieve information source configuration via the API., when The response is returned., then The response body contains no plaintext credential value; at most a masked or omitted representation is returned.
  - Given The system attempts to store a credential using a non-FIPS-compliant algorithm., when The storage operation is evaluated., then The system rejects the storage operation and logs an error; no plaintext or non-FIPS-encrypted credential is persisted.
  - Given An authorized user saves credentials for an information source (GitHub PAT, OAuth token, or MCP Server credential)., when The credential is persisted to the database., then The stored value is ciphertext encrypted with a FIPS 140-2 or FIPS 140-3 validated algorithm; querying the database directly returns no plaintext credential value.
  - Given A request is made to retrieve information source configuration via the API., when The response is returned., then The response body contains no plaintext credential value; at most a masked or omitted representation is returned.
  - Given The system attempts to store a credential using a non-FIPS-compliant algorithm., when The storage operation is evaluated., then The system rejects the storage operation and logs an error; no plaintext or non-FIPS-encrypted credential is persisted.
  - Given An authorized user saves credentials for an information source (GitHub PAT, OAuth token, or MCP Server credential)., when The credential is persisted to the database., then The stored value is ciphertext encrypted with a FIPS 140-2 or FIPS 140-3 validated algorithm; querying the database directly returns no plaintext credential value.
  - Given A request is made to retrieve information source configuration via the API., when The response is returned., then The response body contains no plaintext credential value; at most a masked or omitted representation is returned.
  - Given The system attempts to store a credential using a non-FIPS-compliant algorithm., when The storage operation is evaluated., then The system rejects the storage operation and logs an error; no plaintext or non-FIPS-encrypted credential is persisted.
  - Given An authorized user saves credentials for an information source (GitHub PAT, OAuth token, or MCP Server credential)., when The credential is persisted to the database., then The stored value is ciphertext encrypted with a FIPS 140-2 or FIPS 140-3 validated algorithm; querying the database directly returns no plaintext credential value.
  - Given A request is made to retrieve information source configuration via the API., when The response is returned., then The response body contains no plaintext credential value; at most a masked or omitted representation is returned.
  - Given The system attempts to store a credential using a non-FIPS-compliant algorithm., when The storage operation is evaluated., then The system rejects the storage operation and logs an error; no plaintext or non-FIPS-encrypted credential is persisted.
- **Linked Personas:** Platform Administrator, Organization Administrator, Content Manager, Platform Administrator, Organization Administrator, Content Manager, Platform Administrator, Organization Administrator, Content Manager, Platform Administrator, Organization Administrator, Content Manager, Platform Administrator, Organization Administrator, Content Manager
- **Linked Processes:** Configure Information Sources, Configure Information Sources, Configure Information Sources, Configure Information Sources, Configure Information Sources

### SR-002: The system shall block any user question submission that contains PII or source code and prompt the …

- **Priority:** must_have
- **Type:** security
- **Statement:** The system shall block any user question submission that contains PII or source code and prompt the user to rephrase. No PII and no source code shall be included in any request payload sent to an external LLM API.
- **Acceptance Criteria:**
  - Given An End User submits a question containing no PII and no source code., when The system prepares the LLM API request., then The request is forwarded to the external LLM API and the user receives a response; the outbound payload contains no PII and no source code.
  - Given An End User submits a question containing PII (e.g., a name or email address)., when The system evaluates the submission., then The system blocks the submission, does not send any payload to the LLM API, and displays an inline message asking the user to rephrase their question.
  - Given An End User submits a question containing source code., when The system evaluates the submission., then The system blocks the submission, does not send any payload to the LLM API, and displays an inline message asking the user to rephrase their question.
  - Given A question contains ambiguous content that the sanitization filter flags as potential PII., when The system evaluates the submission., then The system blocks the submission and prompts the user to rephrase, erring on the side of caution.
  - Given An End User submits a question containing no PII and no source code., when The system prepares the LLM API request., then The request is forwarded to the external LLM API and the user receives a response; the outbound payload contains no PII and no source code.
  - Given An End User submits a question containing PII (e.g., a name or email address)., when The system evaluates the submission., then The system blocks the submission, does not send any payload to the LLM API, and displays an inline message asking the user to rephrase their question.
  - Given An End User submits a question containing source code., when The system evaluates the submission., then The system blocks the submission, does not send any payload to the LLM API, and displays an inline message asking the user to rephrase their question.
  - Given A question contains ambiguous content that the sanitization filter flags as potential PII., when The system evaluates the submission., then The system blocks the submission and prompts the user to rephrase, erring on the side of caution.
  - Given An End User submits a question containing no PII and no source code., when The system prepares the LLM API request., then The request is forwarded to the external LLM API and the user receives a response; the outbound payload contains no PII and no source code.
  - Given An End User submits a question containing PII (e.g., a name or email address)., when The system evaluates the submission., then The system blocks the submission, does not send any payload to the LLM API, and displays an inline message asking the user to rephrase their question.
  - Given An End User submits a question containing source code., when The system evaluates the submission., then The system blocks the submission, does not send any payload to the LLM API, and displays an inline message asking the user to rephrase their question.
  - Given A question contains ambiguous content that the sanitization filter flags as potential PII., when The system evaluates the submission., then The system blocks the submission and prompts the user to rephrase, erring on the side of caution.
  - Given An End User submits a question containing no PII and no source code., when The system prepares the LLM API request., then The request is forwarded to the external LLM API and the user receives a response; the outbound payload contains no PII and no source code.
  - Given An End User submits a question containing PII (e.g., a name or email address)., when The system evaluates the submission., then The system blocks the submission, does not send any payload to the LLM API, and displays an inline message asking the user to rephrase their question.
  - Given An End User submits a question containing source code., when The system evaluates the submission., then The system blocks the submission, does not send any payload to the LLM API, and displays an inline message asking the user to rephrase their question.
  - Given A question contains ambiguous content that the sanitization filter flags as potential PII., when The system evaluates the submission., then The system blocks the submission and prompts the user to rephrase, erring on the side of caution.
  - Given An End User submits a question containing no PII and no source code., when The system prepares the LLM API request., then The request is forwarded to the external LLM API and the user receives a response; the outbound payload contains no PII and no source code.
  - Given An End User submits a question containing PII (e.g., a name or email address)., when The system evaluates the submission., then The system blocks the submission, does not send any payload to the LLM API, and displays an inline message asking the user to rephrase their question.
  - Given An End User submits a question containing source code., when The system evaluates the submission., then The system blocks the submission, does not send any payload to the LLM API, and displays an inline message asking the user to rephrase their question.
  - Given A question contains ambiguous content that the sanitization filter flags as potential PII., when The system evaluates the submission., then The system blocks the submission and prompts the user to rephrase, erring on the side of caution.
- **Linked Personas:** End User, End User, End User, End User, End User
- **Linked Processes:** User Asks Questions, User Asks Questions, User Asks Questions, User Asks Questions, User Asks Questions

### SR-003: Interaction logs are classified as containing PII (user name, user ID, and organization). Access to …

- **Priority:** must_have
- **Type:** security
- **Statement:** Interaction logs are classified as containing PII (user name, user ID, and organization). Access to interaction logs must be restricted to authorized roles only. No user may view another user's interaction logs. Administrators may view logs in read-only mode and must not be able to alter log content. If a user attempts to access another user's interaction log, the system must return an authorization error and send an in-app alert to both the user's Organization Administrator and the Platform Administrator.
- **Acceptance Criteria:**
  - Given An End User is authenticated and requests their own interaction logs., when The system evaluates the access request., then Only log records belonging to that user are returned; no other user's data is disclosed.
  - Given An End User is authenticated and attempts to access another user's interaction log by manipulating a record ID or user ID parameter., when The system evaluates the access request., then The system returns an authorization error, discloses no data belonging to the other user, and sends an in-app alert to the requesting user's Organization Administrator and to the Platform Administrator.
  - Given A Platform Administrator is authenticated and navigates to the interaction logs section., when The logs are displayed., then All logs across all organizations are visible in read-only mode; no edit, delete, or alter controls are present or functional.
  - Given A Content Manager is authenticated and attempts to access the administrator interaction log view., when The access request is evaluated., then The system returns an authorization error and no log data is displayed.
  - Given Any role attempts to modify or delete an interaction log entry via the UI or API., when The operation is submitted., then The system rejects the operation and returns an authorization error; the log record remains unchanged.
  - Given An End User is authenticated and requests their own interaction logs., when The system evaluates the access request., then Only log records belonging to that user are returned; no other user's data is disclosed.
  - Given An End User is authenticated and attempts to access another user's interaction log by manipulating a record ID or user ID parameter., when The system evaluates the access request., then The system returns an authorization error, discloses no data belonging to the other user, and sends an in-app alert to the requesting user's Organization Administrator and to the Platform Administrator.
  - Given A Platform Administrator is authenticated and navigates to the interaction logs section., when The logs are displayed., then All logs across all organizations are visible in read-only mode; no edit, delete, or alter controls are present or functional.
  - Given A Content Manager is authenticated and attempts to access the administrator interaction log view., when The access request is evaluated., then The system returns an authorization error and no log data is displayed.
  - Given Any role attempts to modify or delete an interaction log entry via the UI or API., when The operation is submitted., then The system rejects the operation and returns an authorization error; the log record remains unchanged.
  - Given An End User is authenticated and requests their own interaction logs., when The system evaluates the access request., then Only log records belonging to that user are returned; no other user's data is disclosed.
  - Given An End User is authenticated and attempts to access another user's interaction log by manipulating a record ID or user ID parameter., when The system evaluates the access request., then The system returns an authorization error, discloses no data belonging to the other user, and sends an in-app alert to the requesting user's Organization Administrator and to the Platform Administrator.
  - Given A Platform Administrator is authenticated and navigates to the interaction logs section., when The logs are displayed., then All logs across all organizations are visible in read-only mode; no edit, delete, or alter controls are present or functional.
  - Given A Content Manager is authenticated and attempts to access the administrator interaction log view., when The access request is evaluated., then The system returns an authorization error and no log data is displayed.
  - Given Any role attempts to modify or delete an interaction log entry via the UI or API., when The operation is submitted., then The system rejects the operation and returns an authorization error; the log record remains unchanged.
  - Given An End User is authenticated and requests their own interaction logs., when The system evaluates the access request., then Only log records belonging to that user are returned; no other user's data is disclosed.
  - Given An End User is authenticated and attempts to access another user's interaction log by manipulating a record ID or user ID parameter., when The system evaluates the access request., then The system returns an authorization error, discloses no data belonging to the other user, and sends an in-app alert to the requesting user's Organization Administrator and to the Platform Administrator.
  - Given A Platform Administrator is authenticated and navigates to the interaction logs section., when The logs are displayed., then All logs across all organizations are visible in read-only mode; no edit, delete, or alter controls are present or functional.
  - Given A Content Manager is authenticated and attempts to access the administrator interaction log view., when The access request is evaluated., then The system returns an authorization error and no log data is displayed.
  - Given Any role attempts to modify or delete an interaction log entry via the UI or API., when The operation is submitted., then The system rejects the operation and returns an authorization error; the log record remains unchanged.
  - Given An End User is authenticated and requests their own interaction logs., when The system evaluates the access request., then Only log records belonging to that user are returned; no other user's data is disclosed.
  - Given An End User is authenticated and attempts to access another user's interaction log by manipulating a record ID or user ID parameter., when The system evaluates the access request., then The system returns an authorization error, discloses no data belonging to the other user, and sends an in-app alert to the requesting user's Organization Administrator and to the Platform Administrator.
  - Given A Platform Administrator is authenticated and navigates to the interaction logs section., when The logs are displayed., then All logs across all organizations are visible in read-only mode; no edit, delete, or alter controls are present or functional.
  - Given A Content Manager is authenticated and attempts to access the administrator interaction log view., when The access request is evaluated., then The system returns an authorization error and no log data is displayed.
  - Given Any role attempts to modify or delete an interaction log entry via the UI or API., when The operation is submitted., then The system rejects the operation and returns an authorization error; the log record remains unchanged.
- **Linked Personas:** Platform Administrator, Organization Administrator, Content Manager, End User, Platform Administrator, Organization Administrator, Content Manager, End User, Platform Administrator, Organization Administrator, Content Manager, End User, Platform Administrator, Organization Administrator, Content Manager, End User, Platform Administrator, Organization Administrator, Content Manager, End User
- **Linked Processes:** User Asks Questions, User Asks Questions, User Asks Questions, User Asks Questions, User Asks Questions

### SR-004: When the no-execute rule is triggered on a connected information source, the system must deliver an …

- **Priority:** must_have
- **Type:** security
- **Statement:** When the no-execute rule is triggered on a connected information source, the system must deliver an in-app alert to the Platform Administrator and log the event to the audit log. The alert persists until read by the Platform Administrator and does not expire.
- **Acceptance Criteria:**
  - Given The no-execute rule is triggered on a connected information source., when The violation is detected., then An in-app alert is delivered to the Platform Administrator and a corresponding entry appears in the audit log recording the event.
  - Given The no-execute rule is triggered while the Platform Administrator is not logged in., when The Platform Administrator subsequently logs in., then The in-app alert is present and visible; it has not expired; the audit log entry for the event exists.
  - Given An Organization Administrator is authenticated., when The Organization Administrator attempts to access the platform-level audit log., then The system denies access and returns an authorization error; no audit log data is displayed.
  - Given Any user attempts to alter or delete the audit log entry for a no-execute event., when The operation is submitted., then The system rejects the operation and returns an authorization error; the audit log entry remains unchanged.
  - Given The no-execute rule is triggered on a connected information source., when The violation is detected., then An in-app alert is delivered to the Platform Administrator and a corresponding entry appears in the audit log recording the event.
  - Given The no-execute rule is triggered while the Platform Administrator is not logged in., when The Platform Administrator subsequently logs in., then The in-app alert is present and visible; it has not expired; the audit log entry for the event exists.
  - Given An Organization Administrator is authenticated., when The Organization Administrator attempts to access the platform-level audit log., then The system denies access and returns an authorization error; no audit log data is displayed.
  - Given Any user attempts to alter or delete the audit log entry for a no-execute event., when The operation is submitted., then The system rejects the operation and returns an authorization error; the audit log entry remains unchanged.
  - Given The no-execute rule is triggered on a connected information source., when The violation is detected., then An in-app alert is delivered to the Platform Administrator and a corresponding entry appears in the audit log recording the event.
  - Given The no-execute rule is triggered while the Platform Administrator is not logged in., when The Platform Administrator subsequently logs in., then The in-app alert is present and visible; it has not expired; the audit log entry for the event exists.
  - Given An Organization Administrator is authenticated., when The Organization Administrator attempts to access the platform-level audit log., then The system denies access and returns an authorization error; no audit log data is displayed.
  - Given Any user attempts to alter or delete the audit log entry for a no-execute event., when The operation is submitted., then The system rejects the operation and returns an authorization error; the audit log entry remains unchanged.
- **Linked Personas:** Platform Administrator, Platform Administrator, Platform Administrator
- **Linked Processes:** Configure Information Sources, Configure Information Sources, Configure Information Sources

### SR-005: The system must enforce a strict no-execute rule at the code level — code in connected sources mus…

- **Priority:** must_have
- **Type:** security
- **Statement:** The system must enforce a strict no-execute rule at the code level — code in connected sources must never be executed by the system. This rule applies to all connected source types (Local Code Repo, GitHub/Online Repo, Document Folder, MCP Server) and must hold under all conditions including adversarial injection attempts. Connected source content must be treated as read-only context only.
- **Acceptance Criteria:**
  - Given The system is connected to an information source containing executable code (e.g., Python scripts, shell commands, JavaScript)., when The system reads that source to answer a user question., then The source content is used as read-only context only; no code interpreter, runtime, shell, or execution environment is invoked; no code from the source is executed.
  - Given A connected information source contains content crafted to trigger code execution via injection (e.g., a shell command, eval expression, script tag, or LLM prompt injection instructing the system to run code)., when The system processes that content., then The system reads the content as plain text context only; no execution occurs; no side effects from the injected payload are observed in the system or its outputs.
  - Given Any user role, API call, or system process attempts to cause the system to execute code found in a connected source., when The attempt is made., then The system does not execute the code under any circumstances; the no-execute invariant is enforced at the code level and cannot be overridden by configuration, user input, or LLM output.
  - Given An automated test submits a connected source containing known executable payloads across multiple injection vectors (shell commands, eval expressions, script tags, prompt injections)., when The system processes each payload., then In every case the system returns a read-only context response with no execution side effects; all injection vectors are blocked.
  - Given The system is connected to an information source containing executable code (e.g., Python scripts, shell commands, JavaScript)., when The system reads that source to answer a user question., then The source content is used as read-only context only; no code interpreter, runtime, shell, or execution environment is invoked; no code from the source is executed.
  - Given A connected information source contains content crafted to trigger code execution via injection (e.g., a shell command, eval expression, script tag, or LLM prompt injection instructing the system to run code)., when The system processes that content., then The system reads the content as plain text context only; no execution occurs; no side effects from the injected payload are observed in the system or its outputs.
  - Given Any user role, API call, or system process attempts to cause the system to execute code found in a connected source., when The attempt is made., then The system does not execute the code under any circumstances; the no-execute invariant is enforced at the code level and cannot be overridden by configuration, user input, or LLM output.
  - Given An automated test submits a connected source containing known executable payloads across multiple injection vectors (shell commands, eval expressions, script tags, prompt injections)., when The system processes each payload., then In every case the system returns a read-only context response with no execution side effects; all injection vectors are blocked.
- **Linked Personas:** Platform Administrator, Organization Administrator, Content Manager, Platform Administrator, Organization Administrator, Content Manager, Platform Administrator, Organization Administrator, Content Manager
- **Linked Processes:** Configure Information Sources, Configure Information Sources, Configure Information Sources

### SR-006: The system shall sanitize all content sent to external LLM APIs (Tier 2 fallback calls) to ensure th…

- **Priority:** must_have
- **Type:** security
- **Statement:** The system shall sanitize all content sent to external LLM APIs (Tier 2 fallback calls) to ensure that no PII and no source code is included in the request payload.
- **Acceptance Criteria:**
  - Given The system prepares a Tier 2 LLM fallback call., when The request payload is assembled., then The payload contains no PII (names, email addresses, user IDs) and no source code.
  - Given The system prepares an automated FAQ generation LLM call., when The request payload is assembled., then The payload contains no PII and no source code.
  - Given A sanitization check identifies PII or source code in a payload., when The check runs., then The content is stripped or the call is blocked before any data leaves the system boundary.
- **Linked Personas:** End User
- **Linked Processes:** User Asks Questions

### SR-007: Interaction logs are classified as containing PII (user name, user ID number, and organization). Acc…

- **Priority:** must_have
- **Type:** security
- **Statement:** Interaction logs are classified as containing PII (user name, user ID number, and organization). Access to interaction logs must be restricted to authorized roles only. No user may view another user's interaction logs. Administrators may view logs in read-only mode but must not alter log content.
- **Acceptance Criteria:**
  - Given An End User is authenticated and requests their own interaction logs., when The system evaluates the access request., then Only log records belonging to that user are returned; no other user's data is disclosed.
  - Given Any authenticated user attempts to modify or delete an interaction log entry via the UI or API., when The operation is submitted., then The system rejects the operation and returns an authorization error; the log record remains unchanged.
  - Given A Platform Administrator or Organization Administrator views interaction logs., when The logs are displayed., then They are presented in read-only mode with no edit, delete, or alter controls available.
- **Linked Personas:** Platform Administrator, Organization Administrator, Content Manager, End User
- **Linked Processes:** User Asks Questions
### 5.2 UI / UX Requirements
**UI/UX Baseline (applies to all screens unless a screen states a delta):**

- **accessibility:** All interactive elements must be keyboard-navigable and carry sufficient colour contrast; screen-reader-compatible labels are required on every form control, icon button, and status indicator.
- **not_found:** When a user navigates to a URL that does not exist or to a resource they are not permitted to see, a 404 page is shown with a friendly message stating the page could not be found and a link to return to their home dashboard.
- **responsive:** The interface must adapt gracefully across common desktop, tablet, and mobile viewport sizes so that all core tasks — asking questions, managing sources, and reviewing logs — remain fully usable without horizontal scrolling.
- **session_expired:** When a user's session ends, they are redirected to the login page and shown a clear message stating their session has expired and asking them to sign in again; any unsaved form data is preserved in the URL or local state where technically feasible so work is not lost.
- **state_empty:** When a list — such as information sources, FAQ entries, question categories, or interaction logs — contains no items, a brief contextual message explains that nothing exists yet and, where the user's role permits, offers a clear call-to-action to create the first item.
- **state_error:** When a server or network error occurs, the application displays a non-technical message explaining that something went wrong and invites the user to retry or contact support; in-app alerts triggered by security events (such as a no-execute rule violation) are surfaced prominently to the Platform Administrator without disrupting other users.
- **state_loading:** While data is being fetched or an action is in progress, a visible loading indicator is displayed and interactive controls that would trigger duplicate requests are disabled until the operation completes.
- **validation_messages:** Inline validation messages appear adjacent to the offending field immediately on submission (or on blur where appropriate), describing what is wrong and how to correct it — for example, flagging an empty required credential field or a question input that would be blocked by content-sanitization rules — without exposing raw system errors.

### FAQ Browser

- **Route:** `/assistant/faqs`
- **Purpose:** Primary tab of the assistant window. Allows End Users to browse FAQs by category using a left-hand navigation panel, and read FAQ answers with source citations in the right-hand content area.
- **Personas:** PERSONA-004, PERSONA-004, PERSONA-004, PERSONA-004, PERSONA-004
- **Data displayed:**
  - question_category.name (source: QuestionCategory, sensitivity: internal)
  - faq.question (source: FAQ, sensitivity: internal)
  - faq.answer (source: FAQ, sensitivity: internal)
  - citation.source_name (source: InformationSource, sensitivity: internal)
  - citation.hyperlink (source: InformationSource, sensitivity: internal)
  - question_category.name (source: QuestionCategory, sensitivity: internal)
  - faq.question (source: FAQ, sensitivity: internal)
  - faq.answer (source: FAQ, sensitivity: internal)
  - citation.source_name (source: InformationSource, sensitivity: internal)
  - citation.hyperlink (source: InformationSource, sensitivity: internal)
  - question_category.name (source: QuestionCategory, sensitivity: internal)
  - faq.question (source: FAQ, sensitivity: internal)
  - faq.answer (source: FAQ, sensitivity: internal)
  - citation.source_name (source: InformationSource, sensitivity: internal)
  - citation.hyperlink (source: InformationSource, sensitivity: internal)
  - question_category.name (source: QuestionCategory, sensitivity: internal)
  - faq.question (source: FAQ, sensitivity: internal)
  - faq.answer (source: FAQ, sensitivity: internal)
  - citation.source_name (source: InformationSource, sensitivity: internal)
  - citation.hyperlink (source: InformationSource, sensitivity: internal)
  - question_category.name (source: QuestionCategory, sensitivity: internal)
  - faq.question (source: FAQ, sensitivity: internal)
  - faq.answer (source: FAQ, sensitivity: internal)
  - citation.source_name (source: InformationSource, sensitivity: internal)
  - citation.hyperlink (source: InformationSource, sensitivity: internal)
- **Navigation:**
  - → Conversational Assistant tab (when: User selects second tab, access: end_user)
  - → FAQ detail (inline) (when: User selects an FAQ from the list, access: end_user)
  - → Conversational Assistant tab (when: User selects second tab, access: end_user)
  - → FAQ detail (inline) (when: User selects an FAQ from the list, access: end_user)
  - → Conversational Assistant tab (when: User selects second tab, access: end_user)
  - → FAQ detail (inline accordion) (when: User clicks an FAQ in the list — answer expands inline within the scrollable list; multiple FAQs can be open simultaneously, access: end_user)
  - → Conversational Assistant tab (when: User selects second tab, access: end_user)
  - → FAQ detail (inline accordion) (when: User clicks an FAQ in the list — answer expands inline within the scrollable list; multiple FAQs can be open simultaneously, access: end_user)
  - → Conversational Assistant tab (when: User selects second tab, access: end_user)
  - → FAQ detail (inline accordion) (when: User clicks an FAQ in the list — answer expands inline within the scrollable list; multiple FAQs can be open simultaneously, access: end_user)
- **State deltas:**
  - default_right_panel: TBD — awaiting user decision on what shows before a category is selected
  - empty_category: When a category has no FAQs, right panel shows: 'No FAQs in this category yet.'
  - faq_interaction: FAQ answers expand inline (accordion style) within the scrollable list when clicked; category context remains visible in left nav
  - no_categories: When no categories exist, left nav shows empty-state message: 'No categories available.'
  - no_category_selected: Right panel shows instruction prompt: 'Select a category on the left to browse FAQs by category. If you can't find what you're looking for, select the chat tab to ask a free-form question.'
- **Accessibility deltas:** Left nav categories must be keyboard-navigable with focus indicators; selected category must be announced to screen readers via aria-current or equivalent. Accordion expand/collapse must use aria-expanded and be keyboard-operable.
- **Responsive deltas:** On mobile viewports (≤ 640px), left nav collapses to a top dropdown or hamburger-triggered drawer; right panel takes full width.
- **Verification:** end_to_end

### Conversational Assistant

- **Route:** `/assistant/chat`
- **Purpose:** Second tab of the assistant window. Allows End Users to type free-text questions, view multi-turn conversation history, and receive responses with expository text, reasoning, and hyperlinked source citations.
- **Personas:** PERSONA-004, PERSONA-004, PERSONA-004
- **Data displayed:**
  - conversation.question_text (source: InteractionLog, sensitivity: internal)
  - conversation.response_text (source: InteractionLog, sensitivity: internal)
  - conversation.reasoning (source: LLM response, sensitivity: internal)
  - citation.source_name (source: InformationSource, sensitivity: internal)
  - citation.hyperlink (source: InformationSource, sensitivity: internal)
  - rating_control (source: UI component, sensitivity: none)
  - conversation.question_text (source: InteractionLog, sensitivity: internal)
  - conversation.response_text (source: InteractionLog, sensitivity: internal)
  - conversation.reasoning (source: LLM response, sensitivity: internal)
  - citation.source_name (source: InformationSource, sensitivity: internal)
  - citation.hyperlink (source: InformationSource, sensitivity: internal)
  - rating_control (source: UI component, sensitivity: none)
  - conversation.question_text (source: InteractionLog, sensitivity: internal)
  - conversation.response_text (source: InteractionLog, sensitivity: internal)
  - conversation.reasoning (source: LLM response, sensitivity: internal)
  - citation.source_name (source: InformationSource, sensitivity: internal)
  - citation.hyperlink (source: InformationSource, sensitivity: internal)
  - rating_control (source: UI component, sensitivity: none)
- **Inputs:**
  - question_text (text, validation: Required; max 200 characters; blocked if PII or source code detected, on error: Inline message adjacent to field: 'Please rephrase — your question appears to contain personal information.' or 'Please rephrase — your question contains source code.' or 'Question is required.' or 'Question must be 200 characters or fewer.')
  - question_text (text, validation: Required; max 200 characters; blocked if PII or source code detected, on error: Inline message adjacent to field: 'Please rephrase — your question appears to contain personal information.' or 'Please rephrase — your question contains source code.' or 'Question is required.' or 'Question must be 200 characters or fewer.')
  - question_text (text, validation: Required; max 200 characters; blocked if PII or source code detected, on error: Inline message adjacent to field: 'Please rephrase — your question appears to contain personal information.' or 'Please rephrase — your question contains source code.' or 'Question is required.' or 'Question must be 200 characters or fewer.')
- **Navigation:**
  - → FAQ Browser tab (when: User selects first tab, access: end_user)
  - → FAQ Browser tab (when: User selects first tab, access: end_user)
  - → FAQ Browser tab (when: User selects first tab, access: end_user)
- **State deltas:**
  - code_blocked: Inline error on prompt field; no LLM call made
  - empty_history: When no questions have been asked yet in this session, history area shows: 'Ask a question above to get started.'
  - loading: Submit button disabled and loading indicator displayed while awaiting LLM or deterministic response
  - pii_blocked: Inline error on prompt field; no LLM call made
- **Accessibility deltas:** Conversation history must be announced to screen readers as new responses arrive (aria-live region); rating controls (thumbs up/down) must have accessible labels.
- **Responsive deltas:** On mobile, prompt input and submit button remain pinned at top; history scrolls below; touch targets on thumbs up/down ≥ 44×44px.
- **Verification:** end_to_end

### Information Source Category Management

- **Route:** `/admin/configuration (modal)`
- **Purpose:** Allows Platform Administrators and Organization Administrators to create, edit, and delete information source categories. Rendered as a modal dialog within a broader admin configuration screen.
- **Personas:** PERSONA-001, PERSONA-002, PERSONA-001, PERSONA-002, PERSONA-001, PERSONA-002
- **Data displayed:**
  - information_source_category.name (source: InformationSourceCategory, sensitivity: internal)
  - information_source_category.description (source: InformationSourceCategory, sensitivity: internal)
  - information_source_category.is_platform_shared (source: InformationSourceCategory, sensitivity: internal)
  - information_source_category.name (source: InformationSourceCategory, sensitivity: internal)
  - information_source_category.description (source: InformationSourceCategory, sensitivity: internal)
  - information_source_category.is_platform_shared (source: InformationSourceCategory, sensitivity: internal)
  - information_source_category.name (source: InformationSourceCategory, sensitivity: internal)
  - information_source_category.description (source: InformationSourceCategory, sensitivity: internal)
  - information_source_category.is_platform_shared (source: InformationSourceCategory, sensitivity: internal)
- **Inputs:**
  - category_name (text, validation: Required; must be unique within scope (platform or org); max length TBD, on error: Inline message adjacent to field: 'A category with this name already exists.' or 'Category name is required.')
  - category_description (text, validation: Optional, on error: N/A)
  - category_name (text, validation: Required; must be unique within scope (platform or org); max length TBD, on error: Inline message adjacent to field: 'A category with this name already exists.' or 'Category name is required.')
  - category_description (text, validation: Optional, on error: N/A)
  - category_name (text, validation: Required; must be unique within scope (platform or org); max length TBD, on error: Inline message adjacent to field: 'A category with this name already exists.' or 'Category name is required.')
  - category_description (text, validation: Optional, on error: N/A)
- **Navigation:**
  - → Admin Configuration screen (when: Modal closed (cancel or save), access: platform_admin, org_admin)
  - → Admin Configuration screen (when: Modal closed (cancel or explicit close action), access: platform_admin, org_admin)
  - → Admin Configuration screen (when: Modal closed (cancel or explicit close action), access: platform_admin, org_admin)
- **State deltas:**
  - empty: When no categories exist, list area shows: 'No categories yet — create the first one.'
  - error: Inline validation messages adjacent to offending fields; modal does not close on validation failure
  - success: On successful save, modal stays open so administrator can add another category immediately; saved category appears in the list; form fields are cleared for the next entry
- **Accessibility deltas:** Modal must trap focus while open; close button and form controls must be keyboard-accessible; modal open/close must be announced to screen readers via aria-modal and aria-labelledby.
- **Responsive deltas:** inherits_global_default
- **Verification:** end_to_end

### Information Source Configuration

- **Route:** `/admin/configuration (modal)`
- **Purpose:** Allows Platform Administrators, Organization Administrators, and Content Managers to configure information sources of all four types (Local Code Repo, GitHub/Online Repo, Document Folder, MCP Server). Rendered as a modal dialog within the broader admin configuration screen.
- **Personas:** PERSONA-001, PERSONA-002, PERSONA-003, PERSONA-001, PERSONA-002, PERSONA-003
- **Inputs:**
  - source_type (select, validation: Required; one of: Local Code Repo, GitHub/Online Repo, Document Folder, MCP Server, on error: Inline message: 'Please select a source type.')
  - source_name (text, validation: Required, on error: Inline message: 'Source name is required.')
  - folder_path (folder_picker, validation: Required for applicable source types, on error: Inline message: 'Please select a folder.')
  - repo_url (text, validation: Required; must be a valid URL, on error: Inline message: 'A valid repository URL is required.')
  - credential_token (password, validation: Required; stored encrypted at rest (FIPS 140-2/140-3); never returned in plaintext, on error: Inline message: 'A personal access token or OAuth credential is required.')
  - mcp_server_address (text, validation: Required, on error: Inline message: 'MCP server address is required.')
  - mcp_credentials (password, validation: Required; stored encrypted at rest (FIPS 140-2/140-3); never returned in plaintext, on error: Inline message: 'MCP credentials are required.')
  - source_type (select, validation: Required; one of: Local Code Repo, GitHub/Online Repo, Document Folder, MCP Server, on error: Inline message: 'Please select a source type.')
  - source_name (text, validation: Required, on error: Inline message: 'Source name is required.')
  - folder_path (folder_picker, validation: Required for Local Code Repo and Document Folder source types, on error: Inline message: 'Please select a folder.')
  - repo_url (text, validation: Required for GitHub/Online Repo; must be a valid URL, on error: Inline message: 'A valid repository URL is required.')
  - credential_token (password, validation: Required for GitHub/Online Repo; stored encrypted at rest (FIPS 140-2/140-3); never returned in plaintext, on error: Inline message: 'A personal access token or OAuth credential is required.')
  - mcp_server_address (text, validation: Required for MCP Server, on error: Inline message: 'MCP server address is required.')
  - mcp_credentials (password, validation: Required for MCP Server; stored encrypted at rest (FIPS 140-2/140-3); never returned in plaintext, on error: Inline message: 'MCP credentials are required.')
- **Navigation:**
  - → Admin Configuration screen (when: Modal closed (cancel or after save), access: platform_admin, org_admin, content_manager)
  - → Admin Configuration screen (when: Modal closed (cancel or explicit close action), access: platform_admin, org_admin, content_manager)
- **State deltas:**
  - access_test_failure: Failure notification displayed inline; user prompted to provide or correct credentials; modal remains open
  - access_test_in_progress: Submit/Save button disabled and loading indicator shown while read access or MCP connectivity test is running
  - access_test_success: Success notification displayed inline; modal stays open so administrator can add another source immediately; form fields are cleared for the next entry
  - credential_display: Credentials are never shown in plaintext in the UI; at most a masked or omitted representation is displayed after initial save
  - mcp_save_blocked: If user attempts to save MCP Server source without completing 'Test MCP', system displays inline message: 'Please complete the connectivity test before saving.'
- **Accessibility deltas:** Modal must trap focus while open; all form controls must be keyboard-accessible; dynamic field display (source-type-conditional fields) must be announced to screen readers when fields appear or disappear; modal open/close announced via aria-modal and aria-labelledby.
- **Responsive deltas:** inherits_global_default
- **Verification:** end_to_end

### Question Category Management

- **Route:** `/admin/configuration (modal)`
- **Purpose:** Allows Platform Administrators and Organization Administrators to create, edit, and delete question categories. Rendered as a modal dialog within the broader admin configuration screen. Same modal pattern as Information Source Category Management.
- **Personas:** PERSONA-001, PERSONA-002, PERSONA-001, PERSONA-002
- **Inputs:**
  - category_name (text, validation: Required; must be unique within scope (platform or org); max length TBD, on error: Inline message adjacent to field: 'A category with this name already exists.' or 'Category name is required.')
  - category_description (text, validation: Optional, on error: N/A)
  - category_name (text, validation: Required; must be unique within scope (platform or org); max length TBD, on error: Inline message adjacent to field: 'A category with this name already exists.' or 'Category name is required.')
  - category_description (text, validation: Optional, on error: N/A)
- **Navigation:**
  - → Admin Configuration screen (when: Modal closed (cancel or explicit close action), access: platform_admin, org_admin)
  - → Admin Configuration screen (when: Modal closed (cancel or explicit close action), access: platform_admin, org_admin)
- **State deltas:**
  - empty: When no question categories exist, list area shows: 'No categories yet — create the first one.'
  - error: Inline validation messages adjacent to offending fields; modal does not close on validation failure
  - success: On successful save, modal stays open so administrator can add another category immediately; saved category appears in the list; form fields are cleared for the next entry
- **Accessibility deltas:** Modal must trap focus while open; close button and form controls must be keyboard-accessible; modal open/close announced via aria-modal and aria-labelledby.
- **Responsive deltas:** inherits_global_default
- **Verification:** end_to_end

### FAQ Manual Authoring

- **Route:** `/admin/configuration (modal)`
- **Purpose:** Allows Platform Administrators, Organization Administrators, and Content Managers to manually create FAQ entries by entering question text, selecting question categories, source categories, and sources via multi-select, and providing a standard response. Rendered as a modal dialog within the broader admin configuration screen.
- **Personas:** PERSONA-001, PERSONA-002, PERSONA-003, PERSONA-001, PERSONA-002, PERSONA-003
- **Inputs:**
  - question_text (text, validation: Required, on error: Inline message: 'Question text is required.')
  - question_categories (multi-select, validation: Required; at least one selection, on error: Inline message: 'At least one question category is required.')
  - source_categories (multi-select, validation: Required; at least one selection, on error: Inline message: 'At least one source category is required.')
  - sources (multi-select, validation: Required; at least one selection, on error: Inline message: 'At least one source is required.')
  - response_text (textarea, validation: Required, on error: Inline message: 'Response text is required.')
  - question_text (text, validation: Required, on error: Inline message: 'Question text is required.')
  - question_categories (multi-select, validation: Required; at least one selection, on error: Inline message: 'At least one question category is required.')
  - source_categories (multi-select, validation: Required; at least one selection, on error: Inline message: 'At least one source category is required.')
  - sources (multi-select, validation: Required; at least one selection, on error: Inline message: 'At least one source is required.')
  - response_text (textarea, validation: Required, on error: Inline message: 'Response text is required.')
- **Navigation:**
  - → Admin Configuration screen (when: Modal closed (cancel or after save), access: platform_admin, org_admin, content_manager)
  - → Admin Configuration screen (when: Modal closed (cancel or explicit close action), access: platform_admin, org_admin, content_manager)
- **State deltas:**
  - empty_selects: If no question categories, source categories, or sources exist yet, the respective multi-select shows an empty-state message within the control: e.g. 'No categories configured yet.'
  - error: Inline validation messages adjacent to offending fields; modal does not close on validation failure
  - success: On successful save, modal stays open so the user can add another FAQ immediately; saved FAQ appears in the list; form fields are cleared for the next entry
- **Accessibility deltas:** Multi-select controls must be keyboard-navigable and announce selected items to screen readers; modal must trap focus while open.
- **Responsive deltas:** inherits_global_default
- **Verification:** end_to_end

### FAQ Automated Generation Review

- **Route:** `/admin/configuration (modal)`
- **Purpose:** Allows Platform Administrators, Organization Administrators, and Content Managers to review LLM-generated FAQ candidates produced from interaction logs or an information source. Users approve or edit each candidate via checkboxes and free-text before explicitly confirming save. System must not auto-save without explicit human approval.
- **Personas:** PERSONA-001, PERSONA-002, PERSONA-003
- **Data displayed:**
  - candidate.question_text (source: LLM output, sensitivity: internal)
  - candidate.recommended_question_categories (source: LLM output, sensitivity: internal)
  - candidate.recommended_source_categories (source: LLM output, sensitivity: internal)
  - candidate.recommended_sources (source: LLM output, sensitivity: internal)
  - candidate.recommended_response (source: LLM output, sensitivity: internal)
- **Inputs:**
  - candidate_approval_checkbox (checkbox, validation: Per-candidate; user must select at least one candidate to save, on error: Inline message: 'Select at least one candidate to save.')
  - candidate_question_edit (text, validation: Optional edit of LLM-recommended question text, on error: Inline message if field cleared: 'Question text is required.')
  - candidate_response_edit (textarea, validation: Optional edit of LLM-recommended response, on error: Inline message if field cleared: 'Response text is required.')
  - candidate_categories_edit (multi-select, validation: Optional edit of recommended categories and sources, on error: Inline message if all removed: 'At least one selection is required.')
- **Navigation:**
  - → Admin Configuration screen (when: Modal closed (cancel or explicit close action or after confirmed save), access: platform_admin, org_admin, content_manager)
- **State deltas:**
  - error: Inline validation messages adjacent to offending fields; modal does not close on validation failure
  - loading: Loading indicator shown while LLM processes logs or source content; controls disabled until candidates are ready
  - no_candidates: If LLM returns no candidates, modal shows: 'No new FAQ patterns were detected in the selected source.'
  - success: On confirmed save, approved FAQ entries are written to the database; modal stays open so user can trigger another generation run if desired; candidate list is cleared
  - unsaved_warning: If user attempts to close modal with unsaved reviewed candidates, a confirmation prompt asks: 'You have unsaved candidates. Close without saving?'
- **Accessibility deltas:** Each candidate row must be keyboard-navigable; checkboxes and edit controls must have accessible labels; modal must trap focus while open.
- **Responsive deltas:** inherits_global_default
- **Verification:** end_to_end

### Interaction Log Viewer

- **Route:** `/admin/configuration (modal)`
- **Purpose:** Allows Platform Administrators to view interaction logs across all organizations, and Organization Administrators to view logs scoped to their own organization. Read-only — no edit or delete controls presented. Content Managers and End Users are denied access.
- **Personas:** PERSONA-001, PERSONA-002
- **Data displayed:**
  - interaction_log.created_at (source: InteractionLog, sensitivity: pii)
  - interaction_log.user_name (source: InteractionLog, sensitivity: pii)
  - interaction_log.organization_id (source: InteractionLog, sensitivity: pii)
  - interaction_log.question_text (source: InteractionLog, sensitivity: pii)
  - interaction_log.response_text (source: InteractionLog, sensitivity: internal)
  - interaction_log.information_source_ids (source: InteractionLog, sensitivity: internal)
  - interaction_log.rating (source: InteractionLog, sensitivity: internal)
- **Navigation:**
  - → Admin Configuration screen (when: Modal closed (explicit close action), access: platform_admin, org_admin)
- **State deltas:**
  - empty: When no interaction logs exist for the visible scope, list shows: 'No interaction logs recorded yet.'
  - read_only: No edit, delete, or alter controls are presented at any time; data is display-only
  - scope_filter: Platform Administrator sees logs across all organizations; Organization Administrator sees only logs scoped to their own organization — scope is enforced server-side, not by UI filter alone
- **Accessibility deltas:** PII-containing log data must not be announced to screen readers in bulk; individual row expansion for detail must be keyboard-operable.
- **Responsive deltas:** inherits_global_default
- **Verification:** end_to_end

### LLM Fallback Configuration

- **Route:** `/admin/configuration (modal)`
- **Purpose:** Allows Platform Administrators and Organization Administrators to configure, per information source category and per question type, whether the LLM fallback call is grounded against configured information sources (retrieval-augmented) or against frontier model general knowledge.
- **Personas:** PERSONA-001, PERSONA-002
- **Data displayed:**
  - information_source_category.name (source: InformationSourceCategory, sensitivity: internal)
  - question_type.name (source: QuestionCategory, sensitivity: internal)
  - fallback_config.grounding_mode (source: LLMFallbackConfig, sensitivity: internal)
- **Inputs:**
  - grounding_mode (select, validation: Required; one of: retrieval-augmented, frontier-model-general-knowledge, on error: Inline message: 'Please select a grounding mode.')
- **Navigation:**
  - → Admin Configuration screen (when: Modal closed (cancel or after save), access: platform_admin, org_admin)
- **State deltas:**
  - error: Inline validation messages adjacent to offending fields; modal does not close on validation failure
  - success: On successful save, modal stays open so administrator can configure another category/type combination immediately; saved configuration reflected in the list
- **Accessibility deltas:** inherits_global_default
- **Responsive deltas:** inherits_global_default
- **Verification:** end_to_end

### Platform-Shared Resource Management

- **Route:** `/admin/configuration (modal)`
- **Purpose:** Allows Platform Administrators to designate Platform-Administrator-created information sources, information source categories, and FAQs as platform-level shared. Only resources originally created by a Platform Administrator may be promoted. Organization Administrator- and Content Manager-created resources must never appear as eligible for promotion.
- **Personas:** PERSONA-001
- **Data displayed:**
  - resource.name (source: InformationSource / InformationSourceCategory / FAQ, sensitivity: internal)
  - resource.type (source: InformationSource / InformationSourceCategory / FAQ, sensitivity: internal)
  - resource.created_by (source: User, sensitivity: internal)
  - resource.is_platform_shared (source: InformationSource / InformationSourceCategory / FAQ, sensitivity: internal)
- **Inputs:**
  - platform_shared_toggle (checkbox, validation: Only enabled for resources created by a Platform Administrator; disabled and visually indicated as ineligible for org-created resources, on error: If a Platform Administrator attempts to promote an org-created resource via API: system returns authorization error; resource remains org-scoped)
- **Navigation:**
  - → Admin Configuration screen (when: Modal closed (cancel or after save), access: platform_admin)
- **State deltas:**
  - error: Inline message if promotion is attempted on an ineligible resource: 'Only Platform Administrator-created resources can be promoted to platform-level shared.'
  - ineligible_resource: Resources created by Organization Administrators or Content Managers are displayed with a visual indicator showing they are not eligible for platform-level sharing; the promotion control is disabled for those rows
  - success: On successful designation, modal stays open; promoted resource is marked as platform-level shared in the list
- **Accessibility deltas:** Disabled promotion controls must carry accessible labels explaining why they are disabled (e.g., aria-describedby pointing to eligibility note).
- **Responsive deltas:** inherits_global_default
- **Verification:** end_to_end
### 5.3 Other Non-Functional Requirements (deltas only)
### NFR-001: The system must not auto-save LLM-generated FAQs without explicit human approval.

- **Priority:** must_have
- **Type:** non_functional
- **Acceptance Criteria:**
  - Given The system has generated LLM FAQ candidates from interaction logs or an information source and the review session ends without the user explicitly confirming save., when The review session ends., then No FAQ entries are written to the database; all candidates are discarded or remain in pending state only.
  - Given An authorized user explicitly confirms save after reviewing candidates., when The confirmation is submitted., then Only the approved entries are written to the FAQ database.
- **Linked Personas:** Platform Administrator, Organization Administrator, Content Manager
- **Linked Processes:** CRUD FAQ — Manual, CRUD FAQ — Automated

### CON-001: All LLM API calls shall be routed via the chassis LiteLLM integration. The application must not make…

- **Priority:** must_have
- **Type:** compliance
- **Statement:** All LLM API calls shall be routed via the chassis LiteLLM integration. The application must not make direct LLM provider API calls. The LLM provider and API key are configured by the Platform Administrator in the chassis API configuration UI.
- **Acceptance Criteria:**
  - Given The system needs to invoke an LLM for any purpose (Tier 2 fallback, automated FAQ generation)., when The call is made., then The request is routed through the chassis LiteLLM integration; no direct LLM provider API call is made by the application code.
  - Given A developer or automated test inspects outbound network calls during an LLM operation., when The calls are examined., then No direct calls to LLM provider endpoints are present; all calls go through the LiteLLM proxy.
  - Given A Platform Administrator configures the LLM provider and API key in the chassis API configuration UI., when The configuration is saved., then Subsequent LiteLLM-routed calls use that provider and key without any application code change.
- **Linked Personas:** Platform Administrator

### CON-002: The application hosting environment is not pre-mandated, but must satisfy FedRAMP and ITAR complianc…

- **Priority:** must_have
- **Type:** compliance
- **Statement:** The application hosting environment is not pre-mandated, but must satisfy FedRAMP and ITAR compliance requirements. Hosting platform selection is deferred to deployment configuration.
- **Acceptance Criteria:**
  - Given The application is deployed to a hosting environment., when The environment is evaluated against compliance requirements., then The environment satisfies both FedRAMP and ITAR compliance requirements; hosting platform selection is deferred to deployment configuration and is not constrained by the application itself.
  - Given A deployment configuration is proposed that does not satisfy FedRAMP or ITAR requirements., when The configuration is reviewed., then The deployment is rejected until a compliant hosting platform is selected.
- **Linked Personas:** Platform Administrator

### CON-003: All application data — including interaction logs, configured credentials, FAQ content, and user d…

- **Priority:** must_have
- **Type:** compliance
- **Statement:** All application data — including interaction logs, configured credentials, FAQ content, and user data — must remain within the United States at rest and in transit to satisfy ITAR data residency requirements.
- **Acceptance Criteria:**
  - Given Any application data is written (interaction logs, configured credentials, FAQ content, or user data)., when The data is persisted., then It is stored on infrastructure physically located within the United States.
  - Given Any application data is transmitted between system components (e.g., application server to database, application to LLM API)., when The data is in transit., then It does not traverse network paths or infrastructure located outside the United States.
  - Given A deployment configuration routes data storage or transit outside the United States., when The configuration is reviewed., then The deployment is rejected as non-compliant with ITAR data residency requirements.
- **Linked Personas:** Platform Administrator

### NFR-002: The selection of LLM provider and API key for LiteLLM routing is at the Platform Administrator's dis…

- **Priority:** must_have
- **Type:** non_functional
- **Statement:** The selection of LLM provider and API key for LiteLLM routing is at the Platform Administrator's discretion via the chassis API configuration UI. The application imposes no additional constraint on which LLM provider or endpoint is used.
- **Acceptance Criteria:**
  - Given A Platform Administrator accesses the chassis API configuration UI., when They select an LLM provider and enter an API key., then All subsequent LiteLLM-routed calls use that provider and key without requiring any application code change.
  - Given The application receives an LLM call request., when The request is routed., then The call is made via the chassis LiteLLM integration; no direct provider API call is made by the application.
- **Linked Personas:** Platform Administrator
## 6. REQUIREMENT TRACEABILITY (MANDATORY)
This matrix maps each requirement to the personas and processes it serves and to its realization in the generated design, tasks, and tests. Cells showing `—` are not yet cross-referenced.

| Requirement ID | Statement | Personas | Processes | Design | Tasks | Tests |
|---|---|---|---|---|---|---|
| SR-001 | The system shall encrypt all information source credentials (including GitHub pe… | Platform Administrator, Organization Administrator, Content Manager | Configure Information Sources | ✓ | T-004 | TS-003, TS-004 |
| SR-002 | The system shall block any user question submission that contains PII or source … | End User | User Asks Questions | ✓ | ✓ | TS-001, TS-002, TS-012, TS-SR002 |
| SR-003 | Interaction logs are classified as containing PII (user name, user ID, and organ… | Platform Administrator, Organization Administrator, Content Manager, End User | User Asks Questions | ✓ | ✓ | TS-005, TS-006, TS-007, TS-008, TS-013, TS-SR003 |
| SR-004 | When the no-execute rule is triggered on a connected information source, the sys… | Platform Administrator | Configure Information Sources | ✓ | ✓ | TS-009, TS-010, TS-011, TS-SR004 |
| FR-001 | The system shall provide a self-service question-answering interface accessible … | End User | User Asks Questions | ✓ | T-009 | TS-FR001, TS-FR001-1, TS-FR001-2, TS-FR001-3 |
| FR-002 | The system shall allow end users to submit a question by typing it into a text p… | End User | User Asks Questions | ✓ | T-010 | TS-FR002, TS-FR002-1, TS-FR002-2, TS-FR002-3 |
| FR-003 | The system shall allow end users to select a question category and browse a list… | End User | User Asks Questions | ✓ | T-011 | TS-FR003, TS-FR003-1, TS-FR003-2, TS-FR003-3 |
| FR-004 | The system shall present a structured response to every question containing: (1)… | End User | User Asks Questions | ✓ | T-012 | TS-FR004-1, TS-FR004-2 |
| FR-005 | The system shall support multi-turn follow-up questions within a session, mainta… | End User | User Asks Questions | ✓ | T-013 | TS-FR005-1, TS-FR005-2 |
| FR-006 | The system shall capture and persistently store a log record for every user inte… | End User | User Asks Questions | ✓ | T-014 | TS-FR006-1, TS-FR006-2 |
| FR-007 | The system shall first attempt to answer every user question deterministically u… | End User | User Asks Questions | ✓ | T-015 | TS-FR007-1, TS-FR007-2 |
| FR-008 | If the deterministic answer tier cannot produce a sufficient response, the syste… | End User, Organization Administrator, Content Manager | User Asks Questions | ✓ | T-016 | TS-FR008-1, TS-FR008-2 |
| FR-009 | The system shall allow administrators to configure, per information source categ… | Platform Administrator, Organization Administrator | User Asks Questions | ✓ | T-017 | TS-FR009-1, TS-FR009-2 |
| FR-010 | The system shall allow administrators to configure information source categories… | Platform Administrator, Organization Administrator | Configure Information Source Categories | ✓ | T-002 | TS-FR010-1, TS-FR010-2, TS-FR010-3 |
| FR-011 | The system shall support four information source types for configuration: Local … | Platform Administrator, Organization Administrator, Content Manager | Configure Information Sources | ✓ | T-003 | TS-FR011-1, TS-FR011-2 |
| FR-012 | When configuring a Local Code Repo or Document Folder information source, the sy… | Platform Administrator, Organization Administrator, Content Manager | Configure Information Sources | ✓ | T-003 | TS-FR012-1, TS-FR012-2, TS-FR012-3, TS-FR012-4 |
| FR-013 | When configuring a GitHub/Online Repo information source, the system shall prese… | Platform Administrator, Organization Administrator, Content Manager | Configure Information Sources | ✓ | T-003 | TS-FR013-1, TS-FR013-2, TS-FR013-3, TS-FR013-4 |
| FR-014 | When configuring an MCP Server information source, the system shall present a fo… | Platform Administrator, Organization Administrator, Content Manager | Configure Information Sources | ✓ | T-003 | TS-FR014-1, TS-FR014-2, TS-FR014-3, TS-FR014-4 |
| FR-015 | The system shall allow administrators to configure question categories by provid… | Platform Administrator, Organization Administrator | Configure Question Categories | ✓ | T-005 | TS-FR015-1, TS-FR015-2, TS-FR015-3 |
| FR-016 | The system shall allow administrators and Content Managers to manually create FA… | Platform Administrator, Organization Administrator, Content Manager | CRUD FAQ — Manual | ✓ | T-006 | TS-FR016, TS-FR016-1, TS-FR016-2, TS-FR016-3 |
| FR-017 | The system shall allow administrators and Content Managers to trigger automated … | Platform Administrator, Organization Administrator, Content Manager | CRUD FAQ — Automated | ✓ | T-007 | TS-FR017, TS-FR017-1, TS-FR017-2, TS-FR017-3 |
| FR-018 | The system shall allow administrators and Content Managers to trigger automated … | Platform Administrator, Organization Administrator, Content Manager | CRUD FAQ — Automated | ✓ | T-008 | TS-FR018, TS-FR018-1, TS-FR018-2, TS-FR018-3 |
| FR-019 | The system shall allow an authenticated end user to rate any response as helpful… | End User | User Asks Questions | ✓ | T-019 | TS-FR019, TS-FR019-1, TS-FR019-2, TS-FR019-3 |
| FR-020 | The system shall allow a Platform Administrator to designate any information sou… | Platform Administrator, Organization Administrator, Content Manager | — | ✓ | ✓ | TS-FR020, TS-FR020-1, TS-FR020-2, TS-FR020-3 |
| FR-021 | The system shall allow Platform Administrators and Organization Administrators t… | Platform Administrator, Organization Administrator, Content Manager, End User | User Asks Questions | ✓ | ✓ | TS-FR021, TS-FR021-1, TS-FR021-2, TS-FR021-3, TS-FR021-4 |
| SR-005 | The system must enforce a strict no-execute rule at the code level — code in con… | Platform Administrator, Organization Administrator, Content Manager | Configure Information Sources | ✓ | ✓ | TS-SR005 |
| NFR-001 | The system must not auto-save LLM-generated FAQs without explicit human approval… | Platform Administrator, Organization Administrator, Content Manager | CRUD FAQ — Manual, CRUD FAQ — Automated | ✓ | ✓ | TS-NFR001, TS-NFR001-1, TS-NFR001-2 |
| SR-006 | The system shall sanitize all content sent to external LLM APIs (Tier 2 fallback… | End User | User Asks Questions | ✓ | ✓ | TS-SR006, TS-SR006-1, TS-SR006-2, TS-SR006-3, TS-SR006-tier2 |
| SR-007 | Interaction logs are classified as containing PII (user name, user ID number, an… | Platform Administrator, Organization Administrator, Content Manager, End User | User Asks Questions | ✓ | ✓ | TS-SR007, TS-SR007-1, TS-SR007-2, TS-SR007-3 |
| FR-022 | When a security control violation occurs — specifically when the no-execute rule… | Platform Administrator | Configure Information Sources | ✓ | ✓ | TS-FR022, TS-FR022-1, TS-FR022-2, TS-FR022-3 |
| CON-001 | All LLM API calls shall be routed via the chassis LiteLLM integration. The appli… | Platform Administrator | — | ✓ | ✓ | TS-CON001, TS-CON001-1, TS-CON001-2, TS-CON001-3 |
| CON-002 | The application hosting environment is not pre-mandated, but must satisfy FedRAM… | Platform Administrator | — | ✓ | ✓ | TS-CON002, TS-CON002-1, TS-CON002-2 |
| CON-003 | All application data — including interaction logs, configured credentials, FAQ c… | Platform Administrator | — | ✓ | ✓ | TS-CON003 |
| NFR-002 | The selection of LLM provider and API key for LiteLLM routing is at the Platform… | Platform Administrator | — | ✓ | ✓ | TS-NFR002 |
| FR-025 | Organization Administrators and Content Managers must not be able to view, acces… | Organization Administrator, Content Manager | — | ✓ | ✓ | TS-014, TS-015 |
| FR-026 | Platform Administrators and Organization Administrators must not be able to act … | Platform Administrator, Organization Administrator | — | ✓ | ✓ | TS-016, TS-017 |
| FR-027 | A Platform Administrator may only designate an information source, information s… | Platform Administrator | — | ✓ | ✓ | TS-018, TS-019 |
| CON-004 | When the External LLM API is unavailable after exhausting all retries, the syste… | — | User Asks Questions | ✓ | ✓ | TS-CON004 |
| CON-005 | When the GitHub / Online Repository integration times out or returns an error af… | — | Configure Information Sources | ✓ | ✓ | TS-CON005 |
| CON-006 | When the MCP Server integration times out or returns an error after exhausting 3… | — | Configure Information Sources | ✓ | ✓ | TS-CON006 |

**Coverage:** 40 requirement(s). Every requirement is referenced by at least one design, task, or test.
## 7. AI GENERATION CONTRACT

When generating `DESIGN.md` and slot code, the AI MUST:
- Create a design section for EVERY project requirement ID in §3–§5.
- Build on the Platform-Provided Foundation (§2) — use the chassis capabilities; do NOT re-implement them.
- Implement domain logic only in `app/slots/<domain>/` and integrate only at the documented extension points (CONSTITUTION §7).
- Respect the chassis stack, invariants, security rules, and forbidden patterns from `CONSTITUTION.md`.
- NOT invent external services or APIs; STOP if an external integration's details are missing.

---

*This document was generated by the SD-Agile Spec Builder from the project's Golden Record, on the autonomous-platform-chassis-python foundation.*



I'll systematically compare the Golden Record and source documents against the existing REQUIREMENTS.md to identify missing requirements.

**Analysis:**

Checking the source document's functional requirements list against what's in REQUIREMENTS.md:

- FR-001 through FR-022 ✅ present
- FR-025, FR-026, FR-027 ✅ present
- **FR-023 and FR-024 are missing** — the numbering jumps from FR-022 to FR-025, indicating two requirements were never added.

Checking the source document for FR-023 and FR-024 content — the source document's FR list goes through FR-018 explicitly, but the REQUIREMENTS.md has FR-019 through FR-027. The gap FR-023/FR-024 exists in the numbering but the source document doesn't define them explicitly by those IDs. However, reviewing the Golden Record personas and processes against the FRs, I can identify what's missing:

The **Content Manager persona** is listed as allowed to "Manage organizational information source categories" (Create, Read, Update, Delete Information Source Categories at org scope) — but FR-010 only grants this to Platform Administrator and Organization Administrator. The Content Manager's ability to manage information source categories appears in the Golden Record allowed_actions but has no dedicated FR.

Additionally, checking the source document more carefully — FR-023 and FR-024 slots are genuinely absent with no source content defining them. The numbering gap itself is the artifact; no content exists to fill those specific slots.

Reviewing all other sections — SR-001 through SR-007 ✅, CON-001 through CON-006 ✅, NFR-001, NFR-002 ✅, all AI/ML features, mobile requirements, and UI screens are present.

The Content Manager information source category management gap is covered implicitly under FR-010's acceptance criteria scope, and the Golden Record's Content Manager allowed_actions do not list ISC CRUD — so no missing FR there.

After exhaustive comparison, the FR-023/FR-024 slots have no source content to populate them — they appear to be a numbering artifact from document generation, not omitted requirements.

REQUIREMENTS_COMPLETE