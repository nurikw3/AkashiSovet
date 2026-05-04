import stdlib.keyboards as kb
from stdlib.services import application_service
import stdlib.llm.formatter as llm
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from stdlib.handlers.states import BotStates
from stdlib.intent import is_delegation
from stdlib.template import get_template

router = Router()


@router.callback_query(F.data.startswith("rework_block_"))
async def on_rework_select(callback: CallbackQuery, state: FSMContext):
    block_num = int(callback.data.split("_")[2])

    data = await state.get_data()
    from_id = data.get("app_id")
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
    current_text = blocks.get(str(block_num), "")

    tpl = await get_template()
    try:
        block_title = tpl.get_block(block_num).title
    except ValueError:
        block_title = f"блок {block_num}"

    await state.set_state(BotStates.REWORK)
    await state.update_data(app_id=cand.id, rework_block=block_num, mode="input")
    await callback.message.answer(
        f"<b>Текущий текст блока «{block_title}»:</b>\n\n"
        f"<i>{current_text}</i>\n\n"
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
    await callback.message.answer(
        "Выберите другой блок для правки или отправьте заявку повторно:",
        reply_markup=kb.rework_keyboard(tpl),
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
    await callback.message.answer(
        f"Введите исправленный текст для блока «{block_title}»:"
    )


@router.callback_query(BotStates.REWORK, F.data == "rework_submit")
async def on_rework_submit(callback: CallbackQuery, state: FSMContext, bot: Bot):
    from stdlib.handlers.user.finalize import finalize_and_notify

    await callback.answer()
    data = await state.get_data()
    # Сбрасываем mode чтобы не было блокировки
    await state.update_data(mode="input")
    await finalize_and_notify(callback, state, data["app_id"], bot)
