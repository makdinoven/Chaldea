from fastapi import FastAPI, Depends, HTTPException, status, APIRouter
from sqlalchemy.orm import Session
from models import User
from schemas import User, UserCreate, Login  # Импорт схем для пользователя, включая Login
from crud import create_user, get_user_by_email, get_user_by_username, authenticate_user  # Импорт CRUD функций
from auth import *  # Импорт функций аутентификации
from auth import SECRET_KEY, ALGORITHM
from database import SessionLocal, engine, get_db
from jose import JWTError, jwt

app = FastAPI()

# Создаем роутер с префиксом /api
router = APIRouter(prefix="/api")

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
@router.post("/login")
def login_user(form_data: Login, db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.identifier, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": user.email})
    refresh_token = create_refresh_token(data={"sub": user.email})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


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
    new_access_token = create_access_token(data={"sub": user.email})
    return {"access_token": new_access_token, "token_type": "bearer"}

# Получение информации о текущем пользователе
@router.get("/users/me", response_model=User)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

app.include_router(router)
