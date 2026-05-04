"""
Async S3-клиент для MinIO через aiobotocore.
Структура ключей:
  attachments/{user_id}/{app_id}/{filename}
  pdf/{user_id}/{app_id}.pdf
  signatures/{user_id}/signature.png
"""

import io
from contextlib import asynccontextmanager
from pathlib import PurePosixPath

import aiobotocore.session
from botocore.config import Config
from botocore.exceptions import ClientError

from bot.config import config
from bot.logger import logger

_s3_session: aiobotocore.session.AioSession | None = None

BUCKET_ATTACHMENTS = "attachments"
BUCKET_PDF = "pdf-documents"
BUCKET_SIGNATURES = "signatures"

# Явные таймауты: без них aiobotocore может долго «висеть» на медленном MinIO/сети.
_S3_BOTOCORE_CONFIG = Config(
    connect_timeout=10,
    read_timeout=120,
    retries={"max_attempts": 5, "mode": "standard"},
)


def get_s3_session() -> aiobotocore.session.AioSession:
    """Общая сессия aiobotocore; создаётся при первом обращении или после `reset_s3_session`."""
    global _s3_session
    if _s3_session is None:
        _s3_session = aiobotocore.session.get_session()
    return _s3_session


def reset_s3_session() -> None:
    """Сброс сессии при остановке приложения (клиенты S3 при этом контекстные — см. `_s3_client`)."""
    global _s3_session
    _s3_session = None


def _s3_configured() -> bool:
    return bool(
        config.S3_ENDPOINT_URL and config.S3_ACCESS_KEY and config.S3_SECRET_KEY
    )


def is_s3_configured() -> bool:
    """Публичная проверка: можно ли загружать вложения в объектное хранилище."""
    return _s3_configured()


@asynccontextmanager
async def _s3_client():
    if not _s3_configured():
        raise RuntimeError("S3 is not configured (set S3_ENDPOINT_URL, S3_ACCESS_KEY, S3_SECRET_KEY)")
    async with get_s3_session().create_client(
        "s3",
        endpoint_url=config.S3_ENDPOINT_URL,
        aws_access_key_id=config.S3_ACCESS_KEY,
        aws_secret_access_key=config.S3_SECRET_KEY,
        region_name="us-east-1",
        config=_S3_BOTOCORE_CONFIG,
    ) as client:
        yield client


# ── Ключи ─────────────────────────────────────────────────────────────────────
def pdf_key(user_id: int, app_id: int) -> str:
    return f"pdf/{user_id}/{app_id}.pdf"


def attachment_key(user_id: int, app_id: int, filename: str) -> str:
    safe = PurePosixPath(filename).name
    return f"attachments/{user_id}/{app_id}/{safe}"


def is_allowed_attachment_download_key(key: str) -> bool:
    """Разрешённые ключи для скачивания вложений из панели (без выхода за префикс)."""
    if not key or not isinstance(key, str):
        return False
    if ".." in key or key.startswith("/"):
        return False
    parts = PurePosixPath(key).parts
    if len(parts) < 4 or parts[0] != "attachments":
        return False
    try:
        int(parts[1])
        int(parts[2])
    except ValueError:
        return False
    if any(p in ("", ".", "..") for p in parts):
        return False
    return True


def signature_key(user_id: int) -> str:
    return f"signatures/{user_id}/signature.png"


def _user_pdf_prefix(user_id: int) -> str:
    return f"pdf/{user_id}/"


def _user_attachments_prefix(user_id: int) -> str:
    return f"attachments/{user_id}/"


def _app_attachments_prefix(user_id: int, app_id: int) -> str:
    return f"attachments/{user_id}/{app_id}/"


# ── Инициализация ─────────────────────────────────────────────────────────────
async def ensure_buckets() -> None:
    """Создаёт бакеты если их нет. Вызвать в lifespan."""
    if not _s3_configured():
        logger.warning(
            "S3 skipped: set S3_ENDPOINT_URL, S3_ACCESS_KEY, S3_SECRET_KEY (e.g. in .env or compose)"
        )
        return
    async with _s3_client() as s3:
        for bucket in (BUCKET_ATTACHMENTS, BUCKET_PDF, BUCKET_SIGNATURES):
            try:
                await s3.head_bucket(Bucket=bucket)
            except ClientError:
                await s3.create_bucket(Bucket=bucket)
                logger.info("S3: bucket '{}' created", bucket)


# ── Upload ────────────────────────────────────────────────────────────────────
async def upload_bytes(
    data: bytes,
    key: str,
    bucket: str,
    content_type: str = "application/octet-stream",
) -> str:
    async with _s3_client() as s3:
        await s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
    logger.debug("S3 upload: bucket={} key={} size={}b", bucket, key, len(data))
    return key


# ── Download ──────────────────────────────────────────────────────────────────
async def download_bytes(key: str, bucket: str) -> bytes | None:
    async with _s3_client() as s3:
        try:
            resp = await s3.get_object(Bucket=bucket, Key=key)
            async with resp["Body"] as stream:
                return await stream.read()
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None
            raise


async def download_to_bytesio(key: str, bucket: str) -> io.BytesIO | None:
    data = await download_bytes(key, bucket)
    return io.BytesIO(data) if data is not None else None


# ── Delete ────────────────────────────────────────────────────────────────────
async def delete_object(key: str, bucket: str) -> None:
    async with _s3_client() as s3:
        await s3.delete_object(Bucket=bucket, Key=key)


async def _delete_by_prefix(prefix: str, bucket: str) -> None:
    async with _s3_client() as s3:
        paginator = s3.get_paginator("list_objects_v2")
        async for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if objects:
                await s3.delete_objects(Bucket=bucket, Delete={"Objects": objects})


async def delete_app_files(user_id: int, app_id: int) -> None:
    await _delete_by_prefix(
        _app_attachments_prefix(user_id, app_id), BUCKET_ATTACHMENTS
    )
    await delete_object(pdf_key(user_id, app_id), BUCKET_PDF)
    logger.info("S3: deleted all files for user_id={} app_id={}", user_id, app_id)


async def delete_user_files(user_id: int) -> None:
    await _delete_by_prefix(_user_pdf_prefix(user_id), BUCKET_PDF)
    await _delete_by_prefix(_user_attachments_prefix(user_id), BUCKET_ATTACHMENTS)
    await delete_object(signature_key(user_id), BUCKET_SIGNATURES)
    logger.info("S3: deleted ALL files for user_id={}", user_id)


# ── List ──────────────────────────────────────────────────────────────────────
async def _list_keys(prefix: str, bucket: str) -> list[str]:
    keys = []
    async with _s3_client() as s3:
        paginator = s3.get_paginator("list_objects_v2")
        async for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
    return keys


async def list_user_pdfs(user_id: int) -> list[str]:
    return await _list_keys(_user_pdf_prefix(user_id), BUCKET_PDF)


async def list_app_attachments(user_id: int, app_id: int) -> list[str]:
    return await _list_keys(
        _app_attachments_prefix(user_id, app_id), BUCKET_ATTACHMENTS
    )
