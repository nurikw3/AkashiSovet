import json
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, BufferedInputFile

import stdlib.db as db
import stdlib.llm as llm
import stdlib.pdf as pdf
import stdlib.keyboards as kb
from bot.config import config
from bot.logger import logger
from stdlib.handlers.blocks import BLOCKS
from aiogram.fsm.state import StatesGroup, State

router = Router()


class States:
    class States(StatesGroup):
        from aiogram.fsm.state import State

        FILLING = State()
        REWORK = State()
        SU_REJECT = State()


class BotStates(StatesGroup):
    FILLING = State()
    REWORK = State()
    SU_REJECT = State()
    REGISTERING = State()
    FREE_FORM = State()
    REVIEW = State()


# ─── /start ──────────────────────────────────────────────────────────────────


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username

    # Проверка на наличие ФИО
    full_name = await db.get_user_full_name(user_id)
    if not full_name:
        await message.answer(
            "Перед созданием заявки, пожалуйста, укажите ваше Ф.И.О. с помощью команды /register"
        )
        return

    current_state = await state.get_state()

    # Если уже идёт заполнение — спросить продолжить или заново
    if current_state in (BotStates.FILLING, BotStates.REWORK, BotStates.FREE_FORM):
        await message.answer(
            "У вас есть незавершённая заявка. Что сделать?",
            reply_markup=kb.restart_or_continue_keyboard(),
        )
        return

    app_id = await db.get_or_create_app(user_id, username)
    await db.set_t_start(app_id)  # t_start время старта
    mode = await db.get_user_mode(user_id)

    if mode == "free":
        await state.set_state(BotStates.FREE_FORM)
        await state.update_data(app_id=app_id)
        await message.answer(
            "Вы в режиме <b>Свободного ввода</b>.\n\n"
            "Напишите всю суть вашей заявки в одном или нескольких сообщениях (что произошло, зачем выносим, предлагаемое решение и риски).\n"
            "Я проанализирую текст и задам уточняющие вопросы, если чего-то будет не хватать.",
            parse_mode="HTML",
        )
    else:
        await state.set_state(BotStates.FILLING)
        await state.update_data(app_id=app_id, current_block=1, mode="input")
        await message.answer(
            f"Добрый день! Заполним служебную записку на Правление.\n\n"
            f"<b>Блок 1 из 5 — {BLOCKS[1]['title']}</b>\n\n"
            f"{BLOCKS[1]['question']}",
            parse_mode="HTML",
        )


# ─── Выбор режима ────────────────────────────────────────────────────────────


@router.message(Command("mode"))
async def cmd_mode(message: Message):
    user_id = message.from_user.id
    current_mode = await db.get_user_mode(user_id)
    new_mode = "free" if current_mode == "step" else "step"
    await db.set_user_mode(user_id, new_mode)

    mode_name = (
        "Свободный ввод (ИИ сам соберёт заявку)"
        if new_mode == "free"
        else "Пошаговый (5 вопросов)"
    )
    await message.answer(
        f"🔄 Режим изменен.\nТекущий режим: <b>{mode_name}</b>\n\nИспользуйте /start для создания новой заявки.",
        parse_mode="HTML",
    )


# ─── Регистрация ФИО ─────────────────────────────────────────────────────────


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


@router.callback_query(F.data == "continue_draft")
async def on_continue_draft(callback: CallbackQuery):
    await callback.answer("Продолжаем текущую заявку.")
    await callback.message.delete()


@router.callback_query(F.data == "restart_draft")
async def on_restart_draft(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    username = callback.from_user.username

    # Новый черновик
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
        await state.set_state(BotStates.FILLING)
        await state.update_data(app_id=app_id, current_block=1, mode="input")
        await callback.message.answer(
            f"<b>Блок 1 из 5 — {BLOCKS[1]['title']}</b>\n\n{BLOCKS[1]['question']}",
            parse_mode="HTML",
        )


# ─── Ввод текста блока ───────────────────────────────────────────────────────


@router.message(BotStates.FILLING, F.text)
async def handle_block_input(message: Message, state: FSMContext):
    data = await state.get_data()

    if data["mode"] == "confirm":
        return

    current_block = data["current_block"]
    if current_block == "files":
        return

    raw_text = message.text.strip()
    logger.debug(
        "Block input | app_id={} block={} len={}",
        data["app_id"],
        current_block,
        len(raw_text),
    )

    app = await db.get_app(data["app_id"])
    context_blocks = json.loads(app["blocks"]) if app and app["blocks"] else {}

    formatted = await llm.format_text(
        raw_text,
        context_blocks=context_blocks,
        user_id=message.from_user.id,
        app_id=data["app_id"],
    )
    await db.save_block(data["app_id"], current_block, formatted)

    changed = formatted.strip() != raw_text.strip()
    intro = (
        "Текст приведён к деловому стилю:" if changed else "Текст принят без изменений:"
    )

    await state.update_data(mode="confirm")
    await message.answer(
        f"{intro}\n\n<i>{formatted}</i>\n\nВсё верно?",
        parse_mode="HTML",
        reply_markup=kb.confirm_keyboard(),
    )


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

        # Переводим пользователя на этап файлов
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


# ─── Подтверждение / Исправление ─────────────────────────────────────────────


@router.callback_query(BotStates.FILLING, F.data == "confirm")
async def on_confirm(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    current_block = data.get("current_block")

    if data.get("returning_to") == "review":
        await state.set_state(BotStates.REVIEW)
        await state.update_data(returning_to=None)
        await send_review_screen(callback, data["app_id"])
        return

    if current_block < 5:
        next_block = current_block + 1
        await state.update_data(current_block=next_block, mode="input")
        await callback.message.answer(
            f"<b>Блок {next_block} из 5 — {BLOCKS[next_block]['title']}</b>\n\n"
            f"{BLOCKS[next_block]['question']}",
            parse_mode="HTML",
        )
    else:
        await state.update_data(current_block="files", mode="input")
        await callback.message.answer(
            "Отлично! Все разделы заполнены.\n\n"
            "<b>Приложения</b>\n\n"
            "Прикрепите файлы к заявке (договоры, расчёты, согласования и т.д.).\n"
            "Отправляйте по одному. Когда закончите — нажмите <b>Готово</b>.",
            parse_mode="HTML",
            reply_markup=kb.files_keyboard(),
        )


@router.callback_query(BotStates.FILLING, F.data == "edit")
async def on_edit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await state.update_data(mode="input")
    block_title = BLOCKS[data["current_block"]]["title"]
    await callback.message.answer(
        f"Введите исправленный текст для блока «{block_title}»:"
    )


# ─── Загрузка файлов ─────────────────────────────────────────────────────────


@router.message(BotStates.FILLING, F.document | F.photo)
async def handle_file(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("current_block") != "files":
        return

    app = await db.get_app(data["app_id"])
    attachments = json.loads(app["attachments"])

    if message.document:
        attachments.append(
            {
                "file_id": message.document.file_id,
                "name": message.document.file_name,
            }
        )
    elif message.photo:
        name = f"фото_{len(attachments) + 1}.jpg"
        attachments.append({"file_id": message.photo[-1].file_id, "name": name})

    await db.save_attachments(data["app_id"], attachments)
    logger.info("File attached | app_id={} total={}", data["app_id"], len(attachments))

    await message.answer(
        f"✅ Файл принят. Всего приложений: {len(attachments)}",
        reply_markup=kb.files_keyboard(),
    )


# ─── Финализация и отправка на согласование ──────────────────────────────────


async def finalize_and_notify(
    callback: CallbackQuery,
    state: FSMContext,
    app_id: int,
    bot: Bot,
) -> None:
    app = await db.get_app(app_id)
    blocks = json.loads(app["blocks"])
    attachments = json.loads(app["attachments"])

    full_name = await db.get_user_full_name(callback.from_user.id)
    display_name = (
        full_name
        if full_name
        else (callback.from_user.username or str(callback.from_user.id))
    )

    pdf_data = {
        "topic": blocks.get("1", ""),
        "description": blocks.get("2", ""),
        "basis": blocks.get("3", ""),
        "solution": blocks.get("4", ""),
        "risks": blocks.get("5", ""),
        "attachments": [a["name"] for a in attachments],
        "username": display_name,
        "date": datetime.today().strftime("%d.%m.%Y"),
        "app_id": app_id,
    }

    try:
        pdf_buffer = await pdf.generate_pdf(pdf_data)
    except Exception as e:
        logger.error("PDF generation error for app_id={}: {}", app_id, e)
        # Уведомляем СУ текстом
        text_fallback = (
            f"⚠️ <b>Новая заявка #{app_id}</b> (PDF не сгенерирован)\n\n"
            + "\n".join(f"<b>Блок {k}:</b> {v}" for k, v in blocks.items())
        )
        for su_id in config.SUPERUSER_IDS:
            await bot.send_message(su_id, text_fallback, parse_mode="HTML")
        await db.update_status(app_id, "pending")
        await callback.message.answer(
            "📤 Заявка отправлена (без PDF — техническая ошибка)."
        )
        await state.clear()
        return

    await db.update_status(app_id, "pending")
    await db.set_t_submit(app_id)
    await callback.message.answer_document(
        document=BufferedInputFile(
            pdf_buffer.getvalue(), filename=f"application_{app_id}.pdf"
        ),
        caption="📤 Заявка успешно сформирована и отправлена на согласование. Копия приложена выше.",
    )

    for su_id in config.SUPERUSER_IDS:
        try:
            msg = await bot.send_document(
                su_id,
                document=BufferedInputFile(
                    pdf_buffer.getvalue(), filename=f"application_{app_id}.pdf"
                ),
                caption=(
                    f"📋 Новая заявка #{app_id} от @{callback.from_user.username or callback.from_user.id}\n"
                    f"📎 Приложений: {len(attachments)}"
                ),
                reply_markup=kb.approve_reject_keyboard(app_id),
            )
            await db.update_status(app_id, "pending", pdf_file_id=msg.document.file_id)

            if attachments:
                await bot.send_message(su_id, "📁 Приложения к заявке:")
                for att in attachments:
                    await bot.send_document(
                        su_id, document=att["file_id"], caption=att["name"]
                    )
        except Exception as e:
            logger.error(
                "Failed to notify superuser {} for app {}: {}", su_id, app_id, e
            )

    logger.info(
        "App {} submitted for review | attachments={}", app_id, len(attachments)
    )
    await state.clear()


@router.callback_query(BotStates.FILLING, F.data.in_({"files_done", "files_skip"}))
async def on_files_done(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    data = await state.get_data()
    app_id = data["app_id"]

    if data.get("returning_to") == "review":
        await state.set_state(BotStates.REVIEW)
        await state.update_data(returning_to=None)
        await send_review_screen(callback, app_id)
    else:
        await state.set_state(BotStates.REVIEW)
        await send_review_screen(callback, app_id)


# ─── Экран ревью перед отправкой ─────────────────────────────────────────────


async def send_review_screen(message_or_callback, app_id: int):
    # 1. Получаем заявку из базы
    app_raw = await db.get_app(app_id)
    blocks = json.loads(app_raw.get("blocks", "{}"))

    # 2. ДОБАВЛЯЕМ ЧИСТКУ ФАЙЛОВ ДЛЯ ТЕЛЕГРАМ-БОТА
    raw_att = app_raw.get("attachments")
    clean_atts = []
    if raw_att:
        # Если это строка из БД, парсим её
        if isinstance(raw_att, str):
            try:
                raw_att = json.loads(raw_att.replace("'", '"'))
            except:
                raw_att = []

        # Вытаскиваем только имена
        for f in raw_att:
            if isinstance(f, dict):
                clean_atts.append(f.get("name") or f.get("file_name") or "Файл")
            else:
                clean_atts.append(str(f))

    # 3. Собираем данные для PDF с ОЧИЩЕННЫМИ файлами
    pdf_data = {
        "app_id": app_id,
        "topic": blocks.get("1", "Без темы"),
        "description": blocks.get("2", ""),
        "basis": blocks.get("3", ""),
        "solution": blocks.get("4", ""),
        "risks": blocks.get("5", ""),
        "attachments": clean_atts,  # <--- ПЕРЕДАЕМ ТОЛЬКО СПИСОК ИМЕН
        "full_name": await db.get_user_full_name(app_raw["user_id"]),
        "position": await db.get_user_position(app_raw["user_id"]),
        "date": app_raw["created_at"].strftime("%d.%m.%Y"),
    }

    # 4. Генерируем красивый PDF
    pdf_buf = await generate_pdf(pdf_data, user_id=app_raw["user_id"])


@router.callback_query(BotStates.REVIEW, F.data.startswith("review_edit_"))
async def on_review_edit(callback: CallbackQuery, state: FSMContext):
    block_num = int(callback.data.split("_")[2])
    await state.update_data(
        current_block=block_num, mode="input", returning_to="review"
    )
    await state.set_state(BotStates.FILLING)
    await callback.message.answer(
        f"<b>Редактирование: Блок {block_num} — {BLOCKS[block_num]['title']}</b>\n\nВведите новый текст для этого блока:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(BotStates.REVIEW, F.data == "review_files")
async def on_review_files(callback: CallbackQuery, state: FSMContext):
    await state.update_data(current_block="files", returning_to="review")
    await state.set_state(BotStates.FILLING)
    await callback.message.answer(
        "Прикрепите дополнительные файлы. Нажмите <b>Готово</b>, когда закончите.",
        parse_mode="HTML",
        reply_markup=kb.files_keyboard(),
    )
    await callback.answer()


@router.callback_query(BotStates.REVIEW, F.data == "review_submit")
async def on_review_submit(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    data = await state.get_data()
    await finalize_and_notify(callback, state, data["app_id"], bot)


# ─── Доработка (Rework) ───────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("rework_block_"))
async def on_rework_select(callback: CallbackQuery, state: FSMContext):
    block_num = int(callback.data.split("_")[2])
    await callback.answer()

    app = await db.get_last_rework_app(callback.from_user.id)
    if not app:
        await callback.answer("Нет заявок на доработку.", show_alert=True)
        return

    blocks = json.loads(app["blocks"])
    current_text = blocks.get(str(block_num), "")

    await state.set_state(BotStates.REWORK)
    await state.update_data(app_id=app["id"], rework_block=block_num, mode="input")
    await callback.message.answer(
        f"<b>Текущий текст блока «{BLOCKS[block_num]['title']}»:</b>\n\n"
        f"<i>{current_text}</i>\n\n"
        "Введите исправленный вариант:",
        parse_mode="HTML",
    )


@router.message(BotStates.REWORK, F.text)
async def on_rework_input(message: Message, state: FSMContext):
    data = await state.get_data()
    if data["mode"] == "confirm":
        return

    app = await db.get_app(data["app_id"])
    context_blocks = json.loads(app["blocks"]) if app and app["blocks"] else {}

    formatted = await llm.format_text(
        message.text.strip(),
        context_blocks=context_blocks,
        user_id=message.from_user.id,
        app_id=data["app_id"],
    )
    await db.save_block(data["app_id"], data["rework_block"], formatted)

    changed = formatted.strip() != message.text.strip()
    intro = (
        "Текст приведён к деловому стилю:" if changed else "Текст принят без изменений:"
    )

    await state.update_data(mode="confirm")
    await message.answer(
        f"{intro}\n\n<i>{formatted}</i>\n\nВсё верно?",
        parse_mode="HTML",
        reply_markup=kb.confirm_rework_keyboard(),
    )


@router.callback_query(BotStates.REWORK, F.data == "rework_confirm")
async def on_rework_confirmed(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(mode="input")
    await callback.message.answer(
        "Выберите другой блок для правки или отправьте заявку повторно:",
        reply_markup=kb.rework_keyboard(),
    )


@router.callback_query(BotStates.REWORK, F.data == "rework_edit")
async def on_rework_edit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await state.update_data(mode="input")
    block_title = BLOCKS[data["rework_block"]]["title"]
    await callback.message.answer(
        f"Введите исправленный текст для блока «{block_title}»:"
    )


@router.callback_query(BotStates.REWORK, F.data == "rework_submit")
async def on_rework_submit(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    data = await state.get_data()
    await finalize_and_notify(callback, state, data["app_id"], bot)
