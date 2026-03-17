from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from config import settings

# Используем асинхронный драйвер (asyncmy или aiomysql вместо pymysql)
# DATABASE_URL можно переопределить через переменную окружения (например, для тестов)
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# Создаем асинхронный движок
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_recycle=3600,
    pool_pre_ping=True
)

Base = declarative_base()

# Используем async_sessionmaker для асинхронных сессий
async_session = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession
)

async def get_db():
    async with async_session() as session:
        yield session

async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)