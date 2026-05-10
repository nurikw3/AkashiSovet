from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, PlainTextResponse
from slowapi.errors import RateLimitExceeded
from aiogram import Bot

from bot.logger import logger
from bot.config import config
from stdlib import resources
from web.templating import templates
from web.dependencies import limiter


from web.routers import auth, settings, apps, meetings

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not (config.WEB_SESSION_SECRET or "").strip():
        logger.warning(
            "WEB_SESSION_SECRET is not set session cookies will not be signed"
        )
    await resources.init_resources()
    app.state.tg_bot = Bot(token=config.BOT_TOKEN)
    yield
    await resources.shutdown_resources()
    await app.state.tg_bot.session.close()

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.state.limiter = limiter

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