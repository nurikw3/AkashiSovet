import html
from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi import FastAPI, Request, Form, Depends, HTTPException, Response
from pydantic import ValidationError
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from datetime import date, datetime
from aiogram import Bot
from urllib.parse import quote, urlencode
from bot.logger import logger
from passlib.context import CryptContext

import stdlib.db as db
import stdlib.keyboards as kb
from stdlib.pdf import get_app_pdf_buffer, generate_pdf_filename
from bot.config import config
import bcrypt

from stdlib import resources
from stdlib.models import Application
from stdlib.services import application_service, file_service, meeting_service
from stdlib.services.notification_service import (
    notify_user_application_approved,
    notify_user_application_rework,
)
from stdlib.template import ApplicationTemplate, get_template, persist_template
from aiogram.types import BufferedInputFile

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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
    await resources.init_resources()
    app.state.tg_bot = Bot(token=config.BOT_TOKEN)
    yield
    await resources.shutdown_resources()
    await app.state.tg_bot.session.close()


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="web/templates")
templates.env.filters["datetime"] = lambda v: (
    v.strftime("%d.%m.%Y %H:%M") if isinstance(v, datetime) else v
)
templates.env.filters["datefmt"] = lambda v: (
    v.strftime("%d.%m.%Y") if isinstance(v, date) else v
)


# --- AUTH HELPERS ---


async def get_admin(request: Request):
    admin_id = request.cookies.get("admin_session")
    if not admin_id or int(admin_id) not in config.SUPERUSER_IDS:
        raise HTTPException(status_code=401)
    return int(admin_id)


async def _get_hashed_password(user_id: int) -> str | None:
    async with db._pool_conn() as conn:
        row = await conn.fetchrow(
            "SELECT hashed_password FROM users WHERE user_id = $1", user_id
        )
    return row["hashed_password"] if row else None


@app.exception_handler(401)
async def auth_handler(request, exc):
    return RedirectResponse(url="/login")


# --- LOGIN / LOGOUT ---


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    admin_id = request.cookies.get("admin_session")
    if admin_id and int(admin_id) in config.SUPERUSER_IDS:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        request=request, name="login.html", context={"error": None}
    )


@app.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    tg_id: int = Form(...),
    code: str = Form(...),
):
    if tg_id not in config.SUPERUSER_IDS:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Пользователь не найден"},
        )

    hashed = await _get_hashed_password(tg_id)

    if hashed:
        if not bcrypt.checkpw(code.encode(), hashed.encode()):
            otp_ok = await db.verify_web_login_code(user_id=tg_id, input_code=code)
            if not otp_ok:
                return templates.TemplateResponse(
                    request=request,
                    name="login.html",
                    context={"error": "Неверный пароль или код"},
                )
    else:
        otp_ok = await db.verify_web_login_code(user_id=tg_id, input_code=code)
        if not otp_ok:
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={"error": "Неверный код. Получите новый через /web в боте"},
            )

    response = RedirectResponse(
        url="/settings" if not hashed else "/",
        status_code=302,
    )
    response.set_cookie(
        key="admin_session",
        value=str(tg_id),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 8,
    )
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("admin_session")
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
    logger.info(f"Password updated for admin {admin_id}")
    return HTMLResponse(
        '<p class="text-green-500 text-[10px] font-black text-center uppercase tracking-widest">'
        "✓ Password saved — use it on next login</p>"
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
    """Только удаление строки в форме (без записи в БД)."""
    return Response(status_code=204)


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
        {"s3_key": att.s3_key, "file_name": att.name} for att in m.attachments
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


@app.post("/meetings")
async def meetings_create(request: Request, admin_id=Depends(get_admin)):
    """Создаёт заседание и прикрепляет отмеченные согласованные заявки."""
    form = await request.form()
    raw_date = form.get("scheduled_date")
    if not raw_date or not str(raw_date).strip():
        return RedirectResponse(
            url=f"/?status=approved&meeting_err={quote('Укажите дату заседания')}",
            status_code=303,
        )
    try:
        scheduled = datetime.strptime(str(raw_date).strip(), "%Y-%m-%d").date()
    except ValueError:
        return RedirectResponse(
            url=f"/?status=approved&meeting_err={quote('Некорректная дата')}",
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
        await meeting_service.create_meeting_with_applications(
            scheduled, admin_id, app_ids
        )
    except ValueError as e:
        return RedirectResponse(
            url=f"/?status=approved&meeting_err={quote(str(e))}",
            status_code=303,
        )
    logger.info("meeting created by admin {} date {}", admin_id, scheduled)
    return RedirectResponse(url="/meetings?created=1", status_code=303)


@app.get("/meetings", response_class=HTMLResponse)
async def meetings_list(
    request: Request, admin_id=Depends(get_admin), created: str | None = None
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
        },
    )


@app.get("/meetings/{meeting_id}", response_class=HTMLResponse)
async def meeting_detail_page(
    request: Request, meeting_id: int, admin_id=Depends(get_admin)
):
    meeting = await meeting_service.get_by_id(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Заседание не найдено")
    raw_list = await db.get_applications_by_ids(meeting.application_ids)
    apps = [_parse_app(a) for a in raw_list]
    return templates.TemplateResponse(
        request=request,
        name="meeting_detail.html",
        context={"request": request, "meeting": meeting, "apps": apps},
    )


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
