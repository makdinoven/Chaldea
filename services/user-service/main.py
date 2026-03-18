from typing import List, Optional

from fastapi import BackgroundTasks, FastAPI, Depends, HTTPException, status, APIRouter, UploadFile, Query
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer
import models
import schemas
from crud import create_user, get_user_by_email, get_user_by_username, authenticate_user
from auth import *
from auth import SECRET_KEY, ALGORITHM
from database import SessionLocal, engine, get_db
from jose import JWTError, jwt
import os
import shutil
from fastapi.middleware.cors import CORSMiddleware
from producer import send_notification_event
import httpx
from sqlalchemy import func
from datetime import datetime, timedelta
import bleach

ALLOWED_TAGS = [
    "p", "br", "strong", "em", "u", "s",
    "h1", "h2", "h3",
    "ul", "ol", "li",
    "blockquote",
]

def sanitize_html(html: str) -> str:
    """Sanitize HTML content, allowing only safe tags from WYSIWYG editor."""
    return bleach.clean(html, tags=ALLOWED_TAGS, strip=True)

app = FastAPI()

cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    models.Base.metadata.create_all(bind=engine)

router = APIRouter(prefix="/users")

UPLOAD_DIR = "src/assets/avatars/"

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

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

@router.post("/register", response_model=UserRead)
def register_user(user: UserCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    db_user_email = get_user_by_email(db, email=user.email)
    if db_user_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    db_user_username = get_user_by_username(db, username=user.username)
    if db_user_username:
        raise HTTPException(status_code=400, detail="Username already taken")

    new_user = create_user(db=db, user=user)
    background_tasks.add_task(send_notification_event, new_user.id)
    return new_user


@router.post("/login")
def login_user(data: Login, db: Session = Depends(get_db)):
    user = authenticate_user(db, data.identifier, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
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

    me_data = {
        "id": current_user.id,
        "email": current_user.email,
        "username": current_user.username,
        "avatar": current_user.avatar,
        "balance": current_user.balance,
        "role": current_user.role,
        "current_character_id": current_user.current_character,
        "character": None
    }

    if current_user.current_character:
        char_data = await _fetch_character_short(current_user.current_character)
        if char_data:
            me_data["character"] = char_data

    return schemas.MeResponse(**me_data)


@router.post("/upload-avatar/")
async def upload_avatar(file: UploadFile, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    file_path = os.path.join(UPLOAD_DIR, f"{current_user.id}_{file.filename}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    relative_path = f"/assets/avatars/{current_user.id}_{file.filename}"
    current_user.avatar = relative_path
    db.commit()
    return {"avatar_url": relative_path}


# ==================== CHARACTER RELATIONS ====================

@router.put("/{user_id}/update_character")
async def update_user_character(user_id: int, character_data: dict, db: Session = Depends(get_db)):
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
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

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
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.current_character == body.character_id:
        user.current_character = None
        db.commit()

    return {"detail": "Current character cleared"}


# Static files
app.mount("/assets", StaticFiles(directory="src/assets"), name="assets")


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
    admins = db.query(models.User).filter(models.User.role == "admin").all()
    return admins


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
    )


# ==================== GET USER BY ID (catch-all, must be last) ====================

@router.get("/{user_id}", response_model=UserRead)
def get_user_by_id(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


app.include_router(router)
