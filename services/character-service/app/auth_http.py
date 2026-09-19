import os
import requests
from fastapi import HTTPException, status, Depends, Header
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
# FEAT-171 §3.1 D3: same scheme, but a missing Authorization header is not
# an error — it just yields `None` (see `get_optional_user`).
OAUTH2_SCHEME_OPTIONAL = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

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


def get_optional_user(
    token: Optional[str] = Depends(OAUTH2_SCHEME_OPTIONAL),
) -> Optional[UserRead]:
    """Optional authentication (FEAT-171 §3.1 D3).

    Same as `get_current_user_via_http`, but returns `None` instead of raising
    when the request carries no token or the token is not valid. Deliberately a
    sync `def`: FastAPI then runs it in the threadpool, so the blocking
    `requests` call never sits on the event loop.
    """
    if not token:
        return None
    try:
        return get_current_user_via_http(token)
    except HTTPException:
        return None


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


# ============================================================
# Internal service-to-service authentication (FEAT-162 §3.4)
# ============================================================
# Behaviour copied from locations-service (`app/main.py`, verify_internal_token):
# the caller must present `X-Internal-Token` matching the INTERNAL_SERVICE_TOKEN
# env var. Fail-closed: an unset/empty env var rejects every request with 503,
# so a missing config can never silently disable auth on an internal endpoint.

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
