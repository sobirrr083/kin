"""
handlers/admin.py — To'liq admin boshqaruv paneli.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.queries import (
    get_next_code,
    set_next_code,
    add_required_chat,
    delete_movie_by_code,
    get_active_user_ids,
    get_full_stats,
    get_movie_by_code,
    get_required_chats,
    get_top_active_users,
    mark_user_blocked,
    remove_required_chat,
    update_chat_member_count,
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


def kb_monitoring_back():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 Yangilash", callback_data="admin:channel_monitoring"))
    builder.row(InlineKeyboardButton(text="◀️ Kanallar", callback_data="admin:manage_chats"))
    builder.row(InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="admin:back"))
    return builder.as_markup()


async def _show_panel(target: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(_PANEL_TEXT, reply_markup=kb_admin_main(), parse_mode="HTML")
        else:
            await target.answer(_PANEL_TEXT, reply_markup=kb_admin_main(), parse_mode="HTML")
    except TelegramBadRequest as exc:
        if "not modified" not in str(exc).lower():
            logger.warning("_show_panel: %s", exc)
    except Exception as exc:
        logger.error("_show_panel xato: %s", exc)


async def _safe_answer(callback: CallbackQuery, text: str = "") -> None:
    try:
        await callback.answer(text)
    except Exception as exc:
        logger.warning("callback.answer xato: %s", exc)


async def _safe_edit(callback: CallbackQuery, text: str, **kwargs) -> None:
    try:
        await callback.message.edit_text(text, **kwargs)
    except TelegramBadRequest as exc:
        if "not modified" not in str(exc).lower():
            try:
                await callback.message.answer(text, **kwargs)
            except Exception as exc2:
                logger.error("_safe_edit fallback xato: %s", exc2)
    except Exception as exc:
        logger.error("_safe_edit xato: %s", exc)


async def _fetch_member_count(bot: Bot, chat_id: int) -> int:
    try:
        return await bot.get_chat_member_count(chat_id)
    except TelegramForbiddenError:
        logger.warning("_fetch_member_count: bot kanal %s da admin emas", chat_id)
        return -1
    except Exception as exc:
        logger.warning("_fetch_member_count xato chat_id=%s: %s", chat_id, exc)
        return -1


# ═══════════════════════════════════════════════════════════════════════════════
# /admin
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    logger.info("Admin panel: user_id=%s | ADMIN_IDS=%s", message.from_user.id, settings.ADMIN_IDS)
    try:
        await _show_panel(message, state)
    except Exception as exc:
        logger.error("cmd_admin xato: %s", exc)
        await message.answer("❌ Admin panel ochishda xato yuz berdi.")


# ═══════════════════════════════════════════════════════════════════════════════
# 📊 Statistika
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:stats")
async def cb_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
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
            f"  • Faol: <b>{stats['active_users']:,}</b>\n"
            f"  • Bloklagan: <b>{stats['blocked_users']:,}</b>\n\n"
            "📅 <b>Faollik:</b>\n"
            f"  • Bugun: <b>{stats['daily_active']:,}</b>\n"
            f"  • Shu hafta: <b>{stats['weekly_active']:,}</b>\n"
            f"  • Shu oy: <b>{stats['monthly_active']:,}</b>\n\n"
            "🎬 <b>Kinolar:</b>\n"
            f"  • Jami: <b>{stats['total_movies']:,}</b>\n\n"
            f"🏆 <b>TOP-5 Faol:</b>\n{top_lines or '  Hali maʼlumot yoʼq'}"
        )
        await _safe_edit(callback, text, reply_markup=kb_admin_back(), parse_mode="HTML")
    except Exception as exc:
        logger.error("cb_stats xato: %s", exc)
        await _safe_edit(callback, "❌ Statistikani yuklashda xato.", reply_markup=kb_admin_back(), parse_mode="HTML")
    finally:
        await _safe_answer(callback)


# ═══════════════════════════════════════════════════════════════════════════════
# 👥 Foydalanuvchilar
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:users")
async def cb_users(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        top_users = await get_top_active_users(session, limit=10)
        lines = []
        for i, u in enumerate(top_users, 1):
            flag = "🇺🇿" if u.language == "uz" else ("🇷🇺" if u.language == "ru" else "❓")
            last = u.last_active.strftime("%d.%m %H:%M") if u.last_active else "—"
            name = u.full_name or "Nomaʼlum"
            uname = f"@{u.username}" if u.username else f"<code>{u.user_id}</code>"
            lines.append(f"{i}. {flag} <b>{name}</b> ({uname})\n   💬 {u.message_count} xabar | 🕐 {last}")
        text = "👥 <b>Foydalanuvchilar (TOP-10)</b>\n\n" + ("\n\n".join(lines) if lines else "Hali yo'q.")
        await _safe_edit(callback, text, reply_markup=kb_admin_back(), parse_mode="HTML")
    except Exception as exc:
        logger.error("cb_users xato: %s", exc)
        await _safe_edit(callback, "❌ Xato yuz berdi.", reply_markup=kb_admin_back(), parse_mode="HTML")
    finally:
        await _safe_answer(callback)


# ═══════════════════════════════════════════════════════════════════════════════
# 📢 Broadcast
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:broadcast")
async def cb_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.set_state(AdminStates.waiting_broadcast)
        await _safe_edit(
            callback,
            "📢 <b>Broadcast</b>\n\n"
            "Barcha foydalanuvchilarga yuboriladigan xabarni yuboring.\n"
            "Matn, rasm, video — hammasi qo'llab-quvvatlanadi.\n\n"
            "<i>Bekor qilish uchun tugmani bosing.</i>",
            reply_markup=kb_cancel(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("cb_broadcast xato: %s", exc)
        await state.clear()
    finally:
        await _safe_answer(callback)


@router.message(AdminStates.waiting_broadcast)
async def process_broadcast(message: Message, session: AsyncSession, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    if not message.text and not message.photo and not message.video and not message.document:
        await message.answer("❌ Matn, rasm yoki video yuboring.", reply_markup=kb_admin_back())
        return
    try:
        user_ids = await get_active_user_ids(session)
        total = len(user_ids)
        if total == 0:
            await message.answer("⚠️ Faol foydalanuvchi topilmadi.", reply_markup=kb_admin_back())
            return

        status = await message.answer(
            f"📡 <b>Broadcast boshlandi...</b>\n👥 {total:,} ta foydalanuvchiga yuborilmoqda.",
            parse_mode="HTML",
        )
        success = failed = blocked = 0

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
                if idx % 100 == 0:
                    try:
                        await status.edit_text(
                            f"📡 <b>Davom etmoqda...</b>\n✅ {success:,} / {total:,}",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

        await status.edit_text(
            "✅ <b>Broadcast yakunlandi!</b>\n\n"
            f"📨 Yuborildi:  <b>{success:,}</b>\n"
            f"🚫 Bloklagan: <b>{blocked:,}</b>\n"
            f"❌ Xato:      <b>{failed:,}</b>\n"
            f"👥 Jami:      <b>{total:,}</b>",
            reply_markup=kb_admin_back(),
            parse_mode="HTML",
        )
        logger.info("Broadcast: success=%s blocked=%s failed=%s total=%s", success, blocked, failed, total)
    except Exception as exc:
        logger.error("process_broadcast xato: %s", exc)
        await message.answer("❌ Broadcast da xato yuz berdi.", reply_markup=kb_admin_back())


# ═══════════════════════════════════════════════════════════════════════════════
# 🎬 Kinolarni boshqarish
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:manage_movies")
async def cb_manage_movies(callback: CallbackQuery) -> None:
    try:
        await _safe_edit(callback, "🎬 <b>Kinolarni Boshqarish</b>\n\nAmalni tanlang:", reply_markup=kb_admin_manage_movies(), parse_mode="HTML")
    except Exception as exc:
        logger.error("cb_manage_movies xato: %s", exc)
    finally:
        await _safe_answer(callback)


@router.callback_query(F.data == "admin:search_movie")
async def cb_search_movie(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.set_state(AdminStates.waiting_search_code)
        await _safe_edit(callback, "🔍 <b>Kino Qidirish</b>\n\nKino kodini yuboring:", reply_markup=kb_cancel(), parse_mode="HTML")
    except Exception as exc:
        logger.error("cb_search_movie xato: %s", exc)
        await state.clear()
    finally:
        await _safe_answer(callback)


@router.message(AdminStates.waiting_search_code)
async def process_search(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    if not message.text or not message.text.strip():
        await message.answer("❌ Kino kodi matn bo'lishi kerak.", reply_markup=kb_admin_back())
        return
    try:
        code = message.text.strip()
        movie = await get_movie_by_code(session, code)
        if movie is None:
            text = f"❌ Kod <code>{code}</code> bo'yicha kino topilmadi."
        else:
            created = movie.created_at.strftime("%Y-%m-%d %H:%M") if movie.created_at else "—"
            text = (
                f"🎬 <b>Kino topildi</b>\n\n"
                f"📌 <b>Kod:</b>  <code>{movie.code}</code>\n"
                f"🏷 <b>Nomi:</b> {movie.title or '—'}\n"
                f"📁 <b>Turi:</b> {movie.file_type.capitalize()}\n"
                f"📅 <b>Qo'shilgan:</b> {created}"
            )
        await message.answer(text, reply_markup=kb_admin_back(), parse_mode="HTML")
    except Exception as exc:
        logger.error("process_search xato: %s", exc)
        await message.answer("❌ Qidirishda xato yuz berdi.", reply_markup=kb_admin_back())


@router.callback_query(F.data == "admin:delete_movie")
async def cb_delete_movie(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.set_state(AdminStates.waiting_delete_code)
        await _safe_edit(
            callback,
            "🗑 <b>Kinoni O'chirish</b>\n\nKino kodini yuboring:\n<i>⚠️ Bu amal qaytarib bo'lmaydi!</i>",
            reply_markup=kb_cancel(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("cb_delete_movie xato: %s", exc)
        await state.clear()
    finally:
        await _safe_answer(callback)


@router.message(AdminStates.waiting_delete_code)
async def process_delete(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    if not message.text or not message.text.strip():
        await message.answer("❌ Kino kodi matn bo'lishi kerak.", reply_markup=kb_admin_back())
        return
    try:
        code = message.text.strip()
        deleted = await delete_movie_by_code(session, code)
        text = f"✅ Kod <code>{code}</code> o'chirildi." if deleted else f"❌ Kod <code>{code}</code> topilmadi."
        if deleted:
            logger.info("Kino o'chirildi: code=%s admin=%s", code, message.from_user.id)
        await message.answer(text, reply_markup=kb_admin_back(), parse_mode="HTML")
    except Exception as exc:
        logger.error("process_delete xato: %s", exc)
        await message.answer("❌ O'chirishda xato yuz berdi.", reply_markup=kb_admin_back())


# ═══════════════════════════════════════════════════════════════════════════════
# 📡 Majburiy kanallar
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:manage_chats")
async def cb_manage_chats(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        chats = await get_required_chats(session)
        if chats:
            text = (
                f"📡 <b>Majburiy Kanallar ({len(chats)} ta)</b>\n\n"
                "📊 A'zolar soni uchun <b>Monitoring</b> tugmasini bosing.\n"
                "O'chirish uchun 🗑 tugmasini bosing."
            )
        else:
            text = "📡 <b>Majburiy Kanallar</b>\n\nHech qanday kanal qo'shilmagan.\n➕ Qo'shish tugmasini bosing."
        await _safe_edit(callback, text, reply_markup=kb_admin_manage_chats(chats), parse_mode="HTML")
    except Exception as exc:
        logger.error("cb_manage_chats xato: %s", exc)
        await _safe_edit(callback, "❌ Kanallar ro'yxatini yuklashda xato.", reply_markup=kb_admin_back(), parse_mode="HTML")
    finally:
        await _safe_answer(callback)


# ═══════════════════════════════════════════════════════════════════════════════
# 📊 Kanal monitoring
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:channel_monitoring")
async def cb_channel_monitoring(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    try:
        await _safe_answer(callback, "⏳ Tekshirilmoqda...")
        chats = await get_required_chats(session)
        if not chats:
            await _safe_edit(callback, "📡 <b>Kanal Monitoring</b>\n\nHech qanday kanal qo'shilmagan.", reply_markup=kb_admin_back(), parse_mode="HTML")
            return

        lines = []
        for chat in chats:
            icon = "📢" if chat.chat_type == "channel" else "👥"
            count = await _fetch_member_count(bot, chat.chat_id)
            if count >= 0:
                await update_chat_member_count(session, chat.chat_id, count)
                count_str = f"<b>{count:,}</b> ta a'zo"
            else:
                count_str = "⚠️ <i>Bot admin emas yoki xato</i>"
            uname = f" (@{chat.username})" if chat.username else ""
            added = chat.added_at.strftime("%d.%m.%Y") if chat.added_at else "—"
            lines.append(
                f"{icon} <b>{chat.title}</b>{uname}\n"
                f"   👥 {count_str}\n"
                f"   🆔 <code>{chat.chat_id}</code>  |  📅 {added}"
            )

        text = "📊 <b>Kanal Monitoring</b>\n\n" + "\n\n".join(lines) + "\n\n<i>🔄 Hozir yangilandi</i>"
        await _safe_edit(callback, text, reply_markup=kb_monitoring_back(), parse_mode="HTML")
        logger.info("Monitoring: %d kanal tekshirildi, admin=%s", len(chats), callback.from_user.id)
    except Exception as exc:
        logger.error("cb_channel_monitoring xato: %s", exc)
        await _safe_edit(callback, "❌ Monitoring yuklanishda xato.", reply_markup=kb_admin_back(), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════════════
# ➕ Kanal qo'shish
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:add_chat")
async def cb_add_chat(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.set_state(AdminStates.waiting_add_chat)
        await _safe_edit(
            callback,
            "📡 <b>Kanal / Guruh Qo'shish</b>\n\n"
            "Quyidagi usullardan birini ishlating:\n\n"
            "1️⃣ <b>ID orqali:</b> <code>-1001234567890</code>\n\n"
            "2️⃣ <b>Username orqali:</b> <code>@mening_kanalim</code>\n\n"
            "3️⃣ <b>Forward orqali:</b> Kanal/guruhdan istalgan xabarni\n"
            "   shu yerga forward qiling\n\n"
            "<i>⚠️ Bot kanalga admin sifatida qo'shilgan bo'lishi shart!</i>",
            reply_markup=kb_cancel(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("cb_add_chat xato: %s", exc)
        await state.clear()
    finally:
        await _safe_answer(callback)


@router.message(AdminStates.waiting_add_chat)
async def process_add_chat(message: Message, session: AsyncSession, state: FSMContext, bot: Bot) -> None:
    await state.clear()

    chat_id_input = None
    source = ""

    # 1) forward_from_chat
    if message.forward_from_chat:
        chat_id_input = message.forward_from_chat.id
        source = f"forward ({message.forward_from_chat.title})"

    # 2) forward_origin (aiogram v3.7+)
    elif message.forward_origin and hasattr(message.forward_origin, "chat"):
        if message.forward_origin.chat:
            chat_id_input = message.forward_origin.chat.id
            source = f"forward_origin ({message.forward_origin.chat.title})"

    # 3) Matn
    if chat_id_input is None:
        if not message.text or not message.text.strip():
            await message.answer("❌ Matn yuboring yoki kanal/guruhdan xabar forward qiling.", reply_markup=kb_admin_back())
            return
        raw = message.text.strip()
        source = f"matn ({raw!r})"
        chat_id_input = int(raw) if raw.lstrip("-").isdigit() else (raw if raw.startswith("@") else f"@{raw}")

    try:
        chat = await bot.get_chat(chat_id_input)
    except Exception as exc:
        await message.answer(
            f"❌ <b>Kanal/guruh topilmadi.</b>\n\n"
            f"  • Bot kanalga <b>admin</b> sifatida qo'shilganmi?\n"
            f"  • ID to'g'rimi? <code>{chat_id_input}</code>\n"
            f"  • Yoki kanal/guruhdan xabar <b>forward</b> qiling\n\n"
            f"Xato: <code>{exc}</code>",
            reply_markup=kb_admin_back(), parse_mode="HTML",
        )
        return

    invite_link = getattr(chat, "invite_link", None)
    if not invite_link:
        try:
            invite_link = await bot.export_chat_invite_link(chat.id)
        except Exception:
            pass

    member_count = await _fetch_member_count(bot, chat.id)
    chat_type = "channel" if chat.type == "channel" else "group"
    username = getattr(chat, "username", None)

    try:
        _, created = await add_required_chat(
            session,
            chat_id=chat.id,
            title=chat.title or "Nomaʼlum",
            username=username,
            invite_link=invite_link,
            chat_type=chat_type,
        )
        if member_count >= 0:
            await update_chat_member_count(session, chat.id, member_count)

        icon = "📢" if chat_type == "channel" else "👥"
        action = "qo'shildi ✅" if created else "yangilandi 🔄"
        members_str = f"<b>{member_count:,}</b> ta" if member_count >= 0 else "aniqlanmadi"

        await message.answer(
            f"{icon} <b>Kanal {action}</b>\n\n"
            f"📛 <b>Nomi:</b> {chat.title}\n"
            f"🆔 <b>ID:</b> <code>{chat.id}</code>\n"
            f"👤 <b>Username:</b> {'@' + username if username else '—'}\n"
            f"👥 <b>A'zolar:</b> {members_str}\n"
            f"🔗 <b>Havola:</b> {'✅ Bor' if invite_link else '⚠️ Yoq'}\n"
            f"📥 <b>Manba:</b> {source}",
            reply_markup=kb_admin_back(), parse_mode="HTML",
        )
        logger.info("Kanal %s: id=%s title=%s members=%s admin=%s", "qo'shildi" if created else "yangilandi", chat.id, chat.title, member_count, message.from_user.id)
    except Exception as exc:
        logger.error("process_add_chat DB xato: %s", exc)
        await message.answer("❌ Kanalni saqlashda xato yuz berdi.", reply_markup=kb_admin_back())


@router.callback_query(F.data.startswith("admin:del_chat:"))
async def cb_delete_chat(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        chat_id = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await _safe_answer(callback, "❌ Xato")
        return
    try:
        deleted = await remove_required_chat(session, chat_id)
        chats = await get_required_chats(session)
        text = (
            f"✅ O'chirildi.\n\n📡 <b>Majburiy Kanallar ({len(chats)} ta)</b>"
            if deleted else "❌ Kanal topilmadi yoki allaqachon o'chirilgan."
        )
        await _safe_answer(callback, "✅ O'chirildi" if deleted else "❌ Topilmadi")
        await _safe_edit(callback, text, reply_markup=kb_admin_manage_chats(chats), parse_mode="HTML")
        if deleted:
            logger.info("Kanal o'chirildi: chat_id=%s admin=%s", chat_id, callback.from_user.id)
    except Exception as exc:
        logger.error("cb_delete_chat xato: %s", exc)
        await _safe_answer(callback, "❌ Xato yuz berdi")


@router.callback_query(F.data.startswith("admin:chat_info:"))
async def cb_chat_info(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        chat_id = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await _safe_answer(callback, "❌ Xato")
        return
    try:
        chats = await get_required_chats(session)
        chat = next((c for c in chats if c.chat_id == chat_id), None)
        if not chat:
            await _safe_answer(callback, "Topilmadi")
            return
        icon = "📢" if chat.chat_type == "channel" else "👥"
        members = f"{chat.member_count:,} ta" if chat.member_count >= 0 else "—"
        updated = chat.member_count_updated_at.strftime("%d.%m %H:%M") if chat.member_count_updated_at else "—"
        await callback.answer(
            f"{icon} {chat.title}\n"
            f"🆔 {chat.chat_id}\n"
            f"👤 {'@' + chat.username if chat.username else '—'}\n"
            f"👥 A'zolar: {members}\n"
            f"🕐 Yangilangan: {updated}",
            show_alert=True,
        )
    except Exception as exc:
        logger.error("cb_chat_info xato: %s", exc)
        await _safe_answer(callback, "❌ Xato yuz berdi")


# ═══════════════════════════════════════════════════════════════════════════════
# Navigatsiya
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:back")
async def cb_back(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_panel(callback, state)
    await _safe_answer(callback)


@router.callback_query(F.data == "admin:close")
async def cb_close(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await _safe_answer(callback, "Panel yopildi.")


@router.callback_query(F.data == "admin:cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_panel(callback, state)
    await _safe_answer(callback, "Bekor qilindi.")


# ═══════════════════════════════════════════════════════════════════════════════
# 📝 Kino extra caption (qo'shimcha matn) boshqaruvi
# ═══════════════════════════════════════════════════════════════════════════════
# Bu qismni handlers/admin.py ga qo'shamiz — AdminStates ga yangi holatlar kerak

from database.queries import set_movie_extra_caption  # noqa: E402 (already imported above via *)


class _ExtraStates(StatesGroup):
    waiting_extra_code = State()
    waiting_extra_text = State()
    waiting_clear_code = State()


@router.callback_query(F.data == "admin:manage_extra")
async def cb_manage_extra(callback: CallbackQuery) -> None:
    try:
        await _safe_edit(
            callback,
            "📝 <b>Kino Qo'shimcha Matn</b>\n\n"
            "Har bir kino kodiga qo'shimcha caption qo'shish mumkin.\n"
            "Masalan: reklama matni, kanal havolasi va h.k.\n\n"
            "Qo'shimcha matn kinoni yuborishda <b>caption oxiriga</b> qo'shiladi.",
            reply_markup=kb_admin_extra_caption(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("cb_manage_extra xato: %s", exc)
    finally:
        await _safe_answer(callback)


@router.callback_query(F.data == "admin:set_extra")
async def cb_set_extra(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.set_state(_ExtraStates.waiting_extra_code)
        await _safe_edit(
            callback,
            "📝 <b>Qo'shimcha Matn O'rnatish</b>\n\n"
            "1-qadam: Kino kodini yuboring:\n"
            "<i>Misol: <code>1111</code></i>",
            reply_markup=kb_cancel(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("cb_set_extra xato: %s", exc)
        await state.clear()
    finally:
        await _safe_answer(callback)


@router.message(_ExtraStates.waiting_extra_code)
async def process_extra_code(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not message.text or not message.text.strip():
        await message.answer("❌ Kino kodini matn sifatida yuboring.", reply_markup=kb_admin_back())
        await state.clear()
        return
    code = message.text.strip()
    movie = await get_movie_by_code(session, code)
    if movie is None:
        await message.answer(
            f"❌ Kod <code>{code}</code> bo'yicha kino topilmadi.",
            reply_markup=kb_admin_back(),
            parse_mode="HTML",
        )
        await state.clear()
        return
    # Kodni saqlab, matnni so'raymiz
    await state.set_state(_ExtraStates.waiting_extra_text)
    await state.update_data(extra_code=code)
    current = f"\n\nHozirgi qo'shimcha matn:\n<code>{movie.extra_caption}</code>" if movie.extra_caption else ""
    await message.answer(
        f"✅ Kod topildi: <b>{movie.title or code}</b>{current}\n\n"
        "2-qadam: Yangi qo'shimcha matnni yuboring.\n"
        "<i>Matn, emoji, havolalar — hammasi bo'ladi.</i>",
        reply_markup=kb_cancel(),
        parse_mode="HTML",
    )


@router.message(_ExtraStates.waiting_extra_text)
async def process_extra_text(message: Message, session: AsyncSession, state: FSMContext) -> None:
    state_data = await state.get_data()
    code = state_data.get("extra_code", "")
    await state.clear()

    if not message.text or not message.text.strip():
        await message.answer("❌ Matn bo'sh bo'lmasligi kerak.", reply_markup=kb_admin_back())
        return
    extra = message.text.strip()
    updated = await set_movie_extra_caption(session, code, extra)
    if updated:
        await message.answer(
            f"✅ <b>Qo'shimcha matn saqlandi!</b>\n\n"
            f"📌 Kod: <code>{code}</code>\n"
            f"📝 Matn:\n{extra}",
            reply_markup=kb_admin_back(),
            parse_mode="HTML",
        )
        logger.info("Extra caption set: code=%s admin=%s", code, message.from_user.id)
    else:
        await message.answer("❌ Saqlashda xato yuz berdi.", reply_markup=kb_admin_back())


@router.callback_query(F.data == "admin:clear_extra")
async def cb_clear_extra(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.set_state(_ExtraStates.waiting_clear_code)
        await _safe_edit(
            callback,
            "🗑 <b>Qo'shimcha Matnni O'chirish</b>\n\n"
            "Qo'shimcha matni o'chiriladigan kino kodini yuboring:",
            reply_markup=kb_cancel(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("cb_clear_extra xato: %s", exc)
        await state.clear()
    finally:
        await _safe_answer(callback)


@router.message(_ExtraStates.waiting_clear_code)
async def process_clear_extra(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    if not message.text or not message.text.strip():
        await message.answer("❌ Kino kodini yuboring.", reply_markup=kb_admin_back())
        return
    code = message.text.strip()
    updated = await set_movie_extra_caption(session, code, None)
    if updated:
        await message.answer(
            f"✅ Kod <code>{code}</code> ning qo'shimcha matni o'chirildi.",
            reply_markup=kb_admin_back(), parse_mode="HTML",
        )
    else:
        await message.answer(
            f"❌ Kod <code>{code}</code> topilmadi.",
            reply_markup=kb_admin_back(), parse_mode="HTML",
        )


@router.callback_query(F.data == "admin:preview_extra")
async def cb_preview_extra(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.set_state(_ExtraStates.waiting_extra_code)
        await _safe_edit(
            callback,
            "👁 <b>Kinoni Ko'rish</b>\n\nKino kodini yuboring:",
            reply_markup=kb_cancel(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("cb_preview_extra xato: %s", exc)
        await state.clear()
    finally:
        await _safe_answer(callback)


# ═══════════════════════════════════════════════════════════════════════════════
# 🔢 Kino kodi sanagichi boshqaruvi
# ═══════════════════════════════════════════════════════════════════════════════

class _CodeCounterStates(StatesGroup):
    waiting_new_code = State()


@router.callback_query(F.data == "admin:code_counter")
async def cb_code_counter(callback: CallbackQuery, session: AsyncSession) -> None:
    """Hozirgi kod sanagichini ko'rsatadi."""
    try:
        current = await get_next_code(session)
        await _safe_edit(
            callback,
            "🔢 <b>Kino Kodi Sanagichi</b>\n\n"
            f"📌 Keyingi yangi kinoga beriladigan kod: <b><code>{current}</code></b>\n\n"
            "ℹ️ Guruhga video yuborilganda caption da kod yozilmasa,\n"
            "shu raqam avtomatik beriladi va sanagich +1 bo'ladi.\n\n"
            "Sanagichni o'zgartirmoqchi bo'lsangiz, \n"
            "<b>✏️ O'zgartirish</b> tugmasini bosing.",
            reply_markup=kb_code_counter(current),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("cb_code_counter xato: %s", exc)
        await _safe_edit(callback, "❌ Xato yuz berdi.", reply_markup=kb_admin_back(), parse_mode="HTML")
    finally:
        await _safe_answer(callback)


@router.callback_query(F.data == "admin:edit_code_counter")
async def cb_edit_code_counter(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.set_state(_CodeCounterStates.waiting_new_code)
        await _safe_edit(
            callback,
            "✏️ <b>Sanagichni O'zgartirish</b>\n\n"
            "Yangi boshlang'ich kodni yuboring.\n\n"
            "📌 <b>Misol:</b> <code>2000</code>\n"
            "⚠️ Faqat musbat butun son kiriting!\n\n"
            "<i>Keyingi kino shu raqamdan boshlanadi.</i>",
            reply_markup=kb_cancel(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("cb_edit_code_counter xato: %s", exc)
        await state.clear()
    finally:
        await _safe_answer(callback)


@router.message(_CodeCounterStates.waiting_new_code)
async def process_new_code(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()

    if not message.text or not message.text.strip().isdigit():
        await message.answer(
            "❌ Noto'g'ri format. Faqat musbat butun son kiriting.\n"
            "<i>Misol: <code>2000</code></i>",
            reply_markup=kb_admin_back(),
            parse_mode="HTML",
        )
        return

    new_val = int(message.text.strip())
    if new_val < 1:
        await message.answer(
            "❌ Raqam 1 dan katta bo'lishi kerak.",
            reply_markup=kb_admin_back(),
        )
        return

    ok = await set_next_code(session, new_val)
    if ok:
        await message.answer(
            f"✅ <b>Sanagich yangilandi!</b>\n\n"
            f"Keyingi kino kodi: <b><code>{new_val}</code></b>",
            reply_markup=kb_admin_back(),
            parse_mode="HTML",
        )
        logger.info("Kod sanagichi yangilandi: %s | admin=%s", new_val, message.from_user.id)
    else:
        await message.answer("❌ Saqlashda xato yuz berdi.", reply_markup=kb_admin_back())


def kb_code_counter(current: int) -> object:
    """Kod sanagichi boshqaruv tugmalari."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ O'zgartirish", callback_data="admin:edit_code_counter"))
    builder.row(InlineKeyboardButton(text="🔄 Yangilash", callback_data="admin:code_counter"))
    builder.row(InlineKeyboardButton(text="◀️ Asosiy menyu", callback_data="admin:back"))
    return builder.as_markup()
