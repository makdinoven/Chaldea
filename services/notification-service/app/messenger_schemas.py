"""
Pydantic schemas for the private messenger feature.
Uses Pydantic <2.0 syntax (class Config: orm_mode = True).
"""

from enum import Enum
from typing import Optional, List
from datetime import datetime

from pydantic import BaseModel, Field, validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ConversationType(str, Enum):
    direct = "direct"
    group = "group"


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class ConversationCreate(BaseModel):
    type: ConversationType
    participant_ids: List[int] = Field(..., min_items=1)
    title: Optional[str] = Field(None, max_length=100)

    @validator("title")
    def strip_title(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) == 0:
                return None
        return v


class PrivateMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    reply_to_id: Optional[int] = None

    @validator("content")
    def strip_and_validate_content(cls, v):
        v = v.strip()
        if len(v) < 1:
            raise ValueError("Сообщение не может быть пустым")
        if len(v) > 2000:
            raise ValueError("Сообщение не может быть длиннее 2000 символов")
        return v


class PrivateMessageUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)

    @validator("content")
    def strip_and_validate_content(cls, v):
        v = v.strip()
        if len(v) < 1:
            raise ValueError("Сообщение не может быть пустым")
        if len(v) > 2000:
            raise ValueError("Сообщение не может быть длиннее 2000 символов")
        return v


class AddParticipantsRequest(BaseModel):
    user_ids: List[int] = Field(..., min_items=1)


# ---------------------------------------------------------------------------
# Participant info (used inside conversation responses)
# ---------------------------------------------------------------------------

class ParticipantInfo(BaseModel):
    user_id: int
    username: Optional[str] = None
    avatar: Optional[str] = None
    avatar_frame: Optional[str] = None

    class Config:
        orm_mode = True


# ---------------------------------------------------------------------------
# Message responses
# ---------------------------------------------------------------------------

class ReplyPreview(BaseModel):
    id: int
    sender_id: int
    sender_username: Optional[str] = None
    sender_avatar: Optional[str] = None
    content: str
    is_deleted: bool = False

    class Config:
        orm_mode = True


class PrivateMessageResponse(BaseModel):
    id: int
    conversation_id: int
    sender_id: int
    sender_username: Optional[str] = None
    sender_avatar: Optional[str] = None
    sender_avatar_frame: Optional[str] = None
    content: str
    created_at: datetime
    is_deleted: bool = False
    edited_at: Optional[datetime] = None
    reply_to_id: Optional[int] = None
    reply_to: Optional[ReplyPreview] = None

    class Config:
        orm_mode = True


# ---------------------------------------------------------------------------
# Last-message preview (inside conversation list item)
# ---------------------------------------------------------------------------

class LastMessagePreview(BaseModel):
    id: int
    sender_id: int
    sender_username: Optional[str] = None
    content: str
    created_at: datetime
    edited_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Conversation responses
# ---------------------------------------------------------------------------

class ConversationResponse(BaseModel):
    id: int
    type: ConversationType
    title: Optional[str] = None
    created_by: int
    created_at: datetime
    participants: List[ParticipantInfo] = []

    class Config:
        orm_mode = True


class ConversationListItem(BaseModel):
    id: int
    type: ConversationType
    title: Optional[str] = None
    created_at: datetime
    participants: List[ParticipantInfo] = []
    last_message: Optional[LastMessagePreview] = None
    unread_count: int = 0

    class Config:
        orm_mode = True


# ---------------------------------------------------------------------------
# Paginated wrappers
# ---------------------------------------------------------------------------

class PaginatedConversations(BaseModel):
    items: List[ConversationListItem]
    total: int
    page: int
    page_size: int


class PaginatedMessages(BaseModel):
    items: List[PrivateMessageResponse]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Misc responses
# ---------------------------------------------------------------------------

class UnreadCountResponse(BaseModel):
    total_unread: int


class AddParticipantsResponse(BaseModel):
    added: List[int]
    skipped: List[int]
