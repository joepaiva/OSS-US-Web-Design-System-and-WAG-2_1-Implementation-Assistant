# Greeting Slot — Adapted Spec Note

**Version:** 1.0.0
**Date:** 2026-09-02
**Base spec:** `Chassis App/greeting-service-{constitution,requirements,design,tasks,test-scenarios}.md`
(The SD-Agile Project's teaching-exemplar Build Package for "The Greeting Service").

This slot is that draft, implemented against this package's actual chassis-core
(real TOTP MFA, real multi-tenancy, real LiteLLM-backed `app/llm/`), with exactly
two adaptations from the draft — per `chassis-program-DESIGN.md` §3. Everything
else in the draft's five documents applies unchanged: FR-001..005, BR-001..004,
NFR-001..005, the logic-ownership map, the layering rules, and the closed
error-code set.

## Adaptation 1 — FR-004's MFA gate is real

The draft assumes "an MFA-verified administrator." This package has real TOTP
MFA (`app/auth/mfa.py`), but its chassis-wide MFA *mandate*
(`app/deps.py:requires()`) is scoped to platform-wide privileged accounts only
(`app/rbac/service.py:is_privileged_user`) — a per-org admin (the persona
FR-004 actually means, in a multi-tenant SaaS app where each org manages its
own greeting history) is not covered by that mandate. So this slot adds its
own explicit MFA assertion in `routes.py`'s `read_history`, exactly as the
draft's own `TASK-SEC-001` already anticipated: *"the MFA assertion is
explicit and separate from the role check — §5A requires both."* Nothing in
FR-004's contract changed; the enforcement point was always meant to be here.

## Adaptation 2 — an opt-in LLM translation path

This package carries the LLM delta (`chassis-program-REQUIREMENTS.md` §4.4).
Per the program's demo goal — the same functional app, visibly differentiated
across chassis variants — `providers/translation.py` adds a second path
alongside the draft's static `TranslationProvider`: when a caller sets
`use_llm: true` on `POST /api/greetings` AND requests a locale outside the
fixed six of FR-003, the slot attempts an LLM-generated translation into the
*actual* requested locale (not the tenant default) via this package's own
`app/llm/service.complete()`. On any failure (no key configured, transport
error), it falls straight through to FR-002's existing static-fallback
behavior. Every response now carries `translation_source: "static" | "llm"`
so the difference is visible, not just internal. Default is `false` —
FR-001..003's contract is byte-identical to the draft unless a caller
explicitly opts in.

## What did NOT change

- Logic ownership (Constitution §3, DESIGN.md §3) — `TranslationProvider`
  still owns all locale/fallback/formatting decisions; `RateLimiter` still
  owns all rate-limit evaluation; the four-layer split (router → service →
  repository/integration) is unchanged.
- BR-001 tenant isolation, BR-002's 1,000/60-minute ceiling, BR-003's audit
  fields, BR-004's one-default-locale-per-org invariant, NFR-005's
  no-deletion-path rule.
- The closed error-code set (NFR-004) — `translation_source` is an addition
  to the response body, not a change to the error contract.

## One structural note not in the draft

BR-004 ("every organization MUST have exactly one default locale") needs
somewhere to live. The chassis's own `Organization` model is chassis-owned
and this slot must not extend it outside the two marked extension points —
so `models.py`'s `GreetingOrgSettings` is a slot-owned, one-row-per-org table,
lazily created with `en-US` on first access (`repository.py`). See that
model's own docstring for the full reasoning.
