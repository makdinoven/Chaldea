from typing import List

from fastapi import FastAPI, Depends, HTTPException, status, APIRouter, UploadFile
from fastapi.staticfiles import StaticFiles
import models
import schemas
from crud import create_user, get_user_by_email, get_user_by_username, authenticate_user  # Импорт CRUD функций
from auth import *  # Импорт функций аутентификации
from auth import SECRET_KEY, ALGORITHM
from database import SessionLocal, engine, get_db
from jose import JWTError, jwt
import os
import shutil
from fastapi.middleware.cors import CORSMiddleware
from producer import send_notification_event
import httpx

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

models.Base.metadata.create_all(bind=engine)

# Создаем роутер с префиксом /api
router = APIRouter(prefix="/users")

UPLOAD_DIR = "src/assets/avatars/"

# Проверка и создание директории для аватарок, если она не существует
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

CHARACTER_SERVICE_URL = os.getenv("CHARACTER_SERVICE_URL", "http://character-service:8005")
LOCATION_SERVICE_URL = os.getenv("LOCATION_SERVICE_URL", "http://locations-service:8006")
# Регистрация нового пользователя
@router.post("/register", response_model=UserRead)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    # Проверка уникальности email
    db_user_email = get_user_by_email(db, email=user.email)
    if db_user_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Проверка уникальности никнейма
    db_user_username = get_user_by_username(db, username=user.username)
    if db_user_username:
        raise HTTPException(status_code=400, detail="Username already taken")

    # Создание нового пользователя
    new_user = create_user(db=db, user=user)

    # Отправка сообщения в RabbitMQ
    send_notification_event(new_user.id)

    return new_user

# Вход в систему и получение JWT и рефреш-токена
@router.post("/login")
def login_user(data: Login, db: Session = Depends(get_db)):
    user = authenticate_user(db, data.identifier, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    token_data = {
        "sub": user.email,
    }
    
    if user.current_character is not None:
        token_data["current_character"] = user.current_character

    access_token = create_access_token(
        data=token_data,
        role=user.role
    )
    refresh_token = create_refresh_token(
        data=token_data,
        role=user.role
    )

    return {"access_token": access_token, "refresh_token": refresh_token}


# Обновление JWT токена с использованием рефреш-токена
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

    # Создаем новый access token
    new_access_token = create_access_token(data={"sub": user.email}, role=user.role)  # Добавлен role
    return {"access_token": new_access_token, "token_type": "bearer"}

# Получение информации о текущем пользователе
@router.get("/me", response_model=schemas.MeResponse)
async def read_users_me(
    current_user: models.User = Depends(get_current_user)
):
    """
    Возвращает расширенную информацию о пользователе:
      • базовые поля пользователя;
      • current_character_id;
      • упрощённые данные персонажа (id, name, avatar);
      • текущую локацию персонажа (id, name, image_url).
    """
    # ---------- 1. базовая часть -----------------------------------
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

    # ---------- 2. если выбран персонаж – тянем short_info ----------
    if current_user.current_character:
        char_id = current_user.current_character
        char_url = f"{CHARACTER_SERVICE_URL}/characters/{char_id}/short_info"

        async with httpx.AsyncClient(timeout=5.0) as client:
            # --- персонаж ---
            try:
                resp = await client.get(char_url)
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                raise HTTPException(status_code=502, detail="Character‑service unavailable")

            ch_json = resp.json()          # {"id":..,"name":..,"avatar":..,"current_location_id":..}

            # --- локация (если задана) ---
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
                    # если location‑service упал – просто пропускаем
                    pass

            # формируем объект CharacterShort
            me_data["character"] = {
                "id": ch_json["id"],
                "name": ch_json["name"],
                "avatar": ch_json["avatar"],
                "current_location": loc_json
            }

    # ---------- 3. отдаём результат ---------------------------------
    return schemas.MeResponse(**me_data)
# Маршрут для загрузки аватарки
@router.post("/upload-avatar/")
async def upload_avatar(file: UploadFile, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Создаем уникальное имя файла для загрузки
    file_path = os.path.join(UPLOAD_DIR, f"{current_user.id}_{file.filename}")

    # Сохраняем файл на сервере
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Относительный путь к аватарке для хранения в базе данных
    relative_path = f"/assets/avatars/{current_user.id}_{file.filename}"
    current_user.avatar = relative_path
    db.commit()

    # Возвращаем относительный URL загруженного файла
    return {"avatar_url": relative_path}

# Эндпоинт для обновления пользователя с присвоением персонажа
@router.put("/{user_id}/update_character")
async def update_user_character(
    user_id: int, 
    character_data: dict,
    db: Session = Depends(get_db)
):
    """
    Обновляет поле current_character пользователя.
    """
    character_id = character_data.get("current_character")
    if character_id is None:
        raise HTTPException(status_code=400, detail="current_character обязателен")

    # Проверка существования связи пользователь-персонаж
    character_relation = db.query(models.UserCharacter).filter(
        models.UserCharacter.user_id == user_id,
        models.UserCharacter.character_id == character_id
    ).first()
    
    if not character_relation:
        raise HTTPException(
            status_code=400, 
            detail="У пользователя нет доступа к этому персонажу"
        )

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
    """
    Создает связь между пользователем и персонажем.
    """
    db_relation = models.UserCharacter(user_id=user_character.user_id, character_id=user_character.character_id)
    db.add(db_relation)
    db.commit()
    return {"message": "Связь между пользователем и персонажем создана"}

# Настройка статических файлов
app.mount("/assets", StaticFiles(directory="src/assets"), name="assets")

@router.get("/all", response_model=List[UserRead])
def get_all_users(db: Session = Depends(get_db)):
    """
    Возвращает список всех пользователей из базы.
    """
    users = db.query(models.User).all()
    return users

@router.get("/admins", response_model=List[UserRead])
def get_admin_users(db: Session = Depends(get_db)):
    """
    Возвращает список пользователей, у которых роль = 'admin'.
    """
    admins = db.query(models.User).filter(models.User.role == "admin").all()
    return admins

@router.get("/{user_id}", response_model=UserRead)
def get_user_by_id(user_id: int, db: Session = Depends(get_db)):
    """
    Возвращает данные пользователя по его ID:
      - id
      - email
      - username
      - role
      - avatar
      - registered_at
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# Подключаем маршрутизатор к основному приложению FastAPI
app.include_router(router)
