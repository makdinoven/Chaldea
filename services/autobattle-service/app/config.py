import os
from pydantic import BaseSettings

class Settings(BaseSettings):
    BATTLE_SERVICE_URL: str = os.getenv("BATTLE_SERVICE_URL", "http://battle-service:8010")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")

settings = Settings()
