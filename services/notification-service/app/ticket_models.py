"""
SQLAlchemy models for the support ticket feature.
Tables: support_tickets, support_ticket_messages.
"""

from sqlalchemy import (
    Column, Integer, String, Enum, Text, Boolean, DateTime, ForeignKey, Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    subject = Column(String(255), nullable=False)
    category = Column(
        Enum("bug", "question", "suggestion", "complaint", "other", name="ticket_category"),
        nullable=False,
        server_default="other",
    )
    status = Column(
        Enum("open", "in_progress", "awaiting_reply", "closed", name="ticket_status"),
        nullable=False,
        server_default="open",
    )
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    closed_at = Column(DateTime, nullable=True)
    closed_by = Column(Integer, nullable=True)

    messages = relationship(
        "SupportTicketMessage",
        back_populates="ticket",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_tickets_user_id", "user_id"),
        Index("ix_tickets_status", "status"),
        Index("ix_tickets_created_at", "created_at"),
    )


class SupportTicketMessage(Base):
    __tablename__ = "support_ticket_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(
        Integer,
        ForeignKey("support_tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_id = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    attachment_url = Column(String(512), nullable=True)
    is_admin = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    ticket = relationship("SupportTicket", back_populates="messages")

    __table_args__ = (
        Index("ix_ticket_messages_ticket_created", "ticket_id", "created_at"),
    )
