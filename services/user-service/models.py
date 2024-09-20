from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from database import Base
from sqlalchemy.orm import relationship


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)  # Уникальный идентификатор пользователя
    email = Column(String(255), unique=True, index=True, nullable=False)  # Email пользователя
    username = Column(String(255), unique=True, index=True, nullable=False)  # Никнейм пользователя
    hashed_password = Column(String(255), nullable=False)  # Захешированный пароль
    registered_at = Column(DateTime, default=datetime.utcnow)  # Дата и время регистрации
    role = Column(String(100), default='user')  # Роль пользователя ('user', 'admin', и т.д.)
    avatar = Column(String(255), nullable=True)  # URL аватарки пользователя
    balance = Column(Integer, nullable=True) #Баланс доната
    id_character = Column(Integer, nullable=True) #Номер персонажа