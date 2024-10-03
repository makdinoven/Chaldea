from fastapi import FastAPI, Depends, HTTPException, status, APIRouter, UploadFile
from fastapi.staticfiles import StaticFiles
import models
from crud import create_user, get_user_by_email, get_user_by_username, authenticate_user  # Импорт CRUD функций
from auth import *  # Импорт функций аутентификации
from auth import SECRET_KEY, ALGORITHM
from database import SessionLocal, engine, get_db
from jose import JWTError, jwt
import os
import shutil

app = FastAPI()

models.Base.metadata.create_all(bind=engine)

# Создаем роутер с префиксом /api
router = APIRouter(prefix="/users")

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
@router.get("/me", response_model=User)
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

# Эндпоинт для обновления пользователя с присвоением персонажа
@router.put("/{user_id}/update_character")
def update_user_character(user_id: int, character_data: dict, db: Session = Depends(get_db)):
    """
    Обновляет пользователя, присваивая ему персонажа.
    """
    character_id = character_data.get("character_id")

    if character_id is None:
        raise HTTPException(status_code=400, detail="character_id обязателен")

    print(f"Запрос на обновление пользователя с ID {user_id} и персонажем {character_id}")

    # Поиск пользователя в базе данных
    db_user = db.query(models.User).filter(models.User.id == user_id).first()

    if not db_user:
        print(f"Пользователь с ID {user_id} не найден")
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    try:
        # Обновление текущего персонажа пользователя
        db_user.current_character = character_id
        db.commit()

        print(f"Пользователь с ID {user_id} успешно обновлен с персонажем {db_user.current_character}")

        return {"message": f"Пользователю с ID {user_id} присвоен персонаж с ID {db_user.current_character}"}

    except Exception as e:
        db.rollback()  # Откат транзакции в случае ошибки
        print(f"Ошибка при обновлении пользователя с ID {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при обновлении пользователя")


# Настройка статических файлов
app.mount("/assets", StaticFiles(directory="src/assets"), name="assets")

# Подключаем маршрутизатор к основному приложению FastAPI
app.include_router(router)
