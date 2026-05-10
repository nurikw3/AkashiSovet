import time
import functools
from bot.logger import logger

def timed_task(name: str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.monotonic()
            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.monotonic() - start) * 1000
                logger.info(
                    "[task:ok] name={} duration={:.0f}ms",
                    name, duration_ms
                )
                return result
            except Exception as e:
                duration_ms = (time.monotonic() - start) * 1000
                logger.warning(
                    "[task:err] name={} duration={:.0f}ms err={}",
                    name, duration_ms, e
                )
                raise
        return wrapper
    return decorator