"""
PDF-генерация служебной записки через ReportLab с фоном из шаблона.
"""

import re
import io
import json
from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    ListFlowable,
    ListItem,
    PageBreak,
    KeepTogether,
    Image as RLImage,  # Импортируем Image для вставки прямо в текст
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.fonts import addMapping
from datetime import datetime

from bot.logger import logger
import stdlib.db as db
import stdlib.s3 as s3
from stdlib.template import ApplicationTemplate, get_template

ASSETS_DIR = Path(__file__).parent / "assets"

# ─── Шрифты ──────────────────────────────────────────────────────────────────
_FONT_NAME = "TimesNewRoman"
_FONT_BOLD_NAME = "TimesNewRoman-Bold"

try:
    pdfmetrics.registerFont(TTFont(_FONT_NAME, str(ASSETS_DIR / "times.ttf")))
    pdfmetrics.registerFont(TTFont(_FONT_BOLD_NAME, str(ASSETS_DIR / "timesbd.ttf")))

    italic_path = ASSETS_DIR / "timesi.ttf"
    if italic_path.exists():
        pdfmetrics.registerFont(TTFont(f"{_FONT_NAME}-Italic", str(italic_path)))
    else:
        pdfmetrics.registerFont(
            TTFont(f"{_FONT_NAME}-Italic", str(ASSETS_DIR / "times.ttf"))
        )

    addMapping(_FONT_NAME, 0, 0, _FONT_NAME)
    addMapping(_FONT_NAME, 1, 0, _FONT_BOLD_NAME)
    addMapping(_FONT_NAME, 0, 1, f"{_FONT_NAME}-Italic")

    _font_registered = True
    logger.info("Times New Roman fonts successfully loaded from assets.")

except Exception as e:
    logger.warning("PDF: failed to load Times New Roman fonts from assets: {}", e)
    _font_registered = False

if not _font_registered:
    _FONT_NAME = "Helvetica"
    _FONT_BOLD_NAME = "Helvetica-Bold"

LOGO_PATH = ASSETS_DIR / "image1.png"
FOOTER_PATH = ASSETS_DIR / "image2.png"


# ─── Стили ───────────────────────────────────────────────────────────────────
def _styles() -> dict:
    return {
        "header": ParagraphStyle(
            "header",
            fontName=_FONT_BOLD_NAME,
            fontSize=12,
            alignment=TA_RIGHT,
            leading=14,
            spaceAfter=2,
        ),
        "title": ParagraphStyle(
            "title",
            fontName=_FONT_BOLD_NAME,
            fontSize=14,
            alignment=TA_CENTER,
            spaceBefore=20,
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            fontName=_FONT_NAME,
            fontSize=12,
            alignment=TA_CENTER,
            spaceAfter=14,
            fontStyle="italic",
        ),
        "section_title": ParagraphStyle(
            "section_title",
            fontName=_FONT_BOLD_NAME,
            fontSize=12,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body",
            fontName=_FONT_NAME,
            fontSize=12,
            alignment=TA_JUSTIFY,
            leading=16,
            spaceAfter=6,
        ),
        "footer_text": ParagraphStyle(
            "footer_text",
            fontName=_FONT_BOLD_NAME,
            fontSize=8,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#E33A35"),
        ),
    }


def _normalize_risk_placeholder(block_title: str, body_raw: str) -> str:
    if "риск" in block_title.lower() and body_raw.lower().strip() == "не применимо":
        return "(не применимо)"
    return body_raw


def _append_section_paragraphs(story: list, title: str, body: str, s: dict) -> None:
    section_elements = [Paragraph(title, s["section_title"])]
    lines = [line.strip() for line in body.split("\n") if line.strip()]

    has_numbering = any(
        len(line) > 2
        and line[0].isdigit()
        and (line[1:3] == ". " or line[1:3] == ") ")
        for line in lines
    )

    if has_numbering and lines:
        bullet_items = []
        for line in lines:
            clean_line = re.sub(r"^\d+[\.\)]\s*", "", line)
            bullet_items.append(ListItem(Paragraph(clean_line, s["body"])))

        section_elements.append(
            ListFlowable(
                bullet_items, bulletType="bullet", start="•", leftIndent=15
            )
        )
    else:
        for line in lines:
            section_elements.append(Paragraph(line, s["body"]))

    story.append(KeepTogether(section_elements))
    story.append(Spacer(1, 6))


def _parse_attachments_field(raw) -> list:
    attachments = raw or []
    if isinstance(attachments, str):
        try:
            valid_json_str = attachments.replace("'", '"')
            attachments = json.loads(valid_json_str)
        except Exception:
            if attachments.strip() in ("[]", "", "[ ]"):
                attachments = []
            else:
                attachments = [attachments]
    return attachments


# ─── Отрисовка фона ──────────────────────────────────────────────────────────
def draw_background(canvas, doc):
    """Логотип на всех страницах кроме последней."""
    width, height = A4
    canvas.saveState()
    if LOGO_PATH.exists():
        logo_w, logo_h = 320, 110
        canvas.drawImage(
            str(LOGO_PATH),
            (width - logo_w) / 2,
            height - logo_h - 20,
            width=logo_w,
            height=logo_h,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )
    canvas.restoreState()


def draw_last_page(canvas, doc):
    """Логотип + футер — только на последней странице."""
    width, height = A4
    canvas.saveState()
    if LOGO_PATH.exists():
        logo_w, logo_h = 320, 110
        canvas.drawImage(
            str(LOGO_PATH),
            (width - logo_w) / 2,
            height - logo_h - 20,
            width=logo_w,
            height=logo_h,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )
    if FOOTER_PATH.exists():
        footer_h = 100
        canvas.drawImage(
            str(FOOTER_PATH),
            0,
            0,
            width=width,
            height=footer_h,
            preserveAspectRatio=False,
            mask="auto",
        )
    canvas.restoreState()


async def _resolve_user_signature_bytes(user_id: int) -> bytes | None:
    """Берёт подпись пользователя: из S3 по ключу в БД либо устаревшие бинарные данные."""
    ref = await db.get_user_signature(user_id)
    if not ref:
        return None
    if isinstance(ref, (bytes, bytearray)):
        return bytes(ref)
    if not isinstance(ref, str):
        return None
    if ref.startswith("signatures/"):
        try:
            data = await s3.download_bytes(ref, s3.BUCKET_SIGNATURES)
            return data if data else None
        except RuntimeError:
            logger.warning("PDF: S3 не настроен — подпись из объектного хранилища недоступна")
            return None
        except Exception as e:
            logger.warning("PDF: не удалось скачать подпись из S3: {}", e)
            return None
    return None


class _LastPageCanvas(Canvas):
    """Обычный Canvas, подпись теперь рисуется в самом тексте."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for i, state in enumerate(self._saved_page_states, start=1):
            self.__dict__.update(state)
            if i < total:
                draw_background(self, None)
            else:
                draw_last_page(self, None)
            super().showPage()
        super().save()


# ─── Генерация ────────────────────────────────────────────────────────────────
async def generate_pdf(
    data: dict,
    user_id: int | None = None,
    *,
    tpl: ApplicationTemplate | None = None,
    blocks_map: dict[str, str] | None = None,
) -> BytesIO:
    """Генерирует PDF служебной записки с авто-подписью.

    Заявка из БД: передайте ``tpl`` и ``blocks_map`` (ключи — ``str(block_id)``).
    Локальные тесты: плоский ``data`` (topic, description, …) без ``tpl``.
    """
    try:
        if not data:
            data = {}

        signature_bytes: bytes | None = None
        if user_id:
            try:
                signature_bytes = await _resolve_user_signature_bytes(user_id)
            except Exception:
                signature_bytes = None

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=3 * cm,
            rightMargin=2.5 * cm,
            topMargin=4.5 * cm,
            bottomMargin=3.5 * cm,
        )

        s = _styles()
        story = []

        # ── Шапка ──
        story.append(Paragraph("Членам Правления", s["header"]))
        story.append(Paragraph("ПК «AKASHI Data Center PLC»", s["header"]))

        # ── Заголовок ──
        story.append(Paragraph("СЛУЖЕБНАЯ ЗАПИСКА", s["title"]))
        if tpl is not None and blocks_map is not None and tpl.blocks:
            topic = blocks_map.get(str(tpl.blocks[0].id), "") or "Без темы"
        else:
            topic = data.get("topic") or ""
        story.append(Paragraph(f"по вопросу «{topic}»", s["subtitle"]))

        # ── Текстовые блоки ──
        if tpl is not None and blocks_map is not None:
            for sec_idx, block in enumerate(tpl.blocks[1:], start=1):
                raw = blocks_map.get(str(block.id), "")
                body = _normalize_risk_placeholder(block.title, raw)
                _append_section_paragraphs(
                    story, f"{sec_idx}. {block.title}:", body, s
                )
            attach_num = len(tpl.blocks)
        else:
            risks_raw = data.get("risks") or ""
            risks_text = (
                "(не применимо)"
                if risks_raw.lower().strip() == "не применимо"
                else risks_raw
            )
            sections = [
                ("1. Краткое описание и суть вопроса:", data.get("description") or ""),
                ("2. Основание для вынесения:", data.get("basis") or ""),
                (
                    "3. Предлагаемое решение / варианты решений:",
                    data.get("solution") or "",
                ),
                ("4. Риски и последствия (если актуально):", risks_text),
            ]
            for title, body in sections:
                _append_section_paragraphs(story, title, body, s)
            attach_num = 5

        # ── Приложения ──
        story.append(
            Paragraph(
                f"{attach_num}. Приложения / дополнительные материалы:",
                s["section_title"],
            )
        )

        attachments = _parse_attachments_field(data.get("attachments"))

        if attachments and isinstance(attachments, list) and len(attachments) > 0:
            items = [
                ListItem(Paragraph(str(name), s["body"]))
                for name in attachments
                if str(name).strip()
            ]
            if items:
                story.append(
                    ListFlowable(items, bulletType="bullet", start="•", leftIndent=15)
                )
            else:
                story.append(Paragraph("(приложения не прикреплены)", s["body"]))
        else:
            story.append(Paragraph("(приложения не прикреплены)", s["body"]))

        # ── Подвал (подпись) ──
        story.append(PageBreak())
        story.append(Spacer(1, 40))

        username = (
            data.get("full_name")
            or data.get("fio")
            or data.get("username")
            or data.get("name")
            or "Неизвестно"
        )
        position = data.get("position") or "Руководитель подразделения"
        date = data.get("date") or "__.__.____"

        story.append(Paragraph(f"<b>{position}:</b>", s["body"]))

        # Небольшой отступ после должности
        story.append(Spacer(1, 5))

        if signature_bytes:
            try:
                sig_stream = io.BytesIO(signature_bytes)
                # Ограничиваем размер картинки
                sig_img = RLImage(sig_stream, width=4 * cm, height=2 * cm)
                sig_img.hAlign = "LEFT"
                story.append(sig_img)

                # 🔥 МАГИЯ: Отрицательный отступ! Подтягиваем линию ВВЕРХ под картинку
                story.append(Spacer(1, -1 * cm))
            except Exception as e:
                logger.warning("PDF: Ошибка вставки картинки подписи: {}", e)
                story.append(Spacer(1, 1.5 * cm))
        else:
            story.append(Spacer(1, 1.5 * cm))

        story.append(Paragraph(f"________________ /{username}/", s["body"]))
        story.append(Spacer(1, 10))
        story.append(Paragraph(f"<b>Дата:</b> {date}", s["body"]))

        doc.build(story, canvasmaker=_LastPageCanvas)

        buffer.seek(0)
        logger.info("PDF generated successfully for app_id={}", data.get("app_id"))
        return buffer

    except Exception as e:
        logger.error("PDF generation failed for app_id={}: {}", data.get("app_id"), e)
        import traceback

        logger.error("Traceback: {}", traceback.format_exc())
        raise


def generate_pdf_filename(
    full_name: str | None, position: str | None, dt: datetime
) -> str:
    """Генерирует стандартизированное имя для PDF-файла."""
    safe_name = (full_name or "Сотрудник").replace(" ", "_")
    safe_pos = (position or "Должность").replace(" ", "_")
    time_str = dt.strftime("%H-%M_%d-%m-%Y")

    return f"{time_str}_{safe_name}_{safe_pos}.pdf"


async def invalidate_pdf_cache(app_id: int) -> None:
    """Инвалидирует кэш PDF для заявки после изменения данных.

    Сейчас `get_app_pdf_buffer` всегда генерирует PDF заново; при появлении
    Redis-кэша для PDF добавьте сюда удаление ключей.
    """
    _ = app_id


async def get_app_pdf_buffer(app_id: int) -> BytesIO:
    """Универсальная функция подготовки и генерации PDF для заявки.
    Единый источник истины для бота и веба."""

    app_raw = await db.get_app(app_id)
    if not app_raw:
        raise ValueError(f"App {app_id} not found")

    u_id = app_raw["user_id"]
    try:
        blocks = json.loads(app_raw.get("blocks", "{}"))
    except Exception:
        blocks = {}

    tpl = await get_template()

    raw_att = app_raw.get("attachments")
    clean_atts = []
    if raw_att:
        if isinstance(raw_att, str):
            try:
                raw_att = json.loads(raw_att.replace("'", '"'))
            except Exception:
                raw_att = []
        if isinstance(raw_att, list):
            for f in raw_att:
                if isinstance(f, dict):
                    clean_atts.append(f.get("name") or f.get("file_name") or "Файл")
                else:
                    clean_atts.append(str(f))

    pdf_data = {
        "app_id": app_id,
        "attachments": clean_atts,
        "full_name": await db.get_user_full_name(u_id),
        "position": await db.get_user_position(u_id),
        "date": app_raw["created_at"].strftime("%d.%m.%Y"),
    }

    return await generate_pdf(
        pdf_data, user_id=u_id, tpl=tpl, blocks_map=blocks
    )
