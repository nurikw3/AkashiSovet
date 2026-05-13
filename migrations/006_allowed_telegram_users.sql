-- Access control: список Telegram user_id, которым разрешено писать боту.
-- SUPERUSER_IDS по-прежнему берутся из .env и работают независимо от этой таблицы.

CREATE TABLE IF NOT EXISTS allowed_telegram_users (
    user_id     BIGINT PRIMARY KEY,
    added_by    BIGINT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
