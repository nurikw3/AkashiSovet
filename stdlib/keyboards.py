from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from stdlib.handlers.blocks import BLOCKS
from stdlib.template import ApplicationTemplate


def _cancel_button():
    return [InlineKeyboardButton(text="❌ Отменить заявку", callback_data="cancel_app")]


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm"),
                InlineKeyboardButton(text="✏️ Исправить", callback_data="edit"),
            ],
            [_cancel_button()[0]],
        ]
    )


def files_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Готово", callback_data="files_done"),
                InlineKeyboardButton(text="⏭ Пропустить", callback_data="files_skip"),
            ],
            [_cancel_button()[0]],
        ]
    )


def approve_reject_keyboard(app_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Approve", callback_data=f"approve_{app_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Reject", callback_data=f"reject_{app_id}"
                ),
            ]
        ]
    )


def rework_keyboard(tpl: ApplicationTemplate | None = None) -> InlineKeyboardMarkup:
    if tpl is not None:
        buttons = [
            [
                InlineKeyboardButton(
                    text=f"Блок {b.id} — {b.title}",
                    callback_data=f"rework_block_{b.id}",
                )
            ]
            for b in tpl.blocks
        ]
    else:
        buttons = [
            [
                InlineKeyboardButton(
                    text=f"Блок {i} — {BLOCKS[i]['title']}",
                    callback_data=f"rework_block_{i}",
                )
            ]
            for i in range(1, 6)
        ]
    buttons.append(
        [
            InlineKeyboardButton(
                text="📎 Изменить приложения", callback_data="rework_files"
            ),
            InlineKeyboardButton(
                text="📤 Отправить повторно", callback_data="rework_submit"
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def review_keyboard(tpl: ApplicationTemplate | None = None) -> InlineKeyboardMarkup:
    if tpl is not None:
        buttons = [
            [
                InlineKeyboardButton(
                    text=f"✏️ {idx}. {b.title}"[:64],
                    callback_data=f"review_edit_{b.id}",
                )
            ]
            for idx, b in enumerate(tpl.blocks, start=1)
        ]
    else:
        buttons = [
            [
                InlineKeyboardButton(
                    text=f"✏️ Изменить Блок {i}",
                    callback_data=f"review_edit_{i}",
                )
            ]
            for i in range(1, 6)
        ]
    buttons.append(
        [
            InlineKeyboardButton(
                text="📎 Изменить файлы", callback_data="review_files"
            ),
        ]
    )
    buttons.append(
        [
            InlineKeyboardButton(
                text="🚀 Отправить заявку", callback_data="review_submit"
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_rework_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить", callback_data="rework_confirm"
                ),
                InlineKeyboardButton(text="✏️ Исправить", callback_data="rework_edit"),
            ],
            [_cancel_button()[0]],
        ]
    )


def restart_or_continue_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="▶️ Продолжить текущую", callback_data="continue_draft"
                ),
                InlineKeyboardButton(
                    text="🆕 Начать заново", callback_data="restart_draft"
                ),
            ],
            [_cancel_button()[0]],
        ]
    )
