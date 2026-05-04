import stdlib.keyboards as kb
from stdlib.services import application_service
import stdlib.llm.free_form as llm
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from stdlib.handlers.states import BotStates
from stdlib.schemas import LLMComplete, LLMError, LLMIncomplete
from stdlib.telegram_summary import (
    chunk_blocks_summary_html,
    INTRO_FREE_FORM_HTML,
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
        for idx, html in enumerate(
            chunk_blocks_summary_html(tpl, blocks, INTRO_FREE_FORM_HTML)
        ):
            await message.answer(
                html,
                parse_mode="HTML",
                reply_markup=kb.files_keyboard() if idx == 0 else None,
            )
    elif isinstance(result, LLMError):
        await message.answer(result.reply)
    else:
        await message.answer(
            "Произошла ошибка при анализе текста. Пожалуйста, попробуйте переформулировать."
        )
