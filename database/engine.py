"""
database/engine.py — Async SQLAlchemy engine and session factory.

Supports both SQLite (via aiosqlite) and PostgreSQL (via asyncpg)
depending on the DATABASE_URL in config.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings
from database.models import Base

logger = logging.getLogger(__name__)

# ── Engine ────────────────────────────────────────────────────────────────────
# pool_pre_ping=True validates connections before use, preventing
# "server closed the connection unexpectedly" errors on Railway.

_engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,          # Set True to log all SQL for debugging
    pool_pre_ping=True,
    # SQLite does not support concurrent connections the same way;
    # use StaticPool + check_same_thread=False only for SQLite:
    **(
        {
            "connect_args": {"check_same_thread": False},
        }
        if settings.DATABASE_URL.startswith("sqlite")
        else {}
    ),
)

# ── Session factory ───────────────────────────────────────────────────────────
# expire_on_commit=False keeps ORM objects usable after session.commit().
async_session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def create_tables() -> None:
    """Create all tables defined in models.py (idempotent — safe to call every startup)."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created / verified successfully.")


async def dispose_engine() -> None:
    """Gracefully close all connection-pool connections on shutdown."""
    await _engine.dispose()
    logger.info("Database engine disposed.")
