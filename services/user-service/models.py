from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, UniqueConstraint, Enum as SAEnum
from sqlalchemy.sql import func
from datetime import datetime
from database import Base


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)  # user, editor, moderator, admin
    level = Column(Integer, nullable=False, default=0)  # Hierarchy level (higher = more access)
    description = Column(String(255), nullable=True)


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    module = Column(String(50), nullable=False)  # e.g. "users", "items", "skills"
    action = Column(String(50), nullable=False)  # e.g. "read", "create", "update", "delete", "manage"
    description = Column(String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint('module', 'action', name='uq_permission_module_action'),
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id = Column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)


class UserPermission(Base):
    __tablename__ = "user_permissions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)
    granted = Column(Boolean, nullable=False, default=True)  # True = grant, False = revoke

    __table_args__ = (
        UniqueConstraint('user_id', 'permission_id', name='uq_user_permission'),
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)  # Уникальный идентификатор пользователя
    email = Column(String(255), unique=True, index=True, nullable=False)  # Email пользователя
    username = Column(String(255), unique=True, index=True, nullable=False)  # Никнейм пользователя
    hashed_password = Column(String(255), nullable=False)  # Захешированный пароль
    registered_at = Column(DateTime, default=datetime.utcnow)  # Дата и время регистрации
    role = Column(String(100), default='user')  # Legacy role string (kept for backward compat)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=True)  # FK to roles table
    role_display_name = Column(String(100), nullable=True)  # Custom display name for the role
    avatar = Column(String(255), nullable=True)  # URL аватарки пользователя
    balance = Column(Integer, nullable=True) #Баланс доната
    current_character = Column(Integer, nullable=True, ) #Номер персонажа
    last_active_at = Column(DateTime, nullable=True, default=None)  # Last activity timestamp
    profile_bg_color = Column(String(7), nullable=True)
    profile_bg_image = Column(String(512), nullable=True)
    nickname_color = Column(String(7), nullable=True)
    avatar_frame = Column(String(50), nullable=True)
    avatar_effect_color = Column(String(7), nullable=True)
    status_text = Column(String(100), nullable=True)
    profile_bg_position = Column(String(20), nullable=True)
    post_color = Column(String(7), nullable=True)
    profile_style_settings = Column(Text, nullable=True)
    activity_points = Column(Integer, nullable=False, default=0, server_default="0")
    diamonds = Column(Integer, nullable=False, default=0, server_default="0")
    message_privacy = Column(
        SAEnum("all", "friends", "nobody", name="message_privacy_enum"),
        nullable=False,
        default="all",
        server_default="all",
    )
    chat_background = Column(String(50), nullable=True)


class CosmeticFrame(Base):
    __tablename__ = "cosmetic_frames"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(50), nullable=False, unique=True, index=True)
    type = Column(String(10), nullable=False, server_default="css")  # css, image, combo
    css_class = Column(String(100), nullable=True)
    image_url = Column(String(500), nullable=True)
    rarity = Column(String(20), nullable=False, server_default="common")  # common, rare, epic, legendary
    is_default = Column(Boolean, nullable=False, server_default="0")
    is_seasonal = Column(Boolean, nullable=False, server_default="0")
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class CosmeticBackground(Base):
    __tablename__ = "cosmetic_backgrounds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(50), nullable=False, unique=True, index=True)
    type = Column(String(10), nullable=False, server_default="css")  # css, image
    css_class = Column(String(100), nullable=True)
    image_url = Column(String(500), nullable=True)
    rarity = Column(String(20), nullable=False, server_default="common")  # common, rare, epic, legendary
    is_default = Column(Boolean, nullable=False, server_default="0")
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class UserUnlockedFrame(Base):
    __tablename__ = "user_unlocked_frames"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    frame_id = Column(Integer, ForeignKey("cosmetic_frames.id", ondelete="CASCADE"), nullable=False)
    source = Column(String(20), nullable=False, server_default="default")  # default, battlepass, admin
    unlocked_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('user_id', 'frame_id', name='uq_user_frame'),
    )


class UserUnlockedBackground(Base):
    __tablename__ = "user_unlocked_backgrounds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    background_id = Column(Integer, ForeignKey("cosmetic_backgrounds.id", ondelete="CASCADE"), nullable=False)
    source = Column(String(20), nullable=False, server_default="default")  # default, battlepass, admin
    unlocked_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('user_id', 'background_id', name='uq_user_background'),
    )


class UserCharacter(Base):
    __tablename__ = "users_character"

    user_id = Column(Integer,primary_key=True)
    character_id = Column(Integer,primary_key=True)


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


class UserBlock(Base):
    __tablename__ = "user_blocks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    blocked_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "blocked_user_id", name="uq_user_block"),
    )