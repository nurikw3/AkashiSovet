-- Явная настройка format_as_numbered_list для блоков шаблона заявки.
-- Для существующих блоков «решений/вариантов» включаем список по умолчанию (один раз).

UPDATE settings
SET value = jsonb_set(
    value,
    '{blocks}',
    (
        SELECT jsonb_agg(
            elem || jsonb_build_object(
                'format_as_numbered_list',
                CASE
                    WHEN elem ? 'format_as_numbered_list' THEN
                        COALESCE((elem->>'format_as_numbered_list')::boolean, false)
                    WHEN (elem->>'title') ILIKE ANY (ARRAY[
                        '%решени%', '%вариант%', '%предлага%',
                        '%риск%', '%основан%', '%поруч%'
                    ]) THEN true
                    ELSE false
                END
            )
            ORDER BY ord
        )
        FROM jsonb_array_elements(value->'blocks') WITH ORDINALITY AS t(elem, ord)
    ),
    false
)
WHERE key = 'app_template'
  AND jsonb_typeof(value->'blocks') = 'array';
