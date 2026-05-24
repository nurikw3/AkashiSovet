# stdlib/template.py
from __future__ import annotations

import json
from typing import Any, List

from pydantic import BaseModel, Field, field_validator, model_validator

from bot.logger import logger
import stdlib.db as db
from stdlib.resources import get_redis

APP_TEMPLATE_KEY = "app_template"
REDIS_TEMPLATE_CACHE_KEY = "settings:app_template"
TEMPLATE_CACHE_TTL_SEC = 300
# Инкремент при сохранении шаблона — попадает в токен кэша документа (stdlib/docx_gen.py).
DOCX_TEMPLATE_REVISION_KEY = "docx:template_revision"
PDF_TEMPLATE_REVISION_KEY = DOCX_TEMPLATE_REVISION_KEY  # обратная совместимость


class BlockDefinition(BaseModel):
    id: int = Field(gt=0, description="Уникальный положительный идентификатор блока")
    title: str = Field(min_length=1, max_length=500)
    question: str = Field(min_length=1, max_length=50000)
    description_for_llm: str | None = Field(default=None, max_length=10000)
    format_as_numbered_list: bool = Field(
        default=False,
        description="LLM оформляет несколько пунктов нумерованным списком, а не сплошным абзацем.",
    )

    @field_validator("title", "question", mode="before")
    @classmethod
    def _strip_title_question(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("description_for_llm", mode="before")
    @classmethod
    def _strip_description(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("format_as_numbered_list", mode="before")
    @classmethod
    def _coerce_numbered_list_flag(cls, v: Any) -> bool:
        if v is None:
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        s = str(v).strip().lower()
        return s in ("1", "true", "yes", "on")


class ApplicationTemplate(BaseModel):
    blocks: List[BlockDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_block_ids(self) -> ApplicationTemplate:
        ids = [b.id for b in self.blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("ID блоков должны быть уникальными")
        return self

    def get_block(self, block_id: int) -> BlockDefinition:
        for block in self.blocks:
            if block.id == block_id:
                return block
        raise ValueError(f"Block with id {block_id} not found")

    def get_next_block_id(self, current_id: int) -> int | None:
        """Возвращает ID следующего блока или None, если это последний"""
        ids = [b.id for b in self.blocks]
        try:
            idx = ids.index(current_id)
            if idx + 1 < len(ids):
                return ids[idx + 1]
            return None
        except ValueError:
            return None

    def get_prev_block_id(self, current_id: int) -> int | None:
        """Возвращает ID предыдущего блока или None, если это первый"""
        ids = [b.id for b in self.blocks]
        try:
            idx = ids.index(current_id)
            if idx - 1 >= 0:
                return ids[idx - 1]
            return None
        except ValueError:
            return None

    @property
    def first_block_id(self) -> int:
        return self.blocks[0].id

    @property
    def last_block_id(self) -> int:
        return self.blocks[-1].id

    @property
    def total_blocks_count(self) -> int:
        return len(self.blocks)

    def block_index_1based(self, block_id: int) -> int:
        for i, b in enumerate(self.blocks, start=1):
            if b.id == block_id:
                return i
        raise ValueError(f"Block id {block_id} not in template")


def block_wants_numbered_list(block: BlockDefinition) -> bool:
    """Явная настройка в шаблоне: оформлять блок нумерованным списком."""
    return block.format_as_numbered_list


def block_llm_instruction(block: BlockDefinition) -> str:
    """
    Одинаковая справка по блоку для LLM: как в free-form (поля submit_memo).
    «title. question» и при наличии — « — description_for_llm».
    """
    s = f"{block.title}. {block.question}"
    if block.description_for_llm:
        s = f"{s} — {block.description_for_llm}"
    return s


def _coerce_setting_value(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return json.loads(raw)
    raise TypeError(f"unexpected settings value type: {type(raw)}")


async def get_template() -> ApplicationTemplate:
    """
    Загружает шаблон заявки из `settings.app_template`.
    Кэширует JSON в Redis на ``TEMPLATE_CACHE_TTL_SEC`` секунд (при доступном Redis).
    """
    r = get_redis()
    if r:
        try:
            cached = await r.get(REDIS_TEMPLATE_CACHE_KEY)
            if cached:
                return ApplicationTemplate.model_validate_json(cached)
        except Exception as e:
            logger.warning("get_template: redis read failed: {}", e)

    raw = await db.get_setting(APP_TEMPLATE_KEY)
    if raw is None:
        raise RuntimeError(
            f"В таблице settings нет ключа «{APP_TEMPLATE_KEY}». "
            "Примените миграцию migrations/001_settings.sql."
        )

    data = _coerce_setting_value(raw)
    tpl = ApplicationTemplate.model_validate(data)

    if r:
        try:
            await r.set(
                REDIS_TEMPLATE_CACHE_KEY,
                tpl.model_dump_json(),
                ex=TEMPLATE_CACHE_TTL_SEC,
            )
        except Exception as e:
            logger.warning("get_template: redis write failed: {}", e)

    return tpl


async def invalidate_template_cache() -> None:
    """Удаляет кэш шаблона в Redis (вызывать после обновления записи в БД)."""
    r = get_redis()
    if not r:
        return
    try:
        await r.delete(REDIS_TEMPLATE_CACHE_KEY)
    except Exception as e:
        logger.warning("invalidate_template_cache: {}", e)


async def _bump_docx_template_revision() -> None:
    r = get_redis()
    if not r:
        return
    try:
        await r.incr(DOCX_TEMPLATE_REVISION_KEY)
    except Exception as e:
        logger.warning("bump docx template revision: {}", e)


async def _bump_pdf_template_revision() -> None:
    await _bump_docx_template_revision()


async def persist_template(template: ApplicationTemplate) -> None:
    """Сохраняет шаблон в `settings` и сбрасывает Redis-кэш."""
    await db.upsert_setting(APP_TEMPLATE_KEY, template.model_dump(mode="json"))
    await invalidate_template_cache()
    await _bump_pdf_template_revision()
