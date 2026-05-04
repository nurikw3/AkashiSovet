# stdlib/handlers/user/review.py
from datetime import datetime
from html import escape

import stdlib.db as db
import stdlib.keyboards as kb
from stdlib.services import application_service
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from bot.logger import logger
from stdlib.handlers.states import BotStates
from stdlib.pdf import get_app_pdf_buffer, generate_pdf_filename
from stdlib.summary_format import (
    build_review_text_snapshot,
    chunk_plain_text,
    format_blocks_plain_copy,
)
from stdlib.template import get_template

router = Router()


async def send_review_screen(message: Message | CallbackQuery, app_id: int):
    app = await application_service.get_application_record(app_id)
    if not app:
        return
    user_id = app["user_id"]
    tpl = await get_template()

    # Сначала пробуем получить PDF-буфер через общую функцию
    try:
        pdf_buf = await get_app_pdf_buffer(app_id)

        # Достаем данные для правильного имени файла
        full_name = await db.get_user_full_name(user_id)
        position = await db.get_user_position(user_id)
        created_at = app.get("created_at", datetime.now())

        custom_filename = generate_pdf_filename(full_name, position, created_at)

        # Отправляем документ
        msg_func = (
            message.answer_document
            if isinstance(message, Message)
            else message.message.answer_document
        )

        await msg_func(
            document=BufferedInputFile(
                pdf_buf.getvalue(),
                filename=custom_filename,
            ),
            caption="📝 Проверьте PDF и текст ниже перед отправкой.",
            reply_markup=kb.review_keyboard(tpl),
        )
        app_model = await application_service.get_application(app_id)
        if app_model:
            plain = format_blocks_plain_copy(app_model.blocks, tpl)
            for idx, part in enumerate(chunk_plain_text(plain)):
                if idx == 0:
                    snap = build_review_text_snapshot(part)
                else:
                    snap = (
                        "… <i>продолжение текста</i>\n\n"
                        f"<pre>{escape(part)}</pre>"
                    )
                send_fn = (
                    message.answer
                    if isinstance(message, Message)
                    else message.message.answer
                )
                await send_fn(snap, parse_mode="HTML")
        return  # ВАЖНО: Выходим, чтобы не отправлять текстовый фоллбек!

    except Exception as e:
        logger.warning("PDF fallback: {}", e)
        # Если что-то пошло не так - падаем на старый текстовый метод

    # --- ФОЛЛБЕК: только текст (PDF недоступен) — тот же plain-формат, что и в других шагах ---
    app_model = await application_service.get_application(app_id)
    blocks = app_model.blocks if app_model else {}
    plain = format_blocks_plain_copy(blocks, tpl)

    raw_att = app.get("attachments")
    try:
        attachments = (
            json.loads(raw_att.replace("'", '"'))
            if isinstance(raw_att, str)
            else raw_att or []
        )
    except Exception:
        attachments = []

    msg_func = (
        message.answer if isinstance(message, Message) else message.message.answer
    )

    parts_fb = chunk_plain_text(plain)
    foot = f"<i>Приложений в заявке: {len(attachments)}</i>"
    for idx, p in enumerate(parts_fb):
        if idx == 0:
            body = (
                "📝 <b>Проверьте заявку</b> (PDF временно недоступен).\n\n"
                f"<pre>{escape(p)}</pre>\n\n"
                f"{foot}"
            )
        else:
            body = (
                "… <i>продолжение текста заявки</i>\n\n"
                f"<pre>{escape(p)}</pre>"
            )
        await msg_func(
            body,
            parse_mode="HTML",
            reply_markup=kb.review_keyboard(tpl) if idx == 0 else None,
            disable_web_page_preview=True,
        )


@router.callback_query(BotStates.REVIEW, F.data.startswith("review_edit_"))
async def on_review_edit(callback: CallbackQuery, state: FSMContext):
    block_num = int(callback.data.split("_")[2])
    await state.update_data(
        current_block=block_num, mode="input", returning_to="review"
    )
    await state.set_state(BotStates.FILLING)

    tpl = await get_template()
    try:
        b = tpl.get_block(block_num)
        title = b.title
    except ValueError:
        title = f"блок {block_num}"

    await callback.message.answer(
        f"<b>Редактирование: Блок {block_num} — {title}</b>\n\nВведите новый текст для этого блока:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(BotStates.REVIEW, F.data == "review_files")
async def on_review_files(callback: CallbackQuery, state: FSMContext):
    await state.update_data(current_block="files", returning_to="review")
    await state.set_state(BotStates.FILLING)
    await callback.message.answer(
        "Прикрепите дополнительные файлы. Нажмите <b>Готово</b>, когда закончите.",
        parse_mode="HTML",
        reply_markup=kb.files_keyboard(),
    )
    await callback.answer()


@router.callback_query(BotStates.REVIEW, F.data == "review_submit")
async def on_review_submit(callback: CallbackQuery, state: FSMContext, bot: Bot):
    from stdlib.handlers.user.finalize import finalize_and_notify

    await callback.answer()
    data = await state.get_data()
    await finalize_and_notify(callback, state, data["app_id"], bot)
