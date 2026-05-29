"""
database/models.py — SQLAlchemy ORM modellari.

Jadvallar:
  movies         — Telegram file_id ni kod bilan saqlaydi
  users          — Bot ishlatgan barcha userlar (statistika uchun)
  required_chats — Majburiy a'zolik kerak bo'lgan kanal/guruhlar
                   + member_count (bot tomonidan so'ngi tekshiruv)
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Movie(Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    file_id: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False, default="video")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Tanlangan til: 'uz' yoki 'ru' (None = hali tanlamagan)
    language: Mapped[str | None] = mapped_column(String(4), nullable=True, default=None)

    # Faollik statistikasi
    last_active: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Bot bloklagan userlar
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<User id={self.user_id} username={self.username!r} lang={self.language}>"


class RequiredChat(Base):
    """Userlar a'zo bo'lishi majburiy bo'lgan kanal yoki guruhlar."""
    __tablename__ = "required_chats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)

    # @username (public kanallar uchun)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Invite link (private kanallar uchun)
    invite_link: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # 'channel' yoki 'group'
    chat_type: Mapped[str] = mapped_column(String(20), nullable=False, default="channel")

    # Bot so'ngi tekshiruvdagi a'zolar soni (-1 = hali tekshirilmagan)
    member_count: Mapped[int] = mapped_column(Integer, default=-1, nullable=False)

    # member_count so'ngi yangilangan vaqti
    member_count_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<RequiredChat id={self.chat_id} title={self.title!r} members={self.member_count}>"
