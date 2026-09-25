---
applyTo: "tests/**"
---
# Tests are requirements
A failing test means the CODE is wrong — fix the code, never the test. Do not delete/skip tests, loosen assertions, or narrow inputs to pass. Every REQUIREMENTS item / TS-NNN must have a test. If a test genuinely looks wrong, flag it — don't silently change it.
Unit and HTTP-contract tests do NOT verify a UI — anything a user sees in a browser also needs a Playwright browser end-to-end test (see `e2e-browser.instructions.md`).
