FROM python:3.10-slim-bullseye as base

WORKDIR /app

# Устанавливаем необходимые системные пакеты
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libmariadb-dev-compat \
    libmariadb-dev \
    pkg-config \
  && rm -rf /var/lib/apt/lists/*

# Копируем requirements.txt (если есть отдельно) и устанавливаем зависимости
COPY ./services/battle-pass-service/app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем всё приложение
COPY ./services/battle-pass-service/app /app

EXPOSE 8012
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8012"]
