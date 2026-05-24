import stdlib.keyboards as kb
from stdlib.services import application_service
import stdlib.llm.formatter as llm
from html import escape
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from stdlib.handlers.states import BotStates
from stdlib.intent import is_delegation
from stdlib.telegram_ui import edit_nav_anchor, render_nav_screen
from stdlib.template import get_template

router = Router()


def _attachment_names(app) -> list[str]:
    return [att.name for att in (app.attachments or [])]


async def send_rework_menu(
    target: Message | CallbackQuery,
    state: FSMContext,
    app_id: int | None = None,
    *,
    message_text: str | None = None,
    force_new: bool = False,
) -> None:
    tpl = await get_template()
    text = message_text or "✏️ <b>Режим доработки</b>\n\nВыберите блок:"
    markup = kb.rework_keyboard(tpl, app_id)
    await render_nav_screen(
        target, state, text, markup, parse_mode="HTML", force_new=force_new
    )


async def _send_rework_block_input(
    target: Message | CallbackQuery, state: FSMContext, block_num: int, app_id: int
) -> None:
    app = await application_service.get_application(app_id)
    blocks = app.blocks if app else {}
    current_text_raw = (blocks.get(str(block_num), "") or "").strip()
    current_text = escape(current_text_raw) if current_text_raw else "— пусто —"

    tpl = await get_template()
    try:
        block_title = tpl.get_block(block_num).title
    except ValueError:
        block_title = f"блок {block_num}"

    await state.set_state(BotStates.REWORK)
    await state.update_data(
        app_id=app_id,
        rework_block=block_num,
        mode="input",
        rework_screen="block",
    )
    text = (
        f"<b>Текущий текст блока «{block_title}»:</b>\n\n"
        f"<pre>{current_text}</pre>\n\n"
        "Введите исправленный вариант:"
    )
    await render_nav_screen(
        target,
        state,
        text,
        kb.rework_block_input_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("rework_block_"))
async def on_rework_select(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    try:
        if len(parts) == 4:
            forced_app_id = int(parts[2])
            block_num = int(parts[3])
        else:
            forced_app_id = None
            block_num = int(parts[2])
    except (ValueError, IndexError):
        await callback.answer("Некорректная кнопка.", show_alert=True)
        return

    data = await state.get_data()
    from_id = forced_app_id or data.get("app_id")
    if from_id:
        cand = await application_service.get_application(from_id)
        if not cand or cand.user_id != callback.from_user.id:
            cand = None
    else:
        cand = await application_service.get_last_rework_application(callback.from_user.id)
    if not cand:
        await callback.answer("Нет заявки для правки.", show_alert=True)
        return
    await callback.answer()
    await _send_rework_block_input(callback, state, block_num, cand.id)


@router.message(BotStates.REWORK, F.text)
async def on_rework_input(message: Message, state: FSMContext):
    data = await state.get_data()

    if data["mode"] == "confirm":
        await message.answer(
            "Используйте кнопки ниже.",
            reply_markup=kb.confirm_rework_keyboard(),
        )
        return

    raw_text = message.text.strip()
    app = await application_service.get_application(data["app_id"])
    context_blocks = app.blocks if app else {}

    result = await llm.format_text(
        raw_text,
        context_blocks=context_blocks,
        user_id=message.from_user.id,
        app_id=data["app_id"],
        block_number=data["rework_block"],
        generate=is_delegation(raw_text),
    )

    await application_service.save_block(data["app_id"], data["rework_block"], result.text)

    await state.update_data(mode="confirm")
    text = f"{result.intro}\n\n<i>{result.text}</i>\n\nВсё верно?"
    await edit_nav_anchor(
        message.bot,
        state,
        text,
        kb.confirm_rework_keyboard(),
        parse_mode="HTML",
        fallback_chat_id=message.chat.id,
    )


@router.callback_query(BotStates.REWORK, F.data == "rework_confirm")
async def on_rework_confirmed(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(mode="input", rework_screen="menu")
    data = await state.get_data()
    await send_rework_menu(
        callback,
        state,
        data.get("app_id"),
        message_text="Выберите другой блок для правки или отправьте заявку повторно:",
    )


@router.callback_query(BotStates.REWORK, F.data == "rework_edit")
async def on_rework_edit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await _send_rework_block_input(callback, state, data["rework_block"], data["app_id"])


@router.callback_query(F.data == "rework_back")
async def on_rework_back(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state != BotStates.REWORK.state:
        await callback.answer(
            "Эта кнопка устарела — смотрите последнее сообщение бота.",
            show_alert=True,
        )
        return

    data = await state.get_data()
    await callback.answer()

    if data.get("mode") == "confirm":
        await _send_rework_block_input(
            callback, state, data["rework_block"], data["app_id"]
        )
        return

    if data.get("rework_screen") == "block":
        await state.update_data(mode="input", rework_screen="menu")
        await send_rework_menu(callback, state, data.get("app_id"))
        return

    from stdlib.handlers.user.my_apps import send_app_card

    app_id = data.get("app_id")
    if not app_id:
        await callback.message.answer("Заявка не найдена.")
        return
    await state.clear()
    await send_app_card(callback, app_id)


@router.callback_query(F.data.startswith("rework_files"))
async def on_rework_files(callback: CallbackQuery, state: FSMContext):
    from stdlib.handlers.user.files import send_files_screen

    await callback.answer()
    forced_app_id: int | None = None
    parts = callback.data.split("_")
    if len(parts) == 3:
        try:
            forced_app_id = int(parts[2])
        except ValueError:
            forced_app_id = None

    data = await state.get_data()
    app_id = forced_app_id or data.get("app_id")
    if not app_id:
        await callback.answer("Не удалось определить заявку для редактирования.", show_alert=True)
        return
    cand = await application_service.get_application(app_id)
    if not cand or cand.user_id != callback.from_user.id:
        await callback.answer("Эта заявка недоступна для редактирования.", show_alert=True)
        return

    await send_files_screen(callback, state, app_id, returning_to="rework")


@router.callback_query(F.data.startswith("rework_submit"))
async def on_rework_submit(callback: CallbackQuery, state: FSMContext, bot: Bot):
    from stdlib.handlers.user.finalize import finalize_and_notify

    await callback.answer()
    forced_app_id: int | None = None
    parts = callback.data.split("_")
    if len(parts) == 3:
        try:
            forced_app_id = int(parts[2])
        except ValueError:
            forced_app_id = None

    data = await state.get_data()
    app_id = forced_app_id or data.get("app_id")
    if not app_id:
        await callback.answer("Не удалось определить заявку для отправки.", show_alert=True)
        return
    cand = await application_service.get_application(app_id)
    if not cand or cand.user_id != callback.from_user.id:
        await callback.answer("Эта заявка недоступна для отправки.", show_alert=True)
        return

    await state.update_data(app_id=app_id, mode="input")
    await finalize_and_notify(callback, state, app_id, bot)
