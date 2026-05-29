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

from database.models import Movie, RequiredChat, User

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════════
# User queries
# ═══════════════════════════════════════════════════════════════════════════════

async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
    try:
        result = await session.execute(select(User).where(User.user_id == user_id))
        return result.scalar_one_or_none()
    except Exception as exc:
        logger.error("get_user_by_id xato user_id=%s: %s", user_id, exc)
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
        logger.warning("get_or_create_user: UNIQUE conflict user_id=%s — re-select", user_id)
        try:
            result = await session.execute(select(User).where(User.user_id == user_id))
            user = result.scalar_one()
            user.username = username
            user.full_name = full_name
            user.is_blocked = False
            await session.commit()
            return user, False
        except Exception as exc2:
            logger.error("get_or_create_user re-select xato user_id=%s: %s", user_id, exc2)
            await session.rollback()
            raise

    except Exception as exc:
        logger.error("get_or_create_user xato user_id=%s: %s", user_id, exc)
        await session.rollback()
        raise


async def set_user_language(session: AsyncSession, user_id: int, language: str) -> None:
    try:
        await session.execute(
            update(User).where(User.user_id == user_id).values(language=language)
        )
        await session.commit()
    except Exception as exc:
        logger.error("set_user_language xato user_id=%s lang=%s: %s", user_id, language, exc)
        await session.rollback()
        raise


async def update_user_activity(session: AsyncSession, user_id: int) -> None:
    try:
        await session.execute(
            update(User)
            .where(User.user_id == user_id)
            .values(
                last_active=_now(),
                message_count=User.message_count + 1,
                is_blocked=False,
            )
        )
        await session.commit()
    except Exception as exc:
        logger.error("update_user_activity xato user_id=%s: %s", user_id, exc)
        await session.rollback()


async def mark_user_blocked(session: AsyncSession, user_id: int) -> None:
    try:
        await session.execute(
            update(User).where(User.user_id == user_id).values(is_blocked=True)
        )
        await session.commit()
    except Exception as exc:
        logger.error("mark_user_blocked xato user_id=%s: %s", user_id, exc)
        await session.rollback()


async def get_all_user_ids(session: AsyncSession) -> list[int]:
    try:
        result = await session.execute(select(User.user_id))
        return list(result.scalars().all())
    except Exception as exc:
        logger.error("get_all_user_ids xato: %s", exc)
        return []


async def get_active_user_ids(session: AsyncSession) -> list[int]:
    """Broadcast uchun: faqat botni bloklamagan userlar."""
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
        logger.error("count_users xato: %s", exc)
        return 0


async def count_blocked_users(session: AsyncSession) -> int:
    try:
        result = await session.execute(
            select(func.count()).select_from(User).where(User.is_blocked == True)  # noqa: E712
        )
        return result.scalar_one()
    except Exception as exc:
        logger.error("count_blocked_users xato: %s", exc)
        return 0


async def count_active_non_blocked(session: AsyncSession) -> int:
    """Botni bloklamagan userlar soni."""
    try:
        result = await session.execute(
            select(func.count()).select_from(User).where(User.is_blocked == False)  # noqa: E712
        )
        return result.scalar_one()
    except Exception as exc:
        logger.error("count_active_non_blocked xato: %s", exc)
        return 0


async def count_active_users(session: AsyncSession, since: datetime) -> int:
    try:
        result = await session.execute(
            select(func.count())
            .select_from(User)
            .where(User.last_active >= since)
            .where(User.is_blocked == False)  # noqa: E712
        )
        return result.scalar_one()
    except Exception as exc:
        logger.error("count_active_users xato: %s", exc)
        return 0


async def get_top_active_users(session: AsyncSession, limit: int = 10) -> list[User]:
    try:
        result = await session.execute(
            select(User).order_by(User.message_count.desc()).limit(limit)
        )
        return list(result.scalars().all())
    except Exception as exc:
        logger.error("get_top_active_users xato: %s", exc)
        return []


async def get_full_stats(session: AsyncSession) -> dict:
    """Admin panel uchun barcha statistikani qaytaradi."""
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
        logger.error("get_movie_by_code xato code=%s: %s", code, exc)
        return None


async def delete_movie_by_code(session: AsyncSession, code: str) -> bool:
    try:
        result = await session.execute(delete(Movie).where(Movie.code == code))
        await session.commit()
        return result.rowcount > 0
    except Exception as exc:
        logger.error("delete_movie_by_code xato code=%s: %s", code, exc)
        await session.rollback()
        return False


async def count_movies(session: AsyncSession) -> int:
    try:
        result = await session.execute(select(func.count()).select_from(Movie))
        return result.scalar_one()
    except Exception as exc:
        logger.error("count_movies xato: %s", exc)
        return 0


# ═══════════════════════════════════════════════════════════════════════════════
# RequiredChat queries
# ═══════════════════════════════════════════════════════════════════════════════

async def get_required_chats(session: AsyncSession) -> list[RequiredChat]:
    try:
        result = await session.execute(
            select(RequiredChat).order_by(RequiredChat.added_at)
        )
        return list(result.scalars().all())
    except Exception as exc:
        logger.error("get_required_chats xato: %s", exc)
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
        result = await session.execute(
            select(RequiredChat).where(RequiredChat.chat_id == chat_id)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.title = title
            existing.username = username
            existing.invite_link = invite_link
            existing.chat_type = chat_type
            await session.commit()
            return existing, False
        chat = RequiredChat(
            chat_id=chat_id,
            title=title,
            username=username,
            invite_link=invite_link,
            chat_type=chat_type,
        )
        session.add(chat)
        await session.commit()
        return chat, True
    except Exception as exc:
        logger.error("add_required_chat xato chat_id=%s: %s", chat_id, exc)
        await session.rollback()
        raise


async def remove_required_chat(session: AsyncSession, chat_id: int) -> bool:
    try:
        result = await session.execute(
            delete(RequiredChat).where(RequiredChat.chat_id == chat_id)
        )
        await session.commit()
        return result.rowcount > 0
    except Exception as exc:
        logger.error("remove_required_chat xato chat_id=%s: %s", chat_id, exc)
        await session.rollback()
        return False


async def update_chat_member_count(
    session: AsyncSession,
    chat_id: int,
    member_count: int,
) -> None:
    """Kanal a'zolar sonini DB ga yozadi."""
    try:
        await session.execute(
            update(RequiredChat)
            .where(RequiredChat.chat_id == chat_id)
            .values(
                member_count=member_count,
                member_count_updated_at=_now(),
            )
        )
        await session.commit()
    except Exception as exc:
        logger.error("update_chat_member_count xato chat_id=%s: %s", chat_id, exc)
        await session.rollback()
