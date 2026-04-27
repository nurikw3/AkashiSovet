# stdlib/intent.py
import re

_DELEGATION_RE = re.compile(
    r"(напиши|придумай|предложи|сгенерируй|составь|пропиши|сделай).*(сам|за меня)?|"
    r"(сам|ты).*(напиши|придумай|предложи)|"
    r"не знаю|затрудняюсь|помоги написать",
    re.IGNORECASE,
)


def is_delegation(text: str) -> bool:
    return bool(_DELEGATION_RE.search(text))


def escape_markdown_v2(text: str) -> str:
    code_blocks = []

    def save_code(match):
        code_blocks.append(match.group(0))
        return f"__CODE_BLOCK_{len(code_blocks) - 1}__"

    text = re.sub(r"```[\s\S]*?```|`[^`]+`", save_code, text)
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    for char in escape_chars:
        text = text.replace(char, f"\\{char}")

    for i, code in enumerate(code_blocks):
        text = text.replace(f"__CODE_BLOCK_{i}__", code)
    return text
