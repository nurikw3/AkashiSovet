import json
import aiosqlite
from bot.config import config
from bot.logger import logger

DB_PATH = config.DB_PATH

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS applications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    username      TEXT,
    status        TEXT    DEFAULT 'draft',
    blocks        TEXT    DEFAULT '{}',
    attachments   TEXT    DEFAULT '[]',
    feedback      TEXT,
    pdf_file_id   TEXT,
    chat_history  TEXT    DEFAULT '[]',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS llm_cache (
    prompt_hash TEXT PRIMARY KEY,
    response    TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    full_name   TEXT,
    mode        TEXT DEFAULT 'step'
);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLE)

        # Миграции
        try:
            await db.execute("ALTER TABLE users ADD COLUMN mode TEXT DEFAULT 'step'")
        except aiosqlite.OperationalError:
            pass

        try:
            await db.execute(
                "ALTER TABLE applications ADD COLUMN chat_history TEXT DEFAULT '[]'"
            )
        except aiosqlite.OperationalError:
            pass

        await db.commit()
    logger.info("Database initialized: {}", DB_PATH)


async def get_or_create_app(user_id: int, username: str | None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id FROM applications WHERE user_id = ? AND status = 'draft' ORDER BY id DESC LIMIT 1",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()

        if row:
            app_id = row["id"]
            logger.debug("Existing draft app {} for user {}", app_id, user_id)
            return app_id

        async with db.execute(
            "INSERT INTO applications (user_id, username) VALUES (?, ?)",
            (user_id, username),
        ) as cur:
            app_id = cur.lastrowid
        await db.commit()
        logger.info("Created new app {} for user {}", app_id, user_id)
        return app_id


async def get_app(app_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM applications WHERE id = ?", (app_id,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def save_block(app_id: int, block_num: int | str, text: str) -> None:
    app = await get_app(app_id)
    blocks = json.loads(app["blocks"])
    blocks[str(block_num)] = text
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE applications SET blocks = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(blocks, ensure_ascii=False), app_id),
        )
        await db.commit()
    logger.debug("Saved block {} for app {}", block_num, app_id)


async def save_attachments(app_id: int, attachments: list) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE applications SET attachments = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(attachments, ensure_ascii=False), app_id),
        )
        await db.commit()
    logger.debug("Saved {} attachments for app {}", len(attachments), app_id)


async def update_status(
    app_id: int,
    status: str,
    feedback: str | None = None,
    pdf_file_id: str | None = None,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE applications
               SET status = ?,
                   feedback = COALESCE(?, feedback),
                   pdf_file_id = COALESCE(?, pdf_file_id),
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (status, feedback, pdf_file_id, app_id),
        )
        await db.commit()
    logger.info("App {} status → {}", app_id, status)


async def get_pending_apps() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM applications WHERE status = 'pending' ORDER BY created_at"
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_last_rework_app(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM applications WHERE user_id = ? AND status = 'rework' ORDER BY id DESC LIMIT 1",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_cached_llm_response(prompt_hash: str) -> str | None:
    """Возвращает кэшированный ответ LLM, если он существует."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT response FROM llm_cache WHERE prompt_hash = ?", (prompt_hash,)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else None


async def save_llm_response_to_cache(prompt_hash: str, response: str) -> None:
    """Сохраняет ответ LLM в кэш."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO llm_cache (prompt_hash, response) VALUES (?, ?)",
            (prompt_hash, response),
        )
        await db.commit()
    logger.debug("Saved LLM response to cache | hash={}", prompt_hash)


async def set_user_full_name(user_id: int, full_name: str) -> None:
    """Сохраняет ФИО пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO users (user_id, full_name) VALUES (?, ?)",
            (user_id, full_name),
        )
        await db.commit()


async def get_user_full_name(user_id: int) -> str | None:
    """Возвращает ФИО пользователя, если есть."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT full_name FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def get_user_mode(user_id: int) -> str:
    """Возвращает режим пользователя ('step' или 'free')."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT mode FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row and len(row) > 0 and row[0] else "step"


async def set_user_mode(user_id: int, mode: str) -> None:
    """Устанавливает режим пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET mode = ? WHERE user_id = ?", (mode, user_id))
        await db.commit()


async def get_chat_history(app_id: int) -> list:
    app = await get_app(app_id)
    if not app or not app.get("chat_history"):
        return []
    return json.loads(app["chat_history"])


async def save_chat_history(app_id: int, history: list) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE applications SET chat_history = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(history, ensure_ascii=False), app_id),
        )
        await db.commit()


async def save_all_blocks(app_id: int, blocks: dict) -> None:
    """Сохраняет сразу все блоки (используется во free-form режиме)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE applications SET blocks = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(blocks, ensure_ascii=False), app_id),
        )
        await db.commit()
