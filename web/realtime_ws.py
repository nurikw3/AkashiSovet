from __future__ import annotations

import asyncio

from fastapi import WebSocket

from bot.logger import logger
from stdlib.services.realtime_events import ApplicationChangedEvent


class AdminWsHub:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)

    async def broadcast_application_changed(self, event: ApplicationChangedEvent) -> None:
        payload = {
            "type": "application_changed",
            "app_id": event.app_id,
            "status": event.status,
            "event_type": event.event_type,
            "ts": event.ts,
        }

        async with self._lock:
            targets = list(self._connections)

        stale: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception as exc:
                logger.debug("Dropping stale admin websocket: {}", exc)
                stale.append(ws)

        if stale:
            async with self._lock:
                for ws in stale:
                    self._connections.discard(ws)
