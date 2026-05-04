"""Загрузка и скачивание вложений через S3."""

from __future__ import annotations

import io

import stdlib.s3 as s3
from stdlib.models import ApplicationAttachment


async def upload_attachment(
    user_id: int,
    app_id: int,
    file_bytes: bytes,
    filename: str,
    content_type: str = "application/octet-stream",
) -> ApplicationAttachment:
    """Загружает файл в бакет вложений и возвращает метаданные."""
    key = s3.attachment_key(user_id, app_id, filename)
    await s3.upload_bytes(file_bytes, key, s3.BUCKET_ATTACHMENTS, content_type)
    return ApplicationAttachment(name=filename, s3_key=key)


async def download_attachment(key: str) -> bytes | None:
    """Скачивает объект по ключу из бакета вложений."""
    return await s3.download_bytes(key, s3.BUCKET_ATTACHMENTS)


async def download_attachment_bytesio(key: str) -> io.BytesIO | None:
    """Как `download_attachment`, но сразу `BytesIO` (для HTTP-ответов)."""
    return await s3.download_to_bytesio(key, s3.BUCKET_ATTACHMENTS)


async def upload_signature_image(
    user_id: int, image_bytes: bytes, content_type: str = "image/png"
) -> str:
    """Загружает изображение подписи в бакет подписей; возвращает S3-ключ."""
    key = s3.signature_key(user_id)
    await s3.upload_bytes(
        image_bytes, key, s3.BUCKET_SIGNATURES, content_type=content_type
    )
    return key
