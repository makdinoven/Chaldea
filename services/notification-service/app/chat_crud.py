"""
Chat CRUD operations for notification-service.
All functions are sync (SQLAlchemy sync pattern matching the service).
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc

from chat_models import ChatMessage, ChatBan

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def create_message(
    db: Session,
    user_id: int,
    username: str,
    avatar: Optional[str],
    avatar_frame: Optional[str],
    message_data,
) -> ChatMessage:
    """Insert a new chat message and return it with reply_to loaded."""
    msg = ChatMessage(
        channel=message_data.channel.value,
        user_id=user_id,
        username=username,
        avatar=avatar,
        avatar_frame=avatar_frame,
        content=message_data.content,
        reply_to_id=message_data.reply_to_id,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # Eagerly load reply_to relationship if present
    if msg.reply_to_id:
        db.refresh(msg, attribute_names=["reply_to"])

    return msg


def get_messages(
    db: Session,
    channel: str,
    page: int = 1,
    page_size: int = 50,
):
    """Return paginated messages for a channel, newest first, with reply_to nested."""
    query = (
        db.query(ChatMessage)
        .options(joinedload(ChatMessage.reply_to))
        .filter(ChatMessage.channel == channel)
        .order_by(desc(ChatMessage.created_at))
    )

    total = (
        db.query(ChatMessage)
        .filter(ChatMessage.channel == channel)
        .count()
    )

    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def delete_message(db: Session, message_id: int) -> Optional[ChatMessage]:
    """Delete a message by ID and return the deleted object (or None if not found)."""
    msg = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
    if msg is None:
        return None

    # Keep a reference to channel before deleting
    channel = msg.channel
    msg_id = msg.id

    db.delete(msg)
    db.commit()

    # Return a lightweight object with the info needed for broadcast
    class _Deleted:
        pass

    deleted = _Deleted()
    deleted.id = msg_id
    deleted.channel = channel
    return deleted


def cleanup_old_messages(db: Session, channel: str, limit: int = 500) -> int:
    """Delete the oldest messages beyond `limit` for a channel. Returns count deleted."""
    total = (
        db.query(ChatMessage)
        .filter(ChatMessage.channel == channel)
        .count()
    )

    if total <= limit:
        return 0

    to_delete = total - limit

    # Get IDs of the oldest messages to delete
    oldest_ids = (
        db.query(ChatMessage.id)
        .filter(ChatMessage.channel == channel)
        .order_by(ChatMessage.created_at.asc())
        .limit(to_delete)
        .all()
    )

    if oldest_ids:
        ids = [row[0] for row in oldest_ids]
        db.query(ChatMessage).filter(ChatMessage.id.in_(ids)).delete(
            synchronize_session=False
        )
        db.commit()

    logger.info(
        "Chat cleanup: deleted %d old messages from channel '%s'",
        len(oldest_ids),
        channel,
    )
    return len(oldest_ids)


# ---------------------------------------------------------------------------
# Bans
# ---------------------------------------------------------------------------

def create_ban(
    db: Session,
    user_id: int,
    banned_by: int,
    reason: Optional[str] = None,
    expires_at: Optional[datetime] = None,
) -> Optional[ChatBan]:
    """Create a chat ban. Returns None if user is already banned (unique constraint)."""
    existing = db.query(ChatBan).filter(ChatBan.user_id == user_id).first()
    if existing:
        return None  # already banned

    ban = ChatBan(
        user_id=user_id,
        banned_by=banned_by,
        reason=reason,
        expires_at=expires_at,
    )
    db.add(ban)
    db.commit()
    db.refresh(ban)
    return ban


def remove_ban(db: Session, user_id: int) -> bool:
    """Remove a chat ban. Returns True if a ban was deleted, False if not found."""
    ban = db.query(ChatBan).filter(ChatBan.user_id == user_id).first()
    if ban is None:
        return False
    db.delete(ban)
    db.commit()
    return True


def get_ban(db: Session, user_id: int) -> Optional[ChatBan]:
    """Return the active ban for a user, or None. Expired bans are treated as no ban."""
    ban = db.query(ChatBan).filter(ChatBan.user_id == user_id).first()
    if ban is None:
        return None

    # Check expiration
    if ban.expires_at is not None and ban.expires_at < datetime.utcnow():
        # Ban has expired — clean it up and return None
        db.delete(ban)
        db.commit()
        return None

    return ban


def is_user_banned(db: Session, user_id: int) -> bool:
    """Convenience boolean check for ban status."""
    return get_ban(db, user_id) is not None
