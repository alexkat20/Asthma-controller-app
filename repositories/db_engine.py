"""
Подключение к БД — SQLite (локальный файл, по умолчанию) или PostgreSQL,
выбирается переменной окружения DB_BACKEND, без изменений в коде.

Примеры запуска:
    # SQLite (по умолчанию, ничего настраивать не нужно)
    uvicorn main:app

    # PostgreSQL через отдельные переменные
    DB_BACKEND=postgres POSTGRES_HOST=localhost POSTGRES_DB=peakflow \\
    POSTGRES_USER=peakflow POSTGRES_PASSWORD=secret uvicorn main:app

    # PostgreSQL через готовую строку подключения (приоритетнее отдельных переменных)
    DB_BACKEND=postgres DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db uvicorn main:app

Драйвер Postgres — psycopg (v3, пакет psycopg[binary]), современная замена
psycopg2 с тем же диалектом postgresql+psycopg в SQLAlchemy 2.x.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_BACKEND = os.environ.get("DB_BACKEND", "sqlite").strip().lower()


def _build_database_url() -> str:
    if DB_BACKEND in ("postgres", "postgresql"):
        explicit_url = os.environ.get("DATABASE_URL")
        if explicit_url:
            return explicit_url
        user = os.environ.get("POSTGRES_USER", "postgres")
        password = os.environ.get("POSTGRES_PASSWORD", "postgres")
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5432")
        name = os.environ.get("POSTGRES_DB", "peakflow")
        return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"

    # SQLite — как и раньше, один локальный файл.
    sqlite_path = os.environ.get("SQLITE_PATH", "peak_flow.db")
    return f"sqlite:///{sqlite_path}"


DATABASE_URL = _build_database_url()

# check_same_thread=False нужен только SQLite: по умолчанию соединение SQLite
# нельзя использовать из другого потока, а FastAPI/Starlette может обслуживать
# запрос не в том потоке, что открыл соединение. PostgreSQL этого ограничения
# не имеет, поэтому connect_args для него пустые.
_connect_args = (
    {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_session():
    """Открывает новую сессию. Вызывающий код отвечает за session.commit()/close() —
    тот же контракт, что был у прежнего sqlite3.Connection (см. database.py)."""
    return SessionLocal()
