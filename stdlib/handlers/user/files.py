import json
import mimetypes

import stdlib.keyboards as kb
import stdlib.s3 as s3
from stdlib.services import application_service, file_service
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from bot.logger import logger
from stdlib.handlers.states import BotStates
from stdlib.handlers.user.review import send_review_screen

router = Router()


@router.message(BotStates.FILLING, F.document | F.photo)
async def handle_file(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("current_block") != "files":
        return

    app = await application_service.get_application_record(data["app_id"])
    if not app:
        return

    if not s3.is_s3_configured():
        await message.answer(
            "❌ Загрузка файлов недоступна: не настроено объектное хранилище (S3). "
            "Обратитесь к администратору.",
            reply_markup=kb.files_keyboard(),
        )
        return

    raw_att = app.get("attachments")
    attachments = json.loads(raw_att) if raw_att else []

    user_id = message.from_user.id
    app_id = data["app_id"]

    try:
        if message.document:
            doc = message.document
            display_name = (doc.file_name or "").strip()
            if not display_name:
                guessed = mimetypes.guess_extension(doc.mime_type or "") or ".bin"
                display_name = f"файл{guessed}"
            dl = await message.bot.download(doc)
            body = dl.read()
            content_type = doc.mime_type or "application/octet-stream"
        elif message.photo:
            display_name = f"фото_{len(attachments) + 1}.jpg"
            ph = message.photo[-1]
            dl = await message.bot.download(ph)
            body = dl.read()
            content_type = "image/jpeg"
        else:
            return

        att = await file_service.upload_attachment(
            user_id, app_id, body, display_name, content_type
        )
        attachments.append(att.model_dump(mode="json", exclude_none=True))
    except RuntimeError as e:
        logger.error("S3 upload failed | app_id={} err={}", app_id, e)
        await message.answer(
            "❌ Не удалось сохранить файл в хранилище. Попробуйте позже или обратитесь к администратору.",
            reply_markup=kb.files_keyboard(),
        )
        return
    except Exception as e:
        logger.exception("Attachment upload failed | app_id={}", app_id)
        await message.answer(
            "❌ Ошибка при загрузке файла. Попробуйте ещё раз.",
            reply_markup=kb.files_keyboard(),
        )
        return

    await application_service.save_attachments_payload(app_id, attachments)
    logger.info("File attached to S3 | app_id={} total={}", app_id, len(attachments))

    await message.answer(
        f"✅ Файл принят. Всего приложений: {len(attachments)}",
        reply_markup=kb.files_keyboard(),
    )


@router.callback_query(BotStates.FILLING, F.data.in_({"files_done", "files_skip"}))
async def on_files_done(callback: CallbackQuery, state: FSMContext):

    await callback.answer()
    data = await state.get_data()
    app_id = data["app_id"]

    await state.set_state(BotStates.REVIEW)
    if data.get("returning_to") == "review":
        await state.update_data(returning_to=None)
    await send_review_screen(callback, app_id)
