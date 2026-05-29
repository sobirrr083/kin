"""
middlewares/subscription.py — Majburiy a'zolik tekshiruvi.

Har bir private chat xabarida:
  1. User DB da yo'q yoki tili yo'q → o'tkazib yuboradi (language handler ishlaydi)
  2. Majburiy kanallar yo'q → o'tkazib yuboradi
  3. User barcha kanallarga a'zo → faoliyatni yangilaydi, davom etadi
  4. A'zo emas → a'zolik xabarini yuboradi va to'xtatadi
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import (
    get_required_chats,
    get_user_by_id,
    update_user_activity,
)

logger = logging.getLogger(__name__)


async def check_user_subscriptions(
    bot: Bot, user_id: int, chats: list
) -> list:
    """
    Userning qaysi kanallarga a'zo emasligini qaytaradi.
    Tekshirib bo'lmaydigan kanal (bot admin emas) o'tkazib yuboriladi.
    """
    not_subscribed = []
    for chat in chats:
        try:
            member = await bot.get_chat_member(chat.chat_id, user_id)
            if member.status in ("left", "kicked", "banned"):
                not_subscribed.append(chat)
        except TelegramForbiddenError:
            # Bot kanalda admin emas — tekshira olmaydi, o'tkazib yuboramiz
            logger.warning("Bot kanal %s da a'zolikni tekshira olmadi", chat.chat_id)
        except Exception as exc:
            logger.warning("Kanal %s tekshirishda xato: %s", chat.chat_id, exc)
    return not_subscribed


class SubscriptionMiddleware(BaseMiddleware):
    """
    Faqat private chat Message larini tekshiradi.
    CallbackQuery lar bu middleware dan o'tmaydi — ular
    alohida (check_sub callback) handler da boshqariladi.
    """

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        # Faqat private chat
        if event.chat.type != "private":
            return await handler(event, data)

        session: AsyncSession = data.get("session")
        bot: Bot = data.get("bot")

        if not session or not bot or not event.from_user:
            return await handler(event, data)

        user_id = event.from_user.id
        user = await get_user_by_id(session, user_id)

        # User yo'q yoki tili tanlanmagan → language handler ishlaydi
        if user is None or user.language is None:
            return await handler(event, data)

        # Majburiy kanallar ro'yxati
        required_chats = await get_required_chats(session)
        if not required_chats:
            await update_user_activity(session, user_id)
            return await handler(event, data)

        # A'zolikni tekshirish
        not_subscribed = await check_user_subscriptions(bot, user_id, required_chats)

        if not_subscribed:
            # A'zo emas → subscription xabarini yuborish
            from keyboards.inline import kb_subscription
            from locales import t

            lang = user.language
            await event.answer(
                t(lang, "subscribe_required"),
                reply_markup=kb_subscription(required_chats, lang),
                parse_mode="HTML",
            )
            return  # Handleri chaqirmaymiz

        # Hammasi yaxshi — faoliyatni yangilash
        await update_user_activity(session, user_id)
        return await handler(event, data)
