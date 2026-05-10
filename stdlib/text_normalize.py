from __future__ import annotations

import re

_MARKERS = re.compile(r"(?:^|\s)\d{1,2}[\)\.]\s+")


def expand_numbered_newlines(text: str) -> str:
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
    t2 = re.sub(r";\s*(?=\d{1,2}[\)\.]\s)", "\n", t)
    if "\n" in t2:
        return t2
    if len(_MARKERS.findall(t2)) < 2:
        return t2
    return re.sub(
        r'(?<=[\wа-яёА-ЯЁ»"%;,\.\)\]])\s+(?=\d{1,2}[\)\.]\s)',
        "\n",
        t2,
    )
