# Базовый образ
FROM python:3.10-slim

# Установка необходимых системных пакетов для работы с зависимостями
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    build-essential \
    libssl-dev \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    libbz2-dev \
    libreadline-dev \
    libsqlite3-dev \
    libjpeg-dev \
    zlib1g-dev \
    python3-distutils \
    python3-venv \
    python3-setuptools \
    && rm -rf /var/lib/apt/lists/*

# Установка директории приложения
WORKDIR /app

# Копирование и установка зависимостей
COPY ./tests/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода

COPY ./tests /app

# Установка дополнительных зависимостей для тестирования
RUN pip install --no-cache-dir pytest pytest-asyncio

# Команда для запуска тестов
CMD ["pytest", "--asyncio-mode=auto"]
