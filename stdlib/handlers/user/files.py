import json
import mimetypes
from html import escape

import stdlib.keyboards as kb
import stdlib.s3 as s3
from stdlib.pdf import invalidate_pdf_delivery_cache
from stdlib.services import application_service, file_service
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from bot.logger import logger
from stdlib.handlers.states import BotStates
from stdlib.handlers.user.review import send_review_screen
from stdlib.telegram_ui import edit_nav_anchor, render_nav_screen
from stdlib.template import get_template

router = Router()

ATTACHMENT_NAME_MAX_LEN = 200

DEFAULT_FILES_TEXT = (
    "Прикрепите дополнительные файлы.\n"
    "Для каждого файла можно нажать <b>✏️ Название</b> и указать, "
    "как документ должен называться в пояснительной записке "
    "(в PDF расширение файла не отображается).\n"
    "Нажмите <b>Готово</b>, когда закончите."
)

RENAME_ATTACHMENT_PROMPT = (
    "Введите название документа для пояснительной записки "
    "(как в разделе «Приложения»). Расширение файла в PDF не отобразится."
)


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


def _validate_attachment_display_name(raw: str) -> str | None:
    """Возвращает нормализованное имя или None при ошибке валидации."""
    name = (raw or "").replace("\n", " ").replace("\r", " ").strip()
    if not name:
        return None
    if len(name) > ATTACHMENT_NAME_MAX_LEN:
        return None
    return name


async def _clear_rename_mode(state: FSMContext) -> None:
    await state.update_data(mode="input", renaming_attachment_idx=None)


async def apply_attachment_rename(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    app_id = data.get("app_id")
    idx = data.get("renaming_attachment_idx")
    if not app_id or idx is None:
        await _clear_rename_mode(state)
        return

    new_name = _validate_attachment_display_name(message.text or "")
    if not new_name:
        await message.answer(
            f"Укажите непустое название (до {ATTACHMENT_NAME_MAX_LEN} символов, без переносов строк)."
        )
        return

    app = await application_service.get_application_record(app_id)
    if not app:
        await message.answer("Заявка не найдена.")
        await _clear_rename_mode(state)
        return

    attachments = _load_attachments(app.get("attachments"))
    if idx < 0 or idx >= len(attachments):
        await message.answer("Файл уже удалён или список устарел.")
        await _clear_rename_mode(state)
        return

    attachments[idx]["name"] = new_name
    await application_service.save_attachments_payload(
        app_id, attachments, user_id=app.get("user_id")
    )
    await _clear_rename_mode(state)
    await refresh_files_nav(
        message.bot,
        state,
        app_id,
        message.chat.id,
        status_line="✅ Название обновлено.",
    )


def _files_markup_for_app(raw_app: dict, attachments: list[dict]) -> InlineKeyboardMarkup:
    names = [_attachment_name(att, i) for i, att in enumerate(attachments)]
    return kb.files_keyboard_with_main_pdf(
        names,
        has_main_pdf=bool(raw_app.get("main_pdf_s3_key")),
    )


def _files_markup_for_app_id(app_record: dict | None, names: list[str]) -> InlineKeyboardMarkup:
    has_main_pdf = bool(app_record and app_record.get("main_pdf_s3_key"))
    if has_main_pdf:
        return kb.files_keyboard_with_main_pdf(names, has_main_pdf=True)
    return kb.files_keyboard(names)


async def _build_files_screen(
    app_id: int,
    *,
    status_line: str | None = None,
    message_text: str | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    app_record = await application_service.get_application_record(app_id)
    app_model = await application_service.get_application(app_id)
    attachments = _load_attachments(app_record.get("attachments") if app_record else None)
    names = [_attachment_name(att, i) for i, att in enumerate(attachments)]
    if app_model and app_model.attachments:
        names = [att.name for att in app_model.attachments]

    text = message_text or DEFAULT_FILES_TEXT
    if status_line:
        text = f"{status_line}\n\n{text}"

    markup = _files_markup_for_app_id(app_record, names)
    return text, markup


async def refresh_files_nav(
    bot,
    state: FSMContext,
    app_id: int,
    chat_id: int,
    *,
    status_line: str | None = None,
) -> None:
    text, markup = await _build_files_screen(app_id, status_line=status_line)
    await edit_nav_anchor(
        bot,
        state,
        text,
        markup,
        parse_mode="HTML",
        fallback_chat_id=chat_id,
    )


async def send_files_screen(
    target: Message | CallbackQuery,
    state: FSMContext,
    app_id: int,
    *,
    returning_to: str | None = None,
    message_text: str | None = None,
    force_new: bool = False,
) -> None:
    update_data: dict = {
        "app_id": app_id,
        "current_block": "files",
        "mode": "input",
        "returning_to": returning_to,
    }
    await state.set_state(BotStates.FILLING)
    await state.update_data(**update_data)

    text, markup = await _build_files_screen(app_id, message_text=message_text)
    await render_nav_screen(
        target, state, text, markup, parse_mode="HTML", force_new=force_new
    )


@router.message(BotStates.FILLING, F.document | F.photo)
async def handle_file(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("current_block") != "files":
        return
    if data.get("mode") == "rename_attachment":
        await message.answer(
            "Сначала введите название документа или нажмите «Назад» на экране приложений."
        )
        return

    app = await application_service.get_application_record(data["app_id"])
    if not app:
        return

    raw_att = app.get("attachments")
    attachments = _load_attachments(raw_att)

    if not s3.is_s3_configured():
        await refresh_files_nav(
            message.bot,
            state,
            data["app_id"],
            message.chat.id,
            status_line=(
                "❌ Загрузка файлов недоступна: не настроено объектное хранилище (S3). "
                "Обратитесь к администратору."
            ),
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
        await refresh_files_nav(
            message.bot,
            state,
            app_id,
            message.chat.id,
            status_line="❌ Не удалось сохранить файл в хранилище. Попробуйте позже.",
        )
        return
    except Exception:
        logger.exception("Attachment upload failed | app_id={}", app_id)
        await refresh_files_nav(
            message.bot,
            state,
            app_id,
            message.chat.id,
            status_line="❌ Ошибка при загрузке файла. Попробуйте ещё раз.",
        )
        return

    await application_service.save_attachments_payload(
        app_id, attachments, user_id=user_id
    )
    logger.info("File attached to S3 | app_id={} total={}", app_id, len(attachments))

    await refresh_files_nav(
        message.bot,
        state,
        app_id,
        message.chat.id,
        status_line=f"✅ Файл принят. Всего приложений: {len(attachments)}",
    )


@router.callback_query(BotStates.FILLING, F.data.startswith("files_rename_"))
async def on_file_rename_start(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("current_block") != "files":
        await callback.answer("Доступно только на шаге приложений.", show_alert=True)
        return

    app_id = data.get("app_id")
    if not app_id:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    try:
        rename_idx = int(callback.data.rsplit("_", 1)[1])
    except Exception:
        await callback.answer("Некорректная кнопка.", show_alert=True)
        return

    app = await application_service.get_application_record(app_id)
    if not app:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    attachments = _load_attachments(app.get("attachments"))
    if rename_idx < 0 or rename_idx >= len(attachments):
        await callback.answer("Файл уже удалён или список устарел.", show_alert=True)
        return

    await callback.answer()
    await state.update_data(
        mode="rename_attachment",
        renaming_attachment_idx=rename_idx,
    )
    current = escape(_attachment_name(attachments[rename_idx], rename_idx))
    await render_nav_screen(
        callback,
        state,
        f"{RENAME_ATTACHMENT_PROMPT}\n\nТекущее название: <i>{current}</i>",
        _files_markup_for_app_id(app, [_attachment_name(a, i) for i, a in enumerate(attachments)]),
        parse_mode="HTML",
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
    await _clear_rename_mode(state)
    await callback.answer("Файл удалён.")
    text, markup = await _build_files_screen(
        app_id,
        status_line=(
            f"🗑 Удалён файл: {_attachment_name(removed, del_idx)}\n"
            f"Осталось приложений: {len(attachments)}"
        ),
    )
    await render_nav_screen(callback, state, text, markup, parse_mode="HTML")


@router.callback_query(BotStates.FILLING, F.data == "main_pdf_replace")
async def on_main_pdf_replace(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("current_block") != "files":
        await callback.answer("Опция доступна на шаге приложений.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(BotStates.WAITING_MAIN_PDF)
    await render_nav_screen(
        callback,
        state,
        "📄 Отправьте новый PDF, чтобы заменить текущий основной документ.",
        kb.main_pdf_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(BotStates.FILLING, F.data == "main_pdf_delete")
async def on_main_pdf_delete(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("current_block") != "files":
        await callback.answer("Опция доступна на шаге приложений.", show_alert=True)
        return

    app_id = data.get("app_id")
    if not app_id:
        await callback.answer("Черновик не найден.", show_alert=True)
        return

    app = await application_service.get_application_record(app_id)
    if not app or not app.get("main_pdf_s3_key"):
        await callback.answer("Основной PDF уже удалён.", show_alert=True)
        return

    old_key = app.get("main_pdf_s3_key")
    await application_service.clear_main_pdf(app_id)
    await invalidate_pdf_delivery_cache(app_id)
    if old_key and s3.is_s3_configured():
        try:
            await s3.delete_object(old_key, s3.BUCKET_PDF)
        except Exception:
            logger.warning(
                "Failed to delete uploaded main PDF | app_id={} key={}", app_id, old_key
            )

    await callback.answer("Основной PDF удалён.")
    text, markup = await _build_files_screen(
        app_id,
        status_line=(
            "🗑 Основной PDF удалён. Можно добавить новый PDF или продолжить с приложениями."
        ),
    )
    await render_nav_screen(callback, state, text, markup, parse_mode="HTML")


@router.callback_query(BotStates.FILLING, F.data.in_({"files_done", "files_skip"}))
async def on_files_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("mode") == "rename_attachment":
        await callback.answer(
            "Сначала введите название или нажмите «Назад».", show_alert=True
        )
        return
    await callback.answer()
    app_id = data["app_id"]
    await _clear_rename_mode(state)

    if data.get("returning_to") == "rework":
        await state.set_state(BotStates.REWORK)
        await state.update_data(returning_to=None, mode="input", rework_screen="menu")
        from stdlib.handlers.user.rework import send_rework_menu

        await send_rework_menu(
            callback,
            state,
            app_id,
            message_text="Файлы обновлены. Выберите блок для правки или отправьте заявку повторно:",
        )
        return

    await state.set_state(BotStates.REVIEW)
    if data.get("returning_to") == "review":
        await state.update_data(returning_to=None)
    await send_review_screen(callback, state, app_id, force_new=True)


@router.callback_query(BotStates.FILLING, F.data == "files_back")
async def on_files_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("current_block") != "files":
        await callback.answer(
            "Эта кнопка устарела — смотрите последнее сообщение бота.",
            show_alert=True,
        )
        return

    if data.get("mode") == "rename_attachment":
        await _clear_rename_mode(state)

    await callback.answer()
    app_id = data["app_id"]
    returning_to = data.get("returning_to")

    if returning_to == "review":
        await state.set_state(BotStates.REVIEW)
        await state.update_data(returning_to=None)
        await send_review_screen(callback, state, app_id, force_new=True)
        return

    if returning_to == "rework":
        from stdlib.handlers.user.rework import send_rework_menu

        await state.set_state(BotStates.REWORK)
        await state.update_data(returning_to=None, rework_screen="menu")
        await send_rework_menu(callback, state, app_id)
        return

    from stdlib.handlers.user.filling import send_block_input_screen

    tpl = await get_template()
    await send_block_input_screen(callback, state, tpl.last_block_id, style="saved")

