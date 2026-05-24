-- Индексы для дашборда, черновиков и поиска по ФИО.

CREATE INDEX IF NOT EXISTS idx_applications_user_status_id
    ON applications (user_id, status, id DESC);

CREATE INDEX IF NOT EXISTS idx_applications_status_submit
    ON applications (status, t_submit DESC NULLS LAST, updated_at DESC);

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_users_full_name_trgm
    ON users USING gin (full_name gin_trgm_ops);
