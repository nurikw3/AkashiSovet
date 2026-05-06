# Graph Report - AkashiSovet  (2026-05-06)

## Corpus Check
- 56 files · ~75,108 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1041 nodes · 1425 edges · 78 communities detected
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 134 edges (avg confidence: 0.76)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ec534f4b`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 103|Community 103]]
- [[_COMMUNITY_Community 104|Community 104]]
- [[_COMMUNITY_Community 105|Community 105]]

## God Nodes (most connected - your core abstractions)
1. `_pool_conn()` - 43 edges
2. `get_template()` - 35 edges
3. `get_app_pdf_buffer()` - 26 edges
4. `generate_pdf()` - 25 edges
5. `invalidate_pdf_cache()` - 24 edges
6. `ApplicationTemplate` - 19 edges
7. `get_user_apps()` - 17 edges
8. `meetings_create()` - 15 edges
9. `BaseModel` - 15 edges
10. `_handle_delegation()` - 14 edges

## Surprising Connections (you probably didn't know these)
- `main()` --calls--> `generate_pdf()`  [INFERRED]
  test_pdf.py → stdlib/pdf.py
- `template_editor_page()` --calls--> `get_template()`  [INFERRED]
  web/main.py → stdlib/template.py
- `template_editor_save()` --calls--> `persist_template()`  [INFERRED]
  web/main.py → stdlib/template.py
- `reject_app()` --calls--> `get_template()`  [INFERRED]
  web/main.py → stdlib/template.py
- `reject_app()` --calls--> `invalidate_pdf_cache()`  [INFERRED]
  web/main.py → stdlib/pdf.py

## Communities (106 total, 8 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (36): bindToolbar(), build(), initCalendarPage(), applyDefaults(), buildAll(), initCharts(), tokens(), start() (+28 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (33): get_cached_llm_response(), save_llm_response_to_cache(), get_db_pool(), get_redis(), get_s3_session(), init_resources(), Единая инициализация и доступ к asyncpg-пулу, Redis и S3 (aiobotocore session)., Поднимает PostgreSQL, Redis (кэш/служебное) и проверяет бакеты S3. (+25 more)

### Community 2 - "Community 2"
Cohesion: 0.11
Nodes (28): _(), a(), b(), C(), D(), e(), f(), Ft() (+20 more)

### Community 3 - "Community 3"
Cohesion: 0.06
Nodes (36): get_application_status_counts(), get_daily_stats(), get_user_apps(), Возвращает статистику заявок за последние 24 часа., Возвращает статистику заявок за последние 24 часа., Возвращает статистику заявок за последние 24 часа., Проверяет код и сбрасывает его., Возвращает статистику заявок за последние 24 часа. (+28 more)

### Community 4 - "Community 4"
Cohesion: 0.1
Nodes (34): _app_attachments_prefix(), delete_app_files(), _delete_by_prefix(), delete_object(), delete_user_files(), download_bytes(), download_to_bytesio(), ensure_buckets() (+26 more)

### Community 5 - "Community 5"
Cohesion: 0.08
Nodes (30): generate_pdf_filename(), Генерирует стандартизированное имя для PDF-файла., Генерирует стандартизированное имя для PDF-файла., Генерирует стандартизированное имя для PDF-файла., Генерирует стандартизированное имя для PDF-файла., Генерирует стандартизированное имя для PDF-файла., Генерирует стандартизированное имя для PDF-файла., Генерирует стандартизированное имя для PDF-файла. (+22 more)

### Community 6 - "Community 6"
Cohesion: 0.07
Nodes (32): add_applications(), create_meeting(), create_meeting_with_applications(), delete_meeting(), get_by_id(), get_past(), get_upcoming(), Заседания Правления: создание, списки предстоящих/прошедших, добавление заявок в (+24 more)

### Community 7 - "Community 7"
Cohesion: 0.14
Nodes (26): delete_app(), get_app(), get_chat_history(), get_draft_id_for_user(), get_last_rework_app(), get_or_create_app(), get_pending_apps(), get_user_full_name() (+18 more)

### Community 8 - "Community 8"
Cohesion: 0.1
Nodes (27): escape_markdown_v2(), is_delegation(), _block_title(), _get_context(), handle_block_input(), _handle_delegation(), _handle_format(), on_edit() (+19 more)

### Community 9 - "Community 9"
Cohesion: 0.08
Nodes (10): BotStates, finalize_and_notify(), on_confirm(), on_files_done(), on_review_submit(), on_rework_submit(), send_review_screen(), States (+2 more)

### Community 10 - "Community 10"
Cohesion: 0.13
Nodes (24): _block_label(), _build_messages(), format_text(), _make_cache_key(), Форматирование и генерация текста блоков через LLM., Изоляция кэша по заявке и блоку — одинаковый «test» не бьёт в чужой контекст., В ключ входят заявка (и user), иначе Redis отдаёт ответ от другой заявки с тем ж, В ключ входят заявка (и user), иначе Redis отдаёт ответ от другой заявки с тем ж (+16 more)

### Community 11 - "Community 11"
Cohesion: 0.13
Nodes (21): _append_section_paragraphs(), _build_pdf_sync(), _generate_pdf_sync(), _get_pdf_template_revision(), _load_signature_for_user(), _normalize_blocks_payload(), _normalize_pdf_user_text(), _normalize_risk_placeholder() (+13 more)

### Community 12 - "Community 12"
Cohesion: 0.11
Nodes (17): ApplicationTemplate, Application, ApplicationAttachment, ChatMessage, Централизованные Pydantic-модели домена (заявки, пользователи, шаблон, заседания, Пользователь Telegram / запись в таблице `users`., Динамический шаблон структуры заявки (блоки — см. `stdlib.template.ApplicationTe, Пользователь Telegram / запись в таблице `users`. (+9 more)

### Community 13 - "Community 13"
Cohesion: 0.13
Nodes (12): application_detail_page(), _clean_attachments(), dashboard(), _get_hashed_password(), login(), meeting_detail_page(), meeting_remove_app(), _parse_app() (+4 more)

### Community 14 - "Community 14"
Cohesion: 0.11
Nodes (19): main(), generate_pdf(), Генерирует PDF служебной записки с авто-подписью., Берёт подпись пользователя: из S3 по ключу в БД либо устаревшие бинарные данные., Берёт подпись пользователя: из S3 по ключу в БД либо устаревшие бинарные данные., Генерирует PDF служебной записки с авто-подписью.      Заявка из БД: передайте `, Берёт подпись пользователя: из S3 по ключу в БД либо устаревшие бинарные данные., Берёт подпись пользователя: из S3 по ключу в БД либо устаревшие бинарные данные. (+11 more)

### Community 15 - "Community 15"
Cohesion: 0.12
Nodes (18): delete_meeting_by_id(), extend_meeting_application_ids(), _parse_application_ids_jsonb(), Одна запись `meetings` по id., Обновляет дату/время заседания. Возвращает True, если строка была найдена., Добавляет id заявок в JSONB-массив без дубликатов; строка должна существовать., Удаляет заседание по id. Возвращает True, если строка была удалена., Обновляет дату/время заседания. Возвращает True, если строка была найдена. (+10 more)

### Community 16 - "Community 16"
Cohesion: 0.16
Nodes (16): build_files_step_message(), build_review_text_snapshot(), chunk_plain_text(), format_blocks_plain_copy(), html_pre_block(), Единое текстовое представление блоков заявки (plain + HTML с <pre> для Telegram), Все блоки подряд: нумерация, заголовок шаблона, текст — удобно копировать., Один экранированный блок <pre> (parse_mode=HTML). (+8 more)

### Community 17 - "Community 17"
Cohesion: 0.12
Nodes (17): download_attachment(), download_attachment_bytesio(), _object_key_component(), Загрузка и скачивание вложений через S3., Имя файла в ключе S3: уникальный префикс + исходное имя (без коллизий)., Загружает файл в бакет вложений и возвращает метаданные., Загружает файл в бакет вложений и возвращает метаданные., Скачивает объект по ключу из бакета вложений. (+9 more)

### Community 18 - "Community 18"
Cohesion: 0.12
Nodes (15): process_free_form_chat(), Free-form диалог для сбора данных заявки., build_free_form_system(), build_free_form_tools(), Системные промпты и инструменты для LLM., Инструменты для free-form: ask_user + submit_memo с полями по текущему шаблону и, Инструменты для free-form: ask_user + submit_memo с полями по текущему шаблону и, Инструменты для free-form: ask_user + submit_memo с полями по текущему шаблону и (+7 more)

### Community 19 - "Community 19"
Cohesion: 0.12
Nodes (16): invalidate_application_pdf_cache(), Сохраняет список вложений как в БД (в т.ч. реестр файлов из Telegram до выгрузки, save_attachments_payload(), _cache_key(), _get_redis(), invalidate_pdf_cache(), Инвалидирует кэш PDF для заявки после изменения данных.      Сейчас `get_app_pdf, Инвалидирует кэш PDF для заявки после изменения данных.      Сейчас `get_app_pdf (+8 more)

### Community 20 - "Community 20"
Cohesion: 0.25
Nodes (9): BaseModel, AskUser, FormatResult, FormattedBlock, LLMComplete, LLMError, LLMIncomplete, SubmitMemo (+1 more)

### Community 21 - "Community 21"
Cohesion: 0.14
Nodes (10): broadcast_superusers_html(), Рассылает HTML всем суперпользователям (например при ошибке генерации PDF)., now_app(), Текущие дата и время в часовом поясе приложения., on_files_done(), finalize_and_notify(), on_review_edit(), on_review_submit() (+2 more)

### Community 22 - "Community 22"
Cohesion: 0.13
Nodes (9): clear_application_chat_history(), get_application_record(), get_draft_application_id_for_user(), Операции с заявкой: создание черновика, смена статуса, отправка на согласование,, Сырая строка из БД (как `db.get_app`): нужна, где важен исходный JSON вложений (, Обнуляет историю free-form / LLM по заявке., `id` черновика пользователя, если есть., save_all_blocks() (+1 more)

### Community 23 - "Community 23"
Cohesion: 0.14
Nodes (14): meeting_delete(), meeting_reschedule(), Удаление заседания (только суперпользователь)., Удаление заседания (только суперпользователь)., Удаление заседания (только суперпользователь)., Создаёт заседание и прикрепляет отмеченные согласованные заявки., Удаление заседания (только суперпользователь)., Удаление заседания (только суперпользователь). (+6 more)

### Community 24 - "Community 24"
Cohesion: 0.14
Nodes (14): get_app_pdf_buffer(), Универсальная функция подготовки и генерации PDF для заявки.     Единый источник, Отдаёт PDF из S3 (если есть флаг в Redis) или генерирует заново.     Redis храни, Универсальная функция подготовки и генерации PDF для заявки.     Единый источник, Универсальная функция подготовки и генерации PDF для заявки.     Единый источник, Отдаёт PDF из S3 (если есть флаг в Redis) или генерирует заново.     Redis храни, Универсальная функция подготовки и генерации PDF для заявки.     Единый источник, Отдаёт PDF из S3 (если есть флаг в Redis) или генерирует заново.     Redis храни (+6 more)

### Community 25 - "Community 25"
Cohesion: 0.15
Nodes (13): get_application_status_by_ids(), get_applications_by_ids(), id заявки → status (только для существующих id из списка)., id заявки → status (только для существующих id из списка)., id заявки → status (только для существующих id из списка)., Заявки с JOIN к users, порядок как в `ids` (пропуск отсутствующих id)., Заявки с JOIN к users, порядок как в `ids` (пропуск отсутствующих id)., id заявки → status (только для существующих id из списка). (+5 more)

### Community 26 - "Community 26"
Cohesion: 0.15
Nodes (13): list_meetings_past(), list_meetings_upcoming(), Заседания с датой >= сегодня (по календарю БД), ближайшие первыми., Прошедшие заседания, от новых к старым., Заседания с датой >= сегодня (по календарю БД), ближайшие первыми., Заседания с датой >= сегодня (по календарю БД), ближайшие первыми., Заседания в будущем (или «сейчас»), ближайшие первыми., Прошедшие заседания, от новых к старым. (+5 more)

### Community 27 - "Community 27"
Cohesion: 0.15
Nodes (13): get_meeting_by_id(), insert_meeting(), Создаёт заседание; возвращает строку как dict (RETURNING *)., Создаёт заседание; возвращает строку как dict (RETURNING *)., Создаёт заседание; возвращает строку как dict (RETURNING *)., Создаёт заседание; возвращает строку как dict (RETURNING *)., Создаёт заседание; возвращает строку как dict (RETURNING *)., Создаёт заседание; возвращает строку как dict (RETURNING *). (+5 more)

### Community 28 - "Community 28"
Cohesion: 0.26
Nodes (10): _cancel_button(), confirm_keyboard(), confirm_rework_keyboard(), files_keyboard(), _kb_text(), Кнопки привязаны к номеру блока — после перехода на следующий блок старые «Испра, Кнопки привязаны к номеру блока — иначе после перехода к следующему шагу «Исправ, restart_or_continue_keyboard() (+2 more)

### Community 29 - "Community 29"
Cohesion: 0.17
Nodes (12): dashboard_counters_partial(), Фрагмент HTMX: виджеты счётчиков (обновление без перезагрузки)., Фрагмент HTMX: виджеты счётчиков (обновление без перезагрузки)., Фрагмент HTMX: виджеты счётчиков (обновление без перезагрузки)., Фрагмент HTMX: виджеты счётчиков (обновление без перезагрузки)., Фрагмент HTMX: виджеты счётчиков (обновление без перезагрузки)., Фрагмент HTMX: виджеты счётчиков (обновление без перезагрузки)., Фрагмент HTMX: виджеты счётчиков (обновление без перезагрузки). (+4 more)

### Community 30 - "Community 30"
Cohesion: 0.17
Nodes (12): draw_background(), Логотип на всех страницах кроме последней., Логотип на всех страницах кроме последней., Логотип на всех страницах кроме последней., Логотип на всех страницах кроме последней., Для блока про риски сохраняем отображение «не применимо» как в старой вёрстке., Обычный Canvas, подпись теперь рисуется в самом тексте., Для блока про риски сохраняем отображение «не применимо» как в старой вёрстке. (+4 more)

### Community 31 - "Community 31"
Cohesion: 0.2
Nodes (11): _normalize_submit_memo_args(), clean(), Очистка markdown в значениях перед model_validate., Очистка markdown и склеенных нумерованных списков перед model_validate., _strip_md(), strip_submit_memo_args(), strip_text(), expand_numbered_newlines() (+3 more)

### Community 32 - "Community 32"
Cohesion: 0.2
Nodes (11): get_template(), Загружает шаблон заявки из `settings.app_template`.     Кэширует JSON в Redis на, Загружает шаблон заявки из `settings.app_template`.     Кэширует JSON в Redis на, Загружает шаблон заявки из `settings.app_template`.     Кэширует JSON в Redis на, Загружает шаблон заявки из `settings.app_template`.     Кэширует JSON в Redis на, Загружает шаблон заявки из `settings.app_template`.     Кэширует JSON в Redis на, cb_rework_start(), on_rework_confirmed() (+3 more)

### Community 33 - "Community 33"
Cohesion: 0.18
Nodes (11): Только удаление строки в форме (без записи в БД)., Только удаление строки в форме (без записи в БД)., Только удаление строки в форме (без записи в БД).      HTMX по умолчанию не дела, Только удаление строки в форме (без записи в БД)., Только удаление строки в форме (без записи в БД)., Только удаление строки в форме (без записи в БД).      HTMX по умолчанию не дела, Только удаление строки в форме (без записи в БД).      HTMX по умолчанию не дела, Только удаление строки в форме (без записи в БД).      HTMX по умолчанию не дела (+3 more)

### Community 34 - "Community 34"
Cohesion: 0.18
Nodes (11): meetings_create(), Создаёт заседание и прикрепляет отмеченные согласованные заявки., Создаёт заседание (дата+время) и при необходимости прикрепляет заявки., Создаёт заседание и прикрепляет отмеченные согласованные заявки., Создаёт заседание и прикрепляет отмеченные согласованные заявки., Создаёт заседание и прикрепляет отмеченные согласованные заявки., Создаёт заседание и прикрепляет отмеченные согласованные заявки., Создаёт заседание и прикрепляет отмеченные согласованные заявки. (+3 more)

### Community 35 - "Community 35"
Cohesion: 0.18
Nodes (11): draw_last_page(), _escape_para_text(), Логотип + футер — только на последней странице., Логотип + футер — только на последней странице., Логотип + футер — только на последней странице., Логотип + футер — только на последней странице., ReportLab Paragraph — экранирование XML-символов в пользовательском тексте., Логотип + футер — только на последней странице. (+3 more)

### Community 36 - "Community 36"
Cohesion: 0.18
Nodes (3): cmd_mode(), cmd_start(), on_restart_draft()

### Community 37 - "Community 37"
Cohesion: 0.18
Nodes (11): append_attachments(), Добавляет вложение к заявке и сохраняет в БД., Возврат на доработку с комментарием., Добавляет вложение к заявке и сохраняет в БД., Добавляет вложение к заявке и сохраняет в БД., Возврат на доработку с комментарием., Добавляет вложение к заявке и сохраняет в БД., Возврат на доработку с комментарием. (+3 more)

### Community 38 - "Community 38"
Cohesion: 0.24
Nodes (9): notify_user_application_rework(), Уведомляет автора о возврате на доработку., is_superuser(), on_feedback(), on_reject(), Возвращает уже согласованную заявку на доработку (только суперпользователь)., reject_app(), _render_row() (+1 more)

### Community 39 - "Community 39"
Cohesion: 0.22
Nodes (7): Canvas, _LastPageCanvas, Обычный Canvas, подпись теперь рисуется в самом тексте., Обычный Canvas, подпись теперь рисуется в самом тексте., Обычный Canvas, подпись теперь рисуется в самом тексте., Обычный Canvas, подпись теперь рисуется в самом тексте., Обычный Canvas, подпись теперь рисуется в самом тексте.

### Community 40 - "Community 40"
Cohesion: 0.2
Nodes (10): get_or_create_draft(), Находит черновик пользователя или создаёт новый; возвращает `id`., Обновляет `pdf_file_id` у уже отправленной заявки (например после отправки PDF в, Возвращает заявку как `Application` или `None`., Находит черновик пользователя или создаёт новый; возвращает `id`., Находит черновик пользователя или создаёт новый; возвращает `id`., Находит черновик пользователя или создаёт новый; возвращает `id`., Обновляет `pdf_file_id` у уже отправленной заявки (например после отправки PDF в (+2 more)

### Community 41 - "Community 41"
Cohesion: 0.22
Nodes (9): meeting_update_schedule(), Меняет дату и время заседания (форма из карточки заседания)., Меняет дату и время заседания (форма из карточки заседания)., Меняет дату и время заседания (форма из карточки заседания)., Меняет дату и время заседания (форма из карточки заседания)., Меняет дату и время заседания (форма из карточки заседания)., Меняет дату и время заседания (форма из карточки заседания)., Меняет дату и время заседания (форма из карточки заседания). (+1 more)

### Community 42 - "Community 42"
Cohesion: 0.22
Nodes (9): _meeting_form_err_prefix(), Куда редиректить ошибку валидации: страница списка заседаний или дашборд approve, Куда редиректить ошибку валидации: страница списка заседаний или дашборд approve, Куда редиректить ошибку валидации: страница списка заседаний или дашборд approve, Куда редиректить ошибку валидации: страница списка заседаний или дашборд approve, Куда редиректить ошибку валидации: страница списка заседаний или дашборд approve, Куда редиректить ошибку валидации: страница списка заседаний или дашборд approve, Куда редиректить ошибку валидации: страница списка заседаний или дашборд approve (+1 more)

### Community 43 - "Community 43"
Cohesion: 0.22
Nodes (9): _parse_meeting_schedule(), Парсит `scheduled_at` (datetime-local) или устаревшее поле даты (10:00)., Парсит `scheduled_at` (datetime-local) или устаревшее поле даты (10:00)., Парсит `scheduled_at` (datetime-local) или устаревшее поле даты (10:00)., Парсит `scheduled_at` (datetime-local) или устаревшее поле даты (10:00)., Парсит `scheduled_at` (datetime-local) или устаревшее поле даты (10:00)., Парсит `scheduled_at` (datetime-local) или устаревшее поле даты (10:00)., Парсит `scheduled_at` (datetime-local) или дату + 10:00 как локальное время Аста (+1 more)

### Community 44 - "Community 44"
Cohesion: 0.22
Nodes (9): generate_web_login_code(), Генерирует 6-значный код и сохраняет его в колонку mode (как временный буфер)., Генерирует 6-значный код и сохраняет его в колонку mode (как временный буфер)., Генерирует 6-значный код и сохраняет его в колонку mode (как временный буфер)., Генерирует 6-значный код и сохраняет его в колонку mode (как временный буфер)., Генерирует 6-значный код и сохраняет его в колонку mode (как временный буфер)., Генерирует 6-значный код и сохраняет его в колонку mode (как временный буфер)., Генерирует 6-значный код и сохраняет его в колонку mode (как временный буфер). (+1 more)

### Community 45 - "Community 45"
Cohesion: 0.22
Nodes (9): _normalize_list_text(), ReportLab Paragraph — экранирование XML-символов в пользовательском тексте., Нормализует разделители и пробелы, чтобы сплит по «; 2)» срабатывал стабильно., Нормализует разделители и пробелы, чтобы сплит по «; 2)» срабатывал стабильно., Нормализует разделители и пробелы, чтобы сплит по «; 2)» срабатывал стабильно., Делит один абзац на пункты, если LLM вставила «2)», «3.» в одну строку     или ч, Делит один абзац на пункты, если LLM вставила «2)», «3.» в одну строку     или ч, Делит один абзац на пункты, если LLM вставила «2)», «3.» в одну строку     или ч (+1 more)

### Community 46 - "Community 46"
Cohesion: 0.25
Nodes (7): main(), Точка входа Telegram-бота AKASHI Data Center PLC. Включает: AIogram 3.7+, Redis, Задача APScheduler: ежедневный отчет суперюзерам., Задача APScheduler: ежедневный отчет суперюзерам., send_daily_report(), close_redis(), init_redis()

### Community 47 - "Community 47"
Cohesion: 0.25
Nodes (7): parse_admin_session(), Подписанная cookie админ-сессии (HMAC). Без секрета — только для разработки., Разбирает cookie; при WEB_SESSION_SECRET отвергает подделку., sign_admin_session(), get_admin(), login_page(), login_post()

### Community 48 - "Community 48"
Cohesion: 0.29
Nodes (6): notify_user_application_approved(), Отправка уведомлений пользователям через Telegram Bot API., Уведомляет автора о согласовании.     Если передан `pdf_file_id` — отправляет до, is_superuser(), on_approve(), approve_app()

### Community 49 - "Community 49"
Cohesion: 0.25
Nodes (5): InterceptHandler, Централизованная настройка Loguru. Импортируй `logger` из этого модуля во всех ф, Настроить форматы вывода. Вызвать один раз при старте бота., Перенаправляет записи stdlib logging → loguru., setup_logging()

### Community 50 - "Community 50"
Cohesion: 0.29
Nodes (7): download_file(), download_tg_attachment(), Скачивание файла по Telegram file_id (вложения, загруженные в боте до S3)., Скачивание файла по Telegram file_id (вложения, загруженные в боте до S3)., Скачивание файла по Telegram file_id (вложения, загруженные в боте до S3)., Скачивание файла по Telegram file_id (вложения, загруженные в боте до S3)., Скачивание файла по Telegram file_id (вложения, загруженные в боте до S3).

### Community 51 - "Community 51"
Cohesion: 0.29
Nodes (7): approve(), get_application(), list_applications(), Список заявок для веб-таблицы (опционально один статус: draft/pending/rework/app, Возвращает заявку как `Application` или `None`., Возвращает заявку как `Application` или `None`., Возвращает заявку как `Application` или `None`.

### Community 52 - "Community 52"
Cohesion: 0.43
Nodes (4): bumpTitleCount(), findInsertionIndex(), processPost(), uploadMedia()

### Community 53 - "Community 53"
Cohesion: 0.4
Nodes (5): _block_html_fragments(), chunk_blocks_summary_html(), HTML-тексты для Telegram (parse_mode=HTML): сводка по блокам заявки., Тот же формат, что ``build_blocks_summary_html``, но разбитый на несколько сообщ, Тот же формат, что ``build_blocks_summary_html``, но разбитый на несколько сообщ

### Community 54 - "Community 54"
Cohesion: 0.33
Nodes (6): Переводит заявку в `pending`, фиксирует время подачи., Переводит заявку в `pending`, фиксирует время подачи., Переводит заявку в `pending`, фиксирует время подачи., Переводит заявку в `pending`, фиксирует время подачи., Переводит заявку в `pending`, фиксирует время подачи., submit_to_review()

### Community 56 - "Community 56"
Cohesion: 0.4
Nodes (5): get_applications(), Список заявок для веб-таблицы. Без фильтра — все статусы; иначе один из четырёх., Список заявок для веб-таблицы. Без фильтра — все статусы; иначе один из четырёх., Список заявок для веб-таблицы. Без фильтра — все статусы; иначе один из четырёх., Список заявок для веб-таблицы. Без фильтра — все статусы; иначе один из четырёх.

### Community 57 - "Community 57"
Cohesion: 0.4
Nodes (4): Возвращает ID предыдущего блока или None, если это первый, Возвращает ID предыдущего блока или None, если это первый, Возвращает ID предыдущего блока или None, если это первый, Возвращает ID предыдущего блока или None, если это первый

### Community 59 - "Community 59"
Cohesion: 0.4
Nodes (4): Возвращает ID следующего блока или None, если это последний, Возвращает ID следующего блока или None, если это последний, Возвращает ID следующего блока или None, если это последний, Возвращает ID следующего блока или None, если это последний

### Community 60 - "Community 60"
Cohesion: 0.7
Nodes (4): buildReplacementFigure(), findAdminatorFigure(), processPost(), uploadMedia()

### Community 61 - "Community 61"
Cohesion: 0.5
Nodes (4): clear_chat_history(), Сбрасывает free-form / LLM-историю по заявке (при /start, смене режима)., Сбрасывает free-form / LLM-историю по заявке (при /start, смене режима)., save_chat_history()

### Community 62 - "Community 62"
Cohesion: 0.5
Nodes (3): on_cancel_app(), Универсальный обработчик отмены заявки из любого состояния., Универсальный обработчик отмены заявки из любого состояния.

### Community 63 - "Community 63"
Cohesion: 0.5
Nodes (4): get_status_counts(), list_user_applications(), Счётчики по статусам для дашборда (pending / approved / rework / total)., Заявки пользователя (как `db.get_user_apps`).

### Community 64 - "Community 64"
Cohesion: 0.83
Nodes (3): findListicleSection(), moveEntry(), renumberHeading()

### Community 65 - "Community 65"
Cohesion: 0.5
Nodes (3): compile_free_form_local(), Локальные тексты промптов (fallback, если Langfuse недоступен или имя/label не н, Подстановка без Langfuse (тот же синтаксис {{var}}, что в Langfuse text prompt).

### Community 66 - "Community 66"
Cohesion: 0.67
Nodes (3): get_pool(), Публичный доступ к пулу (инициализация через `stdlib.resources.init_resources`)., Публичный доступ к пулу (инициализация через `stdlib.resources.init_resources`).

### Community 67 - "Community 67"
Cohesion: 0.67
Nodes (3): Вставка или обновление JSONB по ключу., Вставка или обновление JSONB по ключу., upsert_setting()

### Community 68 - "Community 68"
Cohesion: 0.67
Nodes (3): Сбрасывает блоки, вложения и free-form чат у черновика.     Нужен при новом /sta, Сбрасывает блоки, вложения и free-form чат у черновика.     Нужен при новом /sta, reset_draft_content()

### Community 69 - "Community 69"
Cohesion: 0.67
Nodes (3): get_setting(), Возвращает JSONB-значение из таблицы `settings` или None, если ключа нет., Возвращает JSONB-значение из таблицы `settings` или None, если ключа нет.

### Community 70 - "Community 70"
Cohesion: 0.67
Nodes (3): Meeting, Заседание Правления: планируемая сущность из `meetings` (id — после появления та, Заседание Правления: планируемая сущность из `meetings` (id — после появления та

### Community 71 - "Community 71"
Cohesion: 0.67
Nodes (3): Чистый черновик для нового /start или «Начать заново» (без контекста старого реж, Чистый черновик для нового /start или «Начать заново» (без контекста старого реж, reset_draft_for_new_session()

## Knowledge Gaps
- **438 isolated node(s):** `Подписанная cookie админ-сессии (HMAC). Без секрета — только для разработки.`, `Разбирает cookie; при WEB_SESSION_SECRET отвергает подделку.`, `Только удаление строки в форме (без записи в БД).      HTMX по умолчанию не дела`, `Фрагмент HTMX: виджеты счётчиков (обновление без перезагрузки).`, `Возвращает уже согласованную заявку на доработку (только суперпользователь).` (+433 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_template()` connect `Community 32` to `Community 1`, `Community 36`, `Community 5`, `Community 38`, `Community 8`, `Community 10`, `Community 13`, `Community 14`, `Community 16`, `Community 18`, `Community 21`, `Community 24`, `Community 31`?**
  _High betweenness centrality (0.212) - this node is a cross-community bridge._
- **Why does `generate_pdf()` connect `Community 14` to `Community 0`, `Community 32`, `Community 11`, `Community 24`, `Community 30`?**
  _High betweenness centrality (0.088) - this node is a cross-community bridge._
- **Why does `invalidate_pdf_cache()` connect `Community 19` to `Community 37`, `Community 38`, `Community 71`, `Community 11`, `Community 14`, `Community 21`, `Community 22`?**
  _High betweenness centrality (0.077) - this node is a cross-community bridge._
- **Are the 28 inferred relationships involving `get_template()` (e.g. with `template_editor_page()` and `reject_app()`) actually correct?**
  _`get_template()` has 28 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `get_app_pdf_buffer()` (e.g. with `download_report()` and `get_template()`) actually correct?**
  _`get_app_pdf_buffer()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `generate_pdf()` (e.g. with `main()` and `main()`) actually correct?**
  _`generate_pdf()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `invalidate_pdf_cache()` (e.g. with `reset_draft_for_new_session()` and `save_block()`) actually correct?**
  _`invalidate_pdf_cache()` has 10 INFERRED edges - model-reasoned connections that need verification._