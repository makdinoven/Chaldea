FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libmariadb-dev-compat \
    libmariadb-dev \
    pkg-config \
    --no-install-recommends && rm -rf /var/lib/apt/lists/*

COPY ./services/character-service/app/requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копирование приложения должно быть ОТДЕЛЬНО от RUN
COPY ./services/character-service/app /app

EXPOSE 8005

CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8005"]