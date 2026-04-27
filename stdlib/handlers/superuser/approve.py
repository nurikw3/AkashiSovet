import stdlib.db as db
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from bot.config import config
from bot.logger import logger

router = Router()


def is_superuser(user_id: int) -> bool:
    return user_id in config.SUPERUSER_IDS


@router.callback_query(F.data.startswith("approve_"))
async def on_approve(callback: CallbackQuery, bot: Bot):
    if not is_superuser(callback.from_user.id):
        return await callback.answer("Нет доступа.", show_alert=True)

    app_id = int(callback.data.split("_")[1])
    app = await db.get_app(app_id)

    if not app:
        return await callback.answer("Заявка не найдена.", show_alert=True)
    if app["status"] != "pending":
        return await callback.answer("Заявка уже обработана.", show_alert=True)

    await db.update_status(app_id, "approved")
    await db.set_t_decision(app_id)
    await callback.answer("✅ Согласовано")
    await callback.message.edit_reply_markup(reply_markup=None)

    try:
        await bot.send_document(
            app["user_id"],
            document=app["pdf_file_id"],
            caption="✅ Ваша заявка согласована Правлением.",
        )
    except Exception as e:
        logger.error(
            "Failed to send approved PDF to user {} for app {}: {}",
            app["user_id"],
            app_id,
            e,
        )

    await callback.message.answer(
        f"Заявка #{app_id} согласована, документ отправлен автору."
    )
    logger.info("App {} approved by superuser {}", app_id, callback.from_user.id)
