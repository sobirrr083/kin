"""
keyboards/inline.py — Barcha InlineKeyboardMarkup factory funksiyalari.
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.models import RequiredChat


# ═══════════════════════════════════════════════════════════════════════════════
# User keyboards
# ═══════════════════════════════════════════════════════════════════════════════

def kb_language_select() -> InlineKeyboardMarkup:
    """Til tanlash tugmalari."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🇺🇿 O'zbek tili", callback_data="lang:uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
    )
    return builder.as_markup()


def kb_subscription(chats: list[RequiredChat], lang: str) -> InlineKeyboardMarkup:
    """
    Har bir majburiy kanal/guruh uchun 'Qo'shilish' tugmasi,
    pastda esa 'Tekshirish' tugmasi.
    """
    from locales import t

    builder = InlineKeyboardBuilder()
    for chat in chats:
        # Public kanal → t.me/username, private → invite_link
        if chat.username:
            url = f"https://t.me/{chat.username.lstrip('@')}"
        elif chat.invite_link:
            url = chat.invite_link
        else:
            continue  # Havola yo'q bo'lsa tugma qo'shmaymiz
        label = "📢 " + chat.title if chat.chat_type == "channel" else "👥 " + chat.title
        builder.row(InlineKeyboardButton(text=label, url=url))

    builder.row(
        InlineKeyboardButton(
            text=t(lang, "check_subscription_btn"),
            callback_data="check_sub",
        )
    )
    return builder.as_markup()


# ═══════════════════════════════════════════════════════════════════════════════
# Admin panel keyboards
# ═══════════════════════════════════════════════════════════════════════════════

def kb_admin_main() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Statistika", callback_data="admin:stats"))
    builder.row(InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="admin:users"))
    builder.row(InlineKeyboardButton(text="📢 Broadcast", callback_data="admin:broadcast"))
    builder.row(
        InlineKeyboardButton(text="🎬 Kinolar", callback_data="admin:manage_movies"),
        InlineKeyboardButton(text="📡 Kanallar", callback_data="admin:manage_chats"),
    )
    builder.row(InlineKeyboardButton(text="❌ Yopish", callback_data="admin:close"))
    return builder.as_markup()


def kb_admin_manage_movies() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔍 Qidirish", callback_data="admin:search_movie"),
        InlineKeyboardButton(text="🗑 O'chirish", callback_data="admin:delete_movie"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin:back"))
    return builder.as_markup()


def kb_admin_manage_chats(chats: list[RequiredChat]) -> InlineKeyboardMarkup:
    """Mavjud kanallar ro'yxati + Monitoring + Qo'shish tugmalari."""
    builder = InlineKeyboardBuilder()
    for chat in chats:
        icon = "📢" if chat.chat_type == "channel" else "👥"
        # A'zolar soni DB da saqlangan bo'lsa ko'rsatamiz
        members = f" · {chat.member_count:,}" if chat.member_count >= 0 else ""
        builder.row(
            InlineKeyboardButton(
                text=f"{icon} {chat.title}{members}",
                callback_data=f"admin:chat_info:{chat.chat_id}",
            ),
            InlineKeyboardButton(
                text="🗑",
                callback_data=f"admin:del_chat:{chat.chat_id}",
            ),
        )
    if chats:
        builder.row(
            InlineKeyboardButton(text="📊 Monitoring", callback_data="admin:channel_monitoring")
        )
    builder.row(InlineKeyboardButton(text="➕ Qo'shish", callback_data="admin:add_chat"))
    builder.row(InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin:back"))
    return builder.as_markup()


def kb_admin_back() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Asosiy menyu", callback_data="admin:back"))
    return builder.as_markup()


def kb_cancel() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin:cancel"))
    return builder.as_markup()
