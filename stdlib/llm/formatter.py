"""
Форматирование и генерация текста блоков через LLM.
"""

import hashlib
import json

from bot.config import config
from bot.logger import logger
from stdlib.llm.client import langfuse, openai_client
from stdlib.llm.prompts import EDITOR_SYSTEM, GENERATE_SYSTEM
from stdlib.schemas import FormattedBlock, FormatResult
from stdlib.template import get_template, ApplicationTemplate

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


def _block_label(tpl: ApplicationTemplate, block_number: int | None) -> tuple[str, str]:
    if not block_number:
        return "текущий блок", "Нет описания"
    try:
        b = tpl.get_block(block_number)
        return f"блок {block_number} — «{b.title}»", b.question
    except ValueError:
        return f"блок {block_number}", "Нет описания"


def _build_messages(
    raw: str,
    context_str: str,
    block_number: int | None,
    generate: bool,
    tpl: ApplicationTemplate,
) -> list:
    block_hint, block_question = _block_label(tpl, block_number)

    if generate:
        return [
            {"role": "system", "content": GENERATE_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"### КОНТЕКСТ\n{context_str}\n\n"
                    f"### ЗАДАЧА\n"
                    f"Предложи текст для {block_hint}.\n"
                    f"Описание: {block_question}"
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

    tpl = await get_template()
    messages = _build_messages(raw, context_str, block_number, generate, tpl)

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
            out = cached.strip() if cached.strip() else raw.strip()
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

            out = (parsed.text or "").strip()
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
