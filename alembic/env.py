from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from shared.config import settings
from shared.db.base import Base

# Ensure all ORM models are imported so metadata includes every table.
import company.models  # noqa: F401
import industry.models  # noqa: F401
import integration.models  # noqa: F401
import macro.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _database_url() -> str:
    return os.getenv("SUPABASE_DB_URL", settings.supabase_db_url)


def _schema() -> str:
    return os.getenv("SUPABASE_SCHEMA", settings.supabase_schema)


def _configure_alembic_url() -> None:
    config.set_main_option("sqlalchemy.url", _database_url())


def include_object(object_, name, type_, reflected, compare_to):
    _ = (object_, name, type_, reflected, compare_to)
    return True


def run_migrations_offline() -> None:
    _configure_alembic_url()
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_object=include_object,
        version_table_schema=_schema(),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    _configure_alembic_url()
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            include_schemas=True,
            include_object=include_object,
            version_table_schema=_schema(),
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
