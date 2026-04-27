"""
OpenAI клиент и Langfuse инициализация.
"""

from openai import AsyncOpenAI
from bot.config import config
from bot.logger import logger

openai_client = AsyncOpenAI(
    api_key=config.OPENAI_API_KEY,
    base_url=config.OPENAI_BASE_URL,
)

langfuse = None
if config.langfuse_enabled:
    try:
        from langfuse import Langfuse

        langfuse = Langfuse(
            public_key=config.LANGFUSE_PUBLIC_KEY,
            secret_key=config.LANGFUSE_SECRET_KEY,
            host=config.LANGFUSE_BASE_URL,
        )
        logger.info("Langfuse трейсинг включён (host={})", config.LANGFUSE_BASE_URL)
    except Exception as e:
        logger.warning("Langfuse недоступен, трейсинг отключён: {}", e)
