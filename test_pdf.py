from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from pathlib import Path
import os

ASSETS_DIR = Path("/Users/nurasyk/Desktop/python/projects/AkashiSovet/stdlib/assets")
logo_path = ASSETS_DIR / "image1.png"
footer_path = ASSETS_DIR / "image2.png"

c = canvas.Canvas("/Users/nurasyk/Desktop/python/projects/AkashiSovet/test.pdf", pagesize=A4)
width, height = A4

# draw logo top center
logo_w, logo_h = 200, 80 # approximate
c.drawImage(str(logo_path), (width - logo_w)/2, height - logo_h - 20, width=logo_w, height=logo_h, preserveAspectRatio=True, anchor='c')

# draw footer background bottom
footer_h = 100
c.drawImage(str(footer_path), 0, 0, width=width, height=footer_h, preserveAspectRatio=False)

c.showPage()
c.save()
print("test.pdf generated")
