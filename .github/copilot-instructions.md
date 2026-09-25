# Repository

**Use `https://github.com/joepaiva/OSS-US-Web-Design-System-and-WAG-2_1-Implementation-Assistant` for all code you create or modify.** Clone it, work in it, and commit and push every change there. Do NOT create a new repository, and do not put generated code anywhere else.

---

# SD-Agile spec-first method — AI agent instructions

This repository ships a **Builder Package** (the authoritative spec) and a chassis. When using an agentic surface (Copilot agent mode / cloud coding agent, Cursor, or Claude Code), follow this method. Inline autocomplete ignores these instructions — use the agentic surfaces.

## Read the spec FIRST (mandatory, before writing any code)
`CONSTITUTION.md` (supreme) · `REQUIREMENTS.md` (what) · `DESIGN.md` (how) · `TASKS.md` (build order) · `TEST-SCENARIOS.md` (TS-NNN tests).
If a task isn't in the spec, stop and ask — do not invent scope.

## Rules
1. **Constitution is supreme** — if anything conflicts with `CONSTITUTION.md`, the constitution wins.
2. **Spec-first** — code derives from the spec; never let code drift from it.
3. **Tests are requirements** — never weaken/skip a test to pass; fix the code. Every TS-NNN needs a passing test.
4. **The chassis is immutable** — implement only in the slots (`app/slots/**`); never modify chassis core (`app/**`) or use forbidden patterns; respect layer boundaries.
5. **Preserve compliance annotations** — keep any control annotations accurate; never claim a control the code doesn't implement.
6. **Verify before done** — build + the chassis test suite must pass; cover the task's TS-NNN.
7. **Browser e2e is mandatory for UI** — for anything a user sees or does in a browser (a page, form, flow, modal, table, navigation, auth/login, or a server response *shape* a page consumes), a Playwright browser end-to-end test that simulates a real user and **asserts the RENDERED result** is required before the task is done. See `.github/instructions/e2e-browser.instructions.md`. Unit + HTTP tests passing is NOT verification of a UI.

## The iterative loop — run it for EVERY task
1. **READ** the spec (Constitution → Requirements → Design → Tasks → the task's TS-NNN).
2. **IMPLEMENT** in the slots only (`app/slots/**`).
3. **TEST** — run the chassis unit/test suite AND, if the task touches anything a user sees in a browser, a comprehensive Playwright browser end-to-end test that drives the real user flow and asserts the rendered result.
4. **FIX the CODE** (never the test) until every test is green. Loop 3–4.
5. **DOCUMENT** — update the spec docs when behavior, an API, or a UI changes; keep them the source of truth.
A task is not done until its tests — unit AND browser-e2e where applicable — pass.

> These instructions steer but do not enforce. A compliance gate on your PR verifies the output against the spec + controls before UAT — write code that will pass it.
