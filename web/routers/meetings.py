from datetime import datetime, time
from urllib.parse import quote
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

import stdlib.db as db
from stdlib.services import meeting_service
from bot.logger import logger
from web.templating import templates
from web.dependencies import get_admin
from web.routers.apps import _parse_app
from stdlib.timezone_util import wall_time_astana_to_utc

router = APIRouter(prefix="/meetings", tags=["meetings"])


def _meeting_form_err_prefix(form) -> str:
    if (form.get("meeting_form_source") or "").strip() == "meetings":
        return "/meetings?meeting_err="
    return "/?status=approved&meeting_err="


def _parse_meeting_schedule(form) -> datetime | None:
    naive = None
    raw_at = form.get("scheduled_at")
    if raw_at and str(raw_at).strip():
        s = str(raw_at).strip()
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                naive = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
    if naive is None:
        raw_date = form.get("scheduled_date")
        if raw_date and str(raw_date).strip():
            try:
                d = datetime.strptime(str(raw_date).strip(), "%Y-%m-%d").date()
                naive = datetime.combine(d, time(10, 0))
            except ValueError:
                pass
    return wall_time_astana_to_utc(naive) if naive else None


@router.post("")
async def meetings_create(request: Request, admin_id=Depends(get_admin)):
    form = await request.form()
    err_base = _meeting_form_err_prefix(form)
    scheduled = _parse_meeting_schedule(form)
    if not scheduled:
        return RedirectResponse(
            url=f"{err_base}{quote('Укажите дату и время заседания')}", status_code=303
        )

    app_ids = [int(x) for x in form.getlist("app_id") if x.isdigit()]
    try:
        if not app_ids:
            await meeting_service.create_meeting(scheduled, admin_id)
        else:
            await meeting_service.create_meeting_with_applications(
                scheduled, admin_id, app_ids
            )
    except Exception as e:
        return RedirectResponse(
            url=f"/meetings?meeting_err={quote(str(e))}", status_code=303
        )

    return RedirectResponse(url="/meetings?created=1", status_code=303)


@router.get("", response_class=HTMLResponse)
async def meetings_list(
    request: Request,
    admin_id=Depends(get_admin),
    created: str | None = None,
    deleted: str | None = None,
):
    upcoming, past = (
        await meeting_service.get_upcoming(),
        await meeting_service.get_past(),
    )
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


@router.get("/{meeting_id}", response_class=HTMLResponse)
async def meeting_detail_page(
    request: Request,
    meeting_id: int,
    admin_id=Depends(get_admin),
    updated: str | None = None,
):
    meeting = await meeting_service.get_by_id(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Заседание не найдено")
    apps = [
        _parse_app(a) for a in await db.get_applications_by_ids(meeting.application_ids)
    ]
    return templates.TemplateResponse(
        request=request,
        name="meeting_detail.html",
        context={
            "request": request,
            "meeting": meeting,
            "apps": apps,
            "schedule_updated_ok": updated == "1",
        },
    )


@router.post("/{meeting_id}/schedule")
async def meeting_update_schedule(
    request: Request, meeting_id: int, admin_id=Depends(get_admin)
):
    form = await request.form()
    scheduled = _parse_meeting_schedule(form)
    if not scheduled:
        return RedirectResponse(
            url=f"/meetings/{meeting_id}?schedule_err={quote('Укажите дату и время')}",
            status_code=303,
        )
    if not await meeting_service.set_scheduled_at(meeting_id, scheduled):
        raise HTTPException(status_code=404)
    return RedirectResponse(url=f"/meetings/{meeting_id}?updated=1", status_code=303)


@router.post("/{meeting_id}/remove_app/{app_id}")
async def meeting_remove_app(meeting_id: int, app_id: int, admin_id=Depends(get_admin)):
    if not await meeting_service.remove_application_from_meeting(meeting_id, app_id):
        raise HTTPException(status_code=404)
    return RedirectResponse(url=f"/meetings/{meeting_id}", status_code=303)


@router.post("/{meeting_id}/delete")
async def meeting_delete(meeting_id: int, admin_id=Depends(get_admin)):
    if not await meeting_service.delete_meeting(meeting_id):
        raise HTTPException(status_code=404)
    return RedirectResponse(url="/meetings?deleted=1", status_code=303)
