from pydantic import BaseSettings


class Settings(BaseSettings):
    DB_HOST: str
    DB_PORT: int = 3306
    DB_USERNAME: str
    DB_PASSWORD: str
    DB_DATABASE: str

    # Cross-service (party-service reads the shared `characters` table directly for
    # ownership/location, and calls attributes-service to charge active XP on create).
    CHARACTER_SERVICE_URL: str = "http://character-service:8005"
    ATTRIBUTES_SERVICE_URL: str = "http://character-attributes-service:8002/attributes/"

    # Party rules (FEAT-144).
    PARTY_MAX_SIZE: int = 4            # leader + 3
    PARTY_CREATE_COST_ACTIVE_XP: int = 0   # 0 while testing
    PARTY_XP_BONUS_PCT: int = 10      # +10% (used from Ф2)

    CORS_ORIGINS: str = "*"


settings = Settings()
