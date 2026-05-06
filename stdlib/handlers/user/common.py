from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from bot.logger import logger
from stdlib.services import application_service

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
            await application_service.delete_application(app_id)
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


@router.callback_query(F.data.startswith("cleanup_chat_"))
async def on_cleanup_chat(callback: CallbackQuery, state: FSMContext):
    """Мягкая чистка служебных сообщений бота по завершённой заявке."""
    await callback.answer()
    try:
        app_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректная кнопка.")
        return

    data = await state.get_data()
    stored_app_id = data.get("cleanup_app_id")
    if stored_app_id != app_id:
        await callback.message.answer(
            "Кнопка устарела. Отправьте заявку повторно и попробуйте ещё раз."
        )
        return

    chat_id = callback.message.chat.id
    to_delete = list(data.get("cleanup_bot_message_ids") or [])
    if callback.message:
        to_delete.append(callback.message.message_id)
    unique_ids = list(dict.fromkeys(to_delete))[-120:]

    deleted = 0
    for mid in reversed(unique_ids):
        try:
            await callback.bot.delete_message(chat_id=chat_id, message_id=mid)
            deleted += 1
        except Exception:
            # Старые/недоступные сообщения пропускаем.
            continue

    await state.clear()
    await callback.bot.send_message(
        chat_id=chat_id,
        text=f"✅ Чат очищен. Удалено служебных сообщений: {deleted}.",
    )
