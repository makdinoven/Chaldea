from motor.motor_asyncio import AsyncIOMotorClient
from config import settings

_client: AsyncIOMotorClient | None = None

def get_mongo_db():
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGO_URL)
    return _client.get_default_database()   # db = game