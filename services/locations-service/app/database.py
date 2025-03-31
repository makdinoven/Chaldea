from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import settings


# Формируем URL подключения к базе данных для асинхронного движка
SQLALCHEMY_DATABASE_URL = f"mysql+aiomysql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"

# Создаем асинхронный движок базы данных
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_recycle=3600,  # Пересоздавать соединения каждые 1 час
    pool_pre_ping=True
)

# Изменяем создание сессии на асинхронную
async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Создаем базовый класс для моделей SQLAlchemy
Base = declarative_base()

# Обновляем функцию get_db для асинхронной работы
async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()

