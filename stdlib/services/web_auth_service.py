"""Одноразовые ссылки для входа суперпользователя в веб-панель (Redis)."""

from __future__ import annotations

import secrets

from bot.config import config
from bot.logger import logger
from stdlib.redis_client import redis_client

_AUTH_PREFIX = "auth_token:"


def _token_key(token: str) -> str:
    return f"{_AUTH_PREFIX}{token}"


async def mint_login_token(user_id: int) -> str | None:
    """Создаёт одноразовый токен, TTL из конфига. Возвращает None, если Redis недоступен."""
    r = redis_client
    if r is None:
        logger.warning("web auth: Redis unavailable, cannot mint token")
        return None
    raw = secrets.token_urlsafe(32)
    ttl = max(60, int(config.WEB_AUTH_TOKEN_TTL_SECONDS))
    ok = await r.set(_token_key(raw), str(user_id), ex=ttl)
    if not ok:
        return None
    return raw


async def consume_login_token(token: str | None) -> int | None:
    """Забирает и удаляет токен (single-use). Возвращает user_id или None."""
    if not token or not str(token).strip():
        return None
    raw = str(token).strip()
    if len(raw) > 512:
        return None
    r = redis_client
    if r is None:
        return None
    key = _token_key(raw)
    try:
        uid_s = await r.getdel(key)
    except Exception:
        uid_s = await r.get(key)
        if uid_s:
            await r.delete(key)
    if not uid_s:
        return None
    try:
        return int(uid_s)
    except (TypeError, ValueError):
        return None
