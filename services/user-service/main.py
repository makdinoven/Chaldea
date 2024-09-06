from fastapi import FastAPI, Depends, HTTPException, status, APIRouter, UploadFile
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from models import User
from schemas import User, UserCreate, Login  # Импорт схем для пользователя, включая Login
from crud import create_user, get_user_by_email, get_user_by_username, authenticate_user  # Импорт CRUD функций
from auth import *  # Импорт функций аутентификации
from auth import SECRET_KEY, ALGORITHM
from database import SessionLocal, engine, get_db
from jose import JWTError, jwt
import os
import shutil

app = FastAPI()

# Создаем роутер с префиксом /api
router = APIRouter(prefix="/user")

UPLOAD_DIR = "src/assets/avatars/"

# Проверка и создание директории для аватарок, если она не существует
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# Регистрация нового пользователя
@router.post("/register", response_model=User)
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
    return create_user(db=db, user=user)

# Вход в систему и получение JWT и рефреш-токена
@router.post("/login")  # Изменено на router.post
def login_user(data: Login, db: Session = Depends(get_db)):
    user = authenticate_user(db, data.identifier, data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token = create_access_token(data={"sub": user.email}, role=user.role)  # Передаем роль пользователя
    refresh_token = create_refresh_token(data={"sub": user.email}, role=user.role)

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
@router.get("/users/me", response_model=User)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

# Маршрут для загрузки аватарки
@router.post("/upload-avatar/")
async def upload_avatar(file: UploadFile, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
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

# Настройка статических файлов
app.mount("/assets", StaticFiles(directory="src/assets"), name="assets")

# Подключаем маршрутизатор к основному приложению FastAPI
app.include_router(router)
