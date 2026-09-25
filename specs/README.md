# Python-FastAPI Chassis — Specification (Build Package)

This directory is the **authoritative specification** for the python-fastapi chassis. The
chassis is a spec-governed subproject: code is derived from these documents (spec-first),
and the Build Package is sufficient to **regenerate the entire chassis with zero human
intervention**.

## The Build Package (5 documents)

| # | Document | Scope |
|---|---|---|
| 1 | [REQUIREMENTS.md](REQUIREMENTS.md) | **Technology-neutral** capabilities + policies. Shared basis for *all* platform chassis (python, .NET, Go). Names no language/framework. |
| 2 | [CONSTITUTION.md](CONSTITUTION.md) | Supreme & immutable. The python-fastapi stack (exact pins), architectural invariants, security rules, coding standards, forbidden patterns, extension contract. |
| 3 | [DESIGN.md](DESIGN.md) | Technology-specific realization: module layout, all data models, endpoint catalog, mechanisms, config, migrations, FR→design traceability. |
| 4 | [TASKS.md](TASKS.md) | Ordered regeneration build order (Phases 0–9), each task mapped to files + its TEST-SCENARIOS exit criterion. |
| 5 | [TEST-SCENARIOS.md](TEST-SCENARIOS.md) | TS groups for every capability mapped to the 203-test suite. |

## Supplemental documentation

- [`../README.md`](../README.md) — overview + quickstart + capability/spec index
- [`../CHANGELOG.md`](../CHANGELOG.md) — version history (0.1.0 → 0.10.0)
- [`../docs/HOW-IT-WORKS.md`](../docs/HOW-IT-WORKS.md) — operator overview
- [`../docs/USER-MANUAL.md`](../docs/USER-MANUAL.md) — end-user + admin guide
- [`../docs/SECURITY-SELF-AUDIT.md`](../docs/SECURITY-SELF-AUDIT.md) — NIST 800-53 FISMA-Moderate control mapping
- [`../docs/`](../docs/) — NFR baselines, responsive design, state handling, slot testing
- [`../ARCHITECTURE.md`](../ARCHITECTURE.md) — LLM-facing slot-authoring reference

## Precedence

CONSTITUTION.md is supreme for this chassis. Where any other document conflicts with it,
the CONSTITUTION wins. REQUIREMENTS.md is shared across chassis and supreme for *what
capabilities* must exist; each chassis's CONSTITUTION/DESIGN say *how*.

## Change protocol

Spec-first: amend the relevant document(s) here (bump version + CHANGELOG) **before** code;
implement; run `uv run pytest -q` + `ruff` + `mypy`; bump `CHASSIS_VERSION` and the platform
Go seed pin together (CI enforces equality); record in `../CHANGELOG.md`.
