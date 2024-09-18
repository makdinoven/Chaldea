import os
from pydantic import BaseSettings

class Settings(BaseSettings):
    DB_HOST: str = os.getenv("DB_HOST", "mysql")
    DB_PORT: int = os.getenv("DB_PORT", 3306)
    DB_USER: str = os.getenv("DB_USERNAME", "myuser")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "mypassword")
    DB_NAME: str = os.getenv("DB_DATABASE", "mydatabase")
    INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL","http://inventory-service:8004/inventory/")
    SKILLS_SERVICE_URL = os.getenv("SKILLS_SERVICE_URL","http://skills-service:8003/skills/")
    ATTRIBUTES_SERVICE_URL = os.getenv("ATTRIBUTES_SERVICE_URL", "http://character-attributes-service:8002/attributes/")
    # RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672")

settings = Settings()
