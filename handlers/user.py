"""
handlers/user.py — Foydalanuvchi private chat handlerlari.

Deep link oqimi:
  /start 1111  →  kod FSM ga saqlanadi
               →  til yo'q → til tanlash
               →  til bor, a'zo emas → subscription so'rov (kod saqlanadi)
               →  til bor, a'zo → kino darhol yuboriladi

Oddiy /start:
  /start → til yo'q → til tanlash
         → til bor → xush kelibsiz

check_sub → a'zolikni tekshiradi → a'zo bo'lsa pending kinoni yuboradi
"""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
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


# FSM — deep link dan kelgan kino kodini a'zolik tekshirilguncha saqlash
class UserStates(StatesGroup):
    pending_movie_code = State()


# ═══════════════════════════════════════════════════════════════════════════════
# Kino yuborish yordamchi funksiyasi
# ═══════════════════════════════════════════════════════════════════════════════

async def _send_movie(
    bot: Bot,
    chat_id: int,
    session: AsyncSession,
    code: str,
    lang: str,
) -> None:
    """
    Kino kodiga mos filmni yuboradi.
    extra_caption bo'lsa — caption ga qo'shadi.
    """
    movie = await get_movie_by_code(session, code)
    if movie is None:
        await bot.send_message(chat_id, t(lang, "movie_not_found", code=code), parse_mode="HTML")
        return

    # Caption quramiz
    if movie.title:
        caption = t(lang, "movie_caption", title=movie.title, code=movie.code)
    else:
        caption = t(lang, "movie_caption_no_title", code=movie.code)

    # Qo'shimcha matn bo'lsa qo'shamiz
    if movie.extra_caption:
        caption = f"{caption}\n\n{movie.extra_caption}"

    # Har doim qo'shiladigan qat'iy matn (oxirida)
    caption = f"{caption}\n\nTezkor Cinema - 🍿 Kino olamiga eng qisqa yo'l."

    try:
        if movie.file_type == "video":
            await bot.send_video(chat_id, video=movie.file_id, caption=caption, parse_mode="HTML")
        else:
            await bot.send_document(chat_id, document=movie.file_id, caption=caption, parse_mode="HTML")
        logger.info("Kino yuborildi: code=%s → chat_id=%s", code, chat_id)
    except Exception as exc:
        logger.error("Kino yuborishda xato: code=%s error=%s", code, exc)
        await bot.send_message(chat_id, t(lang, "movie_send_error", code=code), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════════════
# /start — deep link bilan va oddiy
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(CommandStart())
async def cmd_start(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
    command: CommandObject,
) -> None:
    user = message.from_user
    db_user, _ = await get_or_create_user(
        session, user_id=user.id, username=user.username, full_name=user.full_name,
    )

    # Deep link dan kino kodi kelganmi? → /start 1111
    deep_link_code: str | None = None
    if command.args and command.args.strip():
        raw = command.args.strip()
        # Faqat harf va raqamdan iborat bo'lsa — kino kodi
        if raw.isalnum():
            deep_link_code = raw
            logger.info("Deep link kod keldi: code=%s user=%s", deep_link_code, user.id)

    # Til tanlanmagan → tilni so'rash (kodni saqlaymiz)
    if not db_user.language:
        if deep_link_code:
            await state.set_state(UserStates.pending_movie_code)
            await state.update_data(pending_code=deep_link_code)
        await message.answer(t("uz", "choose_language"), reply_markup=kb_language_select(), parse_mode="HTML")
        return

    lang = db_user.language

    # A'zolikni tekshiramiz
    required_chats = await get_required_chats(session)
    if required_chats:
        not_subscribed = await check_user_subscriptions(bot, user.id, required_chats)
        if not_subscribed:
            if deep_link_code:
                await state.set_state(UserStates.pending_movie_code)
                await state.update_data(pending_code=deep_link_code)
            await message.answer(
                t(lang, "subscribe_required"),
                reply_markup=kb_subscription(not_subscribed, lang),
                parse_mode="HTML",
            )
            return

    # A'zo va til bor — agar kino kodi bo'lsa yuboramiz
    if deep_link_code:
        await state.clear()
        await _send_movie(bot, message.chat.id, session, deep_link_code, lang)
        return

    # Oddiy /start — xush kelibsiz
    await message.answer(t(lang, "welcome", name=user.first_name), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════════════
# Til tanlash
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("lang:"))
async def cb_set_language(
    callback: CallbackQuery, session: AsyncSession, bot: Bot, state: FSMContext
) -> None:
    lang = callback.data.split(":")[1]
    if lang not in ("uz", "ru"):
        await callback.answer("❌ Noto'g'ri til")
        return

    user = callback.from_user
    await get_or_create_user(session, user_id=user.id, username=user.username, full_name=user.full_name)
    await set_user_language(session, user.id, lang)

    await callback.message.edit_text(t(lang, "language_saved"), parse_mode="HTML")
    await callback.answer()

    # Pending kino kodi bormi?
    state_data = await state.get_data()
    pending_code: str | None = state_data.get("pending_code")

    # A'zolikni tekshiramiz
    required_chats = await get_required_chats(session)
    if required_chats:
        not_subscribed = await check_user_subscriptions(bot, user.id, required_chats)
        if not_subscribed:
            # Kodni saqlab subscription so'rav ko'rsatamiz
            if pending_code:
                await state.set_state(UserStates.pending_movie_code)
                await state.update_data(pending_code=pending_code)
            await callback.message.answer(
                t(lang, "subscribe_required"),
                reply_markup=kb_subscription(not_subscribed, lang),
                parse_mode="HTML",
            )
            return

    # A'zo — pending kino bo'lsa yuboramiz
    await state.clear()
    if pending_code:
        await _send_movie(bot, callback.message.chat.id, session, pending_code, lang)
        return

    await callback.message.answer(t(lang, "welcome", name=user.first_name), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════════════
# A'zolikni tekshirish tugmasi
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "check_sub")
async def cb_check_subscription(
    callback: CallbackQuery, session: AsyncSession, bot: Bot, state: FSMContext
) -> None:
    user_id = callback.from_user.id
    db_user = await get_user_by_id(session, user_id)
    lang = db_user.language if db_user else "uz"

    required_chats = await get_required_chats(session)
    if not required_chats:
        await state.clear()
        await callback.message.edit_text(t(lang, "now_subscribed"), parse_mode="HTML")
        await callback.answer()
        return

    not_subscribed = await check_user_subscriptions(bot, user_id, required_chats)
    if not_subscribed:
        await callback.answer(t(lang, "still_not_subscribed"), show_alert=True)
        return

    # Barcha kanallarga a'zo ✅
    await update_user_activity(session, user_id)
    await callback.message.edit_text(t(lang, "now_subscribed"), parse_mode="HTML")
    await callback.answer()

    # Pending kino kodi bormi?
    state_data = await state.get_data()
    pending_code: str | None = state_data.get("pending_code")
    await state.clear()

    if pending_code:
        # Avval kino yuboramiz, keyin xush kelibsiz
        await _send_movie(bot, callback.message.chat.id, session, pending_code, lang)
    else:
        await callback.message.answer(t(lang, "welcome", name=callback.from_user.first_name), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════════════
# Kino kodi — oddiy xabar orqali
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text.regexp(r"^[A-Za-z0-9]+$"))
async def handle_movie_code(message: Message, session: AsyncSession, bot: Bot) -> None:
    """
    Alphanumeric xabar → kino kodi sifatida qabul qilinadi.
    Subscription middleware bu handlerga yetib kelishidan oldin tekshiradi.
    """
    db_user = await get_user_by_id(session, message.from_user.id)
    lang = db_user.language if db_user else "uz"
    await _send_movie(bot, message.chat.id, session, message.text.strip(), lang)
