"""
Pydantic schemas for the support ticket feature.
Uses Pydantic <2.0 syntax (class Config: orm_mode = True).
"""

from enum import Enum
from typing import Optional, List
from datetime import datetime

from pydantic import BaseModel, Field, validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TicketCategory(str, Enum):
    bug = "bug"
    question = "question"
    suggestion = "suggestion"
    complaint = "complaint"
    other = "other"


class TicketStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    awaiting_reply = "awaiting_reply"
    closed = "closed"


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class CreateTicketRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=255)
    category: TicketCategory = TicketCategory.other
    content: str = Field(..., min_length=1, max_length=5000)
    attachment_url: Optional[str] = None

    @validator("subject")
    def strip_and_validate_subject(cls, v):
        v = v.strip()
        if len(v) < 1:
            raise ValueError("Тема тикета не может быть пустой")
        if len(v) > 255:
            raise ValueError("Тема тикета не может быть длиннее 255 символов")
        return v

    @validator("content")
    def strip_and_validate_content(cls, v):
        v = v.strip()
        if len(v) < 1:
            raise ValueError("Сообщение не может быть пустым")
        if len(v) > 5000:
            raise ValueError("Сообщение не может быть длиннее 5000 символов")
        return v


class CreateTicketMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    attachment_url: Optional[str] = None

    @validator("content")
    def strip_and_validate_content(cls, v):
        v = v.strip()
        if len(v) < 1:
            raise ValueError("Сообщение не может быть пустым")
        if len(v) > 5000:
            raise ValueError("Сообщение не может быть длиннее 5000 символов")
        return v


class ChangeTicketStatusRequest(BaseModel):
    status: TicketStatus


# ---------------------------------------------------------------------------
# Responses — Message
# ---------------------------------------------------------------------------

class TicketMessageResponse(BaseModel):
    id: int
    ticket_id: int
    sender_id: int
    sender_username: Optional[str] = None
    sender_avatar: Optional[str] = None
    content: str
    attachment_url: Optional[str] = None
    is_admin: bool
    created_at: datetime

    class Config:
        orm_mode = True


class TicketLastMessage(BaseModel):
    id: int
    sender_id: int
    sender_username: Optional[str] = None
    content: str
    attachment_url: Optional[str] = None
    is_admin: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Responses — Ticket
# ---------------------------------------------------------------------------

class TicketListItem(BaseModel):
    id: int
    user_id: int
    subject: str
    category: TicketCategory
    status: TicketStatus
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None
    closed_by: Optional[int] = None
    last_message: Optional[TicketLastMessage] = None
    message_count: int = 0

    class Config:
        orm_mode = True


class AdminTicketListItem(TicketListItem):
    username: Optional[str] = None


class TicketDetail(BaseModel):
    id: int
    user_id: int
    subject: str
    category: TicketCategory
    status: TicketStatus
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None
    closed_by: Optional[int] = None
    username: Optional[str] = None

    class Config:
        orm_mode = True


class TicketStatusResponse(BaseModel):
    id: int
    status: TicketStatus
    closed_at: Optional[datetime] = None
    closed_by: Optional[int] = None

    class Config:
        orm_mode = True


# ---------------------------------------------------------------------------
# Paginated wrappers
# ---------------------------------------------------------------------------

class PaginatedTickets(BaseModel):
    items: List[TicketListItem]
    total: int
    page: int
    page_size: int


class PaginatedAdminTickets(BaseModel):
    items: List[AdminTicketListItem]
    total: int
    page: int
    page_size: int


class PaginatedTicketMessages(BaseModel):
    items: List[TicketMessageResponse]
    total: int
    page: int
    page_size: int


class TicketDetailResponse(BaseModel):
    ticket: TicketDetail
    messages: PaginatedTicketMessages


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

class OpenTicketCountResponse(BaseModel):
    open_count: int
