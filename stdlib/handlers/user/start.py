import stdlib.db as db
import stdlib.keyboards as kb
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from stdlib.handlers.states import BotStates
from stdlib.template import get_template

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username

    full_name = await db.get_user_full_name(user_id)
    if not full_name:
        await message.answer(
            "Перед созданием заявки, пожалуйста, укажите ваше Ф.И.О. с помощью команды /register"
        )
        return

    current_state = await state.get_state()
    if current_state in (BotStates.FILLING, BotStates.REWORK, BotStates.FREE_FORM):
        await message.answer(
            "У вас есть незавершённая заявка. Что сделать?",
            reply_markup=kb.restart_or_continue_keyboard(),
        )
        return

    app_id = await db.get_or_create_app(user_id, username)
    await db.set_t_start(app_id)
    mode = await db.get_user_mode(user_id)

    if mode == "free":
        await state.set_state(BotStates.FREE_FORM)
        await state.update_data(app_id=app_id)
        await message.answer(
            "Вы в режиме <b>Свободного ввода</b>.\n\n"
            "Напишите всю суть вашей заявки в одном или нескольких сообщениях.\n"
            "Я проанализирую текст и задам уточняющие вопросы, если чего-то будет не хватать.",
            parse_mode="HTML",
        )
    else:
        tpl = await get_template()
        first = tpl.blocks[0]
        await state.set_state(BotStates.FILLING)
        await state.update_data(
            app_id=app_id, current_block=first.id, mode="input"
        )
        await message.answer(
            "Добрый день! Заполним служебную записку на Правление.\n\n"
            f"<b>Блок 1 из {tpl.total_blocks_count} — {first.title}</b>\n\n"
            f"{first.question}",
            parse_mode="HTML",
        )


@router.message(Command("mode"))
async def cmd_mode(message: Message):
    user_id = message.from_user.id
    current_mode = await db.get_user_mode(user_id)
    new_mode = "free" if current_mode == "step" else "step"
    await db.set_user_mode(user_id, new_mode)

    mode_name = (
        "Свободный ввод (ИИ сам соберёт заявку)"
        if new_mode == "free"
        else "Пошаговый (поля из шаблона)"
    )
    await message.answer(
        f"🔄 Режим изменен.\nТекущий режим: <b>{mode_name}</b>\n\nИспользуйте /start для создания новой заявки.",
        parse_mode="HTML",
    )


@router.message(Command("register"))
async def cmd_register(message: Message, state: FSMContext):
    await state.set_state(BotStates.REGISTERING)
    await message.answer(
        "Пожалуйста, введите ваше полное Ф.И.О. (например: Иванов Иван Иванович):"
    )


@router.message(BotStates.REGISTERING, F.text)
async def process_register(message: Message, state: FSMContext):
    full_name = message.text.strip()
    await db.set_user_full_name(message.from_user.id, full_name)
    await state.clear()
    await message.answer(
        f"✅ Ф.И.О. успешно сохранено: <b>{full_name}</b>\n\nТеперь вы можете создать заявку с помощью команды /start",
        parse_mode="HTML",
    )


@router.message(Command("position"))
async def cmd_position(message: Message, state: FSMContext):
    await state.set_state(BotStates.REGISTERING_POSITION)
    await message.answer(
        "📝 Пожалуйста, введите вашу должность (например: Руководитель отдела ИИ):"
    )


@router.message(BotStates.REGISTERING_POSITION, F.text)
async def process_position(message: Message, state: FSMContext):
    position = message.text.strip()
    await db.set_user_position(message.from_user.id, position)
    await state.clear()
    await message.answer(
        f"✅ Должность успешно сохранена: <b>{position}</b>\n\nТеперь она будет подставляться в подпись PDF.",
        parse_mode="HTML",
    )


@router.message(Command("sign"))
async def cmd_sign(message: Message, state: FSMContext):
    await state.set_state(BotStates.WAITING_SIGNATURE)
    await message.answer(
        "🖋️ <b>Загрузка подписи</b>\n\n"
        "Отправьте фото подписи одним сообщением.\n"
        "Бот сохранит её в базу и будет автоматически подставлять в PDF.",
        parse_mode="HTML",
    )


@router.message(BotStates.WAITING_SIGNATURE, F.photo)
async def save_signature(message: Message, state: FSMContext):
    # Берём фото в максимальном качестве
    photo = message.photo[-1]
    file = await message.bot.download(photo)
    img_bytes = file.read()

    # Сохраняем сырые байты (Telegram сам сжимает в JPG/PNG, ReportLab их понимает)
    await db.set_user_signature(message.from_user.id, img_bytes)

    await state.clear()
    await message.answer(
        "✅ <b>Подпись сохранена в базу!</b>\n\n"
        "Теперь при генерации PDF она появится вместо строки для ручной подписи.",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "continue_draft")
async def on_continue_draft(callback: CallbackQuery):
    await callback.answer("Продолжаем текущую заявку.")
    await callback.message.delete()


@router.callback_query(F.data == "restart_draft")
async def on_restart_draft(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    username = callback.from_user.username

    app_id = await db.get_or_create_app(user_id, username)
    await db.set_t_start(app_id)
    mode = await db.get_user_mode(user_id)

    if mode == "free":
        await state.set_state(BotStates.FREE_FORM)
        await state.update_data(app_id=app_id)
        await callback.message.answer(
            "Вы в режиме <b>Свободного ввода</b>.\n\n"
            "Опишите вашу заявку в свободной форме. Я задам вопросы, если что-то будет непонятно.",
            parse_mode="HTML",
        )
    else:
        tpl = await get_template()
        first = tpl.blocks[0]
        await state.set_state(BotStates.FILLING)
        await state.update_data(
            app_id=app_id, current_block=first.id, mode="input"
        )
        await callback.message.answer(
            f"<b>Блок 1 из {tpl.total_blocks_count} — {first.title}</b>\n\n"
            f"{first.question}",
            parse_mode="HTML",
        )
