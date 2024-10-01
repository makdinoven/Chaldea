from typing import Optional
from pydantic import BaseModel, EmailStr
from datetime import datetime

# Базовая схема пользователя
class UserBase(BaseModel):
    email: EmailStr
    username: str
    role: Optional[str] = 'user'

# Схема для создания пользователя (регистрация)
class UserCreate(UserBase):
    password: str  # Пароль пользователя

# Схема для отображения информации о пользователе
class User(UserBase):
    id: int
    registered_at: datetime
    avatar: Optional[str] = None  # URL аватарки пользователя

    class Config:
        orm_mode = True  # Позволяет Pydantic работать с ORM моделями

# Схема для входа пользователя (логин)
class Login(BaseModel):
    identifier: str
    password: str

class Character_users(BaseModel):
    character_id: int
    id : int
    id_row:int