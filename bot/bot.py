"""
Точка входа Telegram-бота AKASHI Data Center PLC.
"""

import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import config
from bot.logger import logger, setup_logging, InterceptHandler
import stdlib.db as db
from stdlib.handlers import user, superuser


os.makedirs("logs", exist_ok=True)
setup_logging(level="INFO")
InterceptHandler.install()


async def main() -> None:
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(user.router)
    dp.include_router(superuser.router)

    await db.init_db()

    logger.info("Bot starting… SUPERUSER_IDS={}", config.SUPERUSER_IDS)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        logger.info("Bot stopped.")
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
