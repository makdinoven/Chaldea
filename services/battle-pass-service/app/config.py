from pydantic import BaseSettings


class Settings(BaseSettings):
    DB_HOST: str
    DB_PORT: int = 3306
    DB_USERNAME: str
    DB_PASSWORD: str
    DB_DATABASE: str
    CORS_ORIGINS: str = "*"
    CHARACTER_SERVICE_URL: str = "http://character-service:8005"
    INVENTORY_SERVICE_URL: str = "http://inventory-service:8004"
    USER_SERVICE_URL: str = "http://user-service:8000"


settings = Settings()
