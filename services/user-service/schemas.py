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

# Схема для входа пользователя (логин)
class Login(BaseModel):
    identifier: str
    password: str

class UserCharacterCreate(BaseModel):
    user_id: int
    character_id: int

class UserRead(BaseModel):
    id: int
    email: str
    username: str
    role: str
    avatar: str | None
    registered_at: datetime | None

    class Config:
        orm_mode = True

class LocationShort(BaseModel):
    id: int
    name: str
    image_url: Optional[str] = ""

class CharacterShort(BaseModel):
    id: int
    name: str
    avatar: str
    current_location: Optional[LocationShort] = None

class MeResponse(BaseModel):
    # базовые поля пользователя
    id: int
    email: EmailStr
    username: str
    avatar: Optional[str] = None
    balance: Optional[int] = 0
    role: Optional[str] = "user"

    # новые поля
    current_character_id: Optional[int] = None
    character: Optional[CharacterShort] = None