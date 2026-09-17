from pydantic import BaseModel, root_validator, validator, constr
from typing import List, Optional, Any, Dict
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
    weapon = "weapon"
    consumable = "consumable"
    resource = "resource"
    scroll = "scroll"
    misc = "misc"
    bracelet = "bracelet"
    recipe = "recipe"
    gem = "gem"
    rune = "rune"
    gathering_tool = "gathering_tool"


# Armor class only means something for these slots (cloak/belt have none)
ARMOR_SUBCLASS_TYPES = ("head", "body")
WEAPON_SUBCLASS_TYPES = ("weapon",)

# FEAT-164: rarity cap. Mythical/divine/demonic exist ONLY on equipment; every
# other item type (incl. any future non-equipment type) is capped at legendary.
# These are sets — no ordering between rarities is implied.
EQUIPMENT_ITEM_TYPES = frozenset({"head", "body", "cloak", "belt", "ring", "necklace", "bracelet", "weapon"})
EQUIPMENT_ONLY_RARITIES = frozenset({"mythical", "divine", "demonic"})
EQUIPMENT_ONLY_RARITY_ERROR = (
    "Мифическая, божественная и демоническая редкость доступны только для снаряжения"
)
FOOD_ITEM_TYPE = "consumable"


def _enum_value(value):
    return value.value if isinstance(value, Enum) else value


def is_rarity_allowed_for_type(item_type, item_rarity) -> bool:
    """False when an equipment-only rarity is used on a non-equipment type."""
    return not (
        _enum_value(item_rarity) in EQUIPMENT_ONLY_RARITIES
        and _enum_value(item_type) not in EQUIPMENT_ITEM_TYPES
    )


class ResourceSubcategory(str, Enum):
    """FEAT-165: resource subcategory (only for item_type='resource')."""
    # raw materials
    ore = "ore"
    herb = "herb"
    wood = "wood"
    ingredient = "ingredient"
    trophy = "trophy"
    # refined products
    ingot = "ingot"
    magic_dust = "magic_dust"
    essence = "essence"
    reagent = "reagent"
    material = "material"
    # profession consumables
    whetstone = "whetstone"
    repair_kit = "repair_kit"


class WhetstoneGroup(str, Enum):
    """FEAT-165: which gear a sharpening stone fits."""
    weapon_armor = "weapon_armor"
    cloak_belt = "cloak_belt"
    jewelry = "jewelry"


WHETSTONE_LEVELS = (1, 2, 3)
# Items that may have socket_count > 0 (belt has no sockets since FEAT-165)
SOCKETABLE_ITEM_TYPES = frozenset({"weapon", "head", "body", "cloak", "ring", "necklace", "bracelet"})

# FEAT-165 conversions / refining bounds
CONVERSION_QTY_MIN = 1
CONVERSION_QTY_MAX = 100
REFINE_MAX_QUANTITY = 9999


class ArmorSubclass(str, Enum):
    cloth = "cloth"
    light_armor = "light_armor"
    medium_armor = "medium_armor"
    heavy_armor = "heavy_armor"


class WeaponSubclass(str, Enum):
    """Weapon kind. Each kind belongs to one category; see WEAPON_KIND_CATEGORY."""
    sword = "sword"
    hatchet = "hatchet"
    mace = "mace"
    sabre = "sabre"
    dagger = "dagger"
    espada = "espada"
    tanto = "tanto"
    war_pick = "war_pick"
    bastard_sword = "bastard_sword"
    axe = "axe"
    katana = "katana"
    broadsword = "broadsword"
    rapier = "rapier"
    war_hammer = "war_hammer"
    zweihander = "zweihander"
    maul = "maul"
    battle_axe = "battle_axe"
    scythe = "scythe"
    nodachi = "nodachi"
    halberd = "halberd"
    glaive = "glaive"
    pike = "pike"
    spear = "spear"
    naginata = "naginata"
    bow = "bow"
    pistol = "pistol"
    musket = "musket"
    buckler = "buckler"
    targe = "targe"
    tower_shield = "tower_shield"
    lute = "lute"
    knuckledusters = "knuckledusters"
    staff = "staff"
    grimoire = "grimoire"
    amulet = "amulet"
    rod = "rod"
    magic_weapon = "magic_weapon"
    catalyst = "catalyst"
    wand = "wand"


# Category of each weapon kind (for class equipment restrictions)
WEAPON_KIND_CATEGORY = {
    "sword": "one_handed", "hatchet": "one_handed", "mace": "one_handed", "sabre": "one_handed", "dagger": "one_handed", "espada": "one_handed", "tanto": "one_handed", "war_pick": "one_handed",
    "bastard_sword": "one_and_half", "axe": "one_and_half", "katana": "one_and_half", "broadsword": "one_and_half", "rapier": "one_and_half", "war_hammer": "one_and_half",
    "zweihander": "two_handed", "maul": "two_handed", "battle_axe": "two_handed", "scythe": "two_handed", "nodachi": "two_handed",
    "halberd": "polearm", "glaive": "polearm", "pike": "polearm", "spear": "polearm", "naginata": "polearm",
    "bow": "ranged", "pistol": "ranged", "musket": "ranged",
    "buckler": "shield", "targe": "shield", "tower_shield": "shield",
    "lute": "other", "knuckledusters": "other",
    "staff": "magic", "grimoire": "magic", "amulet": "magic", "rod": "magic", "magic_weapon": "magic", "catalyst": "magic", "wand": "magic",
}


class ToolCategory(str, Enum):
    pickaxe = "pickaxe"
    sickle = "sickle"
    axe = "axe"


# Equipment-stat modifier fields that gathering_tool items must NOT set.
GATHERING_TOOL_FORBIDDEN_STAT_FIELDS = (
    "strength_modifier",
    "agility_modifier",
    "intelligence_modifier",
    "endurance_modifier",
    "health_modifier",
    "energy_modifier",
    "mana_modifier",
    "stamina_modifier",
    "charisma_modifier",
    "luck_modifier",
    "damage_modifier",
    "dodge_modifier",
    "res_effects_modifier",
    "res_physical_modifier",
    "res_catting_modifier",
    "res_crushing_modifier",
    "res_piercing_modifier",
    "res_magic_modifier",
    "res_fire_modifier",
    "res_ice_modifier",
    "res_watering_modifier",
    "res_electricity_modifier",
    "res_wind_modifier",
    "res_sainting_modifier",
    "res_damning_modifier",
    "critical_hit_chance_modifier",
    "critical_damage_modifier",
    "health_recovery",
    "energy_recovery",
    "mana_recovery",
    "stamina_recovery",
    "vul_effects_modifier",
    "vul_physical_modifier",
    "vul_catting_modifier",
    "vul_crushing_modifier",
    "vul_piercing_modifier",
    "vul_magic_modifier",
    "vul_fire_modifier",
    "vul_ice_modifier",
    "vul_watering_modifier",
    "vul_electricity_modifier",
    "vul_sainting_modifier",
    "vul_wind_modifier",
    "vul_damning_modifier",
)


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
    # FEAT-165
    resource_subcategory: Optional[ResourceSubcategory] = None
    whetstone_group: Optional[WhetstoneGroup] = None

    # Buff fields (for consumable buff items like XP books)
    buff_type: Optional[str] = None
    buff_value: Optional[float] = None
    buff_duration_minutes: Optional[int] = None

    # FEAT-164: food gives "Сытость" (24h) when eaten via /eat-food
    is_food: bool = False

    max_durability: int = 0
    repair_power: Optional[int] = None

    primary_damage_type: Optional[str] = None
    armor_subclass: Optional[ArmorSubclass] = None
    weapon_subclass: Optional[WeaponSubclass] = None

    # Gathering tool fields (only meaningful when item_type='gathering_tool')
    tool_category: Optional[ToolCategory] = None
    gather_double_chance_bonus: Optional[float] = None
    gather_speed_bonus_pct: Optional[float] = None
    gather_stamina_bonus_pct: Optional[float] = None


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
    res_effects_modifier: Optional[float] = None
    res_physical_modifier: Optional[float] = None
    res_catting_modifier: Optional[float] = None
    res_crushing_modifier: Optional[float] = None
    res_piercing_modifier: Optional[float] = None
    res_magic_modifier: Optional[float] = None
    res_fire_modifier: Optional[float] = None
    res_ice_modifier: Optional[float] = None
    res_watering_modifier: Optional[float] = None
    res_electricity_modifier: Optional[float] = None
    res_wind_modifier: Optional[float] = None
    res_sainting_modifier: Optional[float] = None
    res_damning_modifier: Optional[float] = None
    critical_hit_chance_modifier: Optional[float] = None
    critical_damage_modifier: Optional[float] = None
    health_recovery: Optional[int] = None
    energy_recovery: Optional[int] = None
    mana_recovery: Optional[int] = None
    stamina_recovery: Optional[int] = None

    vul_effects_modifier: Optional[float] = None
    vul_physical_modifier: Optional[float] = None
    vul_catting_modifier: Optional[float] = None
    vul_crushing_modifier: Optional[float] = None
    vul_piercing_modifier: Optional[float] = None
    vul_magic_modifier: Optional[float] = None
    vul_fire_modifier: Optional[float] = None
    vul_ice_modifier: Optional[float] = None
    vul_watering_modifier: Optional[float] = None
    vul_electricity_modifier: Optional[float] = None
    vul_sainting_modifier: Optional[float] = None
    vul_wind_modifier: Optional[float] = None
    vul_damning_modifier: Optional[float] = None


class ItemCreate(ItemBase):
    """
    Схема для создания/обновления предмета.
    Включает валидацию специфичных для gathering_tool полей.
    """
    # Recipe item -> the recipe it teaches. Existence is checked in the endpoint.
    blueprint_recipe_id: Optional[int] = None

    @root_validator
    def _validate_type_bound_fields(cls, values):
        item_type = values.get("item_type")
        item_type = item_type.value if isinstance(item_type, Enum) else item_type

        if values.get("armor_subclass") is not None and item_type not in ARMOR_SUBCLASS_TYPES:
            raise ValueError("Класс брони можно указать только для головы и тела")
        if values.get("weapon_subclass") is not None and item_type not in WEAPON_SUBCLASS_TYPES:
            raise ValueError("Подкласс оружия можно указать только для оружия")
        if values.get("blueprint_recipe_id") is not None and item_type != "recipe":
            raise ValueError("Рецепт можно привязать только к предмету-рецепту")
        if (values.get("socket_count") or 0) > 0 and item_type not in SOCKETABLE_ITEM_TYPES:
            raise ValueError("Слоты доступны только для оружия, брони, шлема, плаща и украшений")
        return values

    @root_validator
    def _validate_resource_subcategory(cls, values):
        """FEAT-165: subcategory, sharpening stone and repair kit fields."""
        item_type = _enum_value(values.get("item_type"))
        if item_type is None:
            return values  # field-level validation already failed
        subcategory = _enum_value(values.get("resource_subcategory"))
        whetstone_level = values.get("whetstone_level")
        whetstone_group = values.get("whetstone_group")
        repair_power = values.get("repair_power")
        has_level = whetstone_level not in (None, 0)
        has_power = repair_power not in (None, 0)

        if subcategory is not None and item_type != "resource":
            raise ValueError("Подкатегорию можно указать только для ресурса")

        if subcategory == ResourceSubcategory.whetstone.value:
            if not has_level or whetstone_group is None:
                raise ValueError("Для камня заточки укажите уровень и группу")
            if whetstone_level not in WHETSTONE_LEVELS:
                raise ValueError("Уровень камня заточки должен быть 1, 2 или 3")
        elif has_level or whetstone_group is not None:
            raise ValueError(
                "Уровень и группу камня заточки можно указать только для камня заточки"
            )

        if subcategory == ResourceSubcategory.repair_kit.value:
            if repair_power is None or repair_power <= 0:
                raise ValueError("Для ремкомплекта укажите силу ремонта больше 0")
        elif has_power and item_type == "resource":
            raise ValueError("Сила ремонта указывается только для ремкомплекта")
        return values

    @root_validator
    def _validate_food_and_rarity(cls, values):
        item_type = _enum_value(values.get("item_type"))
        item_rarity = _enum_value(values.get("item_rarity"))
        if item_type is None or item_rarity is None:
            return values  # field-level validation already failed

        if values.get("is_food"):
            if item_type != FOOD_ITEM_TYPE:
                raise ValueError("Едой может быть только расходуемый предмет")
            if values.get("buff_type"):
                raise ValueError("Еда не может быть баффовым предметом")

        if not is_rarity_allowed_for_type(item_type, item_rarity):
            raise ValueError(EQUIPMENT_ONLY_RARITY_ERROR)
        return values

    @root_validator
    def _validate_gathering_tool_fields(cls, values):
        item_type = values.get("item_type")
        tool_category = values.get("tool_category")
        bonus_fields = (
            "gather_double_chance_bonus",
            "gather_speed_bonus_pct",
            "gather_stamina_bonus_pct",
        )

        is_tool = item_type == ItemType.gathering_tool or item_type == "gathering_tool"

        if is_tool:
            # tool_category required and must be in enum (Pydantic already validates enum membership)
            if tool_category is None:
                raise ValueError("Категория инструмента обязательна для предмета типа 'gathering_tool'")

            # max_durability >= 1 required
            max_durability = values.get("max_durability")
            if max_durability is None or max_durability < 1:
                raise ValueError("Прочность инструмента сбора должна быть не меньше 1")

            # Each of the 3 bonus fields must be within 0..50 if provided
            for field in bonus_fields:
                val = values.get(field)
                if val is None:
                    continue
                if val < 0 or val > 50:
                    raise ValueError(
                        f"Бонус '{field}' должен быть в диапазоне от 0 до 50"
                    )

            # All equipment-stat modifiers must be null/zero
            for field in GATHERING_TOOL_FORBIDDEN_STAT_FIELDS:
                v = values.get(field)
                if v is not None and v != 0:
                    raise ValueError(
                        "Инструмент сбора не может иметь модификаторы экипировки"
                    )
        else:
            # Non-tool items must NOT set tool_category or any bonus fields
            if tool_category is not None:
                raise ValueError(
                    "Поле 'tool_category' допустимо только для предметов типа 'gathering_tool'"
                )
            for field in bonus_fields:
                v = values.get(field)
                if v is not None and v != 0:
                    raise ValueError(
                        f"Поле '{field}' допустимо только для предметов типа 'gathering_tool'"
                    )

        return values

class Item(ItemBase):
    """
    Схема для возврата предмета из БД,
    добавляет поле id и включает orm_mode.
    """
    id: int
    name: str
    item_type: str
    blueprint_recipe_id: Optional[int] = None
    # Read-only here: set by photo-service on upload, not accepted in ItemCreate
    full_image: Optional[str] = None

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
    res_effects_modifier: Optional[float] = None
    res_physical_modifier: Optional[float] = None
    res_catting_modifier: Optional[float] = None
    res_crushing_modifier: Optional[float] = None
    res_piercing_modifier: Optional[float] = None
    res_magic_modifier: Optional[float] = None
    res_fire_modifier: Optional[float] = None
    res_ice_modifier: Optional[float] = None
    res_watering_modifier: Optional[float] = None
    res_electricity_modifier: Optional[float] = None
    res_wind_modifier: Optional[float] = None
    res_sainting_modifier: Optional[float] = None
    res_damning_modifier: Optional[float] = None
    critical_hit_chance_modifier: Optional[float] = None
    critical_damage_modifier: Optional[float] = None

    health_recovery: Optional[int] = None
    energy_recovery: Optional[int] = None
    mana_recovery: Optional[int] = None
    stamina_recovery: Optional[int] = None

    vul_effects_modifier: Optional[float] = None
    vul_physical_modifier: Optional[float] = None
    vul_catting_modifier: Optional[float] = None
    vul_crushing_modifier: Optional[float] = None
    vul_piercing_modifier: Optional[float] = None
    vul_magic_modifier: Optional[float] = None
    vul_fire_modifier: Optional[float] = None
    vul_ice_modifier: Optional[float] = None
    vul_watering_modifier: Optional[float] = None
    vul_electricity_modifier: Optional[float] = None
    vul_sainting_modifier: Optional[float] = None
    vul_wind_modifier: Optional[float] = None
    vul_damning_modifier: Optional[float] = None

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
    # FEAT-167: effective damage of the item in this slot (weapon slots only;
    # 0.0 for an empty slot, a non-weapon slot and a broken weapon).
    effective_damage: float = 0.0

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
    # Weapons only: which hand. Omitted = the server picks an allowed hand.
    slot_type: Optional[str] = None

    @validator("slot_type")
    def _hand_slot_only(cls, v):
        if v is not None and v not in ("main_weapon", "additional_weapons"):
            raise ValueError("Рука может быть только main_weapon или additional_weapons")
        return v


# -----------------------------------------------------------------------------
# Class / subclass equipment rules
# -----------------------------------------------------------------------------

class EquipmentRuleIn(BaseModel):
    class_id: int
    subclass_key: Optional[constr(regex=r"^[a-z][a-z_]{1,49}$")] = None
    armor_classes: List[ArmorSubclass] = []
    main_hand: List[str] = []
    off_hand: List[str] = []


class EquipmentRuleOut(BaseModel):
    scope_key: str
    class_id: int
    subclass_key: Optional[str] = None
    armor_classes: List[str]
    main_hand: List[str]
    off_hand: List[str]
    updated_at: Optional[datetime] = None


class CharacterEquipmentRules(BaseModel):
    """None in a list = no restriction for that part."""
    restricted: bool
    class_id: Optional[int] = None
    subclass_key: Optional[str] = None
    armor_classes: Optional[List[str]] = None
    main_hand_kinds: Optional[List[str]] = None
    off_hand_kinds: Optional[List[str]] = None
    two_handed_kinds: List[str]


class RevalidateEquipmentResponse(BaseModel):
    character_id: int
    removed_slots: List[str]


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
    source: str = "learned"  # always "learned" since FEAT-165 (kept for compatibility)

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
    # FEAT-164: deprecated and ignored — recipe rarity is derived from the result item
    rarity: Optional[str] = None
    icon: Optional[str] = None
    auto_learn_rank: Optional[int] = None
    xp_reward: Optional[int] = None
    ingredients: List[RecipeIngredientCreate] = []


class RecipeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    profession_id: Optional[int] = None
    required_rank: Optional[int] = None
    result_item_id: Optional[int] = None
    result_quantity: Optional[int] = None
    rarity: Optional[str] = None  # FEAT-164: deprecated and ignored (derived from the result item)
    icon: Optional[str] = None
    auto_learn_rank: Optional[int] = None
    is_active: Optional[bool] = None
    xp_reward: Optional[int] = None
    ingredients: Optional[List[RecipeIngredientCreate]] = None


class CraftRequest(BaseModel):
    recipe_id: int


class CraftResult(BaseModel):
    success: bool
    crafted_item: dict
    consumed_materials: list
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
    whetstone_group: str


class SharpenInfoResponse(BaseModel):
    item_name: str
    item_type: str
    points_spent: int
    points_remaining: int
    sharpen_group: str
    stats: List[SharpenStatInfo] = []
    whetstones: List[SharpenWhetstoneInfo] = []


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
    insertable_type: str  # "gem" (jewelry) or "rune"
    can_insert: bool  # anyone may insert; False for legacy belts
    can_extract: bool  # jeweler -> gems, enchanter -> runes
    extract_preservation_chance: Optional[int] = None
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


# -----------------------------------------------------------------------------
# 13. Refining schemas (FEAT-165)
# -----------------------------------------------------------------------------

class RefiningRuleOut(BaseModel):
    profession_id: int
    profession_slug: str
    profession_name: str
    source_subcategory: str
    result_subcategory: str


class ConversionItemOut(BaseModel):
    id: int
    name: str
    image: Optional[str] = None
    item_rarity: str


class ItemConversionIn(BaseModel):
    profession_id: int
    source_quantity: int
    result_item_id: int
    result_quantity: int

    @validator("profession_id", "result_item_id")
    def _positive_id(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Идентификатор должен быть положительным")
        return v

    @validator("source_quantity", "result_quantity")
    def _quantity_in_bounds(cls, v: int) -> int:
        if not CONVERSION_QTY_MIN <= v <= CONVERSION_QTY_MAX:
            raise ValueError(
                f"Количество должно быть от {CONVERSION_QTY_MIN} до {CONVERSION_QTY_MAX}"
            )
        return v


class ItemConversionsPayload(BaseModel):
    conversions: List[ItemConversionIn] = []


class ItemConversionOut(BaseModel):
    id: int
    profession_id: int
    profession_name: str
    source_quantity: int
    result_item: ConversionItemOut
    result_quantity: int


class ItemConversionsResponse(BaseModel):
    source_item_id: int
    conversions: List[ItemConversionOut] = []


class RefineSourceOut(BaseModel):
    source_item_id: int
    name: str
    image: Optional[str] = None
    item_rarity: str
    owned_quantity: int
    source_quantity: int
    max_batches: int
    result_item: ConversionItemOut
    result_quantity: int
    xp_per_batch: int


class RefineInfoResponse(BaseModel):
    can_refine: bool
    profession_slug: Optional[str] = None
    source_subcategory: Optional[str] = None
    result_subcategory: Optional[str] = None
    double_chance_pct: Optional[int] = None
    sources: List[RefineSourceOut] = []


class RefineRequest(BaseModel):
    source_item_id: int
    quantity: int

    @validator("source_item_id")
    def _positive_source(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Идентификатор предмета должен быть положительным")
        return v

    @validator("quantity")
    def _quantity_in_bounds(cls, v: int) -> int:
        if not 1 <= v <= REFINE_MAX_QUANTITY:
            raise ValueError(f"Количество должно быть от 1 до {REFINE_MAX_QUANTITY}")
        return v


class RefineResult(BaseModel):
    success: bool
    source_item_id: int
    consumed_quantity: int
    leftover_quantity: int
    batches: int
    doubled_batches: int
    result_item: ConversionItemOut
    result_quantity: int
    xp_earned: int
    new_total_xp: int
    rank_up: bool
    new_rank_name: Optional[str] = None
    auto_learned_recipes: List[dict] = []


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


class EatFoodRequest(BaseModel):
    """FEAT-164: eat one food item from the inventory."""
    inventory_item_id: int


class SatietyInfo(BaseModel):
    """Mirror of character-attributes-service SatietyInfo (FEAT-164)."""
    item_id: Optional[int] = None
    source_item_name: Optional[str] = None
    rarity: str
    regen_bonus_percent: int
    modifiers: Dict[str, float] = {}
    started_at: datetime
    expires_at: datetime
    remaining_seconds: int


class EatFoodResponse(BaseModel):
    success: bool
    message: str
    satiety: SatietyInfo


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


# -----------------------------------------------------------------------------
# 17. Auction schemas
# -----------------------------------------------------------------------------

class AuctionListingStatus(str, Enum):
    active = "active"
    sold = "sold"
    expired = "expired"
    cancelled = "cancelled"


class AuctionStorageSource(str, Enum):
    purchase = "purchase"
    expired = "expired"
    cancelled = "cancelled"
    sale_proceeds = "sale_proceeds"
    deposit = "deposit"


# --- Request schemas ---

class AuctionCreateListingRequest(BaseModel):
    character_id: int
    storage_id: int           # auction_storage.id — item from auction storage
    start_price: int          # minimum bid (> 0)
    buyout_price: Optional[int] = None  # optional instant buy price (> start_price)


class AuctionBidRequest(BaseModel):
    character_id: int
    amount: int               # bid amount (> current_bid)


class AuctionBuyoutRequest(BaseModel):
    character_id: int


class AuctionCancelRequest(BaseModel):
    character_id: int


class AuctionClaimRequest(BaseModel):
    character_id: int
    storage_ids: List[int]    # auction_storage.id(s) to claim


# --- Response schemas ---

class AuctionItemInfo(BaseModel):
    id: int
    name: str
    image: Optional[str] = None
    full_image: Optional[str] = None
    item_type: str
    item_rarity: str
    item_level: int
    weapon_subclass: Optional[str] = None
    armor_subclass: Optional[str] = None

    class Config:
        orm_mode = True


class AuctionListingResponse(BaseModel):
    id: int
    seller_character_id: int
    seller_name: str
    item: AuctionItemInfo
    quantity: int
    enhancement_data: Optional[dict] = None
    start_price: int
    buyout_price: Optional[int] = None
    current_bid: int
    current_bidder_id: Optional[int] = None
    current_bidder_name: Optional[str] = None
    status: str
    created_at: str
    expires_at: str
    time_remaining_seconds: int
    bid_count: int


class AuctionListingsPageResponse(BaseModel):
    listings: List[AuctionListingResponse]
    total: int
    page: int
    per_page: int


class AuctionBidResponse(BaseModel):
    listing_id: int
    bid_id: int
    amount: int
    new_gold_balance: int
    message: str


class AuctionBuyoutResponse(BaseModel):
    listing_id: int
    amount: int
    new_gold_balance: int
    message: str


class AuctionCreateListingResponse(BaseModel):
    listing_id: int
    item_name: str
    quantity: int
    start_price: int
    buyout_price: Optional[int] = None
    expires_at: str
    active_listing_count: int
    message: str


class AuctionCancelResponse(BaseModel):
    listing_id: int
    message: str


class AuctionStorageItemResponse(BaseModel):
    id: int
    item: Optional[AuctionItemInfo] = None
    quantity: int
    enhancement_data: Optional[dict] = None
    gold_amount: int
    source: str
    created_at: str


class AuctionStorageResponse(BaseModel):
    items: List[AuctionStorageItemResponse]
    total_gold: int


class AuctionClaimResponse(BaseModel):
    claimed_items: int
    claimed_gold: int
    new_gold_balance: int
    message: str


class AuctionMyListingsResponse(BaseModel):
    active: List[AuctionListingResponse]
    completed: List[AuctionListingResponse]


# --- Deposit schemas ---

class AuctionDepositRequest(BaseModel):
    character_id: int
    inventory_item_id: int    # character_inventory.id
    quantity: int = 1


class AuctionDepositResponse(BaseModel):
    storage_id: int
    item_name: str
    quantity: int
    message: str


# -----------------------------------------------------------------------------
# 19. Gathering schemas
# -----------------------------------------------------------------------------


class GatheringRankBonuses(BaseModel):
    double_chance_bonus: float
    speed_bonus_pct: float
    stamina_bonus_pct: float


class GatheringNextRank(BaseModel):
    rank_number: int
    required_experience: int
    double_chance_bonus: float
    speed_bonus_pct: float
    stamina_bonus_pct: float


class GatheringSkillOut(BaseModel):
    skill_id: int
    slug: str
    name: str
    category: str
    current_rank: int
    experience: int
    experience_total: int
    is_max_rank: bool
    current_rank_bonuses: GatheringRankBonuses
    next_rank: Optional[GatheringNextRank] = None
    next_rank_bonuses: Optional[GatheringRankBonuses] = None
    experience_to_next: Optional[int] = None


class CharacterGatheringSkillsResponse(BaseModel):
    character_id: int
    skills: List[GatheringSkillOut] = []


class FreeSlotsCheckResponse(BaseModel):
    free_slot_count: int
    is_full: bool


GATHERING_SKILL_SLUGS = frozenset({"mining", "herbalism", "woodcutting", "foraging"})


class GatheringAwardRequest(BaseModel):
    """Тело запроса internal-эндпоинта /gathering/award.

    Все количества — неотрицательные. Если `tool_inventory_item_id` не задан,
    `tool_durability_to_consume` обязан быть 0; при наличии инструмента —
    > 0.
    """

    skill_slug: str
    result_item_id: int
    result_quantity: int
    xp_to_add: int
    tool_inventory_item_id: Optional[int] = None
    tool_durability_to_consume: int = 0

    @validator("skill_slug")
    def _slug_in_set(cls, v: str) -> str:
        if v not in GATHERING_SKILL_SLUGS:
            raise ValueError("Неизвестный навык добычи")
        return v

    @validator("result_quantity")
    def _quantity_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("result_quantity должен быть >= 0")
        return v

    @validator("xp_to_add")
    def _xp_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("xp_to_add должен быть >= 0")
        return v

    @validator("tool_durability_to_consume")
    def _dur_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("tool_durability_to_consume должен быть >= 0")
        return v

    @root_validator
    def _tool_durability_consistency(cls, values: dict) -> dict:
        tool_id = values.get("tool_inventory_item_id")
        consume = values.get("tool_durability_to_consume", 0)
        if tool_id is None and consume != 0:
            raise ValueError(
                "tool_durability_to_consume должен быть 0, если инструмент не указан"
            )
        if tool_id is not None and consume <= 0:
            raise ValueError(
                "tool_durability_to_consume должен быть > 0, если указан инструмент"
            )
        return values


class GatheringAwardResponse(BaseModel):
    """Ответ internal-эндпоинта /gathering/award.

    `tool_durability_remaining` равен None, если инструмент не использовался.
    `new_rank_bonuses` присутствует только если в этом вызове произошёл rank-up.
    """

    items_added: bool
    actual_quantity_added: int
    inventory_full: bool
    tool_durability_remaining: Optional[int] = None
    tool_broke: bool
    xp_awarded: int
    current_rank: int
    current_experience: int
    rank_up: bool
    new_rank_bonuses: Optional[GatheringRankBonuses] = None


# -----------------------------------------------------------------------------
# 18. NPC Equipment schemas
# -----------------------------------------------------------------------------

class AdminNpcEquipRequest(BaseModel):
    """Запрос на экипировку предмета NPC (admin-only)."""
    slot_type: str
    item_id: int


# -----------------------------------------------------------------------------
# Bulk item resolve (FEAT-154) — compact card used by the character wizard
# -----------------------------------------------------------------------------

class ItemBulkResponse(BaseModel):
    """
    Компактная карточка предмета для массового резолва по списку id.
    Поля переименованы под контракт фронтенда (§3.1 FEAT-154).
    """
    id: int
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    rarity: Optional[str] = None
    type: Optional[str] = None

    class Config:
        orm_mode = True
