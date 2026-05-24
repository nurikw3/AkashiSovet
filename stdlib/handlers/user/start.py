import stdlib.db as db
import stdlib.keyboards as kb
from stdlib.services import application_service, file_service
import json
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from bot.config import config
from stdlib.handlers.states import BotStates
from stdlib.template import get_template
from stdlib.telegram_ui import render_nav_screen
from bot.logger import logger
router = Router()


HELP_TEXT_SETTINGS_KEY = "user_help_text"


def _default_help_text() -> str:
    return (
        "📘 <b>Как пользоваться ботом AKASHI</b>\n\n"
        "1) Заполните профиль:\n"
        "• /register — ФИО и должность\n"
        "\n"
        "2) Создайте заявку: /start\n"
        "3) Заполните блоки, добавьте файлы и отправьте на согласование.\n\n"
        "Полезные команды:\n"
        "• /mode — переключить режим (пошаговый / свободный)\n"
        "• /web — вход в веб-панель\n"
        "• /myapps — мои заявки"
    )


async def _get_help_text() -> str:
    raw = await db.get_setting(HELP_TEXT_SETTINGS_KEY)
    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except Exception:
            data = None
    if isinstance(data, dict):
        txt = str(data.get("text") or "").strip()
        if txt:
            return txt
    return _default_help_text()


async def _ensure_profile_complete(message: Message) -> bool:
    """Проверяет обязательные поля профиля перед началом заявки."""
    user_id = message.from_user.id
    full_name = await db.get_user_full_name(user_id)
    position = await db.get_user_position(user_id)

    if full_name and position:
        return True

    await message.answer(
        "Перед созданием заявки заполните профиль командой /register."
    )
    return False


async def _is_user_allowed_for_restricted_commands(user_id: int) -> bool:
    logger.info(f"{user_id} прошел")
    if user_id in config.SUPERUSER_IDS:
        return True
    # return await db.is_user_allowed(user_id)
    return True


async def _prompt_creation_path(message: Message | CallbackQuery, state: FSMContext, app_id: int):
    user_id = message.from_user.id if isinstance(message, Message) else message.from_user.id
    mode = await db.get_user_mode(user_id)
    mode_name = (
        "свободный ввод"
        if mode == "free"
        else "пошаговое заполнение"
    )
    await state.set_state(BotStates.START_CHOICE)
    await state.update_data(app_id=app_id)
    await render_nav_screen(
        message,
        state,
        "Выберите, как создать заявку:\n\n"
        f"• Текущий режим заполнения в боте: <b>{mode_name}</b>\n"
        "• Или загрузите уже готовый PDF-документ.",
        kb.start_creation_path_keyboard(),
        parse_mode="HTML",
    )


async def _enter_fill_flow(target: Message | CallbackQuery, state: FSMContext, app_id: int):
    from stdlib.handlers.user.filling import send_block_input_screen

    user_id = target.from_user.id if isinstance(target, Message) else target.from_user.id
    mode = await db.get_user_mode(user_id)

    if mode == "free":
        await state.set_state(BotStates.FREE_FORM)
        await state.update_data(app_id=app_id)
        await render_nav_screen(
            target,
            state,
            "Вы в режиме <b>Свободного ввода</b>.\n\n"
            "Напишите всю суть вашей заявки в одном или нескольких сообщениях.\n"
            "Я проанализирую текст и задам уточняющие вопросы, если чего-то будет не хватать.",
            kb.free_form_keyboard(),
            parse_mode="HTML",
        )
    else:
        tpl = await get_template()
        first = tpl.blocks[0]
        await state.set_state(BotStates.FILLING)
        await state.update_data(app_id=app_id, current_block=first.id, mode="input")
        await send_block_input_screen(
            target,
            state,
            first.id,
            intro="Добрый день! Заполним пояснительную записку на Правление.",
        )


@router.message(Command("help"))
async def cmd_help(message: Message):
    if not await _is_user_allowed_for_restricted_commands(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к этой команде. Обратитесь к администратору.")
        return

    txt = await _get_help_text()
    try:
        await message.answer(txt, parse_mode="HTML")
    except Exception:
        await message.answer(txt)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username

    if not await _is_user_allowed_for_restricted_commands(user_id):
        await message.answer("⛔ У вас нет доступа к созданию заявки. Обратитесь к администратору.")
        return

    if not await _ensure_profile_complete(message):
        return

    current_state = await state.get_state()
    if current_state in (
        BotStates.START_CHOICE,
        BotStates.WAITING_MAIN_PDF,
        BotStates.FILLING,
        BotStates.REWORK,
        BotStates.FREE_FORM,
    ):
        await message.answer(
            "У вас есть незавершённая заявка. Что сделать?",
            reply_markup=kb.restart_or_continue_keyboard(),
        )
        return

    await state.clear()
    app_id = await application_service.get_or_create_draft(user_id, username)
    await application_service.clear_application_chat_history(app_id)
    await application_service.mark_application_started(app_id)
    await _prompt_creation_path(message, state, app_id)


@router.message(Command("mode"))
async def cmd_mode(message: Message):
    user_id = message.from_user.id
    current_mode = await db.get_user_mode(user_id)
    new_mode = "free" if current_mode == "step" else "step"
    await db.set_user_mode(user_id, new_mode)

    draft_id = await application_service.get_draft_application_id_for_user(user_id)
    if draft_id:
        await application_service.clear_application_chat_history(draft_id)

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
    await state.update_data(register_flow=True)
    await state.set_state(BotStates.REGISTERING)
    await message.answer(
        "Пожалуйста, введите ваше полное Ф.И.О. (например: Иванов Иван Иванович):"
    )


@router.message(BotStates.REGISTERING, F.text)
async def process_register(message: Message, state: FSMContext):
    full_name = message.text.strip()
    if not full_name:
        await message.answer("Ф.И.О. не может быть пустым. Введите Ф.И.О. ещё раз.")
        return

    await state.update_data(full_name=full_name, register_flow=True)
    await state.set_state(BotStates.REGISTERING_POSITION)
    await message.answer(
        "✅ Ф.И.О. принято.\n\nТеперь введите вашу должность:",
        parse_mode="HTML",
    )


@router.message(Command("position"))
async def cmd_position(message: Message, state: FSMContext):
    await state.update_data(register_flow=False)
    await state.set_state(BotStates.REGISTERING_POSITION)
    await message.answer(
        "📝 Пожалуйста, введите вашу должность (например: Руководитель отдела ИИ):"
    )


@router.message(BotStates.REGISTERING_POSITION, F.text)
async def process_position(message: Message, state: FSMContext):
    position = message.text.strip()
    if not position:
        await message.answer("Должность не может быть пустой. Введите должность ещё раз.")
        return

    data = await state.get_data()
    if data.get("register_flow"):
        full_name = (data.get("full_name") or "").strip()
        if not full_name:
            await state.set_state(BotStates.REGISTERING)
            await message.answer(
                "Не удалось найти Ф.И.О. в текущей сессии. Введите Ф.И.О. заново:"
            )
            return
        await db.set_user_full_name(message.from_user.id, full_name)
        await db.set_user_position(message.from_user.id, position)
        await state.clear()
        await message.answer(
            "✅ Профиль успешно заполнен.\n\n"
            f"Ф.И.О.: <b>{full_name}</b>\n"
            f"Должность: <b>{position}</b>\n\n"
            "Теперь можно создавать заявку через /start.",
            parse_mode="HTML",
        )
        return

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
        "Отправьте фото (1:1 , белый фон) подписи одним сообщением. \n"
        "Бот сохранит её в базу и будет автоматически подставлять в PDF.",
        parse_mode="HTML",
    )


@router.message(BotStates.WAITING_SIGNATURE, F.photo)
async def save_signature(message: Message, state: FSMContext):
    # Берём фото в максимальном качестве
    photo = message.photo[-1]
    file = await message.bot.download(photo)
    img_bytes = file.read()

    # Загружаем в S3, в БД — только ключ (generate_pdf скачивает изображение по ключу)
    key = await file_service.upload_signature_image(message.from_user.id, img_bytes)
    await db.set_user_signature(message.from_user.id, key)

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

    if not await _ensure_profile_complete(callback.message):
        return

    await state.clear()
    app_id = await application_service.get_or_create_draft(user_id, username)
    await application_service.reset_draft_for_new_session(app_id)
    await application_service.mark_application_started(app_id)
    await _prompt_creation_path(callback, state, app_id)


@router.callback_query(BotStates.START_CHOICE, F.data == "start_flow_fill")
async def on_start_flow_fill(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    app_id = data.get("app_id")
    if not app_id:
        await callback.answer("Черновик не найден.", show_alert=True)
        return
    await callback.answer()
    await _enter_fill_flow(callback, state, app_id)


@router.callback_query(BotStates.START_CHOICE, F.data == "start_flow_pdf")
async def on_start_flow_pdf(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    app_id = data.get("app_id")
    if not app_id:
        await callback.answer("Черновик не найден.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(BotStates.WAITING_MAIN_PDF)
    await state.update_data(app_id=app_id)
    await render_nav_screen(
        callback,
        state,
        "📄 Отправьте готовый PDF заявки одним сообщением.\n\n"
        "После загрузки можно будет добавить приложения и отправить заявку.",
        kb.main_pdf_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(BotStates.WAITING_MAIN_PDF, F.data == "main_pdf_back")
async def on_main_pdf_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    app_id = data.get("app_id")
    if not app_id:
        await callback.answer("Черновик не найден.", show_alert=True)
        return
    await callback.answer()
    await _prompt_creation_path(callback, state, app_id)


@router.callback_query(BotStates.FREE_FORM, F.data == "free_form_back")
async def on_free_form_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    app_id = data.get("app_id")
    if not app_id:
        await callback.answer("Черновик не найден.", show_alert=True)
        return
    await callback.answer()
    await _prompt_creation_path(callback, state, app_id)
