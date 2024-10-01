FROM mysql:8.0

## Копируем скрипт для восстановления данных в контейнер
#COPY ./docker/mysql/restore.sh /usr/local/bin/restore.sh
#
## Копируем бекапы в контейнер
#COPY ./docker/mysql/backups /backups
#
## Даем права на выполнение скрипта
#RUN chmod +x /usr/local/bin/restore.sh
#
## Добавляем команду для выполнения скрипта при старте
#CMD ["bash", "/usr/local/bin/restore.sh", "&&", "docker-entrypoint.sh", "mysqld" ]
#


EXPOSE 3306
