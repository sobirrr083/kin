"""
middlewares/subscription.py — Majburiy obuna tekshiruvi.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import get_required_chats, get_user_by_id, update_user_activity

logger = logging.getLogger(__name__)


async def check_user_subscriptions(bot: Bot, user_id: int, chats: list) -> list:
    """
    Foydalanuvchi qaysi kanallarga a'zo emasligini qaytaradi.
    Bot kanalda admin bo'lmasa yoki xato chiqsa — o'sha kanal o'tkazib yuboriladi.
    """
    not_subscribed = []
    for chat in chats:
        try:
            member = await bot.get_chat_member(chat.chat_id, user_id)
            if member.status in ("left", "kicked", "banned"):
                not_subscribed.append(chat)
        except TelegramForbiddenError:
            logger.warning(
                "Bot kanal %s da admin emas — subscription tekshirilmadi, o'tkazildi",
                chat.chat_id,
            )
        except Exception as exc:
            logger.warning("Kanal %s tekshirishda xato: %s — o'tkazildi", chat.chat_id, exc)
    return not_subscribed


class SubscriptionMiddleware(BaseMiddleware):
    """
    Majburiy obuna tekshiruvi.
    SUBSCRIPTION_ENABLED = True  →  yoqilgan
    SUBSCRIPTION_ENABLED = False →  o'chirilgan (hammani o'tkazadi)
    """

    SUBSCRIPTION_ENABLED = True  # ✅ YOQILGAN

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        # O'chirilgan bo'lsa hammani o'tkazamiz
        if not self.SUBSCRIPTION_ENABLED:
            return await handler(event, data)

        # Faqat private chatlarda tekshiramiz
        if event.chat.type != "private":
            return await handler(event, data)

        session: AsyncSession = data.get("session")
        bot: Bot = data.get("bot")

        if not session or not bot or not event.from_user:
            return await handler(event, data)

        from config import settings
        from filters.admin import get_all_admin_ids

        user_id = event.from_user.id

        # Admin har doim o'tadi (statik + dinamik adminlar)
        if user_id in get_all_admin_ids():
            return await handler(event, data)

        # Til tanlanmagan → to'g'ridan-to'g'ri o'tadi (til tanlash oqimi ishlashi uchun)
        user = await get_user_by_id(session, user_id)
        if user is None or user.language is None:
            return await handler(event, data)

        # Majburiy kanallar yo'q → o'tadi
        required_chats = await get_required_chats(session)
        if not required_chats:
            await update_user_activity(session, user_id)
            return await handler(event, data)

        # A'zolikni tekshiramiz
        not_subscribed = await check_user_subscriptions(bot, user_id, required_chats)
        if not_subscribed:
            from keyboards.inline import kb_subscription
            from locales import t

            await event.answer(
                t(user.language, "subscribe_required"),
                reply_markup=kb_subscription(not_subscribed, user.language),
                parse_mode="HTML",
            )
            return  # Handleriga yo'q bermaymiz

        await update_user_activity(session, user_id)
        return await handler(event, data)
