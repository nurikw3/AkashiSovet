from __future__ import annotations

import asyncio
import json
from time import perf_counter

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from bot.config import config
from bot.logger import logger
import stdlib.db as db
import stdlib.redis_client as redis_client_module
from stdlib.pdf import get_app_pdf_buffer, generate_pdf_filename
from stdlib.services import application_service
from stdlib.services.pdf_delivery import send_pdf_with_cache
from stdlib.timezone_util import now_app


def _queue_key() -> str:
    return config.TG_PDF_QUEUE_KEY


async def enqueue_pdf_delivery(
    *,
    app_id: int,
    chat_id: int,
    caption: str,
    filename: str | None = None,
) -> bool:
    """Ставит задачу отправки PDF в Redis-очередь."""
    r = redis_client_module.redis_client
    if not r:
        logger.warning("PDF queue unavailable (Redis not initialized), fallback to sync send")
        return False

    payload = {
        "app_id": app_id,
        "chat_id": chat_id,
        "caption": caption,
        "filename": filename,
    }
    await r.lpush(_queue_key(), json.dumps(payload, ensure_ascii=False))
    return True


async def _process_pdf_delivery_task(bot: Bot, payload: dict) -> None:
    app_id = int(payload["app_id"])
    chat_id = int(payload["chat_id"])
    caption = str(payload.get("caption") or "📄 PDF")
    filename = payload.get("filename")

    app = await application_service.get_application_record(app_id)
    if not app:
        logger.warning("PDF queue task dropped: app {} not found", app_id)
        return

    started = perf_counter()
    pdf_buf = await get_app_pdf_buffer(app_id)
    t_pdf_ms = (perf_counter() - started) * 1000

    if not filename:
        full_name, position = await asyncio.gather(
            db.get_user_full_name(app["user_id"]),
            db.get_user_position(app["user_id"]),
        )
        created_at = app.get("created_at") or now_app()
        filename = generate_pdf_filename(full_name, position, created_at)

    try:
        await send_pdf_with_cache(
            bot=bot,
            chat_id=chat_id,
            app_id=app_id,
            pdf_file_id=app.get("pdf_file_id"),
            pdf_buffer=pdf_buf,
            filename=filename,
            caption=caption,
        )
        logger.info(
            "PDF queue task done | app_id={} chat_id={} pdf_ms={:.0f}",
            app_id,
            chat_id,
            t_pdf_ms,
        )
    except TelegramBadRequest as exc:
        if "file is too big" in str(exc).lower():
            logger.warning("PDF queue: file too big | app_id={} err={}", app_id, exc)
            await bot.send_message(
                chat_id=chat_id,
                text="⚠️ PDF слишком большой для отправки через Telegram.",
            )
            return
        raise


async def _pdf_delivery_worker(bot: Bot, stop_event: asyncio.Event, worker_id: int) -> None:
    logger.info("PDF queue worker #{} started", worker_id)
    while not stop_event.is_set():
        r = redis_client_module.redis_client
        if not r:
            await asyncio.sleep(1.0)
            continue
        try:
            item = await r.brpop(_queue_key(), timeout=2)
            if not item:
                continue
            _, raw_payload = item
            payload = json.loads(raw_payload)
            await _process_pdf_delivery_task(bot, payload)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("PDF queue worker #{} failed task: {}", worker_id, exc)

    logger.info("PDF queue worker #{} stopped", worker_id)


def start_pdf_delivery_workers(bot: Bot) -> tuple[list[asyncio.Task], asyncio.Event]:
    workers = max(1, int(config.TG_PDF_QUEUE_WORKERS))
    stop_event = asyncio.Event()
    tasks = [
        asyncio.create_task(
            _pdf_delivery_worker(bot, stop_event, idx),
            name=f"pdf-delivery-worker-{idx}",
        )
        for idx in range(1, workers + 1)
    ]
    logger.info("PDF queue workers started: {}", workers)
    return tasks, stop_event


async def stop_pdf_delivery_workers(tasks: list[asyncio.Task], stop_event: asyncio.Event) -> None:
    stop_event.set()
    if not tasks:
        return
    await asyncio.gather(*tasks, return_exceptions=True)
