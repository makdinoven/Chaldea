"""
SQLAlchemy models for the private messenger feature.
Tables: conversations, conversation_participants, private_messages.
"""

from sqlalchemy import (
    Column, Integer, String, Enum, Text, DateTime, ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(Enum("direct", "group", name="conversation_type"), nullable=False)
    title = Column(String(100), nullable=True)
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    participants = relationship(
        "ConversationParticipant",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    messages = relationship(
        "PrivateMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(Integer, nullable=False)
    joined_at = Column(DateTime, nullable=False, server_default=func.now())
    last_read_at = Column(DateTime, nullable=True)

    conversation = relationship("Conversation", back_populates="participants")

    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_conv_participant"),
        Index("ix_conv_participants_user", "user_id"),
    )


class PrivateMessage(Base):
    __tablename__ = "private_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_id = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    deleted_at = Column(DateTime, nullable=True)
    edited_at = Column(DateTime, nullable=True)
    reply_to_id = Column(
        Integer,
        ForeignKey("private_messages.id", ondelete="SET NULL"),
        nullable=True,
    )

    conversation = relationship("Conversation", back_populates="messages")
    reply_to = relationship("PrivateMessage", remote_side=[id], uselist=False)

    __table_args__ = (
        Index("ix_pm_conv_created", "conversation_id", "created_at"),
        Index("ix_pm_sender", "sender_id"),
        Index("ix_pm_reply_to", "reply_to_id"),
    )
