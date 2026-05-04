"""Единая инициализация и доступ к asyncpg-пулу, Redis и S3 (aiobotocore session)."""

from __future__ import annotations

import asyncpg
import redis.asyncio as redis
from aiobotocore.session import AioSession

import stdlib.db as db
import stdlib.redis_client as redis_client
import stdlib.s3 as s3


async def init_resources() -> None:
    """Поднимает PostgreSQL, Redis (кэш/служебное) и проверяет бакеты S3."""
    await db.init_db()
    await redis_client.init_redis()
    await s3.ensure_buckets()


async def shutdown_resources() -> None:
    """Закрывает пул БД и Redis; S3 — сброс кэшированной сессии."""
    await db.close_db()
    await redis_client.close_redis()
    s3.reset_s3_session()


def get_db_pool() -> asyncpg.Pool:
    """Пул asyncpg после `init_resources`."""
    return db.get_pool()


def get_redis() -> redis.Redis | None:
    """Клиент Redis из `redis_client` (может быть None, если URL не задан)."""
    return redis_client.redis_client


def get_s3_session() -> AioSession:
    """Сессия aiobotocore для S3; операции по-прежнему через `stdlib.s3` и контекстные клиенты."""
    return s3.get_s3_session()
