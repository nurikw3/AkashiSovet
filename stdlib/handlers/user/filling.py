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
from stdlib.telegram_summary import (
    chunk_blocks_summary_html,
    INTRO_STEP_FILLED_HTML,
)
from stdlib.telegram_ui import edit_nav_anchor, render_nav_screen
from stdlib.template import ApplicationTemplate, get_template

router = Router()


async def _remember_cleanup_message(state: FSMContext, message_id: int) -> None:
    data = await state.get_data()
    ids = list(data.get("cleanup_bot_message_ids") or [])
    ids.append(message_id)
    await state.update_data(cleanup_bot_message_ids=ids[-120:])


async def _block_title(block_id: int) -> str:
    tpl = await get_template()
    try:
        return tpl.get_block(block_id).title
    except ValueError:
        return f"блок {block_id}"


def block_show_back(
    block_id: int, returning_to: str | None, tpl: ApplicationTemplate
) -> bool:
    if returning_to in ("review", "rework"):
        return True
    return tpl.get_prev_block_id(block_id) is not None


async def _get_context(app_id: int, current_block: int, pending: str | None) -> dict:
    app = await application_service.get_application(app_id)
    if not app:
        return {}
    context_blocks = dict(app.blocks)
    if pending:
        context_blocks[str(current_block)] = pending
    return context_blocks


async def send_block_input_screen(
    target: Message | CallbackQuery,
    state: FSMContext,
    block_id: int,
    *,
    intro: str | None = None,
    style: str = "question",
    force_new: bool = False,
) -> None:
    """Показать экран ввода блока. style: question | edit | review_edit | saved."""
    data = await state.get_data()
    returning_to = data.get("returning_to")
    tpl = await get_template()
    b = tpl.get_block(block_id)
    idx = tpl.block_index_1based(block_id)
    total = tpl.total_blocks_count
    show_back = block_show_back(block_id, returning_to, tpl)

    await state.update_data(
        current_block=block_id,
        mode="input",
        pending_formatted=None,
        confirm_dialog_block=None,
    )

    markup = kb.block_input_keyboard(block_id, show_back=show_back)

    if style == "edit":
        text = f"Введите исправленный текст для блока «{b.title}»:"
    elif style == "review_edit":
        text = (
            f"<b>Редактирование: Блок {idx} — {b.title}</b>\n\n"
            "Введите новый текст для этого блока:"
        )
    else:
        lines: list[str] = []
        if intro:
            lines.append(intro)
        lines.append(f"<b>Блок {idx} из {total} — {b.title}</b>")
        if style == "saved":
            app = await application_service.get_application(data.get("app_id"))
            if app:
                saved_raw = (app.blocks.get(str(block_id), "") or "").strip()
                if saved_raw:
                    lines.append(
                        f"<b>Сохранённый текст:</b>\n<pre>{escape(saved_raw)}</pre>"
                    )
        lines.append(b.question)
        text = "\n\n".join(lines)

    await render_nav_screen(
        target, state, text, markup, parse_mode="HTML", force_new=force_new
    )


async def _confirm_show_back(block_id: int, state: FSMContext) -> bool:
    data = await state.get_data()
    tpl = await get_template()
    return block_show_back(block_id, data.get("returning_to"), tpl)


async def _send_confirm(
    message: Message, state: FSMContext, text: str, intro: str, block_id: int
):
    await state.update_data(
        mode="confirm",
        pending_formatted=text,
        confirm_dialog_block=block_id,
    )
    show_back = await _confirm_show_back(block_id, state)
    markup = kb.confirm_keyboard(block_id, show_back=show_back)

    safe_intro = escape_markdown_v2(intro)
    safe_text = text.replace("```", "\\`\\`\\`")
    code_block = f"```\n{safe_text}\n```"
    final_message = f"{safe_intro}\n\n{code_block}\n\n_Всё верно?_"

    try:
        await edit_nav_anchor(
            message.bot,
            state,
            final_message,
            markup,
            parse_mode="MarkdownV2",
            fallback_chat_id=message.chat.id,
        )
    except Exception as e:
        logger.error("MarkdownV2 confirm edit failed: {}", e)
        await edit_nav_anchor(
            message.bot,
            state,
            f"{intro}\n\n{text}\n\nВсё верно?",
            markup,
            parse_mode="HTML",
            fallback_chat_id=message.chat.id,
        )


# ── Хэндлеры ввода блоков ─────────────────────────────────────────────────────


@router.message(BotStates.FILLING, F.text)
async def handle_block_input(message: Message, state: FSMContext):
    data = await state.get_data()

    if data["mode"] == "confirm":
        bid = data.get("confirm_dialog_block")
        if not isinstance(bid, int):
            bid = data["current_block"] if isinstance(data.get("current_block"), int) else 1
        show_back = await _confirm_show_back(bid, state)
        await message.answer(
            "Используйте кнопки под предыдущим сообщением с вариантом текста.",
            reply_markup=kb.confirm_keyboard(bid, show_back=show_back),
        )
        return

    current_block = data["current_block"]
    if current_block == "files":
        if data.get("mode") == "rename_attachment":
            from stdlib.handlers.user.files import apply_attachment_rename

            await apply_attachment_rename(message, state)
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

    await _send_confirm(
        message, state, result.text, result.intro, int(data["current_block"])
    )


async def _handle_delegation(message: Message, state: FSMContext, data: dict):
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

    await _send_confirm(
        message, state, result.text, "Предлагаю такой вариант:", int(current_block)
    )


# ── Подтверждение / редактирование ───────────────────────────────────────────


@router.callback_query(BotStates.FILLING, F.data.startswith("fcb_confirm_"))
async def on_confirm(callback: CallbackQuery, state: FSMContext):
    try:
        confirmed_block = int(callback.data.removeprefix("fcb_confirm_"))
    except ValueError:
        await callback.answer("Некорректная кнопка.", show_alert=True)
        return

    data = await state.get_data()

    if not data.get("pending_formatted"):
        await callback.answer(
            "Этот шаг уже подтверждён или устарел — смотрите последнее сообщение бота.",
            show_alert=True,
        )
        return

    cdb = data.get("confirm_dialog_block")
    if cdb is not None and confirmed_block != cdb:
        await callback.answer(
            "Эта кнопка не соответствует текущему черновику подтверждения.",
            show_alert=True,
        )
        return

    await callback.answer()

    pending = data["pending_formatted"]
    await application_service.save_block(data["app_id"], confirmed_block, pending)
    await state.update_data(pending_formatted=None, confirm_dialog_block=None)

    if data.get("returning_to") == "review":
        from stdlib.handlers.user.review import send_review_screen

        await state.set_state(BotStates.REVIEW)
        await state.update_data(returning_to=None)
        await send_review_screen(callback, state, data["app_id"], force_new=True)
        return

    tpl = await get_template()
    next_id = tpl.get_next_block_id(confirmed_block)

    if next_id is not None:
        await send_block_input_screen(callback, state, next_id)
        return

    await state.update_data(current_block="files", mode="input")
    app_row = await application_service.get_application(data["app_id"])
    tpl = await get_template()
    blocks = app_row.blocks if app_row else {}
    chunks = list(chunk_blocks_summary_html(tpl, blocks, INTRO_STEP_FILLED_HTML))
    if chunks:
        await render_nav_screen(
            callback,
            state,
            chunks[0],
            kb.files_keyboard(),
            parse_mode="HTML",
        )
        for html in chunks[1:]:
            sent = await callback.message.answer(html, parse_mode="HTML")
            await _remember_cleanup_message(state, sent.message_id)


@router.callback_query(BotStates.FILLING, F.data.startswith("fcb_edit_"))
async def on_edit(callback: CallbackQuery, state: FSMContext):
    try:
        edit_block = int(callback.data.removeprefix("fcb_edit_"))
    except ValueError:
        await callback.answer("Некорректная кнопка.", show_alert=True)
        return

    await callback.answer()
    await send_block_input_screen(callback, state, edit_block, style="edit")


@router.callback_query(BotStates.FILLING, F.data.startswith("fcb_back_"))
async def on_block_back(callback: CallbackQuery, state: FSMContext):
    try:
        back_from_block = int(callback.data.removeprefix("fcb_back_"))
    except ValueError:
        await callback.answer("Некорректная кнопка.", show_alert=True)
        return

    data = await state.get_data()
    mode = data.get("mode")
    current = data.get("current_block")

    if mode == "confirm":
        cdb = data.get("confirm_dialog_block")
        if cdb is not None and back_from_block != cdb:
            await callback.answer(
                "Эта кнопка устарела — смотрите последнее сообщение бота.",
                show_alert=True,
            )
            return
    elif isinstance(current, int) and current != back_from_block:
        await callback.answer(
            "Эта кнопка устарела — смотрите последнее сообщение бота.",
            show_alert=True,
        )
        return

    await callback.answer()

    returning_to = data.get("returning_to")
    if returning_to == "review":
        from stdlib.handlers.user.review import send_review_screen

        await state.set_state(BotStates.REVIEW)
        await state.update_data(
            returning_to=None,
            pending_formatted=None,
            confirm_dialog_block=None,
        )
        await send_review_screen(callback, state, data["app_id"], force_new=True)
        return

    if returning_to == "rework":
        from stdlib.handlers.user.rework import send_rework_menu

        await state.set_state(BotStates.REWORK)
        await state.update_data(
            returning_to=None,
            pending_formatted=None,
            confirm_dialog_block=None,
        )
        await send_rework_menu(callback, state, data["app_id"])
        return

    tpl = await get_template()
    prev_id = tpl.get_prev_block_id(back_from_block)
    if prev_id is None:
        await callback.answer("Это первый блок.", show_alert=True)
        return

    await send_block_input_screen(callback, state, prev_id, style="saved")
