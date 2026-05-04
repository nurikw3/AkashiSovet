"""Подписанная cookie админ-сессии (HMAC). Без секрета — только для разработки."""

from __future__ import annotations

import hashlib
import hmac

from bot.config import config
from bot.logger import logger


def sign_admin_session(user_id: int) -> str:
    secret = (config.WEB_SESSION_SECRET or "").strip()
    if not secret:
        return str(user_id)
    mac = hmac.new(
        secret.encode("utf-8"),
        str(user_id).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{user_id}.{mac}"


def parse_admin_session(raw: str | None) -> int | None:
    """Разбирает cookie; при WEB_SESSION_SECRET отвергает подделку."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None

    secret = (config.WEB_SESSION_SECRET or "").strip()
    if not secret:
        return int(s) if s.isdigit() else None

    if "." not in s:
        logger.warning("admin_session: отсутствует подпись при включённом WEB_SESSION_SECRET")
        return None

    uid_s, mac = s.split(".", 1)
    if not uid_s.isdigit() or len(mac) < 32:
        return None
    uid = int(uid_s)
    expected = hmac.new(
        secret.encode("utf-8"),
        str(uid).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, mac):
        logger.warning("admin_session: неверная подпись cookie")
        return None
    return uid
