from stdlib.services import application_service
import stdlib.keyboards as kb
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from bot.config import config
from bot.logger import logger
from stdlib.handlers.states import BotStates
from stdlib.services.notification_service import notify_user_application_rework
from stdlib.template import get_template

router = Router()


def is_superuser(user_id: int) -> bool:
    return user_id in config.SUPERUSER_IDS


@router.callback_query(F.data.startswith("reject_"))
async def on_reject(callback: CallbackQuery, state: FSMContext):
    if not is_superuser(callback.from_user.id):
        return await callback.answer("Нет доступа.", show_alert=True)

    app_id = int(callback.data.split("_")[1])
    app = await application_service.get_application(app_id)

    if not app:
        return await callback.answer("Заявка не найдена.", show_alert=True)
    if app.status != "pending":
        return await callback.answer("Заявка уже обработана.", show_alert=True)

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(BotStates.SU_REJECT)
    await state.update_data(app_id=app_id)
    await callback.message.answer(
        f"Введите замечания по заявке #{app_id}:\n(текст будет передан автору)"
    )
    logger.info(
        "App {} reject initiated by superuser {}", app_id, callback.from_user.id
    )


@router.message(BotStates.SU_REJECT)
async def on_feedback(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    app_id = data["app_id"]
    feedback_text = message.text.strip()

    app_row = await application_service.send_for_rework(app_id, feedback_text)
    await state.clear()
    await message.answer(f"Замечания по заявке #{app_id} отправлены автору.")

    tpl = await get_template()
    if not app_row:
        return
    try:
        await notify_user_application_rework(
            bot=bot,
            user_id=app_row.user_id,
            app_id=app_id,
            feedback=feedback_text,
            reply_markup=kb.rework_keyboard(tpl, app_id),
            web_wording=False,
        )
    except Exception as e:
        logger.error(
            "Failed to notify user {} about reject for app {}: {}",
            app_row.user_id,
            app_id,
            e,
        )

    logger.info(
        "App {} rejected by superuser {} | feedback_len={}",
        app_id,
        message.from_user.id,
        len(feedback_text),
    )
