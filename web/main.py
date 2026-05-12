from contextlib import asynccontextmanager
from pathlib import Path
import asyncio
import json

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, PlainTextResponse
from slowapi.errors import RateLimitExceeded
from aiogram import Bot

from bot.logger import logger
from bot.config import config
from stdlib import resources
from stdlib.services.realtime_events import (
    APPLICATION_EVENTS_CHANNEL,
    ApplicationChangedEvent,
    subscribe_application_events,
    unsubscribe_application_events,
)
from web.templating import templates
from web.dependencies import limiter
from prometheus_fastapi_instrumentator import Instrumentator
from web.realtime_ws import AdminWsHub


from web.routers import auth, settings, apps, meetings

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not (config.WEB_SESSION_SECRET or "").strip():
        logger.warning(
            "WEB_SESSION_SECRET is not set session cookies will not be signed"
        )
    await resources.init_resources()
    app.state.tg_bot = Bot(token=config.BOT_TOKEN)
    app.state.admin_ws_hub = AdminWsHub()

    stop_realtime_listener = asyncio.Event()

    async def _broadcast_application_event(event: ApplicationChangedEvent) -> None:
        await app.state.admin_ws_hub.broadcast_application_changed(event)

    async def _redis_realtime_listener() -> None:
        redis_client = resources.get_redis()
        if not redis_client:
            logger.warning("Realtime redis listener is disabled: redis is not available")
            return
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(APPLICATION_EVENTS_CHANNEL)
        logger.info("Realtime redis listener subscribed: {}", APPLICATION_EVENTS_CHANNEL)
        try:
            while not stop_realtime_listener.is_set():
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not message or message.get("type") != "message":
                    continue
                data = message.get("data")
                if not data:
                    continue
                try:
                    payload = json.loads(data)
                    event = ApplicationChangedEvent(
                        app_id=int(payload.get("app_id")),
                        status=payload.get("status"),
                        event_type=str(payload.get("event_type") or "updated"),
                        ts=str(payload.get("ts") or ""),
                    )
                    await _broadcast_application_event(event)
                except Exception as exc:
                    logger.warning("Invalid realtime event payload: {}", exc)
        finally:
            await pubsub.unsubscribe(APPLICATION_EVENTS_CHANNEL)
            await pubsub.close()

    subscribe_application_events(_broadcast_application_event)
    redis_listener_task = asyncio.create_task(_redis_realtime_listener())
    yield
    stop_realtime_listener.set()
    redis_listener_task.cancel()
    try:
        await redis_listener_task
    except asyncio.CancelledError:
        pass
    unsubscribe_application_events(_broadcast_application_event)
    await resources.shutdown_resources()
    await app.state.tg_bot.session.close()

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.state.limiter = limiter

Instrumentator().instrument(app).expose(app)

_static_dir = Path(__file__).resolve().parent / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(apps.router)
app.include_router(meetings.router)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_exc(request: Request, exc: RateLimitExceeded):
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" in accept or request.url.path == "/login":
        return templates.TemplateResponse(
            request=request, name="login.html", context={"error": "Слишком много попыток входа."}, status_code=429
        )
    return PlainTextResponse("Too Many Requests", status_code=429)

@app.exception_handler(401)
async def auth_handler(request, exc):
    return RedirectResponse(url="/login")

@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "accelerometer=(), camera=(), geolocation=(), microphone=()"
    return response