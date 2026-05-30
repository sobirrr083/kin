"""
handlers/ingestion.py — Storage guruhidan kino yuklash.

Kod berilish tartibi:
  1. Caption da kod yozilgan bo'lsa → o'sha kod ishlatiladi
  2. Caption da kod yo'q (faqat title yoki bo'sh) → avtomatik kod beriladi
     Avtomatik kod: DB dagi next_code (1111 dan boshlanadi, har yuklashda +1)

Guruhga video/document yuborilganda:
  Caption formatlari:
    "Inception"            → avtomatik kod + "Inception" title
    "1234 | Inception"     → kod=1234, title=Inception
    "1234"                 → kod=1234, title yo'q
    (caption yo'q)         → avtomatik kod, title yo'q

Har bir kinoga qattiy qo'shimcha: "Tezkor Cinema - 🍿 Kino olamiga eng qisqa yo'l."
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import consume_next_code, save_movie
from filters.admin import IsStorageGroup

logger = logging.getLogger(__name__)

router = Router(name="ingestion")
router.message.filter(IsStorageGroup())

# Har bir kino yuborilganda captionning OXIRIGA qo'shiladigan qat'iy matn
FIXED_CAPTION_SUFFIX = "\n\nTezkor Cinema - 🍿 Kino olamiga eng qisqa yo'l."

# ── Caption parsing ───────────────────────────────────────────────────────────
_CODE_RE = re.compile(r"^(?P<code>[A-Za-z0-9]+)(?:\s*\|\s*|\s+)(?P<title>.+)?", re.DOTALL)
_ONLY_CODE_RE = re.compile(r"^(?P<code>[A-Za-z0-9]+)\s*$")
_STARTS_WITH_DIGIT = re.compile(r"^\d")


def _parse_caption(caption: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """
    Caption dan (code, title) ajratib oladi.

    Qaytarish:
      (code, title)  — kod topildi
      (None, title)  — kod topilmadi, avtomatik berilishi kerak
      (None, None)   — caption bo'sh
    """
    if not caption or not caption.strip():
        return None, None

    caption = caption.strip()

    m = _ONLY_CODE_RE.match(caption)
    if m:
        token = m.group("code")
        if token.isdigit() or (not token.isalpha()):
            return token, None
        return None, token

    m = _CODE_RE.match(caption)
    if m:
        token = m.group("code")
        raw_title = m.group("title")
        title = raw_title.strip() if raw_title else None

        if token.isdigit() or (not token.isalpha()):
            return token, title or None

        return None, caption

    return None, caption or None


# ── Handler ───────────────────────────────────────────────────────────────────

@router.message(F.video | F.document)
async def handle_movie_upload(message: Message, session: AsyncSession, bot: Bot) -> None:
    if message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
    else:
        return

    code, title = _parse_caption(message.caption)

    auto_code = False
    if code is None:
        code = str(await consume_next_code(session))
        auto_code = True
        logger.info("Avtomatik kod berildi: %s", code)

    movie, created = await save_movie(
        session,
        code=code,
        file_id=file_id,
        title=title,
        file_type=file_type,
    )

    action = "✅ Saqlandi" if created else "🔄 Yangilandi"
    title_line = f"\n🏷 <b>Nomi:</b> {title}" if title else ""
    auto_line = "\n🤖 <i>Kod avtomatik berildi</i>" if auto_code else ""

    await message.reply(
        f"{action}!\n"
        f"📌 <b>Kod:</b> <code>{code}</code>"
        f"{title_line}\n"
        f"📁 <b>Turi:</b> {file_type.capitalize()}"
        f"{auto_line}\n\n"
        f"🔗 <b>Havola:</b>\n"
        f"<code>t.me/{(await bot.get_me()).username}?start={code}</code>",
        parse_mode="HTML",
    )
    logger.info(
        "Movie %s | code=%s auto=%s title=%s type=%s user=%s",
        "saqlandi" if created else "yangilandi",
        code, auto_code, title, file_type,
        message.from_user.id if message.from_user else "unknown",
    )
