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
from stdlib.telegram_ui import edit_nav_anchor
from stdlib.template import get_template

router = Router()


async def _remember_cleanup_message(state: FSMContext, message_id: int) -> None:
    data = await state.get_data()
    ids = list(data.get("cleanup_bot_message_ids") or [])
    ids.append(message_id)
    await state.update_data(cleanup_bot_message_ids=ids[-120:])


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
        await edit_nav_anchor(
            message.bot,
            state,
            reply_text,
            kb.free_form_keyboard(),
            parse_mode="HTML",
            fallback_chat_id=message.chat.id,
        )

    elif isinstance(result, LLMComplete):
        blocks = result.blocks
        await application_service.save_all_blocks(app_id, blocks)
        await application_service.save_chat_history(app_id, [])

        await state.update_data(current_block="files", mode="input")
        await state.set_state(BotStates.FILLING)

        tpl = await get_template()
        chunks = list(chunk_blocks_summary_html(tpl, blocks, INTRO_FREE_FORM_HTML))
        if chunks:
            await edit_nav_anchor(
                message.bot,
                state,
                chunks[0],
                kb.files_keyboard(),
                parse_mode="HTML",
                fallback_chat_id=message.chat.id,
            )
            for html in chunks[1:]:
                sent = await message.answer(html, parse_mode="HTML")
                await _remember_cleanup_message(state, sent.message_id)
    elif isinstance(result, LLMError):
        await message.answer(result.reply)
    else:
        await message.answer(
            "Произошла ошибка при анализе текста. Пожалуйста, попробуйте переформулировать."
        )
