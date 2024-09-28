#!/bin/bash

BACKUP_DIR="/docker/mysql/backups"
LATEST_BACKUP=$(ls -t $BACKUP_DIR/*.sql | head -n 1)

if [ -f "$LATEST_BACKUP" ]; then
    echo "Восстанавливаю базу данных из бекапа: $LATEST_BACKUP"
    mysql -u root -p$MYSQL_ROOT_PASSWORD < "$LATEST_BACKUP"
else
    echo "Бекап не найден, пропускаю восстановление."
fi
