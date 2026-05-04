import json
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BufferedInputFile,
)
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
import stdlib.keyboards as kb
from stdlib.pdf import get_app_pdf_buffer
from stdlib.handlers.states import BotStates
from stdlib.template import get_template
from bot.logger import logger
from stdlib.services import application_service

router = Router()
ITEMS_PER_PAGE = 5

STATUS_MAP = {
    "draft": "✏️ Черновик",
    "pending": "⏳ На рассмотрении",
    "approved": "✅ Одобрено",
    "rework": "🔄 На доработке",
}


def _status_label(status: str | None) -> str:
    return STATUS_MAP.get(status, "📄 Новый")


async def _get_apps_page(user_id: int, page: int = 1) -> tuple[list[dict], int, int]:
    raw_apps = await application_service.list_user_applications(user_id)
    apps = [dict(r) for r in raw_apps]  # asyncpg.Record -> dict
    if not apps:
        return [], 1, 1

    apps.sort(key=lambda x: x.get("created_at") or 0, reverse=True)
    total = len(apps)
    total_pages = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    page = max(1, min(page, total_pages))
    start = (page - 1) * ITEMS_PER_PAGE
    return apps[start : start + ITEMS_PER_PAGE], page, total_pages


def _format_card(app: dict) -> str:
    app_id = app.get("id")
    topic = "Без темы"
    blocks = app.get("blocks")
    if blocks:
        try:
            b = json.loads(blocks) if isinstance(blocks, str) else blocks
            if isinstance(b, dict):
                topic = b.get("1", "Без темы")[:30]
        except Exception:
            pass

    created = app.get("created_at")
    date_str = (
        created.strftime("%d.%m %H:%M")
        if hasattr(created, "strftime")
        else str(created)[:16]
    )
    return f"<b>#{app_id}</b> | {topic}\n📅 {date_str} | {_status_label(app.get('status'))}"


async def _safe_edit(msg, text: str, reply_markup=None, parse_mode="HTML"):
    """Универсальная функция: редактирует или отправляет новое сообщение"""
    try:
        await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        return
    except TelegramBadRequest as e:
        if "message is not modified" in e.message:
            return
        if (
            "message can't be edited" in e.message
            or "message to edit not found" in e.message
        ):
            # 🔥 Фоллбэк: отправляем новое сообщение
            try:
                await msg.delete()
            except Exception:
                pass
            await msg.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
            return
        logger.warning("Msg edit failed: {}", e)
    except Exception as e:
        logger.warning("Unexpected send/edit failed: {}", e)
        # Фоллбэк на отправку нового
        try:
            await msg.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            pass


async def _render_list(source, state, user_id: int, page: int):
    apps, curr, total = await _get_apps_page(user_id, page)
    if not apps:
        txt = "📭 Заявок нет. Создайте через /start"
        kb_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Закрыть", callback_data="apps_close")]
            ]
        )
        await _safe_edit(
            source if isinstance(source, Message) else source.message, txt, kb_markup
        )
        return

    lines = [f"📋 <b>Ваши заявки</b> ({curr}/{total})\n"]
    kb_rows = []
    for app in apps:
        lines.append(_format_card(app))
        kb_rows.append(
            [
                InlineKeyboardButton(
                    text=f"👁️ #{app.get('id')}",
                    callback_data=f"apps_view_{app.get('id')}",
                )
            ]
        )

    nav = []
    nav.append(
        InlineKeyboardButton(text="◀️", callback_data=f"apps_pg_{curr - 1}")
        if curr > 1
        else InlineKeyboardButton(text="⚪", callback_data="noop")
    )
    nav.append(InlineKeyboardButton(text=f" {curr}/{total} ", callback_data="noop"))
    nav.append(
        InlineKeyboardButton(text="▶️", callback_data=f"apps_pg_{curr + 1}")
        if curr < total
        else InlineKeyboardButton(text="⚪", callback_data="noop")
    )
    kb_rows.append(nav)
    kb_rows.append(
        [InlineKeyboardButton(text="🏠 Закрыть", callback_data="apps_close")]
    )

    txt = "\n\n".join(lines)
    await _safe_edit(
        source if isinstance(source, Message) else source.message,
        txt,
        InlineKeyboardMarkup(inline_keyboard=kb_rows),
    )


@router.message(Command("my_apps"))
async def cmd_my_apps(message: Message, state: FSMContext):
    await state.clear()
    await _render_list(message, state, message.from_user.id, 1)


@router.callback_query(F.data.startswith("apps_pg_"))
async def cb_page(callback: CallbackQuery, state: FSMContext):
    if callback.data.endswith("_0") or "noop" in callback.data:
        return await callback.answer()
    await callback.answer()
    await _render_list(
        callback, state, callback.from_user.id, int(callback.data.split("_")[-1])
    )


@router.callback_query(F.data.startswith("apps_view_"))
async def cb_view(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    app_id = int(callback.data.split("_")[-1])
    app = await application_service.get_application(app_id)
    if not app:
        return await callback.message.answer("❌ Заявка не найдена")

    tpl = await get_template()
    first_key = str(tpl.first_block_id)
    topic = (
        app.blocks.get(first_key, "Без темы") if app.blocks else "Без темы"
    )

    status = app.status
    created = app.created_at
    date_str = (
        created.strftime("%d.%m.%Y %H:%M")
        if hasattr(created, "strftime")
        else str(created)
    )

    txt = (
        f"📄 <b>Заявка #{app_id}</b>\n"
        f"📌 Тема: {topic}\n"
        f"📊 Статус: {_status_label(status)}\n"
        f"📅 Создана: {date_str}\n"
    )

    kb_rows = [[InlineKeyboardButton(text="📥 PDF", callback_data=f"apps_dl_{app_id}")]]
    if status == "rework":
        kb_rows.append(
            [
                InlineKeyboardButton(
                    text="✏️ Редактировать", callback_data=f"apps_rework_{app_id}"
                )
            ]
        )

    # 🔥 Удалять можно на ЛЮБОМ статусе
    kb_rows.append(
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"apps_del_{app_id}")]
    )
    kb_rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="apps_back")])

    await _safe_edit(
        callback.message, txt, InlineKeyboardMarkup(inline_keyboard=kb_rows)
    )


@router.callback_query(F.data.startswith("apps_dl_"))
async def cb_dl(callback: CallbackQuery):
    await callback.answer("⏳ Генерация...")
    app_id = int(callback.data.split("_")[-1])
    try:
        buf = await get_app_pdf_buffer(app_id)
        input_file = BufferedInputFile(file=buf.read(), filename=f"app_{app_id}.pdf")
        await callback.message.answer_document(
            document=input_file, caption=f"📄 #{app_id}"
        )
    except Exception as e:
        logger.error("PDF err: {}", e)
        await callback.message.answer("❌ Ошибка генерации PDF")


@router.callback_query(F.data.startswith("apps_del_ok_"))
async def cb_del_ok(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    app_id = int(callback.data.split("_")[-1])
    app = await application_service.get_application(app_id)

    if not app or app.user_id != callback.from_user.id:
        return await callback.message.answer("❌ Нельзя удалить эту заявку")

    try:
        await application_service.delete_application(app_id)
        state_data = await state.get_data()
        if state_data.get("app_id") == app_id:
            await state.clear()

        # Сначала показываем список (edit текущего сообщения), потом уведомление
        await _render_list(callback, state, callback.from_user.id, 1)
        await callback.message.answer(f"✅ Заявка #{app_id} успешно удалена.")

    except Exception as e:
        logger.error("Del err: {}", e)
        await callback.message.answer("❌ Ошибк а удаления")


@router.callback_query(F.data.startswith("apps_del_"))
async def cb_del(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    app_id = int(callback.data.split("_")[-1])
    kb_markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, удалить", callback_data=f"apps_del_ok_{app_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена", callback_data=f"apps_view_{app_id}"
                )
            ],
        ]
    )
    await _safe_edit(
        callback.message,
        f"⚠️ Удалить заявку #{app_id}?\nЭто действие нельзя отменить.",
        kb_markup,
    )


@router.callback_query(F.data.startswith("apps_rework_"))
async def cb_rework_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    app_id = int(callback.data.split("_")[-1])
    app = await application_service.get_application(app_id)
    if (
        not app
        or app.user_id != callback.from_user.id
        or app.status != "rework"
    ):
        return await callback.message.answer("❌ Нельзя редактировать")

    await state.clear()
    tpl = await get_template()
    await state.set_state(BotStates.REWORK)
    await state.update_data(
        app_id=app_id, rework_block=tpl.first_block_id, mode="input"
    )
    await callback.message.delete()
    await callback.message.answer(
        "✏️ <b>Режим доработки</b>\n\nВыберите блок:",
        reply_markup=kb.rework_keyboard(tpl),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "apps_back")
async def cb_back(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _render_list(callback, state, callback.from_user.id, 1)


@router.callback_query(F.data == "apps_close")
async def cb_close(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        await callback.message.answer("👋 Список закрыт.")


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()
