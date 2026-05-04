"""Нормализация текста для PDF и LLM: склеенные нумерованные пункты → переносы строк."""

from __future__ import annotations

import re

_MARKERS = re.compile(r"(?:^|\s)\d{1,2}[\)\.]\s+")


def expand_numbered_newlines(text: str) -> str:
    """Расставляет переносы между пунктами «1) … 2) …», если модель выдала одну строку.

    Учитывает типичный случай с точкой с запятой перед следующим номером и случай
    «1) … 2) …» только через пробел.
    """
    if not text or not str(text).strip():
        return text
    s = str(text)
    if "\n" in s:
        return "\n".join(_expand_one_line_numbering(line) for line in s.split("\n"))
    return _expand_one_line_numbering(s)


def _expand_one_line_numbering(line: str) -> str:
    t = line.strip()
    if not t:
        return line
    # «...; 2) ...; 3) ...» в одной строке
    t2 = re.sub(r";\s*(?=\d{1,2}[\)\.]\s)", "\n", t)
    if "\n" in t2:
        return t2
    # «1) ... 2) ...» без точки с запятой (≥2 маркеров пункта)
    if len(_MARKERS.findall(t2)) < 2:
        return t2
    # Пробел перед «2)», если слева символ слова/знака конца фразы
    return re.sub(
        r'(?<=[\wа-яёА-ЯЁ»"%;,\.\)\]])\s+(?=\d{1,2}[\)\.]\s)',
        "\n",
        t2,
    )
