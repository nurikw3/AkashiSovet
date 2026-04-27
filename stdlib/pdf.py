"""
PDF-генерация служебной записки через ReportLab с фоном из шаблона.
"""
from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, ListFlowable, ListItem
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_JUSTIFY

from bot.logger import logger

# ─── Регистрация шрифта ───────────────────────────────────────────────────────
_CYRILLIC_FONT_PATHS = [
    "/Library/Fonts/Arial Unicode.ttf",          # macOS
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
]
_FONT_NAME = "ArialUnicode"
_FONT_BOLD_NAME = "ArialUnicodeBold"

_font_registered = False
for _path in _CYRILLIC_FONT_PATHS:
    if Path(_path).exists():
        try:
            pdfmetrics.registerFont(TTFont(_FONT_NAME, _path))
            _bold_path = _path.replace(".ttf", " Bold.ttf").replace("Regular", "Bold")
            if Path(_bold_path).exists():
                pdfmetrics.registerFont(TTFont(_FONT_BOLD_NAME, _bold_path))
            else:
                _FONT_BOLD_NAME = _FONT_NAME
            _font_registered = True
            logger.debug("PDF: registered font from {}", _path)
            break
        except Exception as e:
            logger.warning("PDF: failed to load font {}: {}", _path, e)

if not _font_registered:
    _FONT_NAME = "Helvetica"
    _FONT_BOLD_NAME = "Helvetica-Bold"

ASSETS_DIR = Path(__file__).parent / "assets"
LOGO_PATH = ASSETS_DIR / "image1.png"
FOOTER_PATH = ASSETS_DIR / "image2.png"

# ─── Стили ───────────────────────────────────────────────────────────────────
def _styles() -> dict:
    return {
        "header": ParagraphStyle(
            "header",
            fontName=_FONT_BOLD_NAME,
            fontSize=11,
            alignment=TA_RIGHT,
            leading=14,
            spaceAfter=2,
        ),
        "title": ParagraphStyle(
            "title",
            fontName=_FONT_BOLD_NAME,
            fontSize=12,
            alignment=TA_CENTER,
            spaceBefore=20,
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            fontName=_FONT_NAME,
            fontSize=11,
            alignment=TA_CENTER,
            spaceAfter=14,
            fontStyle="italic"
        ),
        "section_title": ParagraphStyle(
            "section_title",
            fontName=_FONT_BOLD_NAME,
            fontSize=11,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body",
            fontName=_FONT_NAME,
            fontSize=11,
            alignment=TA_JUSTIFY,
            leading=15,
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

def draw_background(canvas, doc):
    """Рисует логотип сверху и пунктирный фон с текстом снизу на каждой странице."""
    width, height = A4
    canvas.saveState()
    
    # Логотип (image1.png) - сверху по центру
    if LOGO_PATH.exists():
        logo_w, logo_h = 220, 80
        canvas.drawImage(str(LOGO_PATH), (width - logo_w)/2, height - logo_h - 20, width=logo_w, height=logo_h, preserveAspectRatio=True, anchor='c', mask='auto')

    # Пунктирный фон снизу (image2.png)
    if FOOTER_PATH.exists():
        footer_h = 100
        canvas.drawImage(str(FOOTER_PATH), 0, 0, width=width, height=footer_h, preserveAspectRatio=False, mask='auto')

    # Текст поверх нижнего колонтитула
    s = _styles()
    footer_p = Paragraph("ADDRESS: АСТАНА, ADP OFFICES А, УЛ. СЫГАНАК 60/4, ЭТАЖ 11, ОФИС 1104; E-MAIL: SALEM@AKASHI.CLOUD", s["footer_text"])
    footer_p.wrap(width - 4*cm, 50)
    footer_p.drawOn(canvas, 2*cm, 2.5*cm)
    
    canvas.restoreState()


# ─── Генерация ────────────────────────────────────────────────────────────────
async def generate_pdf(data: dict) -> BytesIO:
    """Генерирует PDF служебной записки."""
    try:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=3 * cm,
            rightMargin=2.5 * cm,
            topMargin=4.5 * cm, # Отступ под логотип
            bottomMargin=3.5 * cm, # Отступ под футер
        )

        s = _styles()
        story = []

        # ── Шапка ──
        story.append(Paragraph("Членам Правления", s["header"]))
        story.append(Paragraph("ПК «AKASHI Data Center PLC»", s["header"]))

        # ── Заголовок ──
        story.append(Paragraph("СЛУЖЕБНАЯ ЗАПИСКА", s["title"]))
        topic = data.get("topic", "")
        story.append(Paragraph(f"по вопросу «{topic}»", s["subtitle"]))

        # ── Блоки ──
        risks_raw = data.get("risks", "")
        risks_text = "(не применимо)" if risks_raw.lower().strip() == "не применимо" else risks_raw

        sections = [
            ("1. Краткое описание и суть вопроса:", data.get("description", "")),
            ("2. Основание для вынесения:", data.get("basis", "")),
            ("3. Предлагаемое решение / варианты решений:", data.get("solution", "")),
            ("4. Риски и последствия (если актуально):", risks_text),
        ]
        
        for title, body in sections:
            story.append(Paragraph(title, s["section_title"]))
            for line in (body or "").split("\n"):
                line = line.strip()
                if line:
                    story.append(Paragraph(line, s["body"]))

        # ── Приложения ──
        story.append(Paragraph("5. Приложения / дополнительные материалы:", s["section_title"]))
        attachments: list = data.get("attachments", [])
        if attachments:
            items = [ListItem(Paragraph(name, s["body"]), leftIndent=20) for name in attachments]
            story.append(ListFlowable(items, bulletType="bullet", start="*"))
        else:
            story.append(Paragraph("(приложения не прикреплены)", s["body"]))

        # ── Подвал (подпись) ──
        story.append(Spacer(1, 40))
        username = data.get("username", "")
        date = data.get("date", "")
        
        story.append(Paragraph("<b>Руководитель подразделения:</b>", s["body"]))
        story.append(Paragraph(f"________________ /{username}/", s["body"]))
        story.append(Paragraph(f"<b>Дата:</b> {date}", s["body"]))

        doc.build(story, onFirstPage=draw_background, onLaterPages=draw_background)
        buffer.seek(0)
        logger.info("PDF generated for app_id={}", data.get("app_id"))
        return buffer

    except Exception as e:
        logger.error("PDF generation failed for app_id={}: {}", data.get("app_id"), e)
        raise
