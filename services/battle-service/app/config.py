import os
from pydantic import BaseSettings


class Settings(BaseSettings):
    # из docker‑compose.env
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672//")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://mongo:27017")
    TURN_TIMEOUT_HOURS: int = int(os.getenv("TURN_TIMEOUT_HOURS", 24))
    CHARACTER_SERVICE_URL: str = os.getenv("CHARACTER_SERVICE_URL", "http://character-service:8005")
    SKILLS_URL = os.getenv("SKILLS_SERVICE_URL", "http://skills-service:8003")
    INVENTORY_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:8004")
    INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:8004")

    class Config:
        env_file = ".env"


settings = Settings()