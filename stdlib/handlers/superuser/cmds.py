from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

import stdlib.db as db
from bot.config import config

router = Router()


@router.message(Command("web"), F.from_user.id.in_(config.SUPERUSER_IDS))
async def cmd_web_auth(message: Message):
    uid = message.from_user.id
    otp = await db.generate_web_login_code(uid)

    await message.answer(
        f"🛡 <b>AKASHI SECURE ACCESS</b>\n\n"
        f"Ваш Telegram ID для поля «Telegram ID» на странице входа:\n"
        f"<code>{uid}</code>\n\n"
        f"Временный код для входа в панель:\n"
        f"<code>{otp}</code>\n\n"
        f"<i>Код действителен для одного входа.</i>",
        parse_mode="HTML",
    )
