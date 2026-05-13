import asyncio

import redis.asyncio as redis
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage

from aiogram.client.default import DefaultBotProperties

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import config
from bot.logger import logger, setup_logging, InterceptHandler, prepare_log_storage
import stdlib.db as db
from stdlib.access_middleware import AccessControlMiddleware
from stdlib import resources
from stdlib.handlers import user, superuser
from stdlib.services.pdf_delivery_queue import (
    start_pdf_delivery_workers,
    stop_pdf_delivery_workers,
)
from stdlib.timezone_util import APP_TIMEZONE

prepare_log_storage(
    log_dir=config.LOG_DIR,
    clean_on_start=config.LOG_CLEAN_ON_START,
    max_total_mb=config.LOG_MAX_TOTAL_MB,
)
setup_logging(
    level=config.LOG_LEVEL,
    file_level=config.LOG_FILE_LEVEL,
    error_level=config.LOG_ERROR_LEVEL,
    log_dir=config.LOG_DIR,
    rotation_mb=config.LOG_ROTATION_MB,
    retention_days=config.LOG_RETENTION_DAYS,
    errors_rotation_mb=config.LOG_ERRORS_ROTATION_MB,
    errors_retention_days=config.LOG_ERRORS_RETENTION_DAYS,
)
InterceptHandler.install()

scheduler = AsyncIOScheduler()


async def send_daily_report(bot: Bot) -> None:
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
    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

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
    dp.update.outer_middleware(AccessControlMiddleware())

    dp.include_router(user.router)
    dp.include_router(superuser.router)

    await resources.init_resources()
    pdf_queue_tasks, pdf_queue_stop = start_pdf_delivery_workers(bot)

    # test mode
    # scheduler.add_job(
    #     send_daily_report,
    #     trigger="interval",
    #     seconds=5,
    #     args=[bot],
    #     id="test_report_job",
    #     replace_existing=True,
    # )

    scheduler.add_job(
        send_daily_report,
        trigger="cron",
        hour=10,
        minute=0,
        timezone=APP_TIMEZONE,
        args=[bot],
        id="daily_report_job",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info("🕐 Scheduler started (Test mode: every 5s)")

    logger.info("🤖 Bot starting… SUPERUSER_IDS={}", config.SUPERUSER_IDS)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        logger.info("🛑 Shutting down...")
        scheduler.shutdown(wait=False)
        await stop_pdf_delivery_workers(pdf_queue_tasks, pdf_queue_stop)
        await dp.storage.close()
        await resources.shutdown_resources()
        await bot.session.close()
        logger.info("✅ Bot stopped gracefully.")


if __name__ == "__main__":
    asyncio.run(main())
