import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from pathlib import Path
from datetime import datetime
from aiogram import Bot
from urllib.parse import quote  # Нужно для кириллицы в названиях файлов
from bot.logger import logger

import stdlib.db as db
import stdlib.keyboards as kb
from stdlib.pdf import (
    get_app_pdf_buffer,
    generate_pdf_filename,
)  # Импортируем обе функции
from bot.config import config


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    app.state.tg_bot = Bot(token=config.BOT_TOKEN)
    yield
    await db.close_db()
    await app.state.tg_bot.session.close()


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="web/templates")
templates.env.filters["datetime"] = lambda v: (
    v.strftime("%d.%m.%Y %H:%M") if isinstance(v, datetime) else v
)


async def get_admin(request: Request):
    admin_id = request.cookies.get("admin_session")
    if not admin_id or int(admin_id) not in config.SUPERUSER_IDS:
        raise HTTPException(status_code=401)
    return int(admin_id)


@app.exception_handler(401)
async def auth_handler(request, exc):
    return RedirectResponse(url="/login")


# --- РОУТЫ ---


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, tab: str = "active", admin_id=Depends(get_admin)):
    raw_apps = await db.get_applications(tab)
    parsed_apps = [_parse_app(a) for a in raw_apps]
    tpl = "table_body.html" if "hx-request" in request.headers else "index.html"
    return templates.TemplateResponse(
        request=request,
        name=tpl,
        context={"request": request, "apps": parsed_apps, "tab": tab},
    )


@app.post("/approve/{app_id}")
async def approve_app(request: Request, app_id: int, admin_id=Depends(get_admin)):
    # 1. Обновляем статус в БД
    await db.update_status(app_id, "approved")
    await db.set_t_decision(app_id)

    # 2. Получаем данные заявки, чтобы узнать user_id
    app_data = await db.get_app(app_id)

    if app_data and app_data.get("user_id"):
        try:
            # 3. Отправляем радостную весть юзеру в ТГ
            await app.state.tg_bot.send_message(
                app_data["user_id"],
                f"✅ <b>Ваша заявка #{app_id} успешно согласована!</b>\n\n"
                f"Документ передан в дальнейшую работу.",
                parse_mode="HTML",
            )
            logger.info(f"Approve notification sent to user for app {app_id}")
        except Exception as e:
            # Обернули в try/except, чтобы сайт не упал, если юзер вдруг заблокировал бота
            logger.error(
                f"Ошибка отправки уведомления об апруве для заявки {app_id}: {e}"
            )

    # 4. Обновляем табличку на сайте
    return await _render_row(request, app_id)


@app.post("/reject/{app_id}")
async def reject_app(
    request: Request,
    app_id: int,
    feedback: str = Form(...),
    admin_id=Depends(get_admin),
):
    """Обработка Рework (Отправка на доработку)"""
    await db.update_status(app_id, "rework", feedback=feedback)
    await db.set_t_decision(app_id)
    await db.increment_reject_count(app_id)

    app_data = await db.get_app(app_id)
    try:
        await app.state.tg_bot.send_message(
            app_data["user_id"],
            f"❌ <b>Заявка #{app_id} возвращена на доработку.</b>\n\n"
            f"<b>Замечания:</b>\n{feedback}\n\n"
            "<i>Используйте кнопки ниже для редактирования:</i>",
            parse_mode="HTML",
            reply_markup=kb.rework_keyboard(),
        )
    except Exception as e:
        logger.error(f"Ошибка отправки в ТГ: {e}")

    return await _render_row(request, app_id)


@app.get("/download/{app_id}")
async def download_report(app_id: int, admin_id=Depends(get_admin)):
    """Скачивание сгенерированного PDF"""
    app_raw = await db.get_app(app_id)
    if not app_raw:
        raise HTTPException(status_code=404)

    # 1. Генерируем буфер PDF (там внутри уже чистятся файлы)
    pdf_buf = await get_app_pdf_buffer(app_id)

    # 2. Достаем данные для правильного имени файла
    u_id = app_raw["user_id"]
    full_name = await db.get_user_full_name(u_id)
    position = await db.get_user_position(u_id)

    # Формируем имя через нашу общую функцию
    custom_filename = generate_pdf_filename(full_name, position, app_raw["created_at"])

    # 3. Отдаем браузеру с правильным заголовком
    headers = {
        # inline - пытается открыть в браузере. Если хочешь чтобы всегда скачивалось, замени на attachment
        "Content-Disposition": f"inline; filename*=utf-8''{quote(custom_filename)}"
    }

    return StreamingResponse(pdf_buf, media_type="application/pdf", headers=headers)


@app.get("/download_attachment/{file_id:path}")
async def download_file(file_id: str, admin_id=Depends(get_admin)):
    try:
        bot: Bot = app.state.tg_bot
        file = await bot.get_file(file_id)
        file_url = (
            f"https://api.telegram.org/file/bot{config.BOT_TOKEN}/{file.file_path}"
        )
        return RedirectResponse(url=file_url)
    except Exception as e:
        logger.error(f"Ошибка при получении файла {file_id}: {e}")
        raise HTTPException(
            status_code=400, detail="Не удалось получить файл из Telegram"
        )


# --- Вспомогательные функции (Internal) ---


def _clean_attachments(att):
    """Безопасно превращает строку из БД в нормальный список словарей."""
    if not att:
        return []
    if isinstance(att, list):
        return att
    if isinstance(att, str):
        if att.strip() in ("[]", "", "None"):
            return []
        try:
            return json.loads(att.replace("'", '"'))
        except Exception as e:
            logger.error(f"Ошибка парсинга аттачментов: {e}")
            return []
    return []


def _parse_app(a):
    """Подготавливает данные заявки для row.html"""
    try:
        b = json.loads(a.get("blocks", "{}"))
    except:
        b = {}

    a["topic"] = b.get("1", "Без темы")
    a["display_name"] = a.get("full_name") or a.get("username") or f"ID: {a['user_id']}"

    raw_files = _clean_attachments(a.get("attachments"))

    a["parsed_attachments"] = []
    for f in raw_files:
        if isinstance(f, dict):
            a["parsed_attachments"].append(
                {
                    "file_id": f.get("file_id"),
                    "file_name": f.get("name") or f.get("file_name") or "Файл",
                }
            )

    return a


async def _render_row(request, app_id):
    a = await db.get_app(app_id)
    a["full_name"] = await db.get_user_full_name(a["user_id"])
    return templates.TemplateResponse(
        request=request,
        name="row.html",
        context={"request": request, "app": _parse_app(a)},
    )
