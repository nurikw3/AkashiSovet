#!/usr/bin/env python3
"""One-shot: embed image2_updated.png into board_memo_template.docx (word/media/image2.png)."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "stdlib" / "assets"
TEMPLATE_PATH = ASSETS / "board_memo_template.docx"
FOOTER_IMAGE_PATH = ASSETS / "image2_updated.png"
FOOTER_MEDIA = "word/media/image2.png"


def bake_footer(*, force: bool = False) -> bool:
    if not FOOTER_IMAGE_PATH.exists():
        print(f"Footer image missing: {FOOTER_IMAGE_PATH}", file=sys.stderr)
        return False
    if not TEMPLATE_PATH.exists():
        print(f"Template missing: {TEMPLATE_PATH}", file=sys.stderr)
        return False

    footer_bytes = FOOTER_IMAGE_PATH.read_bytes()
    with ZipFile(TEMPLATE_PATH, "r") as zin:
        try:
            current = zin.read(FOOTER_MEDIA)
        except KeyError:
            current = b""
        if not force and current == footer_bytes:
            print("Template footer already up to date.")
            return True
        buf = io.BytesIO()
        with ZipFile(buf, "w", ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == FOOTER_MEDIA:
                    data = footer_bytes
                zout.writestr(item, data)
    TEMPLATE_PATH.write_bytes(buf.getvalue())
    print(f"Baked footer into {TEMPLATE_PATH.name} ({len(footer_bytes)} bytes)")
    return True


if __name__ == "__main__":
    ok = bake_footer(force="--force" in sys.argv)
    raise SystemExit(0 if ok else 1)
