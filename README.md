# Accessibility Assistant

An AI-assisted support desk for accessibility (Section 508 / WCAG 2.1 AA) questions. It answers questions
deterministically first — from curated FAQs and configured information sources — and falls back to an
LLM (grounded in the same sources, via retrieval-augmented generation) only when no deterministic match is
found, alerting an admin whenever a question can't be answered at all.

Built on the SD-Agile Platform's Python chassis: FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, Alembic,
PostgreSQL, and Redis, with multi-tenant isolation, RBAC, audit logging, and a server-rendered USWDS 3.0
UI (Section 508 / WCAG 2.1 AA) provided by the chassis itself.

## Features

- **Information Sources** — configure local code repos, GitHub repos, document folders, or MCP servers
  as grounding material for answers, organized into categories. Credentials are AES-256-GCM encrypted.
- **Question Categories & FAQs** — curate manually-authored FAQs, tagged by question category and linked
  to the information sources/categories they draw from.
- **Deterministic-first answering** — an incoming question is matched against FAQs (exact, keyword, then
  regex) before any LLM call is made.
- **LLM fallback with RAG** — when no deterministic match exists, an LLM answers grounded in the
  configured information sources; per-(source category, question category) fallback mode is configurable.
- **Unanswerable alerts** — when neither path produces an answer, an acknowledgeable alert is dispatched
  to Org Admins / Content Managers.

## Tech Stack

FastAPI 0.115 · SQLAlchemy 2.0 async · Pydantic v2 · Alembic · PostgreSQL (via psycopg3) · Redis ·
Jinja2 + USWDS 3.0 · pytest / pytest-asyncio · mypy --strict · ruff

## Setup

```bash
cp .env.example .env   # fill in JWT_SECRET, MFA_ENCRYPTION_KEY, LLM_ENCRYPTION_KEY, POSTGRES_PASSWORD
docker compose up --build
```

See `DEPLOYMENT.md` for full deployment instructions and `.env.example` for how to generate each secret.

## API Overview

REST endpoints for information source categories/sources, question categories, FAQs, question answering,
and LLM fallback configuration — see `API-DOCS.md` for the full endpoint reference and `DESIGN.md` for the
underlying data model and architecture.

## Documentation

This repository ships a full spec-first Build Package — see `CONSTITUTION.md` (architectural principles),
`REQUIREMENTS.md` (what this application does), `DESIGN.md` (how it's built), `TASKS.md` (build order), and
`TEST-SCENARIOS.md` (test coverage), plus `HOW-IT-WORKS.md` and `USER-GUIDE.md` for a narrative overview.
