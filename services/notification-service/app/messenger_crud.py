"""
Messenger CRUD operations for notification-service.
All functions are sync (SQLAlchemy sync pattern matching the service).
"""

import logging
from datetime import datetime
from typing import Optional, List, Set

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, func, and_

from messenger_models import Conversation, ConversationParticipant, PrivateMessage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

def create_conversation(
    db: Session,
    conversation_type: str,
    created_by: int,
    participant_ids: List[int],
    title: Optional[str] = None,
) -> Conversation:
    """Create a new conversation and add all participants (including creator)."""
    conv = Conversation(
        type=conversation_type,
        title=title,
        created_by=created_by,
    )
    db.add(conv)
    db.flush()  # get conv.id before adding participants

    # Ensure creator is included in participant list
    all_user_ids = set(participant_ids)
    all_user_ids.add(created_by)

    for uid in all_user_ids:
        participant = ConversationParticipant(
            conversation_id=conv.id,
            user_id=uid,
        )
        db.add(participant)

    db.commit()
    db.refresh(conv)
    return conv


def find_existing_direct(
    db: Session,
    user_id_1: int,
    user_id_2: int,
) -> Optional[Conversation]:
    """Find an existing direct conversation between two users. Returns None if not found."""
    # A direct conversation has exactly these two participants
    conv_ids_1 = (
        db.query(ConversationParticipant.conversation_id)
        .filter(ConversationParticipant.user_id == user_id_1)
        .subquery()
    )
    conv_ids_2 = (
        db.query(ConversationParticipant.conversation_id)
        .filter(ConversationParticipant.user_id == user_id_2)
        .subquery()
    )

    conv = (
        db.query(Conversation)
        .filter(Conversation.type == "direct")
        .filter(Conversation.id.in_(db.query(conv_ids_1.c.conversation_id)))
        .filter(Conversation.id.in_(db.query(conv_ids_2.c.conversation_id)))
        .first()
    )
    return conv


def get_conversation_by_id(
    db: Session,
    conversation_id: int,
) -> Optional[Conversation]:
    """Get a conversation by ID with participants eagerly loaded."""
    return (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id)
        .first()
    )


def is_participant(
    db: Session,
    conversation_id: int,
    user_id: int,
) -> bool:
    """Check whether user_id is a participant of the given conversation."""
    return (
        db.query(ConversationParticipant)
        .filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == user_id,
        )
        .first()
    ) is not None


def get_participant_ids(
    db: Session,
    conversation_id: int,
) -> List[int]:
    """Return all participant user_ids for a conversation."""
    rows = (
        db.query(ConversationParticipant.user_id)
        .filter(ConversationParticipant.conversation_id == conversation_id)
        .all()
    )
    return [r[0] for r in rows]


def add_participants(
    db: Session,
    conversation_id: int,
    user_ids: List[int],
) -> dict:
    """Add participants to an existing conversation. Returns {'added': [...], 'skipped': [...]}."""
    existing = set(get_participant_ids(db, conversation_id))
    added = []
    skipped = []

    for uid in user_ids:
        if uid in existing:
            skipped.append(uid)
            continue
        p = ConversationParticipant(
            conversation_id=conversation_id,
            user_id=uid,
        )
        db.add(p)
        added.append(uid)

    if added:
        db.commit()

    return {"added": added, "skipped": skipped}


def remove_participant(
    db: Session,
    conversation_id: int,
    user_id: int,
) -> bool:
    """Remove a participant from a conversation. Returns True if removed, False if not found."""
    p = (
        db.query(ConversationParticipant)
        .filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == user_id,
        )
        .first()
    )
    if p is None:
        return False
    db.delete(p)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def create_message(
    db: Session,
    conversation_id: int,
    sender_id: int,
    content: str,
    reply_to_id: Optional[int] = None,
) -> PrivateMessage:
    """Insert a new private message and return it."""
    msg = PrivateMessage(
        conversation_id=conversation_id,
        sender_id=sender_id,
        content=content,
        reply_to_id=reply_to_id,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def soft_delete_message(
    db: Session,
    message_id: int,
    sender_id: int,
) -> Optional[PrivateMessage]:
    """Soft-delete a message (set deleted_at). Only the sender may delete.
    Returns the updated message, or None if not found / not sender."""
    msg = db.query(PrivateMessage).filter(PrivateMessage.id == message_id).first()
    if msg is None:
        return None
    if msg.sender_id != sender_id:
        return None  # caller should distinguish 404 vs 403 by checking existence separately
    msg.deleted_at = datetime.utcnow()
    db.commit()
    db.refresh(msg)
    return msg


def get_message_by_id(
    db: Session,
    message_id: int,
) -> Optional[PrivateMessage]:
    """Get a single message by ID."""
    return db.query(PrivateMessage).filter(PrivateMessage.id == message_id).first()


def edit_message(
    db: Session,
    message_id: int,
    new_content: str,
) -> PrivateMessage:
    """Update message content and set edited_at timestamp. Returns updated message."""
    msg = db.query(PrivateMessage).filter(PrivateMessage.id == message_id).first()
    if msg is None:
        return None
    msg.content = new_content
    msg.edited_at = datetime.utcnow()
    db.commit()
    db.refresh(msg)
    return msg


def get_reply_preview(
    db: Session,
    message_id: int,
) -> Optional[dict]:
    """Return a dict with reply preview data for the given message ID.
    Returns None if message not found."""
    msg = db.query(PrivateMessage).filter(PrivateMessage.id == message_id).first()
    if msg is None:
        return None
    return {
        "id": msg.id,
        "sender_id": msg.sender_id,
        "content": msg.content,
        "is_deleted": msg.deleted_at is not None,
    }


def get_messages(
    db: Session,
    conversation_id: int,
    page: int = 1,
    page_size: int = 50,
    blocked_user_ids: Optional[Set[int]] = None,
):
    """Return paginated messages for a conversation, newest first.
    Messages from blocked users are excluded. Soft-deleted messages are included
    but with empty content (handled at the schema/route layer)."""
    base_filter = [PrivateMessage.conversation_id == conversation_id]

    if blocked_user_ids:
        base_filter.append(~PrivateMessage.sender_id.in_(blocked_user_ids))

    total = (
        db.query(func.count(PrivateMessage.id))
        .filter(*base_filter)
        .scalar()
    )

    items = (
        db.query(PrivateMessage)
        .options(joinedload(PrivateMessage.reply_to))
        .filter(*base_filter)
        .order_by(desc(PrivateMessage.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# Read tracking / unread counts
# ---------------------------------------------------------------------------

def mark_conversation_read(
    db: Session,
    conversation_id: int,
    user_id: int,
) -> bool:
    """Set last_read_at = now for a participant. Returns True if updated."""
    p = (
        db.query(ConversationParticipant)
        .filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == user_id,
        )
        .first()
    )
    if p is None:
        return False
    p.last_read_at = datetime.utcnow()
    db.commit()
    return True


def get_unread_count_for_conversation(
    db: Session,
    conversation_id: int,
    user_id: int,
    blocked_user_ids: Optional[Set[int]] = None,
) -> int:
    """Count unread messages in a single conversation for a user."""
    p = (
        db.query(ConversationParticipant)
        .filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == user_id,
        )
        .first()
    )
    if p is None:
        return 0

    filters = [
        PrivateMessage.conversation_id == conversation_id,
        PrivateMessage.deleted_at.is_(None),
        PrivateMessage.sender_id != user_id,
    ]

    if p.last_read_at is not None:
        filters.append(PrivateMessage.created_at > p.last_read_at)

    if blocked_user_ids:
        filters.append(~PrivateMessage.sender_id.in_(blocked_user_ids))

    return (
        db.query(func.count(PrivateMessage.id))
        .filter(*filters)
        .scalar()
    )


def get_unread_count(
    db: Session,
    user_id: int,
    blocked_user_ids: Optional[Set[int]] = None,
) -> int:
    """Total unread message count across all conversations for a user."""
    participations = (
        db.query(ConversationParticipant)
        .filter(ConversationParticipant.user_id == user_id)
        .all()
    )

    total = 0
    for p in participations:
        filters = [
            PrivateMessage.conversation_id == p.conversation_id,
            PrivateMessage.deleted_at.is_(None),
            PrivateMessage.sender_id != user_id,
        ]
        if p.last_read_at is not None:
            filters.append(PrivateMessage.created_at > p.last_read_at)
        if blocked_user_ids:
            filters.append(~PrivateMessage.sender_id.in_(blocked_user_ids))

        count = (
            db.query(func.count(PrivateMessage.id))
            .filter(*filters)
            .scalar()
        )
        total += count

    return total


# ---------------------------------------------------------------------------
# Conversation listing (with last message + unread count)
# ---------------------------------------------------------------------------

def list_conversations(
    db: Session,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    blocked_user_ids: Optional[Set[int]] = None,
):
    """List conversations for a user, sorted by last message time (most recent first).
    Each item includes participants, last_message preview, and unread_count.

    Returns dict compatible with PaginatedConversations schema.
    """
    # Get conversation IDs where user is a participant
    conv_ids_query = (
        db.query(ConversationParticipant.conversation_id)
        .filter(ConversationParticipant.user_id == user_id)
    )
    conv_ids = [r[0] for r in conv_ids_query.all()]

    if not conv_ids:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    total = len(conv_ids)

    # Subquery: last message time per conversation (for ordering)
    last_msg_time = (
        db.query(
            PrivateMessage.conversation_id,
            func.max(PrivateMessage.created_at).label("last_time"),
        )
        .filter(PrivateMessage.conversation_id.in_(conv_ids))
        .group_by(PrivateMessage.conversation_id)
        .subquery()
    )

    # Get conversations ordered by last message time (conversations with no messages
    # use created_at as fallback via COALESCE)
    conversations = (
        db.query(Conversation)
        .outerjoin(last_msg_time, Conversation.id == last_msg_time.c.conversation_id)
        .filter(Conversation.id.in_(conv_ids))
        .order_by(desc(func.coalesce(last_msg_time.c.last_time, Conversation.created_at)))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Build result items
    items = []
    for conv in conversations:
        # Participants (exclude current user for display in direct chats)
        participants = (
            db.query(ConversationParticipant)
            .filter(
                ConversationParticipant.conversation_id == conv.id,
                ConversationParticipant.user_id != user_id,
            )
            .all()
        )

        # Last message (non-blocked, most recent)
        last_msg_filters = [PrivateMessage.conversation_id == conv.id]
        if blocked_user_ids:
            last_msg_filters.append(~PrivateMessage.sender_id.in_(blocked_user_ids))

        last_msg = (
            db.query(PrivateMessage)
            .filter(*last_msg_filters)
            .order_by(desc(PrivateMessage.created_at))
            .first()
        )

        last_message_preview = None
        if last_msg is not None:
            content = "" if last_msg.deleted_at is not None else last_msg.content
            last_message_preview = {
                "id": last_msg.id,
                "sender_id": last_msg.sender_id,
                "sender_username": None,  # populated by route layer
                "content": content,
                "created_at": last_msg.created_at,
                "edited_at": last_msg.edited_at,
            }

        unread = get_unread_count_for_conversation(
            db, conv.id, user_id, blocked_user_ids
        )

        items.append({
            "id": conv.id,
            "type": conv.type,
            "title": conv.title,
            "created_at": conv.created_at,
            "participants": [
                {
                    "user_id": p.user_id,
                    "username": None,  # populated by route layer
                    "avatar": None,
                    "avatar_frame": None,
                }
                for p in participants
            ],
            "last_message": last_message_preview,
            "unread_count": unread,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
