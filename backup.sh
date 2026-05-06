#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="./backups/postgres"
mkdir -p $BACKUP_DIR

docker exec akashi_db pg_dump -U akashi akashi | gzip > $BACKUP_DIR/akashi_$DATE.sql.gz

find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete

echo "Backup done: akashi_$DATE.sql.gz"