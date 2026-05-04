# Деплой и Docker

Краткая шпаргалка по запуску **AkashiSovet** (web + bot + Postgres + Redis + MinIO + опционально Grafana).

## Подготовка

1. Скопируйте `env.example` в `.env` и заполните как минимум: `BOT_TOKEN`, `OPENAI_API_KEY`, `POSTGRES_PASSWORD`, `WEB_SESSION_SECRET` (для продакшена), `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` (или оставьте дефолты только для локалки).
2. В **проде** задайте `WEB_PUBLIC_URL` с публичным URL панели (как в браузере), `WEB_COOKIE_SECURE=true` за HTTPS-прокси.
3. Размер пула БД: `DB_POOL_MIN_SIZE`, `DB_POOL_MAX_SIZE` — в Postgres параметр `max_connections` должен быть **не меньше** `DB_POOL_MAX_SIZE` с запасом на админку и фоновые задачи.

---

## Продакшен / полный стек (без dev)

Используется только `docker-compose.yaml`: код и шаблоны **внутри образа**, после правок Python/HTML нужна **пересборка** сервисов, которые используют этот код.

```bash
# Первый запуск или после изменений в Dockerfile / pyproject / uv.lock
docker compose build web
docker compose up -d

# Одной строкой (сборка web, затем все сервисы)
docker compose up -d --build
```

**Важно:** образ `akashisovet:app` собирается только у сервиса `web`. Сервис `bot` подтягивает **тот же тег** (`pull_policy: never`) — пересоберите `web` перед перезапуском бота, иначе бот может работать на старом образе.

```bash
docker compose build web && docker compose up -d web bot
```

---

## Разработка (hot-reload веба + код с хоста)

Подмешивается `docker-compose.dev.yaml`: монтируются `./web`, `./stdlib` (и для бота ещё `./bot`), у **web** включён `uvicorn --reload`.

```bash
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml up --build
```

- Правки в `web/` и `stdlib/` подхватываются **без** пересборки образа.
- **Бот** при смене `bot/` обычно **перезапускают вручную** (см. ниже), т.к. reload для него не настроен.

---

## Типовые команды

| Действие | Команда |
|----------|---------|
| Статус | `docker compose ps` |
| Логи всех | `docker compose logs -f` |
| Логи одного сервиса | `docker compose logs -f web` / `bot` / `postgres` |
| Остановить | `docker compose down` |
| Остановить и убрать volumes (⚠️ сотрёт БД/MinIO/Redis на диске) | `docker compose down -v` |
| Перезапустить web | `docker compose restart web` |
| Перезапустить bot | `docker compose restart bot` |
| Пересобрать образ с нуля | `docker compose build --no-cache web` |

### После смены зависимостей (`pyproject.toml` / `uv.lock`)

```bash
docker compose build --no-cache web
docker compose up -d web bot
```

Базовый образ в `Dockerfile` — **Python 3.13**; lock-файл рассчитан на `>=3.13`.

---

## Порты (по умолчанию)

| Сервис | Порт |
|--------|------|
| Web (FastAPI) | 8000 |
| Postgres | 5432 |
| Redis | 6379 |
| MinIO API | 9000 |
| MinIO Console | 9001 |
| Grafana | 3000 |

---

## Миграции SQL

SQL-файлы в каталоге `migrations/` применяйте к своей БД вручную или через свой пайплайн (отдельного job в compose нет).

---

## Grafana

Поднимается вместе со стеком; пароль админа из `.env` (`GRAFANA_PASSWORD`). Если переменная не задана, задайте её перед первым `up`.
