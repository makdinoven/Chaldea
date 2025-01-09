from sqlalchemy import Column, Integer, String, Enum, Boolean, DECIMAL, Text, ForeignKey, Float
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
        'head', 'body', 'cloak', 'belt', 'ring', 'necklace', 'bracelet', 'main_weapon',
        'consumable','additional_weapons', 'resource', 'scroll', 'misc'
    ), nullable=False)
    item_rarity = Column(Enum(
        'common', 'rare', 'epic', 'legendary', 'mythical', 'divine', 'demonic'
    ), nullable=False)
    price = Column(Integer, nullable=True)
    max_stack_size = Column(Integer, default=1)
    is_unique = Column(Boolean, nullable=False, default=False)
    description = Column(Text)

    fast_slot_bonus = Column(Integer, default=0)  # Сколько дополнительных быстрых слотов даёт предмет

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

    res_effects_modifier = Column(Float, default=0.0)
    res_physical_modifier = Column(Float, default=0.0)
    res_catting_modifier = Column(Float, default=0.0)
    res_crushing_modifier = Column(Float, default=0.0)
    res_piercing_modifier = Column(Float, default=0.0)
    res_magic_modifier = Column(Float, default=0.0)
    res_fire_modifier = Column(Float, default=0.0)
    res_ice_modifier = Column(Float, default=0.0)
    res_watering_modifier = Column(Float, default=0.0)
    res_electricity_modifier = Column(Float, default=0.0)
    res_wind_modifier = Column(Float, default=0.0)
    res_sainting_modifier = Column(Float, default=0.0)
    res_damning_modifier = Column(Float, default=0.0)
    critical_hit_chance_modifier = Column(Float, default=0.0)
    critical_damage_modifier = Column(Float, default=0.0)

    health_recovery = Column(Integer, default=0)
    energy_recovery = Column(Integer, default=0)
    mana_recovery = Column(Integer, default=0)
    stamina_recovery = Column(Integer, default=0)

    vul_effects_modifier = Column(Float, default=0.0)
    vul_physical_modifier = Column(Float, default=0.0)
    vul_catting_modifier = Column(Float, default=0.0)
    vul_crushing_modifier = Column(Float, default=0.0)
    vul_piercing_modifier = Column(Float, default=0.0)
    vul_magic_modifier = Column(Float, default=0.0)
    vul_fire_modifier = Column(Float, default=0.0)
    vul_ice_modifier = Column(Float, default=0.0)
    vul_watering_modifier = Column(Float, default=0.0)
    vul_electricity_modifier = Column(Float, default=0.0)
    vul_sainting_modifier = Column(Float, default=0.0)
    vul_wind_modifier = Column(Float, default=0.0)
    vul_damning_modifier = Column(Float, default=0.0)

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
        'necklace', 'bracelet', 'main_weapon', 'additional_weapons', 'fast_slot_1', 'fast_slot_2', 'fast_slot_3', 'fast_slot_4',
    'fast_slot_5', 'fast_slot_6', 'fast_slot_7', 'fast_slot_8',
    'fast_slot_9', 'fast_slot_10'
    ), nullable=False)

    item_id = Column(Integer, ForeignKey('items.id'), nullable=True)
    item = relationship("Items", back_populates="equipment_slots")

    is_enabled = Column(Boolean, default=True)

