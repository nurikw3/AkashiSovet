from __future__ import annotations

from io import BytesIO
from time import perf_counter

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, Message

from bot.logger import logger
from stdlib.services import application_service


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
            message = await bot.send_document(
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
    message = await bot.send_document(
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
