"""
database/queries.py — Barcha async DB operatsiyalari.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Movie, RequiredChat, User

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════════
# User queries
# ═══════════════════════════════════════════════════════════════════════════════

async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
    result = await session.execute(select(User).where(User.user_id == user_id))
    return result.scalar_one_or_none()


async def get_or_create_user(
    session: AsyncSession,
    *,
    user_id: int,
    username: Optional[str],
    full_name: Optional[str],
) -> tuple[User, bool]:
    """User mavjud bo'lsa qaytaradi, yo'q bo'lsa yaratadi. (user, created)"""
    result = await session.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is not None:
        # Ma'lumotlarni yangilash
        user.username = username
        user.full_name = full_name
        user.is_blocked = False
        await session.commit()
        return user, False
    user = User(user_id=user_id, username=username, full_name=full_name)
    session.add(user)
    await session.commit()
    logger.info("Yangi user: user_id=%s username=%s", user_id, username)
    return user, True


async def set_user_language(
    session: AsyncSession, user_id: int, language: str
) -> None:
    await session.execute(
        update(User).where(User.user_id == user_id).values(language=language)
    )
    await session.commit()


async def update_user_activity(session: AsyncSession, user_id: int) -> None:
    """Har xabar yuborilganda last_active va message_count ni yangilaydi."""
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


async def mark_user_blocked(session: AsyncSession, user_id: int) -> None:
    await session.execute(
        update(User).where(User.user_id == user_id).values(is_blocked=True)
    )
    await session.commit()


async def get_all_user_ids(session: AsyncSession) -> list[int]:
    result = await session.execute(select(User.user_id))
    return list(result.scalars().all())


async def count_users(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(User))
    return result.scalar_one()


async def count_blocked_users(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count()).select_from(User).where(User.is_blocked == True)  # noqa: E712
    )
    return result.scalar_one()


async def count_active_users(session: AsyncSession, since: datetime) -> int:
    """Berilgan vaqtdan beri faol bo'lgan userlar soni."""
    result = await session.execute(
        select(func.count())
        .select_from(User)
        .where(User.last_active >= since)
        .where(User.is_blocked == False)  # noqa: E712
    )
    return result.scalar_one()


async def get_top_active_users(
    session: AsyncSession, limit: int = 10
) -> list[User]:
    """Eng ko'p xabar yuborgan userlar (TOP-N)."""
    result = await session.execute(
        select(User)
        .order_by(User.message_count.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_full_stats(session: AsyncSession) -> dict:
    """Admin panel uchun barcha statistikani bir so'rovda qaytaradi."""
    now = _now()
    daily = await count_active_users(session, now - timedelta(days=1))
    weekly = await count_active_users(session, now - timedelta(weeks=1))
    monthly = await count_active_users(session, now - timedelta(days=30))
    return {
        "total_users": await count_users(session),
        "blocked_users": await count_blocked_users(session),
        "daily_active": daily,
        "weekly_active": weekly,
        "monthly_active": monthly,
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


async def get_movie_by_code(session: AsyncSession, code: str) -> Optional[Movie]:
    result = await session.execute(select(Movie).where(Movie.code == code))
    return result.scalar_one_or_none()


async def delete_movie_by_code(session: AsyncSession, code: str) -> bool:
    result = await session.execute(delete(Movie).where(Movie.code == code))
    await session.commit()
    return result.rowcount > 0


async def count_movies(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(Movie))
    return result.scalar_one()


# ═══════════════════════════════════════════════════════════════════════════════
# RequiredChat queries
# ═══════════════════════════════════════════════════════════════════════════════

async def get_required_chats(session: AsyncSession) -> list[RequiredChat]:
    result = await session.execute(
        select(RequiredChat).order_by(RequiredChat.added_at)
    )
    return list(result.scalars().all())


async def add_required_chat(
    session: AsyncSession,
    *,
    chat_id: int,
    title: str,
    username: Optional[str],
    invite_link: Optional[str],
    chat_type: str,
) -> tuple[RequiredChat, bool]:
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


async def remove_required_chat(session: AsyncSession, chat_id: int) -> bool:
    result = await session.execute(
        delete(RequiredChat).where(RequiredChat.chat_id == chat_id)
    )
    await session.commit()
    return result.rowcount > 0
