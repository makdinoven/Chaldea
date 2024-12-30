from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

# -----------------------------------------------------------------------------
# 1. Перечисления (Enum)
# -----------------------------------------------------------------------------

class ItemType(str, Enum):
    head = "head"
    body = "body"
    cloak = "cloak"
    belt = "belt"
    ring = "ring"
    necklace = "necklace"
    main_weapon = "main_weapon"
    additional_weapons = "additional_weapons"
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

# -----------------------------------------------------------------------------
# 2. Схемы для предметов (Items)
# -----------------------------------------------------------------------------

class ItemBase(BaseModel):
    """
    Базовая схема для предмета, содержит все основные поля.
    """
    name: str
    image: Optional[str] = None
    item_level: int
    item_type: ItemType
    item_rarity: ItemRarity

    # Разрешаем None, если в базе данных price может быть NULL
    price: Optional[int] = None

    max_stack_size: int
    is_unique: bool
    description: Optional[str] = None

    # Если в БД weight может быть NULL, то используем Optional[float];
    # иначе можно поставить дефолт 0.0
    weight: float = 0.0

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
    """
    Схема для создания нового предмета (ничем не отличается от базовой,
    но на будущее можно расширять).
    """
    pass

class Item(ItemBase):
    """
    Схема для возврата предмета из БД,
    добавляет поле id и включает orm_mode.
    """
    id: int

    class Config:
        orm_mode = True

# -----------------------------------------------------------------------------
# 3. Схемы для операций с инвентарём
# -----------------------------------------------------------------------------

class ItemRequest(BaseModel):
    """
    Запрос на добавление предмета в инвентарь:
    item_id + нужное количество (quantity).
    """
    item_id: int
    quantity: int

class InventoryRequest(BaseModel):
    """
    Запрос на создание/обновление инвентаря для персонажа:
    character_id + список ItemRequest.
    """
    character_id: int
    items: List[ItemRequest]

class ItemResponse(BaseModel):
    """
    Ответ об одном конкретном предмете в инвентаре:
    какой item_id, сколько quantity, базовые поля.
    """
    item_id: int
    name: str
    max_stack_size: int
    quantity: int
    description: Optional[str] = None
    weight: float = 0.0

    # Модификаторы
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
    """
    Ответ при создании/получении инвентаря персонажа:
    ID персонажа + список предметов.
    """
    character_id: int
    items: List[ItemResponse]

class InventoryItem(BaseModel):
    """
    Схема для добавления предметов в инвентарь (при создании?).
    """
    item_id: int
    quantity: int

class CharacterInventoryBase(BaseModel):
    """
    Базовая схема для связки 'персонаж - предмет - количество'.
    """
    character_id: int
    item_id: int
    quantity: int

class CharacterInventory(CharacterInventoryBase):
    """
    Схема, которую можем возвращать из эндпоинтов инвентаря.
    Показывает связь + сам объект Item (через orm_mode).
    """
    id: int
    item: Item

    class Config:
        orm_mode = True

class CharacterInventoryCreate(BaseModel):
    """
    Пример, если нужно одним запросом создать несколько предметов в инвентаре.
    """
    character_id: int
    items: List[InventoryItem]

# -----------------------------------------------------------------------------
# 4. Схемы для слотов экипировки
# -----------------------------------------------------------------------------

class EquipmentSlotBase(BaseModel):
    """
    Базовая схема для слота экипировки:
    указывает персонажа, тип слота и (опционально) предмет, который в слоте.
    """
    character_id: int
    slot_type: str  # Желательно использовать Enum или валидацию
    item_id: Optional[int] = None

class EquipmentSlotCreate(EquipmentSlotBase):
    """
    Схема создания/обновления слота.
    """
    pass

class EquipmentSlot(EquipmentSlotBase):
    """
    Полноценная схема слота с ID и ссылкой на Item (через orm_mode).
    """
    id: int
    item: Optional[Item]

    class Config:
        orm_mode = True

# -----------------------------------------------------------------------------
# 5. Прочие схемы
# -----------------------------------------------------------------------------

class EquipItemRequest(BaseModel):
    """
    Схема-запрос на экипировку предмета (обычно item_id).
    В логике микросервиса мы автоматически подбираем слот по типу.
    """
    item_id: int
