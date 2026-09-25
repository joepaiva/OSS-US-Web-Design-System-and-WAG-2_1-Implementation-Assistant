# Repository

**Use `https://github.com/joepaiva/OSS-US-Web-Design-System-and-WAG-2_1-Implementation-Assistant` for all code you create or modify.** Clone it, work in it, and commit and push every change there. Do NOT create a new repository, and do not put generated code anywhere else.

---

# Agent instructions
This repository follows the SD-Agile spec-first method. The authoritative steering is `.github/copilot-instructions.md` — read it first, then the Builder Package (`CONSTITUTION.md`, `REQUIREMENTS.md`, `DESIGN.md`, `TASKS.md`, `TEST-SCENARIOS.md`). Constitution is supreme; tests are requirements; implement only in chassis slots. Run the iterative loop for every task (read → implement → test → fix the code → document), and for anything a user sees in a browser add a Playwright browser end-to-end test that simulates a real user and asserts the rendered result. Verify build + tests (unit AND browser-e2e where applicable) before finishing.
> Kept as a pointer to a single source of truth to avoid conflicting-instruction precedence.
