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
COPY ./services/inventory-service/app /app

# Устанавливаем зависимости, указанные в файле requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Устанавливаем Alembic для управления миграциями и другие необходимые пакеты
RUN pip install --no-cache-dir alembic pymysql

# Указываем порт, который будет открыт для доступа к микросервису
EXPOSE 8003

# Команда для запуска FastAPI приложения
CMD ["sh", "-c", "sleep 5 && PYTHONPATH=/app uvicorn main:app --host 0.0.0.0 --port 8003 --app-dir /app"]
