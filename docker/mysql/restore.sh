#!/bin/bash

echo "Скрипт восстановления запущен." >> /tmp/restore_log.txt

BACKUP_DIR="/backups"
LATEST_BACKUP=$(ls -t $BACKUP_DIR/*.sql | head -n 1)

if [ -f "$LATEST_BACKUP" ]; then
    echo "Восстанавливаю базу данных из бекапа: $LATEST_BACKUP" >> /tmp/restore_log.txt

    # Удаляем старую базу данных и создаем новую
    mysql -u root -p$MYSQL_ROOT_PASSWORD -e "DROP DATABASE IF EXISTS $MYSQL_DATABASE; CREATE DATABASE $MYSQL_DATABASE;" 2>> /tmp/restore_log.txt

    # Восстанавливаем базу данных из бекапа и записываем ошибки в лог
    mysql -u root -p$MYSQL_ROOT_PASSWORD $MYSQL_DATABASE < "$LATEST_BACKUP" 2>> /tmp/restore_log.txt

    echo "Восстановление завершено." >> /tmp/restore_log.txt
else
    echo "Бекап не найден, пропускаю восстановление." >> /tmp/restore_log.txt
fi

# Запуск MySQL после восстановления
exec docker-entrypoint.sh mysqld
