---
applyTo: "e2e/**"
---
# Browser end-to-end tests are MANDATORY for anything a user sees
Unit tests and HTTP-contract tests can pass while the rendered UI is broken. For ANY change with a browser surface — a page, form, flow, modal, table, navigation, auth/login, or a server response *shape* a page consumes — a Playwright browser end-to-end test that simulates a real user is REQUIRED before the task is done.

The test MUST:
1. **Boot the app.**
2. **Drive the affected flow as a real user** — navigate, fill fields, click, submit — the complete path, not a single page load.
3. **Assert on the RENDERED result** — the row / badge / message / state the user actually sees — NOT merely an HTTP 200 or an empty console.
4. **Check the browser console** for errors and confirm the page's API calls reach the server.

Why: a check that reports success while the page renders nothing is worse than no check. An API test that inspects a response *shape* can pass while the UI — which expected a different shape — shows nothing.

Put each flow's Playwright spec under `e2e/` and record it as a TS-NNN in `TEST-SCENARIOS.md`. A failing browser test means the CODE is wrong — fix the code, never the test.
