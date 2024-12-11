from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class ItemType(str, Enum):
    head = "head"
    body = "body"
    cloak = "cloak"
    belt = "belt"
    ring = "ring"
    necklace = "necklace"
    main_weapon = "main_weapon"
    consumable = "consumable"
    resource = "resource"
    scroll = "scroll"
    misc = "misc"

class ItemRarity(str, Enum):
    common = "common"
    rare = "rare"
    epic = "epic"
    legendary = "legendary"
    mythical = "mythical"
    divine = "divine"
    demonic = "demonic"

# Схемы для предметов
class ItemBase(BaseModel):
    name: str
    image: Optional[str]
    item_level: int
    item_type: ItemType
    item_rarity: ItemRarity
    price: int
    max_stack_size: int
    is_unique: bool
    description: Optional[str]
    weight: float

    # Модификаторы характеристик
    strength_modifier: Optional[int] = None
    agility_modifier: Optional[int] = None
    intelligence_modifier: Optional[int] = None
    endurance_modifier: Optional[int] = None
    health_modifier: Optional[int] = None
    energy_modifier: Optional[int] = None
    mana_modifier: Optional[int] = None
    stamina_modifier: Optional[int] = None
    charisma_modifier: Optional[int] = None
    luck_modifier: Optional[int] = None
    damage_modifier: Optional[int] = None
    dodge_modifier: Optional[int] = None
    res_effects_modifier: Optional[int] = None
    res_physical_modifier: Optional[int] = None
    res_cutting_modifier: Optional[int] = None
    res_crushing_modifier: Optional[int] = None
    res_piercing_modifier: Optional[int] = None
    res_magic_modifier: Optional[int] = None
    res_fire_modifier: Optional[int] = None
    res_ice_modifier: Optional[int] = None
    res_water_modifier: Optional[int] = None
    res_electricity_modifier: Optional[int] = None
    res_wind_modifier: Optional[int] = None
    res_holy_modifier: Optional[int] = None
    res_cursed_modifier: Optional[int] = None
    critical_hit_chance_modifier: Optional[int] = None
    critical_damage_modifier: Optional[int] = None
    health_recovery: Optional[int] = None
    energy_recovery: Optional[int] = None
    mana_recovery: Optional[int] = None
    stamina_recovery: Optional[int] = None

class ItemCreate(ItemBase):
    pass

class ItemRequest(BaseModel):
    item_id: int
    quantity: int

class InventoryRequest(BaseModel):
    character_id: int
    items: List[ItemRequest]


class ItemResponse(BaseModel):
    item_id: int
    name: str
    max_stack_size: int
    quantity: int
    description: Optional[str]
    weight: float
    strength_modifier: Optional[int] = None
    agility_modifier: Optional[int] = None
    intelligence_modifier: Optional[int] = None
    endurance_modifier: Optional[int] = None
    health_modifier: Optional[int] = None
    energy_modifier: Optional[int] = None
    mana_modifier: Optional[int] = None
    stamina_modifier: Optional[int] = None
    charisma_modifier: Optional[int] = None
    luck_modifier: Optional[int] = None
    damage_modifier: Optional[int] = None
    dodge_modifier: Optional[int] = None
    res_effects_modifier: Optional[int] = None
    res_physical_modifier: Optional[int] = None
    res_cutting_modifier: Optional[int] = None
    res_crushing_modifier: Optional[int] = None
    res_piercing_modifier: Optional[int] = None
    res_magic_modifier: Optional[int] = None
    res_fire_modifier: Optional[int] = None
    res_ice_modifier: Optional[int] = None
    res_water_modifier: Optional[int] = None
    res_electricity_modifier: Optional[int] = None
    res_wind_modifier: Optional[int] = None
    res_holy_modifier: Optional[int] = None
    res_cursed_modifier: Optional[int] = None
    critical_hit_chance_modifier: Optional[int] = None
    critical_damage_modifier: Optional[int] = None
    health_recovery: Optional[int] = None
    energy_recovery: Optional[int] = None
    mana_recovery: Optional[int] = None
    stamina_recovery: Optional[int] = None


class InventoryResponse(BaseModel):
    character_id: int
    items: List[ItemResponse]

class Item(ItemBase):
    id: int

    class Config:
        orm_mode = True

# Схемы для инвентаря
class InventoryItem(BaseModel):
    item_id: int
    quantity: int

class CharacterInventoryCreate(BaseModel):
    character_id: int
    items: List[InventoryItem]

class CharacterInventoryBase(BaseModel):
    character_id: int
    item_id: int
    quantity: int

class CharacterInventory(CharacterInventoryBase):
    id: int
    item: Item

    class Config:
        orm_mode = True

# Схемы для слотов экипировки
class EquipmentSlotBase(BaseModel):
    character_id: int
    slot_type: str  # Можно добавить валидацию допустимых типов
    item_id: Optional[int] = None

class EquipmentSlotCreate(EquipmentSlotBase):
    pass

class EquipmentSlot(EquipmentSlotBase):
    id: int
    item: Optional[Item]

    class Config:
        orm_mode = True
