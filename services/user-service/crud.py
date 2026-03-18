from sqlalchemy.orm import Session
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
