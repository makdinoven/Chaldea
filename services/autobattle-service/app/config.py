import os
from pydantic import BaseSettings


class Settings(BaseSettings):
    # URL боевого микросервиса
    BATTLE_SERVICE_URL: str = os.getenv("BATTLE_SERVICE_URL", "http://battle-service:8010")
    # Redis (общий для всех сервисов)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    # Таймаут хода (сек) – нужен, чтобы не забить очередь автокликов
    TURN_TIMEOUT_S: int = int(os.getenv("TURN_TIMEOUT_S", 3))

    class Config:
        env_file = ".env"


settings = Settings()
