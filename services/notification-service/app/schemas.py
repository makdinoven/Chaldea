from enum import Enum

from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class NotificationBase(BaseModel):
    user_id: int
    message: str

class NotificationCreate(NotificationBase):
    pass

class Notification(BaseModel):
    id: int
    user_id: int
    message: str
    status: str
    created_at: datetime

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