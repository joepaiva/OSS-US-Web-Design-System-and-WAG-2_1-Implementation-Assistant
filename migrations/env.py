"""Alembic environment — async-compatible.

Runs Alembic migrations using SQLAlchemy 2.0 async engine. The pattern below
is the canonical Alembic 1.14 async recipe:

    async def run_async_migrations(): ...
    asyncio.run(run_async_migrations())

DO NOT use the synchronous Alembic env.py template — it would force
psycopg-async into psycopg-sync mode and break the chassis' async invariants.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Side-effect imports: every model module MUST be imported here so Alembic's
# `target_metadata` knows about every table for autogenerate.
from app.audit import models as _audit_models  # noqa: F401
from app.auth import models as _auth_models  # noqa: F401
from app.compliance.fisma_audit import models as _fisma_audit_models  # noqa: F401
from app.compliance.inventory import models as _platform_health_models  # noqa: F401
from app.config import get_settings
from app.db import Base
from app.orgs import models as _orgs_models  # noqa: F401
from app.rbac import models as _rbac_models  # noqa: F401

# Slots register their models here. LLMs add one line per slot.
from app.slots.example import models as _slot_example_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject DATABASE_URL from chassis settings so alembic.ini's placeholder doesn't matter.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL to stdout, no DB connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations via the async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
