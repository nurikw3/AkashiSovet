"""Операции с заявкой: создание черновика, смена статуса, отправка на согласование, доработка."""

from __future__ import annotations

import stdlib.db as db
from stdlib.models import Application, ApplicationAttachment
from stdlib.pdf import invalidate_pdf_content_cache


async def list_applications(
    status: str | None = None, full_name_query: str | None = None
) -> list[dict]:
    """Список заявок для веб-таблицы c фильтром по статусу и поиском по ФИО."""
    return await db.get_applications(status, full_name_query)


async def get_status_counts() -> dict[str, int]:
    """Счётчики по статусам для дашборда (pending / approved / rework / total)."""
    return await db.get_application_status_counts()


async def list_user_applications(user_id: int) -> list[dict]:
    """Заявки пользователя (как `db.get_user_apps`)."""
    return await db.get_user_apps(user_id)


async def delete_application(app_id: int) -> None:
    await db.delete_app(app_id)


async def mark_application_started(app_id: int) -> None:
    await db.set_t_start(app_id)


async def reset_draft_for_new_session(app_id: int) -> None:
    """Чистый черновик для нового /start или «Начать заново» (без контекста старого режима)."""
    await db.reset_draft_content(app_id)
    await invalidate_pdf_content_cache(app_id)


async def save_block(app_id: int, block_num: int | str, text: str) -> None:
    await db.save_block(app_id, block_num, text)
    await invalidate_pdf_content_cache(app_id)


async def save_all_blocks(app_id: int, blocks: dict) -> None:
    await db.save_all_blocks(app_id, blocks)
    await invalidate_pdf_content_cache(app_id)


async def get_chat_history(app_id: int) -> list:
    return await db.get_chat_history(app_id)


async def save_chat_history(app_id: int, history: list) -> None:
    await db.save_chat_history(app_id, history)


async def get_last_rework_application(user_id: int) -> Application | None:
    raw = await db.get_last_rework_app(user_id)
    if not raw:
        return None
    return Application.model_validate(raw)


async def invalidate_application_pdf_cache(app_id: int) -> None:
    await invalidate_pdf_content_cache(app_id)


async def get_application(app_id: int) -> Application | None:
    """Возвращает заявку как `Application` или `None`."""
    raw = await db.get_app(app_id)
    if not raw:
        return None
    return Application.model_validate(raw)


async def get_or_create_draft(user_id: int, username: str | None) -> int:
    """Находит черновик пользователя или создаёт новый; возвращает `id`."""
    return await db.get_or_create_app(user_id, username)


async def submit_to_review(
    app_id: int, *, pdf_file_id: str | None = None
) -> None:
    """Переводит заявку в `pending`, фиксирует время подачи."""
    await db.update_status_and_submit(app_id, "pending", pdf_file_id=pdf_file_id)


async def update_submission_pdf_reference(app_id: int, pdf_file_id: str) -> None:
    """Обновляет `pdf_file_id` у уже отправленной заявки (например после отправки PDF в Telegram)."""
    await db.set_pdf_file_id(app_id, pdf_file_id)


async def clear_pdf_reference(app_id: int) -> None:
    """Сбрасывает сохраненный Telegram `pdf_file_id` для заявки."""
    await db.set_pdf_file_id(app_id, None)


async def approve(app_id: int) -> Application | None:
    """Согласование заявки."""
    await db.update_status(app_id, "approved")
    await db.set_t_decision(app_id)
    return await get_application(app_id)


async def send_for_rework(app_id: int, feedback: str) -> Application | None:
    """Возврат на доработку с комментарием."""
    await db.update_status(app_id, "rework", feedback=feedback)
    await db.set_t_decision(app_id)
    await db.increment_reject_count(app_id)
    return await get_application(app_id)


async def append_attachments(
    app_id: int, new: ApplicationAttachment
) -> list[ApplicationAttachment]:
    """Добавляет вложение к заявке и сохраняет в БД."""
    app = await get_application(app_id)
    if not app:
        raise ValueError(f"application {app_id} not found")
    merged = [*app.attachments, new]
    await db.save_attachments(app_id, [a.model_dump() for a in merged])
    await invalidate_pdf_content_cache(app_id)
    return merged


async def get_application_record(app_id: int) -> dict | None:
    """Сырая строка из БД (как `db.get_app`): нужна, где важен исходный JSON вложений (Telegram `file_id`)."""
    return await db.get_app(app_id)


async def save_attachments_payload(
    app_id: int, attachments: list, *, user_id: int | None = None
) -> None:
    """Сохраняет список вложений как в БД (в т.ч. реестр файлов из Telegram до выгрузки в S3)."""
    await db.save_attachments(app_id, attachments)
    await invalidate_pdf_content_cache(app_id, user_id=user_id)


async def clear_application_chat_history(app_id: int) -> None:
    """Обнуляет историю free-form / LLM по заявке."""
    await db.clear_chat_history(app_id)


async def get_draft_application_id_for_user(user_id: int) -> int | None:
    """`id` черновика пользователя, если есть."""
    return await db.get_draft_id_for_user(user_id)
