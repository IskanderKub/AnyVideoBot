"""Async SQLAlchemy engine and sessions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from loguru import logger
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.db.models import Base

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _ensure_sqlite_dir(url: str) -> None:
    """For SQLite, create the database file directory - otherwise the engine fails
    on the first connection."""
    if not url.startswith("sqlite"):
        return
    _, _, path_part = url.partition(":///")
    if not path_part or path_part == ":memory:":
        return
    Path(path_part).expanduser().parent.mkdir(parents=True, exist_ok=True)


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _ensure_sqlite_dir(settings.database_url)
        _engine = create_async_engine(settings.database_url, pool_pre_ping=True, future=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Session that commits on exit and rolls back on exception."""
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create the tables. Real migrations are handled by alembic."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Схема БД готова: {}", settings.database_url.split("://")[0])


async def close_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
