import html
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Request, Form, Depends, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from fastapi.templating import Jinja2Templates
from fastapi.responses import (
    HTMLResponse,
    StreamingResponse,
    RedirectResponse,
    PlainTextResponse,
)
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from datetime import date, datetime, time
from aiogram import Bot
from io import BytesIO
from urllib.parse import quote, urlencode
from bot.logger import logger
import bcrypt
import stdlib.db as db
import stdlib.keyboards as kb
from stdlib.pdf import get_app_pdf_buffer, generate_pdf_filename
from bot.config import config
from stdlib import resources
import stdlib.s3 as s3_keys
from web.auth_session import parse_admin_session, sign_admin_session
from stdlib.models import Application
from stdlib.services import application_service, file_service, meeting_service
from stdlib.services.notification_service import (
    notify_user_application_approved,
    notify_user_application_rework,
)
from stdlib.template import ApplicationTemplate, get_template, persist_template
from aiogram.types import BufferedInputFile

_LOGIN_FAIL_MSG = "Неверный Telegram ID или код"

limiter = Limiter(key_func=get_remote_address, default_limits=[])


def _template_validation_message(e: ValidationError) -> str:
    parts: list[str] = []
    for err in e.errors():
        m = err.get("msg") or "ошибка валидации"
        if m.startswith("Value error, "):
            m = m[len("Value error, ") :]
        loc = err.get("loc") or ()
        if len(loc) >= 2 and loc[0] == "blocks" and isinstance(loc[1], int):
            parts.append(f"Блок {loc[1] + 1}: {m}")
        else:
            parts.append(m)
    return "; ".join(parts) if parts else str(e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not (config.WEB_SESSION_SECRET or "").strip():
        logger.warning(
            "WEB_SESSION_SECRET не задан — cookie сессии без подписи (только для разработки). "
            "В продакшене сгенерируйте секрет и задайте WEB_COOKIE_SECURE=true за HTTPS."
        )
    await resources.init_resources()
    app.state.tg_bot = Bot(token=config.BOT_TOKEN)
    yield
    await resources.shutdown_resources()
    await app.state.tg_bot.session.close()


app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter

_static_dir = Path(__file__).resolve().parent / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

templates = Jinja2Templates(directory="web/templates")
templates.env.filters["datetime"] = lambda v: (
    v.strftime("%d.%m.%Y %H:%M") if isinstance(v, datetime) else v
)
templates.env.filters["datefmt"] = lambda v: (
    v.strftime("%d.%m.%Y") if isinstance(v, (date, datetime)) else v
)
templates.env.filters["urlquote"] = lambda v: quote(str(v or ""), safe="")


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_exc(request: Request, exc: RateLimitExceeded):
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" in accept or request.url.path == "/login":
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Слишком много попыток входа. Подождите немного."},
            status_code=429,
        )
    return PlainTextResponse("Too Many Requests", status_code=429)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "accelerometer=(), camera=(), geolocation=(), microphone=()"
    )
    return response


# --- AUTH HELPERS ---


async def _get_hashed_password(user_id: int) -> str | None:
    async with db._pool_conn() as conn:
        row = await conn.fetchrow(
            "SELECT hashed_password FROM users WHERE user_id = $1", user_id
        )
    return row["hashed_password"] if row else None


async def get_admin(request: Request):
    raw = request.cookies.get("admin_session")
    admin_id = parse_admin_session(raw)
    if admin_id is None or admin_id not in config.SUPERUSER_IDS:
        raise HTTPException(status_code=401)
    return admin_id


@app.exception_handler(401)
async def auth_handler(request, exc):
    return RedirectResponse(url="/login")


# --- LOGIN / LOGOUT ---


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    uid = parse_admin_session(request.cookies.get("admin_session"))
    if uid is not None and uid in config.SUPERUSER_IDS:
        return RedirectResponse(url="/", status_code=302)
    err = request.query_params.get("error")
    return templates.TemplateResponse(
        request=request, name="login.html", context={"error": err}
    )


@app.post("/login", response_class=HTMLResponse)
@limiter.limit(config.WEB_LOGIN_RATE_LIMIT)
async def login_post(
    request: Request,
    tg_id: int = Form(...),
    code: str = Form(...),
):
    err_html = templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": _LOGIN_FAIL_MSG},
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


@app.get("/logout")
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


# --- SETTINGS ---


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, admin_id=Depends(get_admin)):
    hashed = await _get_hashed_password(admin_id)
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "has_password": bool(hashed),
            "success": request.query_params.get("success"),
            "error": None,
        },
    )


@app.post("/settings/password", response_class=HTMLResponse)
async def set_password(
    request: Request,
    password: str = Form(...),
    admin_id=Depends(get_admin),
):
    if len(password) < 8:
        return HTMLResponse(
            '<p class="text-akashi-red text-[10px] font-black text-center uppercase tracking-widest">'
            "⚠ Минимум 8 символов</p>"
        )

    await db.update_user_password(admin_id, password)
    logger.info("Password updated for admin {}", admin_id)
    return HTMLResponse(
        '<p class="text-green-500 text-[10px] font-black text-center uppercase tracking-widest">'
        "✓ Пароль сохранён — используйте его при следующем входе</p>"
    )


# --- Шаблон заявки (БД + Redis) ---


@app.get("/settings/template", response_class=HTMLResponse)
async def template_editor_page(request: Request, admin_id=Depends(get_admin)):
    try:
        tpl = await get_template()
    except RuntimeError as e:
        return templates.TemplateResponse(
            request=request,
            name="template_editor_error.html",
            context={"message": str(e)},
        )
    return templates.TemplateResponse(
        request=request,
        name="template_editor.html",
        context={"blocks": tpl.blocks},
    )


@app.get("/settings/template/new-row", response_class=HTMLResponse)
async def template_editor_new_row(
    request: Request, next_id: int, admin_id=Depends(get_admin)
):
    block = SimpleNamespace(
        id=next_id,
        title="",
        question="",
        description_for_llm=None,
    )
    return templates.TemplateResponse(
        request=request,
        name="template_block_row.html",
        context={"block": block},
    )


@app.delete("/settings/template/ui-row")
async def template_editor_row_delete_ui(admin_id=Depends(get_admin)):
    """Только удаление строки в форме (без записи в БД).

    HTMX по умолчанию не делает swap при 204; для очистки цели нужен 200 и пустое тело.
    """
    return Response(status_code=200, content="")


@app.post("/settings/template/save", response_class=HTMLResponse)
async def template_editor_save(
    admin_id=Depends(get_admin),
    block_id: list[str] = Form(...),
    block_title: list[str] = Form(...),
    block_question: list[str] = Form(...),
    block_desc: list[str] | None = Form(None),
):
    n = len(block_id)
    if n == 0:
        return HTMLResponse(
            '<p class="text-akashi-red text-[10px] font-black">Нужен хотя бы один блок</p>',
            status_code=400,
        )
    if len(block_title) != n or len(block_question) != n:
        return HTMLResponse(
            '<p class="text-akashi-red text-[10px] font-black">Несогласованные поля формы</p>',
            status_code=400,
        )
    desc_list = block_desc or []
    while len(desc_list) < n:
        desc_list.append("")

    rows: list[dict] = []
    for i in range(n):
        d = (desc_list[i] or "").strip()
        try:
            bid = int(block_id[i])
        except ValueError:
            return HTMLResponse(
                '<p class="text-akashi-red text-[10px] font-black">Некорректный ID блока</p>',
                status_code=400,
            )
        if bid <= 0:
            return HTMLResponse(
                '<p class="text-akashi-red text-[10px] font-black">'
                "ID блока должен быть положительным числом</p>",
                status_code=400,
            )
        rows.append(
            {
                "id": bid,
                "title": (block_title[i] or "").strip(),
                "question": (block_question[i] or "").strip(),
                "description_for_llm": d or None,
            }
        )

    try:
        app_tpl = ApplicationTemplate.model_validate({"blocks": rows})
    except ValidationError as e:
        msg = _template_validation_message(e)
        return HTMLResponse(
            f'<p class="text-akashi-red text-[10px] font-black">'
            f"{html.escape(msg)}</p>",
            status_code=400,
        )

    try:
        await persist_template(app_tpl)
    except Exception as e:
        logger.exception("template save failed")
        return HTMLResponse(
            f'<p class="text-akashi-red text-[10px] font-black">Ошибка БД: {e}</p>',
            status_code=500,
        )

    logger.info("app_template updated by admin {}", admin_id)
    return HTMLResponse(
        '<p class="text-green-500 text-[10px] font-black">✓ Шаблон сохранён, кэш Redis сброшен</p>'
    )


# --- DASHBOARD ---


@app.get("/partials/counters", response_class=HTMLResponse)
async def dashboard_counters_partial(request: Request, admin_id=Depends(get_admin)):
    """Фрагмент HTMX: виджеты счётчиков (обновление без перезагрузки)."""
    counts = await application_service.get_status_counts()
    return templates.TemplateResponse(
        request=request,
        name="dashboard_counters.html",
        context={"request": request, "counts": counts},
    )


@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    status: str | None = None,
    admin_id=Depends(get_admin),
):
    # Старые ссылки ?tab=active&status=… / ?tab=archive → без tab
    if "tab" in request.query_params:
        tab_val = request.query_params.get("tab")
        st = request.query_params.get("status")
        q: dict[str, str] = {}
        if st in ("draft", "pending", "rework", "approved"):
            q["status"] = st
        elif tab_val == "archive":
            q["status"] = "approved"
        me = request.query_params.get("meeting_err")
        if me:
            q["meeting_err"] = me
        dest = "/" + ("?" + urlencode(q) if q else "")
        return RedirectResponse(url=dest, status_code=302)

    status_filter = (
        status if status in ("draft", "pending", "rework", "approved") else None
    )
    raw_apps = await application_service.list_applications(status_filter)
    parsed_apps = [_parse_app(a) for a in raw_apps]
    counts = await application_service.get_status_counts()
    meeting_basket = status_filter == "approved"
    ctx = {
        "request": request,
        "apps": parsed_apps,
        "status_filter": status_filter,
        "counts": counts,
        "meeting_basket": meeting_basket,
    }
    tpl = "dashboard_apps.html" if "hx-request" in request.headers else "index.html"
    return templates.TemplateResponse(request=request, name=tpl, context=ctx)


@app.post("/approve/{app_id}")
async def approve_app(request: Request, app_id: int, admin_id=Depends(get_admin)):
    row = await application_service.approve(app_id)
    if row and row.user_id:
        await notify_user_application_approved(
            request.app.state.tg_bot,
            row.user_id,
            app_id,
            pdf_file_id=None,
        )

    return await _render_row(request, app_id)


@app.post("/reject/{app_id}")
async def reject_app(
    request: Request,
    app_id: int,
    feedback: str = Form(...),
    admin_id=Depends(get_admin),
):
    row = await application_service.send_for_rework(app_id, feedback)
    if row:
        tpl = await get_template()
        await notify_user_application_rework(
            request.app.state.tg_bot,
            row.user_id,
            app_id,
            feedback,
            reply_markup=kb.rework_keyboard(tpl),
            web_wording=True,
        )

    return await _render_row(request, app_id)


@app.get("/download_tg_attachment")
async def download_tg_attachment(
    request: Request,
    file_id: str,
    name: str | None = None,
    admin_id=Depends(get_admin),
):
    """Скачивание файла по Telegram file_id (вложения, загруженные в боте до S3)."""
    if not file_id or not file_id.strip():
        raise HTTPException(status_code=400, detail="Пустой file_id")
    bot: Bot = request.app.state.tg_bot
    try:
        tg_file = await bot.get_file(file_id.strip())
    except Exception as e:
        logger.warning("Telegram get_file failed | file_id prefix={} err={}", file_id[:16], e)
        raise HTTPException(
            status_code=404,
            detail="Файл недоступен (истёк срок хранения в Telegram или неверный идентификатор).",
        ) from e
    if not tg_file.file_path:
        raise HTTPException(status_code=404, detail="Нет пути к файлу в Telegram")
    buf = BytesIO()
    await bot.download_file(tg_file.file_path, destination=buf)
    buf.seek(0)
    fname = (name or "attachment").strip() or "attachment"
    headers = {"Content-Disposition": f"attachment; filename*=utf-8''{quote(fname)}"}
    return StreamingResponse(
        buf, media_type="application/octet-stream", headers=headers
    )


@app.get("/download/{app_id}")
async def download_report(app_id: int, admin_id=Depends(get_admin)):
    app_row = await application_service.get_application(app_id)
    if not app_row:
        raise HTTPException(status_code=404)

    pdf_buf = await get_app_pdf_buffer(app_id)
    u_id = app_row.user_id
    full_name = await db.get_user_full_name(u_id)
    position = await db.get_user_position(u_id)
    custom_filename = generate_pdf_filename(full_name, position, app_row.created_at)

    headers = {
        "Content-Disposition": f"inline; filename*=utf-8''{quote(custom_filename)}"
    }
    return StreamingResponse(pdf_buf, media_type="application/pdf", headers=headers)


@app.get("/download_attachment/{s3_key:path}")
async def download_file(s3_key: str, admin_id=Depends(get_admin)):
    # 1. Валидация ключа
    if not s3_key or s3_key.strip() == "":
        raise HTTPException(status_code=400, detail="Пустой S3-ключ")
    if not s3_keys.is_allowed_attachment_download_key(s3_key.strip()):
        logger.warning(
            "Rejected attachment download key | admin={} key_prefix={}",
            admin_id,
            s3_key[:80],
        )
        raise HTTPException(status_code=400, detail="Недопустимый ключ объекта")

    buf = await file_service.download_attachment_bytesio(s3_key)
    if not buf:
        logger.error("File not found in S3: key={}", s3_key)
        raise HTTPException(status_code=404, detail="Файл не найден в хранилище")

    # 3. Определяем имя файла
    filename = s3_key.split("/")[-1]

    # 4. Отдаём с правильными заголовками
    headers = {"Content-Disposition": f"attachment; filename*=utf-8''{quote(filename)}"}
    return StreamingResponse(
        buf, media_type="application/octet-stream", headers=headers
    )


# --- Internal ---


def _parse_app(a: dict) -> dict:
    m = Application.model_validate(a)
    parsed = [
        {
            "s3_key": att.s3_key,
            "file_id": att.file_id,
            "file_name": att.name,
        }
        for att in m.attachments
    ]
    out = {**a}
    out["topic"] = m.blocks.get("1", "Без темы")
    out["display_name"] = m.full_name or m.username or f"ID: {m.user_id}"
    out["parsed_attachments"] = parsed
    return out


async def _render_row(request, app_id):
    app = await application_service.get_application(app_id)
    if not app:
        raise HTTPException(status_code=404)
    row = app.model_dump()
    row["full_name"] = await db.get_user_full_name(app.user_id)
    return templates.TemplateResponse(
        request=request,
        name="row.html",
        context={
            "request": request,
            "app": _parse_app(row),
            "meeting_basket": False,
        },
    )


# --- MEETINGS ---


def _meeting_form_err_prefix(form) -> str:
    """Куда редиректить ошибку валидации: страница списка заседаний или дашборд approved."""
    if (form.get("meeting_form_source") or "").strip() == "meetings":
        return "/meetings?meeting_err="
    return "/?status=approved&meeting_err="


def _parse_meeting_schedule(form) -> datetime | None:
    """Парсит `scheduled_at` (datetime-local) или устаревшее поле даты (10:00)."""
    raw_at = form.get("scheduled_at")
    if raw_at and str(raw_at).strip():
        s = str(raw_at).strip()
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
    raw_date = form.get("scheduled_date")
    if raw_date and str(raw_date).strip():
        try:
            d = datetime.strptime(str(raw_date).strip(), "%Y-%m-%d").date()
            return datetime.combine(d, time(10, 0))
        except ValueError:
            pass
    return None


@app.post("/meetings")
async def meetings_create(request: Request, admin_id=Depends(get_admin)):
    """Создаёт заседание и прикрепляет отмеченные согласованные заявки."""
    form = await request.form()
    err_base = _meeting_form_err_prefix(form)
    scheduled = _parse_meeting_schedule(form)
    if not scheduled:
        return RedirectResponse(
            url=f"{err_base}{quote('Укажите дату и время заседания')}",
            status_code=303,
        )
    raw_ids = form.getlist("app_id")
    app_ids: list[int] = []
    for x in raw_ids:
        try:
            app_ids.append(int(x))
        except (TypeError, ValueError):
            continue
    try:
        if not app_ids:
            await meeting_service.create_meeting(scheduled, admin_id)
        else:
            await meeting_service.create_meeting_with_applications(
                scheduled, admin_id, app_ids
            )
    except ValueError as e:
        return RedirectResponse(
            url=f"{err_base}{quote(str(e))}",
            status_code=303,
        )
    except Exception as e:
        logger.exception("meetings_create failed")
        return RedirectResponse(
            url=f"/meetings?meeting_err={quote(str(e))}",
            status_code=303,
        )
    logger.info("meeting created by admin {} at {}", admin_id, scheduled)
    return RedirectResponse(url="/meetings?created=1", status_code=303)


@app.get("/meetings", response_class=HTMLResponse)
async def meetings_list(
    request: Request,
    admin_id=Depends(get_admin),
    created: str | None = None,
    deleted: str | None = None,
):
    upcoming = await meeting_service.get_upcoming()
    past = await meeting_service.get_past()
    return templates.TemplateResponse(
        request=request,
        name="meetings_list.html",
        context={
            "request": request,
            "upcoming": upcoming,
            "past": past,
            "created_ok": created == "1",
            "deleted_ok": deleted == "1",
            "meeting_err": request.query_params.get("meeting_err"),
        },
    )


@app.get("/meetings/{meeting_id}", response_class=HTMLResponse)
async def meeting_detail_page(
    request: Request,
    meeting_id: int,
    admin_id=Depends(get_admin),
    updated: str | None = None,
):
    meeting = await meeting_service.get_by_id(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Заседание не найдено")
    raw_list = await db.get_applications_by_ids(meeting.application_ids)
    apps = [_parse_app(a) for a in raw_list]
    return templates.TemplateResponse(
        request=request,
        name="meeting_detail.html",
        context={
            "request": request,
            "meeting": meeting,
            "apps": apps,
            "schedule_updated_ok": updated == "1",
            "schedule_err": request.query_params.get("schedule_err"),
        },
    )


@app.post("/meetings/{meeting_id}/schedule")
async def meeting_update_schedule(
    request: Request, meeting_id: int, admin_id=Depends(get_admin)
):
    """Меняет дату и время заседания (форма из карточки заседания)."""
    form = await request.form()
    scheduled = _parse_meeting_schedule(form)
    if not scheduled:
        return RedirectResponse(
            url=f"/meetings/{meeting_id}?schedule_err={quote('Укажите дату и время')}",
            status_code=303,
        )
    ok = await meeting_service.set_scheduled_at(meeting_id, scheduled)
    if not ok:
        raise HTTPException(status_code=404, detail="Заседание не найдено")
    logger.info("meeting {} rescheduled by admin {} to {}", meeting_id, admin_id, scheduled)
    return RedirectResponse(url=f"/meetings/{meeting_id}?updated=1", status_code=303)


@app.post("/meetings/{meeting_id}/delete")
async def meeting_delete(meeting_id: int, admin_id=Depends(get_admin)):
    """Удаление заседания (только суперпользователь)."""
    deleted = await meeting_service.delete_meeting(meeting_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Заседание не найдено")
    logger.info("meeting {} deleted by admin {}", meeting_id, admin_id)
    return RedirectResponse(url="/meetings?deleted=1", status_code=303)


@app.get("/applications/{app_id}", response_class=HTMLResponse)
async def application_detail_page(
    request: Request, app_id: int, admin_id=Depends(get_admin)
):
    app = await application_service.get_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    row = app.model_dump()
    row["full_name"] = await db.get_user_full_name(app.user_id)
    return templates.TemplateResponse(
        request=request,
        name="application_detail.html",
        context={"request": request, "app": _parse_app(row)},
    )
