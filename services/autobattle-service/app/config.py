import os
from pydantic import BaseSettings


class Settings(BaseSettings):
    # URL боевого микросервиса
    BATTLE_SERVICE_URL: str = os.getenv("BATTLE_SERVICE_URL", "http://battle-service:8010")
    # URL сервиса персонажей (для проверки владения)
    CHARACTER_SERVICE_URL: str = os.getenv("CHARACTER_SERVICE_URL", "http://character-service:8005")
    # Redis (общий для всех сервисов)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    # Таймаут хода (сек) – нужен, чтобы не забить очередь автокликов
    TURN_TIMEOUT_S: int = int(os.getenv("TURN_TIMEOUT_S", 3))
    # Задержка медленного автобоя (сек)
    AUTOBATTLE_SLOW_DELAY: float = float(os.getenv("AUTOBATTLE_SLOW_DELAY", 3.0))

    class Config:
        env_file = ".env"


settings = Settings()
