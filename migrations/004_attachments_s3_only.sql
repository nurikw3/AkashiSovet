-- Удалить из JSON attachments все вложения без S3 (file_id, только имя и проч.).
-- Остаются только объекты с непустым s3_key; у них дополнительно сбрасывается ключ file_id.
-- Резервная копия: pg_dump -t applications … или SELECT id, attachments FROM applications;

DO $$
DECLARE
  r RECORD;
  elem jsonb;
  new_arr jsonb;
BEGIN
  FOR r IN SELECT id, attachments FROM applications
  LOOP
    BEGIN
      IF r.attachments IS NULL OR trim(r.attachments) = '' OR trim(r.attachments) = '[]' THEN
        CONTINUE;
      END IF;

      new_arr := '[]'::jsonb;

      FOR elem IN SELECT e FROM jsonb_array_elements(r.attachments::jsonb) AS t(e)
      LOOP
        IF jsonb_typeof(elem) = 'object' AND coalesce(trim(elem->>'s3_key'), '') <> '' THEN
          new_arr := new_arr || jsonb_build_array(elem - 'file_id');
        END IF;
      END LOOP;

      IF new_arr IS DISTINCT FROM r.attachments::jsonb THEN
        UPDATE applications
        SET attachments = new_arr::text,
            updated_at = NOW()
        WHERE id = r.id;
      END IF;

    EXCEPTION
      WHEN OTHERS THEN
        RAISE WARNING 'attachments cleanup skipped for applications.id=%: %', r.id, SQLERRM;
    END;
  END LOOP;
END $$;
