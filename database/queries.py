"""
database/queries.py — Barcha async DB operatsiyalari.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import BotSettings, Movie, RequiredChat, User

logger = logging.getLogger(__name__)

_START_CODE = 1111  # Kod sanagichi boshlang'ich qiymati


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════════
# BotSettings — kino kodi sanagichi
# ═══════════════════════════════════════════════════════════════════════════════

async def _get_or_init_settings(session: AsyncSession) -> BotSettings:
    """
    bot_settings jadvalida yagona qator oladi yoki yaratadi (id=1).
    """
    result = await session.execute(select(BotSettings).where(BotSettings.id == 1))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = BotSettings(id=1, next_code=_START_CODE)
        session.add(settings)
        await session.flush()
    return settings


async def get_next_code(session: AsyncSession) -> int:
    """
    Hozirgi next_code ni qaytaradi (DB ga yozmaydi).
    Admin panelda ko'rsatish uchun.
    """
    try:
        s = await _get_or_init_settings(session)
        await session.commit()
        return s.next_code
    except Exception as exc:
        logger.error("get_next_code xato: %s", exc)
        await session.rollback()
        return _START_CODE


async def consume_next_code(session: AsyncSession) -> int:
    """
    Joriy kodni qaytaradi va counter ni +1 qiladi.
    Yangi kino qo'shilganda chaqiriladi.
    """
    try:
        s = await _get_or_init_settings(session)
        code = s.next_code
        s.next_code = code + 1
        s.updated_at = _now()
        await session.commit()
        logger.info("Kod berildi: %s → keyingisi: %s", code, s.next_code)
        return code
    except Exception as exc:
        logger.error("consume_next_code xato: %s", exc)
        await session.rollback()
        raise


async def set_next_code(session: AsyncSession, new_code: int) -> bool:
    """
    Admin tomonidan next_code ni o'zgartirish.
    new_code >= 1 bo'lishi kerak.
    True — muvaffaqiyatli, False — xato.
    """
    if new_code < 1:
        return False
    try:
        s = await _get_or_init_settings(session)
        old = s.next_code
        s.next_code = new_code
        s.updated_at = _now()
        await session.commit()
        logger.info("next_code o'zgartirildi: %s → %s", old, new_code)
        return True
    except Exception as exc:
        logger.error("set_next_code xato: %s", exc)
        await session.rollback()
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# User queries
# ═══════════════════════════════════════════════════════════════════════════════

async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
    try:
        result = await session.execute(select(User).where(User.user_id == user_id))
        return result.scalar_one_or_none()
    except Exception as exc:
        logger.error("get_user_by_id xato: %s", exc)
        return None


async def get_or_create_user(
    session: AsyncSession,
    *,
    user_id: int,
    username: Optional[str],
    full_name: Optional[str],
) -> tuple[User, bool]:
    try:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if user is not None:
            user.username = username
            user.full_name = full_name
            user.is_blocked = False
            await session.commit()
            return user, False
        user = User(user_id=user_id, username=username, full_name=full_name)
        session.add(user)
        await session.flush()
        await session.commit()
        logger.info("Yangi user: user_id=%s username=%s", user_id, username)
        return user, True
    except IntegrityError:
        await session.rollback()
        try:
            result = await session.execute(select(User).where(User.user_id == user_id))
            user = result.scalar_one()
            user.username = username
            user.full_name = full_name
            user.is_blocked = False
            await session.commit()
            return user, False
        except Exception as exc2:
            logger.error("get_or_create_user re-select xato: %s", exc2)
            await session.rollback()
            raise
    except Exception as exc:
        logger.error("get_or_create_user xato: %s", exc)
        await session.rollback()
        raise


async def set_user_language(session: AsyncSession, user_id: int, language: str) -> None:
    try:
        await session.execute(update(User).where(User.user_id == user_id).values(language=language))
        await session.commit()
    except Exception as exc:
        logger.error("set_user_language xato: %s", exc)
        await session.rollback()
        raise


async def update_user_activity(session: AsyncSession, user_id: int) -> None:
    try:
        await session.execute(
            update(User).where(User.user_id == user_id).values(
                last_active=_now(),
                message_count=User.message_count + 1,
                is_blocked=False,
            )
        )
        await session.commit()
    except Exception as exc:
        logger.error("update_user_activity xato: %s", exc)
        await session.rollback()


async def mark_user_blocked(session: AsyncSession, user_id: int) -> None:
    try:
        await session.execute(update(User).where(User.user_id == user_id).values(is_blocked=True))
        await session.commit()
    except Exception as exc:
        logger.error("mark_user_blocked xato: %s", exc)
        await session.rollback()


async def get_active_user_ids(session: AsyncSession) -> list[int]:
    try:
        result = await session.execute(
            select(User.user_id).where(User.is_blocked == False)  # noqa: E712
        )
        return list(result.scalars().all())
    except Exception as exc:
        logger.error("get_active_user_ids xato: %s", exc)
        return []


async def count_users(session: AsyncSession) -> int:
    try:
        result = await session.execute(select(func.count()).select_from(User))
        return result.scalar_one()
    except Exception as exc:
        return 0


async def count_blocked_users(session: AsyncSession) -> int:
    try:
        result = await session.execute(
            select(func.count()).select_from(User).where(User.is_blocked == True)  # noqa: E712
        )
        return result.scalar_one()
    except Exception as exc:
        return 0


async def count_active_non_blocked(session: AsyncSession) -> int:
    try:
        result = await session.execute(
            select(func.count()).select_from(User).where(User.is_blocked == False)  # noqa: E712
        )
        return result.scalar_one()
    except Exception as exc:
        return 0


async def count_active_users(session: AsyncSession, since: datetime) -> int:
    try:
        result = await session.execute(
            select(func.count()).select_from(User)
            .where(User.last_active >= since)
            .where(User.is_blocked == False)  # noqa: E712
        )
        return result.scalar_one()
    except Exception as exc:
        return 0


async def get_top_active_users(session: AsyncSession, limit: int = 10) -> list[User]:
    try:
        result = await session.execute(
            select(User).order_by(User.message_count.desc()).limit(limit)
        )
        return list(result.scalars().all())
    except Exception as exc:
        return []


async def get_full_stats(session: AsyncSession) -> dict:
    now = _now()
    return {
        "total_users": await count_users(session),
        "active_users": await count_active_non_blocked(session),
        "blocked_users": await count_blocked_users(session),
        "daily_active": await count_active_users(session, now - timedelta(days=1)),
        "weekly_active": await count_active_users(session, now - timedelta(weeks=1)),
        "monthly_active": await count_active_users(session, now - timedelta(days=30)),
        "total_movies": await count_movies(session),
        "top_users": await get_top_active_users(session, limit=5),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Movie queries
# ═══════════════════════════════════════════════════════════════════════════════

async def save_movie(
    session: AsyncSession,
    *,
    code: str,
    file_id: str,
    title: Optional[str],
    file_type: str,
) -> tuple[Movie, bool]:
    try:
        result = await session.execute(select(Movie).where(Movie.code == code))
        movie = result.scalar_one_or_none()
        if movie is not None:
            movie.file_id = file_id
            movie.title = title
            movie.file_type = file_type
            await session.commit()
            return movie, False
        movie = Movie(code=code, file_id=file_id, title=title, file_type=file_type)
        session.add(movie)
        await session.commit()
        return movie, True
    except Exception as exc:
        logger.error("save_movie xato code=%s: %s", code, exc)
        await session.rollback()
        raise


async def get_movie_by_code(session: AsyncSession, code: str) -> Optional[Movie]:
    try:
        result = await session.execute(select(Movie).where(Movie.code == code))
        return result.scalar_one_or_none()
    except Exception as exc:
        logger.error("get_movie_by_code xato: %s", exc)
        return None


async def delete_movie_by_code(session: AsyncSession, code: str) -> bool:
    try:
        result = await session.execute(delete(Movie).where(Movie.code == code))
        await session.commit()
        return result.rowcount > 0
    except Exception as exc:
        logger.error("delete_movie_by_code xato: %s", exc)
        await session.rollback()
        return False


async def set_movie_extra_caption(
    session: AsyncSession, code: str, extra_caption: Optional[str]
) -> bool:
    try:
        result = await session.execute(
            update(Movie).where(Movie.code == code).values(extra_caption=extra_caption)
        )
        await session.commit()
        return result.rowcount > 0
    except Exception as exc:
        logger.error("set_movie_extra_caption xato: %s", exc)
        await session.rollback()
        return False


async def count_movies(session: AsyncSession) -> int:
    try:
        result = await session.execute(select(func.count()).select_from(Movie))
        return result.scalar_one()
    except Exception as exc:
        return 0


# ═══════════════════════════════════════════════════════════════════════════════
# RequiredChat queries
# ═══════════════════════════════════════════════════════════════════════════════

async def get_required_chats(session: AsyncSession) -> list[RequiredChat]:
    try:
        result = await session.execute(select(RequiredChat).order_by(RequiredChat.added_at))
        return list(result.scalars().all())
    except Exception as exc:
        return []


async def add_required_chat(
    session: AsyncSession,
    *,
    chat_id: int,
    title: str,
    username: Optional[str],
    invite_link: Optional[str],
    chat_type: str,
) -> tuple[RequiredChat, bool]:
    try:
        result = await session.execute(select(RequiredChat).where(RequiredChat.chat_id == chat_id))
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.title = title
            existing.username = username
            existing.invite_link = invite_link
            existing.chat_type = chat_type
            await session.commit()
            return existing, False
        chat = RequiredChat(
            chat_id=chat_id, title=title, username=username,
            invite_link=invite_link, chat_type=chat_type,
        )
        session.add(chat)
        await session.commit()
        return chat, True
    except Exception as exc:
        logger.error("add_required_chat xato: %s", exc)
        await session.rollback()
        raise


async def remove_required_chat(session: AsyncSession, chat_id: int) -> bool:
    try:
        result = await session.execute(delete(RequiredChat).where(RequiredChat.chat_id == chat_id))
        await session.commit()
        return result.rowcount > 0
    except Exception as exc:
        await session.rollback()
        return False


async def update_chat_member_count(session: AsyncSession, chat_id: int, member_count: int) -> None:
    try:
        await session.execute(
            update(RequiredChat).where(RequiredChat.chat_id == chat_id).values(
                member_count=member_count,
                member_count_updated_at=_now(),
            )
        )
        await session.commit()
    except Exception as exc:
        logger.error("update_chat_member_count xato: %s", exc)
        await session.rollback()


# ═══════════════════════════════════════════════════════════════════════════════
# Dinamik adminlar boshqaruvi
# ═══════════════════════════════════════════════════════════════════════════════

async def get_dynamic_admin_ids(session: AsyncSession) -> list[int]:
    """DB dagi barcha dinamik admin IDlarini qaytaradi."""
    from database.models import DynamicAdmin
    from sqlalchemy import select
    result = await session.execute(select(DynamicAdmin.user_id))
    return [row[0] for row in result.fetchall()]


async def add_dynamic_admin(session: AsyncSession, user_id: int, added_by: int) -> tuple[bool, bool]:
    """
    Yangi dinamik admin qo'shadi.
    Qaytaradi: (success, already_exists)
    """
    from database.models import DynamicAdmin
    from sqlalchemy import select
    try:
        existing = await session.execute(
            select(DynamicAdmin).where(DynamicAdmin.user_id == user_id)
        )
        if existing.scalar_one_or_none():
            return False, True  # allaqachon bor
        admin = DynamicAdmin(user_id=user_id, added_by=added_by)
        session.add(admin)
        await session.commit()
        return True, False
    except Exception as exc:
        await session.rollback()
        logger.error("add_dynamic_admin xato: %s", exc)
        return False, False


async def remove_dynamic_admin(session: AsyncSession, user_id: int) -> bool:
    """Dinamik adminni o'chiradi. Qaytaradi: True — o'chirildi."""
    from database.models import DynamicAdmin
    from sqlalchemy import select, delete
    try:
        result = await session.execute(
            select(DynamicAdmin).where(DynamicAdmin.user_id == user_id)
        )
        admin = result.scalar_one_or_none()
        if not admin:
            return False
        await session.execute(
            delete(DynamicAdmin).where(DynamicAdmin.user_id == user_id)
        )
        await session.commit()
        return True
    except Exception as exc:
        await session.rollback()
        logger.error("remove_dynamic_admin xato: %s", exc)
        return False


async def get_all_dynamic_admins(session: AsyncSession):
    """Barcha dinamik adminlar ro'yxatini qaytaradi."""
    from database.models import DynamicAdmin
    from sqlalchemy import select
    result = await session.execute(select(DynamicAdmin).order_by(DynamicAdmin.added_at))
    return result.scalars().all()
