import json

import stdlib.keyboards as kb
from stdlib.services import application_service
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from bot.logger import logger
from stdlib.handlers.states import BotStates
from stdlib.handlers.user.review import send_review_screen

router = Router()


@router.message(BotStates.FILLING, F.document | F.photo)
async def handle_file(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("current_block") != "files":
        return

    app = await application_service.get_application_record(data["app_id"])
    if not app:
        return
    raw_att = app.get("attachments")
    attachments = json.loads(raw_att) if raw_att else []

    if message.document:
        attachments.append(
            {"file_id": message.document.file_id, "name": message.document.file_name}
        )
    elif message.photo:
        name = f"фото_{len(attachments) + 1}.jpg"
        attachments.append({"file_id": message.photo[-1].file_id, "name": name})

    await application_service.save_attachments_payload(data["app_id"], attachments)
    logger.info("File attached | app_id={} total={}", data["app_id"], len(attachments))

    await message.answer(
        f"✅ Файл принят. Всего приложений: {len(attachments)}",
        reply_markup=kb.files_keyboard(),
    )


@router.callback_query(BotStates.FILLING, F.data.in_({"files_done", "files_skip"}))
async def on_files_done(callback: CallbackQuery, state: FSMContext):

    await callback.answer()
    data = await state.get_data()
    app_id = data["app_id"]

    await state.set_state(BotStates.REVIEW)
    if data.get("returning_to") == "review":
        await state.update_data(returning_to=None)
    await send_review_screen(callback, app_id)
