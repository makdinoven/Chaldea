from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from datetime import datetime
from database import Base



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
    current_character = Column(Integer, nullable=True, ) #Номер персонажа

class UserCharacter(Base):
    __tablename__ = "users_character"

    user_id = Column(Integer,primary_key=True)
    character_id = Column(Integer,primary_key=True)

class UserAvatarCharacterPreview(Base):
    __tablename__ = "users_avatar_character_preview"
    id = Column(Integer,primary_key=True)
    user_id = Column(Integer,ForeignKey('users.id'))
    avatar =Column(String(255), nullable=True)

class UserAvatarPreview(Base):
    __tablename__ = "users_avatar_preview"
    id = Column(Integer,primary_key=True)
    user_id = Column(Integer,ForeignKey('users.id'))
    avatar =Column(String(255), nullable=True)


class UserPost(Base):
    __tablename__ = "user_posts"

    id = Column(Integer, primary_key=True, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    wall_owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Friendship(Base):
    __tablename__ = "friendships"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    friend_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)