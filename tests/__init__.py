"""Chassis test suite.

Tests use the same docker-compose'd Postgres + Redis as dev (ports 5532/6479)
by default. Override DATABASE_URL via environment if you want isolation —
the chassis honors it through Settings.

Per-test isolation: every test starts by TRUNCATE-ing every chassis table
EXCEPT alembic_version. Slot test files (e.g. tests/test_slots_example.py)
are responsible for any per-test data setup. The truncation strategy keeps
tests honest and is fast enough for ~100 test cases (~5s total at v0.1.0
chassis size).
"""
