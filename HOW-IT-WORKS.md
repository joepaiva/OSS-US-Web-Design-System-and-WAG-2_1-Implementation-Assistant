# HOW-IT-WORKS.md — Accessibility Assistant

## Architecture Overview

This document describes the internal architecture of the Accessibility Assistant — how its components fit together, how data flows through the system, and how the platform chassis integrates with the application's domain logic. It is intended for developers, architects, and operators who need to understand the system at a structural level.

---

## 1. System Context

The Accessibility Assistant is a multi-tenant, FISMA-Moderate web application that helps users evaluate digital content and interfaces for accessibility compliance. Users submit content (text, URLs, or uploaded files) for analysis; the application orchestrates calls to a Large Language Model (LLM) to produce structured accessibility findings, remediation guidance, and compliance summaries. All activity is scoped to an organization (tenant), fully audited, and access-controlled via role-based permissions.

```
┌─────────────────────────────────────────────────────────┐
│                        Browser                          │
│          (USWDS-based server-rendered HTML + HTMX)      │
└────────────────────────┬────────────────────────────────┘
                         │ HTTPS
┌────────────────────────▼────────────────────────────────┐
│                   FastAPI Application                   │
│                   (Uvicorn / ASGI)                      │
│  ┌──────────────────────────────────────────────────┐   │
│  │         Platform Chassis (Immutable Core)        │   │
│  │  Auth · RBAC · Multi-Tenancy · Audit · Admin     │   │
│  │  LLM Gateway · Rate Limiting · Observability     │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │          Application Slot Code                   │   │
│  │   app/slots/  (domain logic, routes, models)     │   │
│  └──────────────────────────────────────────────────┘   │
└──────┬─────────────────┬───────────────────┬────────────┘
       │                 │                   │
┌──────▼──────┐  ┌───────▼──────┐  ┌────────▼───────┐
│ PostgreSQL  │  │    Redis     │  │  LLM Provider  │
│ (primary    │  │ (sessions,   │  │ (OpenAI-compat │
│  datastore) │  │  cache,      │  │  API endpoint) │
│             │  │  rate limit) │  │                │
└─────────────┘  └──────────────┘  └────────────────┘
```

---

## 2. Platform Chassis vs. Application Slot Code

The application is built on the **autonomous-platform-chassis-python**, a pre-built, security-hardened foundation. The chassis is immutable — it provides cross-cutting capabilities that the application consumes but does not re-implement.

### 2.1 What the Chassis Provides

| Capability | Mechanism |
|---|---|
| Identity & Authentication | JWT (Bearer + HttpOnly cookie), bcrypt password hashing, TOTP MFA for platform admins |
| Authorization (RBAC) | `resource:action` permission model; `Depends(require_permission(...))` FastAPI dependency |
| Multi-Tenancy | Organization model with slugs; current-org resolution from subdomain, header, or path prefix |
| Audit Logging | Immutable append-only `AuditLog` table; every mutating action records actor, org, resource, before/after |
| LLM Gateway | Single egress point for all LLM calls; prompt logging, token metering, retry/backoff, provider abstraction |
| Rate Limiting | Redis-backed sliding-window counters per user and per org |
| Administration Shell | `/admin/` UI for user, org, role, and permission management |
| Observability | Structured JSON logs, Prometheus metrics endpoint, OpenTelemetry trace instrumentation |
| Background Tasks | ARQ (async Redis Queue) worker pool for long-running jobs |
| Settings & Config | Pydantic `BaseSettings`; environment-variable-driven; validated at startup |

### 2.2 What the Application Slot Code Provides

All domain logic lives under `app/slots/`. Each slot is a self-contained module that registers its own:

- SQLAlchemy ORM models (extending the chassis `Base`)
- Alembic migration scripts
- FastAPI routers (mounted into the main app)
- Jinja2 templates (extending the chassis base layout)
- RBAC permission declarations (auto-seeded at startup)
- ARQ background task definitions

The application defines the following primary slots:

| Slot | Responsibility |
|---|---|
| `submissions` | Intake of content for analysis (text, URL, file upload) |
| `analyses` | Orchestration of LLM-based accessibility evaluation |
| `findings` | Storage and presentation of structured accessibility findings |
| `reports` | Aggregation, export, and sharing of analysis results |
| `remediation` | LLM-assisted guidance for fixing identified issues |

---

## 3. Request Lifecycle

### 3.1 Authenticated Page Request

```
Browser
  │
  ▼
FastAPI Router
  │
  ├─► Chassis Middleware Stack
  │     • TenantResolutionMiddleware  → sets request.state.org
  │     • SessionMiddleware           → validates JWT / cookie
  │     • AuditContextMiddleware      → attaches actor context
  │
  ├─► Route Handler (slot code)
  │     • Depends(get_current_user)   → resolves authenticated user
  │     • Depends(require_permission) → enforces RBAC; 403 if denied
  │     • Depends(get_async_session)  → injects AsyncSession
  │     │
  │     ├─► Domain Service (slot)
  │     │     • Queries PostgreSQL via SQLAlchemy async
  │     │     • All queries scoped to current org (tenant isolation)
  │     │
  │     └─► Jinja2 Template Render
  │           • Extends chassis base layout (USWDS components)
  │           • Returns HTML response
  │
  └─► AuditLog write (post-response, async)
```

### 3.2 LLM-Assisted Analysis Request

When a user submits content for accessibility analysis, the flow involves both synchronous intake and asynchronous background processing:

```
Browser (form submit)
  │
  ▼
POST /submissions/
  │
  ├─► Validate input (Pydantic schema)
  ├─► Persist Submission record (status=PENDING)
  ├─► Enqueue ARQ background task
  └─► Redirect to submission detail page (202 Accepted pattern)

ARQ Worker (background)
  │
  ├─► Fetch Submission from PostgreSQL
  ├─► Update status → PROCESSING
  │
  ├─► Chassis LLM Gateway
  │     • Constructs structured prompt (system + user messages)
  │     • Enforces per-org token budget (Redis counter)
  │     • Calls LLM provider API (httpx.AsyncClient)
  │     • Logs prompt + response to chassis prompt log table
  │     • Returns structured JSON response
  │
  ├─► Parse LLM response → Finding records
  │     • Maps to WCAG criteria, severity levels, affected elements
  │     • Persists Finding rows linked to Submission + Org
  │
  ├─► Update status → COMPLETE (or FAILED with error detail)
  └─► (Optional) Trigger notification

Browser (polling or HTMX push)
  └─► GET /submissions/{id} → renders findings when COMPLETE
```

---

## 4. Data Model

### 4.1 Chassis-Provided Tables

These tables are owned by the chassis and must not be modified by slot code:

| Table | Purpose |
|---|---|
| `users` | Authenticated identities; email, hashed password, MFA state |
| `organizations` | Tenants; name, slug, settings |
| `memberships` | User ↔ Organization associations with per-org role |
| `roles` / `permissions` | RBAC definitions |
| `audit_logs` | Immutable activity record |
| `llm_prompt_logs` | Record of every LLM request/response with token counts |

### 4.2 Application Domain Tables

```
organizations (chassis)
  │
  ├──< submissions
  │       id, org_id, created_by_user_id
  │       content_type (TEXT | URL | FILE)
  │       content_text, content_url, file_path
  │       status (PENDING | PROCESSING | COMPLETE | FAILED)
  │       created_at, updated_at
  │
  ├──< analyses
  │       id, submission_id, org_id
  │       model_used, prompt_version
  │       token_count_input, token_count_output
  │       started_at, completed_at
  │       raw_llm_response (JSONB)
  │
  ├──< findings
  │       id, analysis_id, org_id
  │       wcag_criterion (e.g. "1.1.1")
  │       wcag_level (A | AA | AAA)
  │       severity (CRITICAL | SERIOUS | MODERATE | MINOR)
  │       affected_element, description, impact
  │       created_at
  │
  └──< reports
          id, org_id, created_by_user_id
          title, summary
          submission_ids[] (linked submissions)
          export_format (PDF | CSV | JSON)
          status, file_path
          created_at
```

### 4.3 Tenant Isolation

Every application table carries an `org_id` foreign key. The chassis `TenantQueryMixin` (applied to all slot repositories) automatically appends `WHERE org_id = :current_org_id` to every query. Cross-tenant data access is structurally prevented at the ORM layer — a query that omits the mixin will fail a startup assertion check.

---

## 5. Authentication and Authorization

### 5.1 Authentication Flow

```
Login form → POST /auth/login
  │
  ├─► Lookup user by email (constant-time comparison)
  ├─► Verify bcrypt hash (cost ≥12)
  ├─► Check lockout state (Redis; 3 failures / 15 min → 30 min lockout)
  ├─► If platform admin: redirect to TOTP challenge step
  └─► Issue signed JWT → set HttpOnly/Secure/SameSite=lax cookie
```

### 5.2 Permission Model

The application registers the following permissions at startup (auto-seeded):

| Permission | Granted To |
|---|---|
| `submissions:read` | `user`, `admin` |
| `submissions:write` | `user`, `admin` |
| `analyses:read` | `user`, `admin` |
| `findings:read` | `user`, `admin` |
| `reports:read` | `user`, `admin` |
| `reports:write` | `user`, `admin` |
| `reports:export` | `user`, `admin` |
| `remediation:read` | `user`, `admin` |
| `admin:manage` | `admin` |

Every slot route declares its required permission via `Depends(require_permission("resource:action"))`. The chassis enforces this server-side; no client-side permission checks are trusted.

---

## 6. LLM Integration

### 6.1 Gateway Architecture

All LLM calls are routed through the chassis LLM Gateway — the application never calls the LLM provider directly. This provides:

- **Single egress point:** one place to rotate API keys, switch providers, or add content filtering
- **Prompt logging:** every request/response pair is written to `llm_prompt_logs` with token counts, model name, and latency
- **Token metering:** per-org cumulative token usage tracked in Redis; configurable budget limits
- **Retry/backoff:** exponential backoff on transient provider errors; dead-letter to ARQ for permanent failures
- **Provider abstraction:** OpenAI-compatible API contract; provider is a configuration value, not a code change

### 6.2 Prompt Structure

Accessibility analysis prompts follow a structured template pattern:

```
System message:
  • Role definition (accessibility expert, WCAG 2.1/2.2 specialist)
  • Output format contract (JSON schema for findings array)
  • Severity and WCAG level classification rules

User message:
  • Content type declaration
  • Submitted content (text / URL content / file text extraction)
  • Specific evaluation scope (if user-specified)

Expected response:
  {
    "findings": [
      {
        "wcag_criterion": "1.1.1",
        "wcag_level": "A",
        "severity": "CRITICAL",
        "affected_element": "<img src='...' >",
        "description": "...",
        "impact": "...",
        "remediation_hint": "..."
      }
    ],
    "summary": "...",
    "overall_compliance_level": "partial|non-compliant|compliant"
  }
```

The response is validated against a Pydantic schema before any findings are persisted. Malformed or truncated LLM responses are logged and the submission is marked `FAILED` with a structured error.

---

## 7. Background Processing

Long-running operations (LLM analysis, report generation, file export) run in ARQ worker processes separate from the web process. This prevents request timeouts and allows independent scaling.

```
Web Process (Uvicorn)          ARQ Worker Process
      │                               │
      │  enqueue(task_fn, args)        │
      ├──────────────────────────────►│
      │         (Redis queue)         │
      │                               ├─► Execute task
      │                               ├─► Update DB status
      │                               └─► (optional) emit event
      │
      │  GET /submissions/{id}
      ◄── poll status from DB ────────┘
```

Worker processes share the same codebase and database connection pool. They are started with `arq app.worker.WorkerSettings` and can be scaled horizontally. Each task is idempotent: re-queuing a task that already completed is a no-op (status check at task entry).

---

## 8. Observability

### 8.1 Structured Logging

All log output is JSON-formatted (via `structlog`). Every log entry carries:

- `timestamp` (ISO 8601)
- `level`
- `request_id` (injected by chassis middleware)
- `user_id` (when authenticated)
- `org_id` (when tenant context is resolved)
- `event` (human-readable description)
- Domain-specific fields (e.g., `submission_id`, `finding_count`, `token_count`)

### 8.2 Metrics

The chassis exposes a Prometheus-compatible `/metrics` endpoint. Application slot code increments named counters and histograms via the chassis metrics registry:

| Metric | Type | Description |
|---|---|---|
| `submissions_total` | Counter | Submissions received, by content type |
| `analyses_completed_total` | Counter | Analyses completed, by status |
| `findings_per_analysis` | Histogram | Number of findings returned per analysis |
| `llm_request_duration_seconds` | Histogram | LLM call latency (chassis-provided) |
| `llm_tokens_used_total` | Counter | Token consumption by org (chassis-provided) |

### 8.3 Audit Trail

Every create, update, and delete operation on domain records writes an `AuditLog` entry. The audit log is append-only (no UPDATE or DELETE is permitted on the table by the application database user). Entries record:

- Actor (user ID + email)
- Organization context
- Resource type and ID
- Action performed
- Before/after state snapshot (JSONB)
- Timestamp and request ID

---

## 9. Configuration and Secrets

All configuration is driven by environment variables, validated at startup by Pydantic `BaseSettings`. The application will refuse to start if required variables are missing or invalid.

Key configuration domains:

| Domain | Variables |
|---|---|
| Database | `DATABASE_URL` (async psycopg3 DSN) |
| Redis | `REDIS_URL` |
| LLM | `LLM_PROVIDER_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME`, `LLM_MAX_TOKENS_PER_ORG_MONTH` |
| Auth | `JWT_SECRET_KEY`, `JWT_TTL_MINUTES` |
| Application | `APP_ENV`, `APP_BASE_URL`, `LOG_LEVEL` |
| File Storage | `UPLOAD_STORAGE_BACKEND`, `UPLOAD_MAX_FILE_SIZE_MB` |

Secrets (`LLM_API_KEY`, `JWT_SECRET_KEY`, database passwords) must never be committed to source control. In production, inject via a secrets manager (Vault, AWS Secrets Manager, Kubernetes Secrets) as environment variables.

---

## 10. Deployment Topology

```
                    ┌─────────────────────────────┐
                    │      Load Balancer / CDN     │
                    └──────────────┬──────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
   ┌──────────▼──────────┐         │        ┌───────────▼──────────┐
   │   Web Container(s)  │         │        │   Worker Container(s) │
   │   uvicorn main:app  │         │        │   arq WorkerSettings  │
   └──────────┬──────────┘         │        └───────────┬──────────┘
              │                    │                    │
              └──────────┬─────────┘────────────────────┘
                         │
              ┌──────────┼──────────┐
              │          │          │
   ┌──────────▼──┐  ┌────▼────┐  ┌─▼──────────────┐
   │ PostgreSQL  │  │  Redis  │  │  LLM Provider  │
   │  (primary + │  │         │  │  (external API) │
   │   replica)  │  │         │  │                │
   └─────────────┘  └─────────┘  └────────────────┘
```

Web and worker containers are stateless and horizontally scalable. State lives exclusively in PostgreSQL and Redis. Database migrations (`alembic upgrade head`) run as a one-shot init container before web/worker containers start.

---

## 11. Key Design Decisions

| Decision | Rationale |
|---|---|
| Server-rendered HTML (Jinja2 + USWDS) over SPA | FISMA Moderate compliance; accessibility-first; no client-side auth token handling |
| ARQ over Celery | Native async Python; shares the same async SQLAlchemy session factory as the web process |
| Single LLM egress via chassis gateway | Audit, metering, key rotation, and provider switching without application code changes |
| Tenant isolation at ORM layer | Structural prevention of cross-tenant data leakage; not dependent on application logic correctness |
| Append-only audit log | Tamper-evident compliance record; satisfies FISMA audit requirements |
| HTMX for dynamic UI | Progressive enhancement; no JavaScript framework; accessible by default; works with server-rendered USWDS components |