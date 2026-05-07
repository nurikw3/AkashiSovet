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
from stdlib.template import get_template

router = Router()


def _load_attachments(raw_att) -> list[dict]:
    if not raw_att:
        return []
    if isinstance(raw_att, str):
        try:
            val = json.loads(raw_att)
        except Exception:
            return []
    elif isinstance(raw_att, list):
        val = raw_att
    else:
        return []
    return [x for x in val if isinstance(x, dict)]


def _attachment_name(att: dict, idx: int) -> str:
    return str(att.get("name") or att.get("file_name") or f"Файл {idx + 1}")


def _files_keyboard_for(attachments: list[dict]):
    names = [_attachment_name(att, i) for i, att in enumerate(attachments)]
    return kb.files_keyboard(names)


@router.message(BotStates.FILLING, F.document | F.photo)
async def handle_file(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("current_block") != "files":
        return

    app = await application_service.get_application_record(data["app_id"])
    if not app:
        return

    raw_att = app.get("attachments")
    attachments = _load_attachments(raw_att)

    if not s3.is_s3_configured():
        await message.answer(
            "❌ Загрузка файлов недоступна: не настроено объектное хранилище (S3). "
            "Обратитесь к администратору.",
            reply_markup=_files_keyboard_for(attachments),
        )
        return

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
            reply_markup=_files_keyboard_for(attachments),
        )
        return
    except Exception as e:
        logger.exception("Attachment upload failed | app_id={}", app_id)
        await message.answer(
            "❌ Ошибка при загрузке файла. Попробуйте ещё раз.",
            reply_markup=_files_keyboard_for(attachments),
        )
        return

    await application_service.save_attachments_payload(
        app_id, attachments, user_id=user_id
    )
    logger.info("File attached to S3 | app_id={} total={}", app_id, len(attachments))

    await message.answer(
        f"✅ Файл принят. Всего приложений: {len(attachments)}",
        reply_markup=_files_keyboard_for(attachments),
    )


@router.callback_query(BotStates.FILLING, F.data.startswith("files_del_"))
async def on_file_delete(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("current_block") != "files":
        await callback.answer("Удаление доступно только в режиме файлов.", show_alert=True)
        return

    app_id = data.get("app_id")
    if not app_id:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return
    app = await application_service.get_application_record(app_id)
    if not app:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    try:
        del_idx = int(callback.data.rsplit("_", 1)[1])
    except Exception:
        await callback.answer("Некорректная кнопка.", show_alert=True)
        return

    attachments = _load_attachments(app.get("attachments"))
    if del_idx < 0 or del_idx >= len(attachments):
        await callback.answer("Файл уже удалён или список устарел.", show_alert=True)
        return

    removed = attachments.pop(del_idx)
    await application_service.save_attachments_payload(
        app_id, attachments, user_id=app.get("user_id")
    )
    await callback.answer("Файл удалён.")
    await callback.message.answer(
        f"🗑 Удалён файл: {_attachment_name(removed, del_idx)}\n"
        f"Осталось приложений: {len(attachments)}",
        reply_markup=_files_keyboard_for(attachments),
    )


@router.callback_query(BotStates.FILLING, F.data.in_({"files_done", "files_skip"}))
async def on_files_done(callback: CallbackQuery, state: FSMContext):

    await callback.answer()
    data = await state.get_data()
    app_id = data["app_id"]

    if data.get("returning_to") == "rework":
        await state.set_state(BotStates.REWORK)
        await state.update_data(returning_to=None, mode="input")
        tpl = await get_template()
        await callback.message.answer(
            "Файлы обновлены. Выберите блок для правки или отправьте заявку повторно:",
            reply_markup=kb.rework_keyboard(tpl, app_id),
        )
        return

    await state.set_state(BotStates.REVIEW)
    if data.get("returning_to") == "review":
        await state.update_data(returning_to=None)
    await send_review_screen(callback, app_id)
