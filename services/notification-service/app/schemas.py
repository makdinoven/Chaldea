from enum import Enum

from pydantic import BaseModel
from typing import Dict, List, Optional
from datetime import datetime

class NotificationBase(BaseModel):
    user_id: int
    message: str

class NotificationCreate(NotificationBase):
    category: Optional[str] = None

class Notification(BaseModel):
    id: int
    user_id: int
    message: str
    status: str
    created_at: datetime
    category: Optional[str] = None

    class Config:
        orm_mode = True

class NotificationTargetType(str, Enum):
    user = "user"      # только один пользователь (target_value = user_id)
    all = "all"        # все пользователи
    admins = "admins"  # все пользователи с ролью admin (пример)

# Pydantic-модель для входящего сообщения в очередь "general_notifications"
class GeneralNotificationPayload(BaseModel):
    target_type: NotificationTargetType
    target_value: Optional[int] = None  # когда target_type="user", это user_id
    message: str
    # One of notification_categories.ALL_CATEGORIES; unknown/missing values are
    # resolved by the consumer (ws_type fallback, then "system").
    category: Optional[str] = None


class NotificationPreferences(BaseModel):
    """GET/PUT /notifications/me/preferences body and response."""
    preferences: Dict[str, str]


class SessionsRevokedPayload(BaseModel):
    """Internal call from user-service: close WebSockets of revoked sessions.

    At most one of `session_ids` / `all_except`; neither = all of the user's sockets.
    """
    user_id: int
    session_ids: Optional[List[str]] = None
    all_except: Optional[str] = None
