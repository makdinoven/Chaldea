from pydantic import BaseSettings

class Settings(BaseSettings):
    DB_HOST: str
    DB_PORT: int = 3306
    DB_USERNAME: str
    DB_PASSWORD: str
    DB_DATABASE: str
    INVENTORY_SERVICE_URL: str = "http://inventory-service:8004/inventory/"
    SKILLS_SERVICE_URL: str = "http://skills-service:8003/skills/"
    ATTRIBUTES_SERVICE_URL: str = "http://character-attributes-service:8002/attributes/"
    USER_SERVICE_URL: str = "http://user-service:8000"
    RABBITMQ_URL: str = "amqp://guest:guest@rabbitmq:5672/"

settings = Settings()
