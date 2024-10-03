FROM mysql:8.0

# Копируем скрипт для восстановления данных
COPY ./docker/mysql/restore.sh /usr/local/bin/restore.sh

# Копируем бекапы в контейнер
COPY ./docker/mysql/backups /backups

EXPOSE 3306
