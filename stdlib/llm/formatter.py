"""
Форматирование и генерация текста блоков через LLM.
"""

import hashlib
import json

from bot.config import config
from bot.logger import logger
from stdlib.llm.client import langfuse, openai_client
from stdlib.llm.prompts import EDITOR_SYSTEM, GENERATE_SYSTEM, NUMBERED_LIST_BLOCK_HINT
from stdlib.text_normalize import ensure_structured_numbered_list, expand_numbered_newlines
from stdlib.schemas import FormattedBlock, FormatResult
from stdlib.template import (
    ApplicationTemplate,
    BlockDefinition,
    block_llm_instruction,
    block_wants_numbered_list,
    get_template,
)

from stdlib.cache import get_cached_llm_response, save_llm_response_to_cache


def _make_cache_key(
    messages: list,
    *,
    app_id: int | None,
    user_id: int | None,
    block_number: int | None,
    generate: bool,
) -> str:
    """В ключ входят заявка (и user), иначе Redis отдаёт ответ от другой заявки с тем же текстом."""
    messages_json = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    scope = f"app_id={app_id}|user_id={user_id}|block={block_number}|gen={generate}"
    payload = f"{config.OPENAI_MODEL}:{scope}:{messages_json}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _block_label(tpl: ApplicationTemplate, block_number: int | None) -> tuple[str, str, BlockDefinition | None]:
    if not block_number:
        return "текущий блок", "Нет описания", None
    try:
        b = tpl.get_block(block_number)
        return f"блок {block_number} — «{b.title}»", block_llm_instruction(b), b
    except ValueError:
        return f"блок {block_number}", "Нет описания", None


def _format_block_output(text: str, block: BlockDefinition | None) -> str:
    out = (text or "").strip()
    if not out:
        return out
    out = expand_numbered_newlines(out)
    if block and block_wants_numbered_list(block):
        out = ensure_structured_numbered_list(out)
    return out


def _task_suffix(block: BlockDefinition | None) -> str:
    if block and block_wants_numbered_list(block):
        return f"\n\n{NUMBERED_LIST_BLOCK_HINT}"
    return ""


def _build_messages(
    raw: str,
    context_str: str,
    block_number: int | None,
    generate: bool,
    tpl: ApplicationTemplate,
) -> list:
    block_hint, block_instruction, block = _block_label(tpl, block_number)
    task_suffix = _task_suffix(block)

    if generate:
        return [
            {"role": "system", "content": GENERATE_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"### КОНТЕКСТ\n{context_str}\n\n"
                    f"### ЗАДАЧА\n"
                    f"Предложи текст для {block_hint}.\n"
                    f"Описание: {block_instruction}{task_suffix}"
                ),
            },
        ]

    user_content = (
        f"### КОНТЕКСТ (только для понимания, не включать в ответ)\n"
        f"{context_str}\n\n"
        f"### ЗАДАЧА\n"
        f"Отредактируй ТОЛЬКО {block_hint}. "
        f"Верни только текст этого блока, без заголовков и контекста.\n"
        f"Описание блока: {block_instruction}{task_suffix}\n\n"
        f"### ТЕКСТ ДЛЯ РЕДАКТИРОВАНИЯ\n"
        f"{raw}"
    )

    return [
        {"role": "system", "content": EDITOR_SYSTEM},
        {"role": "user", "content": user_content},
    ]


async def format_text(
    raw: str,
    context_blocks: dict | None = None,
    user_id: int | None = None,
    app_id: int | None = None,
    block_number: int | None = None,
    generate: bool = False,
) -> FormatResult:
    if context_blocks:
        context_str = "\n".join(
            f"Блок {k}: {v}"
            for k, v in context_blocks.items()
            if str(k).isdigit() and v
        )
    else:
        context_str = "(Контекст пуст)"

    if not context_str:
        context_str = "(Контекст пуст)"

    tpl = await get_template()
    messages = _build_messages(raw, context_str, block_number, generate, tpl)
    block = None
    if block_number:
        try:
            block = tpl.get_block(block_number)
        except ValueError:
            block = None

    async def _call(capture_usage: bool = False) -> FormatResult:
        cache_key = _make_cache_key(
            messages,
            app_id=app_id,
            user_id=user_id,
            block_number=block_number,
            generate=generate,
        )

        # 1. Проверка кеша (через новый модуль)
        cached = await get_cached_llm_response(cache_key)
        if cached:
            logger.info("LLM cache hit | hash={}", cache_key[:8])
            out = _format_block_output(cached, block) if cached.strip() else raw.strip()
            return FormatResult(
                text=out,
                changed=out != raw.strip(),
                block_number=block_number,
                insufficient_context=not out,
            )

        try:
            response = await openai_client.beta.chat.completions.parse(
                model=config.OPENAI_MODEL,
                messages=messages,
                response_format=FormattedBlock,
                temperature=0.4 if generate else 0.2,
                max_tokens=1000,
            )

            choice = response.choices[0]
            parsed: FormattedBlock = choice.message.parsed
            logger.info(
                ">>> BEFORE SAVE: cache_key={}, text_len={}",
                cache_key[:10],
                len(parsed.text),
            )

            # 2. Сохранение в кеш (ИСПРАВЛЕНО: используем функцию из stdlib.cache)
            await save_llm_response_to_cache(cache_key, parsed.text)
            logger.info(
                ">>> AFTER SAVE: cache_key={}, text_len={}",
                cache_key[:10],
                len(parsed.text),
            )

            if capture_usage and langfuse:
                try:
                    langfuse.update_current_generation(
                        output=parsed.text,
                        usage_details={
                            "input": response.usage.prompt_tokens,
                            "output": response.usage.completion_tokens,
                            "total": response.usage.total_tokens,
                        },
                    )
                except Exception as e:
                    logger.warning("Langfuse usage update failed: {}", e)

            logger.info(
                "LLM ok | app={} block={} generate={} tokens={}",
                app_id,
                block_number,
                generate,
                getattr(response.usage, "total_tokens", "?"),
            )

            out = _format_block_output(parsed.text or "", block)
            if not out:
                out = raw.strip()
            return FormatResult(
                text=out,
                changed=out != raw.strip(),
                block_number=block_number,
                insufficient_context=not out,
            )

        except Exception as e:
            logger.error("format_text failed: {}. Returning raw.", e)
            fallback = _format_block_output(raw, block)
            return FormatResult(text=fallback, changed=False, block_number=block_number)

    if langfuse is None:
        return await _call()

    try:
        from langfuse import propagate_attributes

        with propagate_attributes(user_id=str(user_id) if user_id else None):
            with langfuse.start_as_current_observation(
                name="format-text",
                as_type="generation",
                input=messages,
                model=config.OPENAI_MODEL,
                model_parameters={
                    "temperature": 0.4 if generate else 0.2,
                    "max_tokens": 500,
                },
                metadata={"app_id": app_id, "generate": generate},
            ):
                return await _call(capture_usage=True)

    except Exception as e:
        logger.warning("Langfuse context failed: {}", e)
        return await _call()
