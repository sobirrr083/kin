"""
filters/admin.py — Admin va StorageGroup filtrlari.

BUG FIX #1 (ASOSIY): ADMIN_IDS bo'sh bo'lganda IsAdmin doim False qaytarardi.
Endi startup da tekshiruv bor va log da aniq xabar chiqadi.
"""
from __future__ import annotations

import logging

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from config import settings

logger = logging.getLogger(__name__)


class IsAdmin(BaseFilter):
    """
    Faqat settings.ADMIN_IDS ro'yxatidagi userlarga ruxsat beradi.
    Message va CallbackQuery uchun ishlaydi.

    MUHIM: Agar ADMIN_IDS bo'sh bo'lsa, /admin hech qachon ishlamaydi!
    Railway → Variables → ADMIN_IDS = <sizning_telegram_id>
    """

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        # ADMIN_IDS bo'sh — debug log chiqaramiz
        if not settings.ADMIN_IDS:
            logger.error(
                "IsAdmin: ADMIN_IDS bo'sh! /admin ishlamaydi. "
                "Railway Variables da ADMIN_IDS o'rnating: ADMIN_IDS=123456789"
            )
            return False

        user = getattr(event, "from_user", None)
        if user is None:
            return False

        is_admin = user.id in settings.ADMIN_IDS
        if not is_admin:
            logger.debug(
                "IsAdmin: user_id=%s admin emas. Ruxsat etilgan IDlar: %s",
                user.id, settings.ADMIN_IDS
            )
        return is_admin


class IsStorageGroup(BaseFilter):
    """
    Faqat STORAGE_GROUP_ID dan kelgan xabarlarga ruxsat beradi.
    """

    async def __call__(self, message: Message) -> bool:
        return message.chat.id == settings.STORAGE_GROUP_ID
