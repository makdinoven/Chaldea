# auth_http.py (файл в сервисе уведомлений)
import os
import requests
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Optional

class UserRead(BaseModel):
    id: int
    username: str
    role: Optional[str] = None

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
