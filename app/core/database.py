"""Asynchronous PostgreSQL engine and scoped transaction helpers."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Shared ORM metadata."""


engine = create_async_engine(
    get_settings().database_url, pool_pre_ping=True, echo=False
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def transaction() -> AsyncIterator[AsyncSession]:
    """Commit a short unit of work, rolling back on failure."""
    async with SessionLocal() as db:
        async with db.begin():
            yield db
