"""
WebSocket message handlers for the private messenger.

All functions are sync (matching notification-service's sync SQLAlchemy pattern).
They are called from the async WebSocket endpoint via asyncio.to_thread().
Each function creates its own DB session and closes it in a finally block.
"""

import logging
import re
import time
from typing import Optional

from database import SessionLocal
import messenger_crud
from ws_manager import send_to_user

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiting (shared with messenger_routes — import from there)
# ---------------------------------------------------------------------------

# We import the shared rate-limit dict and constant so WS and REST share state.
from messenger_routes import (
    _last_message_time,
    _MESSAGE_RATE_LIMIT_SECONDS,
    _strip_html,
    _can_message_user,
    _fetch_user_profile,
)


def _error(action: str, detail: str) -> dict:
    """Build a standard error response."""
    return {
        "type": "messenger_error",
        "data": {
            "action": action,
            "detail": detail,
        },
    }


# ---------------------------------------------------------------------------
# messenger_send
# ---------------------------------------------------------------------------

def handle_messenger_send(user_id: int, user_token: str, data: dict) -> dict:
    """Send a message via WebSocket. Returns the response dict to send back."""
    action = "messenger_send"
    db = SessionLocal()
    try:
        conversation_id = data.get("conversation_id")
        content = data.get("content")
        reply_to_id = data.get("reply_to_id")

        if not conversation_id or not content:
            return _error(action, "Не указан conversation_id или content")

        # 1. Rate limit
        now = time.time()
        last_time = _last_message_time.get(user_id, 0.0)
        if now - last_time < _MESSAGE_RATE_LIMIT_SECONDS:
            return _error(action, "Подождите перед отправкой следующего сообщения")

        # 2. Check conversation exists
        conv = messenger_crud.get_conversation_by_id(db, conversation_id)
        if conv is None:
            return _error(action, "Беседа не найдена")

        # 3. Check participation
        if not messenger_crud.is_participant(db, conversation_id, user_id):
            return _error(action, "Вы не являетесь участником этой беседы")

        # 4. For direct conversations, check blocks/privacy
        if conv.type == "direct":
            participant_ids = messenger_crud.get_participant_ids(db, conversation_id)
            other_ids = [pid for pid in participant_ids if pid != user_id]
            if other_ids:
                error = _can_message_user(user_token, user_id, other_ids[0])
                if error:
                    return _error(action, error)

        # 5. Sanitize content
        content = _strip_html(content)

        # 5.1. Validate reply_to_id
        reply_preview_data = None
        if reply_to_id is not None:
            replied_msg = messenger_crud.get_message_by_id(db, reply_to_id)
            if replied_msg is None:
                return _error(action, "Цитируемое сообщение не найдено")
            if replied_msg.conversation_id != conversation_id:
                return _error(action, "Цитируемое сообщение не принадлежит этой беседе")
            # Build reply preview
            reply_sender_profile = _fetch_user_profile(replied_msg.sender_id)
            reply_is_deleted = replied_msg.deleted_at is not None
            reply_preview_data = {
                "id": replied_msg.id,
                "sender_id": replied_msg.sender_id,
                "sender_username": reply_sender_profile["username"],
                "sender_avatar": reply_sender_profile["avatar"],
                "content": "" if reply_is_deleted else replied_msg.content,
                "is_deleted": reply_is_deleted,
            }

        # 6. Insert message
        msg = messenger_crud.create_message(
            db=db,
            conversation_id=conversation_id,
            sender_id=user_id,
            content=content,
            reply_to_id=reply_to_id,
        )

        # 7. Update rate limit
        _last_message_time[user_id] = time.time()

        # 8. Build response
        sender_profile = _fetch_user_profile(user_id)

        msg_data = {
            "id": msg.id,
            "conversation_id": msg.conversation_id,
            "sender_id": msg.sender_id,
            "sender_username": sender_profile["username"],
            "sender_avatar": sender_profile["avatar"],
            "sender_avatar_frame": sender_profile["avatar_frame"],
            "content": msg.content,
            "created_at": msg.created_at.isoformat(),
            "is_deleted": False,
            "edited_at": None,
            "reply_to_id": msg.reply_to_id,
            "reply_to": reply_preview_data,
        }

        # 9. Push to other participants
        participant_ids = messenger_crud.get_participant_ids(db, conversation_id)
        ws_push = {
            "type": "private_message",
            "data": msg_data,
        }
        for pid in participant_ids:
            if pid != user_id:
                send_to_user(pid, ws_push)

        return {"type": "messenger_send_ok", "data": msg_data}

    except Exception as e:
        logger.exception("handle_messenger_send error for user %d: %s", user_id, e)
        return _error(action, "Внутренняя ошибка при отправке сообщения")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# messenger_edit
# ---------------------------------------------------------------------------

def handle_messenger_edit(user_id: int, data: dict) -> dict:
    """Edit a message. Returns response dict."""
    action = "messenger_edit"
    db = SessionLocal()
    try:
        message_id = data.get("message_id")
        content = data.get("content")

        if not message_id or not content:
            return _error(action, "Не указан message_id или content")

        # Check message exists
        msg = messenger_crud.get_message_by_id(db, message_id)
        if msg is None:
            return _error(action, "Сообщение не найдено")

        # Only sender can edit
        if msg.sender_id != user_id:
            return _error(action, "Вы можете редактировать только свои сообщения")

        # Cannot edit deleted messages
        if msg.deleted_at is not None:
            return _error(action, "Нельзя редактировать удалённое сообщение")

        # Sanitize content
        content = _strip_html(content)

        # Update message
        updated_msg = messenger_crud.edit_message(db, message_id, content)

        # Build response
        sender_profile = _fetch_user_profile(user_id)

        # Build reply preview if message is a reply
        reply_preview_data = None
        if updated_msg.reply_to_id:
            replied_msg = messenger_crud.get_message_by_id(db, updated_msg.reply_to_id)
            if replied_msg:
                reply_sender_profile = _fetch_user_profile(replied_msg.sender_id)
                reply_is_deleted = replied_msg.deleted_at is not None
                reply_preview_data = {
                    "id": replied_msg.id,
                    "sender_id": replied_msg.sender_id,
                    "sender_username": reply_sender_profile["username"],
                    "sender_avatar": reply_sender_profile["avatar"],
                    "content": "" if reply_is_deleted else replied_msg.content,
                    "is_deleted": reply_is_deleted,
                }

        msg_data = {
            "id": updated_msg.id,
            "conversation_id": updated_msg.conversation_id,
            "sender_id": updated_msg.sender_id,
            "sender_username": sender_profile["username"],
            "sender_avatar": sender_profile["avatar"],
            "sender_avatar_frame": sender_profile["avatar_frame"],
            "content": updated_msg.content,
            "created_at": updated_msg.created_at.isoformat(),
            "is_deleted": False,
            "edited_at": updated_msg.edited_at.isoformat() if updated_msg.edited_at else None,
            "reply_to_id": updated_msg.reply_to_id,
            "reply_to": reply_preview_data,
        }

        # Push to all conversation participants
        conversation_id = updated_msg.conversation_id
        participant_ids = messenger_crud.get_participant_ids(db, conversation_id)
        ws_push = {
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
            if pid != user_id:
                send_to_user(pid, ws_push)

        return {"type": "messenger_edit_ok", "data": msg_data}

    except Exception as e:
        logger.exception("handle_messenger_edit error for user %d: %s", user_id, e)
        return _error(action, "Внутренняя ошибка при редактировании сообщения")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# messenger_delete
# ---------------------------------------------------------------------------

def handle_messenger_delete(user_id: int, data: dict) -> dict:
    """Delete a message. Returns response dict."""
    action = "messenger_delete"
    db = SessionLocal()
    try:
        message_id = data.get("message_id")

        if not message_id:
            return _error(action, "Не указан message_id")

        # Check message exists
        msg = messenger_crud.get_message_by_id(db, message_id)
        if msg is None:
            return _error(action, "Сообщение не найдено")

        # Check sender
        if msg.sender_id != user_id:
            return _error(action, "Вы можете удалять только свои сообщения")

        # Soft delete
        conversation_id = msg.conversation_id
        deleted_msg = messenger_crud.soft_delete_message(db, message_id, user_id)
        if deleted_msg is None:
            return _error(action, "Сообщение не найдено")

        # Push to all conversation participants
        participant_ids = messenger_crud.get_participant_ids(db, conversation_id)
        ws_push = {
            "type": "private_message_deleted",
            "data": {
                "message_id": message_id,
                "conversation_id": conversation_id,
            },
        }
        for pid in participant_ids:
            send_to_user(pid, ws_push)

        return {
            "type": "messenger_delete_ok",
            "data": {
                "message_id": message_id,
                "conversation_id": conversation_id,
            },
        }

    except Exception as e:
        logger.exception("handle_messenger_delete error for user %d: %s", user_id, e)
        return _error(action, "Внутренняя ошибка при удалении сообщения")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# messenger_mark_read
# ---------------------------------------------------------------------------

def handle_messenger_mark_read(user_id: int, data: dict) -> dict:
    """Mark conversation read. Returns response dict."""
    action = "messenger_mark_read"
    db = SessionLocal()
    try:
        conversation_id = data.get("conversation_id")

        if not conversation_id:
            return _error(action, "Не указан conversation_id")

        # Check conversation exists
        conv = messenger_crud.get_conversation_by_id(db, conversation_id)
        if conv is None:
            return _error(action, "Беседа не найдена")

        # Check participation
        if not messenger_crud.is_participant(db, conversation_id, user_id):
            return _error(action, "Вы не являетесь участником этой беседы")

        messenger_crud.mark_conversation_read(db, conversation_id, user_id)

        # Push cross-tab sync event to the same user
        send_to_user(user_id, {
            "type": "conversation_read",
            "data": {
                "conversation_id": conversation_id,
            },
        })

        return {
            "type": "messenger_mark_read_ok",
            "data": {
                "conversation_id": conversation_id,
            },
        }

    except Exception as e:
        logger.exception("handle_messenger_mark_read error for user %d: %s", user_id, e)
        return _error(action, "Внутренняя ошибка при отметке прочтения")
    finally:
        db.close()
