"""
middlewares/subscription.py — Majburiy obuna tekshiruvi.

Arxitektura:
  - Faqat private chatlarda ishlaydi
  - Admin (statik + dinamik) har doim o'tadi
  - Til tanlanmagan foydalanuvchi o'tadi (til tanlash oqimi ishlashi uchun)
  - Majburiy kanallar DB da yo'q bo'lsa — o'tadi
  - A'zo bo'lmagan kanallari bo'lsa — subscription xabari ko'rsatiladi
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
    Foydalanuvchi a'zo bo'lmagan kanallar ro'yxatini qaytaradi.

    Statuses:
      member, creator, administrator → a'zo ✅
      left, kicked, restricted       → a'zo emas ❌
      Xato (bot admin emas, kanal topilmadi) → o'tkazib yuboriladi (kanal hisoblanmaydi)
    """
    not_subscribed = []
    for chat in chats:
        try:
            member = await bot.get_chat_member(chat.chat_id, user_id)
            if member.status in ("left", "kicked", "restricted"):
                not_subscribed.append(chat)
            # member, creator, administrator → o'tadi
        except TelegramForbiddenError:
            # Bot kanalda admin emas — bu kanal tekshiruvdan chiqariladi
            logger.warning(
                "Bot kanal %s (%s) da admin emas — subscription tekshirilmadi, o'tkazildi",
                chat.chat_id, chat.title,
            )
        except Exception as exc:
            logger.warning(
                "Kanal %s (%s) tekshirishda xato: %s — o'tkazildi",
                chat.chat_id, chat.title, exc,
            )
    return not_subscribed


class SubscriptionMiddleware(BaseMiddleware):
    """
    Majburiy obuna tekshiruvi middleware.
    Har bir private chat xabaridan oldin ishlaydi.
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

        from filters.admin import get_all_admin_ids

        user_id = event.from_user.id

        # ── Admin har doim o'tadi (statik + dinamik) ─────────────────────────
        if user_id in get_all_admin_ids():
            return await handler(event, data)

        # ── Til tanlanmagan → til tanlash oqimi ishlaydi ─────────────────────
        user = await get_user_by_id(session, user_id)
        if user is None or user.language is None:
            return await handler(event, data)

        # ── Majburiy kanallar yo'q → o'tadi ──────────────────────────────────
        required_chats = await get_required_chats(session)
        if not required_chats:
            await update_user_activity(session, user_id)
            return await handler(event, data)

        # ── A'zolik tekshiruvi ────────────────────────────────────────────────
        not_subscribed = await check_user_subscriptions(bot, user_id, required_chats)
        if not_subscribed:
            from keyboards.inline import kb_subscription
            from locales import t

            logger.info(
                "Subscription block: user_id=%s | a'zo emas: %s",
                user_id,
                [c.chat_id for c in not_subscribed],
            )
            await event.answer(
                t(user.language, "subscribe_required"),
                reply_markup=kb_subscription(not_subscribed, user.language),
                parse_mode="HTML",
            )
            return  # Handler chaqirilmaydi

        # ── Barcha kanallarga a'zo ✅ ─────────────────────────────────────────
        await update_user_activity(session, user_id)
        return await handler(event, data)
