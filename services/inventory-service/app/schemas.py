from pydantic import BaseModel
from typing import List, Optional, Any
from enum import Enum
from datetime import datetime

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
    blueprint = "blueprint"
    recipe = "recipe"
    gem = "gem"
    rune = "rune"

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

    socket_count: int = 0
    whetstone_level: Optional[int] = None
    identify_level: Optional[int] = None
    essence_result_item_id: Optional[int] = None

    # Buff fields (for consumable buff items like XP books)
    buff_type: Optional[str] = None
    buff_value: Optional[float] = None
    buff_duration_minutes: Optional[int] = None

    max_durability: int = 0
    repair_power: Optional[int] = None

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
    blueprint_recipe_id: Optional[int] = None

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
    is_identified: bool = True
    enhancement_points_spent: int = 0
    enhancement_bonuses: Optional[str] = None
    socketed_gems: Optional[str] = None
    current_durability: Optional[int] = None

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
    id: Optional[int] = None
    character_id: int
    slot_type: str  # Желательно использовать Enum или валидацию
    item_id: Optional[int] = None
    is_enabled: Optional[bool] = None
    enhancement_points_spent: int = 0
    enhancement_bonuses: Optional[str] = None
    socketed_gems: Optional[str] = None
    current_durability: Optional[int] = None

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
    Схема-запрос на экипировку предмета.
    item_id — ID шаблона предмета (обязательный).
    inventory_item_id — ID конкретного экземпляра в инвентаре (опциональный).
    Если inventory_item_id указан, экипируется именно этот экземпляр (с заточкой, камнями и т.д.).
    """
    item_id: int
    inventory_item_id: Optional[int] = None


# -----------------------------------------------------------------------------
# Consume item (service-to-service, battle usage)
# -----------------------------------------------------------------------------

class ConsumeItemRequest(BaseModel):
    item_id: int


class ConsumeItemResponse(BaseModel):
    status: str
    remaining_quantity: int


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


# -----------------------------------------------------------------------------
# 7. Profession schemas
# -----------------------------------------------------------------------------

class ProfessionBase(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    icon: Optional[str] = None
    sort_order: int = 0


class ProfessionCreate(ProfessionBase):
    pass


class ProfessionUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class ProfessionRankOut(BaseModel):
    id: int
    rank_number: int
    name: str
    description: Optional[str] = None
    required_experience: int
    icon: Optional[str] = None

    class Config:
        orm_mode = True


class ProfessionOut(ProfessionBase):
    id: int
    is_active: bool
    ranks: List[ProfessionRankOut] = []

    class Config:
        orm_mode = True


class CharacterProfessionOut(BaseModel):
    character_id: int
    profession: ProfessionOut
    current_rank: int
    rank_name: str
    experience: int
    chosen_at: str

    class Config:
        orm_mode = True


class ChooseProfessionRequest(BaseModel):
    profession_id: int


class ChangeProfessionRequest(BaseModel):
    profession_id: int


class ProfessionRankCreate(BaseModel):
    rank_number: int
    name: str
    description: Optional[str] = None
    required_experience: int = 0
    icon: Optional[str] = None


class ProfessionRankUpdate(BaseModel):
    rank_number: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    required_experience: Optional[int] = None
    icon: Optional[str] = None


class AdminSetRankRequest(BaseModel):
    rank_number: int


# -----------------------------------------------------------------------------
# 8. Recipe / Crafting schemas
# -----------------------------------------------------------------------------

class RecipeIngredientOut(BaseModel):
    item_id: int
    item_name: str
    item_image: Optional[str] = None
    quantity: int
    available: int = 0

    class Config:
        orm_mode = True


class RecipeResultItemOut(BaseModel):
    id: int
    name: str
    image: Optional[str] = None
    item_type: str
    item_rarity: str

    class Config:
        orm_mode = True


class RecipeOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    profession_id: int
    profession_name: str
    required_rank: int
    result_item: RecipeResultItemOut
    result_quantity: int
    rarity: str
    icon: Optional[str] = None
    xp_reward: Optional[int] = None
    ingredients: List[RecipeIngredientOut] = []
    can_craft: bool = False
    source: str  # "learned" or "blueprint"
    blueprint_item_id: Optional[int] = None

    class Config:
        orm_mode = True


class RecipeIngredientCreate(BaseModel):
    item_id: int
    quantity: int


class RecipeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    profession_id: int
    required_rank: int = 1
    result_item_id: int
    result_quantity: int = 1
    rarity: str = "common"
    icon: Optional[str] = None
    auto_learn_rank: Optional[int] = None
    is_blueprint_recipe: bool = False
    xp_reward: Optional[int] = None
    ingredients: List[RecipeIngredientCreate] = []


class RecipeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    profession_id: Optional[int] = None
    required_rank: Optional[int] = None
    result_item_id: Optional[int] = None
    result_quantity: Optional[int] = None
    rarity: Optional[str] = None
    icon: Optional[str] = None
    auto_learn_rank: Optional[int] = None
    is_active: Optional[bool] = None
    is_blueprint_recipe: Optional[bool] = None
    xp_reward: Optional[int] = None
    ingredients: Optional[List[RecipeIngredientCreate]] = None


class CraftRequest(BaseModel):
    recipe_id: int
    blueprint_item_id: Optional[int] = None


class CraftResult(BaseModel):
    success: bool
    crafted_item: dict
    consumed_materials: list
    blueprint_consumed: bool = False
    xp_earned: int = 0
    new_total_xp: int = 0
    rank_up: bool = False
    new_rank_name: Optional[str] = None
    auto_learned_recipes: list = []


class LearnRecipeRequest(BaseModel):
    recipe_id: int


class RecipeAdminOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    profession_id: int
    profession_name: str = ""
    required_rank: int
    result_item_id: int
    result_item_name: str = ""
    result_quantity: int
    rarity: str
    icon: Optional[str] = None
    xp_reward: Optional[int] = None
    is_blueprint_recipe: bool
    is_active: bool
    auto_learn_rank: Optional[int] = None
    ingredients: List[RecipeIngredientOut] = []
    recipe_item_id: Optional[int] = None
    recipe_item_name: Optional[str] = None

    class Config:
        orm_mode = True


class RecipeListResponse(BaseModel):
    items: List[RecipeAdminOut] = []
    total: int
    page: int
    per_page: int


# -----------------------------------------------------------------------------
# 9. Sharpening schemas
# -----------------------------------------------------------------------------

class SharpenRequest(BaseModel):
    inventory_item_id: int  # character_inventory.id or equipment_slots.id
    whetstone_item_id: int  # character_inventory.id of the whetstone
    stat_field: str  # which stat to sharpen, e.g. "strength_modifier", "res_fire_modifier"
    source: str = "inventory"  # "inventory" or "equipment"


class SharpenResult(BaseModel):
    success: bool
    item_name: str
    stat_field: str
    stat_display_name: str
    old_value: float
    new_value: float
    points_spent: int
    points_remaining: int
    point_cost: int
    whetstone_consumed: bool
    xp_earned: int
    new_total_xp: int
    rank_up: bool
    new_rank_name: Optional[str] = None


class SharpenStatInfo(BaseModel):
    field: str
    name: str
    base_value: float
    sharpened_count: int
    max: int
    is_existing: bool
    point_cost: int
    can_sharpen: bool


class SharpenWhetstoneInfo(BaseModel):
    inventory_item_id: int
    name: str
    quantity: int
    success_chance: int


class SharpenInfoResponse(BaseModel):
    item_name: str
    item_type: str
    points_spent: int
    points_remaining: int
    stats: List[SharpenStatInfo] = []
    whetstones: List[SharpenWhetstoneInfo] = []


# -----------------------------------------------------------------------------
# 10. Essence extraction schemas
# -----------------------------------------------------------------------------

class ExtractEssenceRequest(BaseModel):
    crystal_item_id: int  # character_inventory.id of the crystal


class ExtractEssenceResult(BaseModel):
    success: bool
    crystal_name: str
    essence_name: Optional[str] = None
    crystal_consumed: bool = True
    xp_earned: int = 0
    new_total_xp: int = 0
    rank_up: bool = False
    new_rank_name: Optional[str] = None


class CrystalInfo(BaseModel):
    inventory_item_id: int
    item_id: int
    name: str
    image: Optional[str] = None
    quantity: int
    essence_name: str
    essence_image: Optional[str] = None
    success_chance: int = 75


class ExtractInfoResponse(BaseModel):
    crystals: List[CrystalInfo] = []


# -----------------------------------------------------------------------------
# 11. Transmutation schemas
# -----------------------------------------------------------------------------

class TransmuteRequest(BaseModel):
    inventory_item_id: int  # character_inventory.id of the resource to transmute


class TransmuteResult(BaseModel):
    success: bool
    consumed_item_name: str
    consumed_quantity: int
    result_item_name: str
    result_item_rarity: str
    xp_earned: int
    new_total_xp: int
    rank_up: bool
    new_rank_name: Optional[str] = None


class TransmuteItemInfo(BaseModel):
    inventory_item_id: int
    item_id: int
    name: str
    image: Optional[str] = None
    quantity: int
    item_rarity: str
    next_rarity: str
    can_transmute: bool
    required_quantity: int = 5


class TransmuteInfoResponse(BaseModel):
    items: List[TransmuteItemInfo] = []


# -----------------------------------------------------------------------------
# 12. Gem socket schemas
# -----------------------------------------------------------------------------

class GemSlotInfo(BaseModel):
    slot_index: int
    gem_item_id: Optional[int] = None
    gem_name: Optional[str] = None
    gem_image: Optional[str] = None
    gem_modifiers: dict = {}


class AvailableGemInfo(BaseModel):
    inventory_item_id: int
    item_id: int
    name: str
    image: Optional[str] = None
    quantity: int
    modifiers: dict = {}


class SocketInfoResponse(BaseModel):
    item_name: str
    item_type: str
    socket_count: int
    slots: List[GemSlotInfo] = []
    available_gems: List[AvailableGemInfo] = []


class InsertGemRequest(BaseModel):
    item_row_id: int
    source: str = "inventory"
    slot_index: int
    gem_inventory_id: int


class InsertGemResult(BaseModel):
    success: bool
    item_name: str
    gem_name: str
    slot_index: int
    xp_earned: int
    new_total_xp: int
    rank_up: bool
    new_rank_name: Optional[str] = None


class ExtractGemRequest(BaseModel):
    item_row_id: int
    source: str = "inventory"
    slot_index: int


class ExtractGemResult(BaseModel):
    success: bool
    item_name: str
    gem_name: str
    gem_preserved: bool
    preservation_chance: int
    slot_index: int
    xp_earned: int
    new_total_xp: int
    rank_up: bool
    new_rank_name: Optional[str] = None


# -----------------------------------------------------------------------------
# 13. Smelting schemas
# -----------------------------------------------------------------------------

class SmeltIngredientReturn(BaseModel):
    item_id: int
    name: str
    image: Optional[str] = None
    quantity: int


class SmeltInfoResponse(BaseModel):
    item_name: str
    item_type: str
    has_gems: bool
    gem_count: int
    has_recipe: bool
    ingredients: List[SmeltIngredientReturn] = []


class SmeltRequest(BaseModel):
    inventory_item_id: int


class SmeltResult(BaseModel):
    success: bool
    item_name: str
    gems_destroyed: int
    materials_returned: list
    xp_earned: int
    new_total_xp: int
    rank_up: bool
    new_rank_name: Optional[str] = None


# -----------------------------------------------------------------------------
# 14. Identification schemas
# -----------------------------------------------------------------------------

class IdentifyRequest(BaseModel):
    inventory_item_id: int


class IdentifyResult(BaseModel):
    success: bool
    item_name: str
    scroll_used: str
    item_rarity: str


# -----------------------------------------------------------------------------
# 15. Buff schemas
# -----------------------------------------------------------------------------

class ActiveBuffOut(BaseModel):
    id: int
    character_id: int
    buff_type: str
    value: float
    expires_at: str
    source_item_name: Optional[str] = None
    remaining_seconds: int

    class Config:
        orm_mode = True


class ActiveBuffsResponse(BaseModel):
    buffs: List[ActiveBuffOut] = []


class UseBuffItemRequest(BaseModel):
    inventory_item_id: int


class UseBuffItemResult(BaseModel):
    success: bool
    buff_type: str
    value: float
    duration_minutes: int
    source_item_name: str
    message: str


# -----------------------------------------------------------------------------
# 16. Durability / Repair schemas
# -----------------------------------------------------------------------------

class RepairItemRequest(BaseModel):
    inventory_item_id: int  # CharacterInventory.id or EquipmentSlot.id
    repair_kit_item_id: int  # item_id of repair kit (must be in inventory)
    source: str  # "inventory" or "equipment"


class RepairItemResponse(BaseModel):
    success: bool
    new_durability: int
    max_durability: int
    repair_kit_consumed: bool


class UpdateDurabilityEntry(BaseModel):
    slot_type: str
    new_durability: int


class UpdateDurabilityRequest(BaseModel):
    character_id: int
    entries: List[UpdateDurabilityEntry]


class UpdateDurabilityResponse(BaseModel):
    status: str
    updated: int
    mods_removed_for: List[str] = []


class SocketedItemDetail(BaseModel):
    slot_index: int
    item_id: Optional[int] = None
    name: Optional[str] = None
    image: Optional[str] = None
    item_type: Optional[str] = None
    modifiers: dict = {}

    class Config:
        orm_mode = True

class ItemDetailResponse(BaseModel):
    """Full item card data."""
    item: Item
    current_durability: Optional[int] = None
    max_durability: int = 0
    enhancement_points_spent: int = 0
    enhancement_bonuses: Optional[dict] = None
    socketed_gems: Optional[list] = None
    socketed_items: List[SocketedItemDetail] = []
    is_identified: bool = True
    source: str
