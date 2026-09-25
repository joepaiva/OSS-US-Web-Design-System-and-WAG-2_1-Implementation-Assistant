# NFR-BASELINES.md — Chassis Non-Functional Requirements Baselines (chassis v0.6.5 +)

**Current as of chassis v0.10.0.**

**Scope.** Five baselines that the Spec Builder wizard's chassis facilitation
override (Requirements Enumeration) asks about ONCE per session and never
re-asks. Each baseline is a chassis-locked default that the user either
**accepts verbatim** (recommended; majority case) or **overrides** with a
custom NFR annotated `(CHASSIS-OVERRIDE)`.

---

## Override marker

In a generated app's `Constitution.md` or `REQUIREMENTS.md`, deviations are
marked:

```
# CHASSIS-OVERRIDE: nfr-<topic>
<override description here>
```

Without that marker, the baseline applies.

---

## Page Load

**Target.**
- ≤ 2.5 s p95 on 3G Slow (Lighthouse mobile profile).
- ≤ 1.0 s p95 on broadband.

**Why these numbers.** Google Web Vitals "Good" threshold for Largest
Contentful Paint is 2.5 s on mobile; 1.0 s on broadband is achievable for
USWDS-based pages (the CDN delivers the framework; the chassis routes
deliver minimal HTML; HTMX swaps are small).

**Chassis enforcement path.**
- USWDS 3.7 CDN already optimized (cached by Cloudflare).
- HTMX (fragment swaps) ships < 50 KB.
- `app/templates/base.html` ships only critical CSS inline; rest deferred.

**What the user is opting out of when they override.** A custom NFR
("page must paint within 500 ms p95") puts the burden on slot code to
prove it (Lighthouse CI gate; possible CDN promotion; hand-rolled
critical-CSS extraction). The chassis baseline is the no-cost path.

---

## API Response

**Target.**
- ≤ 250 ms p95 for reads (`GET` endpoints).
- ≤ 800 ms p95 for writes (`POST` / `PUT` / `DELETE`).

**Why these numbers.** 250 ms is the threshold below which UI feels
"instant" (no spinner needed under most conditions). 800 ms accommodates
single-table writes with synchronous audit, single-row notification, and
one round-trip to a normalized DB schema.

**Chassis enforcement path.**
- SQLAlchemy 2.0 async on a single Azure Database for PostgreSQL instance
  (typical read latency ~5–15 ms; ~30–80 ms for a 4-join query).
- `@audited` decorator adds one audit-row INSERT (~3 ms) per write.
- structlog JSON logging ships to stdout (no synchronous network call).

**What the user is opting out of when they override.** A custom NFR
("write endpoints must respond in < 200 ms p95") puts pressure on the
audit path (async fire-and-forget?), the DB plan (covered indexes?), and
possibly the deploy topology (read replica?). Specify how the override
will be measured + enforced.

---

## Availability

**Target.** 99.5 % monthly.

**Why this number.** Single-region Azure Container Apps deploy. 99.5 %
allows ~3.6 hours of unplanned downtime per month — sufficient for a single
instance with no active failover, accommodating the platform's own SLA + a
brief recovery window for any single restart.

**Chassis enforcement path.**
- `/readyz` health endpoint pings the DB on each call → Azure Container Apps
  routes traffic only when DB is reachable.
- structlog + `X-Request-ID` middleware gives every error a correlation
  trace for fast postmortem.
- `migrations/` are additive-only (Rule 9) → zero-downtime deploys.

**What the user is opting out of when they override.** 99.9 % requires
multi-region or multi-instance with failover, which is a deploy-time
decision (not a code-time one). Specify the deployment target's
availability SLA.

---

## Concurrent Users

**Target.** 100 concurrent active sessions per single Azure Container Apps
instance.

**Why this number.** Default container instance runs gunicorn with
4 workers × 2 threads = 8 concurrent in-flight requests. With typical
request times of ~80 ms and average user think-time between actions of
~5 s, a single instance comfortably handles 100 active sessions before
queue depth grows.

**Chassis enforcement path.**
- gunicorn + uvloop on async FastAPI (every request yields during DB
  I/O).
- Connection pool: `pool_size=10` + `max_overflow=20` (matches the
  worker × thread count).
- Horizontal scale: `az containerapp update --max-replicas N` adds
  instances behind the Azure Container Apps ingress load balancer.

**What the user is opting out of when they override.** A custom NFR
("must handle 1000 concurrent users") implies one of: (a) deploy with
N replicas at provision time, (b) introduce a read-heavy cache layer
(Redis), (c) move long-running operations to background workers.
Specify which lever the override will pull.

---

## Data Integrity

**Target.**
- SQLAlchemy transactional boundary on every `@audited` service method
  (commit on success, rollback on any raised exception).
- Nightly `pg_dump` retention 30 days (Azure-native automated backup).
- No silent data loss path: every mutating endpoint writes an
  `audit_logs` row before the transaction commits.

**Chassis enforcement path.**
- `app/audit.py` `@audited` decorator wraps the method body in an
  AsyncSession context manager that auto-commits on success.
- `app/db.py` configures SQLAlchemy with `expire_on_commit=False` and
  forces explicit `.flush()` before audit-row INSERT.
- `audit_logs` table has `gen_random_uuid()` primary key + `created_at`
  default `NOW()` + `actor_id` FK to users.
- AU-9 (chassis v0.6.0) ships DB-level REVOKE on `audit_logs` so app
  code cannot DELETE / UPDATE existing rows.

**What the user is opting out of when they override.** A custom NFR
("zero data loss in the event of a single-region failure") implies
multi-region replication (Azure Database for PostgreSQL + a read replica
in another region) + a documented failover playbook. Specify the RPO/RTO
the override targets.

---

## Slot-author rules

1. Do NOT capture FRs for these five baselines unless overriding. The
   chassis ships them; the spec stays silent; the build engine generates
   code that meets the baseline by construction.
2. Annotate every override with `(CHASSIS-OVERRIDE)` in the FR so the
   build engine knows to deviate from the chassis baseline.
3. State the override's measurement + enforcement path. "API response
   must be < 200 ms" without "measured by Datadog APM in production"
   is not actionable.
4. Do NOT confuse chassis NFR baselines with business-rule NFRs.
   "Application supports 100 concurrent users" is chassis-locked.
   "The annual report generation must complete within 4 hours" is a
   business rule — capture it as a real FR.
