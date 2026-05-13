from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

import stdlib.db as db
from bot.config import config
from bot.logger import logger

router = Router()


def is_superuser(user_id: int) -> bool:
    return user_id in config.SUPERUSER_IDS


def _parse_target_user_id(args: str | None) -> int | None:
    raw = (args or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _parse_many_user_ids(args: str | None) -> tuple[list[int], list[str]]:
    raw = (args or "").strip()
    if not raw:
        return [], []

    tokens = raw.replace(",", " ").split()
    valid: list[int] = []
    invalid: list[str] = []
    for token in tokens:
        try:
            value = int(token)
            if value > 0:
                valid.append(value)
            else:
                invalid.append(token)
        except ValueError:
            invalid.append(token)

    # Убираем дубликаты, сохраняя порядок.
    unique_valid = list(dict.fromkeys(valid))
    unique_invalid = list(dict.fromkeys(invalid))
    return unique_valid, unique_invalid


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


@router.message(Command("allow"))
async def cmd_allow_user(message: Message, command: CommandObject):
    if not is_superuser(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    target_user_id = _parse_target_user_id(command.args)
    if not target_user_id:
        await message.answer("Использование: /allow <telegram_user_id>")
        return

    await db.add_allowed_user(target_user_id, added_by=message.from_user.id)
    logger.info(
        "Access allow by superuser {} for user {}",
        message.from_user.id,
        target_user_id,
    )
    await message.answer(f"✅ Пользователь {target_user_id} добавлен в allowlist.")


@router.message(Command("allow_many"))
async def cmd_allow_many_users(message: Message, command: CommandObject):
    if not is_superuser(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    user_ids, invalid_tokens = _parse_many_user_ids(command.args)
    if not user_ids:
        await message.answer("Использование: /allow_many <id1,id2,id3> или через пробел")
        return

    inserted_count = await db.add_allowed_users(user_ids, added_by=message.from_user.id)
    logger.info(
        "Access allow_many by superuser {} for {} users (invalid_tokens={})",
        message.from_user.id,
        inserted_count,
        invalid_tokens,
    )

    invalid_text = (
        f"\n⚠️ Пропущены некорректные значения: {', '.join(invalid_tokens[:20])}"
        if invalid_tokens
        else ""
    )
    suffix = "\n…(показаны первые 20)" if len(invalid_tokens) > 20 else ""
    await message.answer(
        f"✅ Добавлено/обновлено пользователей: {inserted_count}.{invalid_text}{suffix}"
    )


@router.message(Command("deny"))
async def cmd_deny_user(message: Message, command: CommandObject):
    if not is_superuser(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    target_user_id = _parse_target_user_id(command.args)
    if not target_user_id:
        await message.answer("Использование: /deny <telegram_user_id>")
        return

    removed = await db.remove_allowed_user(target_user_id)
    if removed:
        logger.info(
            "Access deny by superuser {} for user {}",
            message.from_user.id,
            target_user_id,
        )
        await message.answer(f"✅ Пользователь {target_user_id} удалён из allowlist.")
        return
    await message.answer(f"Пользователь {target_user_id} не найден в allowlist.")


@router.message(Command("allowed"))
async def cmd_allowed_users(message: Message):
    if not is_superuser(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    allowed_users = await db.list_allowed_users()
    if not allowed_users:
        await message.answer("Список allowlist пуст.")
        return

    logger.info(
        "Access list requested by superuser {} (count={})",
        message.from_user.id,
        len(allowed_users),
    )
    preview = "\n".join(f"• <code>{user_id}</code>" for user_id in allowed_users[:100])
    total = len(allowed_users)
    suffix = "\n…\n(показаны первые 100)" if total > 100 else ""
    await message.answer(
        f"✅ Разрешенные пользователи ({total}):\n{preview}{suffix}",
        parse_mode="HTML",
    )
