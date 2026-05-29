"""
middlewares/database.py — Database session middleware.

Injects a fresh AsyncSession into `data["session"]` for every incoming
update.  Handlers declare `session: AsyncSession` in their signature and
aiogram resolves it automatically via dependency injection.

The session is committed/rolled-back and closed here, so handlers never
need to manage the session lifecycle themselves.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from database.engine import async_session_maker

logger = logging.getLogger(__name__)


class DatabaseMiddleware(BaseMiddleware):
    """
    Opens a new AsyncSession for every update, passes it to the handler
    via data["session"], and ensures cleanup regardless of success/failure.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with async_session_maker() as session:
            data["session"] = session
            try:
                return await handler(event, data)
            except Exception:
                # Roll back any uncommitted changes on unexpected errors.
                await session.rollback()
                raise
            # Session is closed automatically by the context manager.
