"""
Форматирование и генерация текста блоков через LLM.
"""

import hashlib
import json

from bot.config import config
from bot.logger import logger
from stdlib.handlers.blocks import BLOCKS
from stdlib.llm.client import langfuse, openai_client
from stdlib.llm.prompts import EDITOR_SYSTEM, GENERATE_SYSTEM
from stdlib.schemas import FormattedBlock, FormatResult

from stdlib.cache import get_cached_llm_response, save_llm_response_to_cache


def _make_cache_key(messages: list) -> str:
    messages_json = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(f"{config.OPENAI_MODEL}:{messages_json}".encode()).hexdigest()


def _build_messages(
    raw: str,
    context_str: str,
    block_number: int | None,
    generate: bool = False,
) -> list:
    block_hint = (
        f"блок {block_number} — «{BLOCKS[block_number]['title']}»"
        if block_number and block_number in BLOCKS
        else "текущий блок"
    )

    if generate:
        return [
            {"role": "system", "content": GENERATE_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"### КОНТЕКСТ\n{context_str}\n\n"
                    f"### ЗАДАЧА\n"
                    f"Предложи текст для {block_hint}.\n"
                    f"Описание: {BLOCKS.get(block_number, {}).get('question', 'Нет описания')}"
                ),
            },
        ]

    user_content = (
        f"### КОНТЕКСТ (только для понимания, не включать в ответ)\n"
        f"{context_str}\n\n"
        f"### ЗАДАЧА\n"
        f"Отредактируй ТОЛЬКО {block_hint}. "
        f"Верни только текст этого блока, без заголовков и контекста.\n\n"
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

    messages = _build_messages(raw, context_str, block_number, generate)

    async def _call(capture_usage: bool = False) -> FormatResult:
        cache_key = _make_cache_key(messages)

        # 1. Проверка кеша (через новый модуль)
        cached = await get_cached_llm_response(cache_key)
        if cached:
            logger.info("LLM cache hit | hash={}", cache_key[:8])
            return FormatResult(
                text=cached,
                changed=cached.strip() != raw.strip(),
                block_number=block_number,
                insufficient_context=not cached.strip(),
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

            return FormatResult(
                text=parsed.text,
                changed=parsed.text.strip() != raw.strip(),
                block_number=block_number,
                insufficient_context=not parsed.text.strip(),
            )

        except Exception as e:
            logger.error("format_text failed: {}. Returning raw.", e)
            return FormatResult(text=raw, changed=False, block_number=block_number)

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
