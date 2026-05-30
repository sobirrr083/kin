"""
filters/admin.py — IsAdmin va IsStorageGroup filterlari.
Dinamik adminlar DB dan olinadi + statik ADMIN_IDS bilan birlashtiriladi.
"""
from __future__ import annotations

import logging

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from config import settings

logger = logging.getLogger(__name__)

# Runtime da DB dan yuklanadigan dinamik admin IDlar (set)
# admin.py tomonidan yangilanadi
_dynamic_admin_ids: set[int] = set()


def update_dynamic_admins(ids: list[int]) -> None:
    """DB dan olingan dinamik admin IDlarini xotiraga yuklaydi."""
    global _dynamic_admin_ids
    _dynamic_admin_ids = set(ids)
    logger.debug("Dinamik adminlar yangilandi: %s", _dynamic_admin_ids)


def get_all_admin_ids() -> set[int]:
    """Statik + dinamik barcha admin IDlar."""
    return set(settings.ADMIN_IDS) | _dynamic_admin_ids


def get_head_admin_id() -> int | None:
    """Bosh admin — ADMIN_IDS[0]."""
    return settings.ADMIN_IDS[0] if settings.ADMIN_IDS else None


class IsAdmin(BaseFilter):
    """True — foydalanuvchi statik yoki dinamik admin bo'lsa."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        if user is None:
            return False
        all_ids = get_all_admin_ids()
        result = user.id in all_ids
        if not result:
            logger.debug(
                "IsAdmin: ruxsat yo'q — user_id=%s | all_admins=%s",
                user.id, all_ids,
            )
        return result


class IsStorageGroup(BaseFilter):
    """True — xabar STORAGE_GROUP_ID dan kelgan bo'lsa."""

    async def __call__(self, event: Message) -> bool:
        return event.chat.id == settings.STORAGE_GROUP_ID
