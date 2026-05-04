"""Единое текстовое представление блоков заявки (plain + HTML с <pre> для Telegram)."""

from __future__ import annotations

from html import escape

from stdlib.template import ApplicationTemplate


def format_blocks_plain_copy(
    blocks: dict[str, str], tpl: ApplicationTemplate
) -> str:
    """Все блоки подряд: нумерация, заголовок шаблона, текст — удобно копировать."""
    lines: list[str] = []
    for idx, b in enumerate(tpl.blocks, start=1):
        val = (blocks.get(str(b.id)) or "").strip()
        lines.append(f"{idx}. {b.title}")
        lines.append(val if val else "—")
        lines.append("")
    return "\n".join(lines).rstrip()


def html_pre_block(plain_body: str) -> str:
    """Один экранированный блок <pre> (parse_mode=HTML)."""
    return f"<pre>{escape(plain_body)}</pre>"


def build_files_step_message(plain_body: str) -> str:
    """Сообщение после сбора блоков: сводка в monospace + приглашение к вложениям."""
    return (
        "✅ <b>Сводка по заявке</b> — скопируйте текст из блока ниже при необходимости.\n\n"
        f"{html_pre_block(plain_body)}\n\n"
        "<b>Приложения</b>\n"
        "Прикрепите файлы к заявке (договоры, расчёты и т.д.). "
        "Отправляйте по одному. Когда закончите — нажмите <b>Готово</b>."
    )


def build_review_text_snapshot(plain_body: str) -> str:
    """Краткая текстовая копия заявки перед отправкой (рядом с PDF)."""
    return (
        "📋 <b>Текст заявки для копирования</b>\n\n"
        f"{html_pre_block(plain_body)}"
    )


def chunk_plain_text(text: str, max_chars: int = 3500) -> list[str]:
    """Разбивает длинный текст по строкам, чтобы уложиться в лимит Telegram (~4096)."""
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= max_chars:
            chunks.append(rest)
            break
        cut = rest.rfind("\n", 0, max_chars)
        if cut <= 0:
            cut = max_chars
        chunks.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    return chunks
