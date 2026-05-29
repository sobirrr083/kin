"""
handlers/ingestion.py — Movie ingestion from the private storage group.

Flow
----
1. Admin posts a Video or Document in STORAGE_GROUP_ID.
2. The caption must begin with a unique code (numeric or alphanumeric),
   optionally followed by a pipe separator and a title:
     "5055"
     "5055 | Inception"
     "A101 | The Godfather"
3. The bot parses the code + title, stores (code, file_id, file_type)
   in the database, and replies with a confirmation.

Only messages from STORAGE_GROUP_ID are processed (enforced by the
IsStorageGroup router-level filter).
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import save_movie
from filters.admin import IsStorageGroup

logger = logging.getLogger(__name__)

router = Router(name="ingestion")

# ── Router-level filter: only process messages from the storage group ──────────
router.message.filter(IsStorageGroup())

# ── Caption parsing ───────────────────────────────────────────────────────────
# Accepted formats:
#   "5055"
#   "5055 | Inception"
#   "A101 The Godfather"   (space instead of pipe also works)
_CAPTION_RE = re.compile(
    r"^(?P<code>[A-Za-z0-9]+)"          # mandatory code at start
    r"(?:\s*\|\s*|\s+(?=\S))"           # optional separator: " | " or space
    r"(?P<title>.+)?",                   # optional title
    re.DOTALL,
)


def _parse_caption(caption: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """
    Extract (code, title) from a caption string.

    Returns (None, None) when the caption is absent or malformed.
    """
    if not caption:
        return None, None
    caption = caption.strip()
    match = _CAPTION_RE.match(caption)
    if not match:
        return None, None
    code = match.group("code")
    raw_title = match.group("title")
    title = raw_title.strip() if raw_title else None
    return code, title or None


# ── Handler ───────────────────────────────────────────────────────────────────


@router.message(F.video | F.document)
async def handle_movie_upload(message: Message, session: AsyncSession, bot: Bot) -> None:
    """
    Intercepts video/document posts in the storage group and persists them.
    """
    # ── Resolve file metadata ──────────────────────────────────────────────
    if message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
    else:
        return  # Unreachable but satisfies type checker

    # ── Parse the caption ──────────────────────────────────────────────────
    code, title = _parse_caption(message.caption)

    if not code:
        await message.reply(
            "⚠️ <b>Missing movie code in caption.</b>\n\n"
            "Please resend the file with a caption in one of these formats:\n"
            "  • <code>5055</code>\n"
            "  • <code>5055 | Inception</code>\n"
            "  • <code>A101 | The Godfather (1972)</code>",
            parse_mode="HTML",
        )
        return

    # ── Persist to database ────────────────────────────────────────────────
    movie, created = await save_movie(
        session,
        code=code,
        file_id=file_id,
        title=title,
        file_type=file_type,
    )

    action_word = "saved" if created else "updated"
    title_line = f"\n🏷 <b>Title:</b> {title}" if title else ""

    await message.reply(
        f"✅ <b>Movie {action_word} successfully!</b>\n"
        f"📌 <b>Code:</b> <code>{code}</code>"
        f"{title_line}\n"
        f"📁 <b>Type:</b> {file_type.capitalize()}",
        parse_mode="HTML",
    )
    logger.info(
        "Movie %s | code=%s title=%s type=%s by user_id=%s",
        action_word,
        code,
        title,
        file_type,
        message.from_user.id if message.from_user else "unknown",
    )
