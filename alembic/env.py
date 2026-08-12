"""
Alembic-окружение: URL и engine берутся из repositories/db_engine.py (та же
переменная окружения DB_BACKEND, что использует само приложение), поэтому
`alembic upgrade head` применяет миграции ровно к той БД, с которой в этот
момент работает FastAPI-приложение — SQLite или PostgreSQL, без отдельной
настройки для Alembic.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool

from alembic import context

# Корень проекта — на один уровень выше папки alembic/ — нужен в sys.path,
# чтобы импортировать repositories.* при запуске `alembic` как отдельной команды.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from repositories.db_engine import DATABASE_URL  # noqa: E402
from repositories.orm_models import (
    Base,
)  # noqa: E402  (импорт регистрирует все модели в Base.metadata)

config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine

    connect_args = (
        {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
    )
    connectable = create_engine(
        DATABASE_URL, connect_args=connect_args, poolclass=pool.NullPool
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
