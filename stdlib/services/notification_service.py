"""Отправка уведомлений пользователям через Telegram Bot API."""

from __future__ import annotations

import asyncio
import html
import io
import json

from aiogram import Bot
from aiogram.types import BufferedInputFile
from bot.config import config
from bot.logger import logger
import stdlib.db as db
import stdlib.s3 as s3
from stdlib.pdf import get_app_pdf_buffer, resolve_application_pdf_filename
from stdlib.template import get_template
from stdlib.timezone_util import now_app
from stdlib.timing import timed_task

# Параллельная отправка вложений (лимит Telegram на чат обычно не достигается).
_FEEDBACK_ATTACHMENTS_CONCURRENCY = 5


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


async def _send_rework_pdf_if_possible(
    bot: Bot,
    user_id: int,
    app_id: int,
    app_row: dict | None,
) -> None:
    """Пытается отправить пользователю актуальный PDF по заявке."""
    if not app_row:
        return

    try:
        # 1) Есть живой file_id — отправляем мгновенно
        if app_row.get("pdf_file_id"):
            try:
                await bot.send_document(
                    user_id,
                    document=app_row["pdf_file_id"],
                    caption=f"📄 Актуальная версия заявки #{app_id}.",
                )
                logger.debug("Rework PDF source=file_id app_id={}", app_id)
                return
            except Exception:
                # file_id протух — идём на S3
                logger.debug("file_id expired for app {}, falling back to S3", app_id)

        # 2) file_id нет или протух — S3 + данные пользователя параллельно
        pdf_bytes, full_name, position = await asyncio.gather(
            s3.download_bytes(s3.pdf_key(user_id, app_id), s3.BUCKET_PDF),
            db.get_user_full_name(user_id),
            db.get_user_position(user_id),
        )

        # S3 есть — используем, нет — генерируем
        source = "s3"
        pdf_buf = io.BytesIO(pdf_bytes) if pdf_bytes else await get_app_pdf_buffer(app_id)
        if not pdf_bytes:
            source = "generated"
        created_at = app_row.get("created_at") or now_app()
        custom_filename = resolve_application_pdf_filename(
            app_row,
            full_name=full_name,
            position=position,
            dt=created_at,
        )

        sent = await bot.send_document(
            user_id,
            document=BufferedInputFile(
                pdf_buf.getvalue(),
                filename=custom_filename,
            ),
            caption=f"📄 Актуальная версия заявки #{app_id}.",
        )
        logger.debug("Rework PDF source={} app_id={}", source, app_id)

        # сохраняем свежий file_id для следующего раза
        if sent.document:
            await db.set_pdf_file_id(app_id, sent.document.file_id)
            logger.debug("Saved new file_id for app {}", app_id)

    except Exception as e:
        logger.warning(
            "Failed to send rework PDF to user {} for app {}: {}",
            user_id,
            app_id,
            e,
        )


async def _send_one_feedback_attachment(
    bot: Bot,
    user_id: int,
    app_id: int,
    *,
    idx: int,
    total: int,
    file_name: str,
    file_bytes: bytes,
    caption_note: str,
    sem: asyncio.Semaphore,
) -> None:
    async with sem:
        try:
            await bot.send_document(
                user_id,
                document=BufferedInputFile(
                    file_bytes,
                    filename=file_name,
                ),
                caption=f"📎 Файл {idx}/{total} {caption_note} к заявке #{app_id}.",
            )
        except Exception as e:
            logger.warning(
                "Failed to send feedback attachment #{} to user {} for app {}: {}",
                idx,
                user_id,
                app_id,
                e,
            )


async def _send_feedback_attachments(
    bot: Bot,
    user_id: int,
    app_id: int,
    *,
    feedback_files: list[tuple[str, bytes]] | None,
    caption_note: str,
) -> None:
    if not feedback_files:
        return
    total = len(feedback_files)
    sem = asyncio.Semaphore(_FEEDBACK_ATTACHMENTS_CONCURRENCY)
    await asyncio.gather(
        *[
            _send_one_feedback_attachment(
                bot,
                user_id,
                app_id,
                idx=idx,
                total=total,
                file_name=file_name,
                file_bytes=file_bytes,
                caption_note=caption_note,
                sem=sem,
            )
            for idx, (file_name, file_bytes) in enumerate(feedback_files, start=1)
        ]
    )


@timed_task("notify_user_application_approved")
async def notify_user_application_approved(
    bot: Bot,
    user_id: int,
    app_id: int,
    *,
    pdf_file_id: str | None = None,
    feedback: str | None = None,
    feedback_files: list[tuple[str, bytes]] | None = None,
    web_wording: bool = False,
) -> None:
    """
    Уведомляет автора о согласовании.
    Сначала текст (с опциональным комментарием), затем PDF и вложения.
    """
    feedback_text = (feedback or "").strip()
    has_extra = bool(feedback_text or feedback_files)

    if has_extra:
        if web_wording:
            text = (
                f"✅ <b>Заявка #{app_id} согласована.</b>\n\n"
                f"<b>Комментарий:</b>\n{feedback_text or '—'}\n\n"
                "Документ передан в дальнейшую работу."
            )
        else:
            text = (
                f"✅ Заявка #{app_id} согласована.\n\n"
                f"<b>Комментарий:</b>\n{feedback_text or '—'}\n\n"
                "Документ передан в дальнейшую работу."
            )
        text_sent = True
        try:
            await bot.send_message(user_id, text, parse_mode="HTML")
        except Exception as e:
            text_sent = False
            logger.error(
                "Failed to notify user {} about approval for app {}: {}",
                user_id,
                app_id,
                e,
            )
        if text_sent:
            await asyncio.gather(
                _send_approval_pdf_if_possible(bot, user_id, app_id, pdf_file_id),
                _send_feedback_attachments(
                    bot,
                    user_id,
                    app_id,
                    feedback_files=feedback_files,
                    caption_note="к согласованию",
                ),
            )
        return

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
            user_id, app_id, e,
        )


async def _send_approval_pdf_if_possible(
    bot: Bot,
    user_id: int,
    app_id: int,
    pdf_file_id: str | None,
) -> None:
    if not pdf_file_id:
        return
    try:
        await bot.send_document(
            user_id,
            document=pdf_file_id,
            caption=f"📄 Согласованная версия заявки #{app_id}.",
        )
    except Exception as e:
        logger.warning(
            "Failed to send approval PDF to user {} for app {}: {}",
            user_id,
            app_id,
            e,
        )


async def broadcast_superusers_html(bot: Bot, text: str) -> None:
    """Рассылает HTML всем суперпользователям."""
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
    feedback_files: list[tuple[str, bytes]] | None = None,
) -> None:
    """Уведомляет автора о возврате на доработку."""
    app_row = await db.get_app(app_id)
    preview_task = asyncio.create_task(
        _blocks_preview_html(app_row.get("blocks") if app_row else None)
    )
    preview_html = await preview_task

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

    text_sent = True
    try:
        await bot.send_message(
            user_id,
            text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    except Exception as e:
        text_sent = False
        logger.error(
            "Failed to notify user {} about rework for app {}: {}",
            user_id, app_id, e,
        )

    # По запросу UX: сначала текст, потом докидываем документы.
    if text_sent:
        await asyncio.gather(
            _send_rework_pdf_if_possible(bot, user_id, app_id, app_row),
            _send_feedback_attachments(
                bot,
                user_id,
                app_id,
                feedback_files=feedback_files,
                caption_note="с замечаниями",
            ),
        )
