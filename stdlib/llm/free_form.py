"""
Free-form диалог для сбора данных заявки.
"""

import json

from bot.config import config
from bot.logger import logger
from stdlib.llm.client import langfuse, openai_client
from stdlib.llm.prompts import FREE_FORM_SYSTEM, FREE_FORM_TOOLS
from stdlib.schemas import (
    AskUser,
    LLMComplete,
    LLMError,
    LLMIncomplete,
    LLMResponse,
    SubmitMemo,
)


async def process_free_form_chat(
    history: list,
    app_id: int | None = None,
    user_id: int | None = None,
) -> LLMResponse:
    messages = [{"role": "system", "content": FREE_FORM_SYSTEM}] + history

    async def _call() -> LLMResponse:
        response = await openai_client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=messages,
            tools=FREE_FORM_TOOLS,
            tool_choice="required",
            temperature=0.2,
            max_tokens=800,
        )
        msg = response.choices[0].message

        if langfuse:
            try:
                langfuse.update_current_generation(
                    output=msg.content or "Tool Call",
                    usage_details={
                        "input": getattr(response.usage, "prompt_tokens", 0),
                        "output": getattr(response.usage, "completion_tokens", 0),
                        "total": getattr(response.usage, "total_tokens", 0),
                    },
                )
            except Exception as e:
                logger.warning("Langfuse usage update failed: {}", e)

        if not msg.tool_calls:
            return LLMIncomplete(reply=msg.content or "Пожалуйста, уточните детали.")

        tc = msg.tool_calls[0]
        args = json.loads(tc.function.arguments)
        logger.info("Free-form tool='{}' app_id={}", tc.function.name, app_id)

        if tc.function.name == "ask_user":
            return LLMIncomplete(reply=AskUser.model_validate(args).question)

        if tc.function.name == "submit_memo":
            return LLMComplete(blocks=SubmitMemo.model_validate(args).to_memo_blocks())

        return LLMIncomplete(reply="Пожалуйста, уточните детали.")

    try:
        if langfuse:
            from langfuse import propagate_attributes

            with propagate_attributes(user_id=str(user_id) if user_id else None):
                with langfuse.start_as_current_observation(
                    name="free-form-chat",
                    as_type="generation",
                    input=messages,
                    model=config.OPENAI_MODEL,
                    metadata={"app_id": app_id},
                ):
                    return await _call()
        return await _call()
    except Exception as e:
        logger.error("Free-form LLM failed: {}", e)
        return LLMError(
            reply="Произошла ошибка при анализе текста. Пожалуйста, попробуйте ещё раз."
        )
