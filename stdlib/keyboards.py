from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from stdlib.template import ApplicationTemplate


def _cancel_button():
    return [InlineKeyboardButton(text="❌ Отменить заявку", callback_data="cancel_app")]


def confirm_keyboard(block_id: int) -> InlineKeyboardMarkup:
    """Кнопки привязаны к номеру блока — после перехода на следующий блок старые «Исправить» всё ещё ведут в нужный блок."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"fcb_confirm_{block_id}",
                ),
                InlineKeyboardButton(
                    text="✏️ Исправить",
                    callback_data=f"fcb_edit_{block_id}",
                ),
            ],
            [_cancel_button()[0]],
        ]
    )


def files_keyboard(attachment_names: list[str] | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for idx, name in enumerate(attachment_names or []):
        label = (name or f"Файл {idx + 1}").strip() or f"Файл {idx + 1}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 Удалить: {label}"[:64],
                    callback_data=f"files_del_{idx}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="✅ Готово", callback_data="files_done"),
            InlineKeyboardButton(text="⏭ Пропустить", callback_data="files_skip"),
        ]
    )
    rows.append([_cancel_button()[0]])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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


def approve_reject_open_keyboard(
    app_id: int,
    application_url: str | None = None,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="✅ Approve", callback_data=f"approve_{app_id}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_{app_id}"),
        ]
    ]
    if application_url:
        rows.insert(
            0,
            [InlineKeyboardButton(text="🔗 Open In Web", url=application_url)],
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rework_keyboard(tpl: ApplicationTemplate, app_id: int | None = None) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=f"Блок {b.id} — {b.title}",
                callback_data=(
                    f"rework_block_{app_id}_{b.id}"
                    if app_id is not None
                    else f"rework_block_{b.id}"
                ),
            )
        ]
        for b in tpl.blocks
    ]
    buttons.append(
        [
            InlineKeyboardButton(
                text="📎 Изменить приложения",
                callback_data=(
                    f"rework_files_{app_id}" if app_id is not None else "rework_files"
                ),
            ),
            InlineKeyboardButton(
                text="📤 Отправить повторно",
                callback_data=(
                    f"rework_submit_{app_id}" if app_id is not None else "rework_submit"
                ),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def review_keyboard(tpl: ApplicationTemplate) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=f"✏️ {idx}. {b.title}"[:64],
                callback_data=f"review_edit_{b.id}",
            )
        ]
        for idx, b in enumerate(tpl.blocks, start=1)
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


def cleanup_chat_keyboard(app_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧹 Очистить служебные сообщения",
                    callback_data=f"cleanup_chat_{app_id}",
                )
            ]
        ]
    )
