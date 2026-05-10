import html
import json
from types import SimpleNamespace
from fastapi import APIRouter, Request, Form, Depends, Response
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

import stdlib.db as db
from bot.logger import logger
from web.templating import templates
from web.dependencies import get_admin
from web.routers.auth import _get_hashed_password
from stdlib.template import ApplicationTemplate, get_template, persist_template

router = APIRouter(prefix="/settings", tags=["settings"])

HELP_TEXT_SETTINGS_KEY = "user_help_text"

def _default_help_text() -> str:
    return (
        "📘 <b>Как пользоваться ботом AKASHI</b>\n\n"
        "1) Заполните профиль:\n"
        "• /register — ФИО\n"
        "• /position — должность\n"
        "• /sign — подпись\n\n"
        "2) Создайте заявку: /start\n"
        "3) Заполните блоки, добавьте файлы и отправьте на согласование.\n\n"
        "Полезные команды:\n"
        "• /mode — переключить режим (пошаговый / свободный)\n"
        "• /web — вход в веб-панель\n"
        "• /myapps — мои заявки"
    )

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

@router.get("", response_class=HTMLResponse)
async def settings_page(request: Request, admin_id=Depends(get_admin)):
    hashed = await _get_hashed_password(admin_id)
    raw_help = await db.get_setting(HELP_TEXT_SETTINGS_KEY)
    help_text = _default_help_text()
    
    if isinstance(raw_help, str):
        try:
            help_data = json.loads(raw_help)
        except Exception:
            help_data = None
    else:
        help_data = raw_help
        
    if isinstance(help_data, dict):
        saved = str(help_data.get("text") or "").strip()
        if saved:
            help_text = saved
            
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "has_password": bool(hashed),
            "success": request.query_params.get("success"),
            "error": None,
            "help_text": help_text,
        },
    )

@router.post("/password", response_class=HTMLResponse)
async def set_password(request: Request, password: str = Form(...), admin_id=Depends(get_admin)):
    if len(password) < 8:
        return HTMLResponse('<p class="text-akashi-red text-[10px] font-black text-center">⚠ Минимум 8 символов</p>')
    await db.update_user_password(admin_id, password)
    logger.info("Password updated for admin {}", admin_id)
    return HTMLResponse('<p class="text-green-500 text-[10px] font-black text-center">✓ Пароль сохранён</p>')

@router.post("/help-text", response_class=HTMLResponse)
async def set_help_text(help_text: str = Form(...), admin_id=Depends(get_admin)):
    text = (help_text or "").strip()
    if not text:
        return HTMLResponse('<p class="text-akashi-red text-[10px] font-black text-center">⚠ Текст не должен быть пустым</p>', status_code=400)
    await db.upsert_setting(HELP_TEXT_SETTINGS_KEY, {"text": text})
    logger.info("help text updated by admin {}", admin_id)
    return HTMLResponse('<p class="text-green-500 text-[10px] font-black text-center">✓ Инструкция сохранена</p>')

@router.post("/help-text/reset", response_class=HTMLResponse)
async def reset_help_text(admin_id=Depends(get_admin)):
    default_text = _default_help_text()
    await db.upsert_setting(HELP_TEXT_SETTINGS_KEY, {"text": default_text})
    escaped = html.escape(default_text)
    return HTMLResponse(
        '<p class="text-green-500 text-[10px] font-black text-center">✓ Сброшено на дефолт</p>'
        f'<textarea id="help-text-field" hx-swap-oob="true" name="help_text" rows="12" class="ak-input resize-y" required>{escaped}</textarea>'
    )

@router.get("/template", response_class=HTMLResponse)
async def template_editor_page(request: Request, admin_id=Depends(get_admin)):
    try:
        tpl = await get_template()
    except RuntimeError as e:
        return templates.TemplateResponse(request=request, name="template_editor_error.html", context={"message": str(e)})
    return templates.TemplateResponse(request=request, name="template_editor.html", context={"blocks": tpl.blocks})

@router.get("/template/new-row", response_class=HTMLResponse)
async def template_editor_new_row(request: Request, next_id: int, admin_id=Depends(get_admin)):
    block = SimpleNamespace(id=next_id, title="", question="", description_for_llm=None)
    return templates.TemplateResponse(request=request, name="template_block_row.html", context={"block": block})

@router.delete("/template/ui-row")
async def template_editor_row_delete_ui(admin_id=Depends(get_admin)):
    return Response(status_code=200, content="")

@router.post("/template/save", response_class=HTMLResponse)
async def template_editor_save(
    admin_id=Depends(get_admin),
    block_id: list[str] = Form(...),
    block_title: list[str] = Form(...),
    block_question: list[str] = Form(...),
    block_desc: list[str] | None = Form(None),
):
    n = len(block_id)
    if n == 0:
        return HTMLResponse('<p class="text-akashi-red text-[10px]">Нужен хотя бы один блок</p>', status_code=400)
    
    desc_list = block_desc or []
    while len(desc_list) < n:
        desc_list.append("")

    rows = []
    for i in range(n):
        rows.append({
            "id": i + 1,
            "title": (block_title[i] or "").strip(),
            "question": (block_question[i] or "").strip(),
            "description_for_llm": (desc_list[i] or "").strip() or None,
        })

    try:
        app_tpl = ApplicationTemplate.model_validate({"blocks": rows})
        await persist_template(app_tpl)
    except Exception as e:
        return HTMLResponse(f'<p class="text-akashi-red text-[10px]">Ошибка: {html.escape(str(e))}</p>', status_code=500)

    return HTMLResponse('<p class="text-green-500 text-[10px] font-black">✓ Шаблон сохранён</p>')