
from __future__ import annotations

import logging
import os
import re

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def _debug_admin_ids_env() -> None:
    """
    Startup da ADMIN_IDS env o'zgaruvchisining XOM qiymatini logga chiqaradi.
    String bo'lib qolishi yoki umuman yo'qligi shu yerda ko'rinadi.
    """
    raw = os.environ.get("ADMIN_IDS", "<O'RNATILMAGAN>")
    raw_type = type(raw).__name__
    logger.info(
        "ENV tekshiruv → ADMIN_IDS xom qiymat: %r  (turi: %s)",
        raw, raw_type
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    BOT_TOKEN: str
    ADMIN_IDS: list[int] = []
    STORAGE_GROUP_ID: int

    DATABASE_URL: str = "sqlite+aiosqlite:///./kinobot.db"

    BROADCAST_CHUNK_SIZE: int = 25
    BROADCAST_SLEEP_SECONDS: float = 0.5

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v: object) -> list[int]:
        """
        Har qanday formatdan faqat raqamlarni ajratib oladi
        va int ga o'giradi — string sifatida QOLMAYDI.

        "5165462838"  →  [5165462838]   ✅ int
        5165462838    →  [5165462838]   ✅ int
        "111,222"     →  [111, 222]     ✅ int
        "111","222"   →  [111, 222]     ✅ int
        [111, 222]    →  [111, 222]     ✅ int
        ""            →  []             ⚠️  bo'sh
        """
        logger.info("ADMIN_IDS validator chaqirildi → xom qiymat: %r (turi: %s)", v, type(v).__name__)

        if isinstance(v, int):
            # Pydantic ba'zan to'g'ridan-to'g'ri int yuborishi mumkin
            logger.info("ADMIN_IDS → yagona int: [%d]", v)
            return [v]

        if isinstance(v, str):
            # Barcha raqam ketma-ketliklarini topamiz (belgidan qat'iy nazar)
            nums = re.findall(r"\d+", v)
            result = [int(n) for n in nums if n]
            logger.info("ADMIN_IDS parse: xom=%r → int ro'yxat=%s", v, result)
            if not result:
                logger.error(
                    "ADMIN_IDS BO'SH QOLDI! Xom qiymat: %r\n"
                    "Railway > Variables > ADMIN_IDS = 5165462838  (qo'shtirnoqsiz, bo'sh joy yo'q)",
                    v,
                )
            return result

        if isinstance(v, (list, tuple)):
            result = [int(x) for x in v]
            logger.info("ADMIN_IDS → list dan int ro'yxat: %s", result)
            return result

        logger.warning("ADMIN_IDS kutilmagan tur: %r (%s) → bo'sh ro'yxat qaytarildi", v, type(v).__name__)
        return []


# Logging sozlanishidan KEYIN chaqiriladi (main.py da basicConfig dan so'ng)
# Shuning uchun bu funksiyani main.py boshlanganda chaqiramiz:
debug_admin_ids_env = _debug_admin_ids_env

settings = Settings()
