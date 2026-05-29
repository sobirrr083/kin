"""
handlers/admin.py — To'liq admin boshqaruv paneli.

Imkoniyatlar:
  📊 Statistika       — Foydalanuvchilar, faollik, bloklangan, TOP-5
  👥 Foydalanuvchilar — Ro'yxat: ism, username, til, oxirgi kirish
  📢 Broadcast        — Barcha userlarga xabar yuborish
  🎬 Kinolar          — Qidirish / O'chirish
  📡 Kanallar         — Majburiy kanallarni qo'shish / o'chirish
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.queries import (
    add_required_chat,
    count_movies,
    delete_movie_by_code,
    get_all_user_ids,
    get_full_stats,
    get_movie_by_code,
    get_required_chats,
    get_top_active_users,
    mark_user_blocked,
    remove_required_chat,
)
from filters.admin import IsAdmin
from keyboards.inline import (
    kb_admin_back,
    kb_admin_main,
    kb_admin_manage_chats,
    kb_admin_manage_movies,
    kb_cancel,
)

logger = logging.getLogger(__name__)
router = Router(name="admin")
router.message.filter(IsAdmin(), F.chat.type == "private")
router.callback_query.filter(IsAdmin())


# ═══════════════════════════════════════════════════════════════════════════════
# FSM holatlari
# ═══════════════════════════════════════════════════════════════════════════════

class AdminStates(StatesGroup):
    waiting_broadcast = State()
    waiting_search_code = State()
    waiting_delete_code = State()
    waiting_add_chat = State()


# ═══════════════════════════════════════════════════════════════════════════════
# Yordamchi funksiyalar
# ═══════════════════════════════════════════════════════════════════════════════

_PANEL_TEXT = "🛠 <b>Admin Panel</b>\n\nKerakli bo'limni tanlang:"


async def _show_panel(target: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(_PANEL_TEXT, reply_markup=kb_admin_main(), parse_mode="HTML")
    else:
        await target.answer(_PANEL_TEXT, reply_markup=kb_admin_main(), parse_mode="HTML")


def _user_mention(user) -> str:
    name = user.full_name or "Nomaʼlum"
    if user.username:
        return f"<a href='tg://user?id={user.user_id}'>{name}</a> (@{user.username})"
    return f"<a href='tg://user?id={user.user_id}'>{name}</a>"


# ═══════════════════════════════════════════════════════════════════════════════
# /admin buyrug'i
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await _show_panel(message, state)


# ═══════════════════════════════════════════════════════════════════════════════
# 📊 Statistika
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:stats")
async def cb_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    stats = await get_full_stats(session)

    top_lines = ""
    for i, u in enumerate(stats["top_users"], 1):
        name = u.full_name or "Nomaʼlum"
        uname = f" @{u.username}" if u.username else ""
        top_lines += f"  {i}. {name}{uname} — {u.message_count} ta\n"

    text = (
        "📊 <b>Bot Statistikasi</b>\n\n"
        "👥 <b>Foydalanuvchilar:</b>\n"
        f"  • Jami: <b>{stats['total_users']:,}</b>\n"
        f"  • Bot bloklagan: <b>{stats['blocked_users']:,}</b>\n\n"
        "📅 <b>Faollik:</b>\n"
        f"  • Bugun: <b>{stats['daily_active']:,}</b>\n"
        f"  • Shu hafta: <b>{stats['weekly_active']:,}</b>\n"
        f"  • Shu oy: <b>{stats['monthly_active']:,}</b>\n\n"
        "🎬 <b>Kinolar:</b>\n"
        f"  • Jami: <b>{stats['total_movies']:,}</b>\n\n"
        f"🏆 <b>TOP-5 Faol:</b>\n{top_lines or '  Hali ma\'lumot yo\'q'}"
    )
    await callback.message.edit_text(text, reply_markup=kb_admin_back(), parse_mode="HTML")
    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════════════
# 👥 Foydalanuvchilar
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:users")
async def cb_users(callback: CallbackQuery, session: AsyncSession) -> None:
    top_users = await get_top_active_users(session, limit=10)

    lines = []
    for i, u in enumerate(top_users, 1):
        lang_flag = "🇺🇿" if u.language == "uz" else ("🇷🇺" if u.language == "ru" else "❓")
        last = u.last_active.strftime("%d.%m %H:%M") if u.last_active else "—"
        name = u.full_name or "Nomaʼlum"
        uname = f"@{u.username}" if u.username else f"<code>{u.user_id}</code>"
        lines.append(
            f"{i}. {lang_flag} <b>{name}</b> ({uname})\n"
            f"   💬 {u.message_count} xabar | 🕐 {last}"
        )

    text = (
        "👥 <b>Foydalanuvchilar (TOP-10 faol)</b>\n\n"
        + ("\n\n".join(lines) if lines else "Hali foydalanuvchi yo'q.")
    )
    await callback.message.edit_text(text, reply_markup=kb_admin_back(), parse_mode="HTML")
    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════════════
# 📢 Broadcast
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:broadcast")
async def cb_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.waiting_broadcast)
    await callback.message.edit_text(
        "📢 <b>Broadcast</b>\n\n"
        "Barcha userlarga yuboriladigan xabarni yuboring.\n"
        "Matn, rasm, video — hammasi qo'llab-quvvatlanadi.",
        reply_markup=kb_cancel(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_broadcast)
async def process_broadcast(message: Message, session: AsyncSession, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    user_ids = await get_all_user_ids(session)
    total = len(user_ids)
    success = failed = blocked = 0

    status = await message.answer(
        f"📡 <b>Broadcast boshlandi...</b>\n{total:,} ta userlarga yuborilmoqda.",
        parse_mode="HTML",
    )

    for idx, uid in enumerate(user_ids, 1):
        try:
            await message.copy_to(chat_id=uid)
            success += 1
        except TelegramForbiddenError:
            blocked += 1
            await mark_user_blocked(session, uid)
        except Exception as exc:
            failed += 1
            logger.warning("Broadcast xato uid=%s: %s", uid, exc)

        if idx % settings.BROADCAST_CHUNK_SIZE == 0:
            await asyncio.sleep(settings.BROADCAST_SLEEP_SECONDS)

    await status.edit_text(
        "✅ <b>Broadcast yakunlandi!</b>\n\n"
        f"📨 Yuborildi:    <b>{success:,}</b>\n"
        f"🚫 Bloklagan:   <b>{blocked:,}</b>\n"
        f"❌ Xato:        <b>{failed:,}</b>\n"
        f"👥 Jami:        <b>{total:,}</b>",
        reply_markup=kb_admin_back(),
        parse_mode="HTML",
    )
    logger.info("Broadcast: success=%s blocked=%s failed=%s total=%s", success, blocked, failed, total)


# ═══════════════════════════════════════════════════════════════════════════════
# 🎬 Kinolarni boshqarish
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:manage_movies")
async def cb_manage_movies(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🎬 <b>Kinolarni Boshqarish</b>\n\nAmalni tanlang:",
        reply_markup=kb_admin_manage_movies(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin:search_movie")
async def cb_search_movie(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.waiting_search_code)
    await callback.message.edit_text(
        "🔍 <b>Kino Qidirish</b>\n\nKino kodini yuboring:",
        reply_markup=kb_cancel(), parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_search_code)
async def process_search(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    code = message.text.strip()
    movie = await get_movie_by_code(session, code)
    if movie is None:
        text = f"❌ Kod <code>{code}</code> bo'yicha kino topilmadi."
    else:
        title = movie.title or "—"
        text = (
            f"🎬 <b>Kino topildi</b>\n\n"
            f"📌 <b>Kod:</b>   <code>{movie.code}</code>\n"
            f"🏷 <b>Nomi:</b>  {title}\n"
            f"📁 <b>Turi:</b>  {movie.file_type.capitalize()}\n"
            f"📅 <b>Qo'shilgan:</b> {movie.created_at.strftime('%Y-%m-%d %H:%M')}"
        )
    await message.answer(text, reply_markup=kb_admin_back(), parse_mode="HTML")


@router.callback_query(F.data == "admin:delete_movie")
async def cb_delete_movie(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.waiting_delete_code)
    await callback.message.edit_text(
        "🗑 <b>Kinoni O'chirish</b>\n\n"
        "O'chirmoqchi bo'lgan kino kodini yuboring:\n"
        "<i>⚠️ Bu amal qaytarib bo'lmaydi!</i>",
        reply_markup=kb_cancel(), parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_delete_code)
async def process_delete(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    code = message.text.strip()
    deleted = await delete_movie_by_code(session, code)
    if deleted:
        text = f"✅ Kod <code>{code}</code> bo'yicha kino o'chirildi."
        logger.info("Admin kino o'chirdi: code=%s", code)
    else:
        text = f"❌ Kod <code>{code}</code> bo'yicha kino topilmadi."
    await message.answer(text, reply_markup=kb_admin_back(), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════════════
# 📡 Majburiy kanallarni boshqarish
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:manage_chats")
async def cb_manage_chats(callback: CallbackQuery, session: AsyncSession) -> None:
    chats = await get_required_chats(session)
    count = len(chats)
    text = (
        f"📡 <b>Majburiy Kanallar / Guruhlar</b>\n\n"
        f"Hozir: <b>{count}</b> ta kanal/guruh qo'shilgan.\n\n"
        "Ro'yxatdan o'chirish uchun 🗑 tugmasini bosing."
        if chats else
        "📡 <b>Majburiy Kanallar / Guruhlar</b>\n\n"
        "Hozircha hech qanday kanal qo'shilmagan.\n"
        "➕ Qo'shish tugmasini bosing."
    )
    await callback.message.edit_text(
        text,
        reply_markup=kb_admin_manage_chats(chats),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin:add_chat")
async def cb_add_chat(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.waiting_add_chat)
    await callback.message.edit_text(
        "📡 <b>Kanal / Guruh Qo'shish</b>\n\n"
        "Bot a'zo bo'lgan kanal yoki guruhning <b>ID sini</b> yuboring.\n\n"
        "ID ni topish uchun:\n"
        "  • Kanalga <b>@username_bot</b> ni qo'shing\n"
        "  • Yoki kanaldan xabarni botga forward qiling\n\n"
        "<b>Misol:</b> <code>-1001234567890</code>",
        reply_markup=kb_cancel(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_add_chat)
async def process_add_chat(message: Message, session: AsyncSession, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    raw = message.text.strip()

    # chat_id yoki @username qabul qilish
    try:
        chat_id_input = int(raw) if raw.lstrip("-").isdigit() else raw
        chat = await bot.get_chat(chat_id_input)
    except Exception as exc:
        await message.answer(
            f"❌ <b>Kanal/guruh topilmadi.</b>\n\n"
            f"Bot kanalga admin sifatida qo'shilganligini tekshiring.\n"
            f"Xato: <code>{exc}</code>",
            reply_markup=kb_admin_back(),
            parse_mode="HTML",
        )
        return

    # Invite link olish (bot admin bo'lsa)
    invite_link = None
    if chat.invite_link:
        invite_link = chat.invite_link
    else:
        try:
            invite_link = await bot.export_chat_invite_link(chat.id)
        except Exception:
            pass  # Bot admin emas, invite link olmaydi

    chat_type = "channel" if chat.type == "channel" else "group"
    username = chat.username if hasattr(chat, "username") else None

    _, created = await add_required_chat(
        session,
        chat_id=chat.id,
        title=chat.title or "Nomaʼlum",
        username=username,
        invite_link=invite_link,
        chat_type=chat_type,
    )

    icon = "📢" if chat_type == "channel" else "👥"
    action = "qo'shildi" if created else "yangilandi"
    link_status = "✅ Havola bor" if invite_link else "⚠️ Havola yo'q (bot admin emas)"

    await message.answer(
        f"✅ <b>Kanal {action}!</b>\n\n"
        f"{icon} <b>{chat.title}</b>\n"
        f"🆔 <code>{chat.id}</code>\n"
        f"🔗 {link_status}",
        reply_markup=kb_admin_back(),
        parse_mode="HTML",
    )
    logger.info("Majburiy kanal %s: id=%s title=%s", action, chat.id, chat.title)


@router.callback_query(F.data.startswith("admin:del_chat:"))
async def cb_delete_chat(callback: CallbackQuery, session: AsyncSession) -> None:
    chat_id = int(callback.data.split(":")[-1])
    deleted = await remove_required_chat(session, chat_id)

    chats = await get_required_chats(session)
    text = (
        "✅ Kanal/guruh ro'yxatdan o'chirildi.\n\n"
        f"📡 <b>Majburiy Kanallar ({len(chats)} ta)</b>"
    ) if deleted else "❌ Kanal topilmadi."

    await callback.message.edit_text(
        text,
        reply_markup=kb_admin_manage_chats(chats),
        parse_mode="HTML",
    )
    await callback.answer("✅ O'chirildi" if deleted else "❌ Topilmadi")


@router.callback_query(F.data.startswith("admin:chat_info:"))
async def cb_chat_info(callback: CallbackQuery, session: AsyncSession) -> None:
    chat_id = int(callback.data.split(":")[-1])
    chats = await get_required_chats(session)
    chat = next((c for c in chats if c.chat_id == chat_id), None)
    if not chat:
        await callback.answer("Topilmadi", show_alert=True)
        return
    icon = "📢" if chat.chat_type == "channel" else "👥"
    uname = f"@{chat.username}" if chat.username else "—"
    link = chat.invite_link or "—"
    await callback.answer(
        f"{icon} {chat.title}\n🆔 {chat.chat_id}\n👤 {uname}\n🔗 {link[:50]}",
        show_alert=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Navigatsiya callbacklari
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:back")
async def cb_back(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_panel(callback, state)
    await callback.answer()


@router.callback_query(F.data == "admin:close")
async def cb_close(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.delete()
    await callback.answer("Panel yopildi.")


@router.callback_query(F.data == "admin:cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_panel(callback, state)
    await callback.answer("Bekor qilindi.")
