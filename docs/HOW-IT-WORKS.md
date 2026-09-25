# How This Application Works

**Audience:** operators, administrators, and reviewers of an application built on the
autonomous-platform Python chassis (Stack Template #1).

This document explains what the application provides out of the box, how the moving
parts fit together, and where to look when something goes wrong. It describes the
**chassis** — the shared foundation every generated app inherits. Application-specific
behavior (the "slots") is documented separately by the team that built the app.

---

## 1. The big picture

The application is a FastAPI service backed by PostgreSQL and Redis. It ships with a
complete identity, access-control, and administration layer so that application authors
only have to build their domain features on top.

```
Browser ──HTTPS──▶ Reverse proxy ──▶ FastAPI app ──▶ PostgreSQL
                                          │
                                          └────────▶ Redis (background jobs)
```

Everything below "FastAPI app" is provided by the chassis. The chassis is versioned
independently (see the version shown on the **System Health** admin page).

---

## 2. What you get for free

| Capability | Where it lives | Notes |
|---|---|---|
| User registration + login | `/auth/register`, `/auth/login` | JWT access tokens, secure cookie session |
| Account lockout | auth service | 3 failed logins / 15 min → 30 min lockout (AC-7) |
| Password complexity | auth schemas | 14-char minimum, 4 character classes (IA-5) |
| Role-based access control | `app/rbac/` | `admin` / `user` roles, colon-scoped permissions |
| Organizations (multi-tenant) | `app/orgs/` | Each user can belong to one or more orgs |
| Admin shell | `/admin` | User + Org management, System Health, Documentation |
| Audit logging | `app/audit/` | Every privileged mutation recorded with actor + IP |
| Embedded LLM | `app/llm/` | Encrypted provider keys (per-org + shared), routed through LiteLLM |
| File storage | `/api/files` | Org-scoped upload/download with SHA-256 + size cap |
| Notifications | `/api/notifications` | Per-user in-app notifications with read state |
| Rate limiting | `app/ratelimit/` | Opt-in Redis per-client limiter (SC-5) |
| Reporting | `/admin/reports` | Scoped usage figures for admins |
| Health & readiness probes | `/healthz`, `/readyz`, `/version` | For orchestrators and the System Health page |
| Accessible UI | USWDS 3.x templates | Section 508 / WCAG 2.1 AA defaults |

---

## 3. Identity and access control

**Authentication.** Users authenticate with email + password. On success the app issues a
short-lived JWT (default 60 minutes) and sets an `httponly` cookie. The browser admin
shell uses the cookie; API clients send `Authorization: Bearer <token>`.

**Authorization.** Access is governed by RBAC:

- **Permissions** are colon-scoped strings (`users:read`, `users:write`, `orgs:write`,
  `audit:read`, …). The full list lives in `app/rbac/permissions.py`.
- **Roles** bundle permissions. The chassis seeds two: `user` (read-only) and `admin`
  (full management). Roles are seeded automatically on startup — idempotent.
- A **platform admin** is a superuser, or a holder of the chassis-wide `admin` role. An
  **org admin** holds the `admin` role on a specific organization's membership and is
  scoped to that org.

**Multi-tenancy.** Data is partitioned by organization. Org admins only ever see their own
org's users; platform admins see everything. Every audit record carries the acting org so
cross-tenant actions are distinguishable.

---

## 4. The admin shell

Reachable at **`/admin`** by any administrator. Pages:

- **User Management** (`/admin/users`) — platform admins manage all users; org admins
  manage their org's members. Create, deactivate, reactivate. You cannot deactivate your
  own account.
- **Organization Management** (`/admin/orgs`) — platform admins only. List + create orgs.
- **System Health** (`/admin/system-health`) — platform admins only. Live status of the
  application version, environment, database, and Redis. See §6.
- **LLM Provider Keys** (`/admin/llm`) — manage encrypted provider API keys. Org admins
  manage their organization's keys; platform admins also manage the shared key and which
  organizations may use it. See §5.5.
- **Documentation** (`/admin/docs`) — this guide, the user manual, the overview, and the
  security self-audit, rendered in-app.

The shell is gated on the `users:write` permission, so a plain `user` cannot reach it.

---

## 5. Background jobs

Long-running or deferred work runs on a Redis-backed RQ queue (`app/tasks/`). The chassis
ships one built-in job: **audit-log archival** (AU-11), which moves audit rows older than
the retention window (default 365 days online) into a cold-storage table. Application
slots register their own jobs at the documented extension point.

If Redis is unreachable, foreground request handling is unaffected, but queued work will
not run. The System Health page surfaces Redis reachability.

---

## 5.5 Embedded LLM

The chassis can call large language models on behalf of application features, with keys it
manages securely:

- **Encrypted keys.** Provider API keys (Anthropic, OpenAI, Gemini, …) are stored
  **AES-256-GCM encrypted** in the database — never in environment variables or config
  files. They are entered and managed only through the admin shell at `/admin/llm`.
- **Per-org and shared keys.** Each organization can hold its own key. A platform-shared
  key can serve organizations that have none — but only the ones a platform admin has
  explicitly granted shared access (default is denied).
- **Resolution order.** For each request the chassis tries the organization's own key
  first, then the shared key (if that org is allowed), then fails cleanly if neither exists.
- **One route out.** Every completion goes through a single OpenAI-compatible endpoint
  (a LiteLLM proxy by default, set by `LLM_PROXY_URL`), with the resolved key injected per
  request — so no provider key is ever hard-coded and many tenants can share one proxy.

The only LLM-related secret in configuration is `LLM_ENCRYPTION_KEY`, the key used to wrap
the provider keys at rest. In production the app refuses to encrypt with the built-in
default, so a real deployment must supply its own.

---

## 5.6 MCP Client — letting the embedded LLM call external tools

The chassis can let its embedded LLM discover and call tools exposed by external MCP
(Model Context Protocol) servers mid-conversation — a company's internal ticketing system,
knowledge base, or CRM, for example. This is **client-only**: the chassis never exposes its
own data or actions as an inbound MCP server.

- **Registration, admin-managed.** An org admin registers a connection at `/admin/mcp`: a
  display name, the server's URL, and an optional credential (a bearer token/API key the
  target MCP server itself requires — many internal MCP servers need none). A new connection
  is **disabled by default**; registering it does not, by itself, expose its tools.
- **Encrypted credentials, same mechanism as LLM keys.** A stored credential is AES-256-GCM
  encrypted using the exact same encryption service as the embedded-LLM provider keys above
  — there is no separate MCP wrap key. A server with no credential (an unauthenticated
  internal server) is a fully valid configuration.
- **Org-scoped, never shared.** Unlike an LLM provider key, an MCP server connection has no
  platform-shared variant — every connection belongs to exactly one organization, and only
  that organization's own **enabled** connections are ever discovered or called.
- **A real extension of the existing chat call, not a parallel system.** When an org has one
  or more enabled connections, the chassis discovers their tools before the next
  chat-completion call and offers them to the LLM using the same tool-calling mechanism the
  LLM proxy already supports. If the LLM asks to call one, the chassis invokes it against the
  owning MCP server, feeds the result back into the conversation, and lets the LLM continue —
  bounded to a handful of rounds so a misbehaving tool or model can never spin a request
  forever. An org with **zero** enabled connections sees no change at all: no extra step, no
  added latency, the exact chat-completion call that existed before this capability.
- **Graceful degradation, always.** An unreachable MCP server is logged and skipped — the
  rest of the org's tools (and the chat request itself) are unaffected. A tool call that
  fails for any reason (the target rejects the credential, the tool itself errors, it times
  out) comes back to the LLM as a normal tool-result error, never a crash.
- **A live demo.** The bundled Greeting Service slot (`/greet`) ships a fixture-backed demo:
  register and enable a connection pointing at an MCP server exposing a "regional greeting
  convention" lookup tool, request a translation into an unsupported locale with the "Use LLM
  translation" box checked, and the greeting page's result line shows which tool(s) the LLM
  actually called — visibly different from the same request with MCP left off.

Every MCP network call (discovery and invocation) is bounded by a request timeout — the same
class of setting as the LLM request timeout above — so a hung external MCP server can never
hang a chat request.

---

## 6. Observability and health

Three machine-readable endpoints:

- **`GET /healthz`** — liveness. Returns `200 {"status":"ok"}` whenever the process is
  serving requests. Use this for restart probes.
- **`GET /readyz`** — readiness. Pings PostgreSQL; returns `503` when a dependency is
  down so a load balancer routes traffic away.
- **`GET /version`** — the app version and the chassis version it was generated against. (Known issue: the chassis-version field currently surfaces the app package version; CHASSIS_VERSION wiring is pending.)

The **System Health** admin page presents the same signals in a human-readable form, plus
the Redis status, for quick operational triage.

Every request is stamped with an `X-Request-ID` (echoed in the response header and bound to
every log line) so a single request can be traced end-to-end through the structured logs.

---

## 7. When something goes wrong

| Symptom | First check |
|---|---|
| App won't start | Logs for `chassis.rbac.seed_failed`; confirm `DATABASE_URL` + a real `JWT_SECRET` in prod |
| Logins all fail | System Health → database status; confirm migrations ran |
| "Account locked" banner | Expected after repeated failed logins (AC-7); wait out the window |
| Background jobs not running | System Health → Redis status; confirm the RQ worker is running |
| `/readyz` returns 503 | A dependency (DB) is unreachable — the `checks` object names which |

For control-by-control security posture, see **SECURITY-SELF-AUDIT.md**.
