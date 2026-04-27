import stdlib.db as db
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

router = Router()


@router.callback_query(F.data == "cancel_app")
async def on_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    app_id = data.get("app_id")

    if app_id:
        await db.delete_app(app_id)

    await state.clear()
    await callback.message.answer(
        "Заявка отменена. Чтобы создать новую — нажмите /start.",
    )
