from pydantic import BaseSettings

class Settings(BaseSettings):
    DB_HOST: str
    DB_PORT: int = 3306
    DB_USERNAME: str
    DB_PASSWORD: str
    DB_DATABASE: str
    RABBITMQ_URL: str = "amqp://guest:guest@rabbitmq:5672"
    CHARACTER_SERVICE_URL: str = "http://character-service:8005"
    ATTRIBUTES_SERVICE_URL: str = "http://character-attributes-service:8002"

settings = Settings()
