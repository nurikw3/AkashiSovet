import stdlib.keyboards as kb
from stdlib.services import application_service
import stdlib.llm.formatter as llm
from html import escape
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from stdlib.handlers.states import BotStates
from stdlib.intent import is_delegation
from stdlib.template import get_template

router = Router()


def _attachment_names(app) -> list[str]:
    return [att.name for att in (app.attachments or [])]


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

    blocks = cand.blocks
    current_text_raw = (blocks.get(str(block_num), "") or "").strip()
    current_text = escape(current_text_raw) if current_text_raw else "— пусто —"

    tpl = await get_template()
    try:
        block_title = tpl.get_block(block_num).title
    except ValueError:
        block_title = f"блок {block_num}"

    await state.set_state(BotStates.REWORK)
    await state.update_data(app_id=cand.id, rework_block=block_num, mode="input")
    await callback.message.answer(
        f"<b>Текущий текст блока «{block_title}»:</b>\n\n"
        f"<pre>{current_text}</pre>\n\n"
        "Введите исправленный вариант:",
        parse_mode="HTML",
    )


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

    # Сохраняем в БД сразу — в rework нет отдельного pending,
    # confirm здесь означает "показали превью"
    await application_service.save_block(data["app_id"], data["rework_block"], result.text)

    await state.update_data(mode="confirm")
    await message.answer(
        f"{result.intro}\n\n<i>{result.text}</i>\n\nВсё верно?",
        parse_mode="HTML",
        reply_markup=kb.confirm_rework_keyboard(),
    )


@router.callback_query(BotStates.REWORK, F.data == "rework_confirm")
async def on_rework_confirmed(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(mode="input")
    tpl = await get_template()
    data = await state.get_data()
    await callback.message.answer(
        "Выберите другой блок для правки или отправьте заявку повторно:",
        reply_markup=kb.rework_keyboard(tpl, data.get("app_id")),
    )


@router.callback_query(BotStates.REWORK, F.data == "rework_edit")
async def on_rework_edit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await state.update_data(mode="input")
    tpl = await get_template()
    rb = data["rework_block"]
    try:
        block_title = tpl.get_block(rb).title
    except ValueError:
        block_title = f"блок {rb}"
    app = await application_service.get_application(data["app_id"])
    blocks = app.blocks if app else {}
    current_text_raw = (blocks.get(str(rb), "") or "").strip()
    current_text = escape(current_text_raw) if current_text_raw else "— пусто —"
    await callback.message.answer(
        f"<b>Текущий текст блока «{block_title}»:</b>\n\n"
        f"<pre>{current_text}</pre>\n\n"
        "Введите исправленный вариант:",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("rework_files"))
async def on_rework_files(callback: CallbackQuery, state: FSMContext):
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

    await state.update_data(
        app_id=app_id, current_block="files", mode="input", returning_to="rework"
    )
    await state.set_state(BotStates.FILLING)
    attachment_names = _attachment_names(cand)
    await callback.message.answer(
        "Прикрепите дополнительные файлы. Нажмите <b>Готово</b>, когда закончите.",
        parse_mode="HTML",
        reply_markup=kb.files_keyboard(attachment_names),
    )


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

    # Сбрасываем mode чтобы не было блокировки
    await state.update_data(app_id=app_id, mode="input")
    await finalize_and_notify(callback, state, app_id, bot)
