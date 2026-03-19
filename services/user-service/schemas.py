from typing import Optional, List
from pydantic import BaseModel, EmailStr, validator
from datetime import datetime

# Базовая схема пользователя
class UserBase(BaseModel):
    email: EmailStr
    username: str
    role: Optional[str] = 'user'

    @validator('username')
    def validate_username(cls, v):
        if len(v) < 2:
            raise ValueError('Никнейм должен содержать минимум 2 символа')
        if len(v) > 30:
            raise ValueError('Никнейм не должен превышать 30 символов')
        return v

# Схема для создания пользователя (регистрация)
class UserCreate(UserBase):
    password: str  # Пароль пользователя

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('Пароль должен содержать минимум 6 символов')
        if len(v) > 128:
            raise ValueError('Пароль слишком длинный')
        return v

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

    # RBAC fields
    role_display_name: Optional[str] = None
    permissions: List[str] = []

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
    last_active_at: Optional[datetime] = None

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
    profile_bg_color: Optional[str] = None
    profile_bg_image: Optional[str] = None
    nickname_color: Optional[str] = None
    avatar_frame: Optional[str] = None
    avatar_effect_color: Optional[str] = None
    status_text: Optional[str] = None
    profile_bg_position: Optional[str] = None
    post_color: Optional[str] = None
    profile_style_settings: Optional[dict] = None
    last_active_at: Optional[datetime] = None
    activity_points: int = 0


class UserStatsResponse(BaseModel):
    total_users: int
    online_users: int


class UserPublicItem(BaseModel):
    id: int
    username: str
    avatar: Optional[str] = None
    registered_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class UserListResponse(BaseModel):
    items: List[UserPublicItem]
    total: int
    page: int
    page_size: int


class ProfileSettingsUpdate(BaseModel):
    profile_bg_color: Optional[str] = None
    nickname_color: Optional[str] = None
    avatar_frame: Optional[str] = None
    avatar_effect_color: Optional[str] = None
    status_text: Optional[str] = None
    profile_bg_position: Optional[str] = None
    post_color: Optional[str] = None
    profile_style_settings: Optional[dict] = None


class ProfileSettingsResponse(BaseModel):
    profile_bg_color: Optional[str] = None
    nickname_color: Optional[str] = None
    avatar_frame: Optional[str] = None
    avatar_effect_color: Optional[str] = None
    status_text: Optional[str] = None
    profile_bg_position: Optional[str] = None
    post_color: Optional[str] = None
    profile_style_settings: Optional[dict] = None


class UsernameUpdate(BaseModel):
    username: str


class UsernameUpdateResponse(BaseModel):
    id: int
    username: str
    message: str


class UserCharacterItem(BaseModel):
    id: int
    name: str
    avatar: Optional[str] = None
    level: Optional[int] = None
    rp_posts_count: int = 0
    last_rp_post_date: Optional[datetime] = None
    id_race: Optional[int] = None
    id_class: Optional[int] = None
    id_subrace: Optional[int] = None
    race_name: Optional[str] = None
    class_name: Optional[str] = None
    subrace_name: Optional[str] = None


class UserCharactersResponse(BaseModel):
    characters: List[UserCharacterItem]


# ==================== RBAC Schemas ====================

class RoleResponse(BaseModel):
    id: int
    name: str
    level: int
    description: Optional[str] = None

    class Config:
        orm_mode = True


class PermissionItem(BaseModel):
    id: int
    module: str
    action: str
    description: Optional[str] = None

    class Config:
        orm_mode = True


class PermissionsGroupedResponse(BaseModel):
    """Permissions grouped by module."""
    modules: dict  # {"module_name": [PermissionItem, ...]}


class RoleAssignRequest(BaseModel):
    role_id: int
    display_name: Optional[str] = None


class UserRoleResponse(BaseModel):
    id: int
    username: str
    role: str
    role_display_name: Optional[str] = None
    permissions: List[str] = []


class PermissionOverridesRequest(BaseModel):
    """Permission overrides: grants add permissions, revokes remove them."""
    grants: List[str] = []   # ["module:action", ...]
    revokes: List[str] = []  # ["module:action", ...]


class UserPermissionsResponse(BaseModel):
    id: int
    username: str
    role: str
    permissions: List[str] = []
    overrides: dict = {}  # {"grants": [...], "revokes": [...]}


class EffectivePermissionsResponse(BaseModel):
    user_id: int
    username: str
    role: str
    role_display_name: Optional[str] = None
    role_permissions: List[str] = []
    overrides: dict = {}
    effective_permissions: List[str] = []


class AdminUserItem(BaseModel):
    id: int
    username: str
    email: str
    avatar: Optional[str] = None
    role: Optional[str] = "user"
    role_id: Optional[int] = None
    role_display_name: Optional[str] = None
    registered_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None
    permissions: List[str] = []

    class Config:
        orm_mode = True


class AdminUserListResponse(BaseModel):
    items: List[AdminUserItem]
    total: int
    page: int
    page_size: int


class RolePermissionsRequest(BaseModel):
    permissions: List[str]


class RolePermissionsResponse(BaseModel):
    role_id: int
    role_name: str
    permissions: List[str]