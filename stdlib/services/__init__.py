"""Сервисный слой: заявки, файлы, уведомления Telegram."""

from stdlib.services import application_service
from stdlib.services import file_service
from stdlib.services import meeting_service
from stdlib.services import notification_service

__all__ = [
    "application_service",
    "file_service",
    "meeting_service",
    "notification_service",
]
