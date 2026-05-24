from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator, model_validator

from stdlib.template import ApplicationTemplate, block_llm_instruction, block_wants_numbered_list
from stdlib.text_normalize import ensure_structured_numbered_list, expand_numbered_newlines


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
        desc = block_llm_instruction(b)
        if block_wants_numbered_list(b):
            desc = (
                f"{desc}. Несколько вариантов, решений или поручений — "
                "нумерованный список (1) … 2) …), каждый пункт с новой строки, не сплошным абзацем."
            )
        field_defs[name] = (
            str,
            Field(
                default="",
                alias=str(b.id),
                description=desc,
            ),
        )
    return create_model(
        "SubmitMemo",
        __config__=ConfigDict(populate_by_name=True),
        __base__=BaseModel,
        **field_defs,
    )


def strip_submit_memo_args(raw: dict[str, Any], tpl: ApplicationTemplate | None = None) -> dict[str, Any]:
    """Очистка markdown и склеенных нумерованных списков перед model_validate."""
    blocks_by_id: dict[str, Any] = {}
    if tpl is not None:
        blocks_by_id = {str(b.id): b for b in tpl.blocks}

    out: dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(v, str):
            cleaned = expand_numbered_newlines(_strip_md(v))
            block = blocks_by_id.get(str(k))
            if block and block_wants_numbered_list(block):
                cleaned = ensure_structured_numbered_list(cleaned)
            out[k] = cleaned
        else:
            out[k] = v
    return out


# ── Structured Output для format_text ────────────────────────────────────────


class FormattedBlock(BaseModel):
    text: str = Field(
        description=(
            "Текст блока в деловом стиле. Несколько вариантов решений, поручений или мер — "
            "структурированный нумерованный список, каждый пункт с новой строки (1) 2) 3)), "
            "не одним сплошным абзацем и не одной строкой через точку с запятой."
        )
    )

    @field_validator("text", mode="before")
    @classmethod
    def clean(cls, v: str) -> str:
        return expand_numbered_newlines(_strip_md(v))


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
