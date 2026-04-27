# stdlib/cache.py
from bot.logger import logger
import stdlib.redis_client as redis_module


async def get_cached_llm_response(prompt_hash: str) -> str | None:
    client = redis_module.redis_client
    logger.info(
        f"🔍 CACHE GET: client_type={type(client)}, key_prefix={prompt_hash[:8]}"
    )

    if not client:
        logger.error("❌ CACHE GET: client is None!")
        return None
    try:
        val = await client.get(f"llm:{prompt_hash}")
        logger.info(f"✅ CACHE GET: {'HIT' if val else 'MISS'}")
        return val
    except Exception as e:
        logger.error(f"❌ CACHE GET ERROR: {e}")
        return None


async def save_llm_response_to_cache(
    prompt_hash: str, response: str, ttl: int = 604800
) -> None:
    client = redis_module.redis_client
    logger.info(
        f"💾 CACHE SAVE: client_type={type(client)}, key_prefix={prompt_hash[:8]}, response_len={len(response)}"
    )

    if not client:
        logger.error(
            "❌ CACHE SAVE: client is None! Module attrs: "
            + str([a for a in dir(redis_module) if not a.startswith("_")])
        )
        return
    try:
        logger.info("🚀 Executing Redis SETEX...")
        await client.setex(f"llm:{prompt_hash}", ttl, response)
        logger.info("✅ Redis SETEX SUCCESS")
    except Exception as e:
        logger.error(f"❌ CACHE SAVE ERROR: {e}")
        import traceback

        logger.error(f"📋 TRACEBACK: {traceback.format_exc()}")
