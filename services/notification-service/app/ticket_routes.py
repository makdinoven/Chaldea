"""
Support ticket REST endpoints for notification-service.
All endpoints are under the /notifications/tickets prefix (Nginx routes /notifications/*).
"""

import json
import logging
import re
import time
from typing import Optional, Dict

import pika
import requests
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, status
from sqlalchemy.orm import Session

from auth_http import (
    get_current_user_via_http,
    require_permission,
    UserRead,
    AUTH_SERVICE_URL,
    OAUTH2_SCHEME,
)
from database import get_db
from ticket_schemas import (
    CreateTicketRequest,
    CreateTicketMessageRequest,
    ChangeTicketStatusRequest,
    TicketListItem,
    AdminTicketListItem,
    TicketDetail,
    TicketDetailResponse,
    TicketMessageResponse,
    TicketLastMessage,
    TicketStatusResponse,
    PaginatedTickets,
    PaginatedAdminTickets,
    PaginatedTicketMessages,
    OpenTicketCountResponse,
)
import ticket_crud
from ws_manager import send_to_user

logger = logging.getLogger(__name__)

ticket_router = APIRouter(prefix="/notifications/tickets", tags=["tickets"])


# ---------------------------------------------------------------------------
# Rate limiting (in-memory, per-instance)
# ---------------------------------------------------------------------------

_last_message_time: dict = {}
_MESSAGE_RATE_LIMIT_SECONDS = 1.0

_ticket_creation_times: dict = {}
_TICKET_RATE_LIMIT_COUNT = 3
_TICKET_RATE_LIMIT_WINDOW = 300.0  # 3 tickets per 5 minutes


# ---------------------------------------------------------------------------
# HTML tag stripping (XSS prevention)
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Strip HTML tags from text to prevent XSS."""
    return _HTML_TAG_RE.sub("", text)


# ---------------------------------------------------------------------------
# Cross-service helpers
# ---------------------------------------------------------------------------

def _fetch_user_profile(user_id: int) -> dict:
    """Fetch user profile data (username, avatar) from user-service."""
    try:
        url = f"{AUTH_SERVICE_URL}/users/{user_id}/profile"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "username": data.get("username"),
                "avatar": data.get("avatar"),
            }
    except Exception as e:
        logger.warning("Failed to fetch profile for user %d: %s", user_id, e)
    return {"username": None, "avatar": None}


def _publish_notification(payload: dict):
    """Publish a notification to the general_notifications RabbitMQ queue."""
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host="rabbitmq",
                socket_timeout=5,
                connection_attempts=1,
                retry_delay=1,
            )
        )
        channel = connection.channel()
        channel.queue_declare(queue="general_notifications", durable=True)
        channel.basic_publish(
            exchange='',
            routing_key="general_notifications",
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2),
        )
        connection.close()
    except Exception as e:
        logger.warning("Failed to publish notification to RabbitMQ: %s", e)


def _check_ticket_creation_rate_limit(user_id: int):
    """Check if user exceeded ticket creation rate limit (3 per 5 min)."""
    now = time.time()
    timestamps = _ticket_creation_times.get(user_id, [])
    timestamps = [t for t in timestamps if now - t < _TICKET_RATE_LIMIT_WINDOW]
    if len(timestamps) >= _TICKET_RATE_LIMIT_COUNT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много тикетов. Подождите немного перед созданием нового",
        )
    timestamps.append(now)
    _ticket_creation_times[user_id] = timestamps


def _check_message_rate_limit(user_id: int):
    """Check if user exceeded message rate limit (1 per second)."""
    now = time.time()
    last_time = _last_message_time.get(user_id, 0.0)
    if now - last_time < _MESSAGE_RATE_LIMIT_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Подождите перед отправкой следующего сообщения",
        )


def _enrich_ticket_list_item(db: Session, ticket, include_username: bool = False) -> dict:
    """Build a ticket list item dict with last_message and message_count."""
    last_msg = ticket_crud.get_last_message(db, ticket.id)
    msg_count = ticket_crud.get_message_count(db, ticket.id)

    last_message_data = None
    if last_msg:
        sender_profile = _fetch_user_profile(last_msg.sender_id)
        last_message_data = {
            "id": last_msg.id,
            "sender_id": last_msg.sender_id,
            "sender_username": sender_profile["username"],
            "content": last_msg.content[:100],  # preview
            "attachment_url": last_msg.attachment_url,
            "is_admin": last_msg.is_admin,
            "created_at": last_msg.created_at,
        }

    item = {
        "id": ticket.id,
        "user_id": ticket.user_id,
        "subject": ticket.subject,
        "category": ticket.category,
        "status": ticket.status,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "closed_at": ticket.closed_at,
        "closed_by": ticket.closed_by,
        "last_message": last_message_data,
        "message_count": msg_count,
    }

    if include_username:
        profile = _fetch_user_profile(ticket.user_id)
        item["username"] = profile["username"]

    return item


# Status label mapping for notifications (Russian)
_STATUS_LABELS = {
    "open": "Открыт",
    "in_progress": "В работе",
    "awaiting_reply": "Ожидает ответа",
    "closed": "Закрыт",
}


# ---------------------------------------------------------------------------
# POST /notifications/tickets — Create ticket
# ---------------------------------------------------------------------------

@ticket_router.post("", status_code=201)
def create_ticket(
    data: CreateTicketRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    # Rate limit
    _check_ticket_creation_rate_limit(current_user.id)

    # Sanitize inputs
    subject = _strip_html(data.subject)
    content = _strip_html(data.content)

    # Create ticket + first message
    ticket = ticket_crud.create_ticket(
        db=db,
        user_id=current_user.id,
        subject=subject,
        category=data.category.value,
        content=content,
        attachment_url=data.attachment_url,
        is_admin=False,
    )

    # Build response
    result = _enrich_ticket_list_item(db, ticket)
    return result


# ---------------------------------------------------------------------------
# GET /notifications/tickets — List user's own tickets
# ---------------------------------------------------------------------------

@ticket_router.get("", response_model=PaginatedTickets)
def list_user_tickets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    ticket_status: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    result = ticket_crud.get_tickets_by_user(
        db=db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        status_filter=ticket_status,
    )

    items = []
    for ticket in result["items"]:
        items.append(_enrich_ticket_list_item(db, ticket))

    return {
        "items": items,
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
    }


# ---------------------------------------------------------------------------
# GET /notifications/tickets/admin/count — Open ticket count (admin badge)
# ---------------------------------------------------------------------------

@ticket_router.get("/admin/count", response_model=OpenTicketCountResponse)
def get_open_ticket_count(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("tickets:read")),
):
    count = ticket_crud.get_open_ticket_count(db)
    return {"open_count": count}


# ---------------------------------------------------------------------------
# GET /notifications/tickets/admin/list — List all tickets (admin)
# ---------------------------------------------------------------------------

@ticket_router.get("/admin/list", response_model=PaginatedAdminTickets)
def list_all_tickets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    ticket_status: Optional[str] = Query(None, alias="status"),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("tickets:read")),
):
    result = ticket_crud.get_all_tickets(
        db=db,
        page=page,
        page_size=page_size,
        status_filter=ticket_status,
        category_filter=category,
    )

    items = []
    for ticket in result["items"]:
        items.append(_enrich_ticket_list_item(db, ticket, include_username=True))

    return {
        "items": items,
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
    }


# ---------------------------------------------------------------------------
# GET /notifications/tickets/{ticket_id} — Get ticket detail with messages
# ---------------------------------------------------------------------------

@ticket_router.get("/{ticket_id}", response_model=TicketDetailResponse)
def get_ticket_detail(
    ticket_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    ticket = ticket_crud.get_ticket_by_id(db, ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Тикет не найден",
        )

    # Authorization: owner or admin with tickets:read
    is_owner = ticket.user_id == current_user.id
    has_read_perm = "tickets:read" in current_user.permissions
    if not is_owner and not has_read_perm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этому тикету",
        )

    # Ticket detail
    owner_profile = _fetch_user_profile(ticket.user_id)
    ticket_detail = TicketDetail(
        id=ticket.id,
        user_id=ticket.user_id,
        subject=ticket.subject,
        category=ticket.category,
        status=ticket.status,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        closed_at=ticket.closed_at,
        closed_by=ticket.closed_by,
        username=owner_profile["username"],
    )

    # Messages (paginated, ASC order)
    msg_result = ticket_crud.get_ticket_messages(
        db=db,
        ticket_id=ticket_id,
        page=page,
        page_size=page_size,
    )

    # Enrich messages with sender profiles
    profile_cache: Dict[int, dict] = {}
    enriched_messages = []
    for msg in msg_result["items"]:
        sender_id = msg.sender_id
        if sender_id not in profile_cache:
            profile_cache[sender_id] = _fetch_user_profile(sender_id)
        profile = profile_cache[sender_id]

        enriched_messages.append(
            TicketMessageResponse(
                id=msg.id,
                ticket_id=msg.ticket_id,
                sender_id=msg.sender_id,
                sender_username=profile["username"],
                sender_avatar=profile["avatar"],
                content=msg.content,
                attachment_url=msg.attachment_url,
                is_admin=msg.is_admin,
                created_at=msg.created_at,
            )
        )

    return TicketDetailResponse(
        ticket=ticket_detail,
        messages=PaginatedTicketMessages(
            items=enriched_messages,
            total=msg_result["total"],
            page=msg_result["page"],
            page_size=msg_result["page_size"],
        ),
    )


# ---------------------------------------------------------------------------
# POST /notifications/tickets/{ticket_id}/messages — Add message to ticket
# ---------------------------------------------------------------------------

@ticket_router.post("/{ticket_id}/messages", response_model=TicketMessageResponse, status_code=201)
def send_ticket_message(
    ticket_id: int,
    data: CreateTicketMessageRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    # Rate limit
    _check_message_rate_limit(current_user.id)

    # Check ticket exists
    ticket = ticket_crud.get_ticket_by_id(db, ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Тикет не найден",
        )

    # Check ticket is not closed
    if ticket.status == "closed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Тикет закрыт, отправка сообщений невозможна",
        )

    # Authorization: owner or admin with tickets:reply
    is_owner = ticket.user_id == current_user.id
    has_reply_perm = "tickets:reply" in current_user.permissions
    if not is_owner and not has_reply_perm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этому тикету",
        )

    # Determine if sender is admin
    is_admin = has_reply_perm

    # Sanitize content
    content = _strip_html(data.content)

    # Create message
    msg = ticket_crud.create_ticket_message(
        db=db,
        ticket_id=ticket_id,
        sender_id=current_user.id,
        content=content,
        is_admin=is_admin,
        attachment_url=data.attachment_url,
    )

    # Update rate limit
    _last_message_time[current_user.id] = time.time()

    # Auto-update ticket status based on sender
    if is_admin:
        # Admin replied: set status to awaiting_reply
        if ticket.status != "awaiting_reply":
            ticket_crud.update_ticket_status(db, ticket_id, "awaiting_reply")

        # Notify ticket owner
        background_tasks.add_task(
            _publish_notification,
            {
                "target_type": "user",
                "target_value": ticket.user_id,
                "message": f"Администратор ответил на ваш тикет: {ticket.subject}",
                "ws_type": "ticket_reply",
                "ws_data": {"ticket_id": ticket.id},
            },
        )
    else:
        # User replied: set status back to open if was awaiting_reply
        if ticket.status == "awaiting_reply":
            ticket_crud.update_ticket_status(db, ticket_id, "open")

        # Notify admins about new user message
        background_tasks.add_task(
            _publish_notification,
            {
                "target_type": "admins",
                "target_value": None,
                "message": f"Новое сообщение в тикете #{ticket.id}: {ticket.subject}",
                "ws_type": "ticket_new_message",
                "ws_data": {"ticket_id": ticket.id},
            },
        )

    # Build response
    sender_profile = _fetch_user_profile(current_user.id)
    return TicketMessageResponse(
        id=msg.id,
        ticket_id=msg.ticket_id,
        sender_id=msg.sender_id,
        sender_username=sender_profile["username"] or current_user.username,
        sender_avatar=sender_profile["avatar"],
        content=msg.content,
        attachment_url=msg.attachment_url,
        is_admin=msg.is_admin,
        created_at=msg.created_at,
    )


# ---------------------------------------------------------------------------
# PATCH /notifications/tickets/{ticket_id}/status — Change ticket status (admin)
# ---------------------------------------------------------------------------

@ticket_router.patch("/{ticket_id}/status", response_model=TicketStatusResponse)
def change_ticket_status(
    ticket_id: int,
    data: ChangeTicketStatusRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("tickets:manage")),
):
    ticket = ticket_crud.get_ticket_by_id(db, ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Тикет не найден",
        )

    new_status = data.status.value
    updated = ticket_crud.update_ticket_status(
        db=db,
        ticket_id=ticket_id,
        new_status=new_status,
        closed_by=current_user.id if new_status == "closed" else None,
    )

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Тикет не найден",
        )

    # Notify ticket owner about status change
    status_label = _STATUS_LABELS.get(new_status, new_status)
    background_tasks.add_task(
        _publish_notification,
        {
            "target_type": "user",
            "target_value": ticket.user_id,
            "message": f"Статус вашего тикета #{ticket.id} изменён на: {status_label}",
            "ws_type": "ticket_status_changed",
            "ws_data": {"ticket_id": ticket.id, "status": new_status},
        },
    )

    return TicketStatusResponse(
        id=updated.id,
        status=updated.status,
        closed_at=updated.closed_at,
        closed_by=updated.closed_by,
    )
