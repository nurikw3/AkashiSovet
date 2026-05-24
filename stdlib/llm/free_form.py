"""
Free-form диалог для сбора данных заявки.
"""

import json

from bot.config import config
from bot.logger import logger
from stdlib.llm.client import langfuse, openai_client
from stdlib.llm.prompts import build_free_form_system, build_free_form_tools
from stdlib.schemas import (
    AskUser,
    LLMComplete,
    LLMError,
    LLMIncomplete,
    LLMResponse,
    build_submit_memo_model,
    strip_submit_memo_args,
)
from stdlib.template import get_template


async def process_free_form_chat(
    history: list,
    app_id: int | None = None,
    user_id: int | None = None,
) -> LLMResponse:
    tpl = await get_template()
    submit_model = build_submit_memo_model(tpl)
    system = build_free_form_system(tpl)
    tools = build_free_form_tools(submit_model)
    messages = [{"role": "system", "content": system}] + history

    async def _call() -> LLMResponse:
        response = await openai_client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=messages,
            tools=tools,
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
            return LLMIncomplete(
                status="incomplete",
                reply=msg.content or "Пожалуйста, уточните детали.",
            )

        tc = msg.tool_calls[0]
        args = json.loads(tc.function.arguments)
        logger.info("Free-form tool='{}' app_id={}", tc.function.name, app_id)

        if tc.function.name == "ask_user":
            return LLMIncomplete(
                status="incomplete",
                reply=AskUser.model_validate(args).question,
            )

        if tc.function.name == "submit_memo":
            clean = strip_submit_memo_args(args, tpl)
            blocks_dict = submit_model.model_validate(clean).model_dump(by_alias=True)
            return LLMComplete(status="complete", blocks=blocks_dict)

        return LLMIncomplete(status="incomplete", reply="Пожалуйста, уточните детали.")

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
            status="error",
            reply="Произошла ошибка при анализе текста. Пожалуйста, попробуйте ещё раз.",
        )
