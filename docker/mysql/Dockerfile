FROM mysql:8.0

# Копируем скрипт для восстановления данных
COPY ./docker/mysql/restore.sh /usr/local/bin/restore.sh


# Копируем бекапы в контейнер
COPY ./docker/mysql/backups /backups

# Init-скрипты НЕ копируются в docker-entrypoint-initdb.d/ —
# таблицы создаются через Alembic миграции в сервисах,
# seed-данные загружаются после старта через seed.sh
# COPY ./docker/mysql/init /docker-entrypoint-initdb.d/

EXPOSE 3306
