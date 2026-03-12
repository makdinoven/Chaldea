FROM mysql:8.0

# Копируем скрипт для восстановления данных
COPY ./docker/mysql/restore.sh /usr/local/bin/restore.sh


# Копируем бекапы в контейнер
COPY ./docker/mysql/backups /backups

# Копируем init-скрипты (выполняются при первом запуске БД)
COPY ./docker/mysql/init /docker-entrypoint-initdb.d/

EXPOSE 3306
