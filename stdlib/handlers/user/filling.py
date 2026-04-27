# stdlib/handlers/user/filling.py
import json

import stdlib.db as db
import stdlib.keyboards as kb
import stdlib.llm.formatter as llm
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from bot.logger import logger
from stdlib.handlers.blocks import BLOCKS
from stdlib.handlers.states import BotStates
from stdlib.intent import is_delegation, escape_markdown_v2

router = Router()


async def _get_context(app_id: int, current_block: int, pending: str | None) -> dict:
    app = await db.get_app(app_id)
    context_blocks = json.loads(app["blocks"]) if app and app["blocks"] else {}
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
        await message.answer(
            f"Недостаточно контекста для блока «{BLOCKS[current_block]['title']}».\n\n"
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
        await db.save_block(data["app_id"], current_block, pending)
        await state.update_data(pending_formatted=None)

    # Если пришли из экрана ревью — возвращаемся обратно
    if data.get("returning_to") == "review":
        from stdlib.handlers.user.review import send_review_screen

        await state.set_state(BotStates.REVIEW)
        await state.update_data(returning_to=None)
        await send_review_screen(callback, data["app_id"])
        return

    # Переходим к следующему блоку
    if current_block < 5:
        next_block = current_block + 1
        await state.update_data(current_block=next_block, mode="input")
        await callback.message.answer(
            f"<b>Блок {next_block} из 5 — {BLOCKS[next_block]['title']}</b>\n\n"
            f"{BLOCKS[next_block]['question']}",
            parse_mode="HTML",
        )
        return

    # Все 5 блоков заполнены — переходим к файлам
    await state.update_data(current_block="files", mode="input")
    await callback.message.answer(
        "Отлично! Все разделы заполнены.\n\n"
        "<b>Приложения</b>\n\n"
        "Прикрепите файлы к заявке (договоры, расчёты, согласования и т.д.).\n"
        "Отправляйте по одному. Когда закончите — нажмите <b>Готово</b>.",
        parse_mode="HTML",
        reply_markup=kb.files_keyboard(),
    )


@router.callback_query(BotStates.FILLING, F.data == "edit")
async def on_edit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await state.update_data(mode="input")
    block_title = BLOCKS[data["current_block"]]["title"]
    await callback.message.answer(
        f"Введите исправленный текст для блока «{block_title}»:"
    )
