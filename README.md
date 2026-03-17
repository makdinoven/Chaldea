Вс# Chaldea

Браузерная RPG-игра с микросервисной архитектурой.

## Запуск проекта

```bash
docker compose up -d --build
```

## Инициализация базы данных (seed data)

Скрипты в `docker/mysql/init/` выполняются **автоматически при первом запуске** MySQL-контейнера (через механизм `/docker-entrypoint-initdb.d/`):

| Файл | Описание |
|------|----------|
| `01-seed-data.sql` | Игровые данные: страны, регионы, районы, локации, расы, подрасы, классы, навыки, предметы |
| `02-ensure-admin.sql` | Назначение роли `admin` пользователю `chaldea@admin.com` |

Скрипты идемпотентны (`INSERT IGNORE`, условный `UPDATE`), поэтому безопасны при повторном выполнении.

### Первый запуск (автоматически)

При `docker compose up` с чистым volume скрипты выполнятся сами. Ничего делать не нужно.

### Повторная вставка данных (на существующей БД)

Если БД уже существует и нужно применить seed-скрипты заново:

```bash
# Все скрипты по порядку
docker exec -i mysql mysql -u myuser -pmypassword --default-character-set=utf8mb4 mydatabase < docker/mysql/init/01-seed-data.sql
docker exec -i mysql mysql -u myuser -pmypassword --default-character-set=utf8mb4 mydatabase < docker/mysql/init/02-ensure-admin.sql
```

Или по отдельности:

```bash
# Только игровые данные
docker exec -i mysql mysql -u myuser -pmypassword --default-character-set=utf8mb4 mydatabase < docker/mysql/init/01-seed-data.sql

# Только назначение админа
docker exec -i mysql mysql -u myuser -pmypassword --default-character-set=utf8mb4 mydatabase < docker/mysql/init/02-ensure-admin.sql
```

### Полный сброс БД (с нуля)

```bash
docker compose down
docker volume rm chaldea_mysql-data
docker compose up -d --build
```

После пересоздания volume все init-скрипты выполнятся автоматически.
