from sqlalchemy import Column, Integer, String
from database import Base

# Определяем модель для хранения характеристик персонажа
class CharacterAttributes(Base):
    __tablename__ = "character_attributes"

    id = Column(Integer, primary_key=True, index=True)  # Первичный ключ
    character_id = Column(Integer, unique=True, index=True)  # ID персонажа
    health = Column(Integer, default=100)  # Здоровье
    mana = Column(Integer, default=100)  # Мана
    energy = Column(Integer, default=100)  # Энергия
    strength = Column(Integer, default=10)  # Сила
    agility = Column(Integer, default=10)  # Ловкость
    intelligence = Column(Integer, default=10)  # Интеллект
    luck = Column(Integer, default=10)  # Удача
    charisma = Column(Integer, default=10)  # Харизма
