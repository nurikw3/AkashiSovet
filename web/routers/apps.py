import asyncio
import zipfile
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import (
    APIRouter,
    Request,
    Form,
    File,
    UploadFile,
    Depends,
    HTTPException,
    BackgroundTasks,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse, Response
from aiogram import Bot

import stdlib.db as db
import stdlib.keyboards as kb
import stdlib.s3 as s3_keys
from stdlib.models import Application
from stdlib.template import get_template
from stdlib.services import application_service, file_service
from stdlib.services.notification_service import (
    notify_user_application_approved,
    notify_user_application_rework,
)
from stdlib.document import (
    get_app_docx_buffer,
    media_type_for_filename,
    resolve_application_docx_filename,
)

get_app_pdf_buffer = get_app_docx_buffer
resolve_application_pdf_filename = resolve_application_docx_filename
from bot.config import config
from bot.logger import logger
from web.auth_session import parse_admin_session
from web.realtime_ws import AdminWsHub
from web.templating import templates
from web.dependencies import get_admin

router = APIRouter(tags=["applications"])
MAX_FEEDBACK_FILE_BYTES = 20 * 1024 * 1024
MAX_FEEDBACK_FILES_TOTAL_BYTES = 50 * 1024 * 1024


def _telegram_dm_url(user_id: int, username: str | None) -> str:
    if username:
        return f"https://t.me/{username.lstrip('@')}"
    return f"tg://user?id={user_id}"


def _parse_app(a: dict) -> dict:
    m = Application.model_validate(a)
    parsed = [
        {"s3_key": att.s3_key, "file_id": att.file_id, "file_name": att.name}
        for att in m.attachments
    ]
    out = {**a}
    out["topic"] = m.blocks.get("1", "Без темы")
    out["display_name"] = m.full_name or m.username or f"ID: {m.user_id}"
    out["telegram_url"] = _telegram_dm_url(m.user_id, m.username)
    out["parsed_attachments"] = parsed
    return out


async def _render_row(request: Request, app_id: int, *, meeting_basket: bool = False):
    app = await application_service.get_application(app_id)
    if not app:
        logger.warning("Failed to render row: application {} not found", app_id)
        raise HTTPException(status_code=404)
    row = app.model_dump()
    row["full_name"] = await db.get_user_full_name(app.user_id)
    return templates.TemplateResponse(
        request=request,
        name="row.html",
        context={
            "request": request,
            "app": _parse_app(row),
            "meeting_basket": meeting_basket,
        },
    )


async def _read_feedback_files(
    uploads: list[UploadFile] | None,
) -> list[tuple[str, bytes]]:
    if not uploads:
        return []

    out: list[tuple[str, bytes]] = []
    total_bytes = 0
    for upload in uploads:
        if not upload or not upload.filename:
            continue
        file_name = Path(upload.filename).name.strip() or "feedback_attachment"
        data = await upload.read()
        await upload.close()
        if not data:
            continue
        if len(data) > MAX_FEEDBACK_FILE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Файл '{file_name}' слишком большой. "
                    f"Максимум {MAX_FEEDBACK_FILE_BYTES // (1024 * 1024)} MB на файл."
                ),
            )
        total_bytes += len(data)
        if total_bytes > MAX_FEEDBACK_FILES_TOTAL_BYTES:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Суммарный размер файлов слишком большой. "
                    f"Максимум {MAX_FEEDBACK_FILES_TOTAL_BYTES // (1024 * 1024)} MB."
                ),
            )
        out.append((file_name, data))
    return out


def _normalize_feedback_text(feedback: str) -> str:
    normalized = feedback.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Комментарий не может быть пустым.")
    return normalized


def _optional_feedback_text(feedback: str) -> str | None:
    normalized = feedback.strip()
    return normalized or None


def _is_htmx_request(request: Request) -> bool:
    return "hx-request" in request.headers


def _redirect_to_detail(app_id: int) -> RedirectResponse:
    return RedirectResponse(url=f"/applications/{app_id}", status_code=303)


def _valid_status_filter(status: str | None) -> str | None:
    return status if status in ("draft", "pending", "rework", "approved") else None


async def _matches_filters(
    app: Application,
    *,
    status_filter: str | None,
    search_query: str,
) -> bool:
    if status_filter and app.status != status_filter:
        return False
    if search_query:
        full_name = (await db.get_user_full_name(app.user_id) or "").strip()
        if search_query.lower() not in full_name.lower():
            return False
    return True


@router.websocket("/ws/admin/applications")
async def applications_ws(websocket: WebSocket):
    admin_id = parse_admin_session(websocket.cookies.get("admin_session"))
    if admin_id is None or admin_id not in config.SUPERUSER_IDS:
        await websocket.close(code=1008)
        return

    hub: AdminWsHub = websocket.app.state.admin_ws_hub
    await hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(websocket)


@router.get("/partials/counters", response_class=HTMLResponse)
async def dashboard_counters_partial(request: Request, admin_id=Depends(get_admin)):
    counts = await application_service.get_status_counts()
    return templates.TemplateResponse(
        request=request,
        name="dashboard_counters.html",
        context={"request": request, "counts": counts},
    )


@router.get("/partials/row/{app_id}", response_class=HTMLResponse)
async def dashboard_row_partial(
    request: Request,
    app_id: int,
    status: str | None = None,
    q: str | None = None,
    admin_id=Depends(get_admin),
):
    app = await application_service.get_application(app_id)
    if not app:
        return Response(status_code=204)

    status_filter = _valid_status_filter(status)
    search_query = (q or "").strip()
    if not await _matches_filters(app, status_filter=status_filter, search_query=search_query):
        return Response(status_code=204)

    row = app.model_dump()
    row["full_name"] = await db.get_user_full_name(app.user_id)
    meeting_basket = status_filter == "approved"
    return templates.TemplateResponse(
        request=request,
        name="row.html",
        context={
            "request": request,
            "app": _parse_app(row),
            "meeting_basket": meeting_basket,
        },
    )


@router.get("/partials/application-meta/{app_id}", response_class=HTMLResponse)
async def application_meta_partial(
    request: Request,
    app_id: int,
    admin_id=Depends(get_admin),
):
    app = await application_service.get_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    row = app.model_dump()
    row["full_name"] = await db.get_user_full_name(app.user_id)
    return templates.TemplateResponse(
        request=request,
        name="application_detail_meta.html",
        context={"request": request, "app": _parse_app(row)},
    )


@router.get("/partials/application-feedback/{app_id}", response_class=HTMLResponse)
async def application_feedback_partial(
    request: Request,
    app_id: int,
    admin_id=Depends(get_admin),
):
    app = await application_service.get_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    row = app.model_dump()
    row["full_name"] = await db.get_user_full_name(app.user_id)
    return templates.TemplateResponse(
        request=request,
        name="application_detail_feedback.html",
        context={"request": request, "app": _parse_app(row)},
    )


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    status: str | None = None,
    q: str | None = None,
    admin_id=Depends(get_admin),
):
    if "tab" in request.query_params:
        tab_val = request.query_params.get("tab")
        st = request.query_params.get("status")
        query_params = {}
        if st in ("draft", "pending", "rework", "approved"):
            query_params["status"] = st
        elif tab_val == "archive":
            query_params["status"] = "approved"
        if request.query_params.get("meeting_err"):
            query_params["meeting_err"] = request.query_params.get("meeting_err")
        dest = "/" + ("?" + urlencode(query_params) if query_params else "")
        return RedirectResponse(url=dest, status_code=302)

    status_filter = _valid_status_filter(status)
    search_query = (q or "").strip()
    raw_apps, counts = await asyncio.gather(
        application_service.list_applications(status_filter, search_query),
        application_service.get_status_counts(),
    )

    ctx = {
        "request": request,
        "apps": [_parse_app(a) for a in raw_apps],
        "status_filter": status_filter,
        "counts": counts,
        "meeting_basket": status_filter == "approved",
        "search_query": search_query,
    }
    is_hx = "hx-request" in request.headers
    tpl = (
        "tbody_rows.html"
        if is_hx and request.headers.get("hx-target") == "app-table-body"
        else ("dashboard_apps.html" if is_hx else "index.html")
    )
    return templates.TemplateResponse(request=request, name=tpl, context=ctx)


@router.post("/approve/{app_id}")
async def approve_app(
    request: Request,
    app_id: int,
    background_tasks: BackgroundTasks,
    feedback: str = Form(""),
    feedback_files: list[UploadFile] | None = File(default=None),
    admin_id=Depends(get_admin),
):
    feedback_text = _optional_feedback_text(feedback)
    feedback_files_data = await _read_feedback_files(feedback_files)
    row = await application_service.approve(app_id, feedback=feedback_text)
    if row:
        logger.info(
            "Admin {} approved application {}. Feedback len: {}, attachments: {}",
            admin_id,
            app_id,
            len(feedback_text or ""),
            len(feedback_files_data),
        )
        if row.user_id:
            background_tasks.add_task(
                notify_user_application_approved,
                request.app.state.tg_bot,
                row.user_id,
                app_id,
                pdf_file_id=row.pdf_file_id,
                feedback=feedback_text,
                feedback_files=feedback_files_data,
                web_wording=True,
            )
    else:
        logger.warning("Admin {} tried to approve application {}, but it failed", admin_id, app_id)
        
    if _is_htmx_request(request):
        return await _render_row(request, app_id)
    return _redirect_to_detail(app_id)


@router.post("/reject/{app_id}")
async def reject_app(
    request: Request,
    app_id: int,
    background_tasks: BackgroundTasks,
    feedback: str = Form(...),
    feedback_files: list[UploadFile] | None = File(default=None),
    admin_id=Depends(get_admin),
):
    feedback = _normalize_feedback_text(feedback)
    feedback_files_data = await _read_feedback_files(feedback_files)
    row = await application_service.send_for_rework(app_id, feedback)
    if row:
        logger.info(
            "Admin {} sent application {} for rework. Feedback len: {}, attachments: {}",
            admin_id,
            app_id,
            len(feedback),
            len(feedback_files_data),
        )
        tpl = await get_template()
        background_tasks.add_task(
            notify_user_application_rework,
            request.app.state.tg_bot,
            row.user_id,
            app_id,
            feedback,
            reply_markup=kb.rework_keyboard(tpl, app_id),
            web_wording=True,
            feedback_files=feedback_files_data,
        )
    else:
        logger.warning("Admin {} failed to reject application {}", admin_id, app_id)
        
    if _is_htmx_request(request):
        return await _render_row(request, app_id)
    return _redirect_to_detail(app_id)


@router.post("/rework-approved/{app_id}")
async def rework_approved_app(
    request: Request,
    app_id: int,
    background_tasks: BackgroundTasks,
    feedback: str = Form(...),
    feedback_files: list[UploadFile] | None = File(default=None),
    admin_id=Depends(get_admin),
):
    feedback = _normalize_feedback_text(feedback)
    feedback_files_data = await _read_feedback_files(feedback_files)
    app_row = await application_service.get_application(app_id)
    if not app_row or app_row.status != "approved":
        logger.warning("Admin {} tried to rework app {} but status was {}", admin_id, app_id, app_row.status if app_row else 'NOT_FOUND')
        raise HTTPException(status_code=409, detail="Неверный статус")

    row = await application_service.send_for_rework(app_id, feedback)
    if row:
        logger.info(
            "Admin {} returned APPROVED application {} to rework. Attachments: {}",
            admin_id,
            app_id,
            len(feedback_files_data),
        )
        tpl = await get_template()
        background_tasks.add_task(
            notify_user_application_rework,
            request.app.state.tg_bot,
            row.user_id,
            app_id,
            feedback,
            reply_markup=kb.rework_keyboard(tpl, app_id),
            web_wording=True,
            feedback_files=feedback_files_data,
        )

    if _is_htmx_request(request):
        _meeting_basket = "status=approved" in request.headers.get("hx-current-url", "")
        return await _render_row(request, app_id, meeting_basket=_meeting_basket)
    return _redirect_to_detail(app_id)


@router.post("/delete/{app_id}")
async def delete_application_app(
    request: Request,
    app_id: int,
    admin_id=Depends(get_admin),
):
    app = await application_service.get_application(app_id)
    if not app:
        logger.warning("Admin {} tried to delete non-existent application {}", admin_id, app_id)
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    await application_service.delete_application(app_id)
    logger.info("Admin {} deleted application {}", admin_id, app_id)

    if _is_htmx_request(request):
        return Response(status_code=200)
    return RedirectResponse(url="/", status_code=303)


@router.get("/applications/{app_id}", response_class=HTMLResponse)
async def application_detail_page(
    request: Request, app_id: int, admin_id=Depends(get_admin)
):
    app = await application_service.get_application(app_id)
    if not app:
        logger.warning("Admin {} requested details for non-existent application {}", admin_id, app_id)
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    full_name, tpl = await asyncio.gather(
        db.get_user_full_name(app.user_id), get_template()
    )
    row = app.model_dump()
    row["full_name"] = full_name
    return templates.TemplateResponse(
        request=request,
        name="application_detail.html",
        context={
            "request": request,
            "app": _parse_app(row),
            "app_blocks": app.blocks,
            "tpl_blocks_map": {str(b.id): b for b in tpl.blocks},
        },
    )


@router.get("/download/{app_id}")
async def download_report(app_id: int, admin_id=Depends(get_admin)):
    app_row = await application_service.get_application(app_id)
    if not app_row:
        logger.warning("Admin {} tried to download report for non-existent application {}", admin_id, app_id)
        raise HTTPException(status_code=404)
        
    pdf_buf, full_name, position = await asyncio.gather(
        get_app_pdf_buffer(app_id),
        db.get_user_full_name(app_row.user_id),
        db.get_user_position(app_row.user_id),
    )
    custom_filename = resolve_application_pdf_filename(
        app_row.model_dump(),
        full_name=full_name,
        position=position,
        dt=app_row.created_at,
    )
    
    logger.info("Admin {} downloaded document for application {}", admin_id, app_id)
    return StreamingResponse(
        pdf_buf,
        media_type=media_type_for_filename(custom_filename),
        headers={
            "Content-Disposition": f"inline; filename*=utf-8''{quote(custom_filename)}"
        },
    )


@router.get("/download_attachment/{s3_key:path}")
async def download_file(s3_key: str, admin_id=Depends(get_admin)):
    if not s3_key or not s3_keys.is_allowed_attachment_download_key(s3_key.strip()):
        logger.warning("Admin {} requested empty or invalid S3 key: {}", admin_id, s3_key)
        raise HTTPException(status_code=400, detail="Недопустимый ключ")
        
    buf = await file_service.download_attachment_bytesio(s3_key)
    if not buf:
        logger.warning("Admin {}: S3 attachment not found: {}", admin_id, s3_key)
        raise HTTPException(status_code=404, detail="Не найден")
        
    logger.info("Admin {} downloaded S3 attachment: {}", admin_id, s3_key)
    return StreamingResponse(
        buf,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{quote(s3_key.split('/')[-1])}"
        },
    )


@router.get("/download_archive/{app_id}")
async def download_archive(app_id: int, request: Request, admin_id=Depends(get_admin)):
    app_row = await application_service.get_application(app_id)
    if not app_row:
        logger.warning("Admin {} tried to download archive for non-existent application {}", admin_id, app_id)
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    bot: Bot = request.app.state.tg_bot

    async def _fetch_attachment(idx: int, att):
        file_name = Path((att.name or "").strip() or f"attachment_{idx}").name
        try:
            if att.s3_key:
                buf = await file_service.download_attachment_bytesio(att.s3_key)
                if not buf:
                    raise RuntimeError("S3 object is missing")
                return file_name, buf.getvalue()
            elif att.file_id:
                tg_file = await bot.get_file(att.file_id)
                if not tg_file.file_path:
                    raise RuntimeError("Telegram file path is missing")
                tg_buf = BytesIO()
                await bot.download_file(tg_file.file_path, destination=tg_buf)
                return file_name, tg_buf.getvalue()
            else:
                return file_name, None
        except Exception as e:
            logger.warning(
                "Archive item skipped | app_id={} file={} err={}",
                app_id,
                file_name,
                e,
            )
            return file_name, None

    # все запросы параллельно: документ + имя + должность + все вложения
    results = await asyncio.gather(
        get_app_pdf_buffer(app_id),
        db.get_user_full_name(app_row.user_id),
        db.get_user_position(app_row.user_id),
        *[
            _fetch_attachment(i, att)
            for i, att in enumerate(app_row.attachments, start=1)
        ],
    )

    pdf_buf = results[0]
    full_name = results[1]
    position = results[2]
    att_results = results[3:]  # list of (file_name, data | None)

    pdf_name = resolve_application_pdf_filename(
        app_row.model_dump(),
        full_name=full_name,
        position=position,
        dt=app_row.created_at,
    )
    zip_buf = BytesIO()
    missed_files: list[str] = []

    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            Path(pdf_name).name or f"application_{app_id}.docx",
            pdf_buf.getvalue(),
        )
        for file_name, data in att_results:
            if data is not None:
                zf.writestr(file_name, data)
            else:
                missed_files.append(file_name)
        if missed_files:
            zf.writestr(
                "_archive_warnings.txt",
                "Не удалось добавить в архив файлы:\n- " + "\n- ".join(missed_files),
            )

    zip_buf.seek(0)
    headers = {
        "Content-Disposition": f"attachment; filename*=utf-8''{quote(f'application_{app_id}_files.zip')}"
    }
    
    logger.info("Admin {} generated and downloaded ZIP archive for application {}", admin_id, app_id)
    return StreamingResponse(zip_buf, media_type="application/zip", headers=headers)


@router.get("/download_tg_attachment")
async def download_tg_attachment(
    request: Request,
    file_id: str,
    name: str | None = None,
    admin_id=Depends(get_admin),
):
    """Скачивание файла по Telegram file_id (вложения, загруженные в боте до S3)."""
    if not file_id or not file_id.strip():
        logger.warning("Admin {} requested Telegram attachment with empty file_id", admin_id)
        raise HTTPException(status_code=400, detail="Пустой file_id")
        
    bot: Bot = request.app.state.tg_bot
    try:
        tg_file = await bot.get_file(file_id.strip())
    except Exception as e:
        logger.warning(
            "Telegram get_file failed for admin {} | file_id prefix={} err={}", admin_id, file_id[:16], e
        )
        raise HTTPException(
            status_code=404,
            detail="Файл недоступен (истёк срок хранения в Telegram или неверный идентификатор).",
        ) from e
        
    if not tg_file.file_path:
        logger.warning("Admin {}: Telegram file path is missing for file_id {}", admin_id, file_id[:16])
        raise HTTPException(status_code=404, detail="Нет пути к файлу в Telegram")
        
    buf = BytesIO()
    await bot.download_file(tg_file.file_path, destination=buf)
    buf.seek(0)
    fname = (name or "attachment").strip() or "attachment"
    headers = {"Content-Disposition": f"attachment; filename*=utf-8''{quote(fname)}"}
    
    logger.info("Admin {} downloaded Telegram attachment: {}", admin_id, file_id[:16])
    return StreamingResponse(
        buf, media_type="application/octet-stream", headers=headers
    )