import os
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from crud import get_user_by_email
from schemas import UserRead, UserCreate, Login
from database import get_db

# Секретный ключ и алгоритм шифрования.
#
# FEAT-169: fail-fast на импорте. Проверяется именно «правдивость», а не
# наличие ключа: в compose незаданная переменная разворачивается в ПУСТУЮ
# строку (`JWT_SECRET_KEY=` + предупреждение), поэтому `os.environ[...]`
# спокойно пропустил бы пустой секрет и сервис поднялся бы с подписью на "".
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "")
if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY не задан или пуст — user-service не запускается с "
        "пустым JWT-секретом. Задайте JWT_SECRET_KEY в .env "
        "(сгенерировать: openssl rand -hex 32)."
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1200
REFRESH_TOKEN_EXPIRE_DAYS = 7  # Срок жизни рефреш-токена

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Создание JWT токена с добавлением роли пользователя
def create_access_token(data: dict, role: str, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()  # data уже содержит current_character
    to_encode.update({"role": role, "type": "access"})
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict, role: str, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()  # data уже содержит current_character
    to_encode.update({"role": role, "type": "refresh"})
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
        # Reject refresh tokens used as access tokens.
        # Tokens without a "type" claim are legacy (issued before the claim existed) and stay accepted.
        if payload.get("type") == "refresh":
            raise credentials_exception
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



# ============================================================
# Internal service-to-service authentication (FEAT-169 §3.3 M4)
# ============================================================
# user-service is the auth service itself and has no `auth_http.py`, so the
# fail-closed check lives here. Behaviour is identical to the copies in
# character-service / character-attributes-service / inventory-service:
# the caller must present `X-Internal-Token` matching the INTERNAL_SERVICE_TOKEN
# env var. Fail-closed: an unset/empty env var rejects every request with 503,
# so a missing config can never silently disable auth on an internal endpoint.
# The constant is resolved at import time — tests monkeypatch
# `auth.INTERNAL_SERVICE_TOKEN`, not only the env var.

INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "")


def verify_internal_token(
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
) -> None:
    """Reject the request unless `X-Internal-Token` matches
    `INTERNAL_SERVICE_TOKEN` from env. Empty env -> always reject.
    """
    if not INTERNAL_SERVICE_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal service token не настроен",
        )
    if not x_internal_token or x_internal_token != INTERNAL_SERVICE_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный internal token",
        )
