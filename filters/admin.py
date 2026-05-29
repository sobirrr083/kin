"""
filters/admin.py — Custom aiogram BaseFilter subclasses.

IsAdmin       — Passes only for users whose ID is in settings.ADMIN_IDS.
IsStorageGroup — Passes only for messages originating from STORAGE_GROUP_ID.

These are registered at the router level so every handler in a router
automatically inherits the access restriction without repeating code.
"""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from config import settings


class IsAdmin(BaseFilter):
    """
    Allow the handler to run only when the sender is a configured admin.

    Works for both Message and CallbackQuery update types.
    """

    async def __call__(self, event: Message | CallbackQuery) -> bool:  # type: ignore[override]
        user = getattr(event, "from_user", None)
        if user is None:
            return False
        return user.id in settings.ADMIN_IDS


class IsStorageGroup(BaseFilter):
    """
    Allow the handler to run only when the message originates from
    the configured STORAGE_GROUP_ID (the private movie ingestion channel).
    """

    async def __call__(self, message: Message) -> bool:  # type: ignore[override]
        return message.chat.id == settings.STORAGE_GROUP_ID
