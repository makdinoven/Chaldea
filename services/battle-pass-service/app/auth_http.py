import httpx
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import List, Optional
from config import settings


class UserRead(BaseModel):
    id: int
    username: str
    role: Optional[str] = None
    permissions: List[str] = []
    current_character_id: Optional[int] = None

    class Config:
        orm_mode = True


OAUTH2_SCHEME = OAuth2PasswordBearer(tokenUrl="token")


async def get_current_user_via_http(token: str = Depends(OAUTH2_SCHEME)) -> UserRead:
    """
    Async HTTP call to user-service /users/me for JWT validation.
    """
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{settings.USER_SERVICE_URL}/users/me"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
    except httpx.ConnectError:
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


async def get_admin_user(
    user: UserRead = Depends(get_current_user_via_http),
) -> UserRead:
    """
    Verify user is admin or moderator.
    """
    if user.role not in ("admin", "moderator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только администраторы и модераторы могут выполнять это действие",
        )
    return user


def require_permission(permission: str):
    """FastAPI dependency factory for granular permission checks."""

    async def checker(
        user: UserRead = Depends(get_current_user_via_http),
    ) -> UserRead:
        if permission not in user.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав",
            )
        return user

    return checker
