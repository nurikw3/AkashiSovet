# stdlib/redis_client.py
import redis.asyncio as redis
from bot.config import config
from bot.logger import logger

redis_client: redis.Redis | None = None


async def init_redis():
    global redis_client
    if not hasattr(config, "REDIS_URL") or not config.REDIS_URL:
        logger.warning("Redis URL not found in config. Caching disabled.")
        return

    try:
        redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)
        await redis_client.ping()
        logger.info("Redis connected successfully")
    except Exception as e:
        logger.error("Failed to connect to Redis: {}", e)
        redis_client = None


async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.close()
