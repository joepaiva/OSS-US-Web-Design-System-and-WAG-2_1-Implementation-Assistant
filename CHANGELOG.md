# Changelog — Python-FastAPI Chassis

All notable changes to this chassis. Format follows *Keep a Changelog*; this chassis uses
semantic-ish versioning where MINOR bumps add capabilities and PATCH bumps fix/ harden.
`CHASSIS_VERSION` is kept in lockstep with the platform's Go seed pin (CI-enforced).

The full specification (Build Package) lives in [`specs/`](specs/).

## 1.3.3 — 2026-09-21 — No volatile test counts in the test-scenarios template
- **Removed a hard-coded test count** ("110 tests", "31 test modules", …) from the test-scenarios template. Every added test made the number wrong; the sentence now describes the suite without counting it. A test pins that no template states such a count. Templates only; no application code changed.

## [1.3.2] - 2026-09-21

### Fixed
- **Templates stop describing a stack the chassis no longer has:** the constitution template's technology table no longer lists `python-jose` 3.3.0 / `passlib` 1.7.4 / `bcrypt` 4.0.1 — `pyproject.toml` pins `pyjwt==2.13.0` and `bcrypt==5.0.0`, called directly (CP-B.3 removed the old pair) — and the requirements/constitution templates no longer say `passlib`+`bcrypt` or `python-jose`. MFA is now stated as mandatory for platform-wide administrators and the MFA wrapping key is named beside the JWT secret. The MCP client capability the chassis has (`app/mcp/`, `mcp_server_connections`, `/admin/mcp`) is now in the requirements, design, constitution and tasks templates. Template text only; no application code changed. (Task Log `2026-09-21-254` (F-250-3 completion))
- **Not changed, recorded:** this package's own `specs/CONSTITUTION.md` technology table still lists the old JWT/password pair; aligning a spec to the code needs operator approval (Rule: never change specs to match code without it).

## [1.3.1] - 2026-09-18

### Fixed
- **L1 correction — the locked test-scenario floor now binds to the document it governs.** The
  locked `test_scenarios` keys this package declares were validated only against their own baseline
  text, and matched no section in this package's real
  `build-package-templates/template-python-test_scenarios.md` — whose sections are slugged
  `test_generation_contract` / `application_test_scenarios`, not `auth` / `rbac` / `audit`. A locked
  key with no matching `##` heading in the real document enforces nothing, silently. The template now
  carries one `## <Name> (locked — chassis floor)` section per declared key, tagged
  `@locked-by-chassis: true`, with the seeded baseline as its body. Baselines are now heading-less and
  H3-led, matching every constitution baseline: the enforcer emits the document's own heading and
  appends the baseline after it, so an H2-led baseline duplicated the heading in every generated
  package.
- Two platform defects found in the same pass and fixed in `internal/services/locked_sections.go`:
  enforcement was deleting the *following* section's `@owned-by` / `@locked-by-chassis` ownership tag
  (with fourteen consecutive locked scenarios, one enforcement pass would have unlocked thirteen of
  them), and the guard that should have caught the binding failure compared the seed against the seed.

## [1.3.0] — 2026-09-18 — Chassis floor scenarios are locked (L1)

**Added — a locked `test_scenarios` section for every locked constitution clause with something checkable to say.** Before this, the clause was protected while the test that *proves* it stayed freely editable, so an application could satisfy a locked clause's letter by rewriting the scenario that checks it. Canonical text ships in `BaselineSectionContent`; an edit to a floor scenario is refused the same way an edit to a locked constitution clause is.

`overview` and `coding_standards` are deliberately **not** locked: the first has no assertable behaviour, the second is already enforced by executable release gates, and a locked scenario cannot be corrected — so locking one with nothing to say is a permanent liability.

**The finding this pass produced.** A locked section's identity is derived from its `##` heading text, and the drift detector treats a section absent from both document versions as nothing to check — so a locked key whose heading does not derive back to it enforces nothing, silently. The first draft of these baselines used descriptive level-3 headings and would have locked nothing at all. A guard now pairs every declared key with its baseline and asserts the heading derives back to the key.

## [1.2.0] — 2026-09-18 — First extension surface: application dependencies

**Added — `application_dependencies`, the one section of the generated constitution an application may extend (AB-FR-617).** Until now this chassis declared only what was *locked*, so the answer to "may I add a library?" defaulted to no, with no escape hatch. It now declares the other half, and the two sets are asserted disjoint by a test rather than by review.

The section ships as an empty table. That is deliberate and it is the safety argument: the only enforcement that exists today is a locked / not-locked gate, so "extensible" currently means **freely editable, deletion included**. A section is therefore only safe to open if there is no mandate inside it to weaken. `observability` and `state_handling` are additive in principle and are the right next candidates, but they stay **locked** until add-only enforcement exists.

The six rules governing additions (additions only; no second implementation of a chassis concern; exact pins; the same zero-CVE and currency obligation as the chassis's own pins; no new egress; org-admin approval per addition) live in the **locked** `extension_model` section. Rules written inside the extensible section could be edited out by the application they bind.

`specs/CONSTITUTION.md` §6.1 records the policy; §8 gains a fourth clause distinguishing an *extension* from an *amendment*, so an application adding a library does not re-version this chassis.

**Why now.** An application needed `gopdf` and `excelize`, and the chassis correctly refused because dependency pins are locked. The refusal was right and the need was real — which is precisely the gap an extension surface exists to close.

## [1.1.1] — 2026-09-17 — SECURITY: org-admin user deactivation was not org-scoped

### Fixed
- **Cross-tenant privilege escalation in the admin shell (FR-ADM-2, `AC-3`).** `set_user_active`
  resolved its target user by primary key with no organization scope, while the route that calls it
  (`POST /admin/users/{id}/deactivate|reactivate`) authorizes on the `users:write` permission —
  which an **org** administrator holds. An org administrator could therefore deactivate or
  reactivate **any user on the platform**, including other tenants' members and platform
  administrators, by walking sequential user ids. The admin user *listing* was correctly scoped, so
  the acting administrator could not see the users they were nonetheless able to disable — which is
  precisely why this survived: the read scoping made the write gap invisible.

  Proven by execution before any fix was written: Org A's administrator POSTed a deactivate for Org
  B's member and received `303 See Other` with `is_active` going `True → False`, then reactivated the
  same user the same way, while that user was absent from Org A's own `/admin/users` listing.

  `set_user_active` now takes the caller's resolved scope (`platform`, `org_id`) as **required**
  keyword arguments and resolves a non-platform caller's target through their own organization's
  membership. A target outside that organization raises `AdminError("user not found")` → 404 (the
  FR-TEN-7 convention — never a distinguishable 403, which would confirm the account exists), and
  the check runs **before** the mutation, so a refused call leaves the target untouched. The
  arguments are required rather than defaulted so that a future call site cannot reintroduce the gap
  by omission.

  Regression test: `tests/test_admin.py::test_org_admin_cannot_mutate_other_org_member` — asserts
  both obligations (refusal status AND unchanged target state), both verbs, and uses a target who is
  a member of a *different* org rather than an orgless user. Verified by removal proof: with the
  membership check disabled the test fails with `303 != 404`.

### Changed
- `specs/REQUIREMENTS.md` FR-ADM-2 now states the admin **write** scope, not only the read scope
  (shared per-variant requirement, amended across all 16 multi-tenant packages).
- `specs/DESIGN.md` §4.6 records where the `org-admin=members` constraint is enforced. The table
  already asserted that constraint — the code had diverged from its own design document.

## [1.1.0] — 2026-09-10 — MCP Client (FR-MCPCLIENT)
### Added
- **MCP client capability** (`app/mcp/`): lets the embedded-LLM chat-completion call path
  discover and invoke tools exposed by admin-registered external MCP (Model Context
  Protocol) servers — client role only, never an inbound MCP server. New
  `MCPServerConnection` model (org-scoped, no platform-shared variant, `enabled` defaults
  false), migration `0014_mcp_client`. Credentials reuse `app/llm/crypto.py`'s AES-256-GCM
  encryption directly (never a second implementation).
- `app/mcp/client.py`: thin wrapper around the official `mcp` SDK (`mcp==2.2.0`, MIT), client
  surface only (`mcp.Client` over `streamable_http_client`); every SDK/transport failure
  converts to a typed `MCPClientError`.
- `app/mcp/service.py`: CRUD (`@audited`, credential never in the audit payload), plus
  `discover_tools`/`invoke_tool` — org-scoped, never raising for a normal operational
  failure (unreachable server, auth rejection, tool-execution error, timeout all degrade to
  a skipped connection or a `{"error": ...}` tool-result).
- `/admin/mcp` (new `mcp:read`/`mcp:write` permissions): register/list/enable/disable/delete,
  the identical server-rendered form-POST pattern as `/admin/llm`; dashboard tile.
- **Tool-calling loop** wired into `app/slots/greeting/providers/translation.py`'s
  `_try_llm_translate()`: discovers enabled connections' tools, offers them to the LLM, and
  drives up to 3 rounds of tool-call → real MCP invocation → result folded back into the
  conversation. An org with zero enabled connections adds no `tools` kwarg and no latency —
  the exact prior code path. `GreetingResponse.tools_used` (+ `greeting.html`'s meta line)
  surfaces which tool(s) were actually called, so the effect is visible in the browser.
- `tests/fixtures/mcp_fixture_server.py`: in-process fixture MCP server (`echo`, `lookup`
  tools; an optional bearer-token-gated variant for the auth-failure test) — test-only,
  never a runtime dependency. New test suites: `tests/test_mcp_service.py`,
  `tests/test_mcp_admin.py`, `app/slots/greeting/tests/test_mcp_integration.py`.
- `mcp_request_timeout_seconds` config (default 10s) bounds every MCP network call, the same
  class of setting as `llm_request_timeout_seconds`.
- Docs: `docs/HOW-IT-WORKS.md` §5.6, `docs/USER-MANUAL.md`'s new "MCP Server Connections"
  section, `docs/SECURITY-SELF-AUDIT.md` (AC-3/SC-28/SC-12 rows + a new §7 operator-
  responsibility item on the MCP server trust boundary).
- Full suite: 351 tests passing (`uv run pytest -q`, up from 323 pre-change).
### Fixed
- **Same latent test-staleness bug as v1.0.1, recurring on this bump**:
  `tests/test_health.py::test_version_returns_semver` and
  `tests/test_system_health.py::test_gather_system_health_never_raises` each still carried a
  redundant hardcoded `== "1.0.1"` literal duplicating the adjacent, already-correct dynamic
  assertion against `__chassis_version__` — caught live by this bump exactly as v1.0.1's own
  entry predicted. Updated both literals to `"1.1.0"`; the meaningful dynamic assertion is
  unchanged and unweakened.

## [Unreleased]
### Changed
- **Removed the legacy PaaS deploy config + references; Azure/container-host is the deployment target** (2026-06-27): deleted the legacy `*.toml` PaaS deploy config (the chassis is built/run via its `Dockerfile` + Azure; alembic-migrate + uvicorn-start are handled by the Dockerfile/compose path). Replaced all legacy-PaaS naming in `Dockerfile`, `app/config.py`, and `docs/NFR-BASELINES.md` with Azure Container Apps / generic container-host wording (e.g. "per single Azure Container Apps instance"; horizontal scale now documented as `az containerapp update --max-replicas N`). Docs/config only — no runtime behavior change (ports, env-var names read, and Dockerfile build steps unchanged); no `CHASSIS_VERSION` / Go-seed-pin bump.

## [1.0.1] — 2026-09-09 — CI dependency-currency bump
### Fixed
- **`alembic` 1.19.1 → 1.19.2** (`pyproject.toml` + `uv.lock`, `uv lock --upgrade-package alembic`): clears `chassis-ci`'s dependency-currency drift finding (zero CVEs either version — pure patch-currency bump, no behavior change). Verified: 323/323 tests pass.
- **Fixed a latent test staleness bug found by this bump**: `tests/test_health.py`/`tests/test_system_health.py` each carried a redundant hardcoded `== "1.0.0"` literal duplicating the adjacent, already-correct dynamic assertion against `__chassis_version__` — harmless until the first real CHASSIS_VERSION bump (this one), which broke it in real CI (caught live, not by inspection). Updated the literal to `"1.0.1"`; the meaningful dynamic assertion is unchanged and unweakened.

## [0.10.0] — 2026-06-22 — Workstream A4: Files, Notifications, Rate-limiting, Reporting
### Added
- **File storage** (`app/files/`, `/api/files`): org-scoped upload/list/download/delete; disk storage under opaque UUID keys (no traversal); SHA-256 integrity; `max_upload_bytes` cap; `@audited`. Config `file_storage_dir`, `max_upload_bytes`.
- **Notifications** (`app/notifications/`, `/api/notifications`): per-user in-app notifications (level + read state); `notify(...)` producer; list/unread-count/read/read-all; strict user isolation.
- **Rate limiting** (`app/ratelimit/`): opt-in (`RATE_LIMIT_ENABLED`, default off) Redis fixed-window per-client middleware; fail-open; exempts health/version/static (SC-5).
- **Reporting** (`/admin/reports`, `app/admin/reports_service.py`): read-only usage counts; platform=global, org-admin=org-scoped. Dashboard tile.
- Migration `0010_a4_files_notifications`. Docs: SECURITY-SELF-AUDIT SC-5/SC-12/SI-10 updates.
- **Build Package retrofit**: full `specs/` (REQUIREMENTS [tech-neutral], CONSTITUTION, DESIGN, TASKS, TEST-SCENARIOS) + CHANGELOG.
### Fixed
- **Chassis version surfacing** (2026-06-25): `/version` and the System Health admin page reported the app package version (`0.1.0`) in both the `version` and `chassis`/`chassis_version` fields. The chassis field is now sourced from `app.__chassis_version__`, read from the `CHASSIS_VERSION` file at import time (fallback to `__version__` if unreadable), so it correctly reports the chassis framework version (`0.10.0`) distinct from the app version. No `CHASSIS_VERSION` / Go-seed-pin bump (surfacing fix only). DESIGN §4.1/§6.5 → 1.0.1.

## [0.9.0] — 2026-06-22 — Workstream A3: Embedded LLM (Rule-7 parity)
### Added
- `app/llm/`: AES-256-GCM-encrypted provider keys (`llm_provider_keys`), per-org + platform-shared; resolution chain org key → shared key (iff `org_llm_access` grants) → reject; OpenAI-compatible egress (`llm_proxy_url`) with per-request key injection; pluggable `LLMTransport`.
- `/admin/llm` (`llm:write`): org admins manage org keys; platform admins manage shared keys + per-org access policy; keys masked.
- `llm:read`/`llm:write` permissions; migration `0009_llm_keys`; `cryptography` dependency.
- Wrapping key (`llm_encryption_key`) fails closed at use time in production if left at the in-code default.

## [0.8.0] — 2026-06-22 — Workstream A2: System Health, In-app Docs, FISMA self-audit
### Added
- **System Health** (`/admin/system-health`, platform-only): live version/env + best-effort DB/Redis reachability; credential redaction; bounded checks.
- **Documentation** (`/admin/docs[/{slug}]`): whitelisted slug registry + dependency-free HTML-escaping Markdown renderer.
- `docs/HOW-IT-WORKS.md`, `docs/USER-MANUAL.md`, `docs/SECURITY-SELF-AUDIT.md` (NIST 800-53 FISMA-Moderate control mapping).

## [0.7.0] — 2026-06-21 — Workstream A1: Admin shell (User + Org management)
### Added
- `app/admin/`: server-rendered admin shell at `/admin` — User Management (platform = all users; org admin = org members; create/deactivate/reactivate) and Org Management (platform only). Gated on `users:write`.

## [0.6.x] — Security hardening (FISMA-Moderate posture) + UX baselines
### Added / Changed
- **AC-7** account lockout (3/15min → 30min); **AC-8** system-use banner; **IA-5** password complexity (14 chars, 4 classes); **IA-6** anti-enumeration.
- **AU-3** client-IP capture; **AU-9** audit-log immutability (REVOKE UPDATE/DELETE); **AU-11** retention/archival job + `audit_logs_archive`.
- **SI-11** production error handler; **SI-12** `RetainableFor` retention mixin; **FR-351** jwt_secret hardening (placeholder + prod-default rejection).
- **K.7** responsive-design baseline; **K.8** canonical error-message catalog (`error_messages.py`); **K.10** loading/empty/error page-state macros; **K.11** NFR baselines doc.
- Migrations `0006_ac7_lockout`, `0007_au11_archive_logs`, `0008_au9_audit_log_permissions`.

## [0.5.0] — Admin-shell frontend
### Added
- Server-rendered USWDS 3.x + Stripe-aesthetic frontend (`app/frontend.py`, templates, static); HTML auth routes; `/account`; `/dashboard`.

## [0.2.0 – 0.4.0] — Patterns hardened from Phase-3 build runs
### Changed
- Banned naive `datetime.utcnow()`/`datetime.now()` (use `datetime.now(UTC)`); banned `sqlmodel` (not a dependency).
- Added state-machine reference slot (`example_with_states`) with guarded transitions; per-tenant configuration guidance; soft-delete design position.

## [0.1.0] — Base chassis
### Added
- Core: identity + JWT auth, RBAC (roles/permissions, system-wide + per-org), multi-tenancy (`TenantScoped` + auto org filter/stamp), audit (`@audited`, `audit_logs`), health probes (`/healthz`,`/readyz`,`/version`), structured logging + request-id middleware, transactional email, RQ background jobs, settings/config, CRUD reference slot (`example`).
- Migrations `0001_users` … `0005_example_notes`.
- Stack locked: Python 3.12, FastAPI, SQLAlchemy 2.0 async, Pydantic v2, PostgreSQL, Redis.

[0.10.0]: #0100--2026-06-22--workstream-a4-files-notifications-rate-limiting-reporting
[0.9.0]: #090--2026-06-22--workstream-a3-embedded-llm-rule-7-parity
[0.8.0]: #080--2026-06-22--workstream-a2-system-health-in-app-docs-fisma-self-audit
[0.7.0]: #070--2026-06-21--workstream-a1-admin-shell-user--org-management
