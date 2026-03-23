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
    bracelet = "bracelet"
    shield = "shield"

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

    primary_damage_type: Optional[str] = None
    armor_subclass: Optional[str] = None
    weapon_subclass: Optional[str] = None


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
    res_catting_modifier: Optional[int] = None
    res_crushing_modifier: Optional[int] = None
    res_piercing_modifier: Optional[int] = None
    res_magic_modifier: Optional[int] = None
    res_fire_modifier: Optional[int] = None
    res_ice_modifier: Optional[int] = None
    res_watering_modifier: Optional[int] = None
    res_electricity_modifier: Optional[int] = None
    res_wind_modifier: Optional[int] = None
    res_sainting_modifier: Optional[int] = None
    res_damning_modifier: Optional[int] = None
    critical_hit_chance_modifier: Optional[int] = None
    critical_damage_modifier: Optional[int] = None
    health_recovery: Optional[int] = None
    energy_recovery: Optional[int] = None
    mana_recovery: Optional[int] = None
    stamina_recovery: Optional[int] = None

    vul_effects_modifier: Optional[int] = None
    vul_physical_modifier: Optional[int] = None
    vul_catting_modifier: Optional[int] = None
    vul_crushing_modifier: Optional[int] = None
    vul_piercing_modifier: Optional[int] = None
    vul_magic_modifier: Optional[int] = None
    vul_fire_modifier: Optional[int] = None
    vul_ice_modifier: Optional[int] = None
    vul_watering_modifier: Optional[int] = None
    vul_electricity_modifier: Optional[int] = None
    vul_sainting_modifier: Optional[int] = None
    vul_wind_modifier: Optional[int] = None
    vul_damning_modifier: Optional[int] = None


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
    name: str
    item_type: str

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
    res_catting_modifier: Optional[int] = None
    res_crushing_modifier: Optional[int] = None
    res_piercing_modifier: Optional[int] = None
    res_magic_modifier: Optional[int] = None
    res_fire_modifier: Optional[int] = None
    res_ice_modifier: Optional[int] = None
    res_watering_modifier: Optional[int] = None
    res_electricity_modifier: Optional[int] = None
    res_wind_modifier: Optional[int] = None
    res_sainting_modifier: Optional[int] = None
    res_damning_modifier: Optional[int] = None
    critical_hit_chance_modifier: Optional[int] = None
    critical_damage_modifier: Optional[int] = None

    health_recovery: Optional[int] = None
    energy_recovery: Optional[int] = None
    mana_recovery: Optional[int] = None
    stamina_recovery: Optional[int] = None

    vul_effects_modifier: Optional[int] = None
    vul_physical_modifier: Optional[int] = None
    vul_catting_modifier: Optional[int] = None
    vul_crushing_modifier: Optional[int] = None
    vul_piercing_modifier: Optional[int] = None
    vul_magic_modifier: Optional[int] = None
    vul_fire_modifier: Optional[int] = None
    vul_ice_modifier: Optional[int] = None
    vul_watering_modifier: Optional[int] = None
    vul_electricity_modifier: Optional[int] = None
    vul_sainting_modifier: Optional[int] = None
    vul_wind_modifier: Optional[int] = None
    vul_damning_modifier: Optional[int] = None

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
    is_enabled: Optional[bool] = None

class EquipmentSlotCreate(EquipmentSlotBase):
    """
    Схема создания/обновления слота.
    """
    pass

class EquipmentSlot(EquipmentSlotBase):
    """
    Полноценная схема слота с ID и ссылкой на Item (через orm_mode).
    """

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


class FastSlot(BaseModel):
    slot_type: str
    item_id: int
    quantity: int
    name : str
    image : str


# -----------------------------------------------------------------------------
# 6. Trade schemas
# -----------------------------------------------------------------------------

class TradeStatus(str, Enum):
    pending = "pending"
    negotiating = "negotiating"
    completed = "completed"
    cancelled = "cancelled"
    expired = "expired"


class TradeProposeRequest(BaseModel):
    initiator_character_id: int
    target_character_id: int


class TradeProposeResponse(BaseModel):
    trade_id: int
    initiator_character_id: int
    target_character_id: int
    status: str


class TradeItemEntry(BaseModel):
    item_id: int
    quantity: int


class TradeUpdateItemsRequest(BaseModel):
    character_id: int
    items: List[TradeItemEntry] = []
    gold: int = 0


class TradeConfirmRequest(BaseModel):
    character_id: int


class TradeConfirmResponse(BaseModel):
    trade_id: int
    status: str
    message: Optional[str] = None


class TradeCancelResponse(BaseModel):
    trade_id: int
    status: str


class TradeItemDetail(BaseModel):
    item_id: int
    item_name: str
    item_image: Optional[str] = None
    quantity: int


class TradeSideState(BaseModel):
    character_id: int
    character_name: str
    items: List[TradeItemDetail] = []
    gold: int = 0
    confirmed: bool = False


class TradeStateResponse(BaseModel):
    trade_id: int
    status: str
    initiator: TradeSideState
    target: TradeSideState


class PendingTradeEntry(BaseModel):
    trade_id: int
    initiator_character_id: int
    initiator_name: str
    target_character_id: int
    target_name: str
    status: str
    created_at: str
    direction: str  # "incoming" or "outgoing"


class PendingTradesResponse(BaseModel):
    incoming: List[PendingTradeEntry] = []
    outgoing: List[PendingTradeEntry] = []
