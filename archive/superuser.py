from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import stdlib.db as db
import stdlib.keyboards as kb
from bot.config import config
from bot.logger import logger
from stdlib.handlers.user import BotStates

router = Router()


def is_superuser(user_id: int) -> bool:
    return user_id in config.SUPERUSER_IDS


# ─── Approve ─────────────────────────────────────────────────────────────────


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

    # Финальный PDF пользователю (переиспользуем file_id)
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


# ─── Reject → запрос фидбэка ────────────────────────────────────────────────


@router.callback_query(F.data.startswith("reject_"))
async def on_reject(callback: CallbackQuery, state: FSMContext):
    if not is_superuser(callback.from_user.id):
        return await callback.answer("Нет доступа.", show_alert=True)

    app_id = int(callback.data.split("_")[1])
    app = await db.get_app(app_id)

    if not app:
        return await callback.answer("Заявка не найдена.", show_alert=True)

    if app["status"] != "pending":
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


# ─── Получение текста замечаний ──────────────────────────────────────────────


@router.message(BotStates.SU_REJECT)
async def on_feedback(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    app_id = data["app_id"]
    feedback_text = message.text.strip()

    await db.update_status(app_id, "rework", feedback=feedback_text)
    await db.set_t_decision(app_id)
    await db.increment_reject_count(app_id)
    await state.clear()
    await message.answer(f"Замечания по заявке #{app_id} отправлены автору.")

    app = await db.get_app(app_id)

    try:
        await bot.send_message(
            app["user_id"],
            f"❌ Заявка #{app_id} возвращена на доработку.\n\n"
            f"<b>Замечания:</b>\n{feedback_text}\n\n"
            "Выберите блок для редактирования:",
            parse_mode="HTML",
            reply_markup=kb.rework_keyboard(),
        )
    except Exception as e:
        logger.error(
            "Failed to notify user {} about reject for app {}: {}",
            app["user_id"],
            app_id,
            e,
        )

    logger.info(
        "App {} rejected by superuser {} | feedback_len={}",
        app_id,
        message.from_user.id,
        len(feedback_text),
    )
