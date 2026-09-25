# Python-FastAPI Chassis — TEST-SCENARIOS

**Version:** 1.4.1
**Date:** 2026-09-18
**Status:** Authoritative
**Chassis version:** 1.1.0 (Chassis Program pilot: `python-fastapi-mt-fisma-moderate-llm`, forked from the reference chassis at v0.10.0)

> Maps each capability to its verifying scenarios and the automated tests that implement them. The suite under `tests/` is the executable specification: **203 tests, all passing** at v0.10.0 (`uv run pytest -q`). Reference slot tests under `app/slots/*/tests/` add ~19 more (run separately). A chassis is conformant only when every TS group below is green. "Tests are requirements" (CONSTITUTION §4): fix the code, never weaken a test.

Conventions verified across protected endpoints: **401** unauthenticated · **403** authenticated-but-unauthorized · **404** cross-tenant (never 403, to avoid existence disclosure) · **422** invalid input.

---

## TS-AUTH — Authentication (FR-AUTH) → `tests/test_auth.py`
- Register: success → 201 + token + cookie; duplicate email → 409; weak/short password → 422 (IA-5).
- Login: valid → 200 + token; wrong password / unknown email / inactive → 401 **uniform** (IA-6).
- `/auth/me`: with token → 200 profile (no `password_hash`); without → 401.
- Logout → 204, cookie cleared. Token accepted from both bearer header and cookie (FR-AUTH-6).

## TS-AC7 — Account Lockout (FR-AUTH-11) → `tests/test_ac7_lockout.py`
- 3 failures within 15 min → account locked; further attempts → 401 even with correct password while locked; lock rejects **before** password verify; retry-after surfaced; counters reset after the window / on success.

## TS-AC8 — System-Use Banner (FR-UI-6) → `tests/test_ac8_banner.py`
- Banner renders on `/auth/login` when `system_use_notification` set; suppressed entirely when empty.

## TS-RBAC — Authorization (FR-RBAC) → covered via `tests/test_orgs.py`, `tests/test_admin.py`, slot tests
- Superuser bypass; system-wide vs per-org grants; `requires(perm)` → 403 when missing; seeded `admin` (all) vs `user` (`users:read`,`orgs:read`); slot permission registration auto-seeds.

## TS-TEN — Multi-tenancy (FR-TEN) → `tests/test_orgs.py`
- Create org (creator becomes admin member; first membership is default); list member orgs; `GET/PUT /orgs/me` (switch restricted to member orgs, audited); auto org-filter on reads + auto org-stamp on writes; cross-tenant read → 404.

## TS-AUD / TS-AU3 / TS-AU11 — Audit (FR-AUD) → `tests/test_au3_ip_capture.py`, `tests/test_au11_archival.py` (+ asserts in service tests)
- `@audited` writes one row on success with action/actor/org/entity/details/IP/UTC-timestamp; AU-3 IP captured from `X-Forwarded-For` / peer; missing session → skip+warn, op still succeeds; AU-11 archival moves rows older than `audit_retention_days` to archive, idempotent, returns count.

## TS-HEALTH — Health probes (FR-OBS-1..3) → `tests/test_health.py`
- `/healthz` → 200 `{status:ok}`; `/readyz` → 200 ready when DB up (`checks.database=ok`), 503 degraded otherwise; `/version` → 200 semver (`version`==`chassis`).

## TS-SYSHEALTH — System Health page (FR-OBS-6) → `tests/test_system_health.py` (6)
- Anonymous → 303 login; regular user → 403; org admin → 403 (platform-only); platform admin → 200 showing version/env + DB "reachable"; Redis row present regardless of reachability; `gather_system_health` never raises; `_redact_host` strips credentials.

## TS-DOCS — In-app documentation (FR-DOC) → `tests/test_docs.py` (15)
- Anonymous → 303; regular user → 403; admin → 200 index lists docs; render of `security-self-audit` shows `<h1>` + "FISMA Moderate" + "AC-7"; unknown slug → 404; traversal-style slug never reads a file; markdown renderer escapes HTML, emits headings/lists/tables/code, restricts link schemes; registry has the 4 whitelisted docs.

## TS-LLM-CRYPTO — Key encryption + config (FR-LLM-1/7, FR-CFG-2) → `tests/test_llm_crypto.py` (9)
- Encrypt/decrypt round-trip; non-deterministic ciphertext; tamper → `DecryptionError`; malformed token → error; `mask` hides key; prod+default wrap key → `InsecureKeyError` at **use time** (boot still succeeds); prod+real key encrypts; non-hex / wrong-length key rejected at construction.

## TS-LLM-SVC — Resolution + transport (FR-LLM-3/4/6/9) → `tests/test_llm_service.py` (12)
- Org key preferred over shared; shared used only when `org_llm_access` grants (default deny → `LLMKeyUnavailable`); orgless caller uses shared; `set_key` deactivates prior active (one active per scope+provider); deactivated key not resolved; `list_keys` masks + scopes; `complete` injects resolved key into the (fake) transport; missing key → `LLMKeyUnavailable`; transport error propagates; input validation; `llm.key_set` audit row written.

## TS-LLM-ADMIN — LLM admin UI (FR-LLM-8) → `tests/test_llm_admin.py` (7)
- Anonymous → 303; regular user → 403; org admin adds/deactivates org key (stored encrypted, shown masked, plaintext never in HTML); org admin cannot set shared key (403) or access policy (403) and doesn't see those sections; platform admin sets shared key + grants/revokes per-org shared access.

## TS-FILES — File storage (FR-FILE) → `tests/test_files.py` (5)
- Upload→list→download→delete round-trip (sha256 matches, `X-Content-SHA256` + content-disposition on download); cross-org isolation (list excludes, download/delete → 404); size cap → 413; no-org caller → 400; unauthenticated → 401. (Storage redirected to a tmp dir in tests.)

## TS-NOTE — Notifications (FR-NOTE) → `tests/test_notifications.py` (7)
- `notify` + unread count; unknown level → info; mark-read + mark-all-read; foreign-user mark-read → None; API list/unread-count/read/read-all flow; user isolation (B can't see/modify A's; → 404); unauthenticated → 401.

## TS-RL — Rate limiting (FR-RL) → `tests/test_ratelimit.py` (4)
- Off by default (middleware not installed); over-limit → 429 + `Retry-After` (dev app + fake Redis); health endpoints exempt; Redis down → fail open (requests still 200).

## TS-REP — Reporting (FR-REP) → `tests/test_reports.py` (5)
- Anonymous → 303; regular user → 403; org admin → org-scoped report (no platform org-count card); platform admin → global report (org card shown); `gather_report` counts users/notifications (org scope) and audit total + top actions + orgs (platform scope).

## TS-ERR — Error handling + messages (FR-ERR) → `tests/test_error_handlers.py`, `tests/test_error_messages.py`
- Prod uncaught error → generic 500 + request id, no internals; dev → type/message surfaced; full error always logged. Canonical `STANDARD_MESSAGES` for 400/401/403/404/409/413/422/429/500/503; `message_for_status` + `ERR_*` aliases.

## TS-CFG — Secret hardening (FR-CFG-2) → `tests/test_jwt_secret_validator.py` (6)
- `jwt_secret` rejects placeholder markers in any env; rejects in-code dev default in prod only; accepts a real random secret in prod; min length enforced.

## TS-MAIL — Transactional mail (FR-MAIL) → `tests/test_mail.py`
- Console backend logs + returns delivery dict (dev); SMTP path selected by config; both return structured result.

## TS-TASKS — Background jobs (FR-JOB) → `tests/test_tasks.py`
- `enqueue` schedules a job; queue/worker wiring; foreground unaffected by job backend.

## TS-STATES — Page states (FR-UI-5) → `tests/test_states.py`
- `_states.html` macros render loading (`role=status`,`aria-live=polite`), empty (`--info`), error (`role=alert`,`--error`) with required attributes; error text drawn from canonical messages.

## TS-RESPONSIVE — Responsive UI (FR-UI-4, NFR-A11Y-1) → `tests/test_responsive.py`
- Representative viewports (e.g. 320×568, 768×1024, 1280×800): no horizontal scroll; USWDS grid usage; touch-target + input-font rules.

## TS-NFR — NFR baselines (NFR-*) → `tests/test_nfr_baselines.py`
- Asserts the chassis-locked baseline thresholds documented in `docs/NFR-BASELINES.md`.

## TS-SI12 — Retention (FR-RET) → `tests/test_si12_retainable.py`
- `RetainableFor.retained_until` semantics; retention is explicit (not silent delete); archival picks aged-out rows.

## TS-SLOT-CRUD / TS-SLOT-STATES — Reference slots (FR-EXT) → `tests/test_slots_example.py`, `app/slots/*/tests/`
- CRUD slot: happy-path, 401, 403, cross-org 404, 422. State-machine slot: guarded transitions, illegal transition → 409, terminal states.

## TS-ADM — Admin shell base (FR-ADM) → `tests/test_admin.py`
- Anonymous → 303; regular user → 403; org admin sees users not orgs; platform admin full; create user (dup → 409), deactivate/reactivate, cannot self-deactivate; create org (slug taken → 409).
- **An org-scoped admin cannot deactivate OR reactivate a user who is not a member of their own organization — the response is 404 (FR-TEN-7 parity: cross-scope reads as not-found, never 403, which would confirm the account exists), AND the target's `is_active` is unchanged.** Both halves are asserted: a test that checked only the status would pass against a handler that mutates first and refuses afterwards. Both verbs are asserted: a guard placed on only one of deactivate/reactivate is the likelier bug. The target is a member of a *different* org, not an orgless user — a guard that only tested "has any membership" would wrongly survive the orgless case. **This scenario was added after the gap it covers was found live in this package on 2026-09-17** (`POST /admin/users/<id>/deactivate` returned 303 and flipped `is_active` True→False for another tenant's member, while that same user was correctly absent from the acting admin's own `/admin/users` listing — the read scoping made the write gap invisible). FR-ADM-2 v1.1.0/v1.2.0 now states the write scope that was previously only implied.

## TS-MIGRATE — Migrations (FR-DB) → operational
- `alembic upgrade head` on a clean database builds every table; each migration has a reversible `downgrade`; additive-only (no edits to committed migrations). (CI/manual; tests build schema via `create_all`.)

---

## Chassis Program pilot additions (variant 3: MT, FISMA Moderate, LLM) — CP-B.1–CP-B.8

Everything below is specific to this package (`python-fastapi-mt-fisma-moderate-llm`), forked from the reference chassis above. Regression scenarios TS-CPB-1 through TS-CPB-5 were all found live via CP-B.8's mandatory real-browser Playwright pass, not by the unit/service-level test suite — each is recorded here per this project's Rule 13 ("record the exercised flow as a regression scenario") in addition to the unit-level regression test that was added alongside its fix.

### TS-MFA — Real TOTP MFA (IA-2(1)) → `tests/test_mfa.py`
- Enrollment (start/confirm, wrong code, double-start); login branch (MFA-enabled user gets a challenge, not a token); challenge verification (correct TOTP, wrong code, backup-code single-use); disable; backup-code regeneration; the privileged-account MFA mandate in `app/deps.py` (a superuser without MFA enrolled is blocked from every permission-gated action, not just admin-only ones).
- **Live-verified (CP-B.8):** a real superuser account was correctly 403'd on every permission-gated action until MFA was enrolled; `/auth/mfa/enroll` → real TOTP secret + backup codes; `/auth/mfa/enroll/confirm` with a locally-computed TOTP code → `mfa_enabled: true`; the same account then passed the permission gate for real.

### TS-SYSHEALTH — System Health (FR-SYSHEALTH) → `tests/test_system_health.py` (extended)
- DB/Redis/worker/LLM-proxy reachability, chassis version + startup timestamp, bounded check time, graceful per-dependency degradation.
- **Live-verified (CP-B.8):** `GET /admin/system-health` rendered real dependency rows (database reachable, redis reachable, worker/llm_proxy correctly reported unreachable for this isolated test deployment — no RQ worker process, no LLM proxy configured), overall status correctly "degraded," zero console errors.

### TS-PLATHEALTH — Platform Health (FR-PLATHEALTH) → `app/compliance/inventory/`
- Component inventory via this package's own `uv.lock`/`pip-audit`, currency vs. latest stable, vulnerability scan, fail-closed degradation on an unreachable advisory source, gated remediation (auto-apply off by default).
- **Live-verified (CP-B.8):** `GET /admin/platform-health` → "Run scan now" triggered a real `pip-audit` + PyPI-currency scan (~15s, genuinely ran, not mocked) → "Zero open vulnerabilities — 101 components scanned, 0 behind latest stable," a real component table (fastapi 0.141.1, cryptography 50.0.1, etc. — the actual CP-B.3 remediated pins), scan #1 recorded in scan history.

### TS-FISMAAUDIT — FISMA self-audit + report (FR-FISMAAUDIT) → `app/compliance/fisma_audit/`
- Runtime check registry against actual config/DB state (not documentation); four outcomes (pass/fail/not-applicable/operator-responsibility); consumes the FISMA-Moderate policy constants; advisory-only.
- **Live-verified (CP-B.8):** `GET /admin/fisma-audit` → "Run audit now" → real report: 6 pass · 2 fail · 0 N/A · 4 operator-responsibility. **IA-2(1) = pass** ("all 1 privileged account(s) have MFA enrolled" — reflecting the MFA enrollment above). **SI-2/SI-3 = pass** ("0 open vulnerabilities, scan #1" — consuming the Platform Health scan above, proving the two capabilities are actually wired together, not just co-located). The two genuine fails (AC-8 `COOKIE_SECURE=false`, SC-12 `llm_encryption_key` at dev default) are honest findings for this unconfigured test deployment, not code defects — confirms the report doesn't default to a false pass.

### TS-GREET — Greeting Service demo slot (FR-001..FR-005, BR-001..BR-004) → `app/slots/greeting/tests/`
- Full both-floors coverage per the adapted draft Build Package; the two Chassis Program adaptations: the MFA-gated history endpoint (`test_greeting_page_renders_for_authenticated_user` et al.) and the opt-in LLM-vs-static translation path (`translation_source` field).
- **Live-verified (CP-B.8):** `GET /greet` real form; happy-path submission → "Hello, Ada! · Locale: en-GB · Source: static"; unsupported locale (de-DE) without LLM → correctly falls back to the org default locale, source: static; unsupported locale WITH the LLM checkbox → correctly falls back to static with a real "no active key for provider" log line (no provider key configured for this test org — verifies the fail-safe path, not the LLM-success path, which needs a real key this test environment doesn't have); MFA-gated history: 403 (real refusal, not an empty list) before MFA enrollment, real row after.

### TS-MCP-MODEL / TS-MCP-CRYPTO — MCP server connection storage (FR-MCPCLIENT-1/2/4) → `tests/test_mcp_service.py`
- `MCPServerConnection` created with `enabled` defaulting to false (registering ≠ exposing); a stored `encrypted_credential` read directly from the raw DB column (not through the ORM's decrypt path) is provably not the plaintext and does not contain it as a substring; a connection with no credential (`encrypted_credential IS NULL`) is a valid, resolvable config (unauthenticated server).

### TS-MCP-SVC — Discovery + invocation (FR-MCPCLIENT-6/7/8) → `tests/test_mcp_service.py`
- `discover_tools` against a real fixture MCP server (`tests/fixtures/mcp_fixture_server.py`) for a registered **+ enabled** connection returns both fixture tools (`echo`, `lookup`), qualified `<connection-name>.<tool-name>`; a **disabled** connection's tools are never discovered; an org with **zero** connections (or only disabled ones) gets `discover_tools() == []`; discovery is scoped to the calling org only — a second org's enabled connection is never returned, and `invoke_tool` for another org's qualified name resolves to an error, never that org's live connection (FR-MCPCLIENT-8 / FR-TEN parity). `invoke_tool` against the fixture server's `echo` returns the real fixture result (`{"result": "<echoed text>"}`); `invoke_tool` against `lookup` with a known key returns the fixture's real value; with an unknown key returns `{"error": ...}` (the fixture's own error path, proving a normal tool-reported failure round-trips as data, not an exception).

### TS-MCP-DEGRADE — Graceful degradation (FR-MCPCLIENT-9/10/11/12) → `tests/test_mcp_service.py`
- A connection pointed at a closed local port: `discover_tools` excludes it and returns the *other* enabled connections' tools without raising; the request is not failed by one bad server. A simulated auth failure (invalid Bearer credential against a server that rejects it) surfaces as `invoke_tool`'s `{"error": ...}` return, never an unhandled exception. A simulated tool-execution error (the fixture's `lookup` on an unknown key) surfaces the same way. All of the above complete within the configured timeout — no call hangs indefinitely (`mcp_request_timeout_seconds`).

### TS-MCP-ADMIN — Admin UI (FR-MCPCLIENT-13) → `tests/test_mcp_admin.py`
- Anonymous → 303 login; regular user (no `mcp:write`) → 403; org admin can register a connection (name/URL/credential), see it listed with the credential masked (never the plaintext in the rendered HTML), enable it, disable it, and delete it — all via `/admin/mcp`'s form-POST routes, matching `/admin/llm`'s exact interaction shape (no new UI style); an org admin cannot enable/disable/delete another org's connection (403, not 404 — mirrors the existing cross-org admin-action convention on this screen family); every mutation writes an audit row (`mcp.connection_*`) whose `details` never contains the credential value.

### TS-MCP-INTEGRATION / TS-MCP-DEMO — Tool-calling loop + zero-connection no-op (FR-MCPCLIENT-6, NFR-MCPCLIENT-1) → `app/slots/greeting/tests/test_mcp_integration.py`
- **Negative control (proving absence, not just "not mentioned"):** an org with no connections (or only disabled ones) calling `_try_llm_translate` → a mocked/spied `complete()` is asserted to have been called with **no `tools` key at all** in its kwargs, and `discover_tools` is confirmed to add no extra call into `mcp/client.py` on this path.
- **Positive path:** an org with a registered + enabled connection to the fixture server → `complete()` is called with a non-empty `tools` kwarg containing the fixture's qualified tool names; a mocked LLM response carrying a `tool_calls` entry naming the fixture's `lookup` tool drives the loop to call `invoke_tool` against the real fixture server, append a `{"role":"tool", "tool_call_id":..., "content":...}` message, and re-invoke `complete()` — the fixture's real result reaches the second `complete()` call's message list. The loop is bounded (a mocked response that keeps requesting tool calls forever stops at the fixed iteration cap rather than looping unboundedly).
- **Demo visibility:** with the connection enabled, `GreetingResponse.tools_used` is non-empty and `greeting.html`'s meta line renders a "Tools used:" segment; with MCP disabled (no enabled connection), `tools_used == []` and the meta line is unchanged from its pre-MCP form.

### TS-CPB-1 — Login form / JSON API routing collision (regression) → `tests/test_frontend_login.py`
Real bug, live-found: the HTML login form posted to `POST /auth/login`, the identical (path, method) already claimed by the JSON API router included earlier in `app/main.py` — a silent Starlette routing conflict that made the HTML handler permanently unreachable since the reference chassis was first authored. Fixed by moving the browser-facing form to its own path (`POST /login`). The dead handler also unconditionally skipped the IA-2(1) MFA branch; fixed alongside (`POST /login/mfa`).

### TS-CPB-2 — `optional_current_user()` never read the session cookie (regression) → `tests/test_frontend_login.py::test_browser_login_cookie_actually_authenticates_dashboard`
Real bug, live-found: `get_current_user`'s cookie parameter only auto-populates via FastAPI's `Depends()` machinery; called as a plain function (as `optional_current_user` did), it never resolved a real browser's cookie. Every HTML page sharing this helper (the dashboard and the entire `/admin/*` shell) always treated a validly-cookied session as logged out. Fixed by resolving the cookie manually.

### TS-CPB-3 — Greeting page 500'd on every real request (regression) → `app/slots/greeting/tests/test_routes.py::test_greeting_page_renders_for_authenticated_user`
Real bug, live-found: `greeting_page()` built its own ad hoc template context instead of reusing `_common_context()`, so `base.html`'s nav (`settings.is_gov_app`) threw `UndefinedError` on every real render. Fixed by reusing the shared helper.

### TS-CPB-4 — BR-003 audit `details` silently empty (regression) → `app/slots/greeting/tests/test_routes.py::test_greeting_audit_log_details_are_actually_populated`
Real bug, live-found: `greet()` returns `tuple[GreetingEvent, str]`; the `@audited` decorator's `capture_details` lambda assumed the bare event, so every call raised `AttributeError`, silently caught, writing every `AuditLog.details` column empty. Fixed by unpacking the tuple.

### TS-CPB-5 — MFA/secrets fail-closed-in-prod confirmed correct (not a regression) → operational
Live-found during CP-B.8: `POST /auth/mfa/enroll` correctly 500'd with `InsecureKeyError` when `MFA_ENCRYPTION_KEY` was unset in `env=prod` — the same fail-closed pattern already documented for `JWT_SECRET`/`ENCRYPTION_KEY`. Resolved operationally (a real key supplied via the Deployment Module's per-deploy secrets), not by code change. Recorded here so a future session doesn't mistake this for a defect.

---

## Coverage summary

| Area | Tests |
|---|---|
| auth + AC-7 + AC-8 + jwt-validator | test_auth, test_ac7_lockout, test_ac8_banner, test_jwt_secret_validator |
| rbac + orgs + admin | test_orgs, test_admin |
| audit (AU-3/AU-11) | test_au3_ip_capture, test_au11_archival |
| health + system-health | test_health, test_system_health |
| docs | test_docs |
| llm (crypto/service/admin) | test_llm_crypto, test_llm_service, test_llm_admin |
| files / notifications | test_files, test_notifications |
| rate-limit / reports | test_ratelimit, test_reports |
| errors / mail / tasks | test_error_handlers, test_error_messages, test_mail, test_tasks |
| UI states / responsive / NFR | test_states, test_responsive, test_nfr_baselines |
| retention / slots | test_si12_retainable, test_slots_example |
| mcp (service/degradation/admin/integration) | test_mcp_service, test_mcp_admin, app/slots/greeting/tests/test_mcp_integration |
| **Total under `tests/` + `app/`** | **351 passing** (`uv run pytest -q`) |

---

---

## Chassis floor scenarios (L1 — locked, not editable)

The scenarios listed in this package's `StackTemplate.LockedSections["test_scenarios"]` are a
**floor**: an application may add its own scenario sections freely, but may not weaken or delete
these. Their canonical text ships as `BaselineSectionContent["test_scenarios.<key>"]`, and an edit
to one is refused the same way an edit to a locked CONSTITUTION clause is.

**Why this exists.** Before L1 this package locked constitution clauses while leaving the test that
*proves* each clause freely editable — so an application could satisfy a locked clause's letter by
rewriting the scenario that checks it. One locked scenario per locked constitution clause closes
that.

**Two sections are deliberately NOT locked**, and the reason is a property of locking rather than an
oversight: a locked scenario **cannot be corrected**. `overview` is descriptive — there is no
behaviour to assert, and inventing a scenario to reach a count would be exactly the restatement this
mechanism forbids. `coding_standards` is already enforced executably by the formatter, linter and
type checker, which are release gates; duplicating a stronger check inside an uncorrectable document
is a liability, not redundancy.

**The heading text is load-bearing, and the heading lives in the TEMPLATE.** A locked section's
identity is derived from its `##` heading (lowercased, separators normalized, trailing parenthetical
dropped); `EnforceLockedSections` walks the *document's* headings, and the drift detector treats a
section absent from both the old and the new document as nothing to check. A locked key with no
matching heading in the real document therefore enforces **nothing, silently, with no log line**.

The floor is consequently **two halves that must agree**, and neither half alone is the floor:

- `build-package-templates/template-<stack>-test_scenarios.md` carries one `## <Name> (locked —
  chassis floor)` section per key, each tagged `@locked-by-chassis: true`. This is the document a
  customer's `TEST-SCENARIOS.md` is materialized from, and it is where the heading — and so the
  section's identity — comes from.
- `BaselineSectionContent["test_scenarios.<key>"]` carries that section's **body**, heading-less and
  H3-led. The enforcer emits the document's own `##` heading and appends the baseline after it, so a
  baseline carrying its own H2 would duplicate the heading in every generated package.

**This was wrong for eight days and the guard that should have caught it passed.** The first L1 pass
declared the keys and wrote the baselines, and checked them against *each other* — the seed against
the seed. Both halves were mutually consistent and jointly wrong about the document: the real
template's sections were slugged `test_generation_contract`, `application_test_scenarios` and
`security_&_failure_tests`, so not one of the declared keys bound to anything.
`TestLockedTestScenarioKeysBindToTheirTemplateSections` (in `internal/services`, where the production
parser and heading rule live) now reads the template file off disk and asserts, per key, that the
section exists, is tagged locked, and matches the seeded baseline byte for byte.
`TestEveryChassisPackageShipsATestScenariosTemplate` closes the adjacent hole: a package with no
`build-package-templates/` directory falls back to the generic platform templates and would designate
another stack's documents rather than refuse.

## CHANGELOG

**v1.4.1 (2026-09-18) — L1 correction: the floor now binds to the document it governs.** PATCH. The locked `test_scenarios` keys this package declared were checked only against their own baseline text, and bound to nothing in this package's real `build-package-templates/template-python-test_scenarios.md` — whose sections are slugged `test_generation_contract` / `application_test_scenarios`, not `auth` / `rbac` / `audit`. The template now carries one `## <Name> (locked — chassis floor)` section per declared key, tagged `@locked-by-chassis: true`, with the seeded baseline as its body; baselines are heading-less and H3-led because the enforcer emits the document's heading itself. Two platform defects found in the same pass and fixed: enforcement was deleting the *following* section's ownership tag (with fourteen consecutive locked scenarios, one pass would have unlocked thirteen), and the first guard validated the seed against the seed. Task Log: `specs/platform/Task Logs/2026-09-18-321-l1-floor-binds-to-the-document.md`.

**v1.4.0 (2026-09-18) — L1: chassis floor scenarios are locked.** MINOR. This package now declares a locked `test_scenarios` section for every locked constitution clause with something checkable to say (14 of them), with canonical text in `BaselineSectionContent`. Previously the clause was protected while the test proving it stayed freely editable. `overview` and `coding_standards` are deliberately omitted — the first has no assertable behaviour, the second is already enforced by executable release gates, and a locked scenario cannot be corrected. Task Log: `specs/platform/Task Logs/2026-09-18-319-l1-locked-test-scenarios.md`.

**v1.3.0 (2026-09-17) — TS-ADM gains the cross-tenant admin MUTATION scenario.** MINOR: the read-side scoping (an org admin's user listing shows only their own org) was covered; the mutating path was not, and the gap was real — proven by execution on 2026-09-17 before any fix was written. Adds the scenario with both halves asserted (refusal status AND unchanged target state), both verbs (deactivate and reactivate), and a different-org target rather than an orgless one. Task Log: `specs/platform/Task Logs/2026-09-17-313-python-chassis-execution-proof-and-admin-tenancy-gap.md`.

### 1.2.0 — 2026-09-10
- MCP Client capability (FR-MCPCLIENT), this package only: adds TS-MCP-MODEL/TS-MCP-CRYPTO, TS-MCP-SVC, TS-MCP-DEGRADE, TS-MCP-ADMIN, and TS-MCP-INTEGRATION/TS-MCP-DEMO, all real tests against a fixture MCP server (`tests/fixtures/mcp_fixture_server.py`) — never a live third party. Covers registration/CRUD/masking, org-scoped discovery+invocation, the mandatory graceful-degradation paths (unreachable server, auth failure, tool-execution error, timeout), the admin UI matching `/admin/llm`'s pattern, and the tool-calling loop integration into the greeting-translation demo slot with an explicit negative control proving a zero-connection org adds no `tools` kwarg. Task Log: `specs/platform/Task Logs/2026-09-10-003-mcp-client-support.md`.

### 1.1.0 — 2026-09-02
- Chassis Program Phase B pilot (CP-B.1–CP-B.9): added TS-MFA, TS-SYSHEALTH, TS-PLATHEALTH, TS-FISMAAUDIT, TS-GREET for the three new shared capabilities + the adapted Greeting Service demo slot, and TS-CPB-1 through TS-CPB-5 recording the real bugs found and fixed live via CP-B.8's mandatory browser E2E pass (login/JSON routing collision, broken cookie auth, greeting-page template context, BR-003 audit-details tuple bug) plus one confirmed-correct fail-closed behavior (MFA key, not a regression). Full suite: 323 tests passing (`app/` + `app/slots/*/tests/`, `uv run pytest -q`).

### 1.0.0 — 2026-06-22
- Initial TEST-SCENARIOS for the python-fastapi chassis at v0.10.0: TS groups for every capability mapped to the 203-test suite, with FR references and the cross-cutting 401/403/404/422 conventions.
