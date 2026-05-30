"""
handlers/user.py — Foydalanuvchi private chat handlerlari.

Oqim:
  /start [kod]
    → til yo'q         → til tanlash (kod pending da saqlanadi)
    → a'zo emas        → subscription xabari (kod pending da saqlanadi)
    → hamma joyida OK  → agar kod bor → kino yuboriladi
                          agar kod yo'q → xush kelibsiz

  Til tanlangach:
    → a'zo emas        → subscription xabari
    → a'zo             → pending kino yoki xush kelibsiz

  check_sub bosilsa:
    → a'zo emas        → xato xabar
    → a'zo             → pending kino yoki xush kelibsiz

  Kino kodi (4-5 xona, StateFilter(None)):
    → Subscription middleware allaqachon tekshirgan
    → to'g'ridan-to'g'ri kino yuboriladi
"""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart, StateFilter
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


class UserStates(StatesGroup):
    pending_movie_code = State()


# ═══════════════════════════════════════════════════════════════════════════════
# Kino yuborish
# ═══════════════════════════════════════════════════════════════════════════════

async def _send_movie(bot: Bot, chat_id: int, session: AsyncSession, code: str, lang: str) -> None:
    movie = await get_movie_by_code(session, code)
    if movie is None:
        await bot.send_message(chat_id, t(lang, "movie_not_found", code=code), parse_mode="HTML")
        return

    if movie.title:
        caption = t(lang, "movie_caption", title=movie.title, code=movie.code)
    else:
        caption = t(lang, "movie_caption_no_title", code=movie.code)

    if movie.extra_caption:
        caption = f"{caption}\n\n{movie.extra_caption}"

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


async def _show_subscription(
    target: Message | CallbackQuery,
    not_subscribed: list,
    lang: str,
) -> None:
    """Subscription xabarini chiqaradi (Message yoki CallbackQuery uchun)."""
    kb = kb_subscription(not_subscribed, lang)
    text = t(lang, "subscribe_required")
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════════════
# /start
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(CommandStart())
async def cmd_start(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
    command: CommandObject,
) -> None:
    await state.clear()
    user = message.from_user
    db_user, _ = await get_or_create_user(
        session, user_id=user.id, username=user.username, full_name=user.full_name,
    )

    # Deep link kodi
    deep_code: str | None = None
    if command.args and command.args.strip():
        raw = command.args.strip()
        if raw.isalnum():
            deep_code = raw
            logger.info("Deep link: code=%s user=%s", deep_code, user.id)

    # ── 1. Til yo'q → til tanlash ─────────────────────────────────────────────
    if not db_user.language:
        if deep_code:
            await state.set_state(UserStates.pending_movie_code)
            await state.update_data(pending_code=deep_code)
        await message.answer(t("uz", "choose_language"), reply_markup=kb_language_select(), parse_mode="HTML")
        return

    lang = db_user.language

    # ── 2. Subscription tekshiruvi ─────────────────────────────────────────────
    required_chats = await get_required_chats(session)
    if required_chats:
        not_subscribed = await check_user_subscriptions(bot, user.id, required_chats)
        if not_subscribed:
            if deep_code:
                await state.set_state(UserStates.pending_movie_code)
                await state.update_data(pending_code=deep_code)
            await _show_subscription(message, not_subscribed, lang)
            return

    # ── 3. Hamma joyida OK ────────────────────────────────────────────────────
    await state.clear()
    if deep_code:
        await _send_movie(bot, message.chat.id, session, deep_code, lang)
    else:
        await message.answer(t(lang, "welcome", name=user.first_name), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════════════
# Til tanlash
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("lang:"))
async def cb_set_language(
    callback: CallbackQuery, session: AsyncSession, bot: Bot, state: FSMContext
) -> None:
    lang_code = callback.data.split(":")[1]
    if lang_code not in ("uz", "ru"):
        await callback.answer("❌ Noto'g'ri til")
        return

    user = callback.from_user
    await get_or_create_user(session, user_id=user.id, username=user.username, full_name=user.full_name)
    await set_user_language(session, user.id, lang_code)
    await callback.message.edit_text(t(lang_code, "language_saved"), parse_mode="HTML")
    await callback.answer()

    state_data = await state.get_data()
    pending_code: str | None = state_data.get("pending_code")

    # ── Subscription tekshiruvi ────────────────────────────────────────────────
    required_chats = await get_required_chats(session)
    if required_chats:
        not_subscribed = await check_user_subscriptions(bot, user.id, required_chats)
        if not_subscribed:
            if pending_code:
                await state.set_state(UserStates.pending_movie_code)
                await state.update_data(pending_code=pending_code)
            await callback.message.answer(
                t(lang_code, "subscribe_required"),
                reply_markup=kb_subscription(not_subscribed, lang_code),
                parse_mode="HTML",
            )
            return

    # ── A'zo ─────────────────────────────────────────────────────────────────
    await state.clear()
    if pending_code:
        await _send_movie(bot, callback.message.chat.id, session, pending_code, lang_code)
    else:
        await callback.message.answer(t(lang_code, "welcome", name=user.first_name), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════════════
# A'zolikni tekshirish
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "check_sub")
async def cb_check_subscription(
    callback: CallbackQuery, session: AsyncSession, bot: Bot, state: FSMContext
) -> None:
    user_id = callback.from_user.id
    db_user = await get_user_by_id(session, user_id)
    lang = db_user.language if db_user else "uz"

    required_chats = await get_required_chats(session)

    # Kanallar yo'q yoki hammaga a'zo
    if not required_chats:
        await state.clear()
        await callback.message.edit_text(t(lang, "now_subscribed"), parse_mode="HTML")
        await callback.answer()
        await callback.message.answer(t(lang, "welcome", name=callback.from_user.first_name), parse_mode="HTML")
        return

    not_subscribed = await check_user_subscriptions(bot, user_id, required_chats)

    if not_subscribed:
        # Hali a'zo emas — tugmalarni yangilaymiz (yangi holat bo'lishi mumkin)
        await callback.message.edit_reply_markup(
            reply_markup=kb_subscription(not_subscribed, lang)
        )
        await callback.answer(t(lang, "still_not_subscribed"), show_alert=True)
        return

    # ── Barcha kanallarga a'zo ✅ ─────────────────────────────────────────────
    await update_user_activity(session, user_id)
    await callback.message.edit_text(t(lang, "now_subscribed"), parse_mode="HTML")
    await callback.answer()

    state_data = await state.get_data()
    pending_code: str | None = state_data.get("pending_code")
    await state.clear()

    if pending_code:
        await _send_movie(bot, callback.message.chat.id, session, pending_code, lang)
    else:
        await callback.message.answer(t(lang, "welcome", name=callback.from_user.first_name), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════════════
# Havola yo'q kanal tugmasi (no-op)
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "sub_no_link")
async def cb_sub_no_link(callback: CallbackQuery) -> None:
    await callback.answer("⚠️ Bu kanal uchun havola yo'q. Admin bilan bog'laning.", show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Kino kodi — matn orqali (4-5 xona, hech qanday FSM holati yo'q)
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(StateFilter(None), F.text.regexp(r"^[A-Za-z0-9]{4,5}$"))
async def handle_movie_code(message: Message, session: AsyncSession, bot: Bot) -> None:
    """
    StateFilter(None) — FSM holati bo'lganida (admin panel, pending) ishlamaydi.
    Subscription tekshiruvi middleware tomonidan allaqachon o'tkazilgan.
    """
    db_user = await get_user_by_id(session, message.from_user.id)
    lang = db_user.language if db_user else "uz"
    await _send_movie(bot, message.chat.id, session, message.text.strip(), lang)
