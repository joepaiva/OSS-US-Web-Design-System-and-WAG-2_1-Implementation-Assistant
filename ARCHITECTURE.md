# Chassis Architecture — Canonical Patterns Reference

> **READ THIS BEFORE WRITING ANY CODE IN `app/slots/`.**
>
> This document is the "highly-defined declarative template" fed verbatim to LLMs at Phase 2 of the SD-Agile Platform App Builder. It declares the exact modern patterns business-logic slots MUST mirror.
>
> Violation of any **FORBIDDEN** rule below causes:
> 1. The Phase 2 changeset to be rejected by the chassis ForbiddenPatterns AST scanner.
> 2. The Phase 3 `mypy --strict` gate to fail.
> 3. The Phase 3 `pytest` run to fail.

---

## 1. Overall Shape

The chassis is a slot-filling host. **Chassis owns infrastructure**; **LLM-generated slots own business logic**.

```
app/
├── main.py             # FastAPI app factory — chassis-owned
├── config.py           # pydantic-settings — chassis-owned
├── db.py               # async engine + AsyncSession factory — chassis-owned
├── deps.py             # current_user, current_org, requires — chassis-owned
├── logging.py          # structlog — chassis-owned
├── auth/               # auth/JWT — chassis-owned
├── rbac/               # roles/permissions — chassis-owned
├── orgs/               # multi-tenancy — chassis-owned
├── audit/              # audit log — chassis-owned
├── tasks/              # RQ background queue — chassis-owned
├── mail/               # transactional email — chassis-owned
├── admin/              # Jinja2 + HTMX admin shell — chassis-owned
├── health/             # /healthz, /readyz, /version — chassis-owned
└── slots/              # ← LLM writes ONLY here
    └── example/        # reference CRUD — mirror this shape for new domains
        ├── models.py
        ├── routes.py
        ├── schemas.py
        ├── service.py
        └── tests/
```

LLMs may add new packages under `app/slots/` (e.g. `app/slots/inventory/`, `app/slots/billing/`). LLMs MUST NOT touch any file outside `app/slots/`.

---

## 2. Forbidden Patterns

These patterns are common-but-wrong defaults that pre-2023 training data biases LLMs toward. Every one of them has a modern equivalent. **Use the modern form.**

### 2.1 Pydantic v1 → v2

| ❌ FORBIDDEN (v1) | ✅ REQUIRED (v2) |
|---|---|
| `from pydantic import BaseModel, validator` | `from pydantic import BaseModel, field_validator` |
| `@validator('field')` | `@field_validator('field')` |
| `class Config: orm_mode = True` | `model_config = ConfigDict(from_attributes=True)` |
| `class Config: anystr_strip_whitespace = True` | `model_config = ConfigDict(str_strip_whitespace=True)` |
| `Field(default_factory=lambda: ...)` v1 syntax | `Field(default_factory=...)` v2 — same name, different internals |
| `obj.dict()` | `obj.model_dump()` |
| `obj.json()` | `obj.model_dump_json()` |
| `Model.parse_obj(d)` | `Model.model_validate(d)` |
| `Model.parse_raw(s)` | `Model.model_validate_json(s)` |

### 2.2 SQLAlchemy 1.4 → 2.0 Async

| ❌ FORBIDDEN (1.4 sync) | ✅ REQUIRED (2.0 async) |
|---|---|
| `from sqlalchemy.orm import Session` | `from sqlalchemy.ext.asyncio import AsyncSession` |
| `session.query(User).filter(User.id == id).first()` | `(await session.execute(select(User).where(User.id == id))).scalar_one_or_none()` |
| `session.query(User).filter_by(email=e).all()` | `(await session.execute(select(User).where(User.email == e))).scalars().all()` |
| `session.add(obj); session.commit()` | `session.add(obj); await session.commit()` |
| `session.delete(obj)` | `await session.delete(obj)` |
| `obj.related` (lazy load) | `(await session.execute(select(Parent).options(selectinload(Parent.related)).where(...))).scalar_one()` |
| `class User(Base): id = Column(Integer, primary_key=True)` | `class User(Base): id: Mapped[int] = mapped_column(primary_key=True)` |
| `Column(String(255))` | `mapped_column(String(255))` |
| `relationship('Other', backref='users')` | `relationship('Other', back_populates='users')` plus `users: Mapped[list['User']] = relationship(back_populates='other')` on the other side |

### 2.3 Python Typing

| ❌ FORBIDDEN (legacy) | ✅ REQUIRED (PEP 604, 3.12) |
|---|---|
| `from typing import Optional, List, Dict, Union` | (built-ins for List/Dict; `\|` for Union/Optional) |
| `Optional[str]` | `str \| None` |
| `Union[int, str]` | `int \| str` |
| `List[int]` | `list[int]` |
| `Dict[str, int]` | `dict[str, int]` |
| `Tuple[int, ...]` | `tuple[int, ...]` |
| `from __future__ import annotations` | (NOT needed in 3.12; if added, fine, but don't lean on it.) |

### 2.4 Async/Await Discipline

- **Every** database access in `app/slots/` MUST be `await`ed. There is NO synchronous `Session` in this chassis.
- **Every** route handler that touches the DB MUST be `async def`, not `def`.
- **Every** service-layer function that calls another async function MUST itself be `async def`.
- `time.sleep()` in async code is **FORBIDDEN** — use `await asyncio.sleep(...)`.
- `requests.get(...)` in async code is **FORBIDDEN** — use `httpx.AsyncClient`.

### 2.5 Time and Dates (v0.2 — surfaced by Phase 3 HelpDesk run)

LLMs default to `datetime.utcnow()` and `datetime.now()` without timezone arguments. Both are problematic for chassis slot code:

- `datetime.utcnow()` is **deprecated** in Python 3.12+ (emits DeprecationWarning) and slated for removal.
- `datetime.now()` without an explicit timezone returns a naive datetime that compares incorrectly against timezone-aware columns from the chassis (which uses `DateTime(timezone=True)` everywhere).

| ❌ FORBIDDEN | ✅ REQUIRED |
|---|---|
| `datetime.utcnow()` | `datetime.now(UTC)` (where `from datetime import UTC, datetime`) |
| `datetime.now()` (no tz arg) | `datetime.now(UTC)` |
| `datetime.now(timezone.utc)` (legacy import) | `datetime.now(UTC)` (PEP 615 import) |
| Naive datetime arithmetic with chassis DB columns | Use timezone-aware datetimes throughout |

The chassis itself uses `from datetime import UTC` and `datetime.now(UTC)` in `app/auth/models.py` etc. Slot code MUST do the same.

---

## 2.6 Concurrent State Changes — Atomic Row-Lock Pattern (v0.2 — surfaced by Phase 3 EventRSVP run)

When a slot needs atomic check-and-claim (capacity-constrained signups, ticket assignment, sequence-number generation, etc.), the canonical pattern is `select(...).with_for_update()` inside an async transaction.

### Canonical example — atomic capacity claim with waitlist promotion

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

@audited("events.rsvp_created", entity_type="rsvp")
async def create_rsvp(session: AsyncSession, user: User, event_id: int) -> RSVP:
    # 1. Lock the event row for the duration of this transaction.
    #    Other concurrent claim attempts on the same event_id BLOCK here.
    event_stmt = select(Event).where(Event.id == event_id).with_for_update()
    event = (await session.execute(event_stmt)).scalar_one()

    # 2. Count confirmed RSVPs UNDER THE SAME LOCK.
    confirmed_count_stmt = (
        select(func.count(RSVP.id))
        .where(RSVP.event_id == event_id, RSVP.status == "confirmed")
    )
    confirmed_count = (await session.execute(confirmed_count_stmt)).scalar_one()

    # 3. Decide: confirmed or waitlist?
    if confirmed_count < event.capacity:
        rsvp = RSVP(event_id=event_id, user_id=user.id, status="confirmed", position=None)
    else:
        # Compute waitlist position UNDER THE SAME LOCK.
        wl_count_stmt = (
            select(func.count(RSVP.id))
            .where(RSVP.event_id == event_id, RSVP.status == "waitlist")
        )
        wl_count = (await session.execute(wl_count_stmt)).scalar_one()
        rsvp = RSVP(event_id=event_id, user_id=user.id, status="waitlist", position=wl_count + 1)

    session.add(rsvp)
    # 4. Lock released when the surrounding transaction commits.
    return rsvp
```

### Rules

- The `with_for_update()` MUST happen on a query that locks the **row whose state is being mutated** (the Event row, not the RSVP row about to be inserted).
- Counts that drive the decision MUST happen INSIDE the same transaction as the lock, NOT before it. Reading the count outside the lock is a TOCTOU race.
- The promotion-on-cancellation flow (cancel a confirmed RSVP → promote head-of-waitlist) MUST use the same lock pattern, in the same transaction, so the cancellation and the promotion either both succeed or both fail.
- pytest-asyncio test for atomicity:

```python
@pytest.mark.asyncio
async def test_capacity_one_two_simultaneous_rsvps(client, make_event_capacity_1):
    headers_a, headers_b = await make_two_users(client)
    async def claim(headers): return await client.post(f"/events/{event_id}/rsvp", headers=headers)
    results = await asyncio.gather(claim(headers_a), claim(headers_b))
    statuses = sorted(r.json()["status"] for r in results)
    assert statuses == ["confirmed", "waitlist"]
```

### Anti-patterns

- ❌ `session.query(Event).get(event_id)` (SQLAlchemy 1.4)
- ❌ `select(Event).where(Event.id == event_id)` without `.with_for_update()` when concurrent claims are expected
- ❌ Reading the count before opening the transaction
- ❌ Splitting "cancel confirmed RSVP" and "promote waitlist head" into separate transactions

## 2.7 State Machines (v0.4 — surfaced by Phase 3: LeaveLite, RecipeShare, HelpDesk, EventRSVP)

Many slot domains have lifecycle states (draft → submitted → approved). The chassis ships a
canonical reference at `app/slots/example_with_states/` (Approval Request domain). LLM slot
authors with state-machine requirements MUST mirror its pattern. The key invariants:

### Invariants

1. **The state machine is a data structure, not control flow.** Define `ALLOWED_TRANSITIONS:
   dict[Status, frozenset[Status]]` at module scope in `service.py`. Terminal states map to
   `frozenset()`. The `transition()` function consults this table — it does NOT contain
   if/elif chains over status pairs.

2. **All state changes flow through ONE function: `transition()`.** Other service-layer
   functions (e.g. `update_*` for editing title/body) MUST NOT mutate the status column.
   This keeps the @audited decorator coverage uniform and the transition-timestamp
   bookkeeping consistent.

3. **Illegal transitions raise `IllegalTransition`, not `ValueError`.** Routes map this to
   HTTP 409 Conflict (not 422 — the payload was syntactically valid; the business rule
   rejected it). The exception carries `current` + `target` for clear error messages.

4. **Side-effect stamping happens inline in `transition()`.** When a transition fires, stamp
   the relevant timestamps (`submitted_at`, `decided_at`) AND any related metadata
   (`approver_id`, `decision_note`) inside the same transaction as the status update. Don't
   split these into separate service calls — concurrent updates from two approvers could
   race.

5. **Terminal-state guards are belt-and-suspenders.** Update endpoints that mutate fields
   OTHER than status (e.g. `PATCH /resource/{id}` editing title/body) should ALSO reject when
   the row is in a terminal state, even if the state machine doesn't fire there. Same
   `IllegalTransition` exception, but with `current == target` to indicate "this state
   rejects mutations entirely."

### Anti-patterns

- ❌ `if request.status == "draft": ...elif request.status == "submitted": ...` chains —
   refactor to a table lookup
- ❌ Mutating `status` directly in `update_*` functions — funnel through `transition()`
- ❌ Returning 422 for "wrong-state" rejections — 409 is the correct code
- ❌ Stamping `decided_at` in a separate transaction from the status change — race window
- ❌ Letting routes catch `IllegalTransition` and return 200 — defeats the entire point

### Reference

`app/slots/example_with_states/` covers a 4-state machine (draft/submitted/approved/rejected)
with two terminal states. Read service.py for the `ALLOWED_TRANSITIONS` table and
`transition()` function shape; routes.py for the 409/422 exception mapping; tests/test_routes.py
for the test categories (happy path, illegal transitions, terminal-state guards, decision-note
required, cross-org isolation).

## 2.8 Per-Tenant Configuration (v0.4 — surfaced by Phase 3: RecipeShare + EventRSVP)

When a slot has business rules that vary per organization (e.g., "max event capacity",
"recipe spice level scale", "ticket SLA defaults"), the chassis pattern is a **slot-local
config table** keyed by `org_id`, NOT a chassis-wide config table.

### Why slot-local

A chassis-wide `org_configs` table forces every slot's settings into one schema, creating:
- Coupling between unrelated slots (a column for slot A is dead weight for slot B)
- Coordination overhead at migration time (every slot needs to touch the same table)
- A messy mix of typed fields and JSONB blobs that erodes type safety

Slot-local keeps each slot autonomous and lets each define its own typed settings.

### Pattern

In your slot's `models.py`:

```python
from app.db import Base, TenantScoped

class RecipeConfig(Base, TenantScoped):
    """Per-org configuration for the Recipe slot.

    One row per org (enforced by UNIQUE constraint on org_id).
    Lazily created — recipes service does:
        config = await get_or_create_recipe_config(session)
    """
    __tablename__ = "recipe_recipe_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    spice_level_scale: Mapped[int] = mapped_column(default=5)  # 5- vs 10-point
    require_image: Mapped[bool] = mapped_column(default=False)
    default_cuisine: Mapped[str] = mapped_column(String(64), default="other")
    # ... etc

    __table_args__ = (UniqueConstraint("org_id", name="uq_recipe_config_org"),)
```

In your slot's `service.py`:

```python
async def get_or_create_recipe_config(session: AsyncSession) -> RecipeConfig:
    """Return the active org's config, creating it with defaults if missing."""
    result = await session.execute(select(RecipeConfig))
    config = result.scalar_one_or_none()
    if config is None:
        config = RecipeConfig()  # defaults; org_id auto-injected by chassis
        session.add(config)
        await session.flush()
    return config
```

### Rules

- One config table per slot. Don't share across slots.
- Inherit `(Base, TenantScoped)` like any other tenant-owned table.
- UNIQUE constraint on `org_id` so chassis-scope queries always return at most one row.
- Lazy creation in a `get_or_create_*_config()` helper — don't force every new org
  to provision configs at signup time.
- Settings are TYPED columns, not JSONB blobs. If you find yourself wanting JSONB,
  question whether those settings are really per-org configuration or actually
  domain entities (in which case they belong in a different table).

### Admin UI

Each slot is free to add `/<slot>/config` GET + PATCH routes for editing its config.
The chassis admin shell (Jinja2 templates) provides the layout container; slot authors
add domain-specific form pages.

## 2.9 Soft-Delete Design Position (v0.4 — surfaced by Phase 3: RecipeShare)

**Chassis position:** soft-delete is OPT-IN per slot, not chassis-default.

### Why not chassis-default

Soft-delete on every tenant-owned table sounds appealing but introduces real costs:
- Every `SELECT` needs an additional `WHERE deleted_at IS NULL` clause (the chassis
  TenantScoped auto-filter could compose, but the slot has to reason about both filters)
- Restore endpoints are a separate UX concern that not all domains need
- "Cascade soft-delete on org delete" is an open question with no clean answer
- Storage grows unboundedly without a separate archival job — and slot authors who
  haven't considered retention will hit this surprise

### Opt-in mechanism

When a slot DOES want soft-delete, add a `SoftDeletable` mixin to ITS specific model.
The mixin lives in the slot's `models.py` (or factored to a shared slot utility if a slot
has multiple soft-deletable entities). The chassis does NOT ship a global mixin —
intentionally — to keep the decision visible at each model.

```python
from datetime import datetime
from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

class SoftDeletable:
    """Slot-local mixin. Inherit alongside TenantScoped:
        class Recipe(Base, TenantScoped, SoftDeletable): ...
    """
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,  # filter performance
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
```

### Query patterns

Soft-deleted rows are NOT auto-filtered. The slot's service.py is responsible:

```python
# Reads that should hide soft-deletes:
result = await session.execute(
    select(Recipe).where(Recipe.deleted_at.is_(None))
)

# Reads that should show deleted (admin/audit views):
result = await session.execute(select(Recipe))  # no deleted_at filter
```

### Delete + restore

```python
async def soft_delete_recipe(session: AsyncSession, recipe_id: int) -> Recipe:
    recipe = await get_recipe(session, recipe_id)
    recipe.deleted_at = datetime.now(UTC)
    await session.flush()
    return recipe

async def restore_recipe(session: AsyncSession, recipe_id: int) -> Recipe:
    # Note: get_recipe must NOT filter out soft-deletes for the restore path.
    # Either pass a flag or have a separate get_any_recipe_including_deleted().
    recipe = await get_any_recipe_including_deleted(session, recipe_id)
    if recipe.deleted_at is None:
        return recipe  # idempotent
    recipe.deleted_at = None
    await session.flush()
    return recipe
```

### Hard delete

The chassis's `@audited` decorator covers hard-delete actions. Slots that need to PURGE
soft-deleted rows after a retention period should add a background RQ job (chassis ships
the RQ infrastructure; the slot defines the schedule and predicate).

### Rules

- Soft-delete is per-slot-per-model. Don't apply it sweepingly.
- Audit log entries for soft-delete actions use action="recipe.soft_deleted"; for restore
  use "recipe.restored"; for hard delete use "recipe.deleted".
- Document the chosen position (soft vs hard) in the slot's `__init__.py` docstring so
  customers reading the artifact understand the retention behavior.

## 3. Canonical Slot Skeleton

When the LLM is asked to add a new domain (e.g. "inventory"), the LLM SHALL create exactly this shape:

```
app/slots/inventory/
├── __init__.py        # empty
├── models.py          # SQLAlchemy 2.0 async models inheriting TenantScoped
├── schemas.py         # Pydantic v2 request/response models
├── routes.py          # APIRouter with async handlers
├── service.py         # async service-layer functions
└── tests/
    ├── __init__.py
    └── test_routes.py
```

And the LLM SHALL register the router in `app/main.py` by adding ONE line to the existing slot-registration block (chassis-owned but extension-point comment indicates the safe insertion point).

---

## 4. Reference Implementations

### 4a. `app/slots/example/` — Pure CRUD reference (Notes)

The canonical CRUD shape every slot mirrors:

- `models.py` — Inherits `TenantScoped` for automatic `org_id` filtering. Uses `Mapped[T]` + `mapped_column(...)`.
- `schemas.py` — `ConfigDict(from_attributes=True)`. Separate `Create`/`Update`/`Read` schemas.
- `service.py` — `async def` everywhere; takes `AsyncSession` as a parameter; uses `select(Model).where(...).execute(...).scalar_one_or_none()` patterns.
- `routes.py` — `APIRouter(prefix="/example", tags=["example"])`. Dependencies: `current_user`, `current_org`, `requires("example:read")` etc.
- `tests/conftest.py` — slot-local persona fixtures (see `docs/SLOT-TESTING.md`)
- `tests/test_routes.py` — `pytest.mark.asyncio` cases covering happy path, auth, permissions, cross-org isolation

### 4b. `app/slots/example_with_states/` — State-machine reference (Approval Request, v0.4)

Slots with lifecycle states (draft → submitted → approved/rejected, etc.) MUST mirror this
shape. Differences from the pure CRUD reference:

- `models.py` adds a `Status` enum + `status` column + transition timestamps (`submitted_at`,
  `decided_at`) + relevant FK columns (`approver_id`)
- `service.py` defines:
   - `ALLOWED_TRANSITIONS: dict[Status, frozenset[Status]]` — the state machine table
   - `IllegalTransition` exception (distinct from `ValueError`)
   - `transition()` function — the SINGLE entry point for status changes
   - Side-effect stamping inside transition() (timestamps + metadata)
   - Terminal-state guards on `update_*()` functions for defense-in-depth
- `routes.py` adds `POST /<resource>/{id}/transitions` — the transitions sub-resource —
  with exception mapping (`IllegalTransition` → 409, `DecisionNoteRequired` → 422)
- `tests/test_routes.py` covers the additional categories: illegal transitions, terminal-state
  guards, decision-note required, plus the standard CRUD categories

---

## 5. Wiring a New Slot

Steps the LLM follows:

1. Create the slot directory (§3 skeleton).
2. Add permissions to `app/rbac/permissions.py` (the chassis-owned registry has an EXTENSION POINT comment).
3. Register router in `app/main.py` at the EXTENSION POINT comment.
4. Generate Alembic migration: `alembic revision --autogenerate -m "add inventory slot"`. Review it. Commit it under `migrations/versions/`.
5. Write tests.
6. Run: `uv run pytest app/slots/inventory/ -v` then `uv run mypy --strict app/slots/inventory/`. Both must pass.

---

## 6. What Chassis Does FOR The Slot (free, no slot code needed)

- **Auth** — `current_user` dep injects the authenticated `User` ORM object.
- **Multi-tenancy** — Inheriting `TenantScoped` causes `org_id` to be auto-injected on insert and auto-filtered on read for any query inside a request bound to a `current_org`.
- **RBAC** — `Depends(requires("inventory:read"))` returns 403 if the user lacks the permission.
- **Audit** — Decorating a service method with `@audited("inventory.created")` writes an `audit_log` row on success.
- **Background tasks** — `from app.tasks import enqueue; enqueue(send_invoice, invoice_id=42)` schedules a job on RQ.
- **Email** — `from app.mail import send; await send(to=..., subject=..., body=...)` routes through fastapi-mail.
- **Logging** — `structlog.get_logger().info("event", key=value)` produces structured JSON (prod) or pretty (dev) with request-ID auto-attached.
- **Health/version** — `/healthz`, `/readyz`, `/version` already wired.
- **Admin shell** (v0.7) — `app/admin/` ships a built-in, RBAC-gated admin UI at `/admin`: **User Management** (platform admins manage all users; org admins manage their current org's members — create, deactivate, reactivate) and **Org Management** (platform admins only — list + create orgs). "Platform admin" = `is_superuser` or the chassis-wide `admin` role; "org admin" = the `admin` role on the current org's membership. Server-rendered (Jinja2 + USWDS), gated on `users:write` (the seeded `user` role only has `*:read`, so it can't reach the shell). Slots may add their own admin pages at the `# CHASSIS-EXTENSION-POINT: admin-pages` marker in `app/admin/routes.py`.
- **System Health + Documentation** (v0.8) — the admin shell adds two pages. **System Health** (`/admin/system-health`, platform admins only — `app/admin/health_service.py`) shows the app + chassis version, environment, and live, best-effort (never-raising) database + Redis reachability; credentials are redacted from any reported DSN. **Documentation** (`/admin/docs`, any admin — `app/admin/docs_service.py`) renders a whitelisted set of bundled Markdown docs (How It Works, User Manual, **Security Self-Audit / FISMA Moderate**, README) in-app via a small, dependency-free, HTML-escaping Markdown renderer; only registry slugs are served, so path traversal is structurally impossible. The control-by-control security posture lives in `docs/SECURITY-SELF-AUDIT.md`.
- **Files + Notifications + Rate-limiting + Reporting** (v0.10) — four more "free to the slot" capabilities. **Files** (`app/files/`, REST `/api/files`): org-scoped upload/list/download/delete; bytes on local disk under `file_storage_dir` keyed by an opaque UUID (no path traversal), SHA-256 integrity, `max_upload_bytes` cap, `@audited`. **Notifications** (`app/notifications/`, REST `/api/notifications`): per-user in-app notifications (level + read state); slots call `app.notifications.service.notify(...)`. **Rate limiting** (`app/ratelimit/`): opt-in (`RATE_LIMIT_ENABLED`) Redis fixed-window per-client middleware, fail-open, exempting health/static (SC-5). **Reporting** (`/admin/reports`, `app/admin/reports_service.py`): read-only usage counts (users, orgs, audit + top actions, files, notifications, LLM keys), platform-admin = global / org-admin = org-scoped.
- **Embedded LLM** (v0.9) — `app/llm/` gives generated apps a first-class, Rule-7-parity LLM capability. Provider API keys are stored **AES-256-GCM encrypted** (`app/llm/crypto.py`) in `llm_provider_keys` — per-org or platform-shared, **never** in env/config (the only config secret is the wrap key `LLM_ENCRYPTION_KEY`, which fails closed at use time in prod if left at the in-code default). `app/llm/service.py` resolves a key per request via the chain **org key → shared key (iff `org_llm_access` grants it) → reject** and runs completions through `app/llm/transport.py` (OpenAI-format `POST {LLM_PROXY_URL}/chat/completions`, the resolved key injected per request — LiteLLM `configurable_clientside_auth_params`). Admin UI at **`/admin/llm`** (`llm:write`): org admins manage their org's keys; platform admins also manage shared keys + the per-org shared-access policy. Keys are always masked in the UI. Slots call `app.llm.service.complete(...)`.
- **OpenAPI** — `/docs` and `/redoc` auto-generated from your Pydantic schemas + type hints.

---

## 7. Extension Points

Five canonical extension points exist in chassis-owned files:

| File | Marker | What goes here |
|---|---|---|
| `app/main.py` | `# CHASSIS-EXTENSION-POINT: slot-routers` | One `app.include_router(...)` per slot |
| `app/rbac/permissions.py` | `# CHASSIS-EXTENSION-POINT: slot-permissions` | Per-slot permission constants |
| `app/auth/providers/__init__.py` | `# CHASSIS-EXTENSION-POINT: auth-providers` | OAuth/SSO providers (v2+) |
| `migrations/env.py` | (auto-discovered) | Alembic discovers `app/slots/*/models.py` automatically |
| `app/admin/routes.py` | `# CHASSIS-EXTENSION-POINT: admin-pages` | Per-slot admin pages (optional) |

These are the ONLY chassis files the LLM may touch — and only at the marked lines, by adding a single registration line.

---

## 8. Version Compatibility

This document is canonical for **CHASSIS_VERSION = 0.10.0**. Future minor versions (0.x.0) MUST keep extension-point semantics backward-compatible at the slot interface. Major bumps (1.0.0+) require a slot-migration prompt.

When a slot is generated, its tests SHOULD verify against the chassis version pinned in the BuildProject row at build creation. The platform binds slot output to a specific chassis version; chassis upgrades are operator-initiated.
