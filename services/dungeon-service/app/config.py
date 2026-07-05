import os
from pydantic import BaseSettings


class Settings(BaseSettings):
    DB_HOST: str = os.getenv("DB_HOST", "mysql")
    DB_PORT: int = int(os.getenv("DB_PORT", "3306"))
    DB_USERNAME: str = os.getenv("DB_USERNAME", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "password")
    DB_DATABASE: str = os.getenv("DB_DATABASE", "mydatabase")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    CHARACTER_SERVICE_URL: str = os.getenv("CHARACTER_SERVICE_URL", "http://character-service:8005")
    BATTLE_SERVICE_URL: str = os.getenv("BATTLE_SERVICE_URL", "http://battle-service:8010")
    CHAR_ATTRS_SERVICE_URL: str = os.getenv("CHAR_ATTRS_SERVICE_URL", "http://character-attributes-service:8002")
    INVENTORY_SERVICE_URL: str = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:8004")
    USER_SERVICE_URL: str = os.getenv("USER_SERVICE_URL", "http://user-service:8000")
    PARTY_SERVICE_URL: str = os.getenv("PARTY_SERVICE_URL", "http://party-service:8014")

    class Config:
        env_file = ".env"


settings = Settings()
