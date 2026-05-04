from html import escape

import stdlib.keyboards as kb
from stdlib.services import application_service
import stdlib.llm.free_form as llm
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from stdlib.handlers.states import BotStates
from stdlib.schemas import LLMComplete, LLMError, LLMIncomplete
from stdlib.summary_format import (
    build_files_step_message,
    chunk_plain_text,
    format_blocks_plain_copy,
)
from stdlib.template import get_template

router = Router()


@router.message(BotStates.FREE_FORM, F.text)
async def handle_free_form_input(message: Message, state: FSMContext):
    data = await state.get_data()
    app_id = data["app_id"]

    waiting_msg = await message.answer("⏳ Анализирую ваш текст...")

    history = await application_service.get_chat_history(app_id)
    history.append({"role": "user", "content": message.text.strip()})

    result = await llm.process_free_form_chat(
        history, app_id=app_id, user_id=message.from_user.id
    )

    await waiting_msg.delete()

    if isinstance(result, LLMIncomplete):
        reply_text = result.reply or "Пожалуйста, уточните детали."
        history.append({"role": "assistant", "content": reply_text})
        await application_service.save_chat_history(app_id, history)
        await message.answer(reply_text)

    elif isinstance(result, LLMComplete):
        blocks = result.blocks
        await application_service.save_all_blocks(app_id, blocks)
        await application_service.save_chat_history(app_id, [])

        await state.update_data(current_block="files", mode="input")
        await state.set_state(BotStates.FILLING)

        tpl = await get_template()
        plain = format_blocks_plain_copy(blocks, tpl)
        parts = chunk_plain_text(plain)
        first = build_files_step_message(parts[0])
        await message.answer(
            first, parse_mode="HTML", reply_markup=kb.files_keyboard()
        )
        for rest in parts[1:]:
            await message.answer(
                "… <i>продолжение текста заявки</i>\n\n"
                f"<pre>{escape(rest)}</pre>",
                parse_mode="HTML",
            )
    elif isinstance(result, LLMError):
        await message.answer(result.reply)
    else:
        await message.answer(
            "Произошла ошибка при анализе текста. Пожалуйста, попробуйте переформулировать."
        )
