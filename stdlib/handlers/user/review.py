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
from stdlib.telegram_ui import render_nav_screen
from stdlib.template import get_template

router = Router()


async def send_review_screen(
    message: Message | CallbackQuery,
    state: FSMContext,
    app_id: int,
    *,
    force_new: bool = False,
):
    app = await application_service.get_application_record(app_id)
    if not app:
        return
    user_id = app["user_id"]
    tpl = await get_template()

    send_fn = (
        message.answer if isinstance(message, Message) else message.message.answer
    )
    progress_message = await send_fn("⏳ Генерация PDF...")

    try:
        t0 = perf_counter()
        pdf_buf = await get_app_pdf_buffer(app_id)
        t_pdf = (perf_counter() - t0) * 1000

        full_name = await db.get_user_full_name(user_id)
        position = await db.get_user_position(user_id)
        created_at = app.get("created_at") or now_app()

        custom_filename = resolve_application_pdf_filename(
            app,
            full_name=full_name,
            position=position,
            dt=created_at,
        )

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
        return

    except Exception as e:
        logger.warning("PDF fallback: {}", e)
        try:
            await progress_message.delete()
        except Exception:
            pass

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
    chunks = list(
        chunk_blocks_summary_html(
            tpl,
            blocks,
            INTRO_FALLBACK_NO_PDF_HTML,
            attachments_footer=foot,
        )
    )
    if not chunks:
        return

    await render_nav_screen(
        message,
        state,
        chunks[0],
        kb.review_keyboard(tpl),
        parse_mode="HTML",
        force_new=force_new,
    )
    if len(chunks) > 1:
        send_fn = (
            message.answer if isinstance(message, Message) else message.message.answer
        )
        for html in chunks[1:]:
            await send_fn(html, parse_mode="HTML", disable_web_page_preview=True)


@router.callback_query(BotStates.REVIEW, F.data.startswith("review_edit_"))
async def on_review_edit(callback: CallbackQuery, state: FSMContext):
    from stdlib.handlers.user.filling import send_block_input_screen

    block_num = int(callback.data.split("_")[2])
    await state.update_data(returning_to="review")
    await state.set_state(BotStates.FILLING)
    await callback.answer()
    await send_block_input_screen(callback, state, block_num, style="review_edit")


@router.callback_query(BotStates.REVIEW, F.data == "review_files")
async def on_review_files(callback: CallbackQuery, state: FSMContext):
    from stdlib.handlers.user.files import send_files_screen

    data = await state.get_data()
    await callback.answer()
    await send_files_screen(callback, state, data["app_id"], returning_to="review")


@router.callback_query(BotStates.REVIEW, F.data == "review_back")
async def on_review_back(callback: CallbackQuery, state: FSMContext):
    from stdlib.handlers.user.files import send_files_screen

    data = await state.get_data()
    await callback.answer()
    await send_files_screen(callback, state, data["app_id"], force_new=True)


@router.callback_query(BotStates.REVIEW, F.data == "review_submit")
async def on_review_submit(callback: CallbackQuery, state: FSMContext, bot: Bot):
    from stdlib.handlers.user.finalize import finalize_and_notify

    await callback.answer()
    data = await state.get_data()
    await finalize_and_notify(callback, state, data["app_id"], bot)
