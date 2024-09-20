# Используем образ Python 3.10 в качестве базового
FROM python:3.10-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Устанавливаем системные зависимости для сборки пакета mysqlclient и скачиваем dockerize и tini
RUN apt-get update && apt-get install -y \
    gcc \
    libmariadb-dev-compat \
    libmariadb-dev \
    pkg-config \
    wget \
    tini \
    --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Устанавливаем dockerize
RUN wget https://github.com/jwilder/dockerize/releases/download/v0.6.1/dockerize-linux-amd64-v0.6.1.tar.gz \
    && tar -C /usr/local/bin -xzvf dockerize-linux-amd64-v0.6.1.tar.gz \
    && rm dockerize-linux-amd64-v0.6.1.tar.gz

# Копируем файлы проекта в рабочую директорию контейнера
COPY ./services/character-service/app /app

# Устанавливаем зависимости, указанные в файле requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Устанавливаем Alembic для управления миграциями и другие необходимые пакеты
RUN pip install --no-cache-dir alembic pymysql

# Указываем порт, который будет открыт для доступа к микросервису
EXPOSE 8005

CMD ["sh", "-c", "PYTHONPATH=/app uvicorn main:app --host 0.0.0.0 --port 8005 --app-dir /app "]
