"""Общая логика контента документа (PDF/DOCX)."""

from __future__ import annotations

import ast
import json
import re
from typing import Any

from stdlib.template import ApplicationTemplate
from stdlib.text_normalize import expand_numbered_newlines

_UNSAFE_DASH = str.maketrans(
    {
        "\u2011": "-",
        "\u2010": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\ufeff": "",
        "\u00ad": "",
    }
)

_NUMBERED_LINE = re.compile(r"^\d+[\.\)]\s*")


def normalize_user_text(text: str) -> str:
    if not text:
        return text
    t = text.translate(_UNSAFE_DASH)
    for z in ("\u200b", "\u200c", "\u200d", "\u2060"):
        t = t.replace(z, "")
    return t


def normalize_risk_placeholder(block_title: str, body_raw: str) -> str:
    if "риск" in block_title.lower() and body_raw.lower().strip() == "не применимо":
        return "(не применимо)"
    return body_raw


def parse_attachments_field(raw: Any) -> list:
    attachments = raw or []
    if isinstance(attachments, str):
        try:
            attachments = ast.literal_eval(attachments)
        except (ValueError, SyntaxError):
            try:
                attachments = json.loads(attachments)
            except Exception:
                if attachments.strip() in ("[]", "", "[ ]"):
                    attachments = []
                else:
                    attachments = [attachments]
    return attachments


def topic_from_data(
    data: dict,
    tpl: ApplicationTemplate | None,
    blocks_map: dict[str, str] | None,
) -> str:
    if tpl is not None and blocks_map is not None and tpl.blocks:
        return blocks_map.get(str(tpl.blocks[0].id), "") or "Без темы"
    return data.get("topic") or ""


def build_sections(
    data: dict,
    tpl: ApplicationTemplate | None,
    blocks_map: dict[str, str] | None,
) -> tuple[list[tuple[str, str]], int]:
    """Возвращает (список (заголовок секции, тело), номер блока приложений)."""
    if tpl is not None and blocks_map is not None:
        sections: list[tuple[str, str]] = []
        for sec_idx, block in enumerate(tpl.blocks[1:], start=1):
            raw = blocks_map.get(str(block.id), "")
            body = normalize_risk_placeholder(block.title, raw)
            sections.append((f"{sec_idx}. {block.title}:", body))
        return sections, len(tpl.blocks)

    risks_raw = data.get("risks") or ""
    risks_text = (
        "(не применимо)"
        if risks_raw.lower().strip() == "не применимо"
        else risks_raw
    )
    sections = [
        ("1. Краткое описание и суть вопроса:", data.get("description") or ""),
        ("2. Основание для вынесения:", data.get("basis") or ""),
        ("3. Предлагаемое решение / варианты решений:", data.get("solution") or ""),
        ("4. Риски и последствия (если актуально):", risks_text),
    ]
    return sections, 5


def split_section_body(body: str) -> tuple[list[str], bool]:
    """Разбивает тело секции на строки; has_numbering — нумерованный список пунктов."""
    body = normalize_user_text(body)
    body = expand_numbered_newlines(body)
    lines = [line.strip() for line in body.split("\n") if line.strip()]
    has_numbering = any(
        len(line) > 2
        and line[0].isdigit()
        and (line[1:3] == ". " or line[1:3] == ") ")
        for line in lines
    )
    if has_numbering and lines:
        lines = [_NUMBERED_LINE.sub("", line) for line in lines]
    return lines, has_numbering


def signer_name_from_data(data: dict) -> str:
    return normalize_user_text(
        str(
            data.get("full_name")
            or data.get("fio")
            or data.get("username")
            or data.get("name")
            or "Неизвестно"
        )
    )


def signer_position_from_data(data: dict) -> str:
    return normalize_user_text(str(data.get("position") or "Руководитель подразделения"))
