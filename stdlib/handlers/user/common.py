from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from bot.logger import logger
import stdlib.db as db

router = Router()


@router.callback_query(F.data == "cancel_app")
async def on_cancel_app(callback: CallbackQuery, state: FSMContext):
    """Универсальный обработчик отмены заявки из любого состояния."""
    # 1. Получаем данные из текущего состояния
    data = await state.get_data()
    app_id = data.get("app_id")

    # 2. Удаляем черновик из базы данных
    if app_id:
        try:
            await db.delete_app(app_id)
            logger.info("User {} deleted app {}", callback.from_user.id, app_id)
        except Exception as e:
            logger.error("Failed to delete app {} on cancel: {}", app_id, e)

    # 3. Полностью сбрасываем FSM (состояние пользователя)
    await state.clear()

    # 4. Убираем кнопки и уведомляем пользователя
    await callback.answer("Заявка удалена")

    # Редактируем сообщение, чтобы кнопки исчезли и текст обновился
    await callback.message.edit_text(
        "❌ <b>Заявка полностью отменена и удалена.</b>\n\n"
        "Чтобы создать новую, введите /start.",
        parse_mode="HTML",
    )
