from sqlalchemy import Column, Integer, String, Text, Enum, TIMESTAMP, ForeignKey, func
from sqlalchemy.orm import relationship
from database import Base

class CharacterRequest(Base):
    __tablename__ = "character_requests"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(20), index=True)
    id_subrace = Column(Integer)
    biography = Column(Text)
    personality = Column(Text)
    id_class = Column(Integer)
    status = Column(Enum('pending', 'approved', 'rejected'), default='pending')
    created_at = Column(TIMESTAMP, server_default=func.now())
    user_id = Column(Integer, nullable=True)

class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    id_subrace = Column(Integer, nullable=False)
    biography = Column(Text, nullable=True)
    personality = Column(Text, nullable=True)
    id_item_inventory = Column(Integer, nullable=True)  # Поле для инвентаря
    id_skill_inventory = Column(Integer, nullable=True)  # Поле для навыков
    id_class = Column(Integer, nullable=False)
    id_attributes = Column(Integer, nullable=True)  # Поле для атрибутов
    currency_balance = Column(Integer, default=0)
    request_id = Column(Integer, ForeignKey("character_requests.id"), nullable=False)  # Ссылка на заявку
    user_id = Column(Integer, nullable=True)  # Добавляем поле user_id
