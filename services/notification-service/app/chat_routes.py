"""
Chat REST endpoints and SSE stream for notification-service.
All endpoints are under the /notifications/chat prefix (Nginx routes /notifications/*).
"""

import asyncio
import json
import logging
import os
import time
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from auth_http import get_current_user_via_http, require_permission, UserRead, OAUTH2_SCHEME, AUTH_SERVICE_URL
from database import get_db
from chat_schemas import (
    ChatChannel,
    ChatMessageCreate,
    ChatMessageResponse,
    ChatBanCreate,
    ChatBanResponse,
    ChatBanStatus,
    PaginatedChatMessages,
)
import chat_crud
from sse_manager import add_chat_connection, remove_chat_connection, broadcast_to_channel, broadcast_to_all

logger = logging.getLogger(__name__)

chat_router = APIRouter(prefix="/notifications/chat", tags=["chat"])

# ---------------------------------------------------------------------------
# Rate limiting (in-memory, per-instance)
# ---------------------------------------------------------------------------

_last_message_time: dict[int, float] = {}
_RATE_LIMIT_SECONDS = 2.0


# ---------------------------------------------------------------------------
# Helper: fetch user avatar/avatar_frame from user-service
# ---------------------------------------------------------------------------

def _fetch_user_profile_data(user_id: int) -> dict:
    """
    Fetch avatar and avatar_frame from user-service profile endpoint.
    Returns dict with 'avatar' and 'avatar_frame' keys (may be None).
    """
    try:
        url = f"{AUTH_SERVICE_URL}/users/{user_id}/profile"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "avatar": data.get("avatar"),
                "avatar_frame": data.get("avatar_frame"),
            }
    except Exception as e:
        logger.warning("Failed to fetch user profile data for user %d: %s", user_id, e)

    return {"avatar": None, "avatar_frame": None}


# ---------------------------------------------------------------------------
# Helper: optional auth (for endpoints where auth is not required)
# ---------------------------------------------------------------------------

def _get_optional_user(token: Optional[str] = Depends(OAUTH2_SCHEME)) -> Optional[UserRead]:
    """Try to authenticate but return None if no token or invalid token."""
    if not token:
        return None
    try:
        return get_current_user_via_http(token)
    except HTTPException:
        return None


# ---------------------------------------------------------------------------
# POST /chat/messages — Send a message
# ---------------------------------------------------------------------------

@chat_router.post("/messages", response_model=ChatMessageResponse, status_code=201)
def send_message(
    data: ChatMessageCreate,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    # 1. Check ban
    if chat_crud.is_user_banned(db, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы заблокированы в чате",
        )

    # 2. Rate limit
    now = time.time()
    last_time = _last_message_time.get(current_user.id, 0.0)
    if now - last_time < _RATE_LIMIT_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Подождите перед отправкой следующего сообщения",
        )

    # 3. Fetch avatar and avatar_frame from user-service
    profile_data = _fetch_user_profile_data(current_user.id)

    # 4. Insert into DB
    msg = chat_crud.create_message(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        avatar=profile_data["avatar"],
        avatar_frame=profile_data["avatar_frame"],
        message_data=data,
    )

    # 5. Update rate limit timestamp
    _last_message_time[current_user.id] = time.time()

    # 6. Cleanup old messages if exceeding 500
    chat_crud.cleanup_old_messages(db, data.channel.value, limit=500)

    # 7. Build response
    response = ChatMessageResponse.from_orm(msg)

    # 8. Broadcast via SSE
    broadcast_to_channel(data.channel.value, {
        "type": "chat_message",
        "data": json.loads(response.json()),
    })

    # 9. Increment activity points (fire-and-forget, don't block on failure)
    try:
        requests.post(
            f"{AUTH_SERVICE_URL}/users/{current_user.id}/activity/increment",
            json={"points": 1},
            timeout=3,
        )
    except Exception:
        pass  # Non-critical, don't fail the message send

    return response


# ---------------------------------------------------------------------------
# GET /chat/messages — Paginated message list
# ---------------------------------------------------------------------------

@chat_router.get("/messages", response_model=PaginatedChatMessages)
def get_messages(
    channel: ChatChannel,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    result = chat_crud.get_messages(db, channel.value, page, page_size)
    return result


# ---------------------------------------------------------------------------
# DELETE /chat/messages/{message_id} — Delete message (moderation)
# ---------------------------------------------------------------------------

@chat_router.delete("/messages/{message_id}")
def delete_message(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("chat:delete")),
):
    deleted = chat_crud.delete_message(db, message_id)
    if deleted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сообщение не найдено",
        )

    # Broadcast deletion event to all connected chat clients
    broadcast_to_all({
        "type": "chat_message_deleted",
        "data": {"id": deleted.id, "channel": deleted.channel},
    })

    return {"detail": "Сообщение удалено"}


# ---------------------------------------------------------------------------
# POST /chat/bans — Ban a user
# ---------------------------------------------------------------------------

@chat_router.post("/bans", response_model=ChatBanResponse, status_code=201)
def ban_user(
    data: ChatBanCreate,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("chat:ban")),
):
    ban = chat_crud.create_ban(
        db=db,
        user_id=data.user_id,
        banned_by=current_user.id,
        reason=data.reason,
        expires_at=data.expires_at,
    )
    if ban is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь уже заблокирован в чате",
        )
    return ban


# ---------------------------------------------------------------------------
# DELETE /chat/bans/{user_id} — Unban a user
# ---------------------------------------------------------------------------

@chat_router.delete("/bans/{user_id}")
def unban_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("chat:ban")),
):
    removed = chat_crud.remove_ban(db, user_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Бан не найден",
        )
    return {"detail": "Пользователь разбанен"}


# ---------------------------------------------------------------------------
# GET /chat/bans/{user_id} — Check ban status
# ---------------------------------------------------------------------------

@chat_router.get("/bans/{user_id}", response_model=ChatBanStatus)
def check_ban(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    # Users can check their own ban; users with chat:ban can check anyone's
    if user_id != current_user.id and "chat:ban" not in current_user.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав",
        )

    ban = chat_crud.get_ban(db, user_id)
    if ban is None:
        return ChatBanStatus(is_banned=False)

    return ChatBanStatus(
        is_banned=True,
        reason=ban.reason,
        expires_at=ban.expires_at,
    )


# ---------------------------------------------------------------------------
# GET /chat/stream — SSE stream for real-time chat
# ---------------------------------------------------------------------------

@chat_router.get("/stream")
async def chat_sse_stream(
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """
    SSE endpoint for real-time chat messages.
    Client connects once; receives events for ALL channels.
    Frontend filters by the currently active tab.
    """
    user_id = current_user.id
    queue = add_chat_connection(user_id)

    async def event_generator():
        try:
            while True:
                try:
                    # Wait for a message with a timeout for keepalive
                    data_str = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {data_str}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive ping
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            remove_chat_connection(user_id)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
