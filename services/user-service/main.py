from typing import List, Optional

from fastapi import BackgroundTasks, FastAPI, Depends, HTTPException, status, APIRouter, Query
from fastapi.security import OAuth2PasswordBearer
import models
import schemas
from crud import create_user, get_user_by_email, get_user_by_username, authenticate_user, get_effective_permissions, require_permission, require_admin, is_admin, is_admin_or_moderator
from auth import *
from auth import SECRET_KEY, ALGORITHM
from database import SessionLocal, engine, get_db
from jose import JWTError, jwt
import os
from fastapi.middleware.cors import CORSMiddleware
from producer import send_notification_event
import httpx
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
import bleach
import re
import asyncio

ALLOWED_TAGS = [
    "p", "br", "strong", "em", "u", "s",
    "h1", "h2", "h3",
    "ul", "ol", "li",
    "blockquote",
    "a", "img", "span", "mark",
    "figure", "div",
    "pre", "code",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "target", "rel", "class"],
    "img": ["src", "alt", "class", "width", "height"],
    "span": ["style", "class"],
    "mark": ["style", "data-color", "class"],
    "figure": ["data-type", "data-align", "style", "class"],
    "div": ["style", "class", "data-node-view-wrapper"],
    "p": ["style", "class"],
    "h1": ["style", "class"],
    "h2": ["style", "class"],
    "h3": ["style", "class"],
}

ALLOWED_CSS_PROPERTIES = [
    "color", "background-color", "text-align", "width",
    "max-width", "display",
    "margin", "margin-top", "margin-bottom", "margin-left", "margin-right",
    "padding", "padding-top", "padding-bottom", "padding-left", "padding-right",
]

from bleach.css_sanitizer import CSSSanitizer

_css_sanitizer = CSSSanitizer(allowed_css_properties=ALLOWED_CSS_PROPERTIES)

def sanitize_html(html: str) -> str:
    """Sanitize HTML content, allowing safe tags and styles from WYSIWYG editor."""
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        css_sanitizer=_css_sanitizer,
        strip=True,
    )

app = FastAPI()

cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/users")

CHARACTER_SERVICE_URL = os.getenv("CHARACTER_SERVICE_URL", "http://character-service:8005")
LOCATION_SERVICE_URL = os.getenv("LOCATION_SERVICE_URL", "http://locations-service:8006")

# Optional OAuth2 scheme that doesn't raise 401 when no token is present
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)


def get_optional_user(
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(optional_oauth2_scheme),
):
    """Returns current user if valid token provided, None otherwise."""
    if token is None:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            return None
        user = get_user_by_email(db, email=email)
        return user
    except JWTError:
        return None


async def _fetch_character_short(char_id: int):
    """Fetch character short info + location, reused by /me and /profile."""
    char_url = f"{CHARACTER_SERVICE_URL}/characters/{char_id}/short_info"
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(char_url)
            resp.raise_for_status()
        except Exception:
            return None

        ch_json = resp.json()

        loc_json = None
        loc_id = ch_json.get("current_location_id")
        if loc_id:
            loc_url = f"{LOCATION_SERVICE_URL}/locations/{loc_id}/details"
            try:
                loc_resp = await client.get(loc_url)
                if loc_resp.status_code == 200:
                    lj = loc_resp.json()
                    loc_json = {
                        "id": lj["id"],
                        "name": lj["name"],
                        "image_url": lj.get("image_url") or ""
                    }
            except Exception:
                pass

        return {
            "id": ch_json["id"],
            "name": ch_json["name"],
            "avatar": ch_json["avatar"],
            "level": ch_json.get("level"),
            "current_location": loc_json
        }


# ==================== AUTH & REGISTRATION ====================

@router.post("/register")
def register_user(user: UserCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    db_user_email = get_user_by_email(db, email=user.email)
    if db_user_email:
        raise HTTPException(status_code=400, detail="Этот email уже зарегистрирован")

    db_user_username = get_user_by_username(db, username=user.username)
    if db_user_username:
        raise HTTPException(status_code=400, detail="Этот никнейм уже занят")

    new_user = create_user(db=db, user=user)
    background_tasks.add_task(send_notification_event, new_user.id)

    token_data = {"sub": new_user.email}
    access_token = create_access_token(data=token_data, role=new_user.role)
    refresh_token = create_refresh_token(data=token_data, role=new_user.role)
    return {"access_token": access_token, "refresh_token": refresh_token}


@router.post("/login")
def login_user(data: Login, db: Session = Depends(get_db)):
    user = authenticate_user(db, data.identifier, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль"
        )

    token_data = {"sub": user.email}
    if user.current_character is not None:
        token_data["current_character"] = user.current_character

    access_token = create_access_token(data=token_data, role=user.role)
    refresh_token = create_refresh_token(data=token_data, role=user.role)
    return {"access_token": access_token, "refresh_token": refresh_token}


@router.post("/refresh")
def refresh_token(refresh_token: str, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = get_user_by_email(db, email=email)
    if user is None:
        raise credentials_exception

    new_access_token = create_access_token(data={"sub": user.email}, role=user.role)
    return {"access_token": new_access_token, "token_type": "bearer"}


# ==================== CURRENT USER ====================

@router.get("/me", response_model=schemas.MeResponse)
async def read_users_me(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Update last_active_at for online tracking.
    # current_user may be bound to a different session (from get_current_user),
    # so we update via a direct query on the handler's db session.
    # Wrapped in try/except so the endpoint still works if the migration
    # adding last_active_at has not been applied yet.
    try:
        db.query(models.User).filter(models.User.id == current_user.id).update(
            {models.User.last_active_at: datetime.utcnow()}
        )
        db.commit()
    except Exception:
        db.rollback()

    # Compute role name from roles table, fallback to legacy string column
    role_name = current_user.role or "user"
    if current_user.role_id:
        role_obj = db.query(models.Role).filter(models.Role.id == current_user.role_id).first()
        if role_obj:
            role_name = role_obj.name

    permissions = get_effective_permissions(db, current_user)

    me_data = {
        "id": current_user.id,
        "email": current_user.email,
        "username": current_user.username,
        "avatar": current_user.avatar,
        "balance": current_user.balance,
        "role": role_name,
        "role_display_name": current_user.role_display_name,
        "permissions": permissions,
        "current_character_id": current_user.current_character,
        "character": None
    }

    if current_user.current_character:
        char_data = await _fetch_character_short(current_user.current_character)
        if char_data:
            me_data["character"] = char_data

    return schemas.MeResponse(**me_data)


# ==================== PROFILE SETTINGS & USERNAME ====================

HEX_COLOR_REGEX = re.compile(r'^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$')
BG_POSITION_REGEX = re.compile(r'^\d{1,3}%\s\d{1,3}%$')
ALLOWED_FRAMES = {"gold", "silver", "fire"}
USERNAME_REGEX = re.compile(r'^[a-zA-Zа-яА-ЯёЁ0-9_-]+$')


@router.put("/me/settings", response_model=schemas.ProfileSettingsResponse)
def update_profile_settings(
    data: schemas.ProfileSettingsUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Обновить настройки кастомизации профиля."""
    # Validate hex colors
    for field_name in ('profile_bg_color', 'nickname_color', 'avatar_effect_color'):
        value = getattr(data, field_name)
        if value is not None and not HEX_COLOR_REGEX.match(value):
            raise HTTPException(
                status_code=422,
                detail=f"Некорректный формат цвета для {field_name}. Ожидается HEX (например, #fff или #1a1a2e)"
            )

    # Validate avatar_frame
    if data.avatar_frame is not None and data.avatar_frame not in ALLOWED_FRAMES:
        raise HTTPException(
            status_code=422,
            detail=f"Недопустимая рамка. Допустимые значения: {', '.join(ALLOWED_FRAMES)}"
        )

    # Validate status_text
    if data.status_text is not None and len(data.status_text) > 100:
        raise HTTPException(
            status_code=422,
            detail="Статус слишком длинный. Максимум 100 символов"
        )

    # Validate profile_bg_position
    if data.profile_bg_position is not None:
        if not BG_POSITION_REGEX.match(data.profile_bg_position):
            raise HTTPException(
                status_code=422,
                detail="Некорректный формат позиции фона. Ожидается формат '50% 50%' (два процента от 0 до 100)"
            )
        parts = data.profile_bg_position.replace('%', '').split()
        if not all(0 <= int(p) <= 100 for p in parts):
            raise HTTPException(
                status_code=422,
                detail="Значения позиции фона должны быть от 0% до 100%"
            )

    # Update only provided fields
    user = db.query(models.User).filter(models.User.id == current_user.id).first()

    update_fields = data.dict(exclude_unset=True)
    for field_name, value in update_fields.items():
        if field_name == 'status_text' and value is not None:
            value = bleach.clean(value, tags=[], strip=True)
        setattr(user, field_name, value)

    db.commit()
    db.refresh(user)

    return schemas.ProfileSettingsResponse(
        profile_bg_color=user.profile_bg_color,
        nickname_color=user.nickname_color,
        avatar_frame=user.avatar_frame,
        avatar_effect_color=user.avatar_effect_color,
        status_text=user.status_text,
        profile_bg_position=user.profile_bg_position,
    )


@router.put("/me/username", response_model=schemas.UsernameUpdateResponse)
def update_username(
    data: schemas.UsernameUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Сменить никнейм пользователя."""
    username = data.username.strip()

    if not username:
        raise HTTPException(status_code=400, detail="Никнейм не может быть пустым")

    if len(username) > 32:
        raise HTTPException(status_code=400, detail="Никнейм слишком длинный. Максимум 32 символа")

    if not USERNAME_REGEX.match(username):
        raise HTTPException(status_code=400, detail="Никнейм содержит недопустимые символы")

    # Uniqueness check
    existing = get_user_by_username(db, username=username)
    if existing and existing.id != current_user.id:
        raise HTTPException(status_code=400, detail="Этот никнейм уже занят")

    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    user.username = username

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Этот никнейм уже занят")

    db.refresh(user)

    return schemas.UsernameUpdateResponse(
        id=user.id,
        username=user.username,
        message="Никнейм успешно изменён",
    )


# ==================== CHARACTER RELATIONS ====================

@router.put("/{user_id}/update_character")
async def update_user_character(user_id: int, character_data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if user_id != current_user.id:
        if not is_admin_or_moderator(db, current_user):
            raise HTTPException(status_code=403, detail="Вы можете менять только своего активного персонажа")
    character_id = character_data.get("current_character")
    if character_id is None:
        raise HTTPException(status_code=400, detail="current_character обязателен")

    character_relation = db.query(models.UserCharacter).filter(
        models.UserCharacter.user_id == user_id,
        models.UserCharacter.character_id == character_id
    ).first()

    if not character_relation:
        raise HTTPException(status_code=400, detail="У пользователя нет доступа к этому персонажу")

    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    db_user.current_character = character_id
    db.commit()
    return {
        "message": f"Пользователь с ID {user_id} успешно обновлен",
        "current_character": db_user.current_character
    }


@router.post("/user_characters/")
async def create_user_character_relation(user_character: schemas.UserCharacterCreate, db: Session = Depends(get_db)):
    db_relation = models.UserCharacter(user_id=user_character.user_id, character_id=user_character.character_id)
    db.add(db_relation)
    db.commit()
    return {"message": "Связь между пользователем и персонажем создана"}


@router.delete("/user_characters/{user_id}/{character_id}")
def delete_user_character_relation(
    user_id: int,
    character_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_permission(db, current_user, "users:manage")

    relation = db.query(models.UserCharacter).filter(
        models.UserCharacter.user_id == user_id,
        models.UserCharacter.character_id == character_id,
    ).first()

    if not relation:
        raise HTTPException(status_code=404, detail="User-character relation not found")

    db.delete(relation)
    db.commit()
    return {"detail": "User-character relation deleted"}


@router.post("/{user_id}/clear_current_character")
def clear_current_character(
    user_id: int,
    body: schemas.ClearCurrentCharacterRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_permission(db, current_user, "users:manage")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.current_character == body.character_id:
        user.current_character = None
        db.commit()

    return {"detail": "Current character cleared"}


# ==================== USER LISTS & STATS ====================

ONLINE_THRESHOLD_MINUTES = 5


@router.get("/stats", response_model=schemas.UserStatsResponse)
def get_user_stats(db: Session = Depends(get_db)):
    """Public endpoint: total registered users and currently online users."""
    total_users = db.query(func.count(models.User.id)).scalar()
    try:
        threshold = datetime.utcnow() - timedelta(minutes=ONLINE_THRESHOLD_MINUTES)
        online_users = db.query(func.count(models.User.id)).filter(
            models.User.last_active_at >= threshold
        ).scalar()
    except Exception:
        db.rollback()
        online_users = 0
    return schemas.UserStatsResponse(total_users=total_users, online_users=online_users)


@router.get("/online", response_model=schemas.UserListResponse)
def get_online_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Public endpoint: paginated list of online users (active in last 5 min)."""
    try:
        threshold = datetime.utcnow() - timedelta(minutes=ONLINE_THRESHOLD_MINUTES)
        base_query = db.query(models.User).filter(models.User.last_active_at >= threshold)
        total = base_query.count()
        users = (
            base_query
            .order_by(models.User.last_active_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
    except Exception:
        db.rollback()
        total = 0
        users = []
    return schemas.UserListResponse(
        items=[schemas.UserPublicItem.from_orm(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/all", response_model=schemas.UserListResponse)
def get_all_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Public endpoint: paginated list of all registered users."""
    total = db.query(models.User).count()
    users = (
        db.query(models.User)
        .order_by(models.User.registered_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.UserListResponse(
        items=[schemas.UserPublicItem.from_orm(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/admins", response_model=List[UserRead])
def get_admin_users(db: Session = Depends(get_db)):
    # Query by role_id (admin role_id=4) with fallback to legacy role string
    admin_role = db.query(models.Role).filter(models.Role.name == "admin").first()
    if admin_role:
        admins = db.query(models.User).filter(models.User.role_id == admin_role.id).all()
    else:
        # Fallback if roles table not yet populated
        admins = db.query(models.User).filter(models.User.role == "admin").all()
    return admins


# ==================== RBAC MANAGEMENT ====================

@router.get("/roles", response_model=List[schemas.RoleResponse])
def list_roles(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Список всех ролей. Только для администраторов."""
    require_admin(db, current_user)
    roles = db.query(models.Role).order_by(models.Role.level.asc()).all()
    return roles


@router.put("/{user_id}/role", response_model=schemas.UserRoleResponse)
def assign_user_role(
    user_id: int,
    body: schemas.RoleAssignRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Назначить роль пользователю. Только для администраторов."""
    require_admin(db, current_user)

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    new_role = db.query(models.Role).filter(models.Role.id == body.role_id).first()
    if not new_role:
        raise HTTPException(status_code=404, detail="Роль не найдена")

    # Last admin protection
    if user.role_id:
        current_role = db.query(models.Role).filter(models.Role.id == user.role_id).first()
        if current_role and current_role.name == "admin" and new_role.name != "admin":
            admin_role = db.query(models.Role).filter(models.Role.name == "admin").first()
            if admin_role:
                admin_count = db.query(models.User).filter(
                    models.User.role_id == admin_role.id
                ).count()
                if admin_count <= 1:
                    raise HTTPException(
                        status_code=409,
                        detail="Нельзя снять роль администратора с последнего админа"
                    )

    # Update role
    user.role_id = new_role.id
    user.role = new_role.name  # Sync legacy string column
    user.role_display_name = body.display_name

    db.commit()
    db.refresh(user)

    permissions = get_effective_permissions(db, user)

    return schemas.UserRoleResponse(
        id=user.id,
        username=user.username,
        role=new_role.name,
        role_display_name=user.role_display_name,
        permissions=permissions,
    )


@router.get("/permissions", response_model=schemas.PermissionsGroupedResponse)
def list_permissions(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Список всех разрешений, сгруппированных по модулю. Только для администраторов."""
    require_admin(db, current_user)

    all_perms = db.query(models.Permission).order_by(
        models.Permission.module, models.Permission.action
    ).all()

    modules: dict = {}
    for perm in all_perms:
        if perm.module not in modules:
            modules[perm.module] = []
        modules[perm.module].append(schemas.PermissionItem(
            id=perm.id,
            module=perm.module,
            action=perm.action,
            description=perm.description,
        ))

    return schemas.PermissionsGroupedResponse(modules=modules)


@router.put("/{user_id}/permissions", response_model=schemas.UserPermissionsResponse)
def set_user_permission_overrides(
    user_id: int,
    body: schemas.PermissionOverridesRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Установить индивидуальные разрешения пользователю. Только для администраторов."""
    require_admin(db, current_user)

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Cannot set overrides for admin-role users
    if is_admin(db, user):
        raise HTTPException(
            status_code=400,
            detail="Невозможно изменить разрешения администратора"
        )

    # Validate all permission strings and collect Permission objects
    grant_perms = []
    for perm_str in body.grants:
        if ":" not in perm_str:
            raise HTTPException(
                status_code=422,
                detail=f"Некорректный формат разрешения: '{perm_str}'. Ожидается 'модуль:действие'"
            )
        module, action = perm_str.split(":", 1)
        perm = db.query(models.Permission).filter(
            models.Permission.module == module,
            models.Permission.action == action,
        ).first()
        if not perm:
            raise HTTPException(
                status_code=422,
                detail=f"Разрешение '{perm_str}' не найдено"
            )
        grant_perms.append(perm)

    revoke_perms = []
    for perm_str in body.revokes:
        if ":" not in perm_str:
            raise HTTPException(
                status_code=422,
                detail=f"Некорректный формат разрешения: '{perm_str}'. Ожидается 'модуль:действие'"
            )
        module, action = perm_str.split(":", 1)
        perm = db.query(models.Permission).filter(
            models.Permission.module == module,
            models.Permission.action == action,
        ).first()
        if not perm:
            raise HTTPException(
                status_code=422,
                detail=f"Разрешение '{perm_str}' не найдено"
            )
        revoke_perms.append(perm)

    # Clear existing overrides
    db.query(models.UserPermission).filter(
        models.UserPermission.user_id == user_id
    ).delete()

    # Insert new overrides
    for perm in grant_perms:
        db.add(models.UserPermission(
            user_id=user_id,
            permission_id=perm.id,
            granted=True,
        ))

    for perm in revoke_perms:
        db.add(models.UserPermission(
            user_id=user_id,
            permission_id=perm.id,
            granted=False,
        ))

    db.commit()

    # Build response
    effective = get_effective_permissions(db, user)

    # Get role name
    role_name = user.role or "user"
    if user.role_id:
        role_obj = db.query(models.Role).filter(models.Role.id == user.role_id).first()
        if role_obj:
            role_name = role_obj.name

    return schemas.UserPermissionsResponse(
        id=user.id,
        username=user.username,
        role=role_name,
        permissions=effective,
        overrides={
            "grants": [f"{p.module}:{p.action}" for p in grant_perms],
            "revokes": [f"{p.module}:{p.action}" for p in revoke_perms],
        },
    )


@router.get("/{user_id}/effective-permissions", response_model=schemas.EffectivePermissionsResponse)
def get_user_effective_permissions(
    user_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Получить эффективные разрешения пользователя. Только для администраторов."""
    require_admin(db, current_user)

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Get role info
    role_name = user.role or "user"
    if user.role_id:
        role_obj = db.query(models.Role).filter(models.Role.id == user.role_id).first()
        if role_obj:
            role_name = role_obj.name

    # Get role permissions
    role_perms = []
    if user.role_id:
        rows = (
            db.query(models.Permission)
            .join(models.RolePermission, models.RolePermission.permission_id == models.Permission.id)
            .filter(models.RolePermission.role_id == user.role_id)
            .all()
        )
        role_perms = [f"{p.module}:{p.action}" for p in rows]

    # Get overrides
    user_overrides = (
        db.query(models.UserPermission, models.Permission)
        .join(models.Permission, models.Permission.id == models.UserPermission.permission_id)
        .filter(models.UserPermission.user_id == user.id)
        .all()
    )

    grants = []
    revokes = []
    for override, perm in user_overrides:
        perm_str = f"{perm.module}:{perm.action}"
        if override.granted:
            grants.append(perm_str)
        else:
            revokes.append(perm_str)

    # Effective permissions
    effective = get_effective_permissions(db, user)

    return schemas.EffectivePermissionsResponse(
        user_id=user.id,
        username=user.username,
        role=role_name,
        role_display_name=user.role_display_name,
        role_permissions=sorted(role_perms),
        overrides={
            "grants": sorted(grants),
            "revokes": sorted(revokes),
        },
        effective_permissions=effective,
    )


# ==================== ADMIN USER LIST ====================

@router.get("/admin/list", response_model=schemas.AdminUserListResponse)
def admin_list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    role_id: Optional[int] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Список пользователей с ролями и разрешениями для админ-панели."""
    require_admin(db, current_user)

    query = db.query(models.User)

    # Search by username or email
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (models.User.username.ilike(search_pattern)) |
            (models.User.email.ilike(search_pattern))
        )

    # Filter by role_id
    if role_id is not None:
        query = query.filter(models.User.role_id == role_id)

    total = query.count()

    users = (
        query.order_by(models.User.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for user in users:
        # Get role name from roles table, fallback to legacy string
        role_name = user.role or "user"
        if user.role_id:
            role_obj = db.query(models.Role).filter(models.Role.id == user.role_id).first()
            if role_obj:
                role_name = role_obj.name

        permissions = get_effective_permissions(db, user)

        items.append(schemas.AdminUserItem(
            id=user.id,
            username=user.username,
            email=user.email,
            avatar=user.avatar,
            role=role_name,
            role_id=user.role_id,
            role_display_name=user.role_display_name,
            registered_at=user.registered_at,
            last_active_at=user.last_active_at,
            permissions=permissions,
        ))

    return schemas.AdminUserListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


# ==================== ROLE PERMISSIONS ====================

@router.get("/roles/{role_id}/permissions", response_model=schemas.RolePermissionsResponse)
def get_role_permissions(
    role_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Получить разрешения для конкретной роли. Только для администраторов."""
    require_admin(db, current_user)

    role = db.query(models.Role).filter(models.Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Роль не найдена")

    role_perms = (
        db.query(models.Permission)
        .join(models.RolePermission, models.RolePermission.permission_id == models.Permission.id)
        .filter(models.RolePermission.role_id == role_id)
        .order_by(models.Permission.module, models.Permission.action)
        .all()
    )

    return schemas.RolePermissionsResponse(
        role_id=role.id,
        role_name=role.name,
        permissions=[f"{p.module}:{p.action}" for p in role_perms],
    )


@router.put("/roles/{role_id}/permissions", response_model=schemas.RolePermissionsResponse)
def set_role_permissions(
    role_id: int,
    body: schemas.RolePermissionsRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Установить разрешения для роли. Только для администраторов."""
    require_admin(db, current_user)

    role = db.query(models.Role).filter(models.Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Роль не найдена")

    # Cannot modify admin role permissions
    if role.name == "admin":
        raise HTTPException(
            status_code=400,
            detail="Невозможно изменить разрешения администратора — администратор всегда имеет все права",
        )

    # Validate all permission strings and collect Permission objects
    perm_objects = []
    for perm_str in body.permissions:
        if ":" not in perm_str:
            raise HTTPException(
                status_code=422,
                detail=f"Некорректный формат разрешения: '{perm_str}'. Ожидается 'модуль:действие'",
            )
        module, action = perm_str.split(":", 1)
        perm = db.query(models.Permission).filter(
            models.Permission.module == module,
            models.Permission.action == action,
        ).first()
        if not perm:
            raise HTTPException(
                status_code=422,
                detail=f"Разрешение '{perm_str}' не найдено",
            )
        perm_objects.append(perm)

    # Replace all existing role_permissions for this role
    db.query(models.RolePermission).filter(
        models.RolePermission.role_id == role_id
    ).delete()

    for perm in perm_objects:
        db.add(models.RolePermission(
            role_id=role_id,
            permission_id=perm.id,
        ))

    db.commit()

    return schemas.RolePermissionsResponse(
        role_id=role.id,
        role_name=role.name,
        permissions=[f"{p.module}:{p.action}" for p in perm_objects],
    )


# ==================== WALL POSTS ====================

@router.post("/{user_id}/wall/posts", response_model=schemas.PostResponse)
def create_wall_post(
    user_id: int,
    post_data: schemas.PostCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Создать пост на стене пользователя."""
    wall_owner = db.query(models.User).filter(models.User.id == user_id).first()
    if not wall_owner:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if not post_data.content or not post_data.content.strip():
        raise HTTPException(status_code=400, detail="Содержимое поста не может быть пустым")

    clean_content = sanitize_html(post_data.content.strip())
    if not clean_content or not clean_content.replace("<p></p>", "").strip():
        raise HTTPException(status_code=400, detail="Содержимое поста не может быть пустым")

    new_post = models.UserPost(
        author_id=current_user.id,
        wall_owner_id=user_id,
        content=clean_content,
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    return schemas.PostResponse(
        id=new_post.id,
        author_id=new_post.author_id,
        author_username=current_user.username,
        author_avatar=current_user.avatar,
        wall_owner_id=new_post.wall_owner_id,
        content=new_post.content,
        created_at=new_post.created_at,
    )


@router.get("/{user_id}/wall/posts", response_model=List[schemas.PostResponse])
def get_wall_posts(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Получить посты на стене пользователя с пагинацией."""
    wall_owner = db.query(models.User).filter(models.User.id == user_id).first()
    if not wall_owner:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    posts = (
        db.query(models.UserPost, models.User)
        .join(models.User, models.User.id == models.UserPost.author_id)
        .filter(models.UserPost.wall_owner_id == user_id)
        .order_by(models.UserPost.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    result = []
    for post, author in posts:
        result.append(schemas.PostResponse(
            id=post.id,
            author_id=post.author_id,
            author_username=author.username,
            author_avatar=author.avatar,
            wall_owner_id=post.wall_owner_id,
            content=post.content,
            created_at=post.created_at,
        ))
    return result


@router.put("/wall/posts/{post_id}", response_model=schemas.PostResponse)
def update_wall_post(
    post_id: int,
    post_data: schemas.PostCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Редактировать пост. Может только автор поста."""
    post = db.query(models.UserPost).filter(models.UserPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")

    if post.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Редактировать пост может только автор")

    clean_content = sanitize_html(post_data.content.strip())
    if not clean_content or not clean_content.replace("<p></p>", "").strip():
        raise HTTPException(status_code=400, detail="Содержимое поста не может быть пустым")

    post.content = clean_content
    db.commit()
    db.refresh(post)

    author = db.query(models.User).filter(models.User.id == post.author_id).first()
    return schemas.PostResponse(
        id=post.id,
        author_id=post.author_id,
        author_username=author.username if author else "Неизвестный",
        author_avatar=author.avatar if author else None,
        wall_owner_id=post.wall_owner_id,
        content=post.content,
        created_at=post.created_at,
    )


@router.delete("/wall/posts/{post_id}")
def delete_wall_post(
    post_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Удалить пост. Может удалить автор поста или владелец стены."""
    post = db.query(models.UserPost).filter(models.UserPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")

    if post.author_id != current_user.id and post.wall_owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет прав для удаления этого поста")

    db.delete(post)
    db.commit()
    return {"detail": "Пост удалён"}


# ==================== FRIENDS ====================

@router.post("/friends/request", response_model=schemas.FriendshipResponse)
def send_friend_request(
    body: schemas.FriendshipRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Отправить запрос на дружбу."""
    if body.friend_id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя добавить самого себя в друзья")

    friend = db.query(models.User).filter(models.User.id == body.friend_id).first()
    if not friend:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    existing = db.query(models.Friendship).filter(
        (
            (models.Friendship.user_id == current_user.id) &
            (models.Friendship.friend_id == body.friend_id)
        ) | (
            (models.Friendship.user_id == body.friend_id) &
            (models.Friendship.friend_id == current_user.id)
        )
    ).first()

    if existing:
        if existing.status == "accepted":
            raise HTTPException(status_code=400, detail="Вы уже друзья")
        else:
            raise HTTPException(status_code=400, detail="Запрос на дружбу уже существует")

    friendship = models.Friendship(
        user_id=current_user.id,
        friend_id=body.friend_id,
        status="pending",
    )
    db.add(friendship)
    db.commit()
    db.refresh(friendship)
    return friendship


@router.put("/friends/request/{friendship_id}/accept", response_model=schemas.FriendshipResponse)
def accept_friend_request(
    friendship_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Принять запрос на дружбу."""
    friendship = db.query(models.Friendship).filter(models.Friendship.id == friendship_id).first()
    if not friendship:
        raise HTTPException(status_code=404, detail="Запрос на дружбу не найден")

    if friendship.friend_id != current_user.id:
        raise HTTPException(status_code=403, detail="Только получатель может принять запрос на дружбу")

    if friendship.status == "accepted":
        raise HTTPException(status_code=400, detail="Запрос уже принят")

    friendship.status = "accepted"
    db.commit()
    db.refresh(friendship)
    return friendship


@router.delete("/friends/request/{friendship_id}")
def reject_friend_request(
    friendship_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Отклонить/отменить запрос на дружбу."""
    friendship = db.query(models.Friendship).filter(models.Friendship.id == friendship_id).first()
    if not friendship:
        raise HTTPException(status_code=404, detail="Запрос на дружбу не найден")

    if friendship.user_id != current_user.id and friendship.friend_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет прав для отмены этого запроса")

    db.delete(friendship)
    db.commit()
    return {"detail": "Запрос на дружбу отклонён"}


@router.get("/friends/requests/incoming", response_model=List[schemas.FriendRequestResponse])
def get_incoming_friend_requests(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Получить входящие запросы на дружбу."""
    requests = (
        db.query(models.Friendship, models.User)
        .join(models.User, models.User.id == models.Friendship.user_id)
        .filter(
            models.Friendship.friend_id == current_user.id,
            models.Friendship.status == "pending",
        )
        .order_by(models.Friendship.created_at.desc())
        .all()
    )

    result = []
    for friendship, sender in requests:
        result.append(schemas.FriendRequestResponse(
            id=friendship.id,
            user=schemas.FriendResponse(
                id=sender.id,
                username=sender.username,
                avatar=sender.avatar,
            ),
            created_at=friendship.created_at,
        ))
    return result


@router.get("/friends/requests/outgoing", response_model=List[schemas.FriendRequestResponse])
def get_outgoing_friend_requests(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Получить исходящие запросы на дружбу."""
    requests = (
        db.query(models.Friendship, models.User)
        .join(models.User, models.User.id == models.Friendship.friend_id)
        .filter(
            models.Friendship.user_id == current_user.id,
            models.Friendship.status == "pending",
        )
        .order_by(models.Friendship.created_at.desc())
        .all()
    )

    result = []
    for friendship, target in requests:
        result.append(schemas.FriendRequestResponse(
            id=friendship.id,
            user=schemas.FriendResponse(
                id=target.id,
                username=target.username,
                avatar=target.avatar,
            ),
            created_at=friendship.created_at,
        ))
    return result


@router.get("/{user_id}/friends", response_model=List[schemas.FriendResponse])
def get_user_friends(
    user_id: int,
    db: Session = Depends(get_db),
):
    """Получить список друзей пользователя."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    friends_as_sender = (
        db.query(models.User)
        .join(models.Friendship, models.Friendship.friend_id == models.User.id)
        .filter(
            models.Friendship.user_id == user_id,
            models.Friendship.status == "accepted",
        )
        .all()
    )

    friends_as_receiver = (
        db.query(models.User)
        .join(models.Friendship, models.Friendship.user_id == models.User.id)
        .filter(
            models.Friendship.friend_id == user_id,
            models.Friendship.status == "accepted",
        )
        .all()
    )

    all_friends = {u.id: u for u in friends_as_sender + friends_as_receiver}
    return [
        schemas.FriendResponse(id=u.id, username=u.username, avatar=u.avatar)
        for u in all_friends.values()
    ]


@router.delete("/friends/{friend_id}")
def remove_friend(
    friend_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Удалить друга."""
    friendship = db.query(models.Friendship).filter(
        models.Friendship.status == "accepted",
        (
            (models.Friendship.user_id == current_user.id) &
            (models.Friendship.friend_id == friend_id)
        ) | (
            (models.Friendship.user_id == friend_id) &
            (models.Friendship.friend_id == current_user.id)
        )
    ).first()

    if not friendship:
        raise HTTPException(status_code=404, detail="Дружба не найдена")

    db.delete(friendship)
    db.commit()
    return {"detail": "Друг удалён"}


# ==================== USER CHARACTERS ====================

@router.get("/{user_id}/characters", response_model=schemas.UserCharactersResponse)
async def get_user_characters(
    user_id: int,
    db: Session = Depends(get_db),
):
    """Получить список персонажей пользователя."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    relations = db.query(models.UserCharacter).filter(
        models.UserCharacter.user_id == user_id
    ).all()

    character_ids = [r.character_id for r in relations]

    characters = []
    if character_ids:
        tasks = [_fetch_character_short(cid) for cid in character_ids]
        results = await asyncio.gather(*tasks)
        for char_data in results:
            if char_data:
                characters.append(schemas.UserCharacterItem(
                    id=char_data["id"],
                    name=char_data["name"],
                    avatar=char_data.get("avatar"),
                    level=char_data.get("level"),
                    rp_posts_count=0,
                    last_rp_post_date=None,
                ))

    return schemas.UserCharactersResponse(characters=characters)


# ==================== USER PROFILE ====================

@router.get("/{user_id}/profile", response_model=schemas.UserProfileResponse)
async def get_user_profile(
    user_id: int,
    current_user: Optional[models.User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Получить полный профиль пользователя."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Post stats
    total_posts = db.query(func.count(models.UserPost.id)).filter(
        models.UserPost.wall_owner_id == user_id
    ).scalar()

    last_post_date = db.query(func.max(models.UserPost.created_at)).filter(
        models.UserPost.wall_owner_id == user_id
    ).scalar()

    post_stats = schemas.PostStatsResponse(
        total_posts=total_posts or 0,
        last_post_date=last_post_date,
    )

    # Character info
    character_data = None
    if user.current_character:
        character_data = await _fetch_character_short(user.current_character)

    # Friendship status
    is_friend = None
    friendship_status = None
    friendship_id = None

    if current_user and current_user.id != user_id:
        friendship = db.query(models.Friendship).filter(
            (
                (models.Friendship.user_id == current_user.id) &
                (models.Friendship.friend_id == user_id)
            ) | (
                (models.Friendship.user_id == user_id) &
                (models.Friendship.friend_id == current_user.id)
            )
        ).first()

        if friendship:
            friendship_id = friendship.id
            if friendship.status == "accepted":
                is_friend = True
                friendship_status = "accepted"
            elif friendship.user_id == current_user.id:
                is_friend = False
                friendship_status = "pending_sent"
            else:
                is_friend = False
                friendship_status = "pending_received"
        else:
            is_friend = False
            friendship_status = "none"

    return schemas.UserProfileResponse(
        id=user.id,
        username=user.username,
        avatar=user.avatar,
        registered_at=user.registered_at,
        character=character_data,
        post_stats=post_stats,
        is_friend=is_friend,
        friendship_status=friendship_status,
        friendship_id=friendship_id,
        profile_bg_color=user.profile_bg_color,
        profile_bg_image=user.profile_bg_image,
        nickname_color=user.nickname_color,
        avatar_frame=user.avatar_frame,
        avatar_effect_color=user.avatar_effect_color,
        status_text=user.status_text,
        profile_bg_position=user.profile_bg_position,
    )


# ==================== GET USER BY ID (catch-all, must be last) ====================

@router.get("/{user_id}", response_model=UserRead)
def get_user_by_id(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


app.include_router(router)
