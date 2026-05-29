"""
handlers/user.py — Foydalanuvchi private chat handlerlari.

Oqim:
  /start → til yo'q → til tanlash tugmalari
         → til bor → a'zolik tekshiruvi (middleware) → xush kelibsiz
  lang:uz / lang:ru → tilni saqlash → a'zolik tekshiruvi → xush kelibsiz
  check_sub         → a'zolikni qayta tekshirish
  <kod>             → kinoni topish va yuborish
"""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import (
    get_movie_by_code,
    get_or_create_user,
    get_required_chats,
    get_user_by_id,
    set_user_language,
    update_user_activity,
)
from keyboards.inline import kb_language_select, kb_subscription
from locales import t
from middlewares.subscription import check_user_subscriptions

logger = logging.getLogger(__name__)
router = Router(name="user")
router.message.filter(F.chat.type == "private")


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    user = message.from_user
    db_user, _ = await get_or_create_user(
        session,
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
    )

    # Til tanlanmagan → tilni so'rash
    if not db_user.language:
        await message.answer(
            t("uz", "choose_language"),
            reply_markup=kb_language_select(),
            parse_mode="HTML",
        )
        return

    # Til bor — a'zolik middleware tomonidan tekshiriladi,
    # shu yerda faqat xush kelibsiz xabarini ko'rsatamiz
    await message.answer(
        t(db_user.language, "welcome", name=user.first_name),
        parse_mode="HTML",
    )


# ── Til tanlash ───────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("lang:"))
async def cb_set_language(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    lang = callback.data.split(":")[1]  # "uz" yoki "ru"
    if lang not in ("uz", "ru"):
        await callback.answer("❌ Noto'g'ri til")
        return

    user_id = callback.from_user.id
    user = callback.from_user

    # Userni yaratish (agar yo'q bo'lsa) va tilni saqlash
    await get_or_create_user(
        session,
        user_id=user_id,
        username=user.username,
        full_name=user.full_name,
    )
    await set_user_language(session, user_id, lang)

    # Til saqlanganligi haqida xabar
    await callback.message.edit_text(
        t(lang, "language_saved"),
        parse_mode="HTML",
    )
    await callback.answer()

    # A'zolik tekshiruvi
    required_chats = await get_required_chats(session)
    if required_chats:
        not_subscribed = await check_user_subscriptions(bot, user_id, required_chats)
        if not_subscribed:
            await callback.message.answer(
                t(lang, "subscribe_required"),
                reply_markup=kb_subscription(required_chats, lang),
                parse_mode="HTML",
            )
            return

    # A'zo — xush kelibsiz
    await callback.message.answer(
        t(lang, "welcome", name=user.first_name),
        parse_mode="HTML",
    )


# ── A'zolikni tekshirish tugmasi ──────────────────────────────────────────────

@router.callback_query(F.data == "check_sub")
async def cb_check_subscription(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    user_id = callback.from_user.id
    db_user = await get_user_by_id(session, user_id)
    lang = db_user.language if db_user else "uz"

    required_chats = await get_required_chats(session)
    if not required_chats:
        await callback.message.edit_text(
            t(lang, "now_subscribed"),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    not_subscribed = await check_user_subscriptions(bot, user_id, required_chats)

    if not_subscribed:
        await callback.answer(t(lang, "still_not_subscribed"), show_alert=True)
        return

    # Barcha kanallarga a'zo ✅
    await update_user_activity(session, user_id)
    await callback.message.edit_text(
        t(lang, "now_subscribed"),
        parse_mode="HTML",
    )
    await callback.answer()

    # Xush kelibsiz xabarini yuborish
    await callback.message.answer(
        t(lang, "welcome", name=callback.from_user.first_name),
        parse_mode="HTML",
    )


# ── Kino kodi ─────────────────────────────────────────────────────────────────

@router.message(F.text.regexp(r"^[A-Za-z0-9]+$"))
async def handle_movie_code(message: Message, session: AsyncSession, bot: Bot) -> None:
    """
    Alphanumeric xabar → kino kodi sifatida qabul qilinadi.
    Subscription middleware bu handler ga yetib kelishidan oldin
    a'zolikni tekshiradi.
    """
    db_user = await get_user_by_id(session, message.from_user.id)
    lang = db_user.language if db_user else "uz"
    code = message.text.strip()

    movie = await get_movie_by_code(session, code)
    if movie is None:
        await message.answer(t(lang, "movie_not_found", code=code), parse_mode="HTML")
        return

    caption = (
        t(lang, "movie_caption", title=movie.title, code=movie.code)
        if movie.title
        else t(lang, "movie_caption_no_title", code=movie.code)
    )

    try:
        if movie.file_type == "video":
            await bot.send_video(message.chat.id, video=movie.file_id,
                                 caption=caption, parse_mode="HTML")
        else:
            await bot.send_document(message.chat.id, document=movie.file_id,
                                    caption=caption, parse_mode="HTML")
        logger.info("Kino yuborildi: code=%s → user=%s", code, message.from_user.id)
    except Exception as exc:
        logger.error("Kino yuborishda xato: code=%s error=%s", code, exc)
        await message.answer(t(lang, "movie_send_error", code=code), parse_mode="HTML")
