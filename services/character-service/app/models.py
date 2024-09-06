from sqlalchemy import Column, Integer, String, Text, Enum, TIMESTAMP
from sqlalchemy.orm import relationship
from .database import Base

class CharacterRequest(Base):
    __tablename__ = "character_requests"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    id_subrace = Column(Integer)
    biography = Column(Text)
    personality = Column(Text)
    id_class = Column(Integer)
    status = Column(Enum('pending', 'approved', 'rejected'), default='pending')
    created_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')

class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    id_subrace = Column(Integer)
    biography = Column(Text)
    personality = Column(Text)
    id_item_inventory = Column(Integer)
    id_skill_inventory = Column(Integer)
    id_class = Column(Integer)
    id_attributes = Column(Integer)
    currency_balance = Column(Integer, default=0)
