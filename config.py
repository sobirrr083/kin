"""
config.py — Centralised settings loaded from environment / .env file.

pydantic-settings reads each variable from:
  1. The actual environment (Railway injects these at runtime)
  2. The local .env file (useful for local dev)

Any missing required variable raises a clear ValidationError on startup.
"""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # ── Telegram ──────────────────────────────────────────────
    BOT_TOKEN: str
    ADMIN_IDS: list[int] = []
    STORAGE_GROUP_ID: int

    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./kinobot.db"

    # ── Broadcast rate-limit: pause every N messages ──────────
    BROADCAST_CHUNK_SIZE: int = 25
    BROADCAST_SLEEP_SECONDS: float = 0.5

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v: object) -> list[int]:
        """Accept either a real list or a comma-separated string from the env."""
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip().isdigit()]
        if isinstance(v, list):
            return [int(x) for x in v]
        return []


# Single shared instance — import this everywhere.
settings = Settings()
