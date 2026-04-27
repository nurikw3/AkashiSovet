from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
import stdlib.db as db
from bot.config import config

router = Router()


@router.message(Command("web"), F.from_user.id.in_(config.SUPERUSER_IDS))
async def cmd_web_auth(message: Message):
    otp = await db.generate_web_login_code(message.from_user.id)

    await message.answer(
        f"🛡 <b>AKASHI SECURE ACCESS</b>\n\n"
        f"Ваш временный код для входа в панель:\n"
        f"<code>{otp}</code>\n\n"
        f"<i>Код действителен для одного входа.</i>",
        parse_mode="HTML",
    )
