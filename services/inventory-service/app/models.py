from sqlalchemy import Column, Integer, String
from database import Base

# Определяем модель для хранения инвентаря персонажа
class CharacterInventory(Base):
    __tablename__ = "character_inventory"

    id = Column(Integer, primary_key=True, index=True)  # Первичный ключ
    character_id = Column(Integer, unique=True, index=True)  # ID персонажа
    item_1 = Column(String(100), default="Basic Sword")  # Первый предмет
    item_2 = Column(String(100), default="Basic Shield")  # Второй предмет
    item_3 = Column(String(100), default="Health Potion")  # Третий предмет
