#!/bin/bash

# Директория для хранения бекапов
BACKUP_DIR="./docker/mysql/backups"

# Имя файла бекапа с текущей датой и временем
DATE=$(date +"%Y%m%d%H%M")
BACKUP_FILE="$BACKUP_DIR/db_backup_$DATE.sql"

# Команда для создания бекапа базы данных
docker exec -i chaldea_mysql_1 mysqldump -u root -p$MYSQL_ROOT_PASSWORD mydatabase > $BACKUP_FILE

echo "Бекап базы данных сохранен в $BACKUP_FILE"
