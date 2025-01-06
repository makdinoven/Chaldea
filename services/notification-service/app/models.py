from sqlalchemy import Column, Integer, String, Enum, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    message = Column(Text, nullable=False)
    status = Column(Enum("unread", "read", name="notification_status"), default="unread")
    created_at = Column(DateTime, default=datetime.utcnow)


