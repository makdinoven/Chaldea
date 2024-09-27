from sqlalchemy import Column, Integer, String, Enum, Boolean, DECIMAL, Text, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

# Определяем модель для хранения инвентаря персонажа
class Items(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True)
    item_type = Column(Enum('axe', 'armor', 'flask'), nullable=True)
    is_stackable = Column(Boolean, nullable=False, default=False)
    max_stack_size = Column(Integer, default=1)
    weight = Column(DECIMAL(5, 2), nullable=False)
    description = Column(Text)
    is_sellable = Column(Boolean, default=False)
    price = Column(Integer, nullable=True)
    is_rare = Column(Boolean, nullable=False, default=False)
    image = Column(String(255), nullable=True)

    # Обратная связь с CharacterInventory и EquipmentSlot
    inventories = relationship("CharacterInventory", back_populates="item")
    equipment_slots = relationship("EquipmentSlot", back_populates="item")

# Определяем модель для хранения инвентаря персонажа
class CharacterInventory(Base):
    __tablename__ = "character_inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False)
    item_id = Column(Integer, ForeignKey('items.id'), nullable=False)
    slot_type = Column(Enum('bag', 'armor_slot', 'weapon_slot', 'accessory_slot'), nullable=False)
    quantity = Column(Integer, default=1)

    item = relationship("Items", back_populates="inventories")

# Таблица слотов экипировки
class EquipmentSlot(Base):
    __tablename__ = 'equipment_slots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False)
    slot_type = Column(Enum('head', 'chest', 'legs', 'feet', 'weapon', 'accessory'), nullable=False)
    item_id = Column(Integer, ForeignKey('items.id'), nullable=True)

    item = relationship("Items", back_populates="equipment_slots")
