-- Phase 3, step 1: заседания Правления и список включённых заявок (корзина).

CREATE TABLE IF NOT EXISTS meetings (
    id               SERIAL PRIMARY KEY,
    scheduled_date   DATE NOT NULL,
    created_by       BIGINT NOT NULL,
    created_at       TIMESTAMP DEFAULT NOW(),
    application_ids  JSONB NOT NULL DEFAULT '[]'::jsonb
);
