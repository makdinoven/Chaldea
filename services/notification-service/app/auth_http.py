# auth_http.py (файл в сервисе уведомлений)
import base64
import hmac
import json
import logging
import os
import requests
import httpx
from fastapi import HTTPException, status, Depends, Header
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import List, Optional

logger = logging.getLogger("notification-service.auth")

# user-service's GET /users/me fans out to character-service and
# locations-service (5s each), so its own worst case is ~10s. Anything at or
# below that silently fails every handshake instead of only the slow ones —
# a 5s budget here used to reject *all* WebSocket connections because /users/me
# landed at a hair over 5s on every call.
AUTH_REQUEST_TIMEOUT = 15.0

class UserRead(BaseModel):
    id: int
    username: str
    role: Optional[str] = None
    permissions: List[str] = []

OAUTH2_SCHEME = OAuth2PasswordBearer(tokenUrl="token")

AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://user-service:8000")

def get_current_user_via_http(token: str = Depends(OAUTH2_SCHEME)) -> UserRead:
    """
    Делаем HTTP-запрос к auth-service/user-service на маршрут /users/me (или /auth/me).
    Передаём заголовок Authorization: Bearer <token>.
    Если получаем 200, возвращаем UserRead, иначе выбрасываем 401.
    """
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{AUTH_SERVICE_URL}/users/me"
    try:
        resp = requests.get(url, headers=headers, timeout=AUTH_REQUEST_TIMEOUT)
    except requests.RequestException as e:
        logger.error(f"user-service недоступен при проверке токена: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис аутентификации временно недоступен",
        )
    if resp.status_code == 200:
        data = resp.json()
        return UserRead(**data)
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )


async def authenticate_websocket(token: str):
    """Validate JWT by calling user-service. Returns user dict or None."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{AUTH_SERVICE_URL}/users/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=AUTH_REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
            # Log the reason: a silent None here is indistinguishable from an
            # expired token, which hid a service-wide handshake failure.
            logger.warning(
                f"WebSocket-авторизация отклонена user-service: {resp.status_code}"
            )
            return None
    except Exception as e:
        logger.error(f"WebSocket-авторизация не удалась (user-service): {e!r}")
        return None


def require_permission(permission: str):
    """FastAPI dependency factory for granular permission checks."""
    def checker(user: UserRead = Depends(get_current_user_via_http)) -> UserRead:
        if permission not in user.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав",
            )
        return user
    return checker


# ============================================================
# Internal service-to-service authentication
# ============================================================
# Same fail-closed contract as the copies in character-service /
# character-attributes-service / inventory-service: the caller must present
# `X-Internal-Token` matching INTERNAL_SERVICE_TOKEN; an unset/empty env var
# rejects every request with 503. Resolved at import time — tests monkeypatch
# `auth_http.INTERNAL_SERVICE_TOKEN`.

INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "")


def verify_internal_token(
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
) -> None:
    if not INTERNAL_SERVICE_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal service token не настроен",
        )
    if not x_internal_token or not hmac.compare_digest(x_internal_token, INTERNAL_SERVICE_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный internal token",
        )


def unverified_session_id(token: str) -> Optional[str]:
    """The `sid` claim of a JWT, read WITHOUT verifying the signature.

    Only for matching a socket to its login session after the token has
    already been validated by user-service (/users/me) at the handshake —
    never use it to authenticate anything. Returns None for tokens without
    a session (legacy) or anything unparsable.
    """
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        sid = payload.get("sid")
        return str(sid) if sid is not None else None
    except Exception:
        return None
