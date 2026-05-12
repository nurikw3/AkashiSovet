from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

from bot.logger import logger
from stdlib import resources


@dataclass(slots=True)
class ApplicationChangedEvent:
    app_id: int
    status: str | None
    event_type: str
    ts: str


ApplicationEventCallback = Callable[[ApplicationChangedEvent], Awaitable[None]]
_application_subscribers: set[ApplicationEventCallback] = set()
APPLICATION_EVENTS_CHANNEL = "events:applications"


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
    event = ApplicationChangedEvent(
        app_id=app_id,
        status=status,
        event_type=event_type,
        ts=datetime.now(timezone.utc).isoformat(),
    )
    payload = json.dumps(
        {
            "type": "application_changed",
            "app_id": event.app_id,
            "status": event.status,
            "event_type": event.event_type,
            "ts": event.ts,
        },
        ensure_ascii=False,
    )

    redis_client = resources.get_redis()
    published_to_redis = False
    if redis_client:
        try:
            await redis_client.publish(APPLICATION_EVENTS_CHANNEL, payload)
            published_to_redis = True
        except Exception as exc:
            logger.warning("Failed to publish application event to redis: {}", exc)

    if published_to_redis or not _application_subscribers:
        return

    for callback in list(_application_subscribers):
        try:
            await callback(event)
        except Exception as exc:
            logger.warning("Application realtime callback failed: {}", exc)
