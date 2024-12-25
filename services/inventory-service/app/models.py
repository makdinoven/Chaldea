from sqlalchemy import Column, Integer, String, Enum, Boolean, DECIMAL, Text, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

# Определяем модель для хранения инвентаря персонажа
class Items(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True)
    image = Column(String(255), nullable=True)
    item_level = Column(Integer, nullable=False,default=0)
    item_type = Column(Enum(
        'head', 'body', 'cloak', 'belt', 'ring', 'necklace', 'main_weapon',
        'consumable','additional_weapons', 'resource', 'scroll', 'misc'
    ), nullable=False)
    item_rarity = Column(Enum(
        'common', 'rare', 'epic', 'legendary', 'mythical', 'divine', 'demonic'
    ), nullable=False)
    price = Column(Integer, nullable=True)
    max_stack_size = Column(Integer, default=1)
    is_unique = Column(Boolean, nullable=False, default=False)
    description = Column(Text)
    weight = Column(DECIMAL(5, 2), nullable=True, default=0)

    # Модификаторы характеристик
    strength_modifier = Column(Integer, default=0)
    agility_modifier = Column(Integer, default=0)
    intelligence_modifier = Column(Integer, default=0)
    endurance_modifier = Column(Integer, default=0)
    health_modifier = Column(Integer, default=0)
    energy_modifier = Column(Integer, default=0)
    mana_modifier = Column(Integer, default=0)
    stamina_modifier = Column(Integer, default=0)
    charisma_modifier = Column(Integer, default=0)
    luck_modifier = Column(Integer, default=0)
    damage_modifier = Column(Integer, default=0)
    dodge_modifier = Column(Integer, default=0)
    res_effects_modifier = Column(Integer, default=0)
    res_physical_modifier = Column(Integer, default=0)
    res_cutting_modifier = Column(Integer, default=0)
    res_crushing_modifier = Column(Integer, default=0)
    res_piercing_modifier = Column(Integer, default=0)
    res_magic_modifier = Column(Integer, default=0)
    res_fire_modifier = Column(Integer, default=0)
    res_ice_modifier = Column(Integer, default=0)
    res_water_modifier = Column(Integer, default=0)
    res_electricity_modifier = Column(Integer, default=0)
    res_wind_modifier = Column(Integer, default=0)
    res_holy_modifier = Column(Integer, default=0)
    res_cursed_modifier = Column(Integer, default=0)
    critical_hit_chance_modifier = Column(Integer, default=0)
    critical_damage_modifier = Column(Integer, default=0)
    health_recovery = Column(Integer, default=0)
    energy_recovery = Column(Integer, default=0)
    mana_recovery = Column(Integer, default=0)
    stamina_recovery = Column(Integer, default=0)

    # Связи
    inventories = relationship("CharacterInventory", back_populates="item")
    equipment_slots = relationship("EquipmentSlot", back_populates="item")

# Определяем модель для хранения инвентаря персонажа
class CharacterInventory(Base):
    __tablename__ = "character_inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False)
    item_id = Column(Integer, ForeignKey('items.id'), nullable=False)
    quantity = Column(Integer, default=1)

    item = relationship("Items", back_populates="inventories")


# Таблица слотов экипировки
class EquipmentSlot(Base):
    __tablename__ = 'equipment_slots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False)
    slot_type = Column(Enum(
        'head', 'body', 'cloak', 'belt', 'ring',
        'necklace', 'main_weapon', 'additional_weapons', 'fast_slot_1', 'fast_slot_2', 'fast_slot_3', 'fast_slot_4'
    ), nullable=False)

    item_id = Column(Integer, ForeignKey('items.id'), nullable=True)
    item = relationship("Items", back_populates="equipment_slots")
