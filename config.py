"""
config.py — Sozlamalar.

ADMIN_IDS Railway da quyidagi barcha formatlarda ishlaydi:
  5165462838
  "5165462838"
  5165462838,98765432
  "5165462838","98765432"
  [5165462838]
"""
from __future__ import annotations

import logging
import re

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


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
        Har qanday formatdan faqat raqamlarni ajratib oladi.
        "5165462838"  →  [5165462838]
        5165462838    →  [5165462838]
        "111","222"   →  [111, 222]
        [111, 222]    →  [111, 222]
        """
        if isinstance(v, str):
            # Barcha raqam ketma-ketliklarini topamiz (belgidan qat'iy nazar)
            nums = re.findall(r"\d+", v)
            result = [int(n) for n in nums if n]
            logger.info("ADMIN_IDS parse: xom=%r → natija=%s", v, result)
            if not result:
                logger.error(
                    "ADMIN_IDS BO'SH QOLDI! Xom qiymat: %r\n"
                    "Railway > Variables > ADMIN_IDS = 5165462838  (qo'shtirnoqsiz)",
                    v,
                )
            return result
        if isinstance(v, list):
            return [int(x) for x in v]
        return []


settings = Settings()
