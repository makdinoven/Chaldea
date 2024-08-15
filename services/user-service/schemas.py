from pydantic import BaseModel, EmailStr
from datetime import datetime

# Базовая схема пользователя
class UserBase(BaseModel):
    email: EmailStr
    username: str

# Схема для создания пользователя (регистрация)
class UserCreate(UserBase):
    password: str  # Пароль пользователя

# Схема для отображения информации о пользователе
class User(UserBase):
    id: int
    registered_at: datetime

    class Config:
        orm_mode = True  # Позволяет Pydantic работать с ORM моделями

# Схема для входа пользователя (логин)
class Login(BaseModel):
    identifier: str
    password: str
