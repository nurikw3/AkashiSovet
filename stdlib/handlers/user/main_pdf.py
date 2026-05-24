from __future__ import annotations

from pathlib import PurePosixPath

import stdlib.keyboards as kb
import stdlib.s3 as s3
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from bot.logger import logger
from stdlib.handlers.states import BotStates
from stdlib.handlers.user.files import send_files_screen
from stdlib.pdf import invalidate_pdf_delivery_cache
from stdlib.services import application_service, file_service
from stdlib.telegram_ui import edit_nav_anchor

router = Router()


def _is_pdf_document(doc) -> bool:
    mime_ok = (doc.mime_type or "").lower() == "application/pdf"
    name_ok = (doc.file_name or "").lower().endswith(".pdf")
    return mime_ok or name_ok


def _safe_pdf_name(name: str | None) -> str:
    candidate = PurePosixPath((name or "").strip()).name
    if not candidate:
        return "application.pdf"
    if not candidate.lower().endswith(".pdf"):
        return f"{candidate}.pdf"
    return candidate


@router.message(BotStates.WAITING_MAIN_PDF, F.document)
async def on_main_pdf_upload(message: Message, state: FSMContext):
    data = await state.get_data()
    app_id = data.get("app_id")
    if not app_id:
        await message.answer("Черновик не найден. Запустите /start заново.")
        await state.clear()
        return

    doc = message.document
    if not _is_pdf_document(doc):
        await edit_nav_anchor(
            message.bot,
            state,
            "Нужен именно PDF-файл. Отправьте документ с расширением .pdf.",
            kb.main_pdf_keyboard(),
            parse_mode="HTML",
            fallback_chat_id=message.chat.id,
        )
        return

    if not s3.is_s3_configured():
        await message.answer(
            "❌ Загрузка PDF недоступна: не настроено объектное хранилище (S3)."
        )
        return

    app = await application_service.get_application_record(app_id)
    if not app:
        await message.answer("Черновик не найден. Запустите /start заново.")
        await state.clear()
        return

    filename = _safe_pdf_name(doc.file_name)
    try:
        dl = await message.bot.download(doc)
        pdf_bytes = dl.read()
        new_key, display_name = await file_service.upload_main_pdf(
            message.from_user.id, app_id, pdf_bytes, filename
        )
        old_key = app.get("main_pdf_s3_key")
        await application_service.set_main_pdf(app_id, new_key, display_name)
        await invalidate_pdf_delivery_cache(app_id)
        if old_key and old_key != new_key:
            try:
                await s3.delete_object(old_key, s3.BUCKET_PDF)
            except Exception:
                logger.warning(
                    "Failed to cleanup previous main PDF | app_id={} key={}",
                    app_id,
                    old_key,
                )
    except Exception:
        logger.exception("Main PDF upload failed | app_id={}", app_id)
        await message.answer("❌ Не удалось сохранить PDF. Попробуйте ещё раз.")
        return

    await send_files_screen(
        message,
        state,
        app_id,
        message_text=(
            "✅ Основной PDF сохранён.\n\n"
            "Теперь можете прикрепить дополнительные приложения или нажать «Пропустить»."
        ),
    )


@router.message(BotStates.WAITING_MAIN_PDF)
async def on_main_pdf_invalid_message(message: Message, state: FSMContext):
    await edit_nav_anchor(
        message.bot,
        state,
        "Отправьте PDF-файл документом (не фото и не текст).",
        kb.main_pdf_keyboard(),
        parse_mode="HTML",
        fallback_chat_id=message.chat.id,
    )
