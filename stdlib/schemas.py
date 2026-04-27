from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal
import re


def _strip_md(v: str) -> str:
    v = re.sub(r"\*\*(.+?)\*\*", r"\1", v)
    v = re.sub(r"__(.+?)__", r"\1", v)
    v = re.sub(r"\*(.+?)\*", r"\1", v)
    v = re.sub(r"_(.+?)_", r"\1", v)
    v = re.sub(r"^#{1,6}\s+", "", v, flags=re.MULTILINE)
    v = re.sub(r"`(.+?)`", r"\1", v)
    return v.strip()


def _block_field(n: int) -> Field:
    from stdlib.handlers.blocks import BLOCKS

    return Field(
        alias=str(n),
        description=f"{BLOCKS[n]['title']}. {BLOCKS[n]['question']}",
    )


# ── Блоки служебной записки ───────────────────────────────────────────────────


class MemoBlocks(BaseModel):
    b1: str = Field(alias="1")
    b2: str = Field(alias="2")
    b3: str = Field(alias="3")
    b4: str = Field(alias="4")
    b5: str = Field(alias="5")

    model_config = {"populate_by_name": True}

    @field_validator("b1", "b2", "b3", "b4", "b5", mode="before")
    @classmethod
    def clean(cls, v: str) -> str:
        return _strip_md(v)

    def to_context_str(self) -> str:
        return "\n".join(
            [
                f"Блок 1: {self.b1}",
                f"Блок 2: {self.b2}",
                f"Блок 3: {self.b3}",
                f"Блок 4: {self.b4}",
                f"Блок 5: {self.b5}",
            ]
        )

    def as_numbered_dict(self) -> dict[str, str]:
        return self.model_dump(by_alias=True)

    def get_block(self, n: int) -> str:
        return getattr(self, f"b{n}")

    def set_block(self, n: int, value: str) -> "MemoBlocks":
        data = self.as_numbered_dict()
        data[str(n)] = value
        return MemoBlocks.model_validate(data)


# ── Structured Output для format_text ────────────────────────────────────────


class FormattedBlock(BaseModel):
    text: str = Field(description="Текст, приведённый к официально-деловому стилю")

    @field_validator("text", mode="before")
    @classmethod
    def clean(cls, v: str) -> str:
        return _strip_md(v)


# ── Structured Output для free-form чата ─────────────────────────────────────


class AskUser(BaseModel):
    question: str = Field(description="Уточняющий вопрос пользователю")


class SubmitMemo(BaseModel):
    b1: str = _block_field(1)
    b2: str = _block_field(2)
    b3: str = _block_field(3)
    b4: str = _block_field(4)
    b5: str = _block_field(5)

    model_config = {"populate_by_name": True}

    @field_validator("b1", "b2", "b3", "b4", "b5", mode="before")
    @classmethod
    def clean(cls, v: str) -> str:
        return _strip_md(v)

    def to_memo_blocks(self) -> MemoBlocks:
        return MemoBlocks.model_validate(self.model_dump(by_alias=True))


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
    blocks: MemoBlocks


class LLMError(BaseModel):
    status: Literal["error"]
    reply: str


LLMResponse = LLMComplete | LLMIncomplete | LLMError
