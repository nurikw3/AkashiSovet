# stdlib/handlers/user/review.py
import json
from datetime import datetime

import stdlib.db as db
import stdlib.keyboards as kb
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from bot.logger import logger
from stdlib.handlers.states import BotStates
from stdlib.intent import escape_markdown_v2
from stdlib.pdf import get_app_pdf_buffer, generate_pdf_filename
from stdlib.template import get_template

router = Router()


async def send_review_screen(message: Message | CallbackQuery, app_id: int):
    app = await db.get_app(app_id)
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
            caption="📝 *Проверьте вашу заявку перед отправкой:*",
            parse_mode="MarkdownV2",
            reply_markup=kb.review_keyboard(tpl),
        )
        return  # ВАЖНО: Выходим, чтобы не отправлять текстовый фоллбек!

    except Exception as e:
        logger.warning("PDF fallback: {}", e)
        # Если что-то пошло не так - падаем на старый текстовый метод

    # --- ФОЛЛБЕК НА ТЕКСТ (если PDF сломался) ---
    blocks = json.loads(app.get("blocks", "{}"))

    # Безопасный парсинг вложений (как в finalize)
    raw_att = app.get("attachments")
    try:
        attachments = (
            json.loads(raw_att.replace("'", '"'))
            if isinstance(raw_att, str)
            else raw_att or []
        )
    except Exception:
        attachments = []

    # Заголовок (экранируем для MarkdownV2)
    summary_parts = ["📝 *Проверьте вашу заявку перед отправкой:*\n\n"]

    for idx, block in enumerate(tpl.blocks, start=1):
        title = block.title
        val = blocks.get(str(block.id), "_(не заполнено)_")

        # Экранируем заголовок
        safe_title = escape_markdown_v2(f"{idx}. {title}")

        # Для блока кода: заменяем реальные \n на \n (оставляем как есть)
        # Но экранируем только тройные кавычки
        safe_val = val.replace("```", "\\`\\`\\`")

        # Формируем блок: заголовок + код
        block_text = f"*{safe_title}*\n```\n{safe_val}\n```\n\n"
        summary_parts.append(block_text)

    files_info = f"*Приложения:* {len(attachments)} файлов"
    summary_parts.append(files_info)

    final_summary = "".join(summary_parts)

    msg_func = (
        message.answer if isinstance(message, Message) else message.message.answer
    )

    try:
        await msg_func(
            final_summary,
            parse_mode="MarkdownV2",
            reply_markup=kb.review_keyboard(tpl),
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error("Review screen MDv2 failed: {}", e)
        # Фоллбек на HTML
        html_summary = "📝 <b>Проверьте вашу заявку:</b>\n\n"
        for idx, block in enumerate(tpl.blocks, start=1):
            title = block.title
            val = blocks.get(str(block.id), "<i>(не заполнено)</i>")
            html_summary += f"<b>{idx}. {title}</b>\n<pre>{val}</pre>\n\n"
        html_summary += f"<b>Приложения:</b> {len(attachments)} файлов"

        await msg_func(
            html_summary, parse_mode="HTML", reply_markup=kb.review_keyboard(tpl)
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
