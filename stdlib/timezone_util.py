"""Единый часовой пояс приложения: Казахстан (Астана / единое время РК), IANA `Asia/Almaty` (UTC+5).

Моменты времени в PostgreSQL хранятся как UTC (`TIMESTAMPTZ`); для UI, PDF и имён файлов
используется этот пояс.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

APP_TIMEZONE = ZoneInfo("Asia/Almaty")


def now_app() -> datetime:
    """Текущие дата и время в часовом поясе приложения."""
    return datetime.now(APP_TIMEZONE)


def ensure_app_tz(dt: datetime) -> datetime:
    """Приводит `datetime` к `APP_TIMEZONE` (для вывода пользователю)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).astimezone(APP_TIMEZONE)
    return dt.astimezone(APP_TIMEZONE)


def wall_time_astana_to_utc(naive_or_aware: datetime) -> datetime:
    """Локальное «настенное» время из форм (интерпретируем как Астану) → UTC для БД."""
    if naive_or_aware.tzinfo is not None:
        return naive_or_aware.astimezone(timezone.utc)
    return naive_or_aware.replace(tzinfo=APP_TIMEZONE).astimezone(timezone.utc)


def format_app_datetime(dt: datetime | None, fmt: str = "%d.%m.%Y %H:%M") -> str:
    if dt is None:
        return ""
    return ensure_app_tz(dt).strftime(fmt)


def format_app_date_only(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return ensure_app_tz(dt).strftime("%d.%m.%Y")
