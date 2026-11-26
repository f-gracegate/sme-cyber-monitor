"""Migrations run as the database owner role, never as the application role."""

import os

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import settings
from app.models import Base

url = os.environ.get("ALEMBIC_DATABASE_URL") or settings.migration_database_url


def run_migrations_offline() -> None:
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
