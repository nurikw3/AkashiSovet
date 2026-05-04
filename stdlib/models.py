"""Централизованные Pydantic-модели домена (заявки, пользователи, шаблон, заседания)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from stdlib.template import ApplicationTemplate, BlockDefinition

ApplicationStatus = Literal["draft", "pending", "approved", "rework"]


class ApplicationAttachment(BaseModel):
    """Элемент списка вложений: S3 (после выгрузки) или Telegram file_id (как в боте)."""

    name: str
    s3_key: str | None = None
    file_id: str | None = None


class ChatMessage(BaseModel):
    """Сообщение в истории чата с LLM по заявке."""

    role: str
    content: str


class Application(BaseModel):
    """Заявка; поля соответствуют таблице `applications` и типичным JOIN с `users`."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    user_id: int
    username: str | None = None
    status: ApplicationStatus = "draft"
    blocks: dict[str, str] = Field(default_factory=dict)
    attachments: list[ApplicationAttachment] = Field(default_factory=list)
    feedback: str | None = None
    pdf_file_id: str | None = None
    chat_history: list[ChatMessage] = Field(default_factory=list)
    t_start: datetime | None = None
    t_submit: datetime | None = None
    t_decision: datetime | None = None
    reject_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    full_name: str | None = None
    position: str | None = None

    @field_validator("blocks", mode="before")
    @classmethod
    def _parse_blocks(cls, v: Any) -> dict[str, str]:
        if v is None or v == "":
            return {}
        if isinstance(v, str):
            data = json.loads(v)
        else:
            data = v
        return {str(k): str(val) for k, val in (data or {}).items()}

    @field_validator("attachments", mode="before")
    @classmethod
    def _parse_attachments(cls, v: Any) -> list:
        if v is None or v == "":
            return []
        if isinstance(v, str):
            try:
                raw = json.loads(v.replace("'", '"'))
            except (json.JSONDecodeError, TypeError):
                raw = []
        else:
            raw = v
        if not isinstance(raw, list):
            return []
        out: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                name = (item.get("name") or item.get("file_name") or "Файл").strip() or "Файл"
                s3_key = item.get("s3_key")
                if s3_key == "":
                    s3_key = None
                file_id = item.get("file_id")
                if isinstance(file_id, str) and not file_id.strip():
                    file_id = None
                if s3_key or file_id:
                    out.append(
                        {"name": name, "s3_key": s3_key, "file_id": file_id}
                    )
                else:
                    # Только имя (старые данные / перечень в PDF)
                    out.append({"name": name, "s3_key": None, "file_id": None})
            elif isinstance(item, str):
                s = str(item).strip()
                if s:
                    out.append({"name": s, "s3_key": None, "file_id": None})
        return out

    @field_validator("chat_history", mode="before")
    @classmethod
    def _parse_chat_history(cls, v: Any) -> list:
        if v is None or v == "":
            return []
        if isinstance(v, str):
            try:
                raw = json.loads(v)
            except json.JSONDecodeError:
                raw = []
        else:
            raw = v
        if not isinstance(raw, list):
            return []
        return [x for x in raw if isinstance(x, dict) and "role" in x and "content" in x]


class User(BaseModel):
    """Пользователь Telegram / запись в таблице `users`."""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    full_name: str | None = None
    position: str | None = None
    signature_data: str | None = None
    mode: str = "step"
    login: str | None = None
    hashed_password: str | None = None


class Template(ApplicationTemplate):
    """Динамический шаблон структуры заявки (блоки — см. `stdlib.template.ApplicationTemplate`)."""


class Meeting(BaseModel):
    """Заседание Правления: планируемая сущность из `meetings` (id — после появления таблицы в БД)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    scheduled_at: datetime
    created_by: int = Field(description="Telegram user_id инициатора")
    created_at: datetime
    application_ids: list[int] = Field(default_factory=list)

    @field_validator("application_ids", mode="before")
    @classmethod
    def _coerce_app_ids(cls, v: Any) -> list[int]:
        if v is None:
            return []
        if isinstance(v, str):
            try:
                raw = json.loads(v)
            except json.JSONDecodeError:
                return []
        else:
            raw = v
        if not isinstance(raw, list):
            return []
        return [int(x) for x in raw]
