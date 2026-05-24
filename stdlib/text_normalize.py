from __future__ import annotations

import re

_MARKERS = re.compile(r"(?:^|\s)\d{1,2}[\)\.]\s+")
_ALSO_SPLIT = re.compile(r"\s+(?:а\s+также|также|во-?вторых|в\s+дополнение)\s+", re.I)


def has_numbered_list(text: str) -> bool:
    if not text or not str(text).strip():
        return False
    s = str(text)
    if len(_MARKERS.findall(s)) >= 2:
        return True
    lines = [ln.strip() for ln in s.split("\n") if ln.strip()]
    return len(lines) >= 2 and any(_MARKERS.search(ln) for ln in lines)


def expand_numbered_newlines(text: str) -> str:
    if not text or not str(text).strip():
        return text
    s = str(text)
    if "\n" in s:
        return "\n".join(_expand_one_line_numbering(line) for line in s.split("\n"))
    return _expand_one_line_numbering(s)


def ensure_structured_numbered_list(text: str) -> str:
    """Постобработка: разбить несколько пунктов в одной строке в нумерованный список."""
    text = expand_numbered_newlines(text)
    if not text or not str(text).strip() or has_numbered_list(text):
        return text

    s = str(text).strip()
    if "\n" in s:
        return s

    for splitter in (
        lambda t: re.split(r";\s+", t),
        lambda t: _ALSO_SPLIT.split(t),
    ):
        parts = [p.strip(" ;.,") for p in splitter(s) if p.strip(" ;.,")]
        if len(parts) >= 2 and all(len(p) > 8 for p in parts):
            return "\n".join(f"{i}) {p}" for i, p in enumerate(parts, start=1))

    return s


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
