"""
Messenger REST endpoints for notification-service.
All endpoints are under the /notifications/messenger prefix (Nginx routes /notifications/*).
Implements private 1-on-1 and group conversations with cross-service block/privacy checks.
"""

import logging
import re
import time
from typing import Optional, Set, Dict

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from auth_http import get_current_user_via_http, UserRead, AUTH_SERVICE_URL, OAUTH2_SCHEME
from database import get_db
from messenger_schemas import (
    ConversationCreate,
    ConversationResponse,
    PaginatedConversations,
    PaginatedMessages,
    PrivateMessageCreate,
    PrivateMessageUpdate,
    PrivateMessageResponse,
    ReplyPreview,
    AddParticipantsRequest,
    AddParticipantsResponse,
    UnreadCountResponse,
)
import messenger_crud
from ws_manager import send_to_user

logger = logging.getLogger(__name__)

messenger_router = APIRouter(prefix="/notifications/messenger", tags=["messenger"])

# ---------------------------------------------------------------------------
# Rate limiting (in-memory, per-instance)
# ---------------------------------------------------------------------------

_last_message_time: dict[int, float] = {}
_MESSAGE_RATE_LIMIT_SECONDS = 1.0

_last_conversation_time: dict[int, list] = {}
_CONVERSATION_RATE_LIMIT_COUNT = 5
_CONVERSATION_RATE_LIMIT_WINDOW = 60.0  # 5 conversations per 60 seconds


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

def _check_block_status(token: str, other_user_id: int) -> dict:
    """Check block status between current user and other_user_id via user-service.
    Returns {'is_blocked': bool, 'blocked_by_me': bool, 'blocked_by_them': bool}.
    """
    try:
        url = f"{AUTH_SERVICE_URL}/users/blocks/check/{other_user_id}"
        resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.warning("Failed to check block status for user %d: %s", other_user_id, e)
    return {"is_blocked": False, "blocked_by_me": False, "blocked_by_them": False}


def _get_message_privacy(user_id: int) -> str:
    """Get a user's message privacy setting via user-service.
    Returns 'all', 'friends', or 'nobody'.
    """
    try:
        url = f"{AUTH_SERVICE_URL}/users/{user_id}/message-privacy"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("message_privacy", "all")
    except Exception as e:
        logger.warning("Failed to get message privacy for user %d: %s", user_id, e)
    return "all"


def _check_friendship(token: str, friend_id: int) -> bool:
    """Check if current user is friends with friend_id via user-service."""
    try:
        url = f"{AUTH_SERVICE_URL}/users/friends/check/{friend_id}"
        resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("is_friend", False)
    except Exception as e:
        logger.warning("Failed to check friendship with user %d: %s", friend_id, e)
    return False


def _fetch_user_profile(user_id: int) -> dict:
    """Fetch user profile data (username, avatar, avatar_frame) from user-service."""
    try:
        url = f"{AUTH_SERVICE_URL}/users/{user_id}/profile"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "username": data.get("username"),
                "avatar": data.get("avatar"),
                "avatar_frame": data.get("avatar_frame"),
            }
    except Exception as e:
        logger.warning("Failed to fetch profile for user %d: %s", user_id, e)
    return {"username": None, "avatar": None, "avatar_frame": None}


def _get_blocked_user_ids(token: str) -> Set[int]:
    """Get the set of user IDs blocked by the current user (via block list endpoint)."""
    try:
        url = f"{AUTH_SERVICE_URL}/users/blocks"
        resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            return {item["blocked_user_id"] for item in items}
    except Exception as e:
        logger.warning("Failed to fetch blocked users: %s", e)
    return set()


def _enrich_participants(participant_dicts: list) -> list:
    """Enrich participant dicts with username/avatar from user-service profiles."""
    for p in participant_dicts:
        profile = _fetch_user_profile(p["user_id"])
        p["username"] = profile["username"]
        p["avatar"] = profile["avatar"]
        p["avatar_frame"] = profile["avatar_frame"]
    return participant_dicts


def _check_conversation_rate_limit(user_id: int):
    """Check if user exceeded conversation creation rate limit (5 per minute)."""
    now = time.time()
    timestamps = _last_conversation_time.get(user_id, [])
    # Remove old timestamps outside the window
    timestamps = [t for t in timestamps if now - t < _CONVERSATION_RATE_LIMIT_WINDOW]
    if len(timestamps) >= _CONVERSATION_RATE_LIMIT_COUNT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много создаваемых бесед. Подождите немного",
        )
    timestamps.append(now)
    _last_conversation_time[user_id] = timestamps


def _can_message_user(token: str, sender_id: int, recipient_id: int) -> Optional[str]:
    """Check if sender can message recipient (blocks + privacy).
    Returns None if allowed, or a Russian error message string if not.
    """
    # 1. Block check
    block_info = _check_block_status(token, recipient_id)
    if block_info.get("is_blocked"):
        if block_info.get("blocked_by_me"):
            return "Вы заблокировали этого пользователя"
        return "Пользователь заблокировал вас"

    # 2. Privacy check
    privacy = _get_message_privacy(recipient_id)
    if privacy == "nobody":
        return "Пользователь не принимает сообщения"
    if privacy == "friends":
        is_friend = _check_friendship(token, recipient_id)
        if not is_friend:
            return "Пользователь принимает сообщения только от друзей"

    return None


# ---------------------------------------------------------------------------
# POST /messenger/conversations — Create conversation
# ---------------------------------------------------------------------------

@messenger_router.post("/conversations", response_model=ConversationResponse, status_code=201)
def create_conversation(
    data: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
    token: str = Depends(OAUTH2_SCHEME),
):
    # Rate limit
    _check_conversation_rate_limit(current_user.id)

    # Remove self from participant list if present
    participant_ids = [pid for pid in data.participant_ids if pid != current_user.id]

    if not participant_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя создать беседу только с собой",
        )

    # Determine conversation type
    conv_type = data.type.value
    if conv_type == "group" and len(participant_ids) == 1:
        conv_type = "direct"

    # Group chat requires title
    if conv_type == "group" and not data.title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для группового чата необходимо указать название",
        )

    # For direct: only 1 participant allowed
    if conv_type == "direct" and len(participant_ids) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для личного чата можно указать только одного участника",
        )

    # For direct: check existing conversation
    if conv_type == "direct":
        existing = messenger_crud.find_existing_direct(db, current_user.id, participant_ids[0])
        if existing:
            # Return existing conversation with 200
            participants = [
                {"user_id": p.user_id, "username": None, "avatar": None, "avatar_frame": None}
                for p in existing.participants
            ]
            _enrich_participants(participants)
            return ConversationResponse(
                id=existing.id,
                type=existing.type,
                title=existing.title,
                created_by=existing.created_by,
                created_at=existing.created_at,
                participants=participants,
            )

    # Check blocks and privacy for each participant
    valid_participants = []
    errors = []
    for pid in participant_ids:
        error = _can_message_user(token, current_user.id, pid)
        if error:
            errors.append(f"Пользователь {pid}: {error}")
        else:
            valid_participants.append(pid)

    if not valid_participants:
        # All participants blocked or have restrictive privacy
        detail = "; ".join(errors) if errors else "Невозможно создать беседу"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )

    # Create conversation
    conv = messenger_crud.create_conversation(
        db=db,
        conversation_type=conv_type,
        created_by=current_user.id,
        participant_ids=valid_participants,
        title=data.title if conv_type == "group" else None,
    )

    # Build response with enriched participants
    participants = [
        {"user_id": p.user_id, "username": None, "avatar": None, "avatar_frame": None}
        for p in conv.participants
    ]
    _enrich_participants(participants)

    response = ConversationResponse(
        id=conv.id,
        type=conv.type,
        title=conv.title,
        created_by=conv.created_by,
        created_at=conv.created_at,
        participants=participants,
    )

    # Push WebSocket event to all participants (except creator)
    ws_data = {
        "type": "conversation_created",
        "data": {
            "id": conv.id,
            "type": conv.type,
            "title": conv.title,
            "participants": [
                {
                    "user_id": p["user_id"],
                    "username": p["username"],
                    "avatar": p["avatar"],
                    "avatar_frame": p["avatar_frame"],
                }
                for p in participants
            ],
        },
    }
    for pid in valid_participants:
        if pid != current_user.id:
            send_to_user(pid, ws_data)

    return response


# ---------------------------------------------------------------------------
# GET /messenger/conversations — List conversations
# ---------------------------------------------------------------------------

@messenger_router.get("/conversations", response_model=PaginatedConversations)
def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
    token: str = Depends(OAUTH2_SCHEME),
):
    blocked_ids = _get_blocked_user_ids(token)

    result = messenger_crud.list_conversations(
        db=db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        blocked_user_ids=blocked_ids if blocked_ids else None,
    )

    # Enrich participant and last_message usernames/avatars
    for item in result["items"]:
        _enrich_participants(item["participants"])
        if item["last_message"] and item["last_message"]["sender_username"] is None:
            profile = _fetch_user_profile(item["last_message"]["sender_id"])
            item["last_message"]["sender_username"] = profile["username"]

    return result


# ---------------------------------------------------------------------------
# GET /messenger/conversations/{conversation_id}/messages — Get messages
# ---------------------------------------------------------------------------

@messenger_router.get(
    "/conversations/{conversation_id}/messages",
    response_model=PaginatedMessages,
)
def get_messages(
    conversation_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
    token: str = Depends(OAUTH2_SCHEME),
):
    # Check conversation exists
    conv = messenger_crud.get_conversation_by_id(db, conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Беседа не найдена",
        )

    # Check participation
    if not messenger_crud.is_participant(db, conversation_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы не являетесь участником этой беседы",
        )

    blocked_ids = _get_blocked_user_ids(token)

    result = messenger_crud.get_messages(
        db=db,
        conversation_id=conversation_id,
        page=page,
        page_size=page_size,
        blocked_user_ids=blocked_ids if blocked_ids else None,
    )

    # Convert ORM objects to response dicts with enriched sender info
    enriched_items = []
    # Cache profiles to avoid duplicate requests
    profile_cache: Dict[int, dict] = {}

    for msg in result["items"]:
        sender_id = msg.sender_id
        if sender_id not in profile_cache:
            profile_cache[sender_id] = _fetch_user_profile(sender_id)

        profile = profile_cache[sender_id]
        is_deleted = msg.deleted_at is not None

        # Build reply preview if message is a reply
        reply_preview = None
        if msg.reply_to_id and msg.reply_to:
            reply_sender_id = msg.reply_to.sender_id
            if reply_sender_id not in profile_cache:
                profile_cache[reply_sender_id] = _fetch_user_profile(reply_sender_id)
            reply_profile = profile_cache[reply_sender_id]
            reply_is_deleted = msg.reply_to.deleted_at is not None
            reply_preview = ReplyPreview(
                id=msg.reply_to.id,
                sender_id=reply_sender_id,
                sender_username=reply_profile["username"],
                sender_avatar=reply_profile["avatar"],
                content="" if reply_is_deleted else msg.reply_to.content,
                is_deleted=reply_is_deleted,
            )

        enriched_items.append(
            PrivateMessageResponse(
                id=msg.id,
                conversation_id=msg.conversation_id,
                sender_id=msg.sender_id,
                sender_username=profile["username"],
                sender_avatar=profile["avatar"],
                sender_avatar_frame=profile["avatar_frame"],
                content="" if is_deleted else msg.content,
                created_at=msg.created_at,
                is_deleted=is_deleted,
                edited_at=msg.edited_at,
                reply_to_id=msg.reply_to_id,
                reply_to=reply_preview,
            )
        )

    return PaginatedMessages(
        items=enriched_items,
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


# ---------------------------------------------------------------------------
# POST /messenger/conversations/{conversation_id}/messages — Send message
# ---------------------------------------------------------------------------

@messenger_router.post(
    "/conversations/{conversation_id}/messages",
    response_model=PrivateMessageResponse,
    status_code=201,
)
def send_message(
    conversation_id: int,
    data: PrivateMessageCreate,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
    token: str = Depends(OAUTH2_SCHEME),
):
    # 1. Rate limit
    now = time.time()
    last_time = _last_message_time.get(current_user.id, 0.0)
    if now - last_time < _MESSAGE_RATE_LIMIT_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Подождите перед отправкой следующего сообщения",
        )

    # 2. Check conversation exists
    conv = messenger_crud.get_conversation_by_id(db, conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Беседа не найдена",
        )

    # 3. Check participation
    if not messenger_crud.is_participant(db, conversation_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы не являетесь участником этой беседы",
        )

    # 4. For direct conversations, check blocks/privacy before sending
    if conv.type == "direct":
        participant_ids = messenger_crud.get_participant_ids(db, conversation_id)
        other_ids = [pid for pid in participant_ids if pid != current_user.id]
        if other_ids:
            error = _can_message_user(token, current_user.id, other_ids[0])
            if error:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=error,
                )

    # 5. Sanitize content (strip HTML)
    content = _strip_html(data.content)

    # 5.1. Validate reply_to_id if provided
    reply_to_id = data.reply_to_id
    reply_preview = None
    if reply_to_id is not None:
        replied_msg = messenger_crud.get_message_by_id(db, reply_to_id)
        if replied_msg is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Цитируемое сообщение не найдено",
            )
        if replied_msg.conversation_id != conversation_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Цитируемое сообщение не принадлежит этой беседе",
            )
        # Build reply preview for the response
        reply_sender_profile = _fetch_user_profile(replied_msg.sender_id)
        reply_is_deleted = replied_msg.deleted_at is not None
        reply_preview = ReplyPreview(
            id=replied_msg.id,
            sender_id=replied_msg.sender_id,
            sender_username=reply_sender_profile["username"],
            sender_avatar=reply_sender_profile["avatar"],
            content="" if reply_is_deleted else replied_msg.content,
            is_deleted=reply_is_deleted,
        )

    # 6. Insert message
    msg = messenger_crud.create_message(
        db=db,
        conversation_id=conversation_id,
        sender_id=current_user.id,
        content=content,
        reply_to_id=reply_to_id,
    )

    # 7. Update rate limit
    _last_message_time[current_user.id] = time.time()

    # 8. Fetch sender profile for response
    sender_profile = _fetch_user_profile(current_user.id)

    response = PrivateMessageResponse(
        id=msg.id,
        conversation_id=msg.conversation_id,
        sender_id=msg.sender_id,
        sender_username=sender_profile["username"] or current_user.username,
        sender_avatar=sender_profile["avatar"],
        sender_avatar_frame=sender_profile["avatar_frame"],
        content=msg.content,
        created_at=msg.created_at,
        is_deleted=False,
        edited_at=None,
        reply_to_id=msg.reply_to_id,
        reply_to=reply_preview,
    )

    # 9. Push WebSocket event to all other participants
    participant_ids = messenger_crud.get_participant_ids(db, conversation_id)
    ws_data = {
        "type": "private_message",
        "data": {
            "id": msg.id,
            "conversation_id": msg.conversation_id,
            "sender_id": msg.sender_id,
            "sender_username": response.sender_username,
            "sender_avatar": response.sender_avatar,
            "sender_avatar_frame": response.sender_avatar_frame,
            "content": msg.content,
            "created_at": msg.created_at.isoformat(),
            "reply_to_id": msg.reply_to_id,
            "reply_to": reply_preview.dict() if reply_preview else None,
        },
    }
    for pid in participant_ids:
        if pid != current_user.id:
            send_to_user(pid, ws_data)

    return response


# ---------------------------------------------------------------------------
# DELETE /messenger/messages/{message_id} — Soft delete own message
# ---------------------------------------------------------------------------

@messenger_router.delete("/messages/{message_id}")
def delete_message(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    # Check message exists
    msg = messenger_crud.get_message_by_id(db, message_id)
    if msg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сообщение не найдено",
        )

    # Check sender
    if msg.sender_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы можете удалять только свои сообщения",
        )

    # Soft delete
    deleted_msg = messenger_crud.soft_delete_message(db, message_id, current_user.id)
    if deleted_msg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сообщение не найдено",
        )

    # Push WebSocket event to all conversation participants
    conversation_id = msg.conversation_id
    participant_ids = messenger_crud.get_participant_ids(db, conversation_id)
    ws_data = {
        "type": "private_message_deleted",
        "data": {
            "message_id": message_id,
            "conversation_id": conversation_id,
        },
    }
    for pid in participant_ids:
        send_to_user(pid, ws_data)

    return {"detail": "Сообщение удалено"}


# ---------------------------------------------------------------------------
# PUT /messenger/messages/{message_id} — Edit own message
# ---------------------------------------------------------------------------

@messenger_router.put("/messages/{message_id}", response_model=PrivateMessageResponse)
def edit_message(
    message_id: int,
    data: PrivateMessageUpdate,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    # Check message exists
    msg = messenger_crud.get_message_by_id(db, message_id)
    if msg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сообщение не найдено",
        )

    # Only sender can edit
    if msg.sender_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы можете редактировать только свои сообщения",
        )

    # Cannot edit deleted messages
    if msg.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя редактировать удалённое сообщение",
        )

    # Sanitize content (strip HTML)
    content = _strip_html(data.content)

    # Update message
    updated_msg = messenger_crud.edit_message(db, message_id, content)

    # Fetch sender profile for response
    sender_profile = _fetch_user_profile(current_user.id)

    # Build reply preview if message is a reply
    reply_preview = None
    if updated_msg.reply_to_id:
        replied_msg = messenger_crud.get_message_by_id(db, updated_msg.reply_to_id)
        if replied_msg:
            reply_sender_profile = _fetch_user_profile(replied_msg.sender_id)
            reply_is_deleted = replied_msg.deleted_at is not None
            reply_preview = ReplyPreview(
                id=replied_msg.id,
                sender_id=replied_msg.sender_id,
                sender_username=reply_sender_profile["username"],
                sender_avatar=reply_sender_profile["avatar"],
                content="" if reply_is_deleted else replied_msg.content,
                is_deleted=reply_is_deleted,
            )

    response = PrivateMessageResponse(
        id=updated_msg.id,
        conversation_id=updated_msg.conversation_id,
        sender_id=updated_msg.sender_id,
        sender_username=sender_profile["username"] or current_user.username,
        sender_avatar=sender_profile["avatar"],
        sender_avatar_frame=sender_profile["avatar_frame"],
        content=updated_msg.content,
        created_at=updated_msg.created_at,
        is_deleted=False,
        edited_at=updated_msg.edited_at,
        reply_to_id=updated_msg.reply_to_id,
        reply_to=reply_preview,
    )

    # Push WebSocket event to all conversation participants
    conversation_id = updated_msg.conversation_id
    participant_ids = messenger_crud.get_participant_ids(db, conversation_id)
    ws_data = {
        "type": "private_message_edited",
        "data": {
            "id": updated_msg.id,
            "conversation_id": conversation_id,
            "sender_id": updated_msg.sender_id,
            "content": updated_msg.content,
            "edited_at": updated_msg.edited_at.isoformat() if updated_msg.edited_at else None,
        },
    }
    for pid in participant_ids:
        send_to_user(pid, ws_data)

    return response


# ---------------------------------------------------------------------------
# PUT /messenger/conversations/{conversation_id}/read — Mark read
# ---------------------------------------------------------------------------

@messenger_router.put("/conversations/{conversation_id}/read")
def mark_read(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    # Check conversation exists
    conv = messenger_crud.get_conversation_by_id(db, conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Беседа не найдена",
        )

    # Check participation
    if not messenger_crud.is_participant(db, conversation_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы не являетесь участником этой беседы",
        )

    messenger_crud.mark_conversation_read(db, conversation_id, current_user.id)

    # Push WebSocket event for cross-tab sync
    send_to_user(current_user.id, {
        "type": "conversation_read",
        "data": {
            "conversation_id": conversation_id,
        },
    })

    return {"detail": "ok"}


# ---------------------------------------------------------------------------
# GET /messenger/unread-count — Total unread count
# ---------------------------------------------------------------------------

@messenger_router.get("/unread-count", response_model=UnreadCountResponse)
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
    token: str = Depends(OAUTH2_SCHEME),
):
    blocked_ids = _get_blocked_user_ids(token)

    total = messenger_crud.get_unread_count(
        db=db,
        user_id=current_user.id,
        blocked_user_ids=blocked_ids if blocked_ids else None,
    )

    return UnreadCountResponse(total_unread=total)


# ---------------------------------------------------------------------------
# POST /messenger/conversations/{conversation_id}/participants — Add participants
# ---------------------------------------------------------------------------

@messenger_router.post(
    "/conversations/{conversation_id}/participants",
    response_model=AddParticipantsResponse,
)
def add_participants(
    conversation_id: int,
    data: AddParticipantsRequest,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    # Check conversation exists
    conv = messenger_crud.get_conversation_by_id(db, conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Беседа не найдена",
        )

    # Only group conversations
    if conv.type == "direct":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя добавлять участников в личный чат",
        )

    # Check participation
    if not messenger_crud.is_participant(db, conversation_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы не являетесь участником этой беседы",
        )

    result = messenger_crud.add_participants(db, conversation_id, data.user_ids)
    return AddParticipantsResponse(**result)


# ---------------------------------------------------------------------------
# DELETE /messenger/conversations/{conversation_id}/leave — Leave group
# ---------------------------------------------------------------------------

@messenger_router.delete("/conversations/{conversation_id}/leave")
def leave_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    # Check conversation exists
    conv = messenger_crud.get_conversation_by_id(db, conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Беседа не найдена",
        )

    # Only group conversations
    if conv.type == "direct":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя покинуть личный чат",
        )

    # Check participation
    if not messenger_crud.is_participant(db, conversation_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы не являетесь участником этой беседы",
        )

    messenger_crud.remove_participant(db, conversation_id, current_user.id)
    return {"detail": "Вы покинули беседу"}
