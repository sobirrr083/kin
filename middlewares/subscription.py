"""
middlewares/subscription.py — VAQTINCHA O'CHIRILGAN.
Subscription tekshiruvi o'chirildi — hamma xabar to'g'ridan-to'g'ri o'tadi.
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
    not_subscribed = []
    for chat in chats:
        try:
            member = await bot.get_chat_member(chat.chat_id, user_id)
            if member.status in ("left", "kicked", "banned"):
                not_subscribed.append(chat)
        except TelegramForbiddenError:
            logger.warning("Bot kanal %s da admin emas", chat.chat_id)
        except Exception as exc:
            logger.warning("Kanal %s tekshirishda xato: %s", chat.chat_id, exc)
    return not_subscribed


class SubscriptionMiddleware(BaseMiddleware):
    """
    VAQTINCHA O'CHIRILGAN: Barcha xabarlar to'g'ridan-to'g'ri o'tadi.
    Yoqish uchun: SUBSCRIPTION_ENABLED = True qiling.
    """

    SUBSCRIPTION_ENABLED = False  # <-- False = o'chirilgan

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        if not self.SUBSCRIPTION_ENABLED:
            return await handler(event, data)

        if event.chat.type != "private":
            return await handler(event, data)

        session: AsyncSession = data.get("session")
        bot: Bot = data.get("bot")

        if not session or not bot or not event.from_user:
            return await handler(event, data)

        from config import settings
        user_id = event.from_user.id

        if user_id in settings.ADMIN_IDS:
            return await handler(event, data)

        user = await get_user_by_id(session, user_id)
        if user is None or user.language is None:
            return await handler(event, data)

        required_chats = await get_required_chats(session)
        if not required_chats:
            await update_user_activity(session, user_id)
            return await handler(event, data)

        not_subscribed = await check_user_subscriptions(bot, user_id, required_chats)
        if not_subscribed:
            from keyboards.inline import kb_subscription
            from locales import t
            await event.answer(
                t(user.language, "subscribe_required"),
                reply_markup=kb_subscription(required_chats, user.language),
                parse_mode="HTML",
            )
            return

        await update_user_activity(session, user_id)
        return await handler(event, data)
