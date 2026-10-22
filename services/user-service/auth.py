import os
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from crud import get_user_by_email
from models import User
from sessions import get_live_session, touch_session
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

# 401 detail when the token is well-formed but its session is gone (revoked
# from another device, "log out everywhere", password change).
SESSION_REVOKED_DETAIL = "Сессия завершена. Войдите снова."


def build_token_data(user, session_id: Optional[str]) -> dict:
    """Claims shared by the access and the refresh token of one pair.

    `sub` (email) stays for backward compatibility with clients that decode
    it; the server identifies the user by `uid` when it is present.
    """
    data = {"sub": user.email, "uid": user.id}
    if session_id is not None:
        data["sid"] = session_id
    if user.current_character is not None:
        data["current_character"] = user.current_character
    return data


def _encode(data: dict, role: str, token_type: str, expires_delta: timedelta) -> str:
    to_encode = data.copy()  # data уже содержит current_character
    now = datetime.utcnow()
    to_encode.update({"role": role, "type": token_type, "iat": now, "exp": now + expires_delta})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# Создание JWT токена с добавлением роли пользователя
def create_access_token(data: dict, role: str, expires_delta: Optional[timedelta] = None):
    return _encode(data, role, "access", expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))


def create_refresh_token(data: dict, role: str, expires_delta: Optional[timedelta] = None):
    return _encode(data, role, "refresh", expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))


def issue_token_pair(user, session_id: Optional[str]) -> dict:
    token_data = build_token_data(user, session_id)
    return {
        "access_token": create_access_token(data=token_data, role=user.role),
        "refresh_token": create_refresh_token(data=token_data, role=user.role),
        "token_type": "bearer",
    }


def user_from_payload(db: Session, payload: dict):
    """Resolve the token's user: by `uid` when present, else legacy email `sub`."""
    uid = payload.get("uid")
    if uid is not None:
        try:
            uid = int(uid)
        except (TypeError, ValueError):
            return None
        return db.query(User).filter(User.id == uid).first()
    email = payload.get("sub")
    if not email:
        return None
    return get_user_by_email(db, email=email)


class AuthContext:
    """The authenticated user plus the session (`sid`) the token belongs to.

    `session_id` is None for legacy tokens issued before sessions existed.
    """

    def __init__(self, user, session_id: Optional[str]):
        self.user = user
        self.session_id = session_id


def authenticate_access_token(db: Session, token: str) -> AuthContext:
    """Validate an access token and its session. Raises 401 on any failure."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise credentials_exception
    # Reject refresh tokens used as access tokens.
    # Tokens without a "type" claim are legacy (issued before the claim existed) and stay accepted.
    if payload.get("type") == "refresh":
        raise credentials_exception
    if payload.get("sub") is None or payload.get("role") is None:
        raise credentials_exception

    user = user_from_payload(db, payload)
    if user is None:
        raise credentials_exception

    revoked_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=SESSION_REVOKED_DETAIL,
        headers={"WWW-Authenticate": "Bearer"},
    )
    session_id = payload.get("sid")
    if session_id is not None:
        session = get_live_session(db, str(session_id), user.id)
        if session is None:
            raise revoked_exception
        touch_session(db, session)
        return AuthContext(user, session.id)

    # Legacy token without a session: valid only until the account was told
    # to drop every old token (log out everywhere / password change).
    if user.tokens_valid_after is not None:
        raise revoked_exception
    return AuthContext(user, None)


def get_current_auth(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> AuthContext:
    return authenticate_access_token(db, token)


# Получение текущего пользователя по JWT токену
def get_current_user(auth: AuthContext = Depends(get_current_auth)):
    return auth.user



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
