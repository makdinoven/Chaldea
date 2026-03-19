from sqlalchemy import Column, Integer, String, Enum, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel = Column(Enum("general", "trade", "help", name="chat_channel"), nullable=False)
    user_id = Column(Integer, nullable=False)
    username = Column(String(100), nullable=False)
    avatar = Column(String(500), nullable=True)
    avatar_frame = Column(String(50), nullable=True)
    content = Column(Text, nullable=False)
    reply_to_id = Column(Integer, ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    reply_to = relationship("ChatMessage", remote_side=[id], uselist=False)


class ChatBan(Base):
    __tablename__ = "chat_bans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, unique=True)
    banned_by = Column(Integer, nullable=False)
    reason = Column(String(500), nullable=True)
    banned_at = Column(DateTime, nullable=False, server_default=func.now())
    expires_at = Column(DateTime, nullable=True)
