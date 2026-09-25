# STATE-HANDLING.md — Chassis Page-State Policy (chassis v0.6.4 +)

**Current as of chassis v0.10.0.**

**Scope.** Loading, empty, and error page-states for every chassis-shipped or
slot-shipped page.

**Why this is chassis-locked.** Three page-states recur on essentially every
data-driven page in every app the chassis generates. Re-eliciting them
per-screen during the Spec Builder wizard wastes user time and LLM tokens
with zero added information. The chassis-locked baseline is the
known-good default; slot authors override only when a specific page has a
domain-specific state that genuinely differs.

The Spec Builder wizard reads `StackTemplate.LockedSections.constitution`
and, when `state_handling` appears in that list, the
`chassis_ui_ux_design_override.md` facilitation override asks the user
ONCE per topic (accept the chassis default OR record a custom override)
and never re-asks across the session.

---

## Override marker

To deviate from the chassis-locked behavior in a generated app's
`Constitution.md`, include the literal marker:

```
# CHASSIS-OVERRIDE: state-handling
<override description here>
```

Without that marker, the chassis state-handling baseline applies.

---

## Loading state

**When.** Any page or HTMX fragment that fetches data and may take
> 200 ms to first paint, or any operation that may take > 1 s to
return a result.

**Chassis macro.**

```jinja
{% from 'components/_states.html' import state_loading %}
{{ state_loading() }}
```

**Markup contract.**

```html
<div class="usa-prose" role="status" aria-live="polite">
  <span class="usa-icon" aria-hidden="true">
    <!-- USWDS spinner icon -->
  </span>
  <span>Loading…</span>
</div>
```

**Required attributes.**
- `role="status"` so screen readers announce the loading state without
  interrupting the user's current task.
- `aria-live="polite"` so assistive tech only notifies on the next
  natural pause.
- Visible "Loading…" text — never icon-only (Section 508 compliance).

**HTMX integration.** Pair the macro with `hx-indicator` on the
triggering element so the spinner appears only while the request is in
flight:

```html
<button hx-get="/data" hx-target="#out" hx-indicator="#spinner">
  Load data
</button>
<div id="spinner" class="htmx-indicator">{{ state_loading() }}</div>
```

**Long-running operations.** If the operation may take > 2 s, the
chassis recommends pairing this with a progress message ("Generating
report — about 30 seconds…"). For operations > 10 s, use the
background-task pattern (`@background_task` from `app.tasks`) and a
poll-style status page rather than a hung loading state.

---

## Empty state

**When.** A list / table / dashboard tile has zero rows AND the user has
permission to create at least one row.

**Chassis macro.**

```jinja
{% from 'components/_states.html' import state_empty %}
{{ state_empty(message="No leave requests yet.",
               cta_url="/requests/new",
               cta_label="Create one") }}
```

**Markup contract.**

```html
<div class="usa-alert usa-alert--info usa-alert--no-icon" role="status">
  <div class="usa-alert__body">
    <p class="usa-alert__text">No leave requests yet.</p>
    <a class="usa-button" href="/requests/new">Create one</a>
  </div>
</div>
```

**Required attributes.**
- `role="status"` (informational, not blocking).
- USWDS `--info` variant (the situation is not an error; it's the
  starting state for any new user).

**CTA is optional.** Pass `cta_url=None` for read-only contexts where
the user cannot self-create the missing data ("No payroll runs
available — your administrator will run the next batch on Monday.").

**Anti-pattern.** Do NOT use the error variant (`usa-alert--error`) for
empty states. Empty is not an error.

---

## Error state

**When.** Any HTTP 4xx / 5xx response that the user should see, or any
JS-side runtime error that prevented page render. Server-side error
HTML is rendered by `app/error_handlers.py` for FastAPI exception
flows; this macro is for partial-page failures (e.g., HTMX fragment
load failure).

**Chassis macro.**

```jinja
{% from 'components/_states.html' import state_error %}
{{ state_error(message="We couldn't load this section. Please try again.",
               retry_url="/requests") }}
```

**Markup contract.**

```html
<div class="usa-alert usa-alert--error" role="alert">
  <div class="usa-alert__body">
    <h4 class="usa-alert__heading">Something went wrong</h4>
    <p class="usa-alert__text">We couldn't load this section. Please try again.</p>
    <a class="usa-button usa-button--secondary" href="/requests">Try again</a>
  </div>
</div>
```

**Required attributes.**
- `role="alert"` so assistive tech interrupts the user immediately.
- USWDS `--error` variant (red).
- A recovery path: either a retry button (idempotent operations) OR a
  navigation link to a known-safe page.

**Message strings.** The chassis K.8 `app/error_messages.py` module is
the canonical source for user-facing error wording. Slot code SHOULD
read from it:

```python
from app.error_messages import message_for_status
# in a route or HTMX handler:
return templates.TemplateResponse(
    "_states.html",
    {"request": request,
     "message": message_for_status(exc.status_code)},
    status_code=exc.status_code,
)
```

**Anti-pattern.** Do NOT display raw exception strings, stack traces,
or internal IDs. The chassis K.8 canonical messages exist precisely so
slot authors don't have to hand-write user-facing error wording.

---

## Test viewport matrix

The chassis pytest suite verifies each macro renders the required
attributes at default desktop viewport. Visual responsive behavior is
covered by `docs/RESPONSIVE-DESIGN.md`'s 320 / 768 / 1280 px matrix —
the macros inherit USWDS responsive behavior automatically.

---

## Slot-author rules

1. Use the chassis macros instead of hand-rolling state HTML.
2. Use `app.error_messages.STANDARD_MESSAGES` for error wording — never
   hand-write a user-facing 4xx / 5xx message.
3. Pair `hx-indicator` with `state_loading()` for any HTMX-driven
   fragment that may take > 200 ms.
4. If a specific page has a domain-specific delta (e.g., a long-running
   report-generation page that needs a progress bar), record the delta
   in the spec as a screen-specific override of `state_loading`. The
   wizard captures it via the chassis facilitation override's
   "custom: <verbatim>" path.
