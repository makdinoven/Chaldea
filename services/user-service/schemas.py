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
    level: Optional[int] = None
    current_location: Optional[LocationShort] = None

class ClearCurrentCharacterRequest(BaseModel):
    character_id: int

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


class PostCreate(BaseModel):
    content: str


class PostResponse(BaseModel):
    id: int
    author_id: int
    author_username: str
    author_avatar: Optional[str] = None
    wall_owner_id: int
    content: str
    created_at: datetime

    class Config:
        orm_mode = True


class PostStatsResponse(BaseModel):
    total_posts: int
    last_post_date: Optional[datetime] = None


class FriendshipRequest(BaseModel):
    friend_id: int


class FriendshipResponse(BaseModel):
    id: int
    user_id: int
    friend_id: int
    status: str
    created_at: datetime

    class Config:
        orm_mode = True


class FriendResponse(BaseModel):
    id: int
    username: str
    avatar: Optional[str] = None

    class Config:
        orm_mode = True


class FriendRequestResponse(BaseModel):
    id: int
    user: FriendResponse
    created_at: datetime


class UserProfileResponse(BaseModel):
    id: int
    username: str
    avatar: Optional[str] = None
    registered_at: Optional[datetime] = None
    character: Optional[CharacterShort] = None
    post_stats: PostStatsResponse
    is_friend: Optional[bool] = None
    friendship_status: Optional[str] = None
    friendship_id: Optional[int] = None