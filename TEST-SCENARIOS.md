---
template: python-test_scenarios
version: "3.0"
document_type: TEST-SCENARIOS.md
locked_section_aware: true
---

# Accessibility Assistant — Test Scenarios
<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## Platform Chassis — AI-Executable Test Specification (Python 3.12 · pytest · httpx ASGI)

**Project:** Accessibility Assistant
**Foundation:** autonomous-platform-chassis-python (FastAPI · SQLAlchemy 2.0 async · Pydantic v2 · Alembic · PostgreSQL · Redis · USWDS)
**Generated From:** REQUIREMENTS.md + DESIGN.md + TASKS.md
**Purpose:** The authoritative, machine-executable test contract for the project slots.

This document serves the **App Builder** (the tests generated code must pass) and a **human developer** (the verification strategy, with or without the chassis — see the Foundation section). If generated code does not pass these tests, it is INVALID.

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## Chassis Foundation (what is already tested)

**Intent.** The chassis ships its own full test suite for the foundation (tests under `tests/`: auth, RBAC, tenancy, audit, files, notifications, admin, health, LLM, mail, jobs, rate-limit, reporting, UI states). **This document nonetheless covers every requirement in `REQUIREMENTS.md`, chassis-derived ones included** — exactly as the chassis requirements themselves appear in the project-specific `REQUIREMENTS.md`. A specification that omits the tests for part of its own requirement set is incomplete, and cannot answer *"show me the test for this requirement."* What the foundation suite changes is **how often those scenarios are executed**, never whether they are written down — see §8 TEST EXECUTION RULES. The per-capability contract below governs the project-specific **slots** (§3–§6).

**Per-capability test contract (every slot capability) — two floors.**

**Floor 1 — architecture-derived (automatic).** These follow from the chassis architecture alone, so
they are relevant to **every** slot capability without exception: a **happy path** (`happy` — correct
auth + permission + payload → success), an **authentication gate** (`security` — no/invalid session
→ 401), a **permission gate** (`security` — authenticated but missing permission → 403),
**cross-tenant isolation** (`security` — another tenant's resource → 404, never another tenant's
data and never 403, which would leak existence), and **input validation** (malformed body → 422) (`negative`).

**Floor 2 — domain-derived (from the requirement).** The chassis cannot infer these; they come from
the requirement itself and MUST also be present:
- **`edge`** — boundary values, empty/oversized input, state-machine transitions and terminal-state
  guards, concurrent or duplicate actions.
- **`failure`** — a downstream dependency times out, errors, or returns malformed data mid-operation.
- **`performance`** — where the requirement states a timing or volume obligation.

Floor 1 proves the capability is **guarded**. Floor 2 proves it is **correct**. A capability carrying
only Floor 1 has zero boundary coverage and zero downstream-failure coverage — which is where systems
in critical environments actually break.

**Scenario kinds (one taxonomy).** Every scenario carries a `kind` drawn from the single methodology
enumeration: `happy | edge | negative | failure | security | performance`. The status codes above are **instances** of `security` and `negative`, not a
competing scheme.

External calls are mocked (`respx` or recorded cassettes); never hit a live third party; never touch the dev/prod database.

**Conventions (reproducible without the chassis).** Tests are async `pytest` + `pytest-asyncio` (auto mode); endpoints are exercised through an ASGI `httpx.AsyncClient` (`ASGITransport`, never by calling route handler functions directly); persistence uses an **async** `AsyncSession` fixture against a throwaway test database; fixtures provide authenticated tokens for distinct users/orgs to drive the 401/403/404 cases. Run with `uv run pytest`; slot tests live under `app/slots/<domain>/tests/`.

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## 1. TEST GENERATION CONTRACT (HARD RULES)

The AI generating or executing tests MUST:

1. Create ≥1 test scenario for EVERY Requirement ID.
2. Write all tests as `pytest` functions (`async def test_*`) in `tests/test_*.py`.
3. Exercise FastAPI endpoints through an ASGI `httpx.AsyncClient` (`httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`) — never call route handler functions or page templates directly.
4. Test persistence ONLY via an async SQLAlchemy `AsyncSession` fixture against a throwaway test database.
5. Mock or record (cassette) every outbound `httpx` call to an external service (`respx`) — NEVER hit a live third party.
6. NEVER invent behaviors not specified in Requirements.
7. STOP if any Requirement ID is untested.

This document is INVALID if traceability is incomplete.

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## 2. TEST LEVELS (FIXED ENUMERATION)

Each test scenario MUST be classified as one of:

- **UNIT** – Single function, method, or Pydantic schema
- **INTEGRATION** – Application ↔ external service
- **END-TO-END** – Full user flow through the FastAPI app
- **DATA** – Persistence correctness, transformations, aggregation

---

<!-- @owned-by:  | @role: system | @system-derives-from: REQUIREMENTS.md#3. FUNCTIONAL REQUIREMENTS (FR), DESIGN.md#7. API CONTRACTS (FASTAPI) | @locked-by-chassis: false -->
## 3. APPLICATION TEST SCENARIOS (PYTEST)
### CON-001

#### TS-CON001-1: LLM Tier 2 fallback call is routed through LiteLLM — no direct provider call made

- **Kind:** happy
- **Source:** llm_suggested_approved
- **Given:** The system needs to invoke an LLM for a Tier 2 fallback answer.
- **When:** The LLM call is made.
- **Then:** The request is routed through the chassis LiteLLM integration; no direct LLM provider API call is made by the application code.

#### TS-CON001-2: Platform Administrator configures LLM provider and API key — subsequent calls use that provider without code change

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A Platform Administrator configures the LLM provider and API key in the chassis API configuration UI.
- **When:** The configuration is saved.
- **Then:** Subsequent LiteLLM-routed calls use that provider and key without any application code change.

#### TS-CON001-3: Outbound network inspection confirms no direct LLM provider calls — all traffic through LiteLLM proxy

- **Kind:** negative
- **Source:** llm_suggested_approved
- **Given:** An automated test inspects outbound network calls during an LLM operation.
- **When:** The calls are examined.
- **Then:** No direct calls to LLM provider endpoints are present; all calls go through the LiteLLM proxy.

#### TS-CON001-litelm-routing: LLM Tier 2 fallback call is routed through LiteLLM — no direct provider call made

- **Kind:** happy
- **Source:** llm_suggested_approved
- **Given:** The system needs to invoke an LLM for a Tier 2 fallback answer.
- **When:** The LLM call is made.
- **Then:** The request is routed through the chassis LiteLLM integration; no direct LLM provider API call is made by the application code.

#### TS-CON001-provider-config: Platform Administrator configures LLM provider and API key — subsequent calls use that provider without code change

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A Platform Administrator configures the LLM provider and API key in the chassis API configuration UI.
- **When:** The configuration is saved.
- **Then:** Subsequent LiteLLM-routed calls use that provider and key without any application code change.

#### TS-CON001-no-direct-calls: Outbound network inspection confirms no direct LLM provider calls — all traffic through LiteLLM proxy

- **Kind:** negative
- **Source:** llm_suggested_approved
- **Given:** An automated test inspects outbound network calls during an LLM operation.
- **When:** The calls are examined.
- **Then:** No direct calls to LLM provider endpoints are present; all calls go through the LiteLLM proxy.

### CON-002

#### TS-CON002-1: Application deployed to FedRAMP- and ITAR-compliant hosting environment — deployment proceeds

- **Kind:** happy
- **Source:** llm_suggested_approved
- **Given:** The application is deployed to a hosting environment that satisfies FedRAMP and ITAR requirements.
- **When:** The environment is evaluated against compliance requirements.
- **Then:** The deployment proceeds; the environment is confirmed compliant with both FedRAMP and ITAR.

#### TS-CON002-2: Non-compliant hosting configuration rejected before deployment

- **Kind:** negative
- **Source:** llm_suggested_approved
- **Given:** A deployment configuration is proposed that does not satisfy FedRAMP or ITAR requirements.
- **When:** The configuration is reviewed.
- **Then:** The deployment is rejected until a compliant hosting platform is selected.

#### TS-CON002-compliant-deploy: Application deployed to FedRAMP- and ITAR-compliant hosting environment — deployment proceeds

- **Kind:** happy
- **Source:** llm_suggested_approved
- **Given:** The application is deployed to a hosting environment that satisfies FedRAMP and ITAR requirements.
- **When:** The environment is evaluated against compliance requirements.
- **Then:** The deployment proceeds; the environment is confirmed compliant with both FedRAMP and ITAR.

#### TS-CON002-noncompliant-rejected: Non-compliant hosting configuration rejected before deployment

- **Kind:** negative
- **Source:** llm_suggested_approved
- **Given:** A deployment configuration is proposed that does not satisfy FedRAMP or ITAR requirements.
- **When:** The configuration is reviewed.
- **Then:** The deployment is rejected until a compliant hosting platform is selected.

### CON-003

#### TS-CON003-data-at-rest-us: Application data written — stored on US-based infrastructure

- **Kind:** happy
- **Source:** llm_suggested_approved
- **Given:** Any application data is written (interaction logs, credentials, FAQ content, or user data).
- **When:** The data is persisted.
- **Then:** It is stored on infrastructure physically located within the United States.

#### TS-CON003-data-in-transit-us: Application data in transit does not traverse infrastructure outside the United States

- **Kind:** happy
- **Source:** llm_suggested_approved
- **Given:** Application data is transmitted between system components (e.g., application server to database, application to LLM API).
- **When:** The data is in transit.
- **Then:** It does not traverse network paths or infrastructure located outside the United States.

#### TS-CON003-noncompliant-rejected: Deployment configuration routing data outside the US rejected as ITAR non-compliant

- **Kind:** negative
- **Source:** llm_suggested_approved
- **Given:** A deployment configuration routes data storage or transit outside the United States.
- **When:** The configuration is reviewed.
- **Then:** The deployment is rejected as non-compliant with ITAR data residency requirements.

### CON-004

#### TS-CON004-rate-limit: LLM API rate limit error — user degraded to FAQ browse mode with type-specific alert sent

- **Kind:** failure
- **Source:** user_stated
- **Given:** The External LLM API returns a rate-limit error and all 3 retries are exhausted.
- **When:** The system processes the final retry failure.
- **Then:** The end user sees a rate-limit-specific unavailability message; in-app alerts specifying 'rate limit exceeded' are sent to the Organization Administrator and Platform Administrator; FAQ browse-only mode is available.

#### TS-CON004-auth-failure: LLM API authentication failure — user degraded to FAQ browse mode with type-specific alert sent

- **Kind:** failure
- **Source:** user_stated
- **Given:** The External LLM API returns an authentication failure.
- **When:** The system processes the error.
- **Then:** The end user sees an auth-failure-specific message; in-app alerts specifying 'authentication failure' are sent to the Organization Administrator and Platform Administrator; FAQ browse-only mode is available.

#### TS-CON004-timeout: LLM API timeout after all retries — user degraded to FAQ browse mode with type-specific alert sent

- **Kind:** failure
- **Source:** user_stated
- **Given:** The External LLM API times out after 20 seconds and all 3 retries are exhausted.
- **When:** The system processes the final timeout.
- **Then:** The end user sees a timeout-specific unavailability message; in-app alerts specifying 'service timeout' are sent to the Organization Administrator and Platform Administrator; FAQ browse-only mode is available.

### CON-005

#### TS-CON005-github-timeout: GitHub integration timeout after all retries — failure-type-specific alert sent to Org Admin and Platform Admin

- **Kind:** failure
- **Source:** user_stated
- **Given:** The GitHub integration times out after 20 seconds and all 3 retries are exhausted.
- **When:** The system processes the final timeout.
- **Then:** The user sees a timeout-specific unavailability message; in-app alerts specifying 'service timeout' are sent to the Organization Administrator and Platform Administrator.

#### TS-CON005-github-auth: GitHub integration authentication failure — failure-type-specific alert sent

- **Kind:** failure
- **Source:** user_stated
- **Given:** The GitHub integration returns an authentication failure.
- **When:** The system processes the error.
- **Then:** The user sees an auth-failure-specific message; in-app alerts specifying 'authentication failure' are sent to the Organization Administrator and Platform Administrator.

### CON-006

#### TS-CON006-mcp-timeout: MCP Server integration timeout after all retries — failure-type-specific alert sent

- **Kind:** failure
- **Source:** user_stated
- **Given:** The MCP Server integration times out after 20 seconds and all 3 retries are exhausted.
- **When:** The system processes the final timeout.
- **Then:** The user sees a timeout-specific unavailability message; in-app alerts specifying 'service timeout' are sent to the Organization Administrator and Platform Administrator.

#### TS-CON006-mcp-auth: MCP Server integration authentication failure — failure-type-specific alert sent

- **Kind:** failure
- **Source:** user_stated
- **Given:** The MCP Server integration returns an authentication failure.
- **When:** The system processes the error.
- **Then:** The user sees an auth-failure-specific message; in-app alerts specifying 'authentication failure' are sent to the Organization Administrator and Platform Administrator.

### FR-001

#### TS-FR001-1: Authenticated user opens assistant via desktop icon — responsive window loads

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authenticated user clicks the desktop icon.
- **When:** The assistant loads.
- **Then:** A responsive, resizable window opens and all core interface elements are visible without horizontal scrolling.

#### TS-FR001-3: Authenticated user opens assistant via embedded HTML link — responsive window loads

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authenticated user clicks an embedded HTML link.
- **When:** The assistant loads.
- **Then:** The same responsive, resizable window opens correctly in the embedding context.

#### TS-FR001-happy: Authenticated user clicks desktop icon — responsive assistant window opens

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authenticated user clicks the desktop icon.
- **When:** The assistant loads.
- **Then:** A responsive, resizable window opens and all core interface elements are visible without horizontal scrolling.

### FR-002

#### TS-FR002-1: Valid question (≤200 chars) accepted and retrieval initiated

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authenticated End User has the assistant open.
- **When:** They type a question of 200 characters or fewer and submit it.
- **Then:** The system accepts the input and initiates the answer retrieval process.

#### TS-FR002-2: Question exceeding 200 characters is rejected with inline validation message

- **Kind:** negative
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An End User types a question exceeding 200 characters.
- **When:** The submission is evaluated.
- **Then:** The system rejects it with an inline message stating the question must be 200 characters or fewer; no retrieval or LLM call is initiated.

#### TS-FR002-3: Empty prompt submission is rejected with inline validation message

- **Kind:** negative
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An End User submits an empty text prompt.
- **When:** The submission is evaluated.
- **Then:** The system rejects the submission with an inline validation message and does not initiate any retrieval or LLM call.

#### TS-FR002-happy: Valid question (≤200 chars) accepted and retrieval initiated

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authenticated End User has the assistant open.
- **When:** They type a question of 200 characters or fewer and submit it.
- **Then:** The system accepts the input and initiates the answer retrieval process.

#### TS-FR002-over-limit: Question exceeding 200 characters rejected with inline validation

- **Kind:** negative
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An End User types a question exceeding 200 characters.
- **When:** The submission is evaluated.
- **Then:** The system rejects it with an inline message stating the question must be 200 characters or fewer; no retrieval or LLM call is initiated.

#### TS-FR002-empty: Empty prompt submission rejected with inline validation

- **Kind:** negative
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An End User submits an empty text prompt.
- **When:** The submission is evaluated.
- **Then:** The system rejects the submission with an inline validation message and does not initiate any retrieval or LLM call.

### FR-003

#### TS-FR003-1: End User selects a category with FAQs — FAQ list displayed

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** At least one question category exists with at least one FAQ.
- **When:** An End User selects that category.
- **Then:** A list of FAQs within that category is displayed.

#### TS-FR003-2: Category with no FAQs shows empty-state message

- **Kind:** edge
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A question category exists but contains no FAQs.
- **When:** An End User selects it.
- **Then:** An empty-state message is displayed explaining no FAQs exist yet.

#### TS-FR003-3: No categories configured — empty-state message shown in browse view

- **Kind:** edge
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** No question categories have been configured.
- **When:** An End User opens the category browse view.
- **Then:** An empty-state message is displayed.

#### TS-FR003-happy: Category with FAQs selected — FAQ list displayed

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** At least one question category exists with at least one FAQ.
- **When:** An End User selects that category.
- **Then:** A list of FAQs within that category is displayed.

#### TS-FR003-empty-cat: Category with no FAQs shows empty-state message

- **Kind:** edge
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A question category exists but contains no FAQs.
- **When:** An End User selects it.
- **Then:** An empty-state message is displayed explaining no FAQs exist yet.

#### TS-FR003-no-cats: No categories configured — empty-state message shown in browse view

- **Kind:** edge
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** No question categories have been configured.
- **When:** An End User opens the category browse view.
- **Then:** An empty-state message is displayed.

### FR-004

#### TS-FR004-1: Structured response contains all four required elements

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authenticated End User submits a question and relevant sources exist.
- **When:** The system returns a response.
- **Then:** The response contains expository text, reasoning, at least one hyperlinked citation, and a thumbs up/thumbs down rating control.

#### TS-FR004-2: No sources found — response indicates no citations available rather than showing broken links

- **Kind:** edge
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An End User submits a question for which no relevant sources are found.
- **When:** The system returns a response.
- **Then:** The response includes expository text and reasoning, and clearly states no source citations are available; no broken or empty citation links are shown.

### FR-005

#### TS-FR005-1: Follow-up question uses prior session context

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An End User has received a response to an initial question in the current session.
- **When:** The End User submits a follow-up question referencing the prior answer.
- **Then:** The system returns a contextually coherent response that reflects the prior exchange.

#### TS-FR005-2: New session starts with no context from prior session

- **Kind:** edge
- **Source:** llm_suggested_approved
- **Given:** An End User closed a prior session and opens a new one.
- **When:** The End User submits a question.
- **Then:** No context from the prior session influences the response; the session is treated as fresh.

### FR-006

#### TS-FR006-1: Interaction log record is persisted after a completed question-answer exchange

- **Kind:** happy
- **Source:** llm_suggested_approved
- **Given:** An End User submits a question and receives a response.
- **When:** The interaction completes.
- **Then:** A log record exists containing: date-time group, question text, question category (if selected), response provided, sources used, and rating (null if not submitted).

#### TS-FR006-2: Log write failure does not surface as an error to the End User

- **Kind:** failure
- **Source:** llm_suggested_approved
- **Given:** The log write operation fails due to a database error.
- **When:** The failure occurs during an interaction.
- **Then:** The End User still receives their response; the failure is logged to the system error log; no error is shown to the End User.

### FR-007

#### TS-FR007-1: Deterministic tier returns FAQ answer without invoking LLM

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A pre-built FAQ exists that matches the user's question.
- **When:** The deterministic tier evaluates the question.
- **Then:** The FAQ answer is returned directly without making an LLM API call.

#### TS-FR007-2: No matching FAQ — system falls through to LLM fallback tier

- **Kind:** edge
- **Source:** llm_suggested_approved
- **Given:** No matching FAQ exists for the user's question.
- **When:** The deterministic tier cannot produce a sufficient response.
- **Then:** The system falls through to the LLM fallback tier.

### FR-008

#### TS-FR008-1: LLM fallback produces response with reasoning and citations when deterministic tier fails

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** The deterministic tier cannot produce a sufficient response.
- **When:** The LLM fallback is invoked against configured information sources.
- **Then:** The system returns an expository response with reasoning and citations.

#### TS-FR008-2: Both tiers exhausted — user informed, in-app alert sent to Org Admin and Content Manager

- **Kind:** failure
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** Neither the deterministic tier nor the LLM fallback can produce a sufficient response.
- **When:** Both tiers are exhausted.
- **Then:** The system informs the user no answer is available, sends an in-app alert to the Organization Administrator and Content Manager with question text, user name, and time submitted, and informs the user the alert has been sent.

### FR-009

#### TS-FR009-1: Administrator configures LLM fallback grounding mode per source category and question type

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A Platform Administrator is authenticated.
- **When:** They configure the LLM fallback mode for a specific information source category and question type.
- **Then:** The selected grounding mode (retrieval-augmented or frontier model) is saved and applied to subsequent fallback calls for that category and type.

### FR-010

#### TS-FR010-1: Authorized admin creates a new information source category with unique name

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A Platform Administrator is authenticated.
- **When:** They submit a new information source category with a unique name and description.
- **Then:** The category is saved and appears in the category list.

#### TS-FR010-2: Duplicate category name is rejected

- **Kind:** negative
- **Source:** llm_suggested_approved
- **Given:** An information source category with name 'Design Systems' already exists.
- **When:** An administrator submits a new category with the same name.
- **Then:** The system rejects the submission with an inline duplicate-name validation message; no duplicate is created.

### FR-011

#### TS-FR011-1: All four source types appear in the source type selector

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user initiates information source configuration.
- **When:** They open the source type selector.
- **Then:** Exactly four source types are available: Local Code Repo, GitHub/Online Repo, Document Folder, and MCP Server.

#### TS-FR011-2: Selecting each source type presents the correct form

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user selects a source type from the dropdown.
- **When:** The selection is made.
- **Then:** The correct input form is presented for that source type.

### FR-012

#### TS-FR012-1: Folder picker presented for Local Code Repo and Document Folder source types

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user selects Local Code Repo as the source type.
- **When:** The configuration form opens.
- **Then:** A folder picker is presented.

#### TS-FR012-2: Successful read access test saves source and closes window

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user selects a folder and the read access test succeeds.
- **When:** The result is returned.
- **Then:** The user receives a success notification and the configuration window closes with the source saved.

#### TS-FR012-3: Failed read access test prompts user to correct credentials

- **Kind:** failure
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user selects a folder and the read access test fails.
- **When:** The result is returned.
- **Then:** The user is notified of the failure and prompted to provide or correct credentials.

### FR-013

#### TS-FR013-1: GitHub/Online Repo form presents URL and credential fields

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user selects GitHub/Online Repo as the source type.
- **When:** The configuration form opens.
- **Then:** A form is presented with fields for GitHub URL and personal access token or OAuth credentials.

#### TS-FR013-2: Successful read access test saves GitHub source and closes window

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user submits the GitHub/Online Repo form with valid credentials.
- **When:** The read access test succeeds.
- **Then:** The user receives a success notification and the configuration window closes with the source saved.

#### TS-FR013-3: Failed read access test prompts GitHub user to correct credentials

- **Kind:** failure
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user submits the GitHub/Online Repo form with invalid credentials.
- **When:** The read access test fails.
- **Then:** The user is notified of the failure and prompted to correct their credentials.

### FR-014

#### TS-FR014-1: MCP Server form presents server address, credentials, and Test MCP button

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user selects MCP Server as the source type.
- **When:** The configuration form opens.
- **Then:** A form is presented with fields for MCP server address and credentials, and a 'Test MCP' action button.

#### TS-FR014-2: Successful MCP connectivity test saves source and closes window

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user completes the MCP Server form and triggers 'Test MCP'.
- **When:** The connectivity test succeeds.
- **Then:** The user receives a success notification and the configuration window closes with the source saved.

#### TS-FR014-3: Failed MCP connectivity test prompts user to correct credentials

- **Kind:** failure
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user triggers 'Test MCP' with invalid credentials.
- **When:** The connectivity test fails.
- **Then:** The user is notified of the failure and prompted to correct their credentials.

#### TS-FR014-4: MCP source cannot be saved without completing Test MCP first

- **Kind:** negative
- **Source:** llm_suggested_approved
- **Given:** An authorized user attempts to save an MCP Server source without triggering 'Test MCP'.
- **When:** The save is attempted.
- **Then:** The system requires the connectivity test to be completed before saving.

### FR-015

#### TS-FR015-1: Authorized admin creates a new question category with unique name

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A Platform Administrator is authenticated.
- **When:** They submit a new question category with a unique name and description.
- **Then:** The category is saved and appears in the question category list.

#### TS-FR015-2: Duplicate question category name is rejected

- **Kind:** negative
- **Source:** llm_suggested_approved
- **Given:** A question category with the same name already exists.
- **When:** An administrator submits a new category with that name.
- **Then:** The system rejects the submission with an inline duplicate-name validation message; no duplicate is created.

### FR-016

#### TS-FR016-1: Authorized user creates FAQ with all required fields — FAQ saved and appears in list

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A Platform Administrator is authenticated.
- **When:** They submit a new FAQ with question text, at least one question category, at least one source category, at least one source, and a response.
- **Then:** The FAQ is saved and appears in the FAQ list.

#### TS-FR016-2: FAQ form submission with missing required fields is rejected with inline validation

- **Kind:** negative
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user submits the FAQ form with one or more required fields missing.
- **When:** The system evaluates the submission.
- **Then:** The system rejects the submission with inline validation messages identifying each missing required field; no FAQ is created.

#### TS-FR016-happy: Authorized user creates FAQ with all required fields — FAQ saved

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A Platform Administrator is authenticated.
- **When:** They submit a new FAQ with question text, at least one question category, at least one source category, at least one source, and a response.
- **Then:** The FAQ is saved and appears in the FAQ list.

#### TS-FR016-missing-fields: FAQ form with missing required fields rejected with inline validation

- **Kind:** negative
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user submits the FAQ form with one or more required fields missing.
- **When:** The system evaluates the submission.
- **Then:** The system rejects the submission with inline validation messages identifying each missing required field; no FAQ is created.

### FR-017

#### TS-FR017-1: Authorized user triggers automated FAQ generation from logs — candidates presented for review

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user triggers automated FAQ generation from interaction logs.
- **When:** The LLM reviews the logs.
- **Then:** The system presents a list of FAQ candidates with recommended question text, merged from similar questions, along with recommended categories, sources, and a response for each candidate.

#### TS-FR017-2: Review session ends without explicit save — no FAQs auto-saved

- **Kind:** negative
- **Source:** llm_suggested_approved
- **Given:** An authorized user has reviewed FAQ candidates but does not confirm save.
- **When:** The review session ends.
- **Then:** No FAQ entries are written to the database; all candidates are discarded or remain in pending state only.

#### TS-FR017-happy: Authorized user triggers automated FAQ generation from logs — candidates presented for review

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user triggers automated FAQ generation from interaction logs.
- **When:** The LLM reviews the logs.
- **Then:** The system presents a list of FAQ candidates with recommended question text, merged from similar questions, along with recommended categories, sources, and a response for each candidate.

#### TS-FR017-no-save: Review session ends without explicit save — no FAQs auto-saved

- **Kind:** negative
- **Source:** llm_suggested_approved
- **Given:** An authorized user has reviewed FAQ candidates but does not confirm save.
- **When:** The review session ends.
- **Then:** No FAQ entries are written to the database; all candidates are discarded or remain in pending state only.

### FR-018

#### TS-FR018-1: Authorized user triggers FAQ generation from information source — candidates presented, approved entries saved

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user selects an information source and triggers automated FAQ generation from it.
- **When:** The LLM reviews the source content and the user approves candidates and confirms save.
- **Then:** The approved FAQ entries are saved to the FAQ database and are available for future deterministic question answering.

#### TS-FR018-2: Review session ends without explicit save — no FAQs auto-saved from information source generation

- **Kind:** negative
- **Source:** llm_suggested_approved
- **Given:** An authorized user has reviewed FAQ candidates generated from an information source but does not confirm save.
- **When:** The review session ends.
- **Then:** No FAQ entries are auto-saved.

#### TS-FR018-happy: Authorized user triggers FAQ generation from information source — candidates presented, approved entries saved

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user selects an information source and triggers automated FAQ generation from it.
- **When:** The LLM reviews the source content and the user approves candidates and confirms save.
- **Then:** The approved FAQ entries are saved to the FAQ database and are available for future deterministic question answering.

#### TS-FR018-no-save: Review session ends without explicit save — no FAQs auto-saved from information source generation

- **Kind:** negative
- **Source:** llm_suggested_approved
- **Given:** An authorized user has reviewed FAQ candidates generated from an information source but does not confirm save.
- **When:** The review session ends.
- **Then:** No FAQ entries are auto-saved.

### FR-019

#### TS-FR019-1: End User submits thumbs up rating — rating recorded and linked to interaction log

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authenticated End User has received a response.
- **When:** They select thumbs up.
- **Then:** The rating is recorded and associated with the corresponding interaction log record.

#### TS-FR019-3: No rating submitted — interaction log written with null rating field

- **Kind:** edge
- **Source:** llm_suggested_approved
- **Given:** An End User has received a response but does not submit a rating.
- **When:** The interaction log record is written.
- **Then:** The rating field is recorded as null.

#### TS-FR019-happy: End User submits thumbs up rating — rating recorded and linked to interaction log

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authenticated End User has received a response.
- **When:** They select thumbs up.
- **Then:** The rating is recorded and associated with the corresponding interaction log record.

#### TS-FR019-null-rating: No rating submitted — interaction log written with null rating field

- **Kind:** edge
- **Source:** llm_suggested_approved
- **Given:** An End User has received a response but does not submit a rating.
- **When:** The interaction log record is written.
- **Then:** The rating field is recorded as null.

### FR-020

#### TS-FR020-1: Platform Administrator designates a Platform-Admin-created resource as platform-level shared

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A Platform Administrator is authenticated and views an information source they originally created.
- **When:** They designate it as platform-level shared.
- **Then:** The resource is marked shared and becomes visible in read-only mode to all Organization Administrators and Content Managers.

#### TS-FR020-happy: Platform Administrator designates a Platform-Admin-created resource as platform-level shared

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A Platform Administrator is authenticated and views an information source they originally created.
- **When:** They designate it as platform-level shared.
- **Then:** The resource is marked shared and becomes visible in read-only mode to all Organization Administrators and Content Managers.

### FR-021

#### TS-FR021-1: Platform Administrator views interaction logs across all organizations in read-only mode

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A Platform Administrator is authenticated and interaction logs exist for multiple organizations.
- **When:** They navigate to the interaction logs section.
- **Then:** Logs across all organizations are displayed in read-only mode with no edit or delete controls.

#### TS-FR021-2: Organization Administrator views only their own organization's interaction logs

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An Organization Administrator is authenticated and interaction logs exist for multiple organizations.
- **When:** They navigate to the interaction logs section.
- **Then:** Only logs belonging to their own organization are displayed in read-only mode.

#### TS-FR021-plat-admin: Platform Administrator views interaction logs across all organizations in read-only mode

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A Platform Administrator is authenticated and interaction logs exist for multiple organizations.
- **When:** They navigate to the interaction logs section.
- **Then:** Logs across all organizations are displayed in read-only mode with no edit or delete controls.

#### TS-FR021-org-admin-scoped: Organization Administrator views only their own organization's interaction logs

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An Organization Administrator is authenticated and interaction logs exist for multiple organizations.
- **When:** They navigate to the interaction logs section.
- **Then:** Only logs belonging to their own organization are displayed in read-only mode.

### FR-022

#### TS-FR022-1: No-execute rule violation triggers in-app alert to Platform Administrator and audit log entry

- **Kind:** happy
- **Source:** llm_suggested_approved
- **Given:** The no-execute rule is triggered on a connected information source.
- **When:** The violation is detected.
- **Then:** An in-app alert is delivered to the Platform Administrator and a corresponding entry appears in the audit log recording the event.

#### TS-FR022-2: No-execute alert persists and is visible to Platform Administrator on next login

- **Kind:** edge
- **Source:** llm_suggested_approved
- **Given:** The no-execute rule is triggered while the Platform Administrator is not logged in.
- **When:** The Platform Administrator subsequently logs in.
- **Then:** The in-app alert is present and visible; it has not expired; the audit log entry for the event exists.

#### TS-FR022-happy: No-execute rule violation triggers in-app alert to Platform Administrator and audit log entry

- **Kind:** happy
- **Source:** llm_suggested_approved
- **Given:** The no-execute rule is triggered on a connected information source.
- **When:** The violation is detected.
- **Then:** An in-app alert is delivered to the Platform Administrator and a corresponding entry appears in the audit log recording the event.

#### TS-FR022-persist: No-execute alert persists and is visible to Platform Administrator on next login

- **Kind:** edge
- **Source:** llm_suggested_approved
- **Given:** The no-execute rule is triggered while the Platform Administrator is not logged in.
- **When:** The Platform Administrator subsequently logs in.
- **Then:** The in-app alert is present and visible; it has not expired; the audit log entry for the event exists.

### FR-027

#### TS-019: Verify that a Platform Administrator can successfully promote a Platform Administrator-created information source to platform-level shared status.

- **Kind:** happy
- **Source:** user_stated
- **Given:** A Platform Administrator is authenticated and an information source exists that was created by a Platform Administrator.
- **When:** The Platform Administrator designates that information source as platform-level shared.
- **Then:** The resource is marked as platform-level shared and appears in read-only mode for all Organization Administrators and Content Managers.

### NFR-001

#### TS-NFR001-1: Explicit save confirmation after reviewing LLM FAQ candidates — only approved entries written to database

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user has reviewed LLM-generated FAQ candidates and explicitly confirms save.
- **When:** The confirmation is submitted.
- **Then:** Only the approved entries are written to the FAQ database; no unapproved candidates are persisted.

#### TS-NFR001-2: Review session ends without explicit save — no FAQ entries auto-saved

- **Kind:** negative
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user has reviewed LLM-generated FAQ candidates but does not confirm save.
- **When:** The review session ends.
- **Then:** No FAQ entries are written to the database; all candidates are discarded or remain in pending state only.

#### TS-NFR001-happy: Explicit save confirmation — only approved FAQ candidates written to database

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user has reviewed LLM-generated FAQ candidates and explicitly confirms save.
- **When:** The confirmation is submitted.
- **Then:** Only the approved entries are written to the FAQ database; no unapproved candidates are persisted.

#### TS-NFR001-no-save: Review session ends without explicit save — no FAQ entries auto-saved

- **Kind:** negative
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authorized user has reviewed LLM-generated FAQ candidates but does not confirm save.
- **When:** The review session ends.
- **Then:** No FAQ entries are written to the database; all candidates are discarded or remain in pending state only.

### NFR-002

#### TS-NFR002-provider-selection: Platform Administrator selects LLM provider and API key — all subsequent calls use that provider without code change

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A Platform Administrator accesses the chassis API configuration UI and selects an LLM provider and enters an API key.
- **When:** The configuration is saved.
- **Then:** All subsequent LiteLLM-routed calls use that provider and key without requiring any application code change.

#### TS-NFR002-no-direct-call: Application routes LLM call via LiteLLM — no direct provider API call made

- **Kind:** negative
- **Source:** llm_suggested_approved
- **Given:** The application receives an LLM call request.
- **When:** The request is routed.
- **Then:** The call is made via the chassis LiteLLM integration; no direct provider API call is made by the application.

### SR-001

#### TS-003: Verify that GitHub PATs, OAuth tokens, and MCP Server credentials are stored in FIPS-compliant encrypted form in the database and are not retrievable as plaintext.

- **Kind:** happy
- **Source:** llm_suggested_approved
- **Given:** A Content Manager or Platform Administrator configures an information source and provides credentials (GitHub PAT, OAuth token, or MCP Server credential).
- **When:** The credentials are saved.
- **Then:** The stored value in the database is encrypted at rest using a FIPS 140-2 or FIPS 140-3 validated algorithm and cannot be read as plaintext by querying the database directly.

### SR-002

#### TS-001: Verify that when an End User submits a question, the system sanitizes the payload sent to the external LLM API (no PII, no source code) and returns a valid answer.

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An End User is authenticated and has access to at least one configured information source.
- **When:** The End User submits a question through the assistant interface.
- **Then:** The system forwards a sanitized request to the LLM API (containing no PII or source code), receives a response, and displays the answer to the End User.

#### TS-002: Verify that if a user's question input contains PII (e.g. a name or email address), the system strips that data before sending the payload to the external LLM API.

- **Kind:** negative
- **Source:** llm_suggested_approved
- **Given:** An End User is authenticated and submits a question that includes identifiable personal information.
- **When:** The system prepares the LLM API request.
- **Then:** The outbound payload contains no PII and no source code; the sanitized question is sent and the user receives a response without error.

#### TS-012: Verify that when the external LLM API is unreachable, the system handles the failure gracefully and presents an appropriate error message to the End User without exposing internal details.

- **Kind:** failure
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An End User is authenticated and the external LLM API is unavailable.
- **When:** The End User submits a question.
- **Then:** The system returns a user-friendly error message indicating the service is temporarily unavailable; no internal system details or credentials are exposed.

#### TS-SR002-clean-pass: Clean question with no PII or source code is forwarded to LLM API successfully

- **Kind:** happy
- **Source:** llm_suggested_approved
- **Given:** An End User submits a question containing no PII and no source code.
- **When:** The system prepares the LLM API request.
- **Then:** The request is forwarded to the external LLM API and the user receives a response.

### SR-003

#### TS-005: Verify that an End User can access their own interaction logs and that the logs contain their session data only.

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** Two End Users have each asked questions and interaction logs exist for both.
- **When:** End User A requests their interaction logs.
- **Then:** Only logs belonging to End User A are returned; no entries from End User B are visible.

#### TS-007: Verify that a Platform Administrator can view interaction logs across users but cannot modify or delete log entries.

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A Platform Administrator is authenticated and interaction logs exist for multiple users.
- **When:** The Platform Administrator navigates to the interaction logs section.
- **Then:** All logs are displayed in read-only mode; no edit, delete, or alter controls are available or functional.

#### TS-SR003-admin-readonly: Platform Administrator views interaction logs in read-only mode with no edit or delete controls

- **Kind:** happy
- **Source:** llm_suggested_approved
- **Given:** A Platform Administrator is authenticated and interaction logs exist for multiple users.
- **When:** The Platform Administrator navigates to the interaction logs section.
- **Then:** All logs are displayed in read-only mode; no edit, delete, or alter controls are present or functional.

### SR-004

#### TS-009: Verify that when the no-execute rule is triggered on a connected information source, the Platform Administrator receives an in-app alert and the event is recorded in the audit log.

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A connected information source has a no-execute rule configured and the Platform Administrator is authenticated.
- **When:** The no-execute rule condition is met on the information source.
- **Then:** An in-app alert is delivered to the Platform Administrator and a corresponding entry appears in the audit log recording the event.

#### TS-010: Verify that the in-app alert for a no-execute rule event is queued and visible to the Platform Administrator upon their next login or return to the application.

- **Kind:** edge
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** The no-execute rule is triggered while the Platform Administrator is not logged in or is on a different screen.
- **When:** The Platform Administrator logs in or returns to the application.
- **Then:** The in-app alert is present and visible, and the audit log entry for the event exists.

#### TS-SR004-alert-persist: No-execute alert persists and is visible to Platform Administrator on next login

- **Kind:** edge
- **Source:** user_stated
- **Given:** The no-execute rule is triggered while the Platform Administrator is not logged in.
- **When:** The Platform Administrator subsequently logs in.
- **Then:** The in-app alert is present and visible; the audit log entry for the event exists.

#### TS-SR004-happy: No-execute rule violation triggers in-app alert and audit log entry

- **Kind:** happy
- **Source:** llm_suggested_approved
- **Given:** A connected information source has the no-execute rule active.
- **When:** The no-execute rule condition is met.
- **Then:** An in-app alert is delivered to the Platform Administrator and a corresponding audit log entry is created.

### SR-005

#### TS-SR005-happy: System reads code from a connected source as plain text context without executing it

- **Kind:** happy
- **Source:** user_stated
- **Given:** A connected information source contains executable code (e.g., a Python script).
- **When:** The system reads the source to answer a user question.
- **Then:** The code is used as read-only context only; no interpreter or runtime is invoked; no code is executed.

### SR-006

#### TS-SR006-1: Tier 2 LLM fallback call payload contains no PII and no source code

- **Kind:** happy
- **Source:** llm_suggested_approved
- **Given:** The system prepares a Tier 2 LLM fallback call.
- **When:** The request payload is assembled.
- **Then:** The payload contains no PII (names, email addresses, user IDs) and no source code; the call proceeds to the LLM API.

#### TS-SR006-2: Automated FAQ generation LLM call payload contains no PII and no source code

- **Kind:** happy
- **Source:** llm_suggested_approved
- **Given:** The system prepares an automated FAQ generation LLM call.
- **When:** The request payload is assembled.
- **Then:** The payload contains no PII and no source code.

#### TS-SR006-tier2-clean: Tier 2 LLM fallback call payload contains no PII and no source code

- **Kind:** happy
- **Source:** llm_suggested_approved
- **Given:** The system prepares a Tier 2 LLM fallback call.
- **When:** The request payload is assembled.
- **Then:** The payload contains no PII (names, email addresses, user IDs) and no source code; the call proceeds to the LLM API.

#### TS-SR006-faq-gen-clean: Automated FAQ generation LLM call payload contains no PII and no source code

- **Kind:** happy
- **Source:** llm_suggested_approved
- **Given:** The system prepares an automated FAQ generation LLM call.
- **When:** The request payload is assembled.
- **Then:** The payload contains no PII and no source code.

### SR-007

#### TS-SR007-1: Authenticated End User requests their own interaction logs — only their records returned

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authenticated End User requests their own interaction logs.
- **When:** The system evaluates the access request.
- **Then:** Only log records belonging to that user are returned; no other user's data is disclosed.

#### TS-SR007-3: Platform Administrator views interaction logs — read-only mode with no alter controls

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A Platform Administrator is authenticated and interaction logs exist.
- **When:** The Platform Administrator views the interaction logs.
- **Then:** Logs are presented in read-only mode with no edit, delete, or alter controls available.

#### TS-SR007-own-logs: Authenticated End User requests their own interaction logs — only their records returned

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An authenticated End User requests their own interaction logs.
- **When:** The system evaluates the access request.
- **Then:** Only log records belonging to that user are returned; no other user's data is disclosed.

#### TS-SR007-admin-readonly: Platform Administrator views interaction logs — read-only mode with no alter controls

- **Kind:** happy
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A Platform Administrator is authenticated and interaction logs exist.
- **When:** The Platform Administrator views the interaction logs.
- **Then:** Logs are presented in read-only mode with no edit, delete, or alter controls available.
## 4. PERSISTENCE TEST SCENARIOS (SQLALCHEMY)
*Pending — system-derived from DESIGN.md#5. PERSISTENCE & DATA ACCESS (SQLALCHEMY)*

## 5. INTEGRATION TEST SCENARIOS (APPLICATION ↔ EXTERNAL SERVICES)
*Pending — system-derived from DESIGN.md#6. INTEGRATION LAYER (APPLICATION → EXTERNAL SERVICES)*

## 6. SECURITY & FAILURE TESTS (MANDATORY)
### FR-001

#### TS-FR001-2: Unauthenticated user is redirected to login — no assistant content shown

- **Kind:** security
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An unauthenticated user attempts to open the assistant via the desktop icon or embedded HTML link.
- **When:** The window loads.
- **Then:** The user is redirected to the login page and no assistant content is displayed.

#### TS-FR001-unauth: Unauthenticated user attempts to open assistant — redirected to login

- **Kind:** security
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** An unauthenticated user attempts to open the assistant via the desktop icon or embedded HTML link.
- **When:** The window loads.
- **Then:** The user is redirected to the login page and no assistant content is displayed.

### FR-009

#### TS-FR009-2: End User denied access to LLM fallback configuration

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** An End User is authenticated.
- **When:** They attempt to access the LLM fallback configuration.
- **Then:** The system denies access and returns an authorization error.

### FR-010

#### TS-FR010-3: End User denied access to information source category creation

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** An End User is authenticated.
- **When:** They attempt to create an information source category.
- **Then:** The system denies access and returns an authorization error.

### FR-012

#### TS-FR012-4: Executable code in connected source is never executed during access test

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** A connected source contains executable code (e.g., a Python script).
- **When:** The system performs the read access test.
- **Then:** The code is treated as read-only context; no interpreter or runtime is invoked; no code is executed.

### FR-013

#### TS-FR013-4: Executable code in GitHub repo is never executed during access test

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** The GitHub repository contains executable code.
- **When:** The system performs the read access test.
- **Then:** The code is treated as read-only context; no interpreter or runtime is invoked; no code is executed.

### FR-015

#### TS-FR015-3: End User denied access to question category creation

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** An End User is authenticated.
- **When:** They attempt to create a question category.
- **Then:** The system denies access and returns an authorization error.

### FR-016

#### TS-FR016-3: End User denied access to FAQ creation

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** An End User is authenticated.
- **When:** They attempt to create an FAQ.
- **Then:** The system denies access and returns an authorization error.

#### TS-FR016-end-user-blocked: End User denied access to FAQ creation

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** An End User is authenticated.
- **When:** They attempt to create an FAQ.
- **Then:** The system denies access and returns an authorization error.

### FR-017

#### TS-FR017-3: End User denied access to automated FAQ generation trigger

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** An End User is authenticated.
- **When:** They attempt to trigger automated FAQ generation.
- **Then:** The system denies access and returns an authorization error.

#### TS-FR017-end-user-blocked: End User denied access to automated FAQ generation trigger

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** An End User is authenticated.
- **When:** They attempt to trigger automated FAQ generation.
- **Then:** The system denies access and returns an authorization error.

### FR-018

#### TS-FR018-3: End User denied access to automated FAQ generation from information source

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** An End User is authenticated.
- **When:** They attempt to trigger automated FAQ generation from an information source.
- **Then:** The system denies access and returns an authorization error.

#### TS-FR018-end-user-blocked: End User denied access to automated FAQ generation from information source

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** An End User is authenticated.
- **When:** They attempt to trigger automated FAQ generation from an information source.
- **Then:** The system denies access and returns an authorization error.

### FR-019

#### TS-FR019-2: Attempt to change or delete a submitted rating is rejected

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** An End User has submitted a thumbs up rating on a response.
- **When:** Any user or administrator attempts to change or delete that rating via the UI or API.
- **Then:** The system rejects the operation and returns an authorization error; the original rating remains unchanged.

#### TS-FR019-immutable: Attempt to change or delete a submitted rating is rejected

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** An End User has submitted a thumbs up rating on a response.
- **When:** Any user or administrator attempts to change or delete that rating via the UI or API.
- **Then:** The system rejects the operation and returns an authorization error; the original rating remains unchanged.

### FR-020

#### TS-FR020-2: Organization Administrator attempts to edit a platform-level shared resource — denied

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** An Organization Administrator is authenticated and views a platform-level shared information source.
- **When:** They attempt to edit or delete it.
- **Then:** The system denies the action and returns an authorization error; the resource remains unchanged.

#### TS-FR020-3: Content Manager views platform-level shared resources — read-only, no edit or delete controls

- **Kind:** security
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A Content Manager is authenticated.
- **When:** They view the platform-level shared resources list.
- **Then:** The resources are visible in read-only mode with no edit or delete controls presented.

#### TS-FR020-org-admin-blocked: Organization Administrator attempts to edit a platform-level shared resource — denied

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** An Organization Administrator is authenticated and views a platform-level shared information source.
- **When:** They attempt to edit or delete it.
- **Then:** The system denies the action and returns an authorization error; the resource remains unchanged.

#### TS-FR020-content-mgr-readonly: Content Manager views platform-level shared resources — read-only, no edit or delete controls

- **Kind:** security
- **Browser end-to-end:** yes — this scenario is performed by a user in a browser
- **Source:** llm_suggested_approved
- **Given:** A Content Manager is authenticated.
- **When:** They view the platform-level shared resources list.
- **Then:** The resources are visible in read-only mode with no edit or delete controls presented.

### FR-021

#### TS-FR021-3: Content Manager denied access to administrator interaction log view

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** A Content Manager is authenticated.
- **When:** They attempt to access the administrator interaction log view.
- **Then:** The system denies access and returns an authorization error.

#### TS-FR021-4: End User denied access to administrator interaction log view

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** An End User is authenticated.
- **When:** They attempt to access the administrator interaction log view.
- **Then:** The system denies access and returns an authorization error.

#### TS-FR021-content-mgr-blocked: Content Manager denied access to administrator interaction log view

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** A Content Manager is authenticated.
- **When:** They attempt to access the administrator interaction log view.
- **Then:** The system denies access and returns an authorization error.

#### TS-FR021-end-user-blocked: End User denied access to administrator interaction log view

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** An End User is authenticated.
- **When:** They attempt to access the administrator interaction log view.
- **Then:** The system denies access and returns an authorization error.

### FR-022

#### TS-FR022-3: Attempt to alter or delete audit log entry for a no-execute event is rejected

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** A no-execute rule violation has been logged to the audit log.
- **When:** Any user attempts to alter or delete that audit log entry via the UI or API.
- **Then:** The system rejects the operation and returns an authorization error; the audit log entry remains unchanged.

#### TS-FR022-audit-immutable: Attempt to alter or delete audit log entry for a no-execute event is rejected

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** A no-execute rule violation has been logged to the audit log.
- **When:** Any user attempts to alter or delete that audit log entry via the UI or API.
- **Then:** The system rejects the operation and returns an authorization error; the audit log entry remains unchanged.

### FR-025

#### TS-014: Verify that an Organization Administrator cannot access data belonging to a different organization.

- **Kind:** security
- **Source:** user_stated
- **Given:** An Organization Administrator for Org A is authenticated and data exists for Org B.
- **When:** The Organization Administrator attempts to access Org B's users, sources, or FAQ entries.
- **Then:** The system returns an authorization error and no Org B data is disclosed.

#### TS-015: Verify that a Content Manager can view platform-shared resources in read-only mode but cannot edit or delete them.

- **Kind:** security
- **Source:** user_stated
- **Given:** A Content Manager is authenticated and a platform-shared Information Source Category exists.
- **When:** The Content Manager views the Information Source Categories list.
- **Then:** The platform-shared category is visible with no edit or delete controls available.

### FR-026

#### TS-016: Verify that a Platform Administrator cannot impersonate or act as another user.

- **Kind:** security
- **Source:** user_stated
- **Given:** A Platform Administrator is authenticated.
- **When:** An attempt is made to assume another user's identity via any UI or API pathway.
- **Then:** The system rejects the request and returns an authorization error; no impersonation occurs.

#### TS-017: Verify that an Organization Administrator cannot impersonate or act as another user.

- **Kind:** security
- **Source:** user_stated
- **Given:** An Organization Administrator is authenticated.
- **When:** An attempt is made to assume another user's identity via any UI or API pathway.
- **Then:** The system rejects the request and returns an authorization error; no impersonation occurs.

### FR-027

#### TS-018: Verify that a Platform Administrator cannot promote an org-created information source to platform-level shared status.

- **Kind:** security
- **Source:** user_stated
- **Given:** A Platform Administrator is authenticated and an information source exists that was created by an Organization Administrator.
- **When:** The Platform Administrator attempts to designate that information source as platform-level shared.
- **Then:** The system rejects the action and returns an authorization error; the resource remains organization-scoped.

### SR-001

#### TS-004: Verify that API endpoints that return information source configuration do not include plaintext credential values in the response body.

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** A Platform Administrator or Content Manager has previously saved credentials for an information source.
- **When:** An API request is made to retrieve the information source configuration.
- **Then:** The response does not include the plaintext credential value; at most a masked or omitted representation is returned.

### SR-002

#### TS-SR002-block-pii: Submission containing PII is blocked and user is prompted to rephrase

- **Kind:** security
- **Source:** user_stated
- **Given:** An End User submits a question containing a name or email address.
- **When:** The system evaluates the submission.
- **Then:** The submission is blocked; no LLM API request is made; an inline prompt asks the user to rephrase.

#### TS-SR002-block-code: Submission containing source code is blocked and user is prompted to rephrase

- **Kind:** security
- **Source:** user_stated
- **Given:** An End User submits a question containing a source code snippet.
- **When:** The system evaluates the submission.
- **Then:** The submission is blocked; no LLM API request is made; an inline prompt asks the user to rephrase.

### SR-003

#### TS-006: Verify that an End User cannot retrieve or view interaction logs that belong to a different user.

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** End User A and End User B are both authenticated; logs exist for both.
- **When:** End User A attempts to access End User B's interaction logs (e.g. by manipulating a log ID or user ID parameter).
- **Then:** The system returns an authorization error and no log data belonging to End User B is disclosed.

#### TS-008: Verify that Content Manager and Organization Administrator roles cannot access interaction logs belonging to other users.

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** A Content Manager is authenticated; interaction logs exist for End Users.
- **When:** The Content Manager attempts to access the interaction logs listing for all users.
- **Then:** The system denies access and returns an authorization error; no other user's log data is returned.

#### TS-013: Verify that a Content Manager has no ability to alter, delete, or insert interaction log or audit log entries.

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** A Content Manager is authenticated.
- **When:** The Content Manager attempts to call any log modification endpoint directly.
- **Then:** The system returns an authorization error and the log data remains unchanged.

#### TS-SR003-unauth-access: End User attempts to access another user's interaction log — authorization error returned and in-app alert sent to Org Admin and Platform Admin

- **Kind:** security
- **Source:** user_stated
- **Given:** An End User is authenticated and attempts to access another user's interaction log by manipulating a record ID.
- **When:** The system evaluates the access request.
- **Then:** The system returns an authorization error, discloses no data belonging to the other user, and sends an in-app alert to the requesting user's Organization Administrator and to the Platform Administrator.

#### TS-SR003-content-mgr-blocked: Content Manager is denied access to the administrator interaction log view

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** A Content Manager is authenticated.
- **When:** The Content Manager attempts to access the administrator interaction log view.
- **Then:** The system returns an authorization error and no log data is displayed.

#### TS-SR003-immutability: Any attempt to modify or delete an interaction log entry is rejected

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** Any authenticated user attempts to modify or delete an interaction log entry via the UI or API.
- **When:** The operation is submitted.
- **Then:** The system rejects the operation and returns an authorization error; the log record remains unchanged.

### SR-004

#### TS-011: Verify that an Organization Administrator does not have access to the platform-level audit log that records no-execute rule events.

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** An Organization Administrator is authenticated and a no-execute event has been logged.
- **When:** The Organization Administrator attempts to access the audit log.
- **Then:** The system denies access and returns an authorization error; the audit log is not displayed.

#### TS-SR004-org-admin-blocked: Organization Administrator is denied access to the platform-level audit log

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** An Organization Administrator is authenticated and a no-execute event has been logged.
- **When:** The Organization Administrator attempts to access the audit log.
- **Then:** The system denies access and returns an authorization error; the audit log is not displayed.

### SR-005

#### TS-SR005-injection: Injection attack via connected source — adversarial payload does not cause code execution

- **Kind:** security
- **Source:** user_stated
- **Given:** A connected information source contains content crafted to trigger code execution via injection (shell command, eval expression, script tag, or LLM prompt injection instructing the system to run code).
- **When:** The system processes that source content.
- **Then:** The system reads the content as plain text only; no execution occurs; no side effects from the injected payload are observed in system state or outputs.

#### TS-SR005-multi-vector: Multiple injection vectors across source types — all blocked with no execution

- **Kind:** security
- **Source:** user_stated
- **Given:** An automated test submits connected sources containing known executable payloads across multiple injection vectors (shell commands, eval expressions, script tags, prompt injections) across all four source types.
- **When:** The system processes each payload.
- **Then:** In every case the system returns a read-only context response with no execution side effects; all injection vectors are blocked.

### SR-006

#### TS-SR006-3: Sanitization check identifies PII or source code — content stripped or call blocked before leaving system boundary

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** A sanitization check identifies PII or source code in an outbound LLM API payload.
- **When:** The check runs.
- **Then:** The content is stripped or the call is blocked before any data leaves the system boundary; no PII or source code reaches the external LLM API.

#### TS-SR006-strip-blocked: Sanitization check identifies PII or source code — content stripped or call blocked

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** A sanitization check identifies PII or source code in an outbound LLM API payload.
- **When:** The check runs.
- **Then:** The content is stripped or the call is blocked before any data leaves the system boundary; no PII or source code reaches the external LLM API.

### SR-007

#### TS-SR007-2: Any user attempts to modify or delete an interaction log entry — operation rejected

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** Any authenticated user attempts to modify or delete an interaction log entry via the UI or API.
- **When:** The operation is submitted.
- **Then:** The system rejects the operation and returns an authorization error; the log record remains unchanged.

#### TS-SR007-modify-blocked: Any user attempts to modify or delete an interaction log entry — operation rejected

- **Kind:** security
- **Source:** llm_suggested_approved
- **Given:** Any authenticated user attempts to modify or delete an interaction log entry via the UI or API.
- **When:** The operation is submitted.
- **Then:** The system rejects the operation and returns an authorization error; the log record remains unchanged.
## 7. TEST TRACEABILITY MATRIX (HARD REQUIREMENT)
| Requirement | Test scenarios |
|---|---|
| SR-001 | TS-003, TS-004 |
| SR-002 | TS-001, TS-002, TS-012, TS-SR002-block-code, TS-SR002-block-pii, TS-SR002-clean-pass |
| SR-003 | TS-005, TS-006, TS-007, TS-008, TS-013, TS-SR003-admin-readonly, TS-SR003-content-mgr-blocked, TS-SR003-immutability, TS-SR003-unauth-access |
| SR-004 | TS-009, TS-010, TS-011, TS-SR004-alert-persist, TS-SR004-happy, TS-SR004-org-admin-blocked |
| FR-001 | TS-FR001-1, TS-FR001-2, TS-FR001-3, TS-FR001-happy, TS-FR001-unauth |
| FR-002 | TS-FR002-1, TS-FR002-2, TS-FR002-3, TS-FR002-empty, TS-FR002-happy, TS-FR002-over-limit |
| FR-003 | TS-FR003-1, TS-FR003-2, TS-FR003-3, TS-FR003-empty-cat, TS-FR003-happy, TS-FR003-no-cats |
| FR-004 | TS-FR004-1, TS-FR004-2 |
| FR-005 | TS-FR005-1, TS-FR005-2 |
| FR-006 | TS-FR006-1, TS-FR006-2 |
| FR-007 | TS-FR007-1, TS-FR007-2 |
| FR-008 | TS-FR008-1, TS-FR008-2 |
| FR-009 | TS-FR009-1, TS-FR009-2 |
| FR-010 | TS-FR010-1, TS-FR010-2, TS-FR010-3 |
| FR-011 | TS-FR011-1, TS-FR011-2 |
| FR-012 | TS-FR012-1, TS-FR012-2, TS-FR012-3, TS-FR012-4 |
| FR-013 | TS-FR013-1, TS-FR013-2, TS-FR013-3, TS-FR013-4 |
| FR-014 | TS-FR014-1, TS-FR014-2, TS-FR014-3, TS-FR014-4 |
| FR-015 | TS-FR015-1, TS-FR015-2, TS-FR015-3 |
| FR-016 | TS-FR016-1, TS-FR016-2, TS-FR016-3, TS-FR016-end-user-blocked, TS-FR016-happy, TS-FR016-missing-fields |
| FR-017 | TS-FR017-1, TS-FR017-2, TS-FR017-3, TS-FR017-end-user-blocked, TS-FR017-happy, TS-FR017-no-save |
| FR-018 | TS-FR018-1, TS-FR018-2, TS-FR018-3, TS-FR018-end-user-blocked, TS-FR018-happy, TS-FR018-no-save |
| FR-019 | TS-FR019-1, TS-FR019-2, TS-FR019-3, TS-FR019-happy, TS-FR019-immutable, TS-FR019-null-rating |
| FR-020 | TS-FR020-1, TS-FR020-2, TS-FR020-3, TS-FR020-content-mgr-readonly, TS-FR020-happy, TS-FR020-org-admin-blocked |
| FR-021 | TS-FR021-1, TS-FR021-2, TS-FR021-3, TS-FR021-4, TS-FR021-content-mgr-blocked, TS-FR021-end-user-blocked, TS-FR021-org-admin-scoped, TS-FR021-plat-admin |
| SR-005 | TS-SR005-happy, TS-SR005-injection, TS-SR005-multi-vector |
| NFR-001 | TS-NFR001-1, TS-NFR001-2, TS-NFR001-happy, TS-NFR001-no-save |
| SR-006 | TS-SR006-1, TS-SR006-2, TS-SR006-3, TS-SR006-faq-gen-clean, TS-SR006-strip-blocked, TS-SR006-tier2-clean |
| SR-007 | TS-SR007-1, TS-SR007-2, TS-SR007-3, TS-SR007-admin-readonly, TS-SR007-modify-blocked, TS-SR007-own-logs |
| FR-022 | TS-FR022-1, TS-FR022-2, TS-FR022-3, TS-FR022-audit-immutable, TS-FR022-happy, TS-FR022-persist |
| CON-001 | TS-CON001-1, TS-CON001-2, TS-CON001-3, TS-CON001-litelm-routing, TS-CON001-no-direct-calls, TS-CON001-provider-config |
| CON-002 | TS-CON002-1, TS-CON002-2, TS-CON002-compliant-deploy, TS-CON002-noncompliant-rejected |
| CON-003 | TS-CON003-data-at-rest-us, TS-CON003-data-in-transit-us, TS-CON003-noncompliant-rejected |
| NFR-002 | TS-NFR002-no-direct-call, TS-NFR002-provider-selection |
| FR-023 | **none yet** |
| FR-024 | **none yet** |
| FR-025 | TS-014, TS-015 |
| FR-026 | TS-016, TS-017 |
| FR-027 | TS-018, TS-019 |
| CON-004 | TS-CON004-auth-failure, TS-CON004-rate-limit, TS-CON004-timeout |
| CON-005 | TS-CON005-github-auth, TS-CON005-github-timeout |
| CON-006 | TS-CON006-mcp-auth, TS-CON006-mcp-timeout |

**2 requirement(s) have no test scenario yet:** FR-023, FR-024
## 8. TEST EXECUTION RULES

When executing tests, the AI MUST:

- Run the scenarios selected by the **execution cadence** below, using `uv run pytest -q` from the project root.
- Use a throwaway test database (async SQLAlchemy fixtures), never the dev/prod database.
- Execute tests in dependency order.
- STOP code generation on first failure.
- Report failures with Requirement ID references.
- Enforce a minimum coverage threshold via `pytest --cov` (e.g. `pytest --cov=app --cov-report=term-missing --cov-fail-under=80`).


**Execution cadence (what runs, and when).** Every requirement's scenarios live in this document.
They do not all run on every build. Re-running the foundation suite on each incremental pass
re-proves something that did not change, and that cost is paid in wall-clock time and tokens on
**every single build**.

| Trigger | What runs |
|---|---|
| **Minor build** — an incremental code-generation pass; chassis version unchanged | The **project-specific** scenarios (§3–§6). The foundation is assumed green because nothing in it moved. |
| **Major build** — a release build, or the first build after a requirement change that touches foundation-adjacent behavior | **The entire document**, foundation scenarios included. |
| **Chassis baseline change** — the project moves to a new chassis version | **The entire document.** The foundation's assumptions have moved, so the previous green result no longer applies. |

Never skip a tier to save time on a release. The minor-build shortcut is sound **only** while the
foundation is genuinely unchanged; the moment the baseline moves, the full document is the plan.

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## 9. CODE GENERATION GATE

Code is considered VALID only if:

- `uv run pytest -q` passes with zero failures.
- No Requirement ID is skipped.
- Every requirement carries **both floors**: the Floor 1 gates above, AND the Floor 2
  `edge` / `failure` (/ `performance` where stated) scenarios its behavior demands. Floor 1
  alone does NOT satisfy this gate.
- Coverage meets or exceeds the configured threshold.
- No unauthorized logic execution occurs (no live external calls, no prod database access).
- `ruff check .` and `mypy --strict app` are clean.

---

*This document was generated by the SD-Agile Spec Builder from the project's Golden Record, on the autonomous-platform-chassis-python foundation.*
---

<!-- @owned-by:  | @role: system | @system-derives-from: CONSTITUTION.md | @locked-by-chassis: true -->
## Chassis Floor Scenarios (locked — L1)

The sections that follow are a **floor**: the scenarios that prove this chassis's locked
CONSTITUTION clauses. An application adds its own scenario sections freely, above, but may not
weaken or delete these — each is `@locked-by-chassis: true` and an edit is refused the same way an
edit to a locked constitution clause is.

**Why they are here and not only in the platform's database.** A locked section's identity comes from
its `##` heading, and the drift detector treats a section absent from both document versions as
nothing to check. A floor declared only as a database key, with no matching section in THIS document,
therefore enforces nothing at all — silently. These sections are the document half of that pair; the
database's `LockedSections["test_scenarios"]` keys are the slugs of the headings below, and a test
asserts the two agree.

**Two clauses are deliberately not given a floor scenario.** A locked scenario **cannot be
corrected**, so one with nothing assertable to say is a permanent liability: `overview` is
descriptive, and `coding_standards` is already enforced executably by the formatter, linter and
type-checker release gates.


<!-- @owned-by:  | @role: system | @system-derives-from: CONSTITUTION.md | @locked-by-chassis: true -->
## Auth (locked — chassis floor)
### Identity & Authentication (locked — proves the CONSTITUTION's auth clause)
- A registered user authenticating with the correct password receives a token; the stored credential is a bcrypt hash at the configured cost, and the plaintext password appears in NO response body and NO log line.
- A request to any protected route with no credential returns **401**, and with a syntactically valid but unsigned or expired token also **401** — never 200, and never 500.
- **IA-6 anti-enumeration:** an unknown email, a known email with the wrong password, and a known-but-inactive account produce responses that are identical in status, body and timing class. A test that asserts only the status has not checked this clause.
- Repeated failures lock the account at the configured threshold (AC-7) and a correct password during lockout still fails.

<!-- @owned-by:  | @role: system | @system-derives-from: CONSTITUTION.md | @locked-by-chassis: true -->
## RBAC (locked — chassis floor)
### Authorization (locked — proves the CONSTITUTION's RBAC clause)
- A caller holding a permission reaches the route it guards; a caller authenticated but WITHOUT it receives **403**, distinguishable from the unauthenticated **401**.
- Permissions are resolved from the registry, not from a hardcoded list at the call site: a permission removed from a caller's grants immediately denies, with no restart.
- The permission seed is idempotent — running it twice leaves the same rows, not duplicates.

<!-- @owned-by:  | @role: system | @system-derives-from: CONSTITUTION.md | @locked-by-chassis: true -->
## Multi-Tenancy (locked — chassis floor)
### Multi-Tenancy (locked — proves the CONSTITUTION's tenancy clause)
- A tenant-scoped READ for another organization's row returns exactly the shape a genuinely missing row returns (**404**, identical body) — not 403, which would confirm the row exists.
- **A tenant-scoped WRITE is scoped identically to the read, and both halves are asserted:** an administrator of organization A attempting to mutate a member of organization B is refused **404**, AND the target's state is unchanged afterwards. Asserting only the status passes against a handler that mutates and then refuses. Asserting only one verb passes against a guard placed on only one of them.
- The cross-tenant target is a member of a DIFFERENT organization, not an org-less user: a guard that merely tested "has any membership" would wrongly survive the org-less case.
- A tenant-scoped write stamps the organization from the resolved caller context, ignoring any organization supplied in the request payload.

<!-- @owned-by:  | @role: system | @system-derives-from: CONSTITUTION.md | @locked-by-chassis: true -->
## Audit (locked — chassis floor)
### Audit & Accountability (locked — proves the CONSTITUTION's audit clause)
- One privileged mutation produces exactly **one** audit row, carrying actor, organization, action, entity, client IP and a UTC timestamp. Not zero, and not two.
- A mutation that fails validation BEFORE the write produces **zero** audit rows — a refused action is not an audited action.
- Missing audit context logs a warning and does not abort: the underlying operation still succeeds and returns its result.
- Retention/archival moves rows older than the configured window without deleting them outright.

<!-- @owned-by:  | @role: system | @system-derives-from: CONSTITUTION.md | @locked-by-chassis: true -->
## Observability (locked — chassis floor)
### Observability (locked — proves the CONSTITUTION's observability clause)
- The liveness endpoint returns **200** whenever the process is up, performing NO dependency checks — it stays 200 with the database unreachable.
- The readiness endpoint returns **200** with a live datastore and **503** when it is unreachable, and it names the failing dependency. Proven with a deliberately broken connection string, not by mocking the check.
- The version endpoint reports the application version and the chassis version read from the chassis's own version file — never a literal duplicated into the test, which pins a snapshot rather than the invariant and fails on every intended bump.
- Every request carries a correlation id, echoed in the response and present on each log line for that request.

<!-- @owned-by:  | @role: system | @system-derives-from: CONSTITUTION.md | @locked-by-chassis: true -->
## Error Messages (locked — chassis floor)
### Standard Error Messages (locked — proves the CONSTITUTION's error-message clause)
- User-facing 4xx/5xx text comes from the single canonical source, so the same condition never produces two different wordings on two routes.
- No error response, at any status, discloses a stack trace, a SQL fragment, a file path, a dependency version or an internal identifier.
- The uniform-failure requirement above (IA-6) is realized by these messages: the three distinguishable authentication failures map to ONE message.

<!-- @owned-by:  | @role: system | @system-derives-from: CONSTITUTION.md | @locked-by-chassis: true -->
## Security Invariants (locked — chassis floor)
### Security Invariants (locked — proves the CONSTITUTION's security clause)
- No secret — signing key, provider key, database password, encryption key — appears in any log line, any error body, or any audit row, including at debug verbosity.
- Secrets at rest are encrypted with the configured AEAD; the ciphertext is not the plaintext and decryption with a wrong key FAILS rather than returning garbage.
- A placeholder or default secret REFUSES to boot in a production configuration. Proven by booting with the placeholder and asserting the refusal, not by reading the check.
- Every datastore access is parameterized: a value containing SQL metacharacters is stored and returned verbatim, changing no query's meaning.

<!-- @owned-by:  | @role: system | @system-derives-from: CONSTITUTION.md | @locked-by-chassis: true -->
## Technology Stack (locked — chassis floor)
### Technology Stack (locked — proves the CONSTITUTION's stack clause)
- The chassis version reported at runtime equals the chassis's own version file, and that file equals the platform's seed pin. The three must agree; CI enforces the last pair.
- Every dependency in `pyproject.toml` is exactly pinned and present in `uv.lock`; a resolution that differs from the lockfile is refused rather than silently accepted.
- No dependency outside the locked stack is reachable from application code: adding an import of an unlisted package fails the build or the forbidden-pattern scan, not review.

<!-- @owned-by:  | @role: system | @system-derives-from: CONSTITUTION.md | @locked-by-chassis: true -->
## Architectural Invariants (locked — chassis floor)
### Architectural Invariants (locked — proves the CONSTITUTION's invariants clause)
- A service module imports no framework request/response type: the dependency is one-directional, and a test that inspects the module's imports must fail when one is added.
- Persistence types are never returned directly over the API surface; a response body's field set is the declared transport type's, not the storage type's.
- Every timestamp crossing a boundary is UTC and carries its offset; a local-time value is a defect, not a formatting preference.

<!-- @owned-by:  | @role: system | @system-derives-from: CONSTITUTION.md | @locked-by-chassis: true -->
## Forbidden Patterns (locked — chassis floor)
### Forbidden Patterns (locked — proves the CONSTITUTION's forbidden-pattern clause)
- Each forbidden pattern is detected in application code by the real scan, and the scan REFUSES rather than warning. Proven by introducing one instance of each pattern and asserting the refusal names it.
- The scan does not fire on the same text inside a comment or a string that documents the prohibition — otherwise the prohibition cannot be written down.

<!-- @owned-by:  | @role: system | @system-derives-from: CONSTITUTION.md | @locked-by-chassis: true -->
## Extension Model (locked — chassis floor)
### Extension Model (locked — proves the CONSTITUTION's extension clause)
- Every extension point named in the CONSTITUTION exists in the file it names, at the exact marker text. A renamed or absent marker REFUSES the registration rather than appending the insertion somewhere plausible.
- A registration's own symbols are verified to exist in the file it lands in, not merely the marker: an insertion referencing an identifier that file does not define is a deterministic failure and must be refused before it is written.
- Application code confines itself to the application's own area plus those markers; a write anywhere else in the foundation is refused.
- The application-dependency rules are in a LOCKED section and the dependency table is the only extensible one. A section declared both locked and extensible is refused by name, not resolved by picking one reading.

<!-- @owned-by:  | @role: system | @system-derives-from: CONSTITUTION.md | @locked-by-chassis: true -->
## NFR Baselines (locked — chassis floor)
### NFR Baselines (locked — proves the CONSTITUTION's NFR clause)
- The rate limiter admits requests up to the configured threshold and refuses the next one with the documented status, counted per client rather than globally.
- A baseline is a MINIMUM: a test asserting a threshold must fail when the configured value is lowered below the baseline, so the assertion cannot be satisfied by weakening the configuration.

<!-- @owned-by:  | @role: system | @system-derives-from: CONSTITUTION.md | @locked-by-chassis: true -->
## State Handling (locked — chassis floor)
### State Handling (locked — proves the CONSTITUTION's state clause)
- Only the declared transitions are accepted; an undeclared transition is refused and leaves the prior state intact.
- A transition into a terminal state requires its documented justification and is refused without it.
- Concurrent attempts to transition the same entity resolve to one winner, with the loser refused rather than silently overwritten.

<!-- @owned-by:  | @role: system | @system-derives-from: CONSTITUTION.md | @locked-by-chassis: true -->
## Frontend Responsive (locked — chassis floor)
### Frontend & Accessibility (locked — proves the CONSTITUTION's frontend clause)
- Every interactive control is a real semantic control with an accessible name; a click target that is a plain container with a handler is a defect.
- Every form field has a programmatically associated label, and dynamic regions announce their updates.
- The rendered page has no horizontal overflow at phone width, and no control is smaller than the documented minimum target size.

