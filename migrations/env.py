"""Alembic migrations environment — schema: samosbor."""

import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from alembic import context

load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from bot.models import Base  # noqa: E402

target_metadata = Base.metadata
target_metadata.schema = "samosbor"


def run_migrations_offline() -> None:
    """Offline mode."""
    url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="samosbor_alembic_version",
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Online mode."""
    url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    connectable = create_engine(url)

    with connectable.connect() as connection:
        # Создаём схему samosbor, если её нет
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS samosbor"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table="samosbor_alembic_version",
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()