"""Отправка уведомлений пользователям через Telegram Bot API."""

from __future__ import annotations

from aiogram import Bot
from bot.config import config
from bot.logger import logger


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
    if web_wording:
        text = (
            f"❌ <b>Заявка #{app_id} возвращена на доработку.</b>\n\n"
            f"<b>Замечания:</b>\n{feedback}\n\n"
            "<i>Используйте кнопки ниже для редактирования:</i>"
        )
    else:
        text = (
            f"❌ Заявка #{app_id} возвращена на доработку.\n\n"
            f"<b>Замечания:</b>\n{feedback}\n\n"
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
