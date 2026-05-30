"""
filters/admin.py — IsAdmin va IsStorageGroup filterlari.
"""
from __future__ import annotations

import logging

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from config import settings

logger = logging.getLogger(__name__)


class IsAdmin(BaseFilter):
    """True — foydalanuvchi ADMIN_IDS ro'yxatida bo'lsa."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        if user is None:
            return False
        result = user.id in settings.ADMIN_IDS
        if not result:
            logger.debug(
                "IsAdmin: ruxsat yo'q — user_id=%s | ADMIN_IDS=%s",
                user.id, settings.ADMIN_IDS,
            )
        return result


class IsStorageGroup(BaseFilter):
    """True — xabar STORAGE_GROUP_ID dan kelgan bo'lsa."""

    async def __call__(self, event: Message) -> bool:
        return event.chat.id == settings.STORAGE_GROUP_ID
