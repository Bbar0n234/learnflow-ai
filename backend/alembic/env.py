import asyncio
from logging.config import fileConfig

import sqlalchemy as sa
from alembic import context
from app.config import Settings
from app.models import Base  # noqa: F401 — ensure all models registered
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# LangGraph-managed tables — excluded from autogenerate
LANGGRAPH_TABLES = {
    "checkpoint_migrations",
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "store",
    "store_migrations",
    "store_vectors",
    "vector_migrations",
}


def include_object(
    object: sa.schema.SchemaItem,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: sa.schema.SchemaItem | None,
) -> bool:
    return not (type_ == "table" and name in LANGGRAPH_TABLES)


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_database_url() -> str:
    settings = Settings()
    return settings.database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    config.set_main_option("sqlalchemy.url", _get_database_url())

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
