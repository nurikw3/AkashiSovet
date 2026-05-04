# stdlib/cache.py
from bot.logger import logger
from stdlib.resources import get_redis


async def get_cached_llm_response(prompt_hash: str) -> str | None:
    client = get_redis()
    if not client:
        logger.warning("LLM cache GET skipped: Redis unavailable")
        return None
    try:
        return await client.get(f"llm:{prompt_hash}")
    except Exception as e:
        logger.error("LLM cache GET error: {}", e)
        return None


async def save_llm_response_to_cache(
    prompt_hash: str, response: str, ttl: int = 604800
) -> None:
    client = get_redis()
    if not client:
        logger.warning("LLM cache SAVE skipped: Redis unavailable")
        return
    try:
        await client.setex(f"llm:{prompt_hash}", ttl, response)
    except Exception as e:
        logger.error("LLM cache SAVE error: {}", e)
        import traceback

        logger.error("Traceback: {}", traceback.format_exc())
