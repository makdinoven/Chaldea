from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from crud import get_user_by_email
from schemas import UserRead, UserCreate, Login
from database import get_db

# Секретный ключ и алгоритм шифрования
SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7  # Срок жизни рефреш-токена

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Создание JWT токена с добавлением роли пользователя
def create_access_token(data: dict, role: str, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()  # data уже содержит current_character
    to_encode.update({"role": role})
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict, role: str, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()  # data уже содержит current_character
    to_encode.update({"role": role})
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# Получение текущего пользователя по JWT токену
def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        role: str = payload.get("role")
        if email is None or role is None:
            raise credentials_exception
        current_character = payload.get("current_character")  # может быть None
    except JWTError:
        raise credentials_exception

    user = get_user_by_email(db, email=email)
    if user is None:
        raise credentials_exception

    # Если вы хотите проверить, что current_character в токене совпадает
    # с тем, что лежит в базе, это можно сделать:
    # if current_character != user.current_character:
    #     raise HTTPException(status_code=401, detail="Token data mismatch")

    return user

