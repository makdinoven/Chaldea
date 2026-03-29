from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field, validator
from datetime import datetime


class ChatChannel(str, Enum):
    general = "general"
    trade = "trade"
    help = "help"


class ChatMessageCreate(BaseModel):
    channel: ChatChannel
    content: str = Field(..., min_length=1, max_length=500)
    reply_to_id: Optional[int] = None

    @validator("content")
    def strip_and_validate_content(cls, v):
        v = v.strip()
        if len(v) < 1:
            raise ValueError("Сообщение не может быть пустым")
        if len(v) > 500:
            raise ValueError("Сообщение не может быть длиннее 500 символов")
        return v


class ChatMessageReplyInfo(BaseModel):
    id: int
    username: str
    content: str

    class Config:
        orm_mode = True


class ChatMessageResponse(BaseModel):
    id: int
    channel: ChatChannel
    user_id: int
    username: str
    avatar: Optional[str] = None
    avatar_frame: Optional[str] = None
    chat_background: Optional[str] = None
    content: str
    reply_to_id: Optional[int] = None
    reply_to: Optional[ChatMessageReplyInfo] = None
    created_at: datetime

    class Config:
        orm_mode = True


class PaginatedChatMessages(BaseModel):
    items: List[ChatMessageResponse]
    total: int
    page: int
    page_size: int


class ChatBanCreate(BaseModel):
    user_id: int
    reason: Optional[str] = Field(None, max_length=500)
    expires_at: Optional[datetime] = None


class ChatBanResponse(BaseModel):
    id: int
    user_id: int
    banned_by: int
    reason: Optional[str] = None
    banned_at: datetime
    expires_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class ChatBanStatus(BaseModel):
    is_banned: bool
    reason: Optional[str] = None
    expires_at: Optional[datetime] = None
