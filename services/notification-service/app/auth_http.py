# auth_http.py (файл в сервисе уведомлений)
import os
import requests
import httpx
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import List, Optional

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
    resp = requests.get(url, headers=headers)
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
                timeout=5.0
            )
            if resp.status_code == 200:
                return resp.json()
            return None
    except Exception:
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
