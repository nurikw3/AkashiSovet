import asyncio
import hashlib
import re
import io
import json
import ast
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
    Image as RLImage,
    KeepTogether,  
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
from stdlib.template import (
    ApplicationTemplate,
    PDF_TEMPLATE_REVISION_KEY,
    get_template,
)
from stdlib.text_normalize import expand_numbered_newlines
from stdlib.timezone_util import ensure_app_tz, format_app_date_only
import stdlib.redis_client as redis_client_module

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
FOOTER_PATH = (
    ASSETS_DIR / "image2_updated.png"
    if (ASSETS_DIR / "image2_updated.png").exists()
    else ASSETS_DIR / "image2.png"
)


PDF_CACHE_KEY_FMT = "pdf_cache:{app_id}"
PDF_CACHE_TTL_SEC = 7 * 24 * 3600


def _pdf_cache_token(
    app_raw: dict,
    full_name: str | None,
    position: str | None,
    sig_ref: str | None,
    tpl: ApplicationTemplate,
    template_revision: str,
) -> str:
    blocks = app_raw.get("blocks") or ""
    attachments = app_raw.get("attachments") or ""
    updated_at = str(app_raw.get("updated_at") or "")
    tpl_json = json.dumps(
        [b.model_dump(mode="json") for b in tpl.blocks],
        sort_keys=True,
        ensure_ascii=False,
    )
    parts = [
        updated_at,
        str(blocks),
        str(attachments),
        full_name or "",
        position or "",
        sig_ref or "",
        tpl_json,
        template_revision,
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


async def _get_pdf_template_revision() -> str:
    r = redis_client_module.redis_client
    if not r:
        return "0"
    try:
        v = await r.get(PDF_TEMPLATE_REVISION_KEY)
        return v if v is not None else "0"
    except Exception:
        return "0"


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


_PDF_UNSAFE_DASH = str.maketrans(
    {
        "\u2011": "-",
        "\u2010": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\ufeff": "",
        "\u00ad": "",
    }
)


def _normalize_pdf_user_text(text: str) -> str:
    if not text:
        return text
    t = text.translate(_PDF_UNSAFE_DASH)
    for z in ("\u200b", "\u200c", "\u200d", "\u2060"):
        t = t.replace(z, "")
    return t


def _append_section_paragraphs(story: list, title: str, body: str, s: dict) -> None:
    title = _normalize_pdf_user_text(title)
    body = _normalize_pdf_user_text(body)
    body = expand_numbered_newlines(body)
    
    block_story = []
    block_story.append(Paragraph(title, s["section_title"]))
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

        block_story.append(
            ListFlowable(
                bullet_items, bulletType="bullet", start="•", leftIndent=15
            )
        )
    else:
        for line in lines:
            block_story.append(Paragraph(line, s["body"]))
            
    block_story.append(Spacer(1, 6))
    
    story.append(KeepTogether(block_story))


def _parse_attachments_field(raw) -> list:
    attachments = raw or []
    if isinstance(attachments, str):
        try:
            attachments = ast.literal_eval(attachments)
        except (ValueError, SyntaxError):
            try:
                attachments = json.loads(attachments)
            except Exception:
                if attachments.strip() in ("[]", "", "[ ]"):
                    attachments = []
                else:
                    attachments = [attachments]
    return attachments


# ─── Отрисовка фона ──────────────────────────────────────────────────────────
def draw_background(canvas, doc):
    """Рисует логотип в шапке страницы."""
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


def draw_last_page(canvas, doc, *, include_logo: bool = True):
    """Рисует оформление последней страницы (опциональный логотип + футер)."""
    width, height = A4
    canvas.saveState()
    if include_logo and LOGO_PATH.exists():
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
    ref = await db.get_user_signature(user_id)
    return await _load_signature_for_ref(ref)


async def _load_signature_for_ref(ref: str | bytes | bytearray | None) -> bytes | None:
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
    """Рисует логотип на каждой странице, а футер — только на последней."""

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
            
            # Шапка рисуется ВСЕГДА
            draw_background(self, None)
            
            # Подвал (футер) рисуется ТОЛЬКО на последней странице
            if i == total:
                draw_last_page(self, None, include_logo=False)
                
            super().showPage()
        super().save()


# ─── Генерация ────────────────────────────────────────────────────────────────
def _generate_pdf_sync(
    data: dict,
    tpl: ApplicationTemplate | None,
    blocks_map: dict[str, str] | None,
    signature_bytes: bytes | None,
) -> BytesIO:
    if not data:
        data = {}

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=3 * cm,
        rightMargin=2.5 * cm,
        topMargin=4.5 * cm,
        bottomMargin=5.0 * cm,
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
    topic = _normalize_pdf_user_text(topic)
    story.append(Paragraph(f"по вопросу «{topic}»", s["subtitle"]))

    # ── Текстовые блоки ──
    if tpl is not None and blocks_map is not None:
        for sec_idx, block in enumerate(tpl.blocks[1:], start=1):
            raw = blocks_map.get(str(block.id), "")
            body = _normalize_risk_placeholder(block.title, raw)
            _append_section_paragraphs(story, f"{sec_idx}. {block.title}:", body, s)
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
            ("3. Предлагаемое решение / варианты решений:", data.get("solution") or ""),
            ("4. Риски и последствия (если актуально):", risks_text),
        ]
        for sec_title, body in sections:
            _append_section_paragraphs(story, sec_title, body, s)
        attach_num = 5

    # ── Приложения ──
    attach_story = []
    attach_story.append(
        Paragraph(
            f"{attach_num}. Приложения / дополнительные материалы:",
            s["section_title"],
        )
    )

    attachments = _parse_attachments_field(data.get("attachments"))

    if attachments and isinstance(attachments, list) and len(attachments) > 0:
        items = [
            ListItem(Paragraph(_normalize_pdf_user_text(str(name)), s["body"]))
            for name in attachments
            if str(name).strip()
        ]
        if items:
            attach_story.append(
                ListFlowable(items, bulletType="bullet", start="•", leftIndent=15)
            )
        else:
            attach_story.append(Paragraph("(приложения не прикреплены)", s["body"]))
    else:
        attach_story.append(Paragraph("(приложения не прикреплены)", s["body"]))

    # Склеиваем блок "Приложения", чтобы он не разрывался на страницы
    story.append(KeepTogether(attach_story))

    # ── Подвал (подпись) ──
    story.append(Spacer(1, 40))
    
    # Собираем блок подписи целиком, чтобы он не отрывался от имени и даты
    signature_story = []

    username = _normalize_pdf_user_text(
        str(
            data.get("full_name")
            or data.get("fio")
            or data.get("username")
            or data.get("name")
            or "Неизвестно"
        )
    )
    position = _normalize_pdf_user_text(
        str(data.get("position") or "Руководитель подразделения")
    )
    date = str(data.get("date") or "__.__.____")

    signature_story.append(Paragraph(f"<b>{position}:</b>", s["body"]))
    signature_story.append(Spacer(1, 5))

    if signature_bytes:
        try:
            sig_stream = io.BytesIO(signature_bytes)
            sig_img = RLImage(sig_stream, width=4 * cm, height=2 * cm)
            sig_img.hAlign = "LEFT"
            signature_story.append(sig_img)
            signature_story.append(Spacer(1, -1 * cm))
        except Exception as e:
            logger.warning("PDF: Ошибка вставки картинки подписи: {}", e)
            signature_story.append(Spacer(1, 1.5 * cm))
    else:
        signature_story.append(Spacer(1, 1.5 * cm))

    signature_story.append(Paragraph(f"________________ /{username}/", s["body"]))
    signature_story.append(Spacer(1, 10))
    signature_story.append(Paragraph(f"<b>Дата:</b> {date}", s["body"]))

    story.append(KeepTogether(signature_story))

    doc.build(story, canvasmaker=_LastPageCanvas)

    buffer.seek(0)
    return buffer


async def generate_pdf(
    data: dict,
    user_id: int | None = None,
    signature_bytes: bytes | None = None,
    *,
    tpl: ApplicationTemplate | None = None,
    blocks_map: dict[str, str] | None = None,
) -> BytesIO:
    try:
        if not data:
            data = {}

        if signature_bytes is None and user_id:
            try:
                signature_bytes = await _resolve_user_signature_bytes(user_id)
            except Exception:
                signature_bytes = None

        buffer = await asyncio.to_thread(
            _generate_pdf_sync, data, tpl, blocks_map, signature_bytes
        )
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
    safe_name = (full_name or "Сотрудник").replace(" ", "_")
    safe_pos = (position or "Должность").replace(" ", "_")
    time_str = ensure_app_tz(dt).strftime("%H-%M_%d-%m-%Y")
    return f"{time_str}_{safe_name}_{safe_pos}.pdf"


async def invalidate_pdf_cache(app_id: int, *, user_id: int | None = None) -> None:
    r = redis_client_module.redis_client
    cache_key = PDF_CACHE_KEY_FMT.format(app_id=app_id)
    if r:
        try:
            await r.delete(cache_key)
        except Exception as e:
            logger.warning("invalidate_pdf_cache redis delete app_id={}: {}", app_id, e)

    try:
        await db.set_pdf_file_id(app_id, None)
    except Exception as e:
        logger.warning("invalidate_pdf_cache clear pdf_file_id app_id={}: {}", app_id, e)

    if not s3.is_s3_configured():
        return
    uid = user_id
    if uid is None:
        row = await db.get_app(app_id)
        if not row:
            return
        uid = row["user_id"]
    key = s3.pdf_key(uid, app_id)
    try:
        await s3.delete_object(key, s3.BUCKET_PDF)
    except Exception as e:
        logger.warning("invalidate_pdf_cache s3 delete app_id={} key={}: {}", app_id, key, e)


async def get_app_pdf_buffer(app_id: int) -> BytesIO:
    app_raw = await db.get_app(app_id)
    if not app_raw:
        raise ValueError(f"App {app_id} not found")

    u_id = app_raw["user_id"]
    try:
        blocks = json.loads(app_raw.get("blocks", "{}"))
    except Exception:
        blocks = {}

    tpl, full_name, position, sig_ref, tpl_rev = await asyncio.gather(
        get_template(),
        db.get_user_full_name(u_id),
        db.get_user_position(u_id),
        db.get_user_signature(u_id),
        _get_pdf_template_revision(),
    )
    token = _pdf_cache_token(app_raw, full_name, position, sig_ref, tpl, tpl_rev)

    r = redis_client_module.redis_client
    cache_key = PDF_CACHE_KEY_FMT.format(app_id=app_id)
    if r and s3.is_s3_configured():
        try:
            cached = await r.get(cache_key)
            if cached == token:
                pdf_key = s3.pdf_key(u_id, app_id)
                pdf_bytes = await s3.download_bytes(pdf_key, s3.BUCKET_PDF)
                if pdf_bytes:
                    logger.debug(
                        "PDF cache hit app_id={} size_bytes={}",
                        app_id,
                        len(pdf_bytes),
                    )
                    return BytesIO(pdf_bytes)
        except Exception as e:
            logger.warning("PDF cache read failed app_id={}: {}", app_id, e)

    # В get_app_pdf_buffer используем ту же безопасную функцию для парсинга вложений
    raw_att = app_raw.get("attachments")
    parsed_atts = _parse_attachments_field(raw_att)
    clean_atts = []
    
    if isinstance(parsed_atts, list):
        for f in parsed_atts:
            if isinstance(f, dict):
                clean_atts.append(f.get("name") or f.get("file_name") or "Файл")
            else:
                clean_atts.append(str(f))

    pdf_data = {
        "app_id": app_id,
        "attachments": clean_atts,
        "full_name": full_name,
        "position": position,
        "date": format_app_date_only(app_raw["created_at"]),
    }

    signature_bytes = await _load_signature_for_ref(sig_ref)
    buf = await generate_pdf(
        pdf_data,
        user_id=u_id,
        signature_bytes=signature_bytes,
        tpl=tpl,
        blocks_map=blocks,
    )

    if r and s3.is_s3_configured():
        try:
            body = buf.getvalue()
            logger.info(
                "PDF ready | app_id={} size_bytes={} size_kb={:.1f}",
                app_id,
                len(body),
                len(body) / 1024,
            )
            await s3.upload_bytes(
                body, s3.pdf_key(u_id, app_id), s3.BUCKET_PDF, "application/pdf"
            )
            await r.set(cache_key, token, ex=PDF_CACHE_TTL_SEC)
        except Exception as e:
            logger.warning("PDF cache store failed app_id={}: {}", app_id, e)
    else:
        logger.info(
            "PDF ready | app_id={} size_bytes={} size_kb={:.1f}",
            app_id,
            len(buf.getbuffer()),
            len(buf.getbuffer()) / 1024,
        )

    buf.seek(0)
    return buf
