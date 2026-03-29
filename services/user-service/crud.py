from sqlalchemy.orm import Session
from sqlalchemy import or_
from fastapi import HTTPException
from models import *
from schemas import UserCreate
from passlib.context import CryptContext
import re

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEFAULT_AVATAR_URL = "assets/avatars/avatar.png"


def get_effective_permissions(db: Session, user: User) -> list:
    """Compute effective permissions for a user.

    Admin role (name="admin") automatically gets ALL permissions from the
    permissions table.  Other users get their role_permissions plus
    user_permissions overrides (granted=True adds, granted=False removes).
    """
    # Determine role name
    role_name = None
    if user.role_id:
        role = db.query(Role).filter(Role.id == user.role_id).first()
        if role:
            role_name = role.name

    # Fallback to legacy string column
    if not role_name:
        role_name = user.role or "user"

    # Admin gets ALL permissions
    if role_name == "admin":
        all_perms = db.query(Permission).all()
        return [f"{p.module}:{p.action}" for p in all_perms]

    # Get role permissions
    role_perms = set()
    if user.role_id:
        rows = (
            db.query(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id == user.role_id)
            .all()
        )
        role_perms = {(p.module, p.action) for p in rows}

    # Apply user-level overrides
    user_overrides = (
        db.query(UserPermission, Permission)
        .join(Permission, Permission.id == UserPermission.permission_id)
        .filter(UserPermission.user_id == user.id)
        .all()
    )

    effective = set(role_perms)
    for override, perm in user_overrides:
        key = (perm.module, perm.action)
        if override.granted:
            effective.add(key)
        else:
            effective.discard(key)

    return [f"{m}:{a}" for m, a in sorted(effective)]


def require_permission(db: Session, user: User, permission: str):
    """Check that user has a specific permission. Raises 403 if not."""
    perms = get_effective_permissions(db, user)
    if permission not in perms:
        raise HTTPException(status_code=403, detail="Недостаточно прав для выполнения этого действия")


def is_admin(db: Session, user: User) -> bool:
    """Check if user has the admin role."""
    if user.role_id:
        role = db.query(Role).filter(Role.id == user.role_id).first()
        if role and role.name == "admin":
            return True
    # Fallback to legacy string column
    return (user.role or "").lower() == "admin"


def is_admin_or_moderator(db: Session, user: User) -> bool:
    """Check if user has admin or moderator role."""
    if user.role_id:
        role = db.query(Role).filter(Role.id == user.role_id).first()
        if role and role.name in ("admin", "moderator"):
            return True
    # Fallback to legacy string column
    return (user.role or "").lower() in ("admin", "moderator")


def require_admin(db: Session, user: User):
    """Check that user has admin role. Raises 403 if not.

    This is a strict admin-only check (not permission-based) to prevent
    privilege escalation — only admin role can manage roles/permissions.
    """
    if not is_admin(db, user):
        raise HTTPException(
            status_code=403,
            detail="Только администраторы могут выполнять это действие"
        )

# Получение пользователя по email
def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()
# Получение пользователя по емаилу или никнейму
def get_user_by_email_or_username(db: Session, identifier: str):
    # Простая проверка, является ли идентификатор email-адресом
    if re.match(r"[^@]+@[^@]+\.[^@]+", identifier):
        return db.query(User).filter(User.email == identifier).first()
    else:
        return db.query(User).filter(User.username == identifier).first()

# Получение пользователя по никнейму
def get_user_by_username(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()

# Создание нового пользователя
def create_user(db: Session, user: UserCreate):
    hashed_password = pwd_context.hash(user.password)
    db_user = User(
        email=user.email,
        username=user.username,
        hashed_password=hashed_password,
        avatar = DEFAULT_AVATAR_URL
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user

# Аутентификация пользователя
def authenticate_user(db: Session, identifier: str, password: str):
    user = get_user_by_email_or_username(db, identifier)
    if not user or not pwd_context.verify(password, user.hashed_password):
        return False
    return user


# ==================== COSMETICS CRUD ====================

def get_all_frames(db: Session):
    """Get all cosmetic frames."""
    return db.query(CosmeticFrame).order_by(CosmeticFrame.id).all()


def get_all_backgrounds(db: Session):
    """Get all cosmetic backgrounds."""
    return db.query(CosmeticBackground).order_by(CosmeticBackground.id).all()


def get_frame_by_slug(db: Session, slug: str):
    """Get a frame by slug."""
    return db.query(CosmeticFrame).filter(CosmeticFrame.slug == slug).first()


def get_background_by_slug(db: Session, slug: str):
    """Get a background by slug."""
    return db.query(CosmeticBackground).filter(CosmeticBackground.slug == slug).first()


def get_frame_by_id(db: Session, frame_id: int):
    """Get a frame by id."""
    return db.query(CosmeticFrame).filter(CosmeticFrame.id == frame_id).first()


def get_background_by_id(db: Session, bg_id: int):
    """Get a background by id."""
    return db.query(CosmeticBackground).filter(CosmeticBackground.id == bg_id).first()


def get_user_unlocked_frames(db: Session, user_id: int):
    """Get frames user has unlocked + all default frames.

    Returns list of dicts with frame data + source/unlocked_at.
    """
    # Get explicitly unlocked frames
    unlocked = (
        db.query(CosmeticFrame, UserUnlockedFrame)
        .join(UserUnlockedFrame, UserUnlockedFrame.frame_id == CosmeticFrame.id)
        .filter(UserUnlockedFrame.user_id == user_id)
        .all()
    )

    unlocked_ids = {frame.id for frame, unlock in unlocked}

    # Get default frames not already in unlocked set
    defaults = (
        db.query(CosmeticFrame)
        .filter(CosmeticFrame.is_default == True, ~CosmeticFrame.id.in_(unlocked_ids) if unlocked_ids else CosmeticFrame.is_default == True)
        .all()
    )

    items = []
    for frame, unlock in unlocked:
        items.append({
            "id": frame.id,
            "name": frame.name,
            "slug": frame.slug,
            "type": frame.type,
            "css_class": frame.css_class,
            "image_url": frame.image_url,
            "rarity": frame.rarity,
            "is_default": frame.is_default,
            "source": unlock.source,
            "unlocked_at": unlock.unlocked_at,
        })

    for frame in defaults:
        if frame.id not in unlocked_ids:
            items.append({
                "id": frame.id,
                "name": frame.name,
                "slug": frame.slug,
                "type": frame.type,
                "css_class": frame.css_class,
                "image_url": frame.image_url,
                "rarity": frame.rarity,
                "is_default": frame.is_default,
                "source": "default",
                "unlocked_at": None,
            })

    return items


def get_user_unlocked_backgrounds(db: Session, user_id: int):
    """Get backgrounds user has unlocked + all default backgrounds."""
    unlocked = (
        db.query(CosmeticBackground, UserUnlockedBackground)
        .join(UserUnlockedBackground, UserUnlockedBackground.background_id == CosmeticBackground.id)
        .filter(UserUnlockedBackground.user_id == user_id)
        .all()
    )

    unlocked_ids = {bg.id for bg, unlock in unlocked}

    defaults = (
        db.query(CosmeticBackground)
        .filter(CosmeticBackground.is_default == True, ~CosmeticBackground.id.in_(unlocked_ids) if unlocked_ids else CosmeticBackground.is_default == True)
        .all()
    )

    items = []
    for bg, unlock in unlocked:
        items.append({
            "id": bg.id,
            "name": bg.name,
            "slug": bg.slug,
            "type": bg.type,
            "css_class": bg.css_class,
            "image_url": bg.image_url,
            "rarity": bg.rarity,
            "is_default": bg.is_default,
            "source": unlock.source,
            "unlocked_at": unlock.unlocked_at,
        })

    for bg in defaults:
        if bg.id not in unlocked_ids:
            items.append({
                "id": bg.id,
                "name": bg.name,
                "slug": bg.slug,
                "type": bg.type,
                "css_class": bg.css_class,
                "image_url": bg.image_url,
                "rarity": bg.rarity,
                "is_default": bg.is_default,
                "source": "default",
                "unlocked_at": None,
            })

    return items


def user_can_equip_frame(db: Session, user_id: int, slug: str) -> bool:
    """Check if user can equip a frame (it's default or user has unlocked it)."""
    frame = get_frame_by_slug(db, slug)
    if not frame:
        return False
    if frame.is_default:
        return True
    unlock = db.query(UserUnlockedFrame).filter(
        UserUnlockedFrame.user_id == user_id,
        UserUnlockedFrame.frame_id == frame.id,
    ).first()
    return unlock is not None


def user_can_equip_background(db: Session, user_id: int, slug: str) -> bool:
    """Check if user can equip a background (it's default or user has unlocked it)."""
    bg = get_background_by_slug(db, slug)
    if not bg:
        return False
    if bg.is_default:
        return True
    unlock = db.query(UserUnlockedBackground).filter(
        UserUnlockedBackground.user_id == user_id,
        UserUnlockedBackground.background_id == bg.id,
    ).first()
    return unlock is not None


def create_frame(db: Session, data: dict) -> CosmeticFrame:
    """Create a new cosmetic frame."""
    frame = CosmeticFrame(**data)
    db.add(frame)
    db.commit()
    db.refresh(frame)
    return frame


def update_frame(db: Session, frame: CosmeticFrame, data: dict) -> CosmeticFrame:
    """Update a cosmetic frame."""
    for key, value in data.items():
        if value is not None:
            setattr(frame, key, value)
    db.commit()
    db.refresh(frame)
    return frame


def delete_frame(db: Session, frame: CosmeticFrame):
    """Delete a frame and unequip from all users who have it active."""
    # Unequip from users who have this frame active
    db.query(User).filter(User.avatar_frame == frame.slug).update(
        {User.avatar_frame: None}, synchronize_session="fetch"
    )
    db.delete(frame)
    db.commit()


def create_background(db: Session, data: dict) -> CosmeticBackground:
    """Create a new cosmetic background."""
    bg = CosmeticBackground(**data)
    db.add(bg)
    db.commit()
    db.refresh(bg)
    return bg


def update_background(db: Session, bg: CosmeticBackground, data: dict) -> CosmeticBackground:
    """Update a cosmetic background."""
    for key, value in data.items():
        if value is not None:
            setattr(bg, key, value)
    db.commit()
    db.refresh(bg)
    return bg


def delete_background(db: Session, bg: CosmeticBackground):
    """Delete a background and unequip from all users who have it active."""
    db.query(User).filter(User.chat_background == bg.slug).update(
        {User.chat_background: None}, synchronize_session="fetch"
    )
    db.delete(bg)
    db.commit()


def grant_cosmetic_to_user(db: Session, user_id: int, cosmetic_type: str, cosmetic_slug: str, source: str = "admin"):
    """Grant a cosmetic to a user. Idempotent — no error on duplicate.

    Returns (unlocked: bool, reason: str|None).
    """
    if cosmetic_type == "frame":
        frame = get_frame_by_slug(db, cosmetic_slug)
        if not frame:
            raise HTTPException(status_code=404, detail="Рамка не найдена")
        existing = db.query(UserUnlockedFrame).filter(
            UserUnlockedFrame.user_id == user_id,
            UserUnlockedFrame.frame_id == frame.id,
        ).first()
        if existing:
            return False, "already_unlocked"
        unlock = UserUnlockedFrame(user_id=user_id, frame_id=frame.id, source=source)
        db.add(unlock)
        db.commit()
        return True, None
    elif cosmetic_type == "background":
        bg = get_background_by_slug(db, cosmetic_slug)
        if not bg:
            raise HTTPException(status_code=404, detail="Подложка не найдена")
        existing = db.query(UserUnlockedBackground).filter(
            UserUnlockedBackground.user_id == user_id,
            UserUnlockedBackground.background_id == bg.id,
        ).first()
        if existing:
            return False, "already_unlocked"
        unlock = UserUnlockedBackground(user_id=user_id, background_id=bg.id, source=source)
        db.add(unlock)
        db.commit()
        return True, None
    else:
        raise HTTPException(status_code=400, detail="Неверный тип косметики")
