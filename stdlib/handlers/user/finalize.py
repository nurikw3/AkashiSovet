import json

import stdlib.db as db
import stdlib.keyboards as kb
from stdlib.services import application_service, file_service
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, BufferedInputFile
from bot.config import config
from bot.logger import logger
from stdlib.pdf import get_app_pdf_buffer, generate_pdf_filename
from stdlib.timezone_util import now_app


async def finalize_and_notify(
    callback: CallbackQuery,
    state: FSMContext,
    app_id: int,
    bot: Bot,
) -> None:
    data = await state.get_data()
    cleanup_ids = list(data.get("cleanup_bot_message_ids") or [])
    if callback.message:
        cleanup_ids.append(callback.message.message_id)

    app = await application_service.get_application_record(app_id)
    if not app:
        await state.clear()
        return

    user_id = callback.from_user.id
    full_name = await db.get_user_full_name(user_id)
    position = await db.get_user_position(user_id)
    signature = await db.get_user_signature(user_id)
    missing: list[str] = []
    if not full_name:
        missing.append("/register (ФИО)")
    if not position:
        missing.append("/position (должность)")
    if not signature:
        missing.append("/sign (подпись)")
    if missing:
        txt = (
            "❌ Нельзя отправить заявку: не заполнен профиль.\n\n"
            "Заполните обязательные данные:\n"
            + "\n".join(f"• {x}" for x in missing)
        )
        msg = await callback.message.answer(txt)
        cleanup_ids.append(msg.message_id)
        await state.update_data(cleanup_bot_message_ids=cleanup_ids[-120:])
        return

    blocks = json.loads(app.get("blocks") or "{}")

    raw_att = app.get("attachments")
    try:
        attachments = (
            json.loads(raw_att.replace("'", '"'))
            if isinstance(raw_att, str)
            else raw_att or []
        )
    except Exception:
        attachments = []

    # 1. Генерируем PDF через нашу общую функцию
    try:
        pdf_buffer = await get_app_pdf_buffer(app_id)
    except Exception as e:
        logger.error("PDF generation error for app_id={}: {}", app_id, e)
        text_fallback = (
            f"⚠️ <b>Новая заявка #{app_id}</b> (PDF не сгенерирован)\n\n"
            + "\n".join(f"<b>Блок {k}:</b> {v}" for k, v in blocks.items())
        )
        for su_id in config.SUPERUSER_IDS:
            await bot.send_message(su_id, text_fallback, parse_mode="HTML")

        await application_service.submit_to_review(app_id)
        err_msg = await callback.message.answer(
            "📤 Заявка отправлена (без PDF — техническая ошибка)."
        )
        cleanup_ids.append(err_msg.message_id)
        await state.set_state(None)
        await state.update_data(
            cleanup_bot_message_ids=cleanup_ids[-120:],
            cleanup_app_id=app_id,
        )
        return

    # 2. Переводим в pending (время подачи)
    await application_service.submit_to_review(app_id)

    # 3. Достаем данные и формируем красивое имя файла ОДИН раз
    created_at = app.get("created_at") or now_app()

    custom_filename = generate_pdf_filename(full_name, position, created_at)

    # 4. Отправляем копию пользователю
    try:
        await callback.message.answer_document(
            document=BufferedInputFile(
                pdf_buffer.getvalue(),
                filename=custom_filename,
            ),
            caption="📤 Заявка успешно сформирована и отправлена на согласование. Копия приложена выше.",
        )
    except TelegramBadRequest as e:
        if "file is too big" not in str(e).lower():
            raise
        logger.warning("User PDF too big for Telegram | app_id={} err={}", app_id, e)
        await callback.message.answer(
            "📤 Заявка отправлена на согласование.\n\n"
            "⚠️ Копию PDF не удалось отправить в чат: файл слишком большой для Telegram."
        )

    done_msg = await callback.message.answer(
        "Когда проверите, можно очистить служебные сообщения этой заявки:",
        reply_markup=kb.cleanup_chat_keyboard(app_id),
    )
    cleanup_ids.append(done_msg.message_id)

    # 5. Отправляем суперюзерам
    for su_id in config.SUPERUSER_IDS:
        try:
            msg = await bot.send_document(
                su_id,
                document=BufferedInputFile(
                    pdf_buffer.getvalue(),
                    filename=custom_filename,
                ),
                caption=(
                    f"📋 Новая заявка #{app_id} от @{callback.from_user.username or callback.from_user.id}\n"
                    f"📎 Приложений: {len(attachments)}"
                ),
                reply_markup=kb.approve_reject_keyboard(app_id),
            )

            # Сохраняем file_id отправленного PDF, чтобы не генерить его заново при скачивании
            await application_service.update_submission_pdf_reference(
                app_id, msg.document.file_id
            )

            # Пересылаем приложения: байты из S3 (раньше использовался только Telegram file_id)
            if attachments:
                await bot.send_message(su_id, "📁 Приложения к заявке:")
                for att in attachments:
                    if not isinstance(att, dict):
                        continue
                    file_name = att.get("name") or att.get("file_name") or "Приложение"
                    s3_key = att.get("s3_key")
                    if s3_key:
                        body = await file_service.download_attachment(s3_key)
                        if not body:
                            logger.warning(
                                "S3 attachment missing for superuser notify | app_id={} key={}",
                                app_id,
                                s3_key,
                            )
                            continue
                        await bot.send_document(
                            su_id,
                            document=BufferedInputFile(body, filename=file_name),
                            caption=file_name,
                        )
                    elif att.get("file_id"):
                        await bot.send_document(
                            su_id, document=att["file_id"], caption=file_name
                        )
                    else:
                        logger.warning(
                            "Attachment without s3_key/file_id, skip | app_id={} name={}",
                            app_id,
                            file_name,
                        )
        except Exception as e:
            logger.error(
                "Failed to notify superuser {} for app {}: {}", su_id, app_id, e
            )

    logger.info(
        "App {} submitted for review | attachments={}", app_id, len(attachments)
    )
    await state.set_state(None)
    await state.update_data(
        cleanup_bot_message_ids=cleanup_ids[-120:],
        cleanup_app_id=app_id,
    )
