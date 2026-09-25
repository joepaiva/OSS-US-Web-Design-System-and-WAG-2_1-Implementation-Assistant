# python-fastapi-mt-fisma-moderate-llm — REQUIREMENTS

**Version:** 1.2.0
**Date:** 2026-09-17
**Status:** Authoritative
**Variant:** Multi-Tenant, FISMA Moderate, with embedded LLM (Chassis Program variant 3 — the pilot package)
**Composed from:** `specs/chassis-program/deltas/{core,tenancy-multi-tenant,fisma-moderate,llm-present}.md`, per `chassis-program-REQUIREMENTS.md` §4. Per `chassis-program-CONSTITUTION.md` §4, this document MUST be byte-identical to `chassis/dotnet-aspnetcore-mt-fisma-moderate-llm/specs/REQUIREMENTS.md` once that package exists (Phase D), and MUST differ from every other variant's `REQUIREMENTS.md`.

> Technology-neutral by contract, matching `chassis/python-fastapi/specs/REQUIREMENTS.md`'s convention. This document, together with this package's own `CONSTITUTION.md`, `DESIGN.md`, `TASKS.md`, and `TEST-SCENARIOS.md`, MUST be sufficient for an automated agent to regenerate this package with zero human intervention.

---

## 1. Purpose & Scope

### 1.1 Purpose
This chassis gives every application built on it a complete, secure, **multi-tenant** foundation at the **FISMA Moderate** control baseline, **with embedded LLM capability** — identity, access control (including mandatory MFA for privileged accounts), tenancy, audit, administration, observability, System Health, Platform Health, a live FISMA self-audit report, and embedded LLM key/model management — so application authors implement only domain logic.

### 1.2 Scope
Covers this package's own capabilities and policies. Does not cover any specific generated application's domain features, the platform that generates applications, or deployment topology (covered by this package's `DESIGN.md` and the platform Deployment Module).

### 1.3 Regeneration mandate
This document + `CONSTITUTION.md` + `DESIGN.md` + `TASKS.md` + `TEST-SCENARIOS.md` MUST be sufficient to regenerate this package with zero human intervention. Any behavior not derivable from these documents is a specification defect.

### 1.4 Conformance language
"MUST"/"MUST NOT" = mandatory. "SHOULD" = strongly recommended, deviations justified in `DESIGN.md`. "MAY" = optional. Conformant when every MUST is satisfied and verified by the test suite.

---

<!-- @chassis-program-delta:core -->

## 2. Actors & Roles

| Actor | Definition |
|---|---|
| **Anonymous** | An unauthenticated caller. |
| **User** | An authenticated principal with a unique identity (email + secret). |
| **Organization** | A tenant. All tenant-scoped data belongs to exactly one organization. |
| **Member** | A user's association with an organization, carrying an optional per-organization role. |
| **Org Administrator** | A member holding the administrative role within a specific organization; scoped to that organization. |
| **Platform Administrator** | A principal with system-wide administrative authority across all organizations. Per FR-AUTH-15, this actor MUST complete MFA verification before reaching any privileged action. |
| **Slot** | Application-specific code added on top of the chassis. |
| **Background Worker** | A non-interactive process that runs deferred jobs. |

## 3. Identity & Authentication (FR-AUTH)

- **FR-AUTH-1** The chassis MUST allow an anonymous actor to **register** an account with, at minimum, a unique identifier (email), a secret (password), and an optional display name. Registration MUST establish an authenticated session on success.
- **FR-AUTH-2** The chassis MUST allow a user to **authenticate** ("log in") with their identifier + secret and receive an authenticated session.
- **FR-AUTH-3** Sessions MUST be conveyed by a **stateless, signed, expiring session token**, verifiable without a database lookup, carrying the subject identity and an expiry.
<!-- @chassis-program-delta:fisma=moderate -->
- **FR-AUTH-4** The default session lifetime MUST be **60 minutes**. Browser sessions MUST also be carried in a cookie whose lifetime matches the token lifetime.
<!-- /@chassis-program-delta:fisma=moderate -->
- **FR-AUTH-5** The browser session cookie MUST be inaccessible to client scripts, MUST be markable as transport-secure (required in production), and MUST default to a same-site policy that mitigates cross-site request forgery.
- **FR-AUTH-6** The chassis MUST accept the session token from **either** a standard `Authorization` bearer header **or** the session cookie, preferring the header.
- **FR-AUTH-7** The chassis MUST allow a user to **log out**, clearing the browser session.
- **FR-AUTH-8** The chassis MUST expose the **current authenticated user's** profile to that user.
- **FR-AUTH-9 (Password storage — SC-13).** Secrets MUST be stored using an **adaptive, salted, one-way hash** with a configurable work factor. Plaintext secrets MUST never be stored or logged.
<!-- @chassis-program-delta:fisma=moderate -->
- **FR-AUTH-10 (IA-5).** At registration, secrets MUST be at least **14 characters** and contain at least **four character classes** (uppercase, lowercase, digit, special). Violations MUST be rejected with a message naming what is missing.
- **FR-AUTH-11 (AC-7).** After **3 failed authentication attempts within a 15-minute window**, the account MUST be locked for **30 minutes**. While locked, authentication MUST be rejected **before** the secret is verified.
<!-- /@chassis-program-delta:fisma=moderate -->
- **FR-AUTH-12 (Anti-enumeration — IA-6).** Authentication failures MUST return an **identical** response whether the identifier is unknown, the account is inactive, the secret is wrong, or the account is locked.
- **FR-AUTH-13 (Account active state — AC-2).** A user MUST have an explicit **active/inactive** state. Inactive users MUST fail authentication.
- **FR-AUTH-14 (Federated identity — extension).** The chassis MUST provide a documented **extension point** for additional authentication providers without modifying chassis-owned code.
<!-- @chassis-program-delta:fisma=moderate -->
- **FR-AUTH-15 (MFA, mandatory — IA-2(1)).** The chassis MUST implement real, chassis-core multi-factor authentication: TOTP enrollment (secret provisioning + QR-compatible payload), a two-step login (password → MFA challenge → verified session), single-use backup recovery codes, self-service disable/regenerate, and admin-initiated reset for a locked-out user. Every account holding **platform-wide administrative privilege** MUST complete MFA verification before it can reach any privileged (admin-gated) action — this applies to platform-scoped admin privilege only, not to a user who merely holds the "admin" role within one organization by virtue of having created it (that grant is org-scoped, not platform-wide, and MFA-gating it would force MFA onto ordinary multi-tenant onboarding). TOTP secrets MUST be encrypted at rest (AES-256-GCM). Backup codes MUST be single-use and invalidated on use.
<!-- /@chassis-program-delta:fisma=moderate -->

## 4. Authorization & Access Control (FR-RBAC)

- **FR-RBAC-1** Access MUST be governed by **named, string-scoped permissions**.
- **FR-RBAC-2** Permissions MUST be grouped into **roles**; users hold roles, roles grant permissions.
- **FR-RBAC-3** The chassis MUST ship at least two seeded roles: an **administrative** role (all permissions) and a **basic user** role (read-only on the chassis's own read permissions).
<!-- @chassis-program-delta:tenancy=multi-tenant -->
- **FR-RBAC-4** Roles MAY be granted **system-wide** (independent of any organization) **or per-organization** (via membership). A permission check MUST pass if **either** path grants it.
<!-- /@chassis-program-delta:tenancy=multi-tenant -->
- **FR-RBAC-5** A **superuser** flag MUST short-circuit all permission checks to "granted".
- **FR-RBAC-6** The chassis MUST seed all of its own permissions and roles **idempotently at startup**.
- **FR-RBAC-7** The chassis MUST provide a **declarative permission gate** for routes.
- **FR-RBAC-8** The chassis MUST provide a **permission registry** with a documented **extension point** so slots can declare new permissions that auto-seed on next startup.
- **FR-RBAC-9** All authorization decisions MUST be enforced **server-side**.

<!-- /@chassis-program-delta:core (resumes after tenancy) -->
<!-- @chassis-program-delta:tenancy=multi-tenant -->

## 5. Multi-Tenancy (FR-TEN)

- **FR-TEN-1** The chassis MUST model **organizations** (tenants), each with a human name and a unique URL-safe slug.
- **FR-TEN-2** A user MAY belong to **zero or more** organizations. Each membership MAY carry a per-organization role and a **default-context** flag.
- **FR-TEN-3** The chassis MUST deterministically resolve a user's **current/default organization** (explicit default first, else the earliest membership).
- **FR-TEN-4** A user MUST be able to **create** an organization (becoming its first administrator) and **list** the organizations they belong to.
- **FR-TEN-5** A user MUST be able to **switch** their default organization; switching MUST be restricted to organizations they are a member of and MUST be audited.
- **FR-TEN-6 (Isolation invariant).** Every tenant-scoped record MUST belong to exactly one organization. Reads MUST be **automatically filtered** to the current organization and writes **automatically stamped** with it. Cross-tenant access by a non-privileged caller MUST be impossible.
- **FR-TEN-7 (Cross-tenant response policy).** A request for a resource that exists but belongs to another tenant MUST be indistinguishable from "not found".
- **FR-TEN-8** A documented **escape hatch** MUST exist for legitimate cross-tenant operations (administration, background jobs) that is explicit and auditable, never the default.

<!-- /@chassis-program-delta:tenancy=multi-tenant -->
<!-- @chassis-program-delta:core -->

## 6. Audit & Accountability (FR-AUD)

- **FR-AUD-1 (AU-2/AU-12).** Every **privileged mutation** MUST produce an audit record via a single, declarative mechanism.
- **FR-AUD-2 (AU-3 content).** Each audit record MUST capture: action, acting user, organization, entity type+id, structured details, client IP, timestamp.
- **FR-AUD-3 (AU-8).** Audit timestamps MUST be timezone-aware, canonical UTC.
- **FR-AUD-4** Audit records MUST be written **only on success**.
- **FR-AUD-5** A missing session/context at an audit site MUST degrade to "skip the audit with a warning".
- **FR-AUD-6 (AU-9).** Audit records SHOULD be protected against in-place modification and deletion by the application's own runtime role.
<!-- @chassis-program-delta:fisma=moderate -->
- **FR-AUD-7 (AU-11).** The chassis MUST provide a retention/archival job moving audit records older than **365 days** (operator-extendable) online into cold storage. Idempotent, reports records moved.
<!-- /@chassis-program-delta:fisma=moderate -->
- **FR-AUD-8 (AU-6).** A permission MUST exist that authorizes reading the audit log.

## 7. Administration Shell (FR-ADM)

- **FR-ADM-1** The chassis MUST provide a server-rendered **administration interface**, gated so a basic user cannot reach it.
- **FR-ADM-2 (User Management).** Administrators MUST be able to **list, create, deactivate, and reactivate** users. Platform administrators see all users; org administrators see only their organization's members. **An org administrator's WRITE reach MUST be scoped identically to their read reach: every user mutation — deactivate and reactivate included — MUST resolve its target through the administrator's own organization's membership, never by user id alone. A target outside that organization MUST be refused as "not found" (never a distinguishable 403) and MUST NOT be mutated — the refusal and the non-mutation are two separate requirements, and a handler that mutates and then reports a refusal satisfies neither.** An administrator MUST NOT be able to deactivate their own account. All mutations audited.
- **FR-ADM-3 (Organization Management).** Platform administrators MUST be able to **list and create** organizations, hidden from org-only administrators.
- **FR-ADM-4 (Scoping).** Every admin page MUST resolve the caller's scope (platform vs organization) and present only permitted data/actions.
- **FR-ADM-5 (Extensibility).** The admin shell MUST provide a documented **extension point** for slots to add their own admin pages under the same authorization model.

## 8. Observability & Health (FR-OBS) and System Health (FR-SYSHEALTH)

- **FR-OBS-1 (Liveness).** A liveness endpoint returning success whenever the process is serving requests.
- **FR-OBS-2 (Readiness).** A readiness endpoint checking downstream dependencies.
- **FR-OBS-3 (Version).** A version endpoint reporting application + chassis version.
- **FR-OBS-4 (Request correlation).** Every request stamped with a correlation id.
- **FR-OBS-5 (Structured logging).** All logs structured, auto-including correlation id and user/org context.
- **FR-SYSHEALTH-1..3** The admin shell MUST include a **System Health** page (platform-administrator only) reporting datastore connectivity + latency, cache/queue connectivity, and background-worker liveness (time since last completed cycle).
<!-- @chassis-program-delta:llm=present -->
- **FR-SYSHEALTH-4** System Health MUST additionally report the configured LLM proxy's reachability via a lightweight, non-billed probe.
<!-- /@chassis-program-delta:llm=present -->
- **FR-SYSHEALTH-5** System Health MUST report the running `CHASSIS_VERSION` and last successful startup timestamp.
- **FR-SYSHEALTH-6** Checks run synchronously, bounded time (default 5s total), degrade gracefully.
- **FR-SYSHEALTH-7** Gated behind the existing admin permission check; itself an audited read (this package is FISMA Moderate).
- **FR-SYSHEALTH-8** A documented extension point for a slot to register an additional dependency check.

## 9. In-App Documentation (FR-DOC)

- **FR-DOC-1** A Documentation section rendering an overview, user manual, and the live FISMA self-audit report (FR-FISMAAUDIT) alongside the static reference document.
- **FR-DOC-2 (Safety).** Only an explicit whitelisted set of documents servable; path traversal structurally impossible.
- **FR-DOC-3 (Rendering).** Rendered markup produced safely; unknown selection returns "not found".

<!-- /@chassis-program-delta:core -->
<!-- @chassis-program-delta:llm=present -->

## 10. Embedded LLM Capability (FR-LLM)

> Provided so generated applications can call large language models without each app re-solving key management. Mirrors the platform's key-handling discipline ("Rule 7 parity").

- **FR-LLM-1 (Keys at rest — SC-28).** Provider API keys MUST be stored **encrypted at rest** using authenticated symmetric encryption. Plaintext keys MUST never be stored, logged, or returned to a client.
- **FR-LLM-2 (No keys in config).** Provider keys MUST live only in the datastore. The **only** key-related value permitted in configuration is the **wrapping/encryption key**, never a provider key.
- **FR-LLM-3 (Key scopes).** Keys MUST be storable at two scopes: **per-organization** and **platform-shared**.
- **FR-LLM-4 (Resolution chain).** For a given provider and organization: **organization's own active key** → **platform-shared active key, only if policy grants access** → otherwise **reject**. Shared access MUST default to **denied**.
- **FR-LLM-5 (Platform-controlled access).** Platform administrators MUST control which organizations may use the shared key.
- **FR-LLM-6 (One route out).** All model calls MUST go through a **single, provider-neutral egress** (OpenAI-compatible by configuration), with the resolved key injected per request.
- **FR-LLM-7 (Wrapping-key safety).** In production, the chassis MUST **fail closed** if the encryption-wrapping key is left at its in-code default, checked at **use time**.
- **FR-LLM-8 (Admin management).** Org administrators manage their organization's keys; platform administrators additionally manage shared keys and per-organization access policy. Stored keys displayed **masked**. Mutations audited.
- **FR-LLM-9 (Single active key).** At most one key per (scope, provider) active at a time.

<!-- /@chassis-program-delta:llm=present -->
<!-- @chassis-program-delta:core -->

## 11. File Storage (FR-FILE)

- **FR-FILE-1** An **organization-scoped** file capability: upload, list, download, delete, scoped to the caller's current organization.
- **FR-FILE-2 (Isolation).** A caller MUST only see and act on files of their current organization; another organization's file is "not found" (ties to FR-TEN-7).
- **FR-FILE-3 (Metadata + integrity).** Filename, content type, size, integrity hash, owner, organization recorded.
- **FR-FILE-4 (Size cap).** A single upload capped at a configurable maximum.
- **FR-FILE-5 (Storage safety).** Opaque, system-generated identifier; no user-controlled path component. Mutations audited.
- **FR-FILE-6** Unauthenticated callers rejected; callers with no organization context receive a clear error.

## 12. Notifications (FR-NOTE)

- **FR-NOTE-1** Per-user in-app notifications: title, body, severity level, read state.
- **FR-NOTE-2 (Producer).** A producer function slots and subsystems call to create a notification.
- **FR-NOTE-3 (Consumer API).** List (optionally unread-only), unread count, mark-one-read, mark-all-read.
- **FR-NOTE-4 (Isolation).** Scoped to the requesting user only.
- **FR-NOTE-5** An unknown severity level degrades to "informational".

## 13. Rate Limiting (FR-RL)

- **FR-RL-1 (SC-5).** Per-client request rate limiting as edge middleware.
- **FR-RL-2 (Opt-in).** Configurable, default-off.
- **FR-RL-3 (Behavior).** "Too many requests" status with retry-after hint.
- **FR-RL-4 (Exemptions).** Health, version, static-asset paths exempt.
- **FR-RL-5 (Fail-open).** Limiter backing-store outage → requests allowed, condition logged.

## 14. Reporting (FR-REP)

- **FR-REP-1** A read-only Reports page: users, organizations (platform scope), audit events, files, notifications, and active LLM keys.
- **FR-REP-2 (Scope).** Platform administrators see global figures; org administrators see only their organization's slice. Read-only.

## 15. Transactional Messaging (FR-MAIL)

- **FR-MAIL-1** A send-message service with a console/log backend (dev) and a real transport backend (prod).
- **FR-MAIL-2** Both backends log a delivery record; return a structured delivery result.

## 16. Background Jobs (FR-JOB)

- **FR-JOB-1** A deferred-job mechanism (queue + worker) for long-running/asynchronous work.
- **FR-JOB-2** Slots enqueue jobs via a documented helper; chassis ships at least the audit-retention job.
- **FR-JOB-3** A job-backend outage MUST NOT break foreground request handling.

## 17. Frontend & Accessibility (FR-UI)

- **FR-UI-1 (Server-rendered).** No client-side SPA framework, no build/transpile step in the serve path.
- **FR-UI-2 (Design system).** An accessible, government-grade design system, consistent base layout.
- **FR-UI-3 (Accessibility — Section 508 / WCAG 2.1 AA).** Semantic controls, labelled inputs, skip-link, ARIA live regions, accessible dialogs, sufficient contrast, 44×44px touch targets, no mobile auto-zoom.
- **FR-UI-4 (Responsive).** Mobile-first, no horizontal scrolling.
- **FR-UI-5 (Canonical page states).** Reusable loading/empty/error state presentations.
- **FR-UI-6 (System-use banner — AC-8).** Configurable system-use notification banner on login.
- **FR-UI-7 (Government banner).** Conditional official-government-site banner.

## 18. Error Handling & User Messaging (FR-ERR)

- **FR-ERR-1 (SI-11).** Production uncaught errors return a generic message + correlation id, no internal detail; always fully logged internally.
- **FR-ERR-2 (Canonical messages).** User-facing messages from a single canonical catalog.

## 19. Extensibility / Slots (FR-EXT)

- **FR-EXT-1** Application-specific code lives in isolated slots; no editing chassis-owned files outside marked extension points.
- **FR-EXT-2 (Extension points).** At minimum: slot routes, slot permissions, additional auth providers, admin pages.
- **FR-EXT-3 (Canonical slot shape).** At least one reference slot and one state-machine-pattern slot.
- **FR-EXT-4 (Slot guardrails).** Strict typing, modern-idiom linting, forbidden legacy patterns; slot tests cover happy-path, auth gate, permission gate, isolation, validation.

## 20. Configuration & Secrets (FR-CFG)

- **FR-CFG-1** Configuration loads from the environment into a single typed settings object.
<!-- @chassis-program-delta:llm=present -->
- **FR-CFG-2 (Secret hardening — SC-12).** Session-signing secret validated; rejects placeholders in any environment, refuses to boot in production with the dev default. Same discipline for the LLM wrapping key at use time.
<!-- /@chassis-program-delta:llm=present -->
- **FR-CFG-3 (No secrets in source).** No provider key or production secret committed to source/config/images.
- **FR-CFG-4 (Datastore URL normalization).** Accepts common managed-platform URL forms, normalizes to the driver form.

## 21. Data Retention (FR-RET)

- **FR-RET-1 (SI-12).** Bounded, explicit retention: audit via the archival job, a documented per-record mechanism for domain data.
- **FR-RET-2** Retention explicit — not silent deletion.

## 22. Database & Migrations (FR-DB)

- **FR-DB-1** Single relational datastore, typed data-access layer, per-request transaction boundaries.
- **FR-DB-2 (Additive-only migrations).** Ordered, additive-only. Committed migrations never edited in place.
- **FR-DB-3** Seed data applied idempotently in code at startup, not embedded in migrations.

## 23. Platform Health (FR-PLATHEALTH)

Per `specs/chassis-program/shared-capabilities/PLATFORM-HEALTH-REQUIREMENTS.md`: an admin-only capability inventorying this package's own embedded dependencies (via `uv.lock`/`pip-audit`), reporting currency against latest stable, scanning for known vulnerabilities, and offering a gated remediation flow (verify via build+test; auto-apply only for patch/minor bumps under explicit opt-in; major bumps always held for approval). On-demand + daily-scheduled triggers; fails closed (never reports false-clean) when its data source is unreachable. This is also the runtime enforcement arm of the zero-CVE/latest-stable mandate.

## 24. FISMA Controls Self-Audit and Report (FR-FISMAAUDIT)

Per `specs/chassis-program/shared-capabilities/FISMA-SELF-AUDIT-REPORT-REQUIREMENTS.md`: an admin-only, on-demand report generator running a registry of runtime checks against this package's actual **FISMA-Moderate** control set (`FISMA-CONTROL-DELTA-LOW-VS-MODERATE.md`'s Moderate column) — including whether MFA is actually enforced for the admin role (attempted-without-second-factor test), the actual configured lockout/session/password/retention values, and this package's own current zero-CVE status via FR-PLATHEALTH. Four outcomes per check: Pass, Fail, Not Applicable, Operator Responsibility. Report history persisted. Advisory only.

## 25. MCP Client Capability (FR-MCPCLIENT)

<!-- @chassis-program-delta:llm=present -->

Per `specs/chassis-program/shared-capabilities/MCP-CLIENT-REQUIREMENTS.md`: lets the chassis's embedded-LLM chat-completion call path discover and invoke tools exposed by admin-registered external MCP (Model Context Protocol) servers — **client role only**; the chassis never exposes its own data/actions as an inbound MCP server. An org admin registers a connection (display name, server URL, optional credential) that **defaults to disabled** — registering ≠ exposing; only an org's own **enabled** connections are ever discovered or invoked, and only for that org (FR-TEN parity — never another org's connection). Any stored credential is encrypted at rest using the **exact same** encryption mechanism, key management, and wrap-key source as FR-LLM's existing provider-key encryption (FR-MCPCLIENT-2) — a second, divergent encryption implementation is a defect, not a valid alternate design. When an org has zero enabled connections, tool discovery is skipped entirely and the existing chat-completion call path is byte-for-byte unchanged — no `tools` parameter added, no added latency. When one or more tools are discovered, each is qualified as `<connection-name>.<tool-name>` (resolves same-name collisions across servers) and advertised to the LLM via the chassis's existing tool-calling mechanism as a real extension of the existing call, never a parallel path. A tool-call response is invoked against the owning MCP server and its result folded back into the conversation as a tool-result message; the loop continues until a final non-tool-call response or a small, fixed iteration cap is reached. Failure handling is mandatory, not optional polish: an unreachable server at discovery time is logged and excluded (the request continues with whatever other tools discovered successfully); an auth/authorization failure from a tool invocation is reported back into the conversation as a tool-result error, never an unhandled exception, never a silent retry with a different credential; a tool-execution failure (error, timeout, malformed result) is reported the same way. All MCP network calls (discovery and invocation) are bounded by a request timeout, the same class of setting as the existing LLM request timeout. CRUD (create/list/update/delete/enable/disable) is org-admin-scoped, gated by the chassis's existing admin authorization/RBAC middleware (no new permission model), audited on every mutation (the credential value itself never appears in an audit record, log line, or error message), and displayed masked — the identical admin-UI visual/interaction pattern as FR-LLM's key screen (server-rendered form-POST, not a new UI style).

<!-- /@chassis-program-delta:llm=present -->

## 26. Non-Functional Requirements (NFR)

- **NFR-PERF-1 (Page load).** ≤2.5s p95 slow mobile; ≤1.0s p95 broadband.
- **NFR-PERF-2 (API latency).** ≤250ms p95 reads; ≤800ms p95 writes.
- **NFR-AVAIL-1 (Availability).** ≥99.5% monthly single-region; additive-only migrations enable zero-downtime deploys.
- **NFR-SCALE-1 (Concurrency).** ≥100 concurrent active sessions per instance.
- **NFR-INTEG-1 (Data integrity).** Every audited mutation transactional; correlation ids enable tracing.
<!-- @chassis-program-delta:fisma=moderate -->
- **NFR-SEC-1 (Security baseline).** The chassis MUST satisfy the **Moderate**-baseline control set enumerated in `FISMA-CONTROL-DELTA-LOW-VS-MODERATE.md`, verified on demand by FR-FISMAAUDIT, and MUST document operator-responsibility gaps.
<!-- /@chassis-program-delta:fisma=moderate -->
- **NFR-A11Y-1 (Accessibility).** Section 508 / WCAG 2.1 AA, automated checks at representative viewports.
- **NFR-MAINT-1 (Maintainability).** Strict typing + modern-idiom linting on slot code; every capability covered by automated tests.
- **NFR-OBS-1 (Observability).** Structured logs, correlation, liveness/readiness/version endpoints, System Health page.

<!-- /@chassis-program-delta:core -->

## 27. Traceability

Each FR is realized by this package's `DESIGN.md` (technology-specific mapping) and verified by `TEST-SCENARIOS.md`. This package's compliance posture against AC/AU/IA/SC/SI at the FISMA-Moderate baseline, including MFA (IA-2(1)) as **Implemented** (not Operator, unlike the reference chassis) and SI-2/SI-3 as **Implemented** under the zero-CVE mandate, is recorded in `docs/SECURITY-SELF-AUDIT.md` and, live, by the FR-FISMAAUDIT report.

---

## CHANGELOG

**v1.2.0 (2026-09-17) — FR-ADM-2 states the admin WRITE scope, not only the read scope.** MINOR: FR-ADM-2 previously specified that org administrators *see* only their own organization's members, and said nothing about which users they may *mutate*. That silence was load-bearing: three of the four stacks independently implemented the safe behaviour anyway, while the Python stack implemented exactly what was written and shipped a cross-tenant privilege escalation — an org administrator could deactivate or reactivate any user on the platform by id, including another tenant's members, proven by execution on 2026-09-17 (303 See Other, `is_active` True→False, while the same user was correctly absent from that administrator's own listing). The requirement now states the write scope explicitly, requires membership-based target resolution, and separates the two obligations a guard must meet: refuse as "not found", AND do not mutate. No behavioural change to any package whose code already met this; the Python packages' fix is in their own CHANGELOGs. Task Log: `specs/platform/Task Logs/2026-09-17-313-python-chassis-execution-proof-and-admin-tenancy-gap.md`.

**v1.1.1 (2026-09-10) — Cross-stack REQUIREMENTS.md reconciliation:** No new requirements. The initial v1.1.0 FR-MCPCLIENT addition was authored independently by two parallel implementing agents (one per stack) and had drifted from `chassis-program-CONSTITUTION.md` §4's "byte-identical to the sibling stack's same-variant `REQUIREMENTS.md`" rule (self-flagged in `specs/platform/Task Logs/2026-09-10-003-mcp-client-support.md`'s Completion Report, independently confirmed by diff). Reconciled so this document is now byte-identical to `chassis/dotnet-aspnetcore-mt-fisma-moderate-llm/specs/REQUIREMENTS.md`, apart from this document's own title line. No FR/NFR content changed in substance.

**v1.1.0 (2026-09-10) — MCP Client Capability (FR-MCPCLIENT):** Adds §25, realizing `specs/chassis-program/shared-capabilities/MCP-CLIENT-REQUIREMENTS.md` (FR-MCPCLIENT-1..14) for this package — client-only tool discovery/invocation against admin-registered external MCP servers, org-scoped, per-connection enabled/disabled (default disabled), credential encryption reusing FR-LLM's mechanism exactly, mandatory graceful degradation on unreachable/auth-failed/erroring servers, and the FR-LLM admin-UI pattern reused rather than a new style. Renumbers former §25/§26 (NFR/Traceability) to §26/§27. Operator-approved per `MCP-PROTOCOL-OPTIONS-ANALYSIS.md` §5 (2026-09-10). Task Log: `specs/platform/Task Logs/2026-09-10-003-mcp-client-support.md`.

**v1.0.0 (2026-09-02) — Initial:** First authoring, assembled from `specs/chassis-program/deltas/{core,tenancy-multi-tenant,fisma-moderate,llm-present}.md` per `chassis-program-REQUIREMENTS.md` §4. Forked from `chassis/python-fastapi/specs/REQUIREMENTS.md` v1.0.0 (2026-06-22). Adds real, chassis-core MFA (FR-AUTH-15) closing the gap the reference chassis left as operator-responsibility. Task Log: `specs/platform/Task Logs/2026-09-02-003-chassis-program-phase-b-pilot.md`.
