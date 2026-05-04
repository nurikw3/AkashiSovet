"""HTML-тексты для Telegram (parse_mode=HTML): сводка по блокам заявки."""

from __future__ import annotations

from html import escape

from stdlib.template import ApplicationTemplate

# Текст «Полезно копировать» — заголовок блока жирным, значение в <pre> (monospace)

ATTACHMENTS_FOOTER_HTML = (
    "<b>Приложения</b>\n"
    "Прикрепите файлы к заявке (договоры, расчёты, согласования и т.д.).\n"
    "Отправляйте по одному. Когда закончите — нажмите <b>Готово</b>."
)

INTRO_FREE_FORM_HTML = "✅ Отлично! Я собрал всю необходимую информацию."
INTRO_STEP_FILLED_HTML = "✅ <b>Отлично! Все разделы заполнены.</b>"
INTRO_REVIEW_HTML = ""
INTRO_FALLBACK_NO_PDF_HTML = "📝 <b>Проверьте заявку</b> (PDF временно недоступен)."


def build_blocks_summary_html(
    tpl: ApplicationTemplate,
    blocks: dict[str, str],
    intro_html: str,
    *,
    attachments_footer: str | None = ATTACHMENTS_FOOTER_HTML,
) -> str:
    """
    Сводка всех блоков: заголовки жирным, текст блока в <pre> для удобного копирования.
    ``attachments_footer=None`` — без приглашения к вложениям (например экран после PDF).
    """
    parts: list[str] = []
    intro_stripped = intro_html.strip()
    if intro_stripped:
        parts.extend([intro_stripped, ""])
    for idx, b in enumerate(tpl.blocks, start=1):
        val = blocks.get(str(b.id), "")
        parts.append(f"<b>{idx}. {escape(b.title)}</b>")
        parts.append(f"<pre>{escape(val)}</pre>")
    if attachments_footer:
        parts.extend(["", attachments_footer])
    return "\n".join(parts)


def _block_html_fragments(
    tpl: ApplicationTemplate, blocks: dict[str, str]
) -> list[str]:
    return [
        f"<b>{idx}. {escape(b.title)}</b>\n<pre>{escape(blocks.get(str(b.id), ''))}</pre>"
        for idx, b in enumerate(tpl.blocks, start=1)
    ]


def chunk_blocks_summary_html(
    tpl: ApplicationTemplate,
    blocks: dict[str, str],
    intro_html: str,
    *,
    attachments_footer: str | None = ATTACHMENTS_FOOTER_HTML,
    max_chars: int = 3800,
) -> list[str]:
    """
    Тот же формат, что ``build_blocks_summary_html``, но разбитый на несколько сообщений,
    если текст не помещается в лимит Telegram (~4096).
    """
    frags = _block_html_fragments(tpl, blocks)
    if not frags:
        one = intro_html.strip()
        if attachments_footer:
            one += "\n\n" + attachments_footer
        return [one]

    messages: list[str] = []
    i = 0
    first_chunk = True

    while i < len(frags):
        if first_chunk:
            intro_stripped = intro_html.strip()
            header = (intro_stripped + "\n\n") if intro_stripped else ""
        else:
            header = "… <i>продолжение</i>\n\n"
        first_chunk = False
        parts_in_msg: list[str] = []
        len_so_far = len(header)

        while i < len(frags):
            p = frags[i]
            extra = len(p) + (2 if parts_in_msg else 0)
            if parts_in_msg and len_so_far + extra > max_chars:
                break
            parts_in_msg.append(p)
            len_so_far += extra
            i += 1

        body = header + "\n\n".join(parts_in_msg)
        messages.append(body)

    if attachments_footer and messages:
        messages[-1] = messages[-1] + "\n\n" + attachments_footer

    return messages
