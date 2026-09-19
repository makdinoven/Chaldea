import os

import httpx
from fastapi import HTTPException, status, Depends, Header
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


# ============================================================
# Internal service-to-service authentication (FEAT-170 §3.2)
# ============================================================
# Behaviour copied verbatim from character-service (`app/auth_http.py`):
# the caller must present `X-Internal-Token` matching the INTERNAL_SERVICE_TOKEN
# env var. Fail-closed: an unset/empty env var rejects every request with 503,
# so a missing config can never silently disable auth on an internal endpoint.
#
# The token is read from `os.environ` on purpose: `config.Settings` has no
# INTERNAL_SERVICE_TOKEN field and must not gain one (§3.3) — adding it would
# change the strict-env behaviour of the whole service. `crud.py`'s outgoing
# helper reads env the same way.

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
