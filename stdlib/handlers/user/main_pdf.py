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
from stdlib.document import invalidate_docx_delivery_cache
from stdlib.services import application_service, file_service
from stdlib.telegram_ui import edit_nav_anchor

router = Router()

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PDF_MIME = "application/pdf"


def _is_main_document(doc) -> bool:
    mime = (doc.mime_type or "").lower()
    name = (doc.file_name or "").lower()
    if mime == _PDF_MIME or name.endswith(".pdf"):
        return True
    if mime == _DOCX_MIME or name.endswith(".docx"):
        return True
    return False


def _safe_document_name(name: str | None) -> str:
    candidate = PurePosixPath((name or "").strip()).name
    if not candidate:
        return "application.docx"
    lower = candidate.lower()
    if lower.endswith(".pdf") or lower.endswith(".docx"):
        return candidate
    return f"{candidate}.docx"


@router.message(BotStates.WAITING_MAIN_PDF, F.document)
async def on_main_pdf_upload(message: Message, state: FSMContext):
    data = await state.get_data()
    app_id = data.get("app_id")
    if not app_id:
        await message.answer("Черновик не найден. Запустите /start заново.")
        await state.clear()
        return

    doc = message.document
    if not _is_main_document(doc):
        await edit_nav_anchor(
            message.bot,
            state,
            "Нужен PDF или DOCX. Отправьте документ с расширением .pdf или .docx.",
            kb.main_pdf_keyboard(),
            parse_mode="HTML",
            fallback_chat_id=message.chat.id,
        )
        return

    if not s3.is_s3_configured():
        await message.answer(
            "❌ Загрузка документа недоступна: не настроено объектное хранилище (S3)."
        )
        return

    app = await application_service.get_application_record(app_id)
    if not app:
        await message.answer("Черновик не найден. Запустите /start заново.")
        await state.clear()
        return

    filename = _safe_document_name(doc.file_name)
    try:
        dl = await message.bot.download(doc)
        file_bytes = dl.read()
        new_key, display_name = await file_service.upload_main_pdf(
            message.from_user.id, app_id, file_bytes, filename
        )
        old_key = app.get("main_pdf_s3_key")
        await application_service.set_main_pdf(app_id, new_key, display_name)
        await invalidate_docx_delivery_cache(app_id)
        if old_key and old_key != new_key:
            try:
                await s3.delete_object(old_key, s3.BUCKET_PDF)
            except Exception:
                logger.warning(
                    "Failed to cleanup previous main document | app_id={} key={}",
                    app_id,
                    old_key,
                )
    except Exception:
        logger.exception("Main document upload failed | app_id={}", app_id)
        await message.answer("❌ Не удалось сохранить документ. Попробуйте ещё раз.")
        return

    await send_files_screen(
        message,
        state,
        app_id,
        message_text=(
            "✅ Основной документ сохранён.\n\n"
            "Теперь можете прикрепить дополнительные приложения или нажать «Пропустить»."
        ),
    )


@router.message(BotStates.WAITING_MAIN_PDF)
async def on_main_pdf_invalid_message(message: Message, state: FSMContext):
    await edit_nav_anchor(
        message.bot,
        state,
        "Отправьте PDF или DOCX документом (не фото и не текст).",
        kb.main_pdf_keyboard(),
        parse_mode="HTML",
        fallback_chat_id=message.chat.id,
    )
