from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator, model_validator

from stdlib.template import ApplicationTemplate


def _strip_md(v: str) -> str:
    v = re.sub(r"\*\*(.+?)\*\*", r"\1", v)
    v = re.sub(r"__(.+?)__", r"\1", v)
    v = re.sub(r"\*(.+?)\*", r"\1", v)
    v = re.sub(r"_(.+?)_", r"\1", v)
    v = re.sub(r"^#{1,6}\s+", "", v, flags=re.MULTILINE)
    v = re.sub(r"`(.+?)`", r"\1", v)
    return v.strip()


def build_submit_memo_model(tpl: ApplicationTemplate) -> type[BaseModel]:
    """Модель для OpenAI tool submit_memo: поля совпадают с блоками шаблона."""
    field_defs: dict[str, Any] = {}
    for b in tpl.blocks:
        name = f"field_{b.id}"
        field_defs[name] = (
            str,
            Field(
                default="",
                alias=str(b.id),
                description=f"{b.title}. {b.question}",
            ),
        )
    return create_model(
        "SubmitMemo",
        __config__=ConfigDict(populate_by_name=True),
        __base__=BaseModel,
        **field_defs,
    )


def strip_submit_memo_args(raw: dict[str, Any]) -> dict[str, Any]:
    """Очистка markdown в значениях перед model_validate."""
    out: dict[str, Any] = {}
    for k, v in raw.items():
        out[k] = _strip_md(v) if isinstance(v, str) else v
    return out


# ── Structured Output для format_text ────────────────────────────────────────


class FormattedBlock(BaseModel):
    text: str = Field(description="Текст, приведённый к официально-деловому стилю")

    @field_validator("text", mode="before")
    @classmethod
    def clean(cls, v: str) -> str:
        return _strip_md(v)


# ── Structured Output для free-form чата ───────────────────────────────────────


class AskUser(BaseModel):
    question: str = Field(description="Уточняющий вопрос пользователю")


# ── Результат format_text ─────────────────────────────────────────────────────


class FormatResult(BaseModel):
    text: str
    changed: bool
    block_number: int | None = None
    insufficient_context: bool = False

    @model_validator(mode="after")
    def strip_text(self) -> "FormatResult":
        self.text = _strip_md(self.text)
        return self

    @property
    def intro(self) -> str:
        return (
            "Текст приведён к деловому стилю:"
            if self.changed
            else "Текст принят без изменений:"
        )


# ── Ответы LLM ────────────────────────────────────────────────────────────────


class LLMIncomplete(BaseModel):
    status: Literal["incomplete"]
    reply: str


class LLMComplete(BaseModel):
    status: Literal["complete"]
    blocks: dict[str, str]


class LLMError(BaseModel):
    status: Literal["error"]
    reply: str


LLMResponse = LLMComplete | LLMIncomplete | LLMError
