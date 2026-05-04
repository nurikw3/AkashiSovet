-- Phase 2, step 1: глобальные настройки (JSON) и начальный шаблон заявки.
-- Содержимое app_template соответствует stdlib.template.CURRENT_TEMPLATE (ApplicationTemplate).

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value JSONB NOT NULL
);

INSERT INTO settings (key, value)
VALUES (
    'app_template',
    $json$
{"blocks":[{"id":1,"title":"Тема вопроса","question":"Укажите тему вопроса, выносимого на Правление.\n\nНапример: «О заключении договора с подрядчиком X» или «Об утверждении бюджета отдела на Q3».","description_for_llm":null},{"id":2,"title":"Краткое описание и суть вопроса","question":"Кратко опишите ситуацию: что произошло, в чём вопрос или проблема?\n\nПишите как удобно — я приведу текст к нужному стилю.","description_for_llm":null},{"id":3,"title":"Основание для вынесения","question":"Укажите причину и основание для вынесения вопроса на Правление.\n\nНапример: поручение от определённой даты, результаты аудита, истечение срока договора, регуляторное требование.","description_for_llm":null},{"id":4,"title":"Предлагаемое решение!!","question":"Сформулируйте конкретные предложения: что нужно утвердить, согласовать, делегировать или поручить?\n\nЕсли вариантов несколько — перечислите их.","description_for_llm":null},{"id":5,"title":"Риски и последствия","question":"Опишите риски и последствия, если решение не будет принято или отложено.\n\nЕсли раздел не применим — напишите «не применимо».","description_for_llm":null}]}
$json$::jsonb
)
ON CONFLICT (key) DO NOTHING;
