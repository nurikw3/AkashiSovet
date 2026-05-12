from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

from bot.logger import logger


@dataclass(slots=True)
class ApplicationChangedEvent:
    app_id: int
    status: str | None
    event_type: str
    ts: str


ApplicationEventCallback = Callable[[ApplicationChangedEvent], Awaitable[None]]
_application_subscribers: set[ApplicationEventCallback] = set()


def subscribe_application_events(callback: ApplicationEventCallback) -> None:
    _application_subscribers.add(callback)


def unsubscribe_application_events(callback: ApplicationEventCallback) -> None:
    _application_subscribers.discard(callback)


async def publish_application_changed(
    app_id: int,
    *,
    status: str | None,
    event_type: str,
) -> None:
    if not _application_subscribers:
        return

    event = ApplicationChangedEvent(
        app_id=app_id,
        status=status,
        event_type=event_type,
        ts=datetime.now(timezone.utc).isoformat(),
    )
    for callback in list(_application_subscribers):
        try:
            await callback(event)
        except Exception as exc:
            logger.warning("Application realtime callback failed: {}", exc)
