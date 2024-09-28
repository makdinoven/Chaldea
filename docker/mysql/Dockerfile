FROM mysql:8.0

FROM mysql:8.0

# Копируем скрипт для восстановления базы данных
COPY ./docker/mysql/restore.sh /docker-entrypoint-initdb.d/restore.sh
# Копируем бекапы в контейнер
COPY ./docker/mysql/backups /backups

# Даем права на выполнение скрипта
RUN chmod +x /docker-entrypoint-initdb.d/restore.sh




EXPOSE 3306
