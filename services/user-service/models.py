from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)  # Уникальный идентификатор пользователя
    email = Column(String, unique=True, index=True, nullable=False)  # Email пользователя
    username = Column(String, unique=True, index=True, nullable=False)  # Никнейм пользователя
    hashed_password = Column(String, nullable=False)  # Захешированный пароль
    registered_at = Column(DateTime, default=datetime.utcnow)  # Дата и время регистрации
