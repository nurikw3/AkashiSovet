"""
Точка входа Telegram-бота AKASHI Data Center PLC.
Включает: AIogram 3.7+, Redis FSM (Manual Client), PostgreSQL, APScheduler (Астана UTC+6)
"""

import asyncio
import os

import pytz
import redis.asyncio as redis
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage

# ✅ ИСПРАВЛЕНИЕ: Правильный импорт DefaultBotProperties в новых версиях Aiogram
from aiogram.client.default import DefaultBotProperties

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import config
from bot.logger import logger, setup_logging, InterceptHandler
import stdlib.db as db
from stdlib import resources
from stdlib.handlers import user, superuser

# ─── Настройка логирования ────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
setup_logging(level="INFO")
InterceptHandler.install()

# ─── Планировщик и Таймзона ───────────────────────────────────────────────────
scheduler = AsyncIOScheduler()
ASTANA_TZ = pytz.timezone("Asia/Almaty")


async def send_daily_report(bot: Bot) -> None:
    """Задача APScheduler: ежедневный отчет суперюзерам."""
    try:
        stats = await db.get_daily_stats()

        text = (
            "📊 <b>Ежедневный отчет по заявкам</b>\n\n"
            "🕒 Текущие суммы по статусам:\n"
            f"✅ Согласовано: <b>{stats.get('approved', 0)}</b>\n"
            f"⏳ В ожидании: <b>{stats.get('pending', 0)}</b>\n"
            f"✎ Черновики: <b>{stats.get('draft', 0)}</b>\n"
            f"🔁 На доработке: <b>{stats.get('rework', 0)}</b>\n\n"
            "Не забудь проверить заявки в ожидании! 👀"
        )

        for admin_id in config.SUPERUSER_IDS:
            try:
                await bot.send_message(admin_id, text, parse_mode="HTML")
            except Exception as e:
                logger.warning("Failed to send report to admin {}: {}", admin_id, e)

    except Exception as e:
        logger.error("Daily report task failed: {}", e)


async def main() -> None:
    # Используем DefaultBotProperties для parse_mode
    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

    # ─── ВАРИАНТ 2: Ручное создание клиента Redis для FSM ─────────────────────
    fsm_redis_client = redis.from_url(
        config.REDIS_URL,
        db=1,
        decode_responses=True,
        health_check_interval=30,
        socket_connect_timeout=5,
        socket_timeout=5,
    )

    redis_storage = RedisStorage(redis=fsm_redis_client)
    dp = Dispatcher(storage=redis_storage)

    # ─── Роутеры ──────────────────────────────────────────────────────────────
    dp.include_router(user.router)
    dp.include_router(superuser.router)

    # ─── Инициализация сервисов ───────────────────────────────────────────────
    await resources.init_resources()

    # ─── Настройка Планировщика (ТЕСТОВЫЙ РЕЖИМ: каждые 5 секунд) ─────────────
    # ПОМНИ: Верни 'cron' перед продакшеном!
    # scheduler.add_job(
    #     send_daily_report,
    #     trigger="interval",
    #     seconds=5,
    #     args=[bot],
    #     id="test_report_job",
    #     replace_existing=True,
    # )

    # Для продакшена раскомментируй это, а верхний блок закомментируй:
    scheduler.add_job(
        send_daily_report,
        trigger="cron",
        hour=10,
        minute=0,
        timezone=ASTANA_TZ,
        args=[bot],
        id="daily_report_job",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info("🕐 Scheduler started (Test mode: every 5s)")

    logger.info("🤖 Bot starting… SUPERUSER_IDS={}", config.SUPERUSER_IDS)

    # ─── Запуск Polling ───────────────────────────────────────────────────────
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        logger.info("🛑 Shutting down...")
        scheduler.shutdown(wait=False)
        await dp.storage.close()
        await resources.shutdown_resources()
        await bot.session.close()
        logger.info("✅ Bot stopped gracefully.")


if __name__ == "__main__":
    asyncio.run(main())
