from pydantic import BaseSettings


class Settings(BaseSettings):
    DB_HOST: str
    DB_PORT: int = 3306
    DB_USERNAME: str
    DB_PASSWORD: str
    DB_DATABASE: str
    CHARACTER_SERVICE_URL: str = "http://character-service:8005"
    LOCATION_SERVICE_URL: str = "http://locations-service:8006"


settings = Settings()
