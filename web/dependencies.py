from fastapi import Request, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
from web.auth_session import parse_admin_session
from bot.config import config

limiter = Limiter(key_func=get_remote_address, default_limits=[])


async def get_admin(request: Request) -> int:
    raw = request.cookies.get("admin_session")
    admin_id = parse_admin_session(raw)
    if admin_id is None or admin_id not in config.SUPERUSER_IDS:
        raise HTTPException(status_code=401)
    return admin_id
