"""SDK core database infrastructure — SQLAlchemy engine and session factory."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from sdk.core.config import config


# Convert sync SQLite URL to async aiosqlite URL
def _get_async_db_url(url: str) -> str:
    """Convert sync SQLite URL to async aiosqlite URL."""
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///")
    elif url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://")
    return url


# Async SQLAlchemy engine
engine = create_async_engine(
    _get_async_db_url(config.db_url),
    echo=config.db_echo,
    pool_pre_ping=True,
    # SQLite-specific settings
    connect_args={"check_same_thread": False} if "sqlite" in config.db_url else {},
)

# Async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all tables (call once at startup)."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def close_db() -> None:
    """Close all database connections (call at shutdown)."""
    await engine.dispose()


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Context manager for async database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
