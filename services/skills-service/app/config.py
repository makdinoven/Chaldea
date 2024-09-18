import os
from pydantic import BaseSettings

class Settings(BaseSettings):
    DB_HOST: str = os.getenv("DB_HOST", "mysql")
    DB_PORT: int = os.getenv("DB_PORT", 3306)
    DB_USER: str = os.getenv("DB_USERNAME", "myuser")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "mypassword")
    DB_NAME: str = os.getenv("DB_DATABASE", "mydatabase")
    RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672")

settings = Settings()
