# battle-service/app/database.py
import os
from sqlalchemy.ext.asyncio import (
    AsyncSession, create_async_engine
)
from sqlalchemy.orm import sessionmaker, declarative_base

DB_HOST = os.getenv("DB_HOST", "mysql")
DB_NAME = os.getenv("DB_DATABASE", "mydatabase")
DB_USER = os.getenv("DB_USERNAME", "myuser")
DB_PASS = os.getenv("DB_PASSWORD", "mypassword")

DATABASE_URL = (
    f"mysql+aiomysql://{DB_USER}:{DB_PASS}@{DB_HOST}:3306/{DB_NAME}"
)

engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


async def get_db():
    """
    Зависимость FastAPI:
        async def route(db: AsyncSession = Depends(get_db)):
    """
    async with AsyncSessionLocal() as session:
        yield session
