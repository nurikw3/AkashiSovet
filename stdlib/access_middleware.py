from __future__ import annotations

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import config
from bot.logger import logger
import stdlib.db as db


class AccessControlMiddleware(BaseMiddleware):
    """Пропускает только SUPERUSER_IDS и пользователей из allowlist в БД."""

    async def __call__(self, handler, event: TelegramObject, data: dict):
        # Для update-level middleware aiogram передаёт пользователя в data["event_from_user"].
        user = data.get("event_from_user") or getattr(event, "from_user", None)
        user_id = getattr(user, "id", None)

        # Фейлим "закрыто": без user_id update не обрабатываем.
        if user_id is None:
            return None

        if user_id in config.SUPERUSER_IDS:
            return await handler(event, data)

        try:
            if await db.is_user_allowed(int(user_id)):
                return await handler(event, data)
        except Exception as e:
            logger.error("Access check failed for user {}: {}", user_id, e)

        if isinstance(event, Message):
            await event.answer(
                "⛔ Доступ к боту ограничен. Обратитесь к администратору."
            )
        elif isinstance(event, CallbackQuery):
            await event.answer("Нет доступа.", show_alert=True)

        logger.warning("Blocked unauthorized user {}", user_id)
        return None
