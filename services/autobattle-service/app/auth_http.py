import os
import requests
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import List, Optional


class UserRead(BaseModel):
    id: int
    username: str
    role: Optional[str] = None
    permissions: List[str] = []

    class Config:
        orm_mode = True


OAUTH2_SCHEME = OAuth2PasswordBearer(tokenUrl="token")

AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://user-service:8000")


def get_current_user_via_http(token: str = Depends(OAUTH2_SCHEME)) -> UserRead:
    """
    HTTP-запрос к user-service на /users/me для валидации JWT-токена.
    """
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{AUTH_SERVICE_URL}/users/me"
    try:
        resp = requests.get(url, headers=headers, timeout=5)
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис аутентификации недоступен",
        )
    if resp.status_code == 200:
        data = resp.json()
        return UserRead(**data)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось подтвердить учётные данные",
    )


def get_admin_user(user: UserRead = Depends(get_current_user_via_http)) -> UserRead:
    """
    Проверяет, что пользователь имеет роль admin или moderator.
    """
    if user.role not in ("admin", "moderator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только администраторы и модераторы могут выполнять это действие",
        )
    return user


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
