from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import settings

# Формируем URL подключения к базе данных
SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{settings.DB_USERNAME}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_DATABASE}"

# Создаем движок базы данных
# character-service is the busiest sync service and fans out to several other
# services per request. SQLAlchemy's default pool (5 + 10 overflow) was too
# small: under concurrent load it hit "QueuePool limit ... reached" and the
# whole service stopped answering, including endpoints that touch no DB.
# Kept at 30 max: MySQL's max_connections is 151, shared by every service.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=15,
    max_overflow=15,
    pool_timeout=10,
    pool_recycle=3600,
    pool_pre_ping=True
    )
# Создаем сессию для работы с базой данных
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Создаем базовый класс для моделей SQLAlchemy
Base = declarative_base()
