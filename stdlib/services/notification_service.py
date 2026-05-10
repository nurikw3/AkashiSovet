"""Отправка уведомлений пользователям через Telegram Bot API."""

from __future__ import annotations

import html
import json

from aiogram import Bot
from aiogram.types import BufferedInputFile
from bot.config import config
from bot.logger import logger
import stdlib.db as db
from stdlib.pdf import get_app_pdf_buffer, generate_pdf_filename
from stdlib.template import get_template
from stdlib.timezone_util import now_app
from stdlib.timing import timed_task


async def _blocks_preview_html(blocks_raw, limit: int = 2600) -> str:
    """Короткий HTML-превью текста заявки для уведомления о доработке."""
    try:
        blocks = (
            json.loads(blocks_raw) if isinstance(blocks_raw, str) else (blocks_raw or {})
        )
    except Exception:
        blocks = {}
    if not isinstance(blocks, dict) or not blocks:
        return "<i>Текст заявки недоступен.</i>"

    tpl = await get_template()
    title_by_id = {b.id: b.title for b in tpl.blocks}

    lines: list[str] = []
    for k, v in sorted(
        blocks.items(), key=lambda x: int(str(x[0])) if str(x[0]).isdigit() else 999
    ):
        val = str(v or "").strip()
        if not val:
            continue
        bid = int(str(k)) if str(k).isdigit() else None
        title = title_by_id.get(bid, "Без названия") if bid is not None else "Без названия"
        lines.append(
            f"<b>Блок {html.escape(str(k))} — {html.escape(title)}</b>\n"
            f"<pre>{html.escape(val)}</pre>"
        )
    if not lines:
        return "<i>Текст заявки пуст.</i>"
    txt = "\n\n".join(lines)
    if len(txt) > limit:
        txt = txt[: limit - 1].rstrip() + "…"
    return txt


@timed_task("notify_user_application_approved")
async def notify_user_application_approved(
    bot: Bot,
    user_id: int,
    app_id: int,
    *,
    pdf_file_id: str | None = None,
) -> None:
    """
    Уведомляет автора о согласовании.
    Если передан `pdf_file_id` — отправляет документ как в боте; иначе короткое HTML-сообщение (как из веб-панели).
    """
    try:
        if pdf_file_id:
            await bot.send_document(
                user_id,
                document=pdf_file_id,
                caption="✅ Ваша заявка согласована Правлением.",
            )
        else:
            await bot.send_message(
                user_id,
                f"✅ <b>Ваша заявка #{app_id} успешно согласована!</b>\n\n"
                "Документ передан в дальнейшую работу.",
                parse_mode="HTML",
            )
    except Exception as e:
        logger.error(
            "Failed to notify user {} about approval for app {}: {}",
            user_id,
            app_id,
            e,
        )


async def broadcast_superusers_html(bot: Bot, text: str) -> None:
    """Рассылает HTML всем суперпользователям (например при ошибке генерации PDF)."""
    for su_id in config.SUPERUSER_IDS:
        try:
            await bot.send_message(su_id, text, parse_mode="HTML")
        except Exception as e:
            logger.error("Failed to broadcast to superuser {}: {}", su_id, e)


@timed_task("notify_user_application_rework")
async def notify_user_application_rework(
    bot: Bot,
    user_id: int,
    app_id: int,
    feedback: str,
    *,
    reply_markup: object | None = None,
    web_wording: bool = False,
) -> None:
    """Уведомляет автора о возврате на доработку."""
    app_row = await db.get_app(app_id)
    pdf_sent = False
    if app_row:
        try:
            # 1) Предпочтительно отправляем уже готовый Telegram file_id (самый надёжный путь).
            if app_row.get("pdf_file_id"):
                await bot.send_document(
                    user_id,
                    document=app_row["pdf_file_id"],
                    caption=f"📄 Актуальная версия заявки #{app_id}.",
                )
                pdf_sent = True
            # 2) Если file_id отсутствует — генерируем PDF заново.
            if not pdf_sent:
                pdf_buf = await get_app_pdf_buffer(app_id)
                full_name = await db.get_user_full_name(user_id)
                position = await db.get_user_position(user_id)
                created_at = app_row.get("created_at") or now_app()
                custom_filename = generate_pdf_filename(full_name, position, created_at)
                await bot.send_document(
                    user_id,
                    document=BufferedInputFile(
                        pdf_buf.getvalue(),
                        filename=custom_filename,
                    ),
                    caption=f"📄 Актуальная версия заявки #{app_id}.",
                )
                pdf_sent = True
        except Exception as e:
            logger.warning(
                "Failed to send rework PDF to user {} for app {}: {}",
                user_id,
                app_id,
                e,
            )

    preview_html = await _blocks_preview_html(app_row.get("blocks") if app_row else None)
    if web_wording:
        text = (
            f"❌ <b>Заявка #{app_id} возвращена на доработку.</b>\n\n"
            f"<b>Замечания:</b>\n{feedback}\n\n"
            f"<b>Текущая версия текста:</b>\n{preview_html}\n\n"
            "<i>Используйте кнопки ниже для редактирования:</i>"
        )
    else:
        text = (
            f"❌ Заявка #{app_id} возвращена на доработку.\n\n"
            f"<b>Замечания:</b>\n{feedback}\n\n"
            f"<b>Текущая версия текста:</b>\n{preview_html}\n\n"
            "Выберите блок для редактирования:"
        )
    try:
        await bot.send_message(
            user_id,
            text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    except Exception as e:
        logger.error(
            "Failed to notify user {} about rework for app {}: {}",
            user_id,
            app_id,
            e,
        )
