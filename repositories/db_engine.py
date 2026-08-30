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

_connect_args = (
    {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_session():
    return SessionLocal()


def init_db() -> None:
    from repositories import orm_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
