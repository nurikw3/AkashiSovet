import html
from urllib.parse import quote

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import config
from stdlib.services import web_auth_service

router = Router()


@router.message(Command("web"), F.from_user.id.in_(config.SUPERUSER_IDS))
async def cmd_web_auth(message: Message):
    base = (config.WEB_PUBLIC_URL or "").strip().rstrip("/")
    if not base:
        await message.answer(
            "❌ В конфигурации не задан <code>WEB_PUBLIC_URL</code> "
            "(публичный адрес веб-панели). Добавьте его в .env и перезапустите бота.",
            parse_mode="HTML",
        )
        return

    token = await web_auth_service.mint_login_token(message.from_user.id)
    if not token:
        await message.answer(
            "❌ Не удалось выдать ссылку: Redis недоступен или ошибка записи.",
            parse_mode="HTML",
        )
        return

    url = f"{base}/auth?token={quote(token, safe='')}"
    minutes = max(1, config.WEB_AUTH_TOKEN_TTL_SECONDS // 60)

    await message.answer(
        f"🛡 <b>Вход в панель</b>\n\n"
        f"Одноразовая ссылка (~{minutes} мин):\n"
        f'<a href="{html.escape(url)}">Открыть панель</a>\n\n'
        f"<code>{html.escape(url)}</code>",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
