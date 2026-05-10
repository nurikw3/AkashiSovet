from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import bcrypt
import stdlib.db as db
from web.templating import templates
from web.dependencies import limiter, get_admin
from web.auth_session import parse_admin_session, sign_admin_session
from bot.config import config

router = APIRouter()
_LOGIN_FAIL_MSG = "Неверный Telegram ID или код"

async def _get_hashed_password(user_id: int) -> str | None:
    async with db._pool_conn() as conn:
        row = await conn.fetchrow(
            "SELECT hashed_password FROM users WHERE user_id = $1", user_id
        )
    return row["hashed_password"] if row else None

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    uid = parse_admin_session(request.cookies.get("admin_session"))
    if uid is not None and uid in config.SUPERUSER_IDS:
        return RedirectResponse(url="/", status_code=302)
    err = request.query_params.get("error")
    return templates.TemplateResponse(
        request=request, name="login.html", context={"error": err}
    )

@router.post("/login", response_class=HTMLResponse)
@limiter.limit(config.WEB_LOGIN_RATE_LIMIT)
async def login_post(
    request: Request,
    tg_id: int = Form(...),
    code: str = Form(...),
):
    err_html = templates.TemplateResponse(
        request=request, name="login.html", context={"error": _LOGIN_FAIL_MSG},
    )

    if tg_id not in config.SUPERUSER_IDS:
        return err_html

    hashed = await _get_hashed_password(tg_id)
    ok = False
    if hashed:
        if bcrypt.checkpw(code.encode(), hashed.encode()):
            ok = True
        else:
            ok = await db.verify_web_login_code(user_id=tg_id, input_code=code)
    else:
        ok = await db.verify_web_login_code(user_id=tg_id, input_code=code)

    if not ok:
        return err_html

    response = RedirectResponse(
        url="/settings" if not hashed else "/",
        status_code=302,
    )
    response.set_cookie(
        key="admin_session",
        value=sign_admin_session(tg_id),
        httponly=True,
        samesite="lax",
        secure=config.WEB_COOKIE_SECURE,
        max_age=config.ADMIN_SESSION_MAX_AGE_SECONDS,
        path="/",
    )
    return response

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(
        "admin_session",
        path="/",
        httponly=True,
        samesite="lax",
        secure=config.WEB_COOKIE_SECURE,
    )
    return response