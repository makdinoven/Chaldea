# Используем образ Python 3.10 в качестве базового
FROM python:3.10-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Устанавливаем системные зависимости для сборки пакета mysqlclient
RUN apt-get update && apt-get install -y \
    gcc \
    libmariadb-dev-compat \
    libmariadb-dev \
    pkg-config \
    --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Копируем файлы проекта в рабочую директорию контейнера
COPY ./services/user-service /app

# Устанавливаем зависимости, указанные в файле requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Устанавливаем Alembic для управления миграциями
RUN pip install --no-cache-dir alembic

# Копируем директорию alembic и конфигурационный файл alembic.ini в контейнер
COPY .alembic.ini /app/alembic.ini
COPY .alembic /app/alembic

# Указываем порт, который будет открыт для доступа к микросервису
EXPOSE 8000

# Команда для запуска миграций и FastAPI приложения
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000 --app-dir /app"]
