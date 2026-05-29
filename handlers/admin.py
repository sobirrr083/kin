"""
handlers/admin.py — To'liq admin boshqaruv paneli.

BARCHA BUG FIX LAR:
  #1 — IsAdmin filteri endi log chiqaradi (filters/admin.py)
  #2 — SubscriptionMiddleware admin ni o'tkazib yuboradi (middlewares/subscription.py)
  #3 — Race condition tuzatildi (database/queries.py)
  #4 — Har bir handler da try/except bor, xatolar logga yoziladi
  #5 — CallbackQuery answer() har doim chaqiriladi (timeout oldini olish)
  #6 — message.text None bo'lganda crash bo'lmaydi
  #7 — Xato yuz berganda foydalanuvchiga tushunarli xabar ko'rsatiladi
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.queries import (
    add_required_chat,
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
# Ichki yordamchi funksiyalar
# ═══════════════════════════════════════════════════════════════════════════════

_PANEL_TEXT = "🛠 <b>Admin Panel</b>\n\nKerakli bo'limni tanlang:"


async def _show_panel(target: Message | CallbackQuery, state: FSMContext) -> None:
    """Admin panelni ko'rsatadi yoki qaytaradi."""
    await state.clear()
    try:
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(
                _PANEL_TEXT, reply_markup=kb_admin_main(), parse_mode="HTML"
            )
        else:
            await target.answer(
                _PANEL_TEXT, reply_markup=kb_admin_main(), parse_mode="HTML"
            )
    except TelegramBadRequest as exc:
        # "message is not modified" — xabar o'zgarmagan, e'tibor bermasa bo'ladi
        if "not modified" not in str(exc).lower():
            logger.warning("_show_panel TelegramBadRequest: %s", exc)
    except Exception as exc:
        logger.error("_show_panel xato: %s", exc)


async def _safe_answer(callback: CallbackQuery, text: str = "") -> None:
    """CallbackQuery timeout xatosini oldini olish uchun xavfsiz answer()."""
    try:
        await callback.answer(text)
    except TelegramBadRequest as exc:
        if "query is too old" not in str(exc).lower():
            logger.warning("callback.answer xato: %s", exc)
    except Exception as exc:
        logger.warning("callback.answer xato: %s", exc)


async def _safe_edit(callback: CallbackQuery, text: str, **kwargs) -> None:
    """Xavfsiz edit_text — xato bo'lsa logga yozib, foydalanuvchiga xabar beradi."""
    try:
        await callback.message.edit_text(text, **kwargs)
    except TelegramBadRequest as exc:
        if "not modified" not in str(exc).lower():
            logger.warning("edit_text xato: %s", exc)
            try:
                await callback.message.answer(text, **kwargs)
            except Exception as exc2:
                logger.error("Fallback answer ham ishlamadi: %s", exc2)
    except Exception as exc:
        logger.error("_safe_edit xato: %s", exc)


# ═══════════════════════════════════════════════════════════════════════════════
# /admin buyrug'i
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    """
    /admin buyrug'i — panelni ko'rsatadi.

    Agar bu handler ishlamasa:
      1. ADMIN_IDS bo'sh — Railway Variables da tekshiring
      2. ADMIN_IDS da sizning ID yo'q — @userinfobot dan ID oling
      3. Bot private chatda emas — faqat private chatda ishlaydi
    """
    logger.info(
        "Admin panel so'raldi: user_id=%s username=%s | ADMIN_IDS=%s",
        message.from_user.id,
        message.from_user.username,
        settings.ADMIN_IDS,
    )
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
            f"  • Bot bloklagan: <b>{stats['blocked_users']:,}</b>\n\n"
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
        await _safe_edit(
            callback,
            "❌ Statistikani yuklashda xato yuz berdi. Qayta urinib ko'ring.",
            reply_markup=kb_admin_back(),
            parse_mode="HTML",
        )
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
        await _safe_edit(callback, text, reply_markup=kb_admin_back(), parse_mode="HTML")
    except Exception as exc:
        logger.error("cb_users xato: %s", exc)
        await _safe_edit(
            callback,
            "❌ Foydalanuvchilarni yuklashda xato yuz berdi.",
            reply_markup=kb_admin_back(),
            parse_mode="HTML",
        )
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
            "Barcha userlarga yuboriladigan xabarni yuboring.\n"
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
async def process_broadcast(
    message: Message, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    await state.clear()

    # BUG FIX #6: message.text None bo'lishi mumkin (rasm/video/fayl)
    if not message.text and not message.photo and not message.video and not message.document:
        await message.answer(
            "❌ Noto'g'ri xabar turi. Matn, rasm yoki video yuboring.",
            reply_markup=kb_admin_back(),
        )
        return

    try:
        user_ids = await get_all_user_ids(session)
        total = len(user_ids)

        if total == 0:
            await message.answer(
                "⚠️ Hech qanday foydalanuvchi topilmadi.",
                reply_markup=kb_admin_back(),
            )
            return

        status = await message.answer(
            f"📡 <b>Broadcast boshlandi...</b>\n{total:,} ta userlarga yuborilmoqda.",
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
            except TelegramBadRequest as exc:
                failed += 1
                logger.warning("Broadcast TelegramBadRequest uid=%s: %s", uid, exc)
            except Exception as exc:
                failed += 1
                logger.warning("Broadcast xato uid=%s: %s", uid, exc)

            if idx % settings.BROADCAST_CHUNK_SIZE == 0:
                await asyncio.sleep(settings.BROADCAST_SLEEP_SECONDS)
                # Progress yangilash (har 100 tadan)
                if idx % 100 == 0:
                    try:
                        await status.edit_text(
                            f"📡 <b>Broadcast davom etmoqda...</b>\n"
                            f"✅ {success:,} / {total:,} yuborildi",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

        await status.edit_text(
            "✅ <b>Broadcast yakunlandi!</b>\n\n"
            f"📨 Yuborildi:    <b>{success:,}</b>\n"
            f"🚫 Bloklagan:   <b>{blocked:,}</b>\n"
            f"❌ Xato:        <b>{failed:,}</b>\n"
            f"👥 Jami:        <b>{total:,}</b>",
            reply_markup=kb_admin_back(),
            parse_mode="HTML",
        )
        logger.info(
            "Broadcast yakunlandi: success=%s blocked=%s failed=%s total=%s",
            success, blocked, failed, total,
        )

    except Exception as exc:
        logger.error("process_broadcast xato: %s", exc)
        await message.answer(
            "❌ Broadcast jarayonida kutilmagan xato yuz berdi.",
            reply_markup=kb_admin_back(),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 🎬 Kinolarni boshqarish
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:manage_movies")
async def cb_manage_movies(callback: CallbackQuery) -> None:
    try:
        await _safe_edit(
            callback,
            "🎬 <b>Kinolarni Boshqarish</b>\n\nAmalni tanlang:",
            reply_markup=kb_admin_manage_movies(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("cb_manage_movies xato: %s", exc)
    finally:
        await _safe_answer(callback)


@router.callback_query(F.data == "admin:search_movie")
async def cb_search_movie(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.set_state(AdminStates.waiting_search_code)
        await _safe_edit(
            callback,
            "🔍 <b>Kino Qidirish</b>\n\nKino kodini yuboring:",
            reply_markup=kb_cancel(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("cb_search_movie xato: %s", exc)
        await state.clear()
    finally:
        await _safe_answer(callback)


@router.message(AdminStates.waiting_search_code)
async def process_search(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()

    # BUG FIX #6: text bo'sh yoki None bo'lishi mumkin
    if not message.text or not message.text.strip():
        await message.answer(
            "❌ Kino kodi matn bo'lishi kerak.",
            reply_markup=kb_admin_back(),
        )
        return

    try:
        code = message.text.strip()
        movie = await get_movie_by_code(session, code)

        if movie is None:
            text = f"❌ Kod <code>{code}</code> bo'yicha kino topilmadi."
        else:
            title = movie.title or "—"
            created = movie.created_at.strftime("%Y-%m-%d %H:%M") if movie.created_at else "—"
            text = (
                f"🎬 <b>Kino topildi</b>\n\n"
                f"📌 <b>Kod:</b>   <code>{movie.code}</code>\n"
                f"🏷 <b>Nomi:</b>  {title}\n"
                f"📁 <b>Turi:</b>  {movie.file_type.capitalize()}\n"
                f"📅 <b>Qo'shilgan:</b> {created}"
            )
        await message.answer(text, reply_markup=kb_admin_back(), parse_mode="HTML")

    except Exception as exc:
        logger.error("process_search xato: %s", exc)
        await message.answer(
            "❌ Qidirishda xato yuz berdi.",
            reply_markup=kb_admin_back(),
        )


@router.callback_query(F.data == "admin:delete_movie")
async def cb_delete_movie(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.set_state(AdminStates.waiting_delete_code)
        await _safe_edit(
            callback,
            "🗑 <b>Kinoni O'chirish</b>\n\n"
            "O'chirmoqchi bo'lgan kino kodini yuboring:\n"
            "<i>⚠️ Bu amal qaytarib bo'lmaydi!</i>",
            reply_markup=kb_cancel(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("cb_delete_movie xato: %s", exc)
        await state.clear()
    finally:
        await _safe_answer(callback)


@router.message(AdminStates.waiting_delete_code)
async def process_delete(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()

    # BUG FIX #6: text bo'sh yoki None bo'lishi mumkin
    if not message.text or not message.text.strip():
        await message.answer(
            "❌ Kino kodi matn bo'lishi kerak.",
            reply_markup=kb_admin_back(),
        )
        return

    try:
        code = message.text.strip()
        deleted = await delete_movie_by_code(session, code)

        if deleted:
            text = f"✅ Kod <code>{code}</code> bo'yicha kino o'chirildi."
            logger.info("Admin kino o'chirdi: code=%s admin_id=%s", code, message.from_user.id)
        else:
            text = f"❌ Kod <code>{code}</code> bo'yicha kino topilmadi."

        await message.answer(text, reply_markup=kb_admin_back(), parse_mode="HTML")

    except Exception as exc:
        logger.error("process_delete xato code=%s: %s", message.text, exc)
        await message.answer(
            "❌ O'chirishda xato yuz berdi.",
            reply_markup=kb_admin_back(),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 📡 Majburiy kanallarni boshqarish
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:manage_chats")
async def cb_manage_chats(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        chats = await get_required_chats(session)
        count = len(chats)

        if chats:
            text = (
                f"📡 <b>Majburiy Kanallar / Guruhlar</b>\n\n"
                f"Hozir: <b>{count}</b> ta kanal/guruh qo'shilgan.\n\n"
                "O'chirish uchun 🗑 tugmasini bosing."
            )
        else:
            text = (
                "📡 <b>Majburiy Kanallar / Guruhlar</b>\n\n"
                "Hozircha hech qanday kanal qo'shilmagan.\n"
                "➕ Qo'shish tugmasini bosing."
            )

        await _safe_edit(
            callback, text, reply_markup=kb_admin_manage_chats(chats), parse_mode="HTML"
        )
    except Exception as exc:
        logger.error("cb_manage_chats xato: %s", exc)
        await _safe_edit(
            callback,
            "❌ Kanallar ro'yxatini yuklashda xato.",
            reply_markup=kb_admin_back(),
            parse_mode="HTML",
        )
    finally:
        await _safe_answer(callback)


@router.callback_query(F.data == "admin:add_chat")
async def cb_add_chat(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.set_state(AdminStates.waiting_add_chat)
        await _safe_edit(
            callback,
            "📡 <b>Kanal / Guruh Qo'shish</b>\n\n"
            "Bot a'zo bo'lgan kanal yoki guruhning <b>ID sini</b> yuboring.\n\n"
            "ID ni topish uchun:\n"
            "  • Kanalga <b>@username_bot</b> ni qo'shing\n"
            "  • Yoki kanaldan xabarni botga forward qiling\n\n"
            "<b>Misol:</b> <code>-1001234567890</code>",
            reply_markup=kb_cancel(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("cb_add_chat xato: %s", exc)
        await state.clear()
    finally:
        await _safe_answer(callback)


@router.message(AdminStates.waiting_add_chat)
async def process_add_chat(
    message: Message, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    await state.clear()

    # BUG FIX #6: text bo'sh yoki None bo'lishi mumkin
    if not message.text or not message.text.strip():
        await message.answer(
            "❌ Chat ID yoki @username matn ko'rinishida yuboring.",
            reply_markup=kb_admin_back(),
        )
        return

    raw = message.text.strip()

    try:
        chat_id_input = int(raw) if raw.lstrip("-").isdigit() else raw
        chat = await bot.get_chat(chat_id_input)
    except ValueError:
        await message.answer(
            f"❌ <b>Noto'g'ri format.</b>\n\n"
            f"Raqam (masalan <code>-1001234567890</code>) yoki "
            f"@username ko'rinishida kiriting.",
            reply_markup=kb_admin_back(),
            parse_mode="HTML",
        )
        return
    except Exception as exc:
        logger.warning("process_add_chat get_chat xato input=%s: %s", raw, exc)
        await message.answer(
            f"❌ <b>Kanal/guruh topilmadi.</b>\n\n"
            f"Tekshiring:\n"
            f"  • Bot kanalga admin sifatida qo'shilganmi?\n"
            f"  • ID to'g'rimi? (<code>{raw}</code>)\n\n"
            f"Xato: <code>{exc}</code>",
            reply_markup=kb_admin_back(),
            parse_mode="HTML",
        )
        return

    # Invite link olish
    invite_link = None
    if getattr(chat, "invite_link", None):
        invite_link = chat.invite_link
    else:
        try:
            invite_link = await bot.export_chat_invite_link(chat.id)
        except TelegramForbiddenError:
            logger.warning("Bot kanal %s da admin emas — invite link olinmadi", chat.id)
        except Exception as exc:
            logger.warning("export_chat_invite_link xato chat_id=%s: %s", chat.id, exc)

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
        logger.info(
            "Majburiy kanal %s: id=%s title=%s admin_id=%s",
            action, chat.id, chat.title, message.from_user.id,
        )

    except Exception as exc:
        logger.error("process_add_chat DB xato chat_id=%s: %s", chat.id, exc)
        await message.answer(
            "❌ Kanalni saqlashda xato yuz berdi.",
            reply_markup=kb_admin_back(),
        )


@router.callback_query(F.data.startswith("admin:del_chat:"))
async def cb_delete_chat(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        chat_id = int(callback.data.split(":")[-1])
    except (ValueError, IndexError) as exc:
        logger.error("cb_delete_chat: chat_id parse xato: %s", exc)
        await _safe_answer(callback, "❌ Xato")
        return

    try:
        deleted = await remove_required_chat(session, chat_id)
        chats = await get_required_chats(session)

        if deleted:
            text = (
                "✅ Kanal/guruh ro'yxatdan o'chirildi.\n\n"
                f"📡 <b>Majburiy Kanallar ({len(chats)} ta)</b>"
            )
            await _safe_answer(callback, "✅ O'chirildi")
            logger.info(
                "Kanal o'chirildi: chat_id=%s admin_id=%s",
                chat_id, callback.from_user.id,
            )
        else:
            text = "❌ Kanal topilmadi yoki allaqachon o'chirilgan."
            await _safe_answer(callback, "❌ Topilmadi")

        await _safe_edit(
            callback, text, reply_markup=kb_admin_manage_chats(chats), parse_mode="HTML"
        )

    except Exception as exc:
        logger.error("cb_delete_chat xato chat_id=%s: %s", chat_id, exc)
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
            await _safe_answer(callback, "Topilmadi", )
            return

        icon = "📢" if chat.chat_type == "channel" else "👥"
        uname = f"@{chat.username}" if chat.username else "—"
        link = (chat.invite_link or "—")[:50]

        await callback.answer(
            f"{icon} {chat.title}\n🆔 {chat.chat_id}\n👤 {uname}\n🔗 {link}",
            show_alert=True,
        )
    except Exception as exc:
        logger.error("cb_chat_info xato chat_id=%s: %s", chat_id, exc)
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
    except TelegramBadRequest as exc:
        logger.warning("cb_close delete xato: %s", exc)
    await _safe_answer(callback, "Panel yopildi.")


@router.callback_query(F.data == "admin:cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_panel(callback, state)
    await _safe_answer(callback, "Bekor qilindi.")
