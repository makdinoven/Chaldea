# auth_http.py (файл в сервисе уведомлений)
import logging
import os
import requests
import httpx
from fastapi import HTTPException, status, Depends
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
