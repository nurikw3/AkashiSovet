"""Заседания Правления: создание, списки предстоящих/прошедших, добавление заявок в корзину."""

from __future__ import annotations

from datetime import datetime

import stdlib.db as db
from stdlib.models import Meeting


async def create_meeting(scheduled_at: datetime, created_by: int) -> Meeting:
    """Создаёт заседание на указанные дату и время; инициатор — Telegram user_id суперпользователя."""
    row = await db.insert_meeting(scheduled_at, created_by)
    return Meeting.model_validate(row)


async def get_upcoming() -> list[Meeting]:
    """Предстоящие заседания (`scheduled_at >= now`), по времени по возрастанию."""
    rows = await db.list_meetings_upcoming()
    return [Meeting.model_validate(r) for r in rows]


async def get_past() -> list[Meeting]:
    """Прошедшие заседания, сначала с более поздней датой."""
    rows = await db.list_meetings_past()
    return [Meeting.model_validate(r) for r in rows]


async def add_applications(meeting_id: int, application_ids: list[int]) -> None:
    """Добавляет id заявок в `application_ids` (уникальные, объединение с имеющимися)."""
    await db.extend_meeting_application_ids(meeting_id, application_ids)


async def get_by_id(meeting_id: int) -> Meeting | None:
    """Заседание по первичному ключу или None."""
    row = await db.get_meeting_by_id(meeting_id)
    if not row:
        return None
    return Meeting.model_validate(row)


async def delete_meeting(meeting_id: int) -> bool:
    """Удаляет заседание; True если запись существовала и удалена."""
    return await db.delete_meeting_by_id(meeting_id)


async def create_meeting_with_applications(
    scheduled_at: datetime,
    created_by: int,
    application_ids: list[int],
) -> Meeting:
    """Создаёт заседание и прикрепляет заявки (только status approved)."""
    if not application_ids:
        raise ValueError("Выберите хотя бы одну заявку")
    ids = list(dict.fromkeys(int(x) for x in application_ids))
    status_map = await db.get_application_status_by_ids(ids)
    for aid in ids:
        st = status_map.get(aid)
        if st is None:
            raise ValueError(f"Заявка {aid} не найдена")
        if st != "approved":
            raise ValueError(
                "В заседание можно добавить только согласованные заявки (approved)"
            )
    meeting = await create_meeting(scheduled_at, created_by)
    await add_applications(meeting.id, ids)
    updated = await get_by_id(meeting.id)
    if not updated:
        raise RuntimeError("meeting_create_with_apps: meeting missing after insert")
    return updated
