# stdlib/handlers/user/filling.py
from html import escape

import stdlib.keyboards as kb
from stdlib.services import application_service
import stdlib.llm.formatter as llm
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from bot.logger import logger
from stdlib.handlers.states import BotStates
from stdlib.intent import is_delegation, escape_markdown_v2
from stdlib.summary_format import (
    build_files_step_message,
    chunk_plain_text,
    format_blocks_plain_copy,
)
from stdlib.template import get_template

router = Router()


async def _block_title(block_id: int) -> str:
    tpl = await get_template()
    try:
        return tpl.get_block(block_id).title
    except ValueError:
        return f"блок {block_id}"


async def _get_context(app_id: int, current_block: int, pending: str | None) -> dict:
    app = await application_service.get_application(app_id)
    if not app:
        return {}
    context_blocks = dict(app.blocks)
    if pending:
        context_blocks[str(current_block)] = pending
    return context_blocks


async def _send_confirm(message: Message, state: FSMContext, text: str, intro: str):
    await state.update_data(mode="confirm", pending_formatted=text)

    # 1. Экранируем ввод пользователя (intro), так как он может содержать спецсимволы
    safe_intro = escape_markdown_v2(intro)

    # 2. Формируем блок кода.
    # Важно: сам текст внутри блока кода НЕ нужно экранировать полностью,
    # но тройные кавычки внутри текста могут сломать разметку.
    # Для простоты заменим тройные кавычки внутри ответа на одинарные или экранируем их.
    safe_text = text.replace("```", "\\`\\`\\`")

    # Оборачиваем в блок кода с указанием языка 'text' (чтобы не было подсветки синтаксиса, которая может глючить)
    code_block = f"```\n{safe_text}\n```"

    final_message = f"{safe_intro}\n\n{code_block}\n\n_Всё верно?_"

    try:
        await message.answer(
            final_message,
            parse_mode="MarkdownV2",
            reply_markup=kb.confirm_keyboard(),
        )
    except Exception as e:
        logger.error("MarkdownV2 send failed: {}", e)
        await message.answer(
            f"{intro}\n\n{text}\n\nВсё верно?",
            reply_markup=kb.confirm_keyboard(),
        )


# ── Хэндлеры ввода блоков ─────────────────────────────────────────────────────


@router.message(BotStates.FILLING, F.text)
async def handle_block_input(message: Message, state: FSMContext):
    data = await state.get_data()

    if data["mode"] == "confirm":
        await message.answer(
            "Используйте кнопки ниже.",
            reply_markup=kb.confirm_keyboard(),
        )
        return

    current_block = data["current_block"]
    if current_block == "files":
        return

    raw_text = message.text.strip()
    logger.debug(
        "Block input | app_id={} block={} len={}",
        data["app_id"],
        current_block,
        len(raw_text),
    )

    if is_delegation(raw_text):
        await _handle_delegation(message, state, data)
    else:
        await _handle_format(message, state, data, raw_text)


async def _handle_format(
    message: Message, state: FSMContext, data: dict, raw_text: str
):
    """Обычный флоу — редактируем то что написал юзер."""
    context_blocks = await _get_context(
        data["app_id"],
        data["current_block"],
        data.get("pending_formatted"),
    )

    result = await llm.format_text(
        raw=raw_text,
        context_blocks=context_blocks,
        user_id=message.from_user.id,
        app_id=data["app_id"],
        block_number=data["current_block"],
        generate=False,
    )

    await _send_confirm(message, state, result.text, result.intro)


async def _handle_delegation(message: Message, state: FSMContext, data: dict):
    """Делегирование — генерируем текст блока из контекста."""
    current_block = data["current_block"]
    context_blocks = await _get_context(
        data["app_id"],
        current_block,
        data.get("pending_formatted"),
    )

    result = await llm.format_text(
        raw="",
        context_blocks=context_blocks,
        user_id=message.from_user.id,
        app_id=data["app_id"],
        block_number=current_block,
        generate=True,
    )

    if result.insufficient_context or not result.text:
        title = await _block_title(current_block)
        await message.answer(
            f"Недостаточно контекста для блока «{title}».\n\n"
            f"Заполните предыдущие блоки подробнее — тогда смогу предложить вариант."
        )
        return

    await _send_confirm(message, state, result.text, "Предлагаю такой вариант:")


# ── Подтверждение / редактирование ───────────────────────────────────────────


@router.callback_query(BotStates.FILLING, F.data == "confirm")
async def on_confirm(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    current_block = data["current_block"]

    # Сохраняем в БД только после подтверждения
    if pending := data.get("pending_formatted"):
        await application_service.save_block(data["app_id"], current_block, pending)
        await state.update_data(pending_formatted=None)

    # Если пришли из экрана ревью — возвращаемся обратно
    if data.get("returning_to") == "review":
        from stdlib.handlers.user.review import send_review_screen

        await state.set_state(BotStates.REVIEW)
        await state.update_data(returning_to=None)
        await send_review_screen(callback, data["app_id"])
        return

    tpl = await get_template()
    next_id = tpl.get_next_block_id(current_block)

    if next_id is not None:
        b = tpl.get_block(next_id)
        idx = tpl.block_index_1based(next_id)
        total = tpl.total_blocks_count
        await state.update_data(current_block=next_id, mode="input")
        await callback.message.answer(
            f"<b>Блок {idx} из {total} — {b.title}</b>\n\n{b.question}",
            parse_mode="HTML",
        )
        return

    # Все блоки шаблона заполнены — переходим к файлам (та же сводка, что и в free-form)
    await state.update_data(current_block="files", mode="input")
    app_row = await application_service.get_application(data["app_id"])
    tpl = await get_template()
    blocks = app_row.blocks if app_row else {}
    plain = format_blocks_plain_copy(blocks, tpl)
    parts = chunk_plain_text(plain)
    first = build_files_step_message(parts[0])
    await callback.message.answer(
        first, parse_mode="HTML", reply_markup=kb.files_keyboard()
    )
    for rest in parts[1:]:
        await callback.message.answer(
            "… <i>продолжение текста заявки</i>\n\n"
            f"<pre>{escape(rest)}</pre>",
            parse_mode="HTML",
        )


@router.callback_query(BotStates.FILLING, F.data == "edit")
async def on_edit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await state.update_data(mode="input")
    cb = data["current_block"]
    block_title = await _block_title(cb) if isinstance(cb, int) else str(cb)
    await callback.message.answer(
        f"Введите исправленный текст для блока «{block_title}»:"
    )
