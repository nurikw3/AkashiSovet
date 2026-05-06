#!/bin/bash

# Настройки
CONTAINER_NAME="akashi_db"
DB_USER="akashi"
DB_NAME="akashi"
BACKUP_DIR="./backups"
DAYS_TO_KEEP=7

# Создаем папку для бекапов, если её нет
mkdir -p "$BACKUP_DIR"

# Генерируем имя файла с текущей датой и временем
DATE=$(date +%Y-%m-%d_%H-%M-%S)
FILE_NAME="$BACKUP_DIR/${DB_NAME}_backup_${DATE}.sql.gz"

echo "Начинаем создание бекапа БД..."

# Выполняем дамп внутри контейнера и сразу сжимаем его
docker exec -t $CONTAINER_NAME pg_dump -U $DB_USER -d $DB_NAME | gzip > "$FILE_NAME"

if [ $? -eq 0 ]; then
  echo "✅ Бекап успешно создан: $FILE_NAME"
else
  echo "❌ Ошибка при создании бекапа!"
  exit 1
fi

# Удаляем старые бекапы (старше $DAYS_TO_KEEP дней)
echo "Очистка старых бекапов (оставляем за последние $DAYS_TO_KEEP дней)..."
find "$BACKUP_DIR" -type f -name "*.sql.gz" -mtime +$DAYS_TO_KEEP -exec rm {} \;

echo "Готово."
