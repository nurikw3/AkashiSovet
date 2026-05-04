-- Phase 3, step 5+: дата и время заседания вместо только даты.

ALTER TABLE meetings
    ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMP;

UPDATE meetings
SET scheduled_at = COALESCE(scheduled_at, scheduled_date::timestamp);

ALTER TABLE meetings
    ALTER COLUMN scheduled_at SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_meetings_scheduled_at ON meetings (scheduled_at);

ALTER TABLE meetings
    DROP COLUMN IF EXISTS scheduled_date;
