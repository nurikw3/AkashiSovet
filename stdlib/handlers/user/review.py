# stdlib/handlers/user/review.py
import json
from time import perf_counter

import stdlib.db as db
import stdlib.keyboards as kb
from stdlib.services import application_service
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from bot.logger import logger
from stdlib.handlers.states import BotStates
from stdlib.pdf import get_app_pdf_buffer, resolve_application_pdf_filename
from stdlib.services.pdf_delivery import send_pdf_with_cache
from stdlib.timezone_util import now_app
from stdlib.telegram_summary import INTRO_FALLBACK_NO_PDF_HTML, chunk_blocks_summary_html
from stdlib.template import get_template

router = Router()


async def send_review_screen(message: Message | CallbackQuery, app_id: int):
    app = await application_service.get_application_record(app_id)
    if not app:
        return
    user_id = app["user_id"]
    tpl = await get_template()

    send_fn = (
        message.answer if isinstance(message, Message) else message.message.answer
    )
    progress_message = await send_fn("⏳ Генерация PDF...")

    # Сначала пробуем получить PDF-буфер через общую функцию
    try:
        t0 = perf_counter()
        pdf_buf = await get_app_pdf_buffer(app_id)
        t_pdf = (perf_counter() - t0) * 1000

        # Достаем данные для правильного имени файла
        full_name = await db.get_user_full_name(user_id)
        position = await db.get_user_position(user_id)
        created_at = app.get("created_at") or now_app()

        custom_filename = resolve_application_pdf_filename(
            app,
            full_name=full_name,
            position=position,
            dt=created_at,
        )

        # Отправляем документ
        t1 = perf_counter()
        target_message = message if isinstance(message, Message) else message.message
        await send_pdf_with_cache(
            bot=target_message.bot,
            chat_id=target_message.chat.id,
            app_id=app_id,
            pdf_file_id=app.get("pdf_file_id"),
            pdf_buffer=pdf_buf,
            filename=custom_filename,
            caption="📝 Проверьте PDF перед отправкой заявки.",
            reply_markup=kb.review_keyboard(tpl),
        )
        t_send = (perf_counter() - t1) * 1000
        logger.info(
            "Review PDF timings | app_id={} pdf_ms={:.0f} send_ms={:.0f}",
            app_id,
            t_pdf,
            t_send,
        )
        try:
            await progress_message.delete()
        except Exception:
            pass
        return  # ВАЖНО: Выходим, чтобы не отправлять текстовый фоллбек!

    except Exception as e:
        logger.warning("PDF fallback: {}", e)
        try:
            await progress_message.delete()
        except Exception:
            pass
        # Если что-то пошло не так — текстом тем же форматом, что и сводка к файлам

    # --- ФОЛЛБЕК: PDF недоступен ---
    app_model = await application_service.get_application(app_id)
    blocks = app_model.blocks if app_model else {}

    raw_att = app.get("attachments")
    try:
        attachments = (
            json.loads(raw_att.replace("'", '"'))
            if isinstance(raw_att, str)
            else raw_att or []
        )
    except Exception:
        attachments = []

    foot = f"<i>Приложений в заявке: {len(attachments)}</i>"
    for idx, html in enumerate(
        chunk_blocks_summary_html(
            tpl,
            blocks,
            INTRO_FALLBACK_NO_PDF_HTML,
            attachments_footer=foot,
        )
    ):
        await send_fn(
            html,
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
    data = await state.get_data()
    app = await application_service.get_application(data["app_id"])
    attachment_names = [att.name for att in (app.attachments or [])] if app else []
    await state.update_data(current_block="files", returning_to="review")
    await state.set_state(BotStates.FILLING)
    await callback.message.answer(
        "Прикрепите дополнительные файлы. Нажмите <b>Готово</b>, когда закончите.",
        parse_mode="HTML",
        reply_markup=kb.files_keyboard(attachment_names),
    )
    await callback.answer()


@router.callback_query(BotStates.REVIEW, F.data == "review_submit")
async def on_review_submit(callback: CallbackQuery, state: FSMContext, bot: Bot):
    from stdlib.handlers.user.finalize import finalize_and_notify

    await callback.answer()
    data = await state.get_data()
    await finalize_and_notify(callback, state, data["app_id"], bot)
