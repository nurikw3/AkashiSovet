"""
LLM-форматирование текста с трейсингом через Langfuse v4 и управлением промптами.
"""

from openai import AsyncOpenAI
from bot.config import config
from bot.logger import logger
import stdlib.db as db
import hashlib
import json
import re

openai_client = AsyncOpenAI(
    api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL
)

# Langfuse v4 — инициализируем только если ключи заданы
_langfuse = None
if config.langfuse_enabled:
    try:
        from langfuse import Langfuse, propagate_attributes

        _langfuse = Langfuse(
            public_key=config.LANGFUSE_PUBLIC_KEY,
            secret_key=config.LANGFUSE_SECRET_KEY,
            host=config.LANGFUSE_BASE_URL,
        )
        logger.info("Langfuse трейсинг включён (host={})", config.LANGFUSE_BASE_URL)
    except Exception as e:
        logger.warning("Langfuse недоступен, трейсинг отключён: {}", e)

_SYSTEM_PROMPT = (
    "Ты редактор текстов. Твоя задача — привести переданный пользователем текст в официально-деловой стиль.\n"
    "Соблюдай следующие правила:\n"
    "— Сохраняй исходный смысл. \n"
    "— КАТЕГОРИЧЕСКИ ЗАПРЕЩАЕТСЯ выдумывать несуществующие документы, приказы, даты, имена или регламенты. Если в тексте этого нет, не добавляй.\n"
    "— Улучшай грамматику и пунктуацию.\n"
    "— Текст должен звучать профессионально (Board-ready).\n"
    "— Если текст уже идеален, верни его без изменений.\n"
    "— В ином случае исправь текст и предоставь только финальный вариант.\n"
    "— Запрещено добавлять пояснения, вводные фразы или постскриптумы. Только исправленный текст."
)

_FALLBACK_MESSAGES = [
    {"role": "system", "content": _SYSTEM_PROMPT},
    {
        "role": "user",
        "content": "Контекст служебной записки:\n{{context}}\n\nТекст для редактирования и интеграции в шаблон:\n{{raw}}",
    },
]


def ensure_sentence_end(text: str) -> str:
    if not text:
        return text

    text = text.rstrip()  # убираем пробелы справа

    # если уже заканчивается на ., ! или ?
    if text[-1] in ".!?":
        return text

    return text + "."


def preprocess_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    text = text[:1].upper() + text[1:] if text else text
    text = ensure_sentence_end(text)

    return text


async def format_text(
    raw: str,
    context_blocks: dict | None = None,
    user_id: int | None = None,
    app_id: int | None = None,
) -> str:
    """
    Приводит текст к официально-деловому стилю.
    Использует контекст предыдущих блоков.
    Берёт промпт `editor_prompt` из Langfuse (если доступно).
    """
    context_str = ""
    if context_blocks:
        context_str = "\n".join(
            f"Блок {k}: {v}"
            for k, v in context_blocks.items()
            if str(k).isdigit() and v
        )
    if not context_str.strip():
        context_str = "(Контекст пуст)"

    prompt_client = None
    messages = []

    if _langfuse:
        try:
            prompt_client = _langfuse.get_prompt(
                name="editor_prompt", type="chat", fallback=_FALLBACK_MESSAGES
            )
            messages = prompt_client.compile(context=context_str, raw=raw)
        except Exception as e:
            logger.warning("Langfuse get_prompt failed: {}", e)

    if not messages:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Контекст заявки:\n{context_str}\n\nТекст для редактирования:\n{raw}",
            },
        ]

    # Предварительная обработка входных сообщений для минимизации
    for m in messages:
        if m["role"] == "user":
            m["content"] = preprocess_text(m["content"])

    # ── Без Langfuse ──────────────────────────────────────────────────────────
    if _langfuse is None:
        return await _call_llm(messages, app_id, user_id, raw)

    # ── С Langfuse: оборачиваем вызов в generation-контекст ──────────────────
    try:
        with propagate_attributes(user_id=str(user_id) if user_id else None):
            with _langfuse.start_as_current_observation(
                name="format-text",
                as_type="generation",
                input=messages,
                model=config.OPENAI_MODEL,
                model_parameters={"temperature": 0.2, "max_tokens": 1000},
                metadata={"app_id": app_id},
                prompt=prompt_client,  # Связываем с промптом из Langfuse
            ):
                result = await _call_llm(
                    messages, app_id, user_id, raw, capture_usage=True
                )
                return result
    except Exception as e:
        logger.warning("Langfuse context failed, running without tracing: {}", e)
        return await _call_llm(messages, app_id, user_id, raw)


async def _call_llm(
    messages: list,
    app_id: int | None,
    user_id: int | None,
    raw: str,
    capture_usage: bool = False,
) -> str:
    """Делает запрос к OpenAI-совместимому API с кэшированием."""
    # Генерация хеша для кэширования
    messages_json = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    prompt_hash = hashlib.sha256(
        f"{config.OPENAI_MODEL}:{messages_json}".encode("utf-8")
    ).hexdigest()

    # Проверка кэша
    cached_result = await db.get_cached_llm_response(prompt_hash)
    if cached_result:
        logger.info("LLM cache hit | hash={}", prompt_hash[:8])
        return cached_result

    try:
        response = await openai_client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=1000,
        )
        result = response.choices[0].message.content.strip()

        # Сохранение в кэш
        await db.save_llm_response_to_cache(prompt_hash, result)

        # Обновляем текущий Langfuse span usage (если внутри контекста)
        if capture_usage and _langfuse is not None:
            try:
                _langfuse.update_current_generation(
                    output=result,
                    usage_details={
                        "input": response.usage.prompt_tokens,
                        "output": response.usage.completion_tokens,
                        "total": response.usage.total_tokens,
                    },
                )
            except Exception as e:
                logger.warning("Langfuse update_current_generation failed: {}", e)

        logger.info(
            "LLM ok | model={} app_id={} user_id={} tokens={}",
            config.OPENAI_MODEL,
            app_id,
            user_id,
            getattr(response.usage, "total_tokens", "?"),
        )
        return result

    except Exception as e:
        logger.error("LLM format_text failed: {}. Returning raw text.", e)
        return raw  # fallback: возвращаем оригинал


# _FREE_FORM_SYSTEM = (
#     "Ты — умный ассистент, помогающий составить служебную записку. "
#     "Для служебной записки необходимо собрать 5 пунктов:\n"
#     "1. Тема вопроса.\n"
#     "2. Краткое описание и суть вопроса.\n"
#     "3. Основание для вынесения.\n"
#     "4. Предлагаемое решение.\n"
#     "5. Риски и последствия (если нет, то 'не применимо').\n\n"
#     "Проанализируй предоставленный пользователем текст. Если какой-либо важной информации не хватает, "
#     "задай короткий уточняющий вопрос. Если информации достаточно, сформируй готовые блоки.\n\n"
#     "ОТВЕЧАЙ СТРОГО В ФОРМАТЕ JSON:\n"
#     "Если нужны уточнения:\n"
#     '{"status": "incomplete", "reply": "текст твоего вопроса к пользователю"}\n'
#     "Если всё собрано (тексты блоков должны быть в официально-деловом стиле):\n"
#     '{"status": "complete", "blocks": {"1": "тема...", "2": "описание...", "3": "основание...", "4": "решение...", "5": "риски..."}}'
# )

from stdlib.handlers.blocks import BLOCKS


def _build_free_form_system_prompt() -> str:
    lines = [
        "Ты — проактивный ассистент ПК «AKASHI Data Center PLC».",
        "Твоя цель — собрать данные для 5 блоков служебной записки.",
        "",
        "═══ АБСОЛЮТНЫЙ ЗАПРЕТ (важнее всех остальных правил) ═══",
        "Никогда не добавляй факты, которых нет в словах пользователя:",
        "— даты, периоды, годы",
        "— названия документов, приказов, регламентов, номера актов",
        "— имена, должности, названия отделов",
        "— конкретные цифры, суммы, проценты",
        "— детали исследований или аудитов, которые пользователь не упомянул",
        "Если пользователь сказал «был аудит» — пиши «по результатам аудита», без дат и деталей.",
        "",
        "═══ ПРИМЕР ═══",
        "Пользователь: «нужно обновить охлаждение, был аудит»",
        "✓ «По результатам проведённого аудита выявлена необходимость модернизации системы охлаждения.»",
        "✗ «По результатам аудита от марта 2024 г. ...» — дату не называл, добавлять запрещено.",
        "",
        "═══ БЛОКИ ═══",
    ]
    for i in range(1, 6):
        lines.append(f"{i}. {BLOCKS[i]['title']} — {BLOCKS[i]['question']}")
    lines += [
        "",
        "═══ ПРАВИЛА ═══",
        "— Обязательно вызывай одну из функций: ask_user или submit_memo.",
        "— Если не хватает данных для блоков 3, 4 или 5 — вызови ask_user с одним коротким вопросом.",
        "— Не задавай общих вопросов о политиках компании.",
        "— При submit_memo стилизуй текст официально, но включай ТОЛЬКО то, что сказал пользователь.",
    ]
    return "\n".join(lines)


_FREE_FORM_SYSTEM = _build_free_form_system_prompt()


async def process_free_form_chat(
    history: list, app_id: int | None = None, user_id: int | None = None
) -> dict:
    """Анализирует диалог и возвращает JSON со статусом сбора данных."""

    messages = [{"role": "system", "content": _FREE_FORM_SYSTEM}] + history
    logger.debug(
        "process_free_form_chat: user_id={}, history_len={}", user_id, len(history)
    )

    tools = [
        {
            "type": "function",
            "function": {
                "name": "ask_user",
                "description": "Задать уточняющий вопрос пользователю.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "Текст вопроса"}
                    },
                    "required": ["question"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "submit_memo",
                "description": "Сформировать готовые 5 блоков служебной записки.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "1": {"type": "string", "description": "Блок 1: Тема вопроса"},
                        "2": {
                            "type": "string",
                            "description": "Блок 2: Краткое описание и суть вопроса",
                        },
                        "3": {
                            "type": "string",
                            "description": "Блок 3: Основание для вынесения",
                        },
                        "4": {
                            "type": "string",
                            "description": "Блок 4: Предлагаемое решение",
                        },
                        "5": {
                            "type": "string",
                            "description": "Блок 5: Риски и последствия",
                        },
                    },
                    "required": ["1", "2", "3", "4", "5"],
                },
            },
        },
    ]

    async def _call():
        response = await openai_client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=messages,
            temperature=0.2,
            tools=tools,
            tool_choice="required",
            max_tokens=800,
        )
        msg = response.choices[0].message

        # update usage
        if _langfuse:
            try:
                _langfuse.update_current_generation(
                    output=msg.content or "Tool Call",
                    usage_details={
                        "input": getattr(response.usage, "prompt_tokens", 0),
                        "output": getattr(response.usage, "completion_tokens", 0),
                        "total": getattr(response.usage, "total_tokens", 0),
                    },
                )
            except Exception as e:
                logger.warning("Langfuse update_current_generation failed: {}", e)

        if msg.tool_calls:
            tool_call = msg.tool_calls[0]
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)

            logger.info("Free-form LLM called tool '{}' for app {}", name, app_id)
            if name == "ask_user":
                return {
                    "status": "incomplete",
                    "reply": args.get("question", "Пожалуйста, уточните детали."),
                }
            elif name == "submit_memo":
                return {"status": "complete", "blocks": args}

        return {
            "status": "incomplete",
            "reply": msg.content or "Пожалуйста, уточните детали.",
        }

    try:
        if _langfuse:
            with propagate_attributes(user_id=str(user_id) if user_id else None):
                with _langfuse.start_as_current_observation(
                    name="free-form-chat",
                    as_type="generation",
                    input=messages,
                    model=config.OPENAI_MODEL,
                    metadata={"app_id": app_id},
                ):
                    return await _call()
        else:
            return await _call()
    except Exception as e:
        logger.error("Free-form LLM failed: {}", e)
        return {
            "status": "error",
            "reply": "Произошла ошибка при анализе текста. Пожалуйста, попробуйте еще раз.",
        }
