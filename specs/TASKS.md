# Python-FastAPI Chassis — TASKS (Regeneration Build Order)

**Version:** 1.1.0
**Date:** 2026-09-10
**Status:** Authoritative
**Chassis version:** 1.1.0

> Ordered task list to build the chassis from an empty repository to the v0.10.0 state, with **zero human intervention**. Each task names its files, its dependencies, and its exit criterion (the relevant TEST-SCENARIOS group — see [`TEST-SCENARIOS.md`](TEST-SCENARIOS.md)). Tasks within a phase may run in any order unless `depends_on` says otherwise; phases are sequential. Every phase MUST end compile-clean (`ruff`, `mypy`), with its tests green, before the next begins (CONSTITUTION §2/§4).

Legend: **Produces** = files written · **Verifies** = TS group · **Dep** = prerequisite task.

---

## Phase 0 — Project Skeleton
- **T-0.1 Toolchain & manifest.** `pyproject.toml` with the exact pinned deps + dev deps + tool config (ruff/mypy/pytest/coverage) from CONSTITUTION §1; `.python-version` (3.12); `uv.lock`; `README.md` quickstart; `.env.example`; `.gitignore` (includes `data/`). **Verifies:** build boots.
- **T-0.2 Runtime config.** `app/config.py` — `Settings` + validators (datastore-URL normalization, FR-351 jwt_secret, llm_encryption_key hex/length). **Verifies:** TS-CFG. **Dep:** T-0.1.
- **T-0.3 Data layer.** `app/db.py` — `Base`, async engine/sessionmaker, `SessionDep`, context vars, `TenantScoped`, `RetainableFor`, tenancy event listeners; `app/deps_context.py`. **Verifies:** TS-TEN (later). **Dep:** T-0.2.
- **T-0.4 Logging + errors.** `app/logging.py` (structlog), `app/error_handlers.py` (SI-11), `app/error_messages.py` (catalog). **Verifies:** TS-ERR. **Dep:** T-0.2.
- **T-0.5 App factory.** `app/main.py` — `create_app`, lifespan stub, middleware (request-id+IP, CORS, exception handler), extension-point markers. **Dep:** T-0.3, T-0.4.

## Phase 1 — Identity, RBAC, Tenancy (the security core)
- **T-1.1 Auth models + schemas.** `app/auth/models.py` (`users`), `app/auth/schemas.py` (IA-5 complexity validator). **Verifies:** TS-AUTH (partial). **Dep:** T-0.3.
- **T-1.2 Auth service.** `app/auth/service.py` — hashing, JWT issue/decode, `register_user`, `authenticate` (AC-7 lockout), exceptions. **Verifies:** TS-AUTH, TS-AC7. **Dep:** T-1.1.
- **T-1.3 RBAC.** `app/rbac/models.py`, `app/rbac/permissions.py` (CorePermissions + registry + extension marker), `app/rbac/service.py` (`user_has_permission`, `seed_chassis_rbac`, `assign_role_to_user`). **Verifies:** TS-RBAC. **Dep:** T-1.1.
- **T-1.4 Auth deps + routes + providers.** `app/deps.py` (`get_current_user`, `get_current_org`, `requires`, cookie const), `app/auth/routes.py`, `app/auth/providers/__init__.py` (extension marker). Wire RBAC seeding into the lifespan. **Verifies:** TS-AUTH. **Dep:** T-1.2, T-1.3.
- **T-1.5 Orgs.** `app/orgs/models.py`, `schemas.py`, `service.py` (create/list/default/switch, audited), `routes.py`. **Verifies:** TS-TEN. **Dep:** T-1.4, T-2.1 (audit decorator) — if audit not yet present, mark service audited and complete in Phase 2.

## Phase 2 — Audit, Health, Mail, Jobs
- **T-2.1 Audit.** `app/audit/models.py` (`audit_logs`), `app/audit/decorator.py` (`@audited`), `app/audit/tasks.py` (AU-11 archival). **Verifies:** TS-AUD, TS-AU3, TS-AU11. **Dep:** T-0.3, T-0.3 context vars. Back-apply `@audited` to orgs service (T-1.5).
- **T-2.2 Health.** `app/health/routes.py` (`/healthz`,`/readyz`,`/version`). **Verifies:** TS-HEALTH. **Dep:** T-0.5.
- **T-2.3 Mail.** `app/mail/service.py` (console/SMTP). **Verifies:** TS-MAIL. **Dep:** T-0.2.
- **T-2.4 Jobs.** `app/tasks/queue.py` (`enqueue`), `app/tasks/worker.py`. **Verifies:** TS-TASKS. **Dep:** T-0.2.

## Phase 3 — Frontend & Accessibility
- **T-3.1 Templates + static.** `app/templates/base.html` (USWDS, skip-nav, gov banner, AC-8 banner), `error.html`, `auth/*`, `dashboard/index.html`, `components/forms.html`, `components/_states.html` (loading/empty/error); `app/static/css/stripe-overrides.css`. **Verifies:** TS-UI, TS-STATES, TS-RESPONSIVE, TS-AC8. **Dep:** T-1.4.
- **T-3.2 Frontend routes.** `app/frontend.py` (templates instance, `_common_context`, `optional_current_user`, HTML auth routes, `mount_static`); register in `main.py`. **Verifies:** TS-UI. **Dep:** T-3.1.

## Phase 4 — Admin Shell (base)
- **T-4.1 Admin core.** `app/admin/service.py` (platform/org predicates, user/org admin queries+mutations, audited), `app/admin/routes.py` (`_resolve` gate, dashboard, user mgmt, org mgmt, admin-pages extension marker), templates `admin/{dashboard,users,orgs,forbidden}.html`. Register `admin_router`; add nav link in `base.html`. **Verifies:** TS-ADM. **Dep:** T-1.5, T-2.1.

## Phase 5 — Reference Slots
- **T-5.1 CRUD slot.** `app/slots/example/` (models/schemas/service/routes/__init__ + tests). **Verifies:** TS-SLOT-CRUD. **Dep:** Phase 1–2.
- **T-5.2 State-machine slot.** `app/slots/example_with_states/` (guarded transitions). **Verifies:** TS-SLOT-STATES. **Dep:** T-5.1.

## Phase 6 — Mini-platform: System Health + In-app Docs (chassis v0.8 / A2)
- **T-6.1 System Health page.** `app/admin/health_service.py` (`gather_system_health`, redaction, bounded Redis ping), route `/admin/system-health`, template. **Verifies:** TS-SYSHEALTH. **Dep:** T-4.1, T-2.4.
- **T-6.2 In-app docs.** `app/admin/docs_service.py` (whitelist registry + safe markdown renderer), routes `/admin/docs[/{slug}]`, templates `admin/{docs,doc}.html`; author `docs/HOW-IT-WORKS.md`, `docs/USER-MANUAL.md`, `docs/SECURITY-SELF-AUDIT.md`. **Verifies:** TS-DOCS. **Dep:** T-4.1.
- **T-6.3 Dashboard tiles + nav.** System Health (platform) + Documentation tiles. **Dep:** T-6.1, T-6.2.

## Phase 7 — Mini-platform: Embedded LLM (chassis v0.9 / A3)
- **T-7.1 Crypto + config.** `app/llm/crypto.py` (AES-256-GCM, use-time prod fail-closed), config `llm_*`. **Verifies:** TS-LLM-CRYPTO. **Dep:** T-0.2.
- **T-7.2 Models + transport + service.** `app/llm/models.py` (`llm_provider_keys`,`org_llm_access`), `transport.py` (`LLMTransport`/`HTTPTransport`/get/set), `service.py` (resolution chain, CRUD, `complete`). **Verifies:** TS-LLM-SVC. **Dep:** T-7.1, T-2.1.
- **T-7.3 RBAC + admin UI.** `llm:read`/`llm:write` perms; `/admin/llm` routes (generalize `_resolve(permission=)`), template, dashboard tile. **Verifies:** TS-LLM-ADMIN. **Dep:** T-7.2, T-4.1.

## Phase 8 — Mini-platform: Files, Notifications, Rate-limit, Reporting (chassis v0.10 / A4)
- **T-8.1 Rate limiting.** `app/ratelimit/middleware.py` + `install_rate_limiting`; config `rate_limit_*`; wire in `main.py`. **Verifies:** TS-RL. **Dep:** T-0.5, T-2.4.
- **T-8.2 Files.** `app/files/` (models/service/schemas/routes); config `file_storage_dir`,`max_upload_bytes`; register router. **Verifies:** TS-FILES. **Dep:** T-1.4, T-2.1.
- **T-8.3 Notifications.** `app/notifications/` (models/service/schemas/routes); register router. **Verifies:** TS-NOTE. **Dep:** T-1.4.
- **T-8.4 Reporting.** `app/admin/reports_service.py`, route `/admin/reports`, template, dashboard tile. **Verifies:** TS-REP. **Dep:** T-8.2, T-8.3, T-7.2.

## Phase 9 — Migrations & Release
- **T-9.1 Migrations.** `migrations/versions/0001..0011` matching the models (additive-only; up+down each). **Verifies:** TS-MIGRATE (alembic upgrade head on a clean DB). **Dep:** all model tasks.
- **T-9.2 Supplemental docs.** `README.md`, `CHANGELOG.md`, `docs/HOW-IT-WORKS.md`, `docs/USER-MANUAL.md`, `docs/SECURITY-SELF-AUDIT.md`, plus `docs/{NFR-BASELINES,RESPONSIVE-DESIGN,STATE-HANDLING,SLOT-TESTING}.md`. **Dep:** features complete.
- **T-9.3 Version pin.** Set `CHASSIS_VERSION`; the platform Go seed pin must match (CI enforces). **Verifies:** version-consistency. **Dep:** all.
- **T-9.4 Full-suite gate.** `uv run pytest -q` green, `ruff` + `mypy` clean. **Dep:** all.

## Phase 10 — Mini-platform: MCP Client (this package only, chassis v1.1.0)
- **T-10.1 SDK pin + crypto reuse.** Add `mcp` (official SDK) to `pyproject.toml` at the verified-current latest-stable pin. `app/mcp/models.py` (`mcp_server_connections`, org-scoped, `enabled` default false) reusing `app/llm/crypto.py`'s `encrypt`/`decrypt`/`mask` directly — no second encryption implementation. **Verifies:** TS-MCP-MODEL. **Dep:** T-7.1.
- **T-10.2 Client wrapper + service.** `app/mcp/client.py` (thin SDK wrapper: `list_tools`, `call_tool`, both catching every SDK/transport exception into `MCPClientError`), `app/mcp/service.py` (CRUD audited per `llm/service.py`'s shape; `discover_tools`/`invoke_tool`, org-scoped, never raising for a normal operational failure). **Verifies:** TS-MCP-SVC, TS-MCP-DEGRADE. **Dep:** T-10.1, T-2.1.
- **T-10.3 RBAC + admin UI.** `mcp:read`/`mcp:write` perms in `rbac/permissions.py`; `/admin/mcp` routes in `app/admin/routes.py` (same `_resolve(permission=)` gate shape as `/admin/llm`), `admin/mcp.html` template, dashboard tile. **Verifies:** TS-MCP-ADMIN. **Dep:** T-10.2, T-4.1.
- **T-10.4 Tool-calling integration + demo.** Extend `app/slots/greeting/providers/translation.py`'s `_try_llm_translate()` with the discover→advertise→invoke→loop mechanism (§6.14 of `DESIGN.md`), bounded to 3 iterations; extend `GreetingResponse`/`greeting.html` to surface `tools_used`. Fixture MCP server `tests/fixtures/mcp_fixture_server.py` (`echo`, `lookup` tools) for the test suite only. **Verifies:** TS-MCP-INTEGRATION, TS-MCP-DEMO. **Dep:** T-10.2.
- **T-10.5 Migration + version bump.** `migrations/versions/0014_mcp_client.py` (additive, up+down). Bump `CHASSIS_VERSION` (MINOR) and the platform Go seed pin together. **Verifies:** TS-MIGRATE, version-consistency. **Dep:** T-10.1..T-10.4.

---

## Build-order rationale
Security core (identity → RBAC → tenancy) precedes everything because every later capability depends on `CurrentUser`/`CurrentOrg`/`requires` and on tenant scoping. Audit (Phase 2) precedes the admin shell because admin mutations must be audited. The mini-platform phases (6–8) layer onto the base admin shell. Migrations are authored last to match the final model set (tests use `create_all`, so feature phases don't block on Alembic).

---

## CHANGELOG

### 1.1.0 — 2026-09-10
- Adds Phase 10 (T-10.1..T-10.5): the MCP Client capability (FR-MCPCLIENT), this package only. SDK pin + crypto reuse, client wrapper + service (discover/invoke, graceful degradation), RBAC + admin UI matching `/admin/llm`'s pattern, the tool-calling integration into the greeting-translation demo slot, and the migration + version bump. Task Log: `specs/platform/Task Logs/2026-09-10-003-mcp-client-support.md`.

### 1.0.0 — 2026-06-22
- Initial regeneration build order (Phases 0–9) for the python-fastapi chassis at v0.10.0, each task mapped to its files + TEST-SCENARIOS exit criterion.
