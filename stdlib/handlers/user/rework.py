import json

import stdlib.db as db
import stdlib.keyboards as kb
import stdlib.llm.formatter as llm
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from stdlib.handlers.blocks import BLOCKS
from stdlib.handlers.states import BotStates
from stdlib.intent import is_delegation

router = Router()


@router.callback_query(F.data.startswith("rework_block_"))
async def on_rework_select(callback: CallbackQuery, state: FSMContext):
    block_num = int(callback.data.split("_")[2])
    await callback.answer()

    app = await db.get_last_rework_app(callback.from_user.id)
    if not app:
        await callback.answer("Нет заявок на доработку.", show_alert=True)
        return

    blocks = json.loads(app["blocks"])
    current_text = blocks.get(str(block_num), "")

    await state.set_state(BotStates.REWORK)
    await state.update_data(app_id=app["id"], rework_block=block_num, mode="input")
    await callback.message.answer(
        f"<b>Текущий текст блока «{BLOCKS[block_num]['title']}»:</b>\n\n"
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
    app = await db.get_app(data["app_id"])
    context_blocks = json.loads(app["blocks"]) if app and app["blocks"] else {}

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
    await db.save_block(data["app_id"], data["rework_block"], result.text)  # .text !

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
    await callback.message.answer(
        "Выберите другой блок для правки или отправьте заявку повторно:",
        reply_markup=kb.rework_keyboard(),
    )


@router.callback_query(BotStates.REWORK, F.data == "rework_edit")
async def on_rework_edit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await state.update_data(mode="input")
    block_title = BLOCKS[data["rework_block"]]["title"]
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
