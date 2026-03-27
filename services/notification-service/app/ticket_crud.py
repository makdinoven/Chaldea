"""
Ticket CRUD operations for notification-service.
All functions are sync (SQLAlchemy sync pattern matching the service).
"""

import logging
from datetime import datetime
from typing import Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from ticket_models import SupportTicket, SupportTicketMessage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------

def create_ticket(
    db: Session,
    user_id: int,
    subject: str,
    category: str,
    content: str,
    attachment_url: Optional[str] = None,
    is_admin: bool = False,
) -> SupportTicket:
    """Create a new support ticket and its first message. Returns the ticket."""
    ticket = SupportTicket(
        user_id=user_id,
        subject=subject,
        category=category,
        status="open",
    )
    db.add(ticket)
    db.flush()  # get ticket.id before adding the first message

    msg = SupportTicketMessage(
        ticket_id=ticket.id,
        sender_id=user_id,
        content=content,
        attachment_url=attachment_url,
        is_admin=is_admin,
    )
    db.add(msg)
    db.commit()
    db.refresh(ticket)
    return ticket


def create_ticket_message(
    db: Session,
    ticket_id: int,
    sender_id: int,
    content: str,
    is_admin: bool = False,
    attachment_url: Optional[str] = None,
) -> SupportTicketMessage:
    """Insert a new message into a ticket. Returns the message."""
    msg = SupportTicketMessage(
        ticket_id=ticket_id,
        sender_id=sender_id,
        content=content,
        attachment_url=attachment_url,
        is_admin=is_admin,
    )
    db.add(msg)

    # Update ticket's updated_at
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if ticket:
        ticket.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(msg)
    return msg


def get_ticket_by_id(
    db: Session,
    ticket_id: int,
) -> Optional[SupportTicket]:
    """Get a ticket by ID."""
    return (
        db.query(SupportTicket)
        .filter(SupportTicket.id == ticket_id)
        .first()
    )


def get_tickets_by_user(
    db: Session,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
) -> dict:
    """Return paginated tickets for a specific user, ordered by updated_at DESC."""
    base_filter = [SupportTicket.user_id == user_id]
    if status_filter:
        base_filter.append(SupportTicket.status == status_filter)

    total = (
        db.query(func.count(SupportTicket.id))
        .filter(*base_filter)
        .scalar()
    )

    tickets = (
        db.query(SupportTicket)
        .filter(*base_filter)
        .order_by(desc(SupportTicket.updated_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": tickets,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_all_tickets(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
) -> dict:
    """Return paginated list of all tickets (admin view), ordered by updated_at DESC."""
    base_filter = []
    if status_filter:
        base_filter.append(SupportTicket.status == status_filter)
    if category_filter:
        base_filter.append(SupportTicket.category == category_filter)

    total = (
        db.query(func.count(SupportTicket.id))
        .filter(*base_filter)
        .scalar()
    )

    tickets = (
        db.query(SupportTicket)
        .filter(*base_filter)
        .order_by(desc(SupportTicket.updated_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": tickets,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_ticket_messages(
    db: Session,
    ticket_id: int,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Return paginated messages for a ticket, ordered by created_at ASC (oldest first)."""
    base_filter = [SupportTicketMessage.ticket_id == ticket_id]

    total = (
        db.query(func.count(SupportTicketMessage.id))
        .filter(*base_filter)
        .scalar()
    )

    items = (
        db.query(SupportTicketMessage)
        .filter(*base_filter)
        .order_by(SupportTicketMessage.created_at.asc())
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


def update_ticket_status(
    db: Session,
    ticket_id: int,
    new_status: str,
    closed_by: Optional[int] = None,
) -> Optional[SupportTicket]:
    """Update ticket status. Returns the updated ticket or None if not found."""
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if ticket is None:
        return None

    ticket.status = new_status
    ticket.updated_at = datetime.utcnow()

    if new_status == "closed":
        ticket.closed_at = datetime.utcnow()
        ticket.closed_by = closed_by
    else:
        # If reopening from closed, clear closed fields
        ticket.closed_at = None
        ticket.closed_by = None

    db.commit()
    db.refresh(ticket)
    return ticket


def get_open_ticket_count(db: Session) -> int:
    """Count all tickets that are not closed (for admin badge)."""
    return (
        db.query(func.count(SupportTicket.id))
        .filter(SupportTicket.status != "closed")
        .scalar()
    )


def get_last_message(
    db: Session,
    ticket_id: int,
) -> Optional[SupportTicketMessage]:
    """Get the most recent message for a ticket."""
    return (
        db.query(SupportTicketMessage)
        .filter(SupportTicketMessage.ticket_id == ticket_id)
        .order_by(desc(SupportTicketMessage.created_at))
        .first()
    )


def get_message_count(
    db: Session,
    ticket_id: int,
) -> int:
    """Count total messages in a ticket."""
    return (
        db.query(func.count(SupportTicketMessage.id))
        .filter(SupportTicketMessage.ticket_id == ticket_id)
        .scalar()
    )
