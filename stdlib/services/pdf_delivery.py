from __future__ import annotations

import asyncio
import random
from io import BytesIO
from time import perf_counter

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import BufferedInputFile, Message

from bot.config import config
from bot.logger import logger
from stdlib.services import application_service

_SEND_DOCUMENT_SEMAPHORE = asyncio.Semaphore(
    max(1, config.TG_SEND_DOCUMENT_MAX_CONCURRENCY)
)


async def _send_document_throttled(*, bot: Bot, **kwargs) -> Message:
    """Отправка документа с ограничением параллелизма и ретраями на TelegramRetryAfter."""
    max_retries = max(1, int(config.TG_SEND_DOCUMENT_MAX_RETRIES))
    max_backoff = max(0.1, float(config.TG_SEND_DOCUMENT_MAX_BACKOFF_SEC))
    jitter_sec = max(0.0, float(config.TG_SEND_DOCUMENT_JITTER_SEC))

    attempt = 0
    while True:
        attempt += 1
        try:
            async with _SEND_DOCUMENT_SEMAPHORE:
                return await bot.send_document(**kwargs)
        except TelegramRetryAfter as exc:
            retry_after = float(getattr(exc, "retry_after", 1.0) or 1.0)
            wait_sec = min(max_backoff, max(0.1, retry_after))
            if jitter_sec > 0:
                wait_sec += random.uniform(0.0, jitter_sec)
            if attempt >= max_retries:
                logger.warning(
                    "PDF send rate-limited; retries exhausted | attempts={} wait_sec={:.2f}",
                    attempt,
                    wait_sec,
                )
                raise
            logger.warning(
                "PDF send rate-limited; retrying | attempt={}/{} wait_sec={:.2f}",
                attempt,
                max_retries,
                wait_sec,
            )
            await asyncio.sleep(wait_sec)


async def send_pdf_with_cache(
    *,
    bot: Bot,
    chat_id: int,
    app_id: int,
    pdf_file_id: str | None,
    pdf_buffer: BytesIO,
    filename: str,
    caption: str,
    reply_markup: object | None = None,
) -> Message:
    if pdf_file_id:
        try:
            started_at = perf_counter()
            message = await _send_document_throttled(
                bot=bot,
                chat_id=chat_id,
                document=pdf_file_id,
                caption=caption,
                reply_markup=reply_markup,
            )
            logger.info(
                "PDF send via file_id | app_id={} chat_id={} send_ms={:.0f}",
                app_id,
                chat_id,
                (perf_counter() - started_at) * 1000,
            )
            return message
        except TelegramBadRequest as exc:
            logger.warning(
                "PDF file_id send failed, fallback to bytes | app_id={} chat_id={} err={}",
                app_id,
                chat_id,
                exc,
            )
            await application_service.clear_pdf_reference(app_id)

    payload = pdf_buffer.getvalue()
    started_at = perf_counter()
    message = await _send_document_throttled(
        bot=bot,
        chat_id=chat_id,
        document=BufferedInputFile(payload, filename=filename),
        caption=caption,
        reply_markup=reply_markup,
    )
    send_ms = (perf_counter() - started_at) * 1000
    if message.document and message.document.file_id:
        await application_service.update_submission_pdf_reference(
            app_id, message.document.file_id
        )
    logger.info(
        "PDF send via bytes | app_id={} chat_id={} size_bytes={} size_kb={:.1f} send_ms={:.0f} stored_file_id={}",
        app_id,
        chat_id,
        len(payload),
        len(payload) / 1024,
        send_ms,
        bool(message.document and message.document.file_id),
    )
    return message
