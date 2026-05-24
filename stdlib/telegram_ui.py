from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.logger import logger


async def safe_edit_or_send(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str = "HTML",
) -> Message:
    """Редактирует сообщение или отправляет новое при ошибке."""
    try:
        await message.edit_text(
            text, reply_markup=reply_markup, parse_mode=parse_mode
        )
        return message
    except TelegramBadRequest as e:
        if "message is not modified" in e.message:
            return message
        if (
            "message can't be edited" in e.message
            or "message to edit not found" in e.message
        ):
            try:
                await message.delete()
            except Exception:
                pass
            return await message.answer(
                text, reply_markup=reply_markup, parse_mode=parse_mode
            )
        logger.warning("Msg edit failed: {}", e)
    except Exception as e:
        logger.warning("Unexpected send/edit failed: {}", e)

    return await message.answer(
        text, reply_markup=reply_markup, parse_mode=parse_mode
    )


async def store_nav_message(state: FSMContext, message: Message) -> None:
    await state.update_data(
        nav_message_id=message.message_id,
        nav_chat_id=message.chat.id,
    )


async def edit_nav_anchor(
    bot,
    state: FSMContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    *,
    parse_mode: str = "HTML",
    fallback_chat_id: int | None = None,
) -> Message | None:
    """Редактирует якорное сообщение из FSM; при ошибке — новое сообщение."""
    data = await state.get_data()
    nav_message_id = data.get("nav_message_id")
    nav_chat_id = data.get("nav_chat_id") or fallback_chat_id

    if nav_message_id and nav_chat_id:
        try:
            await bot.edit_message_text(
                text,
                chat_id=nav_chat_id,
                message_id=nav_message_id,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
            return None
        except TelegramBadRequest as e:
            if "message is not modified" in e.message:
                return None
            logger.warning("Nav anchor edit failed: {}", e)

    if not fallback_chat_id:
        return None

    msg = await bot.send_message(
        fallback_chat_id,
        text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )
    await store_nav_message(state, msg)
    return msg


async def render_nav_screen(
    target: Message | CallbackQuery,
    state: FSMContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    *,
    parse_mode: str = "HTML",
    force_new: bool = False,
) -> Message | None:
    """
    Callback → edit сообщения с кнопкой.
    Message → edit якоря или answer + сохранить nav_message_id.
    force_new → всегда новое сообщение (Review PDF и т.п.).
    """
    if force_new:
        answer_fn = (
            target.answer if isinstance(target, Message) else target.message.answer
        )
        msg = await answer_fn(
            text, reply_markup=reply_markup, parse_mode=parse_mode
        )
        await store_nav_message(state, msg)
        return msg

    if isinstance(target, CallbackQuery):
        msg = await safe_edit_or_send(
            target.message,
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
        await store_nav_message(state, msg)
        return msg

    chat_id = target.chat.id
    edited = await edit_nav_anchor(
        target.bot,
        state,
        text,
        reply_markup,
        parse_mode=parse_mode,
        fallback_chat_id=chat_id,
    )
    if edited is not None:
        return edited
    return None
