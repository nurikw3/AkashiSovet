-- scheduled_at: хранение момента времени в UTC (TIMESTAMPTZ).
-- Старые значения без часового пояса интерпретируем как локальное время Астаны (Asia/Almaty, UTC+5).

ALTER TABLE meetings
    ALTER COLUMN scheduled_at TYPE TIMESTAMPTZ
    USING (scheduled_at AT TIME ZONE 'Asia/Almaty');
