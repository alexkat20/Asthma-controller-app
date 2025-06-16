from sqlalchemy import func, String, UUID
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine, AsyncSession
import os
from dotenv import load_dotenv
from uuid6 import uuid7

load_dotenv()


DATABASE_USER = os.environ["DATABASE_USER"]
DATABASE_PASSWORD = os.environ["DATABASE_PASSWORD"]
DATABASE_HOST = os.environ["DATABASE_HOST"]
DATABASE_NAME = os.environ["DATABASE_NAME"]
DATABASE_SCHEMA = os.environ["DATABASE_SCHEMA"]
DATABASE_PORT = os.environ["DATABASE_PORT"]

DATABASE_URL = (
    f"postgresql+asyncpg://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
)

engine = create_async_engine(url=DATABASE_URL)
async_session = async_sessionmaker(engine, class_=AsyncSession)


def connection(func):
    async def wrapper(*args, **kwargs):
        async with async_session() as session:
            return await func(session, *args, **kwargs)

    return wrapper


class Base(AsyncAttrs, DeclarativeBase):
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=uuid7)