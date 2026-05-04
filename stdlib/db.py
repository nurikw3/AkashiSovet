import json
import asyncpg
from bot.config import config
from bot.logger import logger
from datetime import date, datetime, timezone
import random
import string
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_pool: asyncpg.Pool | None = None


async def init_db() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        config.DATABASE_URL,
        min_size=config.DB_POOL_MIN_SIZE,
        max_size=config.DB_POOL_MAX_SIZE,
    )

    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id            SERIAL PRIMARY KEY,
                user_id       BIGINT NOT NULL,
                username      TEXT,
                status        TEXT    DEFAULT 'draft',
                blocks        TEXT    DEFAULT '{}',
                attachments   TEXT    DEFAULT '[]',
                feedback      TEXT,
                pdf_file_id   TEXT,
                chat_history  TEXT    DEFAULT '[]',
                t_start       TIMESTAMPTZ,
                t_submit      TIMESTAMPTZ,
                t_decision    TIMESTAMPTZ,
                reject_count  INTEGER DEFAULT 0,
                created_at    TIMESTAMPTZ DEFAULT NOW(),
                updated_at    TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id     BIGINT PRIMARY KEY,
                full_name   TEXT,
                position    TEXT,
                signature_data TEXT,
                mode        TEXT DEFAULT 'step',
                login       TEXT UNIQUE,
                hashed_password TEXT
            );
        """)
    logger.info("Database initialized: {}", config.DATABASE_URL)


async def close_db() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Публичный доступ к пулу (инициализация через `stdlib.resources.init_resources`)."""
    if not _pool:
        raise RuntimeError("DB pool not initialized. Call init_db() first.")
    return _pool


def _pool_conn():
    if not _pool:
        raise RuntimeError("DB pool not initialized. Call init_db() first.")
    return _pool.acquire()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── Settings ────────────────────────────────────────────────────────────────


async def get_setting(key: str):
    """Возвращает JSONB-значение из таблицы `settings` или None, если ключа нет."""
    async with _pool_conn() as conn:
        row = await conn.fetchrow("SELECT value FROM settings WHERE key = $1", key)
    if not row:
        return None
    return row["value"]


async def upsert_setting(key: str, value: dict | list) -> None:
    """Вставка или обновление JSONB по ключу."""
    payload = json.dumps(value, ensure_ascii=False)
    async with _pool_conn() as conn:
        await conn.execute(
            """
            INSERT INTO settings (key, value)
            VALUES ($1, $2::jsonb)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            key,
            payload,
        )


# ─── Applications ─────────────────────────────────────────────────────────────


async def get_or_create_app(user_id: int, username: str | None) -> int:
    async with _pool_conn() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM applications WHERE user_id = $1 AND status = 'draft' ORDER BY id DESC LIMIT 1",
            user_id,
        )
        if row:
            logger.debug("Existing draft app {} for user {}", row["id"], user_id)
            return row["id"]

        row = await conn.fetchrow(
            "INSERT INTO applications (user_id, username) VALUES ($1, $2) RETURNING id",
            user_id,
            username,
        )
        logger.info("Created new app {} for user {}", row["id"], user_id)
        return row["id"]


async def reset_draft_content(app_id: int) -> None:
    """
    Сбрасывает блоки, вложения и free-form чат у черновика.
    Нужен при новом /start, чтобы не тянуть контекст прошлой сессии (другой режим / free-form).
    """
    async with _pool_conn() as conn:
        await conn.execute(
            """UPDATE applications
               SET blocks = '{}',
                   attachments = '[]',
                   chat_history = '[]',
                   updated_at = NOW()
               WHERE id = $1 AND status = 'draft'""",
            app_id,
        )
    logger.debug("reset_draft_content app_id={}", app_id)


async def get_app(app_id: int) -> dict | None:
    async with _pool_conn() as conn:
        row = await conn.fetchrow("SELECT * FROM applications WHERE id = $1", app_id)
    return dict(row) if row else None


async def save_block(app_id: int, block_num: int | str, text: str) -> None:
    app = await get_app(app_id)
    blocks = json.loads(app["blocks"])
    blocks[str(block_num)] = text
    async with _pool_conn() as conn:
        await conn.execute(
            "UPDATE applications SET blocks = $1, updated_at = NOW() WHERE id = $2",
            json.dumps(blocks, ensure_ascii=False),
            app_id,
        )
    logger.debug("Saved block {} for app {}", block_num, app_id)


async def save_attachments(app_id: int, attachments: list) -> None:
    async with _pool_conn() as conn:
        await conn.execute(
            "UPDATE applications SET attachments = $1, updated_at = NOW() WHERE id = $2",
            json.dumps(attachments, ensure_ascii=False),
            app_id,
        )
    logger.debug("Saved {} attachments for app {}", len(attachments), app_id)


async def update_status(
    app_id: int,
    status: str,
    feedback: str | None = None,
    pdf_file_id: str | None = None,
) -> None:
    async with _pool_conn() as conn:
        await conn.execute(
            """UPDATE applications
               SET status = $1,
                   feedback = COALESCE($2, feedback),
                   pdf_file_id = COALESCE($3, pdf_file_id),
                   updated_at = NOW()
               WHERE id = $4""",
            status,
            feedback,
            pdf_file_id,
            app_id,
        )
    logger.info("App {} status → {}", app_id, status)


async def get_pending_apps() -> list[dict]:
    async with _pool_conn() as conn:
        rows = await conn.fetch(
            "SELECT * FROM applications WHERE status = 'pending' ORDER BY created_at"
        )
    return [dict(r) for r in rows]


async def get_last_rework_app(user_id: int) -> dict | None:
    async with _pool_conn() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM applications WHERE user_id = $1 AND status = 'rework' ORDER BY id DESC LIMIT 1",
            user_id,
        )
    return dict(row) if row else None


async def save_all_blocks(app_id: int, blocks: dict) -> None:
    async with _pool_conn() as conn:
        await conn.execute(
            "UPDATE applications SET blocks = $1, updated_at = NOW() WHERE id = $2",
            json.dumps(blocks, ensure_ascii=False),
            app_id,
        )


# ─── Telemetry ────────────────────────────────────────────────────────────────


async def set_t_start(app_id: int) -> None:
    async with _pool_conn() as conn:
        await conn.execute(
            "UPDATE applications SET t_start = $1 WHERE id = $2 AND t_start IS NULL",
            _now(),
            app_id,
        )


async def set_t_submit(app_id: int) -> None:
    async with _pool_conn() as conn:
        await conn.execute(
            "UPDATE applications SET t_submit = $1 WHERE id = $2",
            _now(),
            app_id,
        )


async def set_t_decision(app_id: int) -> None:
    async with _pool_conn() as conn:
        await conn.execute(
            "UPDATE applications SET t_decision = $1 WHERE id = $2",
            _now(),
            app_id,
        )


async def increment_reject_count(app_id: int) -> None:
    async with _pool_conn() as conn:
        await conn.execute(
            "UPDATE applications SET reject_count = reject_count + 1 WHERE id = $1",
            app_id,
        )


# ─── Users ────────────────────────────────────────────────────────────────────


async def set_user_full_name(user_id: int, full_name: str) -> None:
    async with _pool_conn() as conn:
        await conn.execute(
            """INSERT INTO users (user_id, full_name)
               VALUES ($1, $2)
               ON CONFLICT (user_id) DO UPDATE SET full_name = EXCLUDED.full_name""",
            user_id,
            full_name,
        )


async def get_user_full_name(user_id: int) -> str | None:
    async with _pool_conn() as conn:
        row = await conn.fetchrow(
            "SELECT full_name FROM users WHERE user_id = $1", user_id
        )
    return row["full_name"] if row else None


async def get_user_mode(user_id: int) -> str:
    async with _pool_conn() as conn:
        row = await conn.fetchrow("SELECT mode FROM users WHERE user_id = $1", user_id)
    return row["mode"] if row and row["mode"] else "step"


async def set_user_mode(user_id: int, mode: str) -> None:
    async with _pool_conn() as conn:
        await conn.execute(
            "UPDATE users SET mode = $1 WHERE user_id = $2", mode, user_id
        )


# ─── Chat History ─────────────────────────────────────────────────────────────


async def get_chat_history(app_id: int) -> list:
    app = await get_app(app_id)
    if not app or not app.get("chat_history"):
        return []
    return json.loads(app["chat_history"])


async def save_chat_history(app_id: int, history: list) -> None:
    async with _pool_conn() as conn:
        await conn.execute(
            "UPDATE applications SET chat_history = $1, updated_at = NOW() WHERE id = $2",
            json.dumps(history, ensure_ascii=False),
            app_id,
        )


async def clear_chat_history(app_id: int) -> None:
    """Сбрасывает free-form / LLM-историю по заявке (при /start, смене режима)."""
    await save_chat_history(app_id, [])


async def get_draft_id_for_user(user_id: int) -> int | None:
    async with _pool_conn() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM applications WHERE user_id = $1 AND status = 'draft' ORDER BY id DESC LIMIT 1",
            user_id,
        )
    return row["id"] if row else None


async def delete_app(app_id: int) -> None:
    async with _pool_conn() as conn:
        await conn.execute("DELETE FROM applications WHERE id = $1", app_id)
        logger.info("Deleted app {}", app_id)


# ─── Positions ────────────────────────────────────────────────────────────────


async def get_user_position(user_id: int) -> str | None:
    async with _pool_conn() as conn:
        row = await conn.fetchrow(
            "SELECT position FROM users WHERE user_id = $1", user_id
        )
    return row["position"] if row and row["position"] else None


async def set_user_position(user_id: int, position: str) -> None:
    async with _pool_conn() as conn:
        await conn.execute(
            """INSERT INTO users (user_id, position)
               VALUES ($1, $2)
               ON CONFLICT (user_id) DO UPDATE SET position = EXCLUDED.position""",
            user_id,
            position,
        )


# ─── Signatures ───────────────────────────────────────────────────────────────


async def set_user_signature(user_id: int, s3_key: str) -> None:  # ← принимаем str
    async with _pool_conn() as conn:
        await conn.execute(
            """INSERT INTO users (user_id, signature_data)
               VALUES ($1, $2)
               ON CONFLICT (user_id) DO UPDATE SET signature_data = EXCLUDED.signature_data""",
            user_id,
            s3_key,  # ← сохраняем ключ строкой
        )


# Функция get_user_signature:
async def get_user_signature(user_id: int) -> str | None:  # ← возвращаем str
    async with _pool_conn() as conn:
        row = await conn.fetchrow(
            "SELECT signature_data FROM users WHERE user_id = $1", user_id
        )
    return row["signature_data"] if row and row["signature_data"] else None


async def get_daily_stats() -> dict:
    """Агрегаты по заявкам (четыре статуса: draft, pending, rework, approved)."""
    query = """
        SELECT
            COUNT(*) FILTER (WHERE status = 'pending')::bigint AS pending,
            COUNT(*) FILTER (WHERE status = 'draft')::bigint AS draft,
            COUNT(*) FILTER (WHERE status = 'rework')::bigint AS rework,
            COUNT(*) FILTER (WHERE status = 'approved')::bigint AS approved
        FROM applications
    """
    async with _pool_conn() as conn:
        row = await conn.fetchrow(query)

    return {
        "pending": int(row["pending"] or 0),
        "draft": int(row["draft"] or 0),
        "rework": int(row["rework"] or 0),
        "approved": int(row["approved"] or 0),
    }


async def generate_web_login_code(user_id: int) -> str:
    """Генерирует 6-значный код и сохраняет его в колонку mode (как временный буфер)."""
    code = "".join(random.choices(string.digits, k=6))
    async with _pool_conn() as conn:
        await conn.execute(
            """INSERT INTO users (user_id, mode)
               VALUES ($1, $2)
               ON CONFLICT (user_id) DO UPDATE SET mode = EXCLUDED.mode""",
            user_id,
            f"otp_{code}",
        )
    return code


async def verify_web_login_code(user_id: int, input_code: str) -> bool:
    """Проверяет код и сбрасывает его."""
    async with _pool_conn() as conn:
        current_mode = await conn.fetchval(
            "SELECT mode FROM users WHERE user_id = $1", user_id
        )
        if current_mode == f"otp_{input_code}":
            await conn.execute(
                "UPDATE users SET mode = 'step' WHERE user_id = $1", user_id
            )
            return True
    return False


async def get_application_status_counts() -> dict[str, int]:
    """Агрегаты по заявкам: pending, approved, rework и всего строк (для виджетов панели)."""
    async with _pool_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'pending')::int  AS pending,
                COUNT(*) FILTER (WHERE status = 'approved')::int AS approved,
                COUNT(*) FILTER (WHERE status = 'rework')::int   AS rework,
                COUNT(*)::int                                   AS total
            FROM applications
            """
        )
    if row is None:
        return {"pending": 0, "approved": 0, "rework": 0, "total": 0}
    return {
        "pending": row["pending"],
        "approved": row["approved"],
        "rework": row["rework"],
        "total": row["total"],
    }


async def get_applications(status: str | None = None) -> list[dict]:
    """Список заявок для веб-таблицы. Без фильтра — все статусы; иначе один из четырёх."""
    allowed = frozenset({"draft", "pending", "rework", "approved"})
    async with _pool_conn() as conn:
        if status in allowed:
            rows = await conn.fetch(
                """
                SELECT a.*, u.full_name, u.position
                FROM applications a
                LEFT JOIN users u ON a.user_id = u.user_id
                WHERE a.status = $1
                ORDER BY a.created_at DESC
                """,
                status,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT a.*, u.full_name, u.position
                FROM applications a
                LEFT JOIN users u ON a.user_id = u.user_id
                ORDER BY a.created_at DESC
                """
            )
    return [dict(r) for r in rows]


async def get_application_status_by_ids(ids: list[int]) -> dict[int, str]:
    """id заявки → status (только для существующих id из списка)."""
    if not ids:
        return {}
    async with _pool_conn() as conn:
        rows = await conn.fetch(
            "SELECT id, status FROM applications WHERE id = ANY($1::int[])",
            ids,
        )
    return {r["id"]: r["status"] for r in rows}


async def get_applications_by_ids(ids: list[int]) -> list[dict]:
    """Заявки с JOIN к users, порядок как в `ids` (пропуск отсутствующих id)."""
    if not ids:
        return []
    async with _pool_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT a.*, u.full_name, u.position
            FROM applications a
            LEFT JOIN users u ON a.user_id = u.user_id
            WHERE a.id = ANY($1::int[])
            """,
            ids,
        )
    by_id = {r["id"]: dict(r) for r in rows}
    return [by_id[i] for i in ids if i in by_id]


# ─── Meetings (таблица `meetings`) ───────────────────────────────────────────


async def insert_meeting(scheduled_at: datetime, created_by: int) -> dict:
    """Создаёт заседание; возвращает строку как dict (RETURNING *)."""
    async with _pool_conn() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO meetings (scheduled_at, created_by)
            VALUES ($1::timestamptz, $2)
            RETURNING id, scheduled_at, created_by, created_at, application_ids
            """,
            scheduled_at,
            created_by,
        )
    if not row:
        raise RuntimeError("insert_meeting: INSERT returned no row")
    return dict(row)


async def list_meetings_upcoming() -> list[dict]:
    """Заседания в будущем (или «сейчас»), ближайшие первыми."""
    async with _pool_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT id, scheduled_at, created_by, created_at, application_ids
            FROM meetings
            WHERE scheduled_at >= NOW()
            ORDER BY scheduled_at ASC, id ASC
            """
        )
    return [dict(r) for r in rows]


async def list_meetings_past() -> list[dict]:
    """Прошедшие заседания, от новых к старым."""
    async with _pool_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT id, scheduled_at, created_by, created_at, application_ids
            FROM meetings
            WHERE scheduled_at < NOW()
            ORDER BY scheduled_at DESC, id DESC
            """
        )
    return [dict(r) for r in rows]


async def get_meeting_by_id(meeting_id: int) -> dict | None:
    """Одна запись `meetings` по id."""
    async with _pool_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, scheduled_at, created_by, created_at, application_ids
            FROM meetings
            WHERE id = $1
            """,
            meeting_id,
        )
    return dict(row) if row else None


async def update_meeting_scheduled_at(meeting_id: int, scheduled_at: datetime) -> bool:
    """Обновляет дату/время заседания. Возвращает True, если строка была найдена."""
    async with _pool_conn() as conn:
        row = await conn.fetchrow(
            """
            UPDATE meetings
            SET scheduled_at = $2::timestamptz
            WHERE id = $1
            RETURNING id
            """,
            meeting_id,
            scheduled_at,
        )
    return row is not None


async def delete_meeting_by_id(meeting_id: int) -> bool:
    """Удаляет заседание по id. Возвращает True, если строка была удалена."""
    async with _pool_conn() as conn:
        row = await conn.fetchrow(
            "DELETE FROM meetings WHERE id = $1 RETURNING id", meeting_id
        )
    return row is not None


def _parse_application_ids_jsonb(v) -> list[int]:
    if v is None:
        return []
    if isinstance(v, list):
        return [int(x) for x in v]
    if isinstance(v, str):
        try:
            data = json.loads(v)
        except json.JSONDecodeError:
            return []
        return [int(x) for x in data] if isinstance(data, list) else []
    return []


async def extend_meeting_application_ids(meeting_id: int, app_ids: list[int]) -> None:
    """Добавляет id заявок в JSONB-массив без дубликатов; строка должна существовать."""
    if not app_ids:
        return
    new_ids = [int(x) for x in app_ids]
    async with _pool_conn() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT application_ids FROM meetings WHERE id = $1 FOR UPDATE",
                meeting_id,
            )
            if not row:
                raise ValueError(f"meeting {meeting_id} not found")
            cur = _parse_application_ids_jsonb(row["application_ids"])
            merged = sorted(set(cur + new_ids))
            payload = json.dumps(merged, ensure_ascii=False)
            await conn.execute(
                "UPDATE meetings SET application_ids = $1::jsonb WHERE id = $2",
                payload,
                meeting_id,
            )


import bcrypt


async def update_user_password(user_id: int, password: str):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    async with _pool_conn() as conn:
        await conn.execute(
            "UPDATE users SET hashed_password = $1 WHERE user_id = $2", hashed, user_id
        )


async def get_user_apps(user_id: int) -> list[dict]:
    """Возвращает заявки пользователя как список dict."""
    query = """
        SELECT id, blocks, status, created_at 
        FROM applications 
        WHERE user_id = $1 
        ORDER BY created_at DESC
    """
    async with _pool_conn() as conn:
        rows = await conn.fetch(query, user_id)
    return [dict(row) for row in rows]  # 🔥 Конвертируем Record → dict
