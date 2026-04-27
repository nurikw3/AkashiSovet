import stdlib.db as db
import stdlib.keyboards as kb
import stdlib.llm.free_form as llm
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from stdlib.handlers.blocks import BLOCKS
from stdlib.handlers.states import BotStates

router = Router()


@router.message(BotStates.FREE_FORM, F.text)
async def handle_free_form_input(message: Message, state: FSMContext):
    data = await state.get_data()
    app_id = data["app_id"]

    waiting_msg = await message.answer("⏳ Анализирую ваш текст...")

    history = await db.get_chat_history(app_id)
    history.append({"role": "user", "content": message.text.strip()})

    result = await llm.process_free_form_chat(
        history, app_id=app_id, user_id=message.from_user.id
    )

    await waiting_msg.delete()

    if result.get("status") == "incomplete":
        reply_text = result.get("reply", "Пожалуйста, уточните детали.")
        history.append({"role": "assistant", "content": reply_text})
        await db.save_chat_history(app_id, history)
        await message.answer(reply_text)

    elif result.get("status") == "complete":
        blocks = result.get("blocks", {})
        await db.save_all_blocks(app_id, blocks)
        await db.save_chat_history(app_id, [])

        await state.update_data(current_block="files", mode="input")
        await state.set_state(BotStates.FILLING)

        summary = "✅ Отлично! Я собрал всю необходимую информацию.\n\n"
        for i in range(1, 6):
            title = BLOCKS[i]["title"]
            val = blocks.get(str(i), "")
            summary += f"<b>{i}. {title}</b>\n{val}\n\n"
        summary += (
            "<b>Приложения</b>\nПрикрепите файлы к заявке и нажмите <b>Готово</b>."
        )

        await message.answer(
            summary, parse_mode="HTML", reply_markup=kb.files_keyboard()
        )
    else:
        await message.answer(
            "Произошла ошибка при анализе текста. Пожалуйста, попробуйте переформулировать."
        )
