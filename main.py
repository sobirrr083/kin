"""
main.py — KinoBot ishga tushirish nuqtasi.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from database.engine import create_tables, dispose_engine
from handlers import admin, ingestion, user
from middlewares.database import DatabaseMiddleware
from middlewares.subscription import SubscriptionMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)-8s]  %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logging.getLogger("aiogram").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def _build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(DatabaseMiddleware())
    dp.message.middleware(SubscriptionMiddleware())
    dp.include_router(ingestion.router)
    dp.include_router(admin.router)
    dp.include_router(user.router)
    return dp


async def main() -> None:
    logger.info("═══════════════════════════════════════")
    logger.info("  KinoBot ishga tushmoqda...")
    logger.info("═══════════════════════════════════════")

    await create_tables()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = _build_dispatcher()

    logger.info(
        "Admin: %s | StorageGroup: %s | DB: %s | Subscription: %s",
        settings.ADMIN_IDS,
        settings.STORAGE_GROUP_ID,
        settings.DATABASE_URL.split("://")[0],
        "YOQILGAN" if SubscriptionMiddleware.SUBSCRIPTION_ENABLED else "O'CHIRILGAN",
    )

    if not settings.ADMIN_IDS:
        logger.error(
            "\n"
            "══════════════════════════════════════════\n"
            " XATO: ADMIN_IDS BO'SH!\n"
            " /admin ISHLAMAYDI!\n"
            "\n"
            " Yechim — Railway > Variables > Add:\n"
            "   Name:  ADMIN_IDS\n"
            "   Value: 123456789   ← o'z ID ingiz\n"
            "\n"
            " ID ni bilish: @userinfobot > /start\n"
            "══════════════════════════════════════════"
        )
    else:
        logger.info("✅ Admin tayyor. ADMIN_IDS: %s", settings.ADMIN_IDS)

    logger.info("Bot polling rejimida ishlamoqda.")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await dispose_engine()
        await bot.session.close()
        logger.info("KinoBot to'xtatildi.")


if __name__ == "__main__":
    asyncio.run(main())
