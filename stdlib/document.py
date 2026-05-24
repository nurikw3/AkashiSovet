"""Публичный API генерации и доставки документов заявки (DOCX)."""

from stdlib.docx_gen import (
    DOCX_CACHE_KEY_FMT,
    DOCX_CACHE_TTL_SEC,
    generate_docx,
    generate_docx_filename,
    get_app_docx_buffer,
    invalidate_docx_cache,
    invalidate_docx_content_cache,
    invalidate_docx_delivery_cache,
    media_type_for_filename,
    resolve_application_docx_filename,
)

# Обратная совместимость имён (PDF → DOCX)
get_app_pdf_buffer = get_app_docx_buffer
generate_pdf = generate_docx
generate_pdf_filename = generate_docx_filename
resolve_application_pdf_filename = resolve_application_docx_filename
invalidate_pdf_cache = invalidate_docx_cache
invalidate_pdf_content_cache = invalidate_docx_content_cache
invalidate_pdf_delivery_cache = invalidate_docx_delivery_cache
PDF_CACHE_KEY_FMT = DOCX_CACHE_KEY_FMT
PDF_CACHE_TTL_SEC = DOCX_CACHE_TTL_SEC
