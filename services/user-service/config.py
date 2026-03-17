from pydantic import BaseSettings


class Settings(BaseSettings):
    DB_HOST: str = "mysql"
    DB_PORT: int = 3306
    DB_USERNAME: str = "myuser"
    DB_PASSWORD: str = "mypassword"
    DB_DATABASE: str = "mydatabase"

    class Config:
        env_file = ".env"


settings = Settings()
