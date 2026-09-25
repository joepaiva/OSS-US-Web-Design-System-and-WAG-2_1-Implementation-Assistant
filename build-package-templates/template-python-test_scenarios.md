---
template: python-test_scenarios
version: "3.0"
document_type: TEST-SCENARIOS.md
locked_section_aware: true
---

# {{PROJECT_NAME}} — Test Scenarios
<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## Platform Chassis — AI-Executable Test Specification (Python 3.12 · pytest · httpx ASGI)

**Project:** {{PROJECT_NAME}}
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

{{#PYTEST_TEST_SCENARIOS}}
### TS-{{ID}}: {{TITLE}}

**Test Level:** UNIT | INTEGRATION | END-TO-END

**Scenario Kind:** `happy | edge | negative | failure | security | performance`

**Source Requirement ID:** {{REQUIREMENT_ID}}

**Target Component:** Router | Service | Model | Schema

**Test File:** `app/slots/{{DOMAIN}}/tests/test_{{MODULE}}.py`

**Description:**
{{DESCRIPTION}}

**Preconditions:**
{{#PRECONDITIONS}}
- {{ITEM}}
{{/PRECONDITIONS}}

**Test Steps:**
{{#STEPS}}
1. {{STEP}}
{{/STEPS}}

**Example (pytest + httpx ASGI client):**
```python
import pytest


@pytest.mark.asyncio
async def test_{{ID}}(async_client):
    response = await async_client.{{HTTP_METHOD}}("{{ENDPOINT}}", json={{REQUEST_BODY}})
    assert response.status_code == {{EXPECTED_STATUS}}
    body = response.json()
    assert body{{JSON_ASSERTION}}
```

**Expected Result:**
{{EXPECTED_RESULT}}

**Failure Conditions:**
- {{FAILURE_CONDITIONS}}

---
{{/PYTEST_TEST_SCENARIOS}}

---

<!-- @owned-by:  | @role: system | @system-derives-from: DESIGN.md#5. PERSISTENCE & DATA ACCESS (SQLALCHEMY) | @locked-by-chassis: false -->
## 4. PERSISTENCE TEST SCENARIOS (SQLALCHEMY)

This section is REQUIRED if any persistent models exist.

{{#SQLALCHEMY_TEST_SCENARIOS}}
### TS-DB-{{ID}}: {{TITLE}}

**Test Level:** DATA | INTEGRATION

**Source Requirement ID:** {{REQUIREMENT_ID}}

**Target Model:** {{MODEL_NAME}}

**Test File:** `app/slots/{{DOMAIN}}/tests/test_{{MODULE}}_persistence.py`

**Fixtures:**
- `db_session` — an **async** SQLAlchemy `AsyncSession` bound to a throwaway test database
- a bound current-org context var so the `TenantScoped` auto-filter (`do_orm_execute`) / auto-stamp (`before_flush`) apply; seed data committed before assertions, rolled back after

**Test Steps:**
{{#STEPS}}
1. {{STEP}}
{{/STEPS}}

**Example (pytest-asyncio + AsyncSession):**
```python
import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_{{ID}}(db_session):
    record = {{MODEL_NAME}}({{MODEL_FIELDS}})  # org_id auto-stamped for TenantScoped
    db_session.add(record)
    await db_session.commit()

    result = await db_session.execute(
        select({{MODEL_NAME}}).where({{FILTER}})
    )
    fetched = result.scalar_one()
    assert fetched.{{FIELD}} == {{EXPECTED_VALUE}}
```

**Expected Result:**
- Row persisted/updated/deleted as specified
- Schema and constraints (nullability, FK, unique) enforced
- Alembic migration head matches model metadata (`alembic check` / `--autogenerate` produces no diff)

**Failure Conditions:**
- {{FAILURE_CONDITIONS}}

---
{{/SQLALCHEMY_TEST_SCENARIOS}}

---

<!-- @owned-by:  | @role: system | @system-derives-from: DESIGN.md#6. INTEGRATION LAYER (APPLICATION → EXTERNAL SERVICES) | @locked-by-chassis: false -->
## 5. INTEGRATION TEST SCENARIOS (APPLICATION ↔ EXTERNAL SERVICES)

{{#INTEGRATION_TEST_SCENARIOS}}
### TS-INT-{{ID}}: {{TITLE}}

**Provider:** {{PROVIDER}}

**Source Requirement ID:** {{REQUIREMENT_ID}}

**Endpoint / API:** {{ENDPOINT}}

**Test File:** `app/slots/{{DOMAIN}}/tests/test_integration_{{MODULE}}.py`

**Description:**
{{DESCRIPTION}}

**Preconditions:**
- The external `httpx` call is mocked via `respx` (or replayed from a recorded cassette); never a live endpoint
- Credentials supplied through test config/fixtures (never live secrets); LLM-shaped calls inject a fake `LLMTransport` via `app.llm.transport.set_transport(...)`

**Test Steps:**
{{#STEPS}}
1. {{STEP}}
{{/STEPS}}

**Example (pytest + respx mock):**
```python
import httpx
import respx


@respx.mock
@pytest.mark.asyncio
async def test_{{ID}}(async_client):
    respx.{{HTTP_METHOD}}("{{ENDPOINT}}").mock(
        return_value=httpx.Response({{MOCK_STATUS}}, json={{MOCK_BODY}})
    )
    response = await async_client.{{APP_METHOD}}("{{APP_ENDPOINT}}")
    assert response.status_code == {{EXPECTED_STATUS}}
```

**Expected Result:**
{{EXPECTED_RESULT}}

**Error Handling Validation:**
- Timeout behavior (`httpx.TimeoutException`)
- Retry behavior
- Error mapping (upstream status → application error response, canonical `error_messages.py` catalog)

---
{{/INTEGRATION_TEST_SCENARIOS}}

---

<!-- @owned-by: phase5b_security_requirements | @role: tech | @system-derives-from: CONSTITUTION.md#8. SECURITY (MANDATORY), REQUIREMENTS.md#5. NON-FUNCTIONAL REQUIREMENTS (NFR) (Category: Security), DESIGN.md#5B. SECURITY DESIGN (APPLICATION-SPECIFIC) | @locked-by-chassis: false -->
## 6. SECURITY & FAILURE TESTS (MANDATORY)

{{#SECURITY_TESTS}}
### TS-SEC-{{ID}}: {{TITLE}}

**Source Requirement ID:** {{REQUIREMENT_ID}}

**Scenario Type:** Authorization | Authentication | Input Validation | Multi-Tenant Isolation | Rate Limiting | Field Encryption | Audit | Dependency Failure | Timeout | Partial Write / Rollback

**Test File:** `app/slots/{{DOMAIN}}/tests/test_security_{{MODULE}}.py`

**Description:**
{{DESCRIPTION}}

**Test Steps:**
{{#STEPS}}
1. {{STEP}}
{{/STEPS}}

**Example (pytest + httpx — authz / isolation / validation):**
```python
@pytest.mark.asyncio
async def test_{{ID}}_forbidden(async_client, other_tenant_token):
    # Wrong role or wrong tenant must be rejected
    response = await async_client.get(
        "{{ENDPOINT}}",
        headers={"Authorization": f"Bearer {other_tenant_token}"},
    )
    assert response.status_code in (401, 403, 404)


@pytest.mark.asyncio
async def test_{{ID}}_invalid_payload(async_client, auth_token):
    # Pydantic validation failure must return 422
    response = await async_client.post(
        "{{ENDPOINT}}",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={{INVALID_BODY}},
    )
    assert response.status_code == 422
```

**Expected Result:**
{{EXPECTED_RESULT}}

---
{{/SECURITY_TESTS}}

---

<!-- @owned-by:  | @role: system | @system-derives-from: TEST-SCENARIOS.md#3. APPLICATION TEST SCENARIOS (PYTEST), REQUIREMENTS.md#3. FUNCTIONAL REQUIREMENTS (FR) | @locked-by-chassis: false -->
## 7. TEST TRACEABILITY MATRIX (HARD REQUIREMENT)

| Test ID | Requirement ID | Task ID | Test Level | Target | Test File |
|---------|----------------|---------|------------|--------|-----------|

Every Requirement ID MUST appear ≥1 time.

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
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
