from inspect import classify_class_attrs
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field, root_validator, validator
from datetime import datetime

# Базовая схема для заявки на создание персонажа
# Максимальная длина имени персонажа (правило 32, по образцу 30b).
# Колонка character_requests.name — String(20). Проверка длины вынесена из
# Pydantic-схемы в доменную валидацию (crud.validate_character_request_payload),
# чтобы игрок получал 400 с русским сообщением, а не стандартный 422 от FastAPI.
MAX_CHARACTER_NAME_LENGTH = 20


class CharacterRequestBase(BaseModel):
    name: str
    id_subrace: int
    biography: Optional[str]
    personality: Optional[str]
    appearance: str
    background: Optional[str]
    age: Optional[int]
    weight: Optional[str]
    height: Optional[str]
    sex: Optional[str]
    id_class: int
    id_race: int
    user_id: Optional[int]
    # FEAT-154 (D5): аватар больше не обязателен — загрузка может не состояться,
    # это не должно блокировать подачу заявки.
    avatar: Optional[str] = None
    # FEAT-154: новые поля заявки, все необязательные (R3)
    origin_id: Optional[int] = None
    start_location_id: Optional[int] = None
    skitaltsy_since_year: Optional[int] = None
    skitaltsy_since_segment: Optional[int] = None

# Схема для создания заявки на персонажа
class CharacterRequestCreate(CharacterRequestBase):
    pass

# Схема для возврата заявки
class CharacterRequest(CharacterRequestBase):
    id: int
    status: str
    # FEAT-154: раньше эти поля не возвращались, из-за чего клиент не узнавал
    # ни времени подачи, ни типа заявки, ни причины отказа.
    created_at: Optional[datetime] = None
    request_type: Optional[str] = None
    character_id: Optional[int] = None
    rejection_reason: Optional[str] = None

    class Config:
        orm_mode = True

# Максимальная длина причины отклонения заявки (правило 30b).
# Проверка вынесена из Pydantic-валидатора в эндпоинт, чтобы игрок/модератор
# получал 400 с русским сообщением, а не стандартный 422 от FastAPI.
MAX_REJECTION_REASON_LENGTH = 1000


# Схема тела запроса на отклонение заявки (тело необязательно)
class CharacterRequestReject(BaseModel):
    reason: Optional[str] = None

    @validator("reason")
    def validate_reason(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        # Длина НЕ проверяется здесь намеренно: см. MAX_REJECTION_REASON_LENGTH.
        return v

    class Config:
        orm_mode = True


# ===== FEAT-154: заявки игрока и публичный паспорт персонажа =====

class ClassResponse(BaseModel):
    """Игровой класс. Публичный справочник для мастера создания персонажа."""

    id_class: int
    name: str
    description: Optional[str] = None

    class Config:
        orm_mode = True


class CharacterRequestMy(BaseModel):
    """Заявка текущего пользователя (GET /characters/requests/my, PUT /characters/requests/{id})."""

    id: int
    status: str
    request_type: Optional[str] = None
    created_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None

    name: Optional[str] = None
    id_race: Optional[int] = None
    id_subrace: Optional[int] = None
    id_class: Optional[int] = None
    race_name: Optional[str] = None
    subrace_name: Optional[str] = None
    class_name: Optional[str] = None

    avatar: Optional[str] = None
    origin_id: Optional[int] = None
    start_location_id: Optional[int] = None

    biography: Optional[str] = None
    personality: Optional[str] = None
    appearance: Optional[str] = None
    background: Optional[str] = None

    sex: Optional[str] = None
    age: Optional[int] = None
    weight: Optional[str] = None
    height: Optional[str] = None

    skitaltsy_since_year: Optional[int] = None
    skitaltsy_since_segment: Optional[int] = None
    character_id: Optional[int] = None


class CharacterRequestUpdate(CharacterRequestBase):
    """
    Тело PUT /characters/requests/{id} — то же, что и при создании, но без user_id:
    владелец определяется по токену, подменить его нельзя.
    """

    user_id: Optional[int] = None


class CharacterPublicStrangerResponse(BaseModel):
    """Паспорт персонажа так, как его видит ЧУЖОЙ (FEAT-171 §3.4 C3, стиль A).

    Полная схема `CharacterPublicResponse` наследуется от этой и лишь добавляет
    приватные поля — второго списка полей нет (§3.2 D5), поэтому публичная форма
    не может отстать от полной.
    """

    id: int
    name: str
    avatar: Optional[str] = None
    level: Optional[int] = None

    id_race: Optional[int] = None
    id_subrace: Optional[int] = None
    id_class: Optional[int] = None
    race_name: Optional[str] = None
    subrace_name: Optional[str] = None
    class_name: Optional[str] = None
    subrace_image: Optional[str] = None
    subrace_distinctive_features: Optional[str] = None

    sex: Optional[str] = None
    age: Optional[int] = None
    weight: Optional[str] = None
    height: Optional[str] = None

    appearance: Optional[str] = None
    biography: Optional[str] = None
    personality: Optional[str] = None
    background: Optional[str] = None

    origin_id: Optional[int] = None
    registered_at: Optional[datetime] = None
    skitaltsy_since_year: Optional[int] = None
    skitaltsy_since_segment: Optional[int] = None
    current_location_id: Optional[int] = None

    is_npc: bool = False
    user_id: Optional[int] = None
    username: Optional[str] = None

    # Замороженный слепок выданного набора (rule 12d / D17). Если слепка нет —
    # здесь живой resolve, а granted_kit_is_snapshot = False (D18).
    # FEAT-171 §3.4 C3 / D4 архитектуры: набор остаётся ПУБЛИЧНЫМ — это запись
    # о вступлении (список id предметов), а не характеристики.
    granted_kit: Optional[Dict[str, Any]] = None
    granted_kit_is_snapshot: bool = False

    # FEAT-199: публичная слава — только название ступени, без числа
    fame_tier_code: str = "nameless"
    fame_tier_name: str = "Безвестный"


class CharacterPublicResponse(CharacterPublicStrangerResponse):
    """Полный паспорт: то же плюс приватные стартовые характеристики.

    Отдаётся только владельцу, админу/модератору с `characters:read` и на NPC
    (у него нет приватного слоя). Для чужого используется базовая схема, и тогда
    этих ключей в JSON просто НЕТ (§3.2 D4).
    """

    # FEAT-155: ЗАМОРОЖЕННЫЕ стартовые характеристики — то, с чем персонаж
    # вступил в Скитальцы (правило 27, по образцу granted_kit / правило 12d).
    # Текущие статы здесь НЕ отдаются намеренно: паспорт это запись о вступлении,
    # а актуальный билд игрока не должен утекать в чужую анкету.
    # None -> блок «Оценка при вступлении» просто не рисуется.
    starting_attributes: Optional[Dict[str, int]] = None
    # True — слепок, снятый при одобрении. False — реконструкция из пресета
    # подрасы для персонажа, созданного до FEAT-155 (по образцу D18).
    starting_attributes_is_snapshot: bool = False


# Схема для создания персонажа (эквивалент CharacterCreate)
class CharacterCreate(BaseModel):
    name: str
    id_subrace: int
    biography: str
    personality: str
    id_class: int
    id_item_inventory: int
    id_skill_inventory: int
    id_attributes: int
    currency_balance: int = 0
    appearance: str
    background:str
    age: int
    weight: str
    height: str
    id_race: int
    class Config:
        orm_mode = True

# Схема для обновления персонажа
class CharacterUpdate(BaseModel):
    name: str = None
    id_subrace: int = None
    biography: str = None
    personality: str = None
    id_class: int = None
    id_item_inventory: int = None
    id_skill_inventory: int = None
    id_attributes: int = None
    currency_balance: int = None
    current_title_id: Optional[int] = None

    class Config:
        orm_mode = True

class CharacterBase(BaseModel):
    name: str
    id_subrace: int
    biography: str
    personality: str
    id_class: int
    id_item_inventory: int
    id_skill_inventory: int
    id_attributes: int
    currency_balance: int = 0
    appearance: str
    background: str
    age: int
    weight: str
    height: str
    id_race: int

    class Config:
        orm_mode = True

class CharacterTitle(BaseModel):
    character_id: int
    title_id: int

    class Config:
        orm_mode = True


class TitleBase(BaseModel):
    name: str
    description: Optional[str] = None

class TitleCreate(TitleBase):
    pass

class Title(TitleBase):
    id_title: int

    class Config:
        orm_mode = True


# ========== Extended Title Schemas (FEAT-080) ==========

class TitleCondition(BaseModel):
    type: str
    stat: Optional[str] = None
    operator: str = ">="
    value: Any = None


class TitleCreateFull(BaseModel):
    name: str
    description: Optional[str] = None
    rarity: str = "common"
    conditions: Optional[List[TitleCondition]] = None
    icon: Optional[str] = None
    sort_order: int = 0
    reward_passive_exp: int = 0
    reward_active_exp: int = 0

    @validator("rarity")
    def validate_rarity(cls, v):
        if v not in ("common", "rare", "legendary"):
            raise ValueError("Редкость должна быть common, rare или legendary")
        return v


class TitleUpdateFull(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    rarity: Optional[str] = None
    conditions: Optional[List[TitleCondition]] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    reward_passive_exp: Optional[int] = None
    reward_active_exp: Optional[int] = None

    @validator("rarity")
    def validate_rarity(cls, v):
        if v is not None and v not in ("common", "rare", "legendary"):
            raise ValueError("Редкость должна быть common, rare или legendary")
        return v


class TitleAdminResponse(BaseModel):
    id_title: int
    name: str
    description: Optional[str] = None
    rarity: str
    conditions: Optional[List] = None
    icon: Optional[str] = None
    sort_order: int
    is_active: bool
    reward_passive_exp: int = 0
    reward_active_exp: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    holders_count: int = 0

    class Config:
        orm_mode = True


class TitleAdminListResponse(BaseModel):
    items: List[TitleAdminResponse]
    total: int
    page: int
    per_page: int


class CharacterTitleResponse(BaseModel):
    id_title: int
    name: str
    description: Optional[str] = None
    rarity: str = "common"
    conditions: Optional[List] = None
    icon: Optional[str] = None
    reward_passive_exp: int = 0
    reward_active_exp: int = 0
    is_unlocked: bool = False
    unlocked_at: Optional[datetime] = None
    is_custom: bool = False
    progress: Optional[Dict] = None


class TitleGrantRequest(BaseModel):
    character_id: int
    title_id: int


class LevelProgress(BaseModel):
    # Earned within the current level (never below 0) and the experience left to the next one.
    current_exp_in_level: int
    exp_to_next_level: int
    progress_fraction: float
    # The whole step from this level to the next (the bar's 100%); 0 past the table's last level.
    exp_for_level: int = 0
    next_level: Optional[int] = None
    # No threshold above this level: the table's last level is reached.
    max_level: bool = False
    # All the experience the character has ever earned (the profile shows it on a click).
    total_exp: int = 0

class Attribute(BaseModel):
    current: int
    max: int

class FullProfileResponse(BaseModel):
    name: str
    currency_balance: int
    level: int
    stat_points: int
    level_progress: LevelProgress
    attributes: Dict[str, Attribute]
    active_title: Optional[str]
    active_title_rarity: Optional[str] = None
    avatar: Optional[str]


class PublicProfileResponse(BaseModel):
    """Витрина персонажа для чужого (FEAT-171 §3.4 C1, стиль A).

    Ни денег, ни очков характеристик, ни прогресса уровня, ни текущих
    hp/mana/energy/stamina: эти ключи в ответе ОТСУТСТВУЮТ, а не равны null.
    Строится единственной проекцией `public_profile(full)` (§3.2 D5).
    """

    id: int
    name: str
    level: int
    active_title: Optional[str] = None
    active_title_rarity: Optional[str] = None
    avatar: Optional[str] = None


def public_profile(character_id: int, full: FullProfileResponse) -> PublicProfileResponse:
    """Единственная проекция полного профиля в публичный (§3.2 D5)."""
    return PublicProfileResponse(
        id=character_id,
        name=full.name,
        level=full.level,
        active_title=full.active_title,
        active_title_rarity=full.active_title_rarity,
        avatar=full.avatar,
    )


class CharacterBaseInfoResponse(BaseModel):
    id: int
    id_class: int
    id_race: int
    id_subrace: int
    level: int

    class Config:
        orm_mode = True

class PlayerInLocation(BaseModel):
    id: int
    name: str
    avatar: Optional[str] = None
    level: int = 1
    class_name: Optional[str] = None
    race_name: Optional[str] = None
    character_title: Optional[str] = ""
    character_title_rarity: Optional[str] = None
    user_id: Optional[int] = None
    # FEAT-180 stage 7: inside a house of this location ({house_id, house_name}), the room not told.
    in_house: Optional[dict] = None

class CharacterProfileResponse(BaseModel):
        character_photo: str
        character_title: str
        character_title_rarity: Optional[str] = None
        character_name: str
        character_level: Optional[int] = None
        # Board miniatures (FEAT-175): 1 warrior, 2 rogue, 3 mage.
        character_class_id: Optional[int] = None
        user_id: Optional[int] = None
        user_nickname: Optional[str] = None
        current_location_id: Optional[int] = None
        travel_cooldown_until: Optional[datetime] = None
        # FEAT-175: {"locked", "reason": "dungeon"|"unconscious"|null, "until", "dungeon_session_id"}
        activity_lock: Optional[dict] = None

        class Config:
            orm_mode = True

class CharacterShort(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True


class CharacterPublicListItem(BaseModel):
    id: int
    name: str
    avatar: Optional[str] = None
    level: int = 1
    id_class: int
    id_race: int
    id_subrace: int
    biography: Optional[str] = None
    personality: Optional[str] = None
    appearance: Optional[str] = None
    background: Optional[str] = None
    sex: Optional[str] = None
    age: Optional[int] = None
    is_npc: bool = False
    user_id: Optional[int] = None
    username: Optional[str] = None
    class_name: Optional[str] = None
    race_name: Optional[str] = None
    subrace_name: Optional[str] = None


class ClaimRequestCreate(BaseModel):
    character_id: int


class ClaimRequestResponse(BaseModel):
    id: int
    character_id: int
    user_id: int
    status: str
    request_type: str
    name: str
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class CharacterCountResponse(BaseModel):
    count: int
    # None = лимита нет (settings.MAX_CHARACTERS_PER_USER <= 0, значение по умолчанию)
    limit: Optional[int] = None


# Starter Kit schemas
class StarterKitItem(BaseModel):
    item_id: int
    quantity: int = 1


class StarterKitSkill(BaseModel):
    skill_id: int


class StarterKitResponse(BaseModel):
    id: int
    class_id: int
    # FEAT-154 (D16): 0 = набор класса по умолчанию, >0 = переопределение под происхождение.
    # Ключ аддитивный — старые клиенты его просто игнорируют.
    origin_id: int = 0
    items: List[StarterKitItem]
    skills: List[StarterKitSkill]
    currency_amount: int

    class Config:
        orm_mode = True


class StarterKitUpdate(BaseModel):
    items: List[StarterKitItem] = []
    skills: List[StarterKitSkill] = []
    currency_amount: int = 0


class StarterKitResolved(BaseModel):
    """Результат crud.resolve_starter_kit: точная пара -> дефолт класса -> пусто."""

    class_id: int
    origin_id: int
    resolved_from: str  # "exact" | "class_default" | "none"
    items: List[StarterKitItem] = []
    skills: List[StarterKitSkill] = []
    currency_amount: int = 0


class StarterKitCoverageClass(BaseModel):
    id_class: int
    name: str
    has_default: bool


class StarterKitCoverageOverride(BaseModel):
    class_id: int
    origin_id: int


class StarterKitCoverageResponse(BaseModel):
    classes: List[StarterKitCoverageClass] = []
    overrides: List[StarterKitCoverageOverride] = []


# Admin character management schemas
class AdminCharacterListItem(BaseModel):
    id: int
    name: str
    level: int
    id_race: int
    id_class: int
    id_subrace: int
    user_id: Optional[int]
    avatar: Optional[str]
    currency_balance: int
    stat_points: int
    current_location_id: Optional[int]

    class Config:
        orm_mode = True


class AdminCharacterListResponse(BaseModel):
    items: List[AdminCharacterListItem]
    total: int
    page: int
    page_size: int


class AdminCharacterUpdate(BaseModel):
    level: Optional[int] = None
    stat_points: Optional[int] = None
    currency_balance: Optional[int] = None


# ========== Stat Preset Schema ==========

STAT_PRESET_KEYS = [
    "strength", "agility", "intelligence", "endurance",
    "health", "energy", "mana", "stamina",
    "charisma", "luck", "stealth",
]


class StatPreset(BaseModel):
    strength: int = 0
    agility: int = 0
    intelligence: int = 0
    endurance: int = 0
    health: int = 0
    energy: int = 0
    mana: int = 0
    stamina: int = 0
    charisma: int = 0
    luck: int = 0
    stealth: int = 0                            # FEAT-201: optional, existing presets stay valid

    @validator(*STAT_PRESET_KEYS)
    def values_non_negative(cls, v):
        if v < 0:
            raise ValueError("Значение стата не может быть отрицательным")
        return v

    @root_validator(skip_on_failure=True)
    def preset_sum_must_be_100(cls, values):
        # FEAT-201: a root validator sums EVERY key once (the old field validator on "luck" depended on the key order)
        total = sum(int(values.get(key) or 0) for key in STAT_PRESET_KEYS)
        if total != 100:
            raise ValueError(f"Сумма пресета должна быть равна 100, получено {total}")
        return values


# ========== Race Schemas ==========

class RaceCreate(BaseModel):
    name: str
    description: Optional[str] = None

class RaceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class RaceResponse(BaseModel):
    id_race: int
    name: str
    description: Optional[str] = None
    image: Optional[str] = None

    class Config:
        orm_mode = True


# ========== Subrace Schemas ==========

class SubraceCreate(BaseModel):
    id_race: int
    name: str
    description: Optional[str] = None
    stat_preset: StatPreset
    distinctive_features: Optional[str] = None
    height_min: Optional[int] = None
    height_max: Optional[int] = None
    typical_origin_ids: Optional[List[int]] = None

class SubraceUpdate(BaseModel):
    id_race: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    stat_preset: Optional[StatPreset] = None
    distinctive_features: Optional[str] = None
    height_min: Optional[int] = None
    height_max: Optional[int] = None
    typical_origin_ids: Optional[List[int]] = None

class SubraceResponse(BaseModel):
    id_subrace: int
    id_race: int
    name: str
    description: Optional[str] = None
    stat_preset: Optional[Dict] = None
    image: Optional[str] = None
    distinctive_features: Optional[str] = None
    height_min: Optional[int] = None
    height_max: Optional[int] = None
    typical_origin_ids: Optional[List[int]] = None

    class Config:
        orm_mode = True


# ========== Race with Subraces (for public endpoint) ==========

class SubraceWithPreset(BaseModel):
    id_subrace: int
    # Родительская раса. Раньше поля здесь не было, и потребители, читавшие
    # `subrace.id_race` из этого ответа, молча получали undefined.
    id_race: int
    name: str
    description: Optional[str] = None
    stat_preset: Optional[Dict] = None
    image: Optional[str] = None
    distinctive_features: Optional[str] = None
    height_min: Optional[int] = None
    height_max: Optional[int] = None
    typical_origin_ids: Optional[List[int]] = None

    class Config:
        orm_mode = True

class RaceWithSubraces(BaseModel):
    id_race: int
    name: str
    description: Optional[str] = None
    image: Optional[str] = None
    subraces: List[SubraceWithPreset] = []

    class Config:
        orm_mode = True


# ========== NPC Schemas ==========

# FEAT-197: reputation gate / kill-weight fields (shared by the NPC, bank and teleport admin schemas)
import reputation_core as _rep_core  # noqa: E402

REPUTATION_POINTS_LIMIT = 1000


def _reputation_tier_code(v):
    """'' / None -> None (no gate); a fixed tier code -> itself; anything else -> 422."""
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValueError("Неизвестная ступень репутации")
    v = v.strip()
    if not v:
        return None
    if v not in _rep_core.TIER_CODES:
        raise ValueError("Неизвестная ступень репутации")
    return v


def _reputation_kill_points(v):
    if v is None or v == "":
        return None
    v = int(v)
    if not -REPUTATION_POINTS_LIMIT <= v <= REPUTATION_POINTS_LIMIT:
        raise ValueError("Репутация за убийство — от −1000 до 1000")
    return v


class NpcCreate(BaseModel):
    name: str
    id_class: int
    id_race: int
    id_subrace: int
    npc_role: Optional[str] = None
    biography: Optional[str] = None
    personality: Optional[str] = None
    appearance: str = ""
    background: Optional[str] = None
    sex: Optional[str] = "genderless"
    age: Optional[int] = None
    weight: Optional[str] = None
    height: Optional[str] = None
    avatar: str = ""
    level: int = 1
    stat_points: int = 0
    currency_balance: int = 0
    current_location_id: Optional[int] = None
    reputation_min_tier: Optional[str] = None       # FEAT-197 NPC gate (tier code, null = none)
    reputation_kill_points: Optional[int] = None    # FEAT-197 per-NPC kill weight (null = role weight)

    _rep_tier = validator("reputation_min_tier", pre=True, allow_reuse=True)(_reputation_tier_code)
    _rep_kill = validator("reputation_kill_points", pre=True, allow_reuse=True)(_reputation_kill_points)


class NpcUpdate(BaseModel):
    name: Optional[str] = None
    id_class: Optional[int] = None
    id_race: Optional[int] = None
    id_subrace: Optional[int] = None
    npc_role: Optional[str] = None
    biography: Optional[str] = None
    personality: Optional[str] = None
    appearance: Optional[str] = None
    background: Optional[str] = None
    sex: Optional[str] = None
    age: Optional[int] = None
    weight: Optional[str] = None
    height: Optional[str] = None
    avatar: Optional[str] = None
    level: Optional[int] = None
    stat_points: Optional[int] = None
    currency_balance: Optional[int] = None
    current_location_id: Optional[int] = None
    npc_status: Optional[str] = None
    reputation_min_tier: Optional[str] = None       # FEAT-197 NPC gate (tier code, null = none)
    reputation_kill_points: Optional[int] = None    # FEAT-197 per-NPC kill weight (null = role weight)

    _rep_tier = validator("reputation_min_tier", pre=True, allow_reuse=True)(_reputation_tier_code)
    _rep_kill = validator("reputation_kill_points", pre=True, allow_reuse=True)(_reputation_kill_points)

    @validator("npc_status")
    def validate_npc_status(cls, v):
        if v is not None and v not in ("alive", "dead"):
            raise ValueError("Статус NPC должен быть alive или dead")
        return v


class NpcListItem(BaseModel):
    id: int
    name: str
    level: int
    id_race: int
    id_class: int
    npc_role: Optional[str] = None
    avatar: Optional[str] = None
    current_location_id: Optional[int] = None
    npc_status: Optional[str] = None

    class Config:
        orm_mode = True


class NpcListResponse(BaseModel):
    items: List[NpcListItem]
    total: int
    page: int
    page_size: int


class NpcInLocation(BaseModel):
    id: int
    name: str
    avatar: Optional[str] = None
    level: int = 1
    class_name: Optional[str] = None
    race_name: Optional[str] = None
    npc_role: Optional[str] = None
    # FEAT-204: a patrolling guard's departure bucket ('soon' | 'short' | 'long'); None = not patrolling
    patrol_departure: Optional[str] = None


# ========== Mob Template Schemas ==========

class MobTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    tier: str = "normal"
    level: int = 1
    avatar: Optional[str] = None
    id_race: int = 1
    id_subrace: int = 1
    id_class: int
    sex: Optional[str] = "genderless"
    base_attributes: Optional[Dict] = None
    xp_reward: int = 0
    gold_reward: int = 0
    respawn_enabled: bool = False
    respawn_seconds: Optional[int] = None

    @validator("tier")
    def validate_tier(cls, v):
        if v not in ("normal", "elite", "boss"):
            raise ValueError("Тип моба должен быть normal, elite или boss")
        return v

    @validator("level")
    def validate_level(cls, v):
        if v < 1:
            raise ValueError("Уровень моба должен быть >= 1")
        return v

    @validator("xp_reward", "gold_reward")
    def validate_rewards(cls, v):
        if v < 0:
            raise ValueError("Награда не может быть отрицательной")
        return v


class MobTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tier: Optional[str] = None
    level: Optional[int] = None
    avatar: Optional[str] = None
    id_race: Optional[int] = None
    id_subrace: Optional[int] = None
    id_class: Optional[int] = None
    sex: Optional[str] = None
    base_attributes: Optional[Dict] = None
    xp_reward: Optional[int] = None
    gold_reward: Optional[int] = None
    respawn_enabled: Optional[bool] = None
    respawn_seconds: Optional[int] = None

    @validator("tier")
    def validate_tier(cls, v):
        if v is not None and v not in ("normal", "elite", "boss"):
            raise ValueError("Тип моба должен быть normal, elite или boss")
        return v

    @validator("level")
    def validate_level(cls, v):
        if v is not None and v < 1:
            raise ValueError("Уровень моба должен быть >= 1")
        return v

    @validator("xp_reward", "gold_reward")
    def validate_rewards(cls, v):
        if v is not None and v < 0:
            raise ValueError("Награда не может быть отрицательной")
        return v


class MobTemplateResponse(BaseModel):
    id: int
    name: str
    tier: str
    level: int
    avatar: Optional[str] = None
    xp_reward: int
    gold_reward: int
    respawn_enabled: bool
    respawn_seconds: Optional[int] = None

    class Config:
        orm_mode = True


class MobTemplateListResponse(BaseModel):
    items: List[MobTemplateResponse]
    total: int
    page: int
    page_size: int


class MobSkillResponse(BaseModel):
    id: int
    skill_id: int

    class Config:
        orm_mode = True


class MobLootEntryResponse(BaseModel):
    id: int
    item_id: int
    drop_chance: float
    min_quantity: int
    max_quantity: int

    class Config:
        orm_mode = True


class MobSpawnResponse(BaseModel):
    id: int
    location_id: int
    spawn_chance: float
    max_active: int
    is_enabled: bool

    class Config:
        orm_mode = True


class MobTemplateDetailResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    tier: str
    level: int
    avatar: Optional[str] = None
    id_race: int
    id_subrace: int
    id_class: int
    sex: Optional[str] = None
    base_attributes: Optional[Dict] = None
    xp_reward: int
    gold_reward: int
    respawn_enabled: bool
    respawn_seconds: Optional[int] = None
    skills: List[MobSkillResponse] = []
    loot_entries: List[MobLootEntryResponse] = []
    spawn_locations: List[MobSpawnResponse] = []

    class Config:
        orm_mode = True


class MobSkillsUpdate(BaseModel):
    skill_ids: List[int]


class MobLootEntry(BaseModel):
    item_id: int
    drop_chance: float
    min_quantity: int = 1
    max_quantity: int = 1

    @validator("drop_chance")
    def validate_drop_chance(cls, v):
        if v < 0.0 or v > 100.0:
            raise ValueError("Шанс дропа должен быть от 0 до 100")
        return v

    @validator("min_quantity", "max_quantity")
    def validate_quantity(cls, v):
        if v < 1:
            raise ValueError("Количество должно быть >= 1")
        return v


class MobLootUpdate(BaseModel):
    entries: List[MobLootEntry]


class MobSpawnEntry(BaseModel):
    location_id: int
    spawn_chance: float = 5.0
    max_active: int = 1
    is_enabled: bool = True

    @validator("spawn_chance")
    def validate_spawn_chance(cls, v):
        if v < 0.0 or v > 100.0:
            raise ValueError("Шанс спавна должен быть от 0 до 100")
        return v

    @validator("max_active")
    def validate_max_active(cls, v):
        if v < 1:
            raise ValueError("Максимальное количество должно быть >= 1")
        return v


class MobSpawnUpdate(BaseModel):
    spawns: List[MobSpawnEntry]


class ActiveMobResponse(BaseModel):
    id: int
    mob_template_id: int
    character_id: int
    location_id: int
    status: str
    battle_id: Optional[int] = None
    spawn_type: str
    spawned_at: Optional[datetime] = None
    killed_at: Optional[datetime] = None
    respawn_at: Optional[datetime] = None
    template_name: Optional[str] = None
    template_tier: Optional[str] = None
    template_level: Optional[int] = None

    class Config:
        orm_mode = True


class ActiveMobListResponse(BaseModel):
    items: List[ActiveMobResponse]
    total: int
    page: int
    page_size: int


class ManualSpawnRequest(BaseModel):
    mob_template_id: int
    location_id: int


class TrySpawnRequest(BaseModel):
    location_id: int
    character_id: int


class TrySpawnResponse(BaseModel):
    spawned: bool
    mob: Optional[Dict] = None


class SpawnDungeonMobsRequest(BaseModel):
    mob_template_ids: List[int]
    location_id: int
    # FEAT-175: dungeon `mob_multiplier`, scales the mobs' base stats.
    stat_multiplier: float = 1.0

    @validator("stat_multiplier")
    def validate_stat_multiplier(cls, v):
        if v <= 0 or v > 10:
            raise ValueError("stat_multiplier должен быть в диапазоне (0, 10]")
        return v


class DespawnDungeonMobsRequest(BaseModel):
    character_ids: List[int]


class ActivityLockResponse(BaseModel):
    locked: bool
    reason: Optional[str] = None
    until: Optional[str] = None
    dungeon_session_id: Optional[int] = None
    law_encounter_id: Optional[int] = None      # FEAT-198: reason "law_encounter"


class DungeonLockRequest(BaseModel):
    character_ids: List[int]
    session_id: int


class KnockoutRequest(BaseModel):
    character_ids: List[int]
    seconds: int
    # Only clear a dungeon lock that belongs to this session (None = any).
    session_id: Optional[int] = None
    # Put the characters back to this location if they are elsewhere.
    return_location_id: Optional[int] = None

    @validator("seconds")
    def validate_seconds(cls, v):
        if v <= 0 or v > 7 * 24 * 3600:
            raise ValueError("seconds должен быть в диапазоне (0, 604800]")
        return v


class SpawnDungeonMobsResponse(BaseModel):
    character_ids: List[int]


class DeductGoldRequest(BaseModel):
    character_id: int
    amount: int
    # FEAT-181 C3 (optional, backward compatible): where the money goes and replay protection.
    location_id: Optional[int] = None
    op_type: str = "dungeon_expense"
    idempotency_key: Optional[str] = Field(None, min_length=1, max_length=128)

    @validator("amount")
    def validate_positive(cls, v):
        if v <= 0:
            raise ValueError("amount должен быть положительным числом")
        return v

    @validator("op_type")
    def validate_op_type(cls, v):
        from crud import DEDUCT_GOLD_OP_TYPES
        if v not in DEDUCT_GOLD_OP_TYPES:
            raise ValueError("Недопустимый тип операции")
        return v


class DeductGoldResponse(BaseModel):
    ok: bool
    new_balance: int
    duplicate: bool = False


class MobInLocation(BaseModel):
    active_mob_id: int
    character_id: int
    name: str
    level: int
    tier: str
    avatar: Optional[str] = None
    status: str
    # FEAT-152: last persisted HP from the shared character_attributes table.
    # None when the attributes row is missing (frontend hides the HP bar).
    current_hp: Optional[int] = None
    max_hp: Optional[int] = None


# ============================================================
# Mob Packs (FEAT-147)
# ============================================================

class MobPackMemberInput(BaseModel):
    mob_template_id: int
    quantity: int = 1

    @validator("quantity")
    def validate_quantity(cls, v):
        if v < 1 or v > 50:
            raise ValueError("Количество мобов в стае должно быть от 1 до 50")
        return v


class MobPackMemberResponse(BaseModel):
    mob_template_id: int
    quantity: int
    template_name: Optional[str] = None
    template_tier: Optional[str] = None
    template_level: Optional[int] = None
    template_avatar: Optional[str] = None


class MobPackCreate(BaseModel):
    name: str
    description: Optional[str] = None
    avatar: Optional[str] = None
    respawn_enabled: bool = False
    respawn_seconds: Optional[int] = None
    members: List[MobPackMemberInput] = []


class MobPackUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    avatar: Optional[str] = None
    respawn_enabled: Optional[bool] = None
    respawn_seconds: Optional[int] = None
    members: Optional[List[MobPackMemberInput]] = None


class MobPackListItem(BaseModel):
    id: int
    name: str
    avatar: Optional[str] = None
    respawn_enabled: bool
    respawn_seconds: Optional[int] = None
    member_count: int = 0
    total_mobs: int = 0


class MobPackListResponse(BaseModel):
    items: List[MobPackListItem]
    total: int
    page: int
    page_size: int


class MobPackDetailResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    avatar: Optional[str] = None
    respawn_enabled: bool
    respawn_seconds: Optional[int] = None
    members: List[MobPackMemberResponse] = []


class PlacePackRequest(BaseModel):
    pack_id: int
    location_id: int


class ActiveMobPackResponse(BaseModel):
    id: int
    pack_id: int
    location_id: int
    status: str
    pack_name: Optional[str] = None
    alive_count: int = 0
    total_count: int = 0
    spawned_at: Optional[datetime] = None
    killed_at: Optional[datetime] = None
    respawn_at: Optional[datetime] = None


class ActiveMobPackListResponse(BaseModel):
    items: List[ActiveMobPackResponse]
    total: int
    page: int
    page_size: int


class PackMemberInLocation(BaseModel):
    name: str
    tier: str
    level: int
    avatar: Optional[str] = None
    count: int = 1
    # FEAT-152: summed persisted HP of the group's living members
    # (members are aggregated by template). None when no attributes rows found.
    current_hp: Optional[int] = None
    max_hp: Optional[int] = None


class MobPackInLocation(BaseModel):
    active_pack_id: int
    name: str
    avatar: Optional[str] = None
    status: str
    # Smallest living member character_id — the combat-gate handle (FEAT-145).
    lead_character_id: int
    members: List[PackMemberInLocation] = []


class MobPackRosterResponse(BaseModel):
    active_pack_id: int
    location_id: int
    status: str
    member_character_ids: List[int] = []
    lead_character_id: Optional[int] = None


class AddRewardsRequest(BaseModel):
    xp: int = 0
    gold: int = 0
    # FEAT-168 #6: какой книгой опыта ускоряется эта награда. По умолчанию —
    # опыт за бои: именно для боёв эндпоинт и писался, старые клиенты (battle-service,
    # dungeon-service) поля не шлют и работают как раньше.
    xp_source: str = "character_xp_battle_bonus"
    # FEAT-181 C2 (optional, backward compatible): op type of the gold posting, who pays
    # ("location" — treasury of location_id / the character's location; "world" — «Казна
    # Скитальцев») and replay protection (a repeated key adds neither XP nor gold).
    gold_op_type: str = "battle_reward"
    location_id: Optional[int] = None
    payer: str = "location"
    idempotency_key: Optional[str] = Field(None, min_length=1, max_length=128)

    @validator("xp", "gold")
    def validate_non_negative(cls, v):
        if v < 0:
            raise ValueError("Значение награды не может быть отрицательным")
        return v

    @validator("gold_op_type")
    def validate_gold_op_type(cls, v):
        from crud import REWARD_GOLD_OP_TYPES
        if v not in REWARD_GOLD_OP_TYPES:
            raise ValueError("Недопустимый тип операции")
        return v

    @validator("payer")
    def validate_payer(cls, v):
        from crud import REWARD_PAYERS
        if v not in REWARD_PAYERS:
            raise ValueError("Недопустимый плательщик")
        return v

    @validator("xp_source")
    def validate_xp_source(cls, v):
        # Импорт внутри валидатора: schemas не должен зависеть от crud на уровне модуля.
        from crud import CHARACTER_XP_SOURCES
        if v not in CHARACTER_XP_SOURCES:
            raise ValueError("Недопустимый источник опыта")
        return v


class AddRewardsResponse(BaseModel):
    ok: bool
    new_balance: int
    new_xp: Optional[int] = None
    duplicate: bool = False


class MobLootTableEntryResponse(BaseModel):
    item_id: int
    drop_chance: float
    min_quantity: int
    max_quantity: int


class MobRewardDataResponse(BaseModel):
    xp_reward: int
    gold_reward: int
    loot_table: List[MobLootTableEntryResponse] = []
    template_name: str
    tier: str


class UpdateActiveMobStatusRequest(BaseModel):
    status: str

    @validator("status")
    def validate_status(cls, v):
        if v not in ("alive", "in_battle", "dead"):
            raise ValueError("Статус должен быть alive, in_battle или dead")
        return v


NPC_KILLER_IDS_MAX = 200  # FEAT-200: cap of the kill-reputation recipients per NPC death


class UpdateNpcStatusRequest(BaseModel):
    status: str
    # FEAT-197 (optional, backward compatible): the battle and every character of the winning team; only real
    # players among them get the kill reputation, only on an alive -> dead transition.
    battle_id: Optional[int] = None
    killer_character_ids: Optional[List[int]] = None

    @validator("status")
    def validate_status(cls, v):
        if v not in ("alive", "dead"):
            raise ValueError("Статус NPC должен быть alive или dead")
        return v

    @validator("killer_character_ids")
    def cap_killer_ids(cls, v):
        # FEAT-200 (fix 7): never 422 on a big winning team (the NPC must die regardless) — dedupe, keep the
        # first NPC_KILLER_IDS_MAX ids
        if v is None:
            return v
        return list(dict.fromkeys(v))[:NPC_KILLER_IDS_MAX]


# ========== Bestiary Schemas ==========

class RecordMobKillRequest(BaseModel):
    character_id: int
    mob_character_id: int


class RecordMobKillResponse(BaseModel):
    ok: bool
    mob_template_id: int
    already_recorded: bool


class BestiarySkillEntry(BaseModel):
    skill_id: int
    skill_name: Optional[str] = None

    class Config:
        orm_mode = True


class BestiaryLootEntry(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    drop_chance: float
    min_quantity: int
    max_quantity: int

    class Config:
        orm_mode = True


class BestiarySpawnEntry(BaseModel):
    location_id: int
    location_name: Optional[str] = None

    class Config:
        orm_mode = True


class BestiaryEntry(BaseModel):
    id: int
    name: str
    tier: str
    level: int
    avatar: Optional[str] = None
    killed: bool
    description: Optional[str] = None
    base_attributes: Optional[Dict] = None
    skills: Optional[List[BestiarySkillEntry]] = None
    loot_entries: Optional[List[BestiaryLootEntry]] = None
    spawn_locations: Optional[List[BestiarySpawnEntry]] = None

    class Config:
        orm_mode = True


class BestiaryResponse(BaseModel):
    entries: List[BestiaryEntry]
    total: int
    killed_count: int


# ========== Character Log Schemas (FEAT-095) ==========

class CreateCharacterLogRequest(BaseModel):
    event_type: str
    description: str
    metadata: Optional[dict] = None


class CharacterLogResponse(BaseModel):
    id: int
    character_id: int
    event_type: str
    description: str
    metadata: Optional[dict] = None
    created_at: datetime

    class Config:
        orm_mode = True


class CharacterLogsListResponse(BaseModel):
    logs: List[CharacterLogResponse]
    total: int


# ============================================================
# Teleport (FEAT-123)
# ============================================================

class TeleportLinkCreate(BaseModel):
    from_npc_id: int
    to_npc_id: int
    cost_gold: int
    bidirectional: bool = True
    min_reputation_tier: Optional[str] = None       # FEAT-197 (applied to the reverse link too)

    _rep_tier = validator("min_reputation_tier", pre=True, allow_reuse=True)(_reputation_tier_code)

    @validator("cost_gold")
    def _cost_non_negative(cls, v):
        if v < 0:
            raise ValueError("Стоимость телепорта не может быть отрицательной")
        return v

    @validator("to_npc_id")
    def _not_same(cls, v, values):
        if "from_npc_id" in values and v == values["from_npc_id"]:
            raise ValueError("Нельзя создать связь NPC с самим собой")
        return v


class TeleportLinkUpdate(BaseModel):
    cost_gold: Optional[int] = None
    min_reputation_tier: Optional[str] = None       # FEAT-197: sent -> stored (null clears), omitted -> unchanged

    _rep_tier = validator("min_reputation_tier", pre=True, allow_reuse=True)(_reputation_tier_code)

    @validator("cost_gold")
    def _cost_non_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError("Стоимость телепорта не может быть отрицательной")
        return v


class TeleportLinkRead(BaseModel):
    id: int
    from_npc_id: int
    to_npc_id: int
    cost_gold: int
    created_at: Optional[datetime] = None
    min_reputation_tier: Optional[str] = None

    class Config:
        orm_mode = True


class TeleportOption(BaseModel):
    link_id: int
    to_npc_id: int
    to_npc_name: str
    to_location_id: Optional[int] = None
    to_location_name: Optional[str] = None
    cost_gold: int
    locked_reason: Optional[str] = None             # FEAT-197 «Нужна репутация: X» for the active character


class TeleportOptionsResponse(BaseModel):
    from_npc_id: int
    cooldown_seconds_remaining: int
    options: List[TeleportOption]
    locked_reason: Optional[str] = None             # FEAT-197 NPC-level gate for the active character


class TeleportRequest(BaseModel):
    link_id: int


class TeleportResult(BaseModel):
    new_location_id: int
    new_location_name: Optional[str] = None
    currency_balance: int
    last_teleport_at: datetime
    # FEAT-198: the guard encounter created on arrival (LawEncounterOut shape), else None
    law_encounter: Optional[dict] = None
    # FEAT-203: the guards did not notice the character on arrival
    law_slipped: bool = False


class PublicPostHistoryItem(BaseModel):
    """Пост так, как его видит чужой (FEAT-171 §3.4 C7, Q4b): без `xp_earned`."""

    id: int
    character_id: int
    location_id: int
    location_name: str
    content: str
    char_count: int
    created_at: datetime


class PostHistoryItem(PublicPostHistoryItem):
    """То же плюс начисленный опыт — только владельцу/админу/NPC."""

    xp_earned: int


class PostHistoryResponse(BaseModel):
    posts: List[PostHistoryItem]


class PublicPostHistoryResponse(BaseModel):
    posts: List[PublicPostHistoryItem]


class SetTravelCooldownRequest(BaseModel):
    minutes: int


# ── Home page mini-stats leaderboards ──
class LeaderboardEntry(BaseModel):
    character_id: int
    name: str
    avatar: str
    value: int


class HomeLeaderboardsResponse(BaseModel):
    symbols_daily: List[LeaderboardEntry]  # characters written in the last 24h
    pvp: List[LeaderboardEntry]            # PvP wins (all-time)
    pve: List[LeaderboardEntry]            # PvE points = sum of defeated mob levels (all-time)


# ── FEAT-162: перенос персонажа администратором ──
class AdminMoveCharacterRequest(BaseModel):
    new_location_id: int


class AdminMoveCharacterResponse(BaseModel):
    detail: str
    character_id: int
    moved: bool
    from_location_id: Optional[int] = None
    from_location_name: Optional[str] = None
    to_location_id: int
    to_location_name: Optional[str] = None
    gathering_cancelled: bool = False


# FEAT-180 stage 6b: internal home teleport (inventory-service, scroll used).
class HomeTeleportRequest(BaseModel):
    location_id: int
    # FEAT-180 stage 7: the return circle room the character arrives in (inside the house).
    house_room_id: Optional[int] = None


class HomeTeleportResponse(BaseModel):
    character_id: int
    from_location_id: Optional[int] = None
    location_id: int
    location_name: Optional[str] = None
    gathering_cancelled: bool = False


# ---------- Level thresholds (admin, 2026-10-25) ----------

LEVEL_MAX = 500


class LevelThresholdItem(BaseModel):
    """`required_experience` is the TOTAL experience a character needs to reach `level_number`."""
    level_number: int
    required_experience: int

    class Config:
        orm_mode = True


class LevelThresholdsSaved(BaseModel):
    thresholds: List[LevelThresholdItem]
    # Players whose experience was raised to the threshold of the level they hold.
    raised: int = 0


class LevelThresholdsUpdate(BaseModel):
    """The whole table at once: levels 2, 3, 4… with no gaps, total experience rising."""
    thresholds: List[LevelThresholdItem]

    @validator("thresholds")
    def _consistent(cls, v):
        if len(v) > LEVEL_MAX - 1:
            raise ValueError(f"Не больше {LEVEL_MAX} уровней")
        ordered = sorted(v, key=lambda t: t.level_number)
        prev_xp = 0
        for idx, t in enumerate(ordered):
            if t.level_number != idx + 2:
                raise ValueError("Уровни идут подряд со 2-го, без пропусков и повторов")
            if t.required_experience <= prev_xp:
                raise ValueError(f"Уровень {t.level_number}: опыта должно быть больше, чем для предыдущего")
            prev_xp = t.required_experience
        return ordered


# ===========================================================================
# FEAT-181 world economy — economy API (app/economy_api.py)
# ===========================================================================

from datetime import date as _date  # noqa: E402
from pydantic import StrictInt  # noqa: E402

ECON_MAX_ADMIN_AMOUNT = 10 ** 12           # upper bound of one admin emission / adjustment
ECON_COMMENT_MIN = 3
ECON_COMMENT_MAX = 500
ECON_FORM_MAX = 50                         # econ_settings.currency_* VARCHAR(50)
ECON_SHORT_MAX = 20                        # econ_settings.currency_short VARCHAR(20)
ECON_MAX_TAX_RATE = 0.5
ECON_FORBIDDEN_FORM_CHARS = set("<>")


def _econ_comment(v):
    if not isinstance(v, str):
        raise ValueError("Комментарий обязателен")
    v = v.strip()
    if len(v) < ECON_COMMENT_MIN:
        raise ValueError(f"Комментарий — не короче {ECON_COMMENT_MIN} символов")
    if len(v) > ECON_COMMENT_MAX:
        raise ValueError(f"Комментарий — не длиннее {ECON_COMMENT_MAX} символов")
    return v


class EconCurrencyForms(BaseModel):
    """Currency word forms. Also the public `GET /characters/economy/currency` response."""
    name: str
    genitive: str
    one: str
    few: str
    many: str
    short: str

    @validator("name", "genitive", "one", "few", "many", "short", pre=True)
    def _form(cls, v, field):
        if not isinstance(v, str):
            raise ValueError("Ожидается строка")
        v = v.strip()
        limit = ECON_SHORT_MAX if field.name == "short" else ECON_FORM_MAX
        if not v:
            raise ValueError("Поле не может быть пустым")
        if len(v) > limit:
            raise ValueError(f"Не длиннее {limit} символов")
        if any(ch in ECON_FORBIDDEN_FORM_CHARS for ch in v) or any(ord(ch) < 32 for ch in v):
            raise ValueError("Недопустимые символы")
        return v


class EconSettingsBody(BaseModel):
    """GET/PUT /characters/admin/economy/settings."""
    currency: EconCurrencyForms
    country_tax_rate: float

    @validator("country_tax_rate", pre=True)
    def _rate(cls, v):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("Ставка налога — число от 0 до 0.5")
        if not 0 <= v <= ECON_MAX_TAX_RATE:
            raise ValueError("Ставка налога — от 0 до 0.5")
        return round(float(v), 4)


class EconEmissionRequest(BaseModel):
    account_id: StrictInt
    amount: StrictInt
    comment: str

    @validator("amount")
    def _amount(cls, v):
        if not 1 <= v <= ECON_MAX_ADMIN_AMOUNT:
            raise ValueError("Сумма — от 1 до 1 000 000 000 000")
        return v

    _comment = validator("comment", pre=True, allow_reuse=True)(_econ_comment)


class EconAdjustRequest(BaseModel):
    account_id: StrictInt
    delta: StrictInt
    comment: str

    @validator("delta")
    def _delta(cls, v):
        if v == 0:
            raise ValueError("Изменение не может быть нулевым")
        if abs(v) > ECON_MAX_ADMIN_AMOUNT:
            raise ValueError("Изменение — не больше 1 000 000 000 000 по модулю")
        return v

    _comment = validator("comment", pre=True, allow_reuse=True)(_econ_comment)


class EconActionResponse(BaseModel):
    operation_id: Optional[int]
    account_id: int
    balance: int


class EconAccountItem(BaseModel):
    account_id: int
    kind: str
    ref_id: int
    name: Optional[str]
    balance: int
    is_active: bool


class EconAccountsPage(BaseModel):
    items: List[EconAccountItem]
    total: int
    page: int
    page_size: int


class EconPostingAccount(BaseModel):
    account_id: int
    kind: Optional[str]
    ref_id: Optional[int]
    name: Optional[str]


class EconPostingItem(BaseModel):
    from_: EconPostingAccount = Field(..., alias="from")
    to: EconPostingAccount
    amount: int
    leg_type: str

    class Config:
        allow_population_by_field_name = True


class EconOperationItem(BaseModel):
    id: int
    op_type: str
    created_at: datetime
    source_service: str
    location_id: Optional[int]
    region_id: Optional[int]
    actor_user_id: Optional[int]
    comment: Optional[str]
    metadata: Optional[Dict[str, Any]]
    postings: List[EconPostingItem]


class EconOperationsPage(BaseModel):
    items: List[EconOperationItem]
    total: int
    page: int
    page_size: int


class EconTotals(BaseModel):
    issued: int
    held: int
    players: int
    npcs: int
    escrow: int
    auction_storage: int
    region_treasuries: int
    country_treasuries: int
    world_treasury: int
    population_purses: int = 0               # FEAT-182: all population purses (already part of `held`)
    banks: int = 0                           # FEAT-184: own money of all banks (`bank` accounts)
    bank_deposits: int = 0                   # FEAT-184: vaults of player deposits (`bank_deposits` accounts)
    caravan_escrow: int = 0                  # FEAT-192: money of caravans on the road («Караваны в пути»)


class EconDriftingCharacter(BaseModel):
    character_id: int
    name: Optional[str]
    balance: int
    ledger: int


class EconInvariant(BaseModel):
    ok: bool
    ledger_sum: int
    escrow_expected: int
    escrow_actual: int
    storage_expected: int
    storage_actual: int
    bank_deposits_expected: int = 0          # FEAT-184: Σ open deposit rows (amount + interest_accrued)
    bank_deposits_actual: int = 0            # FEAT-184: Σ vault balances — part of `ok`
    caravan_escrow_expected: int = 0         # FEAT-192: Σ (paid_purse + paid_treasury) of caravans in transit
    caravan_escrow_actual: int = 0           # FEAT-192: the `caravan_escrow` balance — part of `ok`
    drifting_characters: List[EconDriftingCharacter]


class EconRegionTreasury(BaseModel):
    account_id: int
    region_id: int
    name: Optional[str]
    balance: int
    is_active: bool
    purse_account_id: Optional[int] = None   # FEAT-182: the region's population purse, if it exists
    purse_balance: Optional[int] = None


class EconCountryTreasury(BaseModel):
    account_id: Optional[int]          # None only for the «Без страны» group of orphan regions
    country_id: Optional[int]
    name: Optional[str]
    balance: int
    is_active: bool
    regions: List[EconRegionTreasury]


class EconSystemAccount(BaseModel):
    account_id: int
    kind: str
    name: Optional[str]
    balance: int


class EconSummarySettings(BaseModel):
    country_tax_rate: float


class EconSummary(BaseModel):
    currency: Dict[str, str]
    totals: EconTotals
    invariant: EconInvariant
    countries: List[EconCountryTreasury]
    system_accounts: List[EconSystemAccount]
    settings: EconSummarySettings


# ===========================================================================
# FEAT-182 living regions — economy simulation API (app/economy_api.py, contract 3.7)
# ===========================================================================

from pydantic import Extra, StrictBool  # noqa: E402

import econ_core as _econ_core  # noqa: E402

ECON_MAX_POPULATION = 1_000_000_000        # lore population (FEAT-186); econ_regions.population INT
ECON_MAX_PRODUCTION = 100_000
ECON_MAX_CONSUMPTION_MULT = 10
ECON_MAX_STOCK = 10 ** 12                  # econ_region_goods.stock DECIMAL(16,3)
ECON_MAX_BASE_PRICE = 1_000_000
ECON_MAX_NORM_PER_1000 = 100_000
ECON_MIN_NORM_DAYS, ECON_MAX_NORM_DAYS = 0.5, 365
ECON_MAX_ELASTICITY = 3
ECON_MAX_CLASS_DEMAND = 20          # FEAT-194: per-capita class demand weight of a goods group
ECON_CLASS_SUM_TOLERANCE = 0.001    # FEAT-194: the three class shares must sum to 1 within this
ECON_MIN_RATIO, ECON_MAX_RATIO = 0.001, 100
ECON_NAME_MAX = 100
ECON_DESCRIPTION_MAX = 500
ECON_NOUN_MAX = 50
ECON_NOUN_GENDERS = ("m", "f", "n")
ECON_MAX_BULK_IDS = 500
ECON_MAX_ID = 2 ** 63 - 1

# Bounds of every econ_sim.SimParams key (PUT /admin/economy/sim). Integer keys are listed in ECON_SIM_INT_PARAMS.
# Cross-field rules (economy_sim_crud): price_min < price_max, prod_price_min < prod_price_max.
ECON_SIM_PARAM_BOUNDS: Dict[str, tuple] = {
    "dt": (0.05, 1.0),
    "price_min": (0.05, 1.0),
    "price_max": (1.0, 20.0),
    "price_exponent": (0.05, 5.0),
    "stock_cap_mult": (1.0, 20.0),
    "prod_price_elasticity": (0.0, 2.0),
    "prod_price_min": (0.1, 1.0),
    "prod_price_max": (1.0, 5.0),
    "full_stability": (1.0, 100.0),
    "hunger_prod_penalty": (0.0, 1.0),
    "afford_days": (0.1, 30.0),
    "treasury_reserve_days": (0.0, 60.0),
    "treasury_release_ticks": (1, 100),
    "country_grant_share": (0.0, 1.0),
    "purse_start_days": (0.0, 60.0),
    "stab_base": (0.0, 100.0),
    "stab_hunger_w": (0.0, 500.0),
    "stab_goods_w": (0.0, 500.0),
    "stab_free_tax": (0.0, 0.5),
    "stab_tax_w": (0.0, 1000.0),
    "stab_debt_penalty": (0.0, 100.0),
    "stab_rate_up": (0.0, 1.0),
    "stab_rate_down": (0.0, 1.0),
    "prosp_rate": (0.0, 1.0),
    "prosp_w_sat": (0.0, 1.0),
    "prosp_w_liq": (0.0, 1.0),
    "prosp_w_stab": (0.0, 1.0),
    "prosp_hunger_w": (0.0, 500.0),
    "prosp_liq_days": (0.1, 60.0),
    "history_retention_days": (1, 365),
    # FEAT-183 NPC merchants
    "merchant_bid_share": (0.0, 1.0),
    "merchant_wholesale_share": (0.05, 1.0),
    "merchant_resident_share": (0.0, 1.0),
    "merchant_resident_share_max": (0.0, 1.0),
    "merchant_purse_share": (0.0, 0.5),
    "merchant_take_share": (0.0, 1.0),
    "merchant_cash_target_mult": (0.0, 20.0),
    "merchant_cash_cap_mult": (1.0, 20.0),
    "merchant_cash_release": (0.0, 1.0),
    # FEAT-184 banks
    "bank_demand_rate_day": (0.0, 0.05),
    "bank_term_rate_day_7": (0.0, 0.05),
    "bank_term_rate_day_14": (0.0, 0.05),
    "bank_term_rate_day_28": (0.0, 0.05),
    "bank_loan_rate_day": (0.0, 0.1),
    "bank_penalty_rate_day": (0.0, 0.1),
    "bank_debt_cap_mult": (1.0, 10.0),
    "bank_loan_cap_base": (0, 1_000_000_000),
    "bank_loan_cap_per_level": (0, 1_000_000_000),
    "bank_min_amount": (1, 1_000_000),
    "bank_transfer_fee_rate": (0.0, 0.5),
    "bank_transfer_fee_min": (0, 1_000_000),
    "bank_start_capital": (0, 1_000_000_000),
    "bank_reserve_ratio": (0.0, 1.0),
    "bank_rate_cover": (0.5, 5.0),
    "bank_rate_factor_min": (0.0, 1.0),
    "bank_rate_smoothing": (0.0, 1.0),
    "bank_resident_deposit_share": (0.0, 0.9),
    "bank_resident_loan_share": (0.0, 0.9),
    "bank_resident_adjust": (0.0, 1.0),
    "bank_profit_to_treasury_share": (0.0, 1.0),
    # FEAT-186 population scale: the sim uses lore population / scale
    "population_scale": (1, 10_000),
    # FEAT-187 region events
    "events_enabled": (0, 1),
    "event_rate_per_season": (0.0, 10.0),
    "event_season_days": (1.0, 400.0),
    "event_max_active": (1, 10),
    "event_mult_min": (0.01, 1.0),
    "event_mult_max": (1.0, 10.0),
    "event_delta_max": (0.0, 50.0),
    "event_spread_max_depth": (0, 5),
    "event_riot_stability": (0.0, 100.0),
    "event_riot_after_days": (0.25, 60.0),
    # FEAT-191 mint and season quota
    "quota_season_amount": (0, 1_000_000_000),
    "mint_season_limit": (0, 1_000_000_000),
    "mint_court_marks_per_unit": (0.01, 10_000.0),
    "mint_court_threshold_pct": (0.0, 1000.0),
    # FEAT-192 NPC caravans
    "caravans_enabled": (0, 1),
    "caravan_surplus_share": (0.0, 1.0),
    "caravan_purse_share": (0.0, 1.0),
    "caravan_treasury_food_share": (0.0, 1.0),
    "caravan_travel_domestic": (1, 8),
    "caravan_travel_foreign": (1, 8),
    "caravan_min_value": (1, 1_000_000),
    "caravan_max_per_run": (1, 5_000),
    # FEAT-193 guild orders
    "guild_enabled": (0, 1),
    "guild_markup_pct": (0.0, 200.0),
    "guild_open_threshold_pct": (1.0, 100.0),
    "guild_min_order_value": (1, 1_000_000),
    "guild_purse_share": (0.0, 1.0),
    "guild_treasury_food_share": (0.0, 1.0),
    "guild_xp_per_mark": (0.0, 10.0),
    "guild_xp_per_mark_merchant_items": (0.0, 10.0),
    "guild_xp_daily_cap": (0, 1_000_000),
    # FEAT-194 social classes and the wealth norm
    "classes_enabled": (0, 1),
    "class_norm_days_poor": (0.0, 365.0),
    "class_norm_days_middling": (0.0, 365.0),
    "class_norm_days_rich": (0.0, 365.0),
    "wealth_tax_rate": (0.0, 0.2),
    "class_tax_w_poor": (0.0, 5.0),
    "class_tax_w_middling": (0.0, 5.0),
    "class_tax_w_rich": (0.0, 5.0),
    "class_stab_poor_threshold": (0.0, 1.0),
    "class_stab_poor_w": (0.0, 500.0),
    "class_stab_poor_hunger_w": (0.0, 500.0),
    "class_stab_rich_free_tax": (0.0, 1.0),
    "class_stab_rich_tax_w": (0.0, 2000.0),
    "mob_rate_up": (0.0, 0.05),
    "mob_rate_down": (0.0, 0.05),
    "mob_rich_factor": (0.0, 1.0),
    "mob_dead_zone": (0.0, 0.9),
    "mob_w_prosperity": (0.0, 5.0),
    "mob_w_money": (0.0, 5.0),
    "mob_w_stability": (0.0, 5.0),
    "mob_w_hunger": (0.0, 5.0),
    "class_share_min": (0.0, 0.3),
    "class_share_max": (0.4, 1.0),
    "grant_deficit_share": (0.0, 1.0),
}
ECON_SIM_INT_PARAMS = frozenset({
    "treasury_release_ticks", "history_retention_days",
    "bank_loan_cap_base", "bank_loan_cap_per_level", "bank_min_amount", "bank_transfer_fee_min", "bank_start_capital",
    "population_scale",
    "events_enabled", "event_max_active", "event_spread_max_depth",
    "quota_season_amount", "mint_season_limit",
    "caravans_enabled", "caravan_travel_domestic", "caravan_travel_foreign", "caravan_min_value",
    "caravan_max_per_run",
    "guild_enabled", "guild_min_order_value", "guild_xp_daily_cap",
    "classes_enabled",
})


def _econ_number(v, lo, hi, label: str, integer: bool = False):
    """Number within [lo, hi]; bools and non-numeric strings are rejected with a Russian message."""
    if isinstance(v, bool):
        raise ValueError(f"{label}: ожидается число")
    if isinstance(v, str):
        try:
            v = float(v.strip())
        except ValueError:
            raise ValueError(f"{label}: ожидается число")
    if not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf")):
        raise ValueError(f"{label}: ожидается число")
    if integer:
        if float(v) != int(v):
            raise ValueError(f"{label}: ожидается целое число")
        v = int(v)
    if not lo <= v <= hi:
        raise ValueError(f"{label}: от {lo} до {hi}")
    return v


def _econ_text(v, max_len: int, label: str, optional: bool = False):
    """Stripped text without '<', '>' and control characters."""
    if v is None and optional:
        return None
    if not isinstance(v, str):
        raise ValueError(f"{label}: ожидается строка")
    v = v.strip()
    if optional and not v:
        return None
    if not v:
        raise ValueError(f"{label}: не может быть пустым")
    if len(v) > max_len:
        raise ValueError(f"{label}: не длиннее {max_len} символов")
    if any(ch in ECON_FORBIDDEN_FORM_CHARS for ch in v) or any(ord(ch) < 32 for ch in v):
        raise ValueError(f"{label}: недопустимые символы")
    return v


def _econ_group_code(v):
    if not isinstance(v, str) or v not in _econ_core.GOODS_GROUPS:
        raise ValueError("Неизвестная группа товаров")
    return v


def _econ_unique_codes(items, attr: str, label: str):
    codes = [getattr(item, attr) for item in items]
    if len(codes) != len(set(codes)):
        raise ValueError(f"{label}: группа указана дважды")
    return items


def _econ_bulk_ids(v, label: str):
    if not v:
        raise ValueError(f"Не выбрано ни одного: {label}")
    if len(v) > ECON_MAX_BULK_IDS:
        raise ValueError(f"Не больше {ECON_MAX_BULK_IDS} за раз ({label})")
    if any(not 1 <= i <= ECON_MAX_ID for i in v):
        raise ValueError(f"Некорректный id ({label})")
    return sorted(set(v))


_ECON_CLASS_LABELS = {"class_poor": "Доля бедных", "class_middling": "Доля зажиточных", "class_rich": "Доля богатых"}


class EconRegionGoodsIn(BaseModel):
    group_code: str
    production_per_1000: float
    consumption_mult: float
    stock: Optional[float] = None

    _code = validator("group_code", pre=True, allow_reuse=True)(_econ_group_code)

    @validator("production_per_1000", pre=True)
    def _prod(cls, v):
        return _econ_number(v, 0, ECON_MAX_PRODUCTION, "Производство на 1000 жителей")

    @validator("consumption_mult", pre=True)
    def _cmult(cls, v):
        return _econ_number(v, 0, ECON_MAX_CONSUMPTION_MULT, "Множитель потребления")

    @validator("stock", pre=True)
    def _stock(cls, v):
        return None if v is None else _econ_number(v, 0, ECON_MAX_STOCK, "Запас")


class EconRegionUpdateRequest(BaseModel):
    template_code: Optional[str] = None
    population: int
    tax_rate: float
    stability: Optional[float] = None
    prosperity: Optional[float] = None
    goods: Optional[List[EconRegionGoodsIn]] = None
    # FEAT-194: all three or none (omitted -> kept; checked with the sum in economy_sim_crud -> 400);
    # middling is stored as 1 - poor - rich
    class_poor: Optional[float] = None
    class_middling: Optional[float] = None
    class_rich: Optional[float] = None

    @validator("class_poor", "class_middling", "class_rich", pre=True)
    def _class_share(cls, v, field):
        return None if v is None else _econ_number(v, 0, 1, _ECON_CLASS_LABELS[field.name])

    @validator("template_code", pre=True)
    def _template(cls, v):
        if v is None or v == "":
            return None
        return _econ_text(v, 32, "Шаблон")

    @validator("population", pre=True)
    def _population(cls, v):
        return _econ_number(v, 0, ECON_MAX_POPULATION, "Население", integer=True)

    @validator("tax_rate", pre=True)
    def _tax(cls, v):
        return _econ_number(v, 0, ECON_MAX_TAX_RATE, "Ставка налога")

    @validator("stability", "prosperity", pre=True)
    def _percent(cls, v, field):
        label = "Стабильность" if field.name == "stability" else "Достаток"
        return None if v is None else _econ_number(v, 0, 100, label)

    @validator("goods")
    def _goods(cls, v):
        if v is None:
            return v
        return _econ_unique_codes(v, "group_code", "Товары")


class EconApplyTemplateRequest(BaseModel):
    reset_stocks: StrictBool = True


class EconFillRequest(BaseModel):
    region_ids: Optional[List[StrictInt]] = None
    population_from_template: StrictBool = False
    reset_stocks: StrictBool = True
    fund_purses: StrictBool = True
    # Added by B6: also top up each region treasury to its wage reserve target (otherwise wages stay 0 until the
    # treasury fills from taxes, ~a week, and purses only shrink after a fill).
    treasury_to_reserve: StrictBool = True
    # FEAT-184: open banks (one-time capital seed after the treasury top-up) in capital / port regions
    open_banks: StrictBool = True
    # FEAT-186 «Привести к масштабу»: return the purse / treasury part above the fill targets to emission
    return_purse_excess: StrictBool = False
    return_treasury_excess: StrictBool = False
    # FEAT-194: also reset the class shares to the template (rows without shares always get the template's)
    reset_classes: StrictBool = False
    comment: str

    _comment = validator("comment", pre=True, allow_reuse=True)(_econ_comment)

    @validator("region_ids")
    def _ids(cls, v):
        return None if v is None else _econ_bulk_ids(v, "регионы")


class EconMerchantFundRequest(BaseModel):
    """FEAT-183 «Пополнить кассы торговцев»: default = every living merchant."""
    region_ids: Optional[List[StrictInt]] = None
    npc_ids: Optional[List[StrictInt]] = None
    comment: str

    _comment = validator("comment", pre=True, allow_reuse=True)(_econ_comment)

    @validator("region_ids")
    def _regions(cls, v):
        return None if v is None else _econ_bulk_ids(v, "регионы")

    @validator("npc_ids")
    def _npcs(cls, v):
        return None if v is None else _econ_bulk_ids(v, "торговцы")


class EconGroupInputIn(BaseModel):
    input_code: str
    ratio: float

    _code = validator("input_code", pre=True, allow_reuse=True)(_econ_group_code)

    @validator("ratio", pre=True)
    def _ratio(cls, v):
        return _econ_number(v, ECON_MIN_RATIO, ECON_MAX_RATIO, "Расход сырья")


class EconGoodsGroupUpdateRequest(BaseModel):
    name: str
    base_price: int
    norm_per_1000: float
    norm_days: float
    prosperity_elasticity: float
    price_elasticity: float
    inputs: List[EconGroupInputIn] = []
    # FEAT-194: per-capita demand weights of the classes (None -> kept)
    class_demand_poor: Optional[float] = None
    class_demand_middling: Optional[float] = None
    class_demand_rich: Optional[float] = None

    @validator("class_demand_poor", "class_demand_middling", "class_demand_rich", pre=True)
    def _class_demand(cls, v):
        return None if v is None else _econ_number(v, 0, ECON_MAX_CLASS_DEMAND, "Спрос класса")

    @validator("name", pre=True)
    def _name(cls, v):
        return _econ_text(v, ECON_NAME_MAX, "Название")

    @validator("base_price", pre=True)
    def _price(cls, v):
        return _econ_number(v, 1, ECON_MAX_BASE_PRICE, "Базовая цена", integer=True)

    @validator("norm_per_1000", pre=True)
    def _norm(cls, v):
        return _econ_number(v, 0, ECON_MAX_NORM_PER_1000, "Норма потребления")

    @validator("norm_days", pre=True)
    def _days(cls, v):
        return _econ_number(v, ECON_MIN_NORM_DAYS, ECON_MAX_NORM_DAYS, "Запас в днях")

    @validator("prosperity_elasticity", "price_elasticity", pre=True)
    def _elasticity(cls, v):
        return _econ_number(v, 0, ECON_MAX_ELASTICITY, "Эластичность")

    @validator("inputs")
    def _inputs(cls, v):
        return _econ_unique_codes(v, "input_code", "Сырьё")


class EconTemplateGoodsIn(BaseModel):
    group_code: str
    production_per_1000: float
    consumption_mult: float

    _code = validator("group_code", pre=True, allow_reuse=True)(_econ_group_code)

    @validator("production_per_1000", pre=True)
    def _prod(cls, v):
        return _econ_number(v, 0, ECON_MAX_PRODUCTION, "Производство на 1000 жителей")

    @validator("consumption_mult", pre=True)
    def _cmult(cls, v):
        return _econ_number(v, 0, ECON_MAX_CONSUMPTION_MULT, "Множитель потребления")


class EconTemplateUpdateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    settlement_noun: str
    noun_gender: str
    default_population: int
    tax_rate: float
    goods: List[EconTemplateGoodsIn] = []
    # FEAT-194: default class mix, all three or none (None -> kept); middling stored as 1 - poor - rich
    class_poor: Optional[float] = None
    class_middling: Optional[float] = None
    class_rich: Optional[float] = None

    @validator("class_poor", "class_middling", "class_rich", pre=True)
    def _class_share(cls, v, field):
        return None if v is None else _econ_number(v, 0, 1, _ECON_CLASS_LABELS[field.name])

    @validator("name", pre=True)
    def _name(cls, v):
        return _econ_text(v, ECON_NAME_MAX, "Название")

    @validator("description", pre=True)
    def _description(cls, v):
        return _econ_text(v, ECON_DESCRIPTION_MAX, "Описание", optional=True)

    @validator("settlement_noun", pre=True)
    def _noun(cls, v):
        return _econ_text(v, ECON_NOUN_MAX, "Слово для поселения")

    @validator("noun_gender", pre=True)
    def _gender(cls, v):
        if v not in ECON_NOUN_GENDERS:
            raise ValueError("Род: m, f или n")
        return v

    @validator("default_population", pre=True)
    def _population(cls, v):
        return _econ_number(v, 0, ECON_MAX_POPULATION, "Население по умолчанию", integer=True)

    @validator("tax_rate", pre=True)
    def _tax(cls, v):
        return _econ_number(v, 0, ECON_MAX_TAX_RATE, "Ставка налога")

    @validator("goods")
    def _goods(cls, v):
        return _econ_unique_codes(v, "group_code", "Товары")


class EconItemGroupsUpdateRequest(BaseModel):
    """Fields left out stay unchanged (see ``__fields_set__``); ``null`` = back to the auto rule."""
    item_ids: List[StrictInt]
    group_code: Optional[str] = None
    off_market: Optional[StrictBool] = None
    reset: StrictBool = False

    @validator("item_ids")
    def _ids(cls, v):
        return _econ_bulk_ids(v, "предметы")

    @validator("group_code", pre=True)
    def _group(cls, v):
        return None if v is None else _econ_group_code(v)


class EconSimParamsIn(BaseModel):
    """Simulation params; a missing key keeps the stored value. Bounds: ECON_SIM_PARAM_BOUNDS."""
    dt: Optional[float] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    price_exponent: Optional[float] = None
    stock_cap_mult: Optional[float] = None
    prod_price_elasticity: Optional[float] = None
    prod_price_min: Optional[float] = None
    prod_price_max: Optional[float] = None
    full_stability: Optional[float] = None
    hunger_prod_penalty: Optional[float] = None
    afford_days: Optional[float] = None
    treasury_reserve_days: Optional[float] = None
    treasury_release_ticks: Optional[int] = None
    country_grant_share: Optional[float] = None
    purse_start_days: Optional[float] = None
    stab_base: Optional[float] = None
    stab_hunger_w: Optional[float] = None
    stab_goods_w: Optional[float] = None
    stab_free_tax: Optional[float] = None
    stab_tax_w: Optional[float] = None
    stab_debt_penalty: Optional[float] = None
    stab_rate_up: Optional[float] = None
    stab_rate_down: Optional[float] = None
    prosp_rate: Optional[float] = None
    prosp_w_sat: Optional[float] = None
    prosp_w_liq: Optional[float] = None
    prosp_w_stab: Optional[float] = None
    prosp_hunger_w: Optional[float] = None
    prosp_liq_days: Optional[float] = None
    history_retention_days: Optional[int] = None
    merchant_bid_share: Optional[float] = None
    merchant_wholesale_share: Optional[float] = None
    merchant_resident_share: Optional[float] = None
    merchant_resident_share_max: Optional[float] = None
    merchant_purse_share: Optional[float] = None
    merchant_take_share: Optional[float] = None
    merchant_cash_target_mult: Optional[float] = None
    merchant_cash_cap_mult: Optional[float] = None
    merchant_cash_release: Optional[float] = None
    bank_demand_rate_day: Optional[float] = None
    bank_term_rate_day_7: Optional[float] = None
    bank_term_rate_day_14: Optional[float] = None
    bank_term_rate_day_28: Optional[float] = None
    bank_loan_rate_day: Optional[float] = None
    bank_penalty_rate_day: Optional[float] = None
    bank_debt_cap_mult: Optional[float] = None
    bank_loan_cap_base: Optional[int] = None
    bank_loan_cap_per_level: Optional[int] = None
    bank_min_amount: Optional[int] = None
    bank_transfer_fee_rate: Optional[float] = None
    bank_transfer_fee_min: Optional[int] = None
    bank_start_capital: Optional[int] = None
    bank_reserve_ratio: Optional[float] = None
    bank_rate_cover: Optional[float] = None
    bank_rate_factor_min: Optional[float] = None
    bank_rate_smoothing: Optional[float] = None
    bank_resident_deposit_share: Optional[float] = None
    bank_resident_loan_share: Optional[float] = None
    bank_resident_adjust: Optional[float] = None
    bank_profit_to_treasury_share: Optional[float] = None
    population_scale: Optional[int] = None
    events_enabled: Optional[int] = None
    event_rate_per_season: Optional[float] = None
    event_season_days: Optional[float] = None
    event_max_active: Optional[int] = None
    event_mult_min: Optional[float] = None
    event_mult_max: Optional[float] = None
    event_delta_max: Optional[float] = None
    event_spread_max_depth: Optional[int] = None
    event_riot_stability: Optional[float] = None
    event_riot_after_days: Optional[float] = None
    quota_season_amount: Optional[int] = None
    mint_season_limit: Optional[int] = None
    mint_court_marks_per_unit: Optional[float] = None
    mint_court_threshold_pct: Optional[float] = None
    caravans_enabled: Optional[int] = None
    caravan_surplus_share: Optional[float] = None
    caravan_purse_share: Optional[float] = None
    caravan_treasury_food_share: Optional[float] = None
    caravan_travel_domestic: Optional[int] = None
    caravan_travel_foreign: Optional[int] = None
    caravan_min_value: Optional[int] = None
    caravan_max_per_run: Optional[int] = None
    guild_enabled: Optional[int] = None
    guild_markup_pct: Optional[float] = None
    guild_open_threshold_pct: Optional[float] = None
    guild_min_order_value: Optional[int] = None
    guild_purse_share: Optional[float] = None
    guild_treasury_food_share: Optional[float] = None
    guild_xp_per_mark: Optional[float] = None
    guild_xp_per_mark_merchant_items: Optional[float] = None
    guild_xp_daily_cap: Optional[int] = None
    classes_enabled: Optional[int] = None
    class_norm_days_poor: Optional[float] = None
    class_norm_days_middling: Optional[float] = None
    class_norm_days_rich: Optional[float] = None
    wealth_tax_rate: Optional[float] = None
    class_tax_w_poor: Optional[float] = None
    class_tax_w_middling: Optional[float] = None
    class_tax_w_rich: Optional[float] = None
    class_stab_poor_threshold: Optional[float] = None
    class_stab_poor_w: Optional[float] = None
    class_stab_poor_hunger_w: Optional[float] = None
    class_stab_rich_free_tax: Optional[float] = None
    class_stab_rich_tax_w: Optional[float] = None
    mob_rate_up: Optional[float] = None
    mob_rate_down: Optional[float] = None
    mob_rich_factor: Optional[float] = None
    mob_dead_zone: Optional[float] = None
    mob_w_prosperity: Optional[float] = None
    mob_w_money: Optional[float] = None
    mob_w_stability: Optional[float] = None
    mob_w_hunger: Optional[float] = None
    class_share_min: Optional[float] = None
    class_share_max: Optional[float] = None
    grant_deficit_share: Optional[float] = None

    class Config:
        extra = Extra.forbid

    @validator("*", pre=True)
    def _bounded(cls, v, field):
        if v is None:
            return v
        lo, hi = ECON_SIM_PARAM_BOUNDS[field.name]
        return _econ_number(v, lo, hi, f"Параметр {field.name}", integer=field.name in ECON_SIM_INT_PARAMS)


class EconSimUpdateRequest(BaseModel):
    tick_enabled: StrictBool
    params: EconSimParamsIn = EconSimParamsIn()


# ===========================================================================
# FEAT-184 banks — player API (contract 3.9 / 3.11; app/economy_bank_crud.py)
# ===========================================================================

from typing import Literal  # noqa: E402
from pydantic import conint, constr, root_validator  # noqa: E402

BANK_TERMS = (7, 14, 28)
BANK_MAX_AMOUNT = 1_000_000_000
_BANK_REQ_ID = constr(regex=r"^[A-Za-z0-9-]{8,64}$")
# strict: a float / bool / numeric string is a 422, never silently truncated
_BANK_AMOUNT = conint(strict=True, ge=1, le=BANK_MAX_AMOUNT)
_BANK_ID = conint(strict=True, gt=0)
_BANK_TERM_ERROR = "Срок — 7, 14 или 28 дней"


def _bank_term(v):
    if isinstance(v, bool) or not isinstance(v, int) or v not in BANK_TERMS:
        raise ValueError(_BANK_TERM_ERROR)
    return v


class BankDepositIn(BaseModel):
    character_id: _BANK_ID
    kind: Literal["demand", "term"]
    term_days: Optional[int] = None
    amount: _BANK_AMOUNT
    request_id: Optional[_BANK_REQ_ID] = None

    @validator("term_days", pre=True, always=True)
    def _term(cls, v, values):
        kind = values.get("kind")
        if kind == "term":
            return _bank_term(v)
        if v is not None:
            raise ValueError("У вклада до востребования нет срока")
        return None


class BankWithdrawIn(BaseModel):
    character_id: _BANK_ID
    deposit_id: _BANK_ID
    amount: Optional[_BANK_AMOUNT] = None      # demand: required (handler 400 «Укажите сумму»); term: ignored
    request_id: Optional[_BANK_REQ_ID] = None


class BankTransferIn(BaseModel):
    character_id: _BANK_ID
    deposit_id: _BANK_ID
    to_region_id: _BANK_ID
    amount: _BANK_AMOUNT
    request_id: Optional[_BANK_REQ_ID] = None


class BankSendIn(BaseModel):
    character_id: _BANK_ID
    source: Literal["wallet", "deposit"]
    deposit_id: Optional[_BANK_ID] = None      # required iff source == 'deposit'
    recipient_name: constr(strip_whitespace=True, min_length=1, max_length=255)
    to_region_id: _BANK_ID
    amount: _BANK_AMOUNT
    request_id: Optional[_BANK_REQ_ID] = None

    @root_validator(skip_on_failure=True)
    def _source(cls, values):
        if values.get("source") == "deposit":
            if values.get("deposit_id") is None:
                raise ValueError("Выберите вклад, с которого отправить деньги")
        elif values.get("deposit_id") is not None:
            raise ValueError("Вклад указывается только при переводе со вклада")
        return values


class BankLoanIn(BaseModel):
    character_id: _BANK_ID
    amount: _BANK_AMOUNT
    term_days: int
    request_id: Optional[_BANK_REQ_ID] = None

    _term = validator("term_days", pre=True, allow_reuse=True)(_bank_term)


class BankRepayIn(BaseModel):
    character_id: _BANK_ID
    amount: _BANK_AMOUNT
    request_id: Optional[_BANK_REQ_ID] = None


class BankTermRate(BaseModel):
    term_days: int
    rate_day: float


class BankRatesOut(BaseModel):
    demand_rate_day: float                      # current (base x factor)
    term_rates: List[BankTermRate]              # for new term deposits
    loan_rate_day: float
    penalty_rate_day: float
    transfer_fee_rate: float
    transfer_fee_min: int
    min_amount: int


class BankDepositOut(BaseModel):
    id: int
    region_id: int
    region_name: Optional[str]                  # None -> «удалённый регион»
    kind: str                                   # demand | term
    amount: int
    interest_accrued: int
    interest_total: int
    rate_day: Optional[float]                   # demand: current rate of its bank (0 when that bank is disabled)
    term_days: Optional[int]
    opened_at: datetime
    matures_at: Optional[datetime]
    matured: bool
    here: bool                                  # in the banker's bank

    class Config:
        orm_mode = True


class BankLoanOut(BaseModel):
    id: int
    region_id: int
    region_name: Optional[str]
    status: str
    principal: int
    debt: int                                   # projected to now
    interest_total: int
    penalty_total: int
    paid_total: int
    collected_total: int
    rate_day: float
    penalty_rate_day: float
    term_days: int
    issued_at: datetime
    due_at: datetime
    overdue: bool

    class Config:
        orm_mode = True


class BankRegionOut(BaseModel):
    region_id: int
    name: str
    country_name: Optional[str]


class BankView(BaseModel):
    npc_id: int
    npc_name: str
    region_id: Optional[int]
    region_name: Optional[str]
    bank_enabled: bool
    rates: BankRatesOut                         # rates of this bank (factor 1 when no row)
    wallet: int
    deposits: List[BankDepositOut]              # ALL own open deposits, any bank, `here` first
    loan: Optional[BankLoanOut]
    debtor: bool
    loan_cap: int
    max_loan_now: int                           # 0 when disabled / has loan / debtor; else min(cap, lendable)
    loan_refusal: Optional[str]                 # Russian reason when max_loan_now == 0
    bank_regions: List[BankRegionOut]           # enabled banks (transfer destinations)
    reputation_lock: Optional[str] = None       # FEAT-197 NPC gate: every banker action is refused with this text


class BankActionOut(BaseModel):
    message: str                                # Russian, shown as a toast
    operation_id: Optional[int]
    wallet: int
    view: BankView


class BankSummary(BaseModel):
    character_id: int
    total_deposits: int                         # Σ amount + interest_accrued
    deposits: List[BankDepositOut]              # here = False
    loan: Optional[BankLoanOut]
    debtor: bool


# FEAT-184 banks — admin API (contract 3.10; responses are plain dicts like the other FEAT-182/183 admin reads)

class BankFlagIn(BaseModel):
    is_enabled: StrictBool
    seed_capital: StrictBool = True             # first switch-on takes the start capital from the treasury once
    loan_min_reputation_tier: Optional[str] = None  # FEAT-197: sent -> stored (null clears), omitted -> unchanged

    _rep_tier = validator("loan_min_reputation_tier", pre=True, allow_reuse=True)(_reputation_tier_code)


class BankCapitalIn(BaseModel):
    direction: Literal["in", "out"]
    amount: _BANK_AMOUNT
    comment: str

    _comment = validator("comment", pre=True, allow_reuse=True)(_econ_comment)


class BankWriteOffIn(BaseModel):
    comment: str

    _comment = validator("comment", pre=True, allow_reuse=True)(_econ_comment)


# ===========================================================================
# FEAT-187 region events — admin & public API (contract 3.7 / 3.8; app/economy_events_crud.py)
# ===========================================================================

from pydantic import confloat, conlist  # noqa: E402

import econ_events as _econ_events  # noqa: E402

EVENT_ICONS = _econ_events.EVENT_ICONS          # mirrored in the frontend icon map
GAME_SEGMENTS = _econ_events.GAME_SEGMENTS
EVENT_MAX_DURATION_DAYS = 365
EVENT_MAX_WEIGHT = 1000
EVENT_MAX_CHAINS = 10
EVENT_MAX_REGION_TEMPLATES = 50
EVENT_HISTORY_MAX_PAGE_SIZE = 200
EVENT_CODE_RE = r"^[a-z][a-z0-9_]{1,31}$"
_EVENT_CODE = constr(regex=EVENT_CODE_RE)
_EVENT_GROUP = constr(regex=r"^(\*|[a-z][a-z0-9_]{0,31})$")
_EVENT_SCOPE = Literal["region", "neighbours", "country", "world"]

# Russian labels of effect types / fields (validation messages only; the UI has its own labels)
EVENT_EFFECT_LABELS = {
    "production": "производство", "consumption": "потребление", "labor": "больные жители", "price": "цены",
    "tax_income": "доход казны", "stability": "стабильность", "prosperity": "достаток",
    "merchants_halt": "торговцы не докупают", "bank_panic": "паника в банке", "loan_boom": "бум займов",
    "stock_loss": "потеря запасов", "treasury_expense": "расход казны", "population": "население",
    "class_shift": "сдвиг классов",
}
_EVENT_FIELD_LABELS = {"groups": "группы товаров", "mult": "множитель", "share": "долю", "delta": "изменение",
                       "pct": "изменение населения"}
_EVENT_VALUE_FIELDS = ("groups", "mult", "share", "delta", "pct")


def _event_number(value: float) -> str:
    return f"{value:g}".replace(".", ",")


class EventEffectIn(BaseModel):
    """One effect of a template (3.4): exactly the fields of its type; null fields count as absent."""

    type: Literal["production", "consumption", "labor", "price", "tax_income", "stability", "prosperity",
                  "merchants_halt", "bank_panic", "loan_boom", "stock_loss", "treasury_expense", "population",
                  "class_shift"]
    groups: Optional[conlist(_EVENT_GROUP, min_items=1, max_items=12)] = None
    mult: Optional[confloat(ge=0, le=5)] = None
    share: Optional[confloat(ge=0, le=0.9)] = None
    delta: Optional[confloat(ge=-10, le=10)] = None
    pct: Optional[confloat(ge=-0.5, le=0.5)] = None

    class Config:
        extra = Extra.forbid

    @root_validator(skip_on_failure=True)
    def _fields_of_type(cls, values):
        kind = values.get("type")
        label = EVENT_EFFECT_LABELS.get(kind, kind)
        allowed = _econ_events.EFFECT_FIELDS.get(kind, ())
        for name in _EVENT_VALUE_FIELDS:
            present = values.get(name) is not None
            if present and name not in allowed:
                raise ValueError(f"Лишнее поле «{name}» для эффекта «{label}»")
            if not present and name in allowed:
                raise ValueError(f"Для эффекта «{label}» нужно указать {_EVENT_FIELD_LABELS[name]}")
        bounds = _econ_events.EFFECT_BOUNDS.get(kind)
        if bounds is not None:
            name, lo, hi = bounds
            if not lo <= float(values[name]) <= hi:
                raise ValueError(f"Для эффекта «{label}» значение — от {_event_number(lo)} до {_event_number(hi)}")
        if values.get("groups") is not None:
            groups = list(dict.fromkeys(values["groups"]))
            values["groups"] = [_econ_events.ALL_GROUPS] if _econ_events.ALL_GROUPS in groups else groups
        return values

    def stored(self) -> dict:
        """The JSON object kept in ``effects`` (only the fields of the type)."""
        return {k: v for k, v in self.dict().items() if v is not None}


class EventChainIn(BaseModel):
    code: _EVENT_CODE
    chance: confloat(ge=0, le=1)


class EventTemplateUpdate(BaseModel):
    """Body of ``PUT /admin/economy/events/templates/{id}`` — every field of a template except the immutable code."""

    name: constr(strip_whitespace=True, min_length=2, max_length=100)
    icon: str
    kind: Literal["good", "bad"]
    player_text: constr(strip_whitespace=True, min_length=3, max_length=500)
    admin_note: Optional[constr(strip_whitespace=True, max_length=1000)] = None
    trigger_kind: Literal["random", "low_stability", "manual"] = "random"
    weight: confloat(ge=0, le=EVENT_MAX_WEIGHT) = 1.0
    duration_min_days: confloat(gt=0, le=EVENT_MAX_DURATION_DAYS)
    duration_max_days: confloat(gt=0, le=EVENT_MAX_DURATION_DAYS)
    scope: _EVENT_SCOPE = "region"
    spread_chance: confloat(ge=0, le=1) = 0.0
    region_templates: conlist(constr(strip_whitespace=True, min_length=1, max_length=32),
                              max_items=EVENT_MAX_REGION_TEMPLATES) = []
    seasons: conlist(str, max_items=len(GAME_SEGMENTS) * 2) = []
    effects: conlist(EventEffectIn, min_items=1, max_items=_econ_events.MAX_EFFECTS)
    chains: conlist(EventChainIn, max_items=EVENT_MAX_CHAINS) = []
    is_enabled: StrictBool = True

    @validator("icon")
    def _icon_known(cls, v):
        if v not in EVENT_ICONS:
            raise ValueError("Неизвестная иконка")
        return v

    @validator("admin_note")
    def _note_empty_is_none(cls, v):
        return v or None

    @validator("region_templates", "seasons", "chains", pre=True)
    def _none_is_empty(cls, v):
        return [] if v is None else v

    @validator("region_templates")
    def _region_templates_unique(cls, v):
        return list(dict.fromkeys(v))

    @validator("seasons")
    def _seasons_known(cls, v):
        for name in v:
            if name not in GAME_SEGMENTS:
                raise ValueError(f"Неизвестный сезон: {name}")
        return list(dict.fromkeys(v))

    @validator("chains")
    def _chains_unique(cls, v):
        codes = [c.code for c in v]
        for code in codes:
            if codes.count(code) > 1:
                raise ValueError(f"Цепочка на «{code}» указана дважды")
        return v

    @root_validator(skip_on_failure=True)
    def _duration_range(cls, values):
        if values["duration_max_days"] < values["duration_min_days"]:
            raise ValueError("Максимальная длительность меньше минимальной")
        return values


class EventTemplateIn(EventTemplateUpdate):
    code: _EVENT_CODE


class EventTemplateOut(BaseModel):
    """A template as the admin sees it (lenient: stored JSON is echoed as is)."""

    id: int
    code: str
    name: str
    icon: str
    kind: str
    player_text: str
    admin_note: Optional[str]
    trigger_kind: str
    weight: float
    duration_min_days: float
    duration_max_days: float
    scope: str
    spread_chance: float
    region_templates: List[str] = []
    seasons: List[str] = []
    effects: List[Dict[str, Any]] = []
    chains: List[Dict[str, Any]] = []
    is_enabled: bool
    active_count: int = 0
    updated_at: Optional[datetime]


class EventStartIn(BaseModel):
    template_id: conint(gt=0, le=2 ** 31 - 1)
    region_id: conint(gt=0, le=ECON_MAX_ID)
    scope: Optional[_EVENT_SCOPE] = None              # None = as the template
    duration_days: Optional[confloat(gt=0, le=EVENT_MAX_DURATION_DAYS)] = None   # None = rolled from the template
    request_id: Optional[constr(regex=r"^[A-Za-z0-9-]{8,64}$")] = None


class EventCancelIn(BaseModel):
    comment: str

    _comment = validator("comment", pre=True, allow_reuse=True)(_econ_comment)


class RegionEventOut(BaseModel):
    id: int
    region_id: int
    region_name: Optional[str]
    country_id: Optional[int]
    template_id: Optional[int]
    template_code: str
    name: str
    icon: str
    kind: str
    player_text: str
    trigger_kind: str
    effects: List[Dict[str, Any]] = []
    origin: str
    parent_event_id: Optional[int]
    root_event_id: Optional[int]
    generation: int
    status: str
    started_at: datetime
    ends_at: datetime
    ended_at: Optional[datetime]
    game_segment: Optional[str]
    started_by_user_id: Optional[int]
    cancelled_by_user_id: Optional[int]
    cancel_comment: Optional[str]
    applied_at: Optional[datetime]
    population_before: Optional[int]
    population_after: Optional[int]
    outcome: Optional[Dict[str, Any]]


class EventSkip(BaseModel):
    region_id: int
    region_name: Optional[str]
    reason: str                                   # Russian text (shown as is)


class EventStartOut(BaseModel):
    started: List[RegionEventOut]
    skipped: List[EventSkip]


class RegionEventsPage(BaseModel):
    items: List[RegionEventOut]
    total: int
    page: int
    page_size: int


class RegionCardEvent(BaseModel):
    code: str
    name: str
    icon: str
    kind: str
    text: str
    started_at: datetime
    ends_at: datetime


class EventBadge(BaseModel):
    name: str
    icon: str
    kind: str


# ===========================================================================
# FEAT-191 mint and season quota (contract 3.10; app/economy_mint_crud.py)
# ===========================================================================

MINT_MAX_QUANTITY = 10_000
MINT_MAX_RATE = 1_000_000
MINT_MAX_LIMIT = 1_000_000_000


class SeasonPeriodOut(BaseModel):
    index: int
    year: int
    season: str                                  # spring | summer | autumn | winter (UI: utils/gameTime.ts labels)
    starts_at: datetime                          # naive UTC
    ends_at: datetime                            # naive UTC, exclusive


class MintIn(BaseModel):
    character_id: conint(strict=True, ge=1)
    item_id: conint(strict=True, ge=1)
    quantity: conint(strict=True, ge=1, le=MINT_MAX_QUANTITY)
    request_id: _BANK_REQ_ID                     # required: the ledger key mint:{character}:{request_id}


class MintItemView(BaseModel):
    item_id: int
    name: Optional[str]
    image: Optional[str]
    marks_per_item: int
    have: int                                    # plain stacks in the bag
    max_by_limit: int                            # floor(remaining / marks_per_item)


class MintView(BaseModel):
    npc_id: int
    npc_name: str
    country_id: int
    country_name: Optional[str]
    region_id: int
    region_name: Optional[str]
    working: bool
    closed_reason: Optional[str]                 # Russian, when working is false
    period: Optional[SeasonPeriodOut]            # null when the calendar is unavailable
    limit: int
    minted_court: int
    minted_players: int
    remaining: int                               # 0 when closed
    items: List[MintItemView]
    wallet: int
    reputation_lock: Optional[str] = None        # FEAT-197 NPC gate: minting is refused with this text


class MintActionOut(BaseModel):
    message: str                                 # Russian, shown as a toast
    operation_id: int
    marks: int                                   # marks actually paid (for the accepted pieces)
    quantity: int                                # pieces actually accepted (≤ requested when the limit runs out)
    requested: int                               # pieces the player asked to mint
    partial: bool                                # True when only part was accepted (rest of the ore stays)
    wallet: int
    view: MintView


class MintCandidateOut(BaseModel):
    region_id: int
    name: Optional[str]
    template_code: Optional[str]


class MintMinterOut(BaseModel):
    npc_id: int
    name: Optional[str]
    npc_status: Optional[str]
    location_name: Optional[str]
    in_capital: bool


class MintCountryOut(BaseModel):
    country_id: int
    country_name: Optional[str]
    is_enabled: bool
    capital_region_id: Optional[int]
    capital_region_name: Optional[str]
    capital_source: str                          # auto | manual | none
    capital_override_id: Optional[int]
    override_stale: bool
    candidates: List[MintCandidateOut]
    working: bool
    closed_reason: Optional[str]
    season_limit_override: Optional[int]
    season_limit: int
    minted_court: int
    minted_players: int
    remaining: int
    ore_stock: Optional[float]
    ore_norm: Optional[float]
    minters: List[MintMinterOut]


class MintParamsOut(BaseModel):
    mint_season_limit: int
    mint_court_marks_per_unit: float
    mint_court_threshold_pct: float
    quota_season_amount: int


class MintAdminOut(BaseModel):
    period: Optional[SeasonPeriodOut]
    params: MintParamsOut
    countries: List[MintCountryOut]


class MintCountryIn(BaseModel):
    """Full replace; every key is required, null = auto capital / default limit."""
    capital_region_id: Optional[conint(strict=True, ge=1)] = Field(...)
    season_limit: Optional[conint(strict=True, ge=0, le=MINT_MAX_LIMIT)] = Field(...)
    is_enabled: StrictBool

    class Config:
        extra = Extra.forbid


class MintItemIn(BaseModel):
    marks_per_item: conint(strict=True, ge=1, le=MINT_MAX_RATE)
    is_enabled: StrictBool

    class Config:
        extra = Extra.forbid


class MintItemOut(BaseModel):
    item_id: int
    name: Optional[str]
    image: Optional[str]
    item_type: Optional[str]
    resource_subcategory: Optional[str]
    effective_group: Optional[str]
    marks_per_item: int
    is_enabled: bool
    valid: bool                                  # effective_group == 'ore_metal'


class QuotaOut(BaseModel):
    operation_id: int
    created_at: datetime
    period_index: Optional[int]
    year: Optional[int]
    season: Optional[str]
    amount: int
    regions: int


# ===========================================================================
# FEAT-192 NPC caravans (contract 3.11 / 3.12; app/economy_caravan_crud.py)
# ===========================================================================

CARAVAN_STATUS_RE = r"^(in_transit|delivered|cancelled|all)$"
CARAVAN_MAX_DUTY_PCT = 100
CARAVAN_LIST_MAX_LIMIT = 200


class TradePairIn(BaseModel):
    """Symmetric trade permission of two countries; normalised to country_a < country_b by the server."""
    country_a: conint(strict=True, ge=1)
    country_b: conint(strict=True, ge=1)
    is_enabled: StrictBool
    duty_pct: confloat(ge=0, le=CARAVAN_MAX_DUTY_PCT)

    class Config:
        extra = Extra.forbid


class TradePairOut(BaseModel):
    country_a: int
    country_b: int
    name_a: Optional[str]
    name_b: Optional[str]
    is_enabled: bool
    duty_pct: float
    updated_at: Optional[datetime]


class CaravanParamsOut(BaseModel):
    caravans_enabled: int
    caravan_surplus_share: float
    caravan_purse_share: float
    caravan_treasury_food_share: float
    caravan_travel_domestic: int
    caravan_travel_foreign: int
    caravan_min_value: int
    caravan_max_per_run: int


class CaravanEscrowOut(BaseModel):
    balance: int
    expected: int
    ok: bool


class CaravanTransitOut(BaseModel):
    count: int
    value: int
    duty: int


class CaravanLastRunOut(BaseModel):
    run_id: int
    dispatched: int
    delivered: int
    cancelled: int


class CaravanCountryOut(BaseModel):
    country_id: int
    name: Optional[str]
    participating_regions: int


class CaravanOverviewOut(BaseModel):
    params: CaravanParamsOut
    escrow: CaravanEscrowOut
    in_transit: CaravanTransitOut
    last_run: Optional[CaravanLastRunOut]
    countries: List[CaravanCountryOut]
    pairs: List[TradePairOut]


class CaravanOut(BaseModel):
    id: int
    status: str                                  # in_transit | delivered | cancelled
    group_code: str
    group_name: Optional[str]
    from_region_id: int
    from_region_name: Optional[str]              # null = region deleted
    from_country_id: int
    from_country_name: Optional[str]
    to_region_id: int
    to_region_name: Optional[str]
    to_country_id: int
    to_country_name: Optional[str]
    units: float
    unit_price: float
    value: int
    duty: int
    duty_pct: float
    paid_purse: int
    paid_treasury: int
    travel_runs: int
    runs_left: int
    dispatch_run_id: int
    finished_run_id: Optional[int]
    cancel_reason: Optional[str]                 # destination_left | destination_deleted
    goods_returned: Optional[bool]
    created_at: datetime
    finished_at: Optional[datetime]


class CaravanListOut(BaseModel):
    total: int
    items: List[CaravanOut]


class CaravanCardLine(BaseModel):
    """Region card line — words only (no units, prices or money)."""
    group_code: str
    group_name: str
    region_id: int
    region_name: Optional[str]
    country_name: Optional[str]                  # only for another country
    foreign: bool
    in_transit: bool


class RegionCaravansOut(BaseModel):
    incoming: List[CaravanCardLine] = []
    outgoing: List[CaravanCardLine] = []


# ===========================================================================
# FEAT-193 guild orders (contract 3.10; app/economy_guild_crud.py)
# ===========================================================================

GUILD_MAX_QUANTITY = 10_000
GUILD_STATUS_RE = r"^(open|filled|closed|all)$"   # «closed» lists closed and filled orders
GUILD_LIST_MAX_LIMIT = 200


class GuildHandInIn(BaseModel):
    character_id: conint(strict=True, ge=1)
    item_id: conint(strict=True, ge=1)
    quantity: conint(strict=True, ge=1, le=GUILD_MAX_QUANTITY)
    request_id: _BANK_REQ_ID                     # required: the ledger key guild:{character}:{request_id}


class GuildOrderOut(BaseModel):
    order_id: int
    group_code: str
    group_name: str
    is_food: bool
    units_total: float
    units_left: float
    filled_pct: int
    payable: bool                                # false = «жителям нечем платить до пересчёта»


class GuildOfferOut(BaseModel):
    item_id: int
    name: Optional[str]
    image: Optional[str]
    group_code: str
    order_id: int
    have: int                                    # plain stacks in the bag
    unit_price: int
    units_per_item: float
    max_accept: int                              # min(have, by volume, by money, 10000)
    capped_by_merchants: bool
    xp_rate: float                               # XP per mark for this item (3.6a)


class GuildRefusedOut(BaseModel):
    item_id: int
    name: Optional[str]
    image: Optional[str]
    group_code: Optional[str]
    have: int
    reason: str                                  # Russian


class GuildXpInfo(BaseModel):
    per_mark: float
    per_mark_merchant_items: float
    daily_cap: int
    left_today: int                              # base XP left today (UTC day)
    multiplier: float                            # quest XP book


class GuildView(BaseModel):
    npc_id: int
    npc_name: str
    region_id: Optional[int]                     # null when the NPC's location resolves to no region
    region_name: Optional[str]
    working: bool
    closed_reason: Optional[str]                 # Russian, when working is false
    markup_pct: float
    orders: List[GuildOrderOut]
    offers: List[GuildOfferOut]
    refused: List[GuildRefusedOut]
    xp: GuildXpInfo
    wallet: int
    reputation_lock: Optional[str] = None        # FEAT-197 NPC gate / «Вне закона» (then working = false)


class GuildActionOut(BaseModel):
    message: str                                 # Russian, includes the XP granted
    operation_id: int
    quantity: int                                # pieces actually accepted
    requested: int
    partial: bool
    unit_price: int
    total: int
    xp: int                                      # XP granted (after the book)
    xp_capped: bool                              # the daily cap cut the base XP
    wallet: int
    view: GuildView


class GuildParamsOut(BaseModel):
    guild_enabled: int
    guild_markup_pct: float
    guild_open_threshold_pct: float
    guild_min_order_value: int
    guild_purse_share: float
    guild_treasury_food_share: float
    guild_xp_per_mark: float
    guild_xp_per_mark_merchant_items: float
    guild_xp_daily_cap: int


class GuildTotalsOut(BaseModel):
    open: int
    units_left_value: int
    paid_last_7d: int
    hand_ins_last_7d: int
    xp_last_7d: int


class GuildMasterOut(BaseModel):
    npc_id: int
    name: Optional[str]
    npc_status: str
    location_name: Optional[str]


class GuildRegionOut(BaseModel):
    region_id: int
    region_name: Optional[str]
    guild_budget: int
    guild_food_budget: int
    open_orders: int
    masters: List[GuildMasterOut]


class GuildOrderRowOut(BaseModel):
    id: int
    region_id: int
    region_name: Optional[str]                   # null = region deleted
    group_code: str
    group_name: Optional[str]
    status: str                                  # open | filled | closed
    close_reason: Optional[str]                  # filled | no_shortage | no_money | disabled | region_left
    units_total: float
    units_left: float
    units_filled: float
    price_mult: float
    markup_pct: float
    pieces: int
    paid_total: int
    paid_treasury: int
    hand_ins: int
    opened_at: datetime
    updated_at: Optional[datetime]
    closed_at: Optional[datetime]


class GuildAdminOut(BaseModel):
    params: GuildParamsOut
    totals: GuildTotalsOut
    regions: List[GuildRegionOut]
    total: int
    items: List[GuildOrderRowOut]


class GuildWantOut(BaseModel):
    """Region card line «Гильдия ищет: …» — words only."""
    group_code: str
    group_name: str


# ===========================================================================
# FEAT-197 region reputation — API (contract §3.5; app/reputation_api.py)
# ===========================================================================

from uuid import UUID as _UUID  # noqa: E402

REPUTATION_PAGE_MAX = 50
REPUTATION_DELTA_LIMIT = 2000
REPUTATION_REASON_MIN = 3
REPUTATION_REASON_MAX = 500


class ReputationTierBrief(BaseModel):
    code: str
    name: str
    sort_order: int


class ReputationRegionOut(BaseModel):
    """Player view of one region — tier and bar only, never the number."""
    region_id: int
    region_name: Optional[str]
    country_id: Optional[int]
    country_name: Optional[str]
    tier_code: str
    tier_name: str
    progress: float                              # 0..1 inside the tier band
    trade_refused: bool                          # merchants of the region refuse (Вне закона)


class ReputationView(BaseModel):
    regions: List[ReputationRegionOut]
    tiers: List[ReputationTierBrief]             # the scale, lowest first


class ReputationHistoryItem(BaseModel):
    created_at: datetime
    region_id: int
    region_name: Optional[str]
    direction: str                               # up | down
    action_name: str
    text: str                                    # Russian phrase, no numbers
    tier_after_name: str
    tier_changed: bool


class ReputationHistoryPage(BaseModel):
    items: List[ReputationHistoryItem]
    total: int


class ReputationSettingsIn(BaseModel):
    min_value: int
    max_value: int
    echo_pct: float
    decay_per_day: float


class ReputationTierIn(BaseModel):
    code: str
    name: str = Field(..., max_length=60)
    min_value: Optional[int] = None
    price_pct: float = 0
    sell_pct: float = 0
    trade_refused: bool = False


class ReputationTierOut(ReputationTierIn):
    sort_order: int


class ReputationSettingsBody(BaseModel):
    settings: ReputationSettingsIn
    tiers: List[ReputationTierIn] = Field(..., min_items=8, max_items=8)


class ReputationSettingsOut(BaseModel):
    settings: ReputationSettingsIn
    tiers: List[ReputationTierOut]


class ReputationActionOut(BaseModel):
    code: str
    name: str
    points: int
    daily_cap: Optional[int]
    is_builtin: bool
    has_source: bool
    sort_order: int


def _rep_name(v):
    if not isinstance(v, str) or not v.strip():
        raise ValueError("Название обязательно")
    v = v.strip()
    if len(v) > 100:
        raise ValueError("Название — не длиннее 100 символов")
    return v


class ReputationActionUpdate(BaseModel):
    name: str
    points: int = Field(..., ge=-REPUTATION_POINTS_LIMIT, le=REPUTATION_POINTS_LIMIT)
    daily_cap: Optional[int] = Field(None, ge=1, le=100000)
    sort_order: Optional[int] = Field(None, ge=0, le=100000)

    _name = validator("name", pre=True, allow_reuse=True)(_rep_name)


class ReputationActionCreate(ReputationActionUpdate):
    code: str = Field(..., regex=_rep_core.ACTION_CODE_RE)


class ReputationRoleWeight(BaseModel):
    role: str = Field(..., regex=_rep_core.ROLE_RE)
    points: int = Field(..., ge=-REPUTATION_POINTS_LIMIT, le=REPUTATION_POINTS_LIMIT)


class ReputationAdminRegionOut(BaseModel):
    region_id: int
    region_name: Optional[str]
    country_id: Optional[int]
    country_name: Optional[str]
    value: int                                   # effective (decay applied)
    tier_code: str
    tier_name: str
    decaying: bool
    updated_at: Optional[datetime]


class ReputationAdminHistoryItem(BaseModel):
    id: int
    created_at: datetime
    region_id: int
    region_name: Optional[str]
    action: str
    action_name: str
    event_key: str
    is_echo: bool
    origin_region_id: Optional[int]
    origin_region_name: Optional[str]
    requested_delta: int
    applied_delta: int
    value_after: int
    tier_before: str
    tier_before_name: str
    tier_after: str
    tier_after_name: str
    reason: Optional[str]
    actor_user_id: Optional[int]
    actor_username: Optional[str]


class ReputationAdminHistoryPage(BaseModel):
    items: List[ReputationAdminHistoryItem]
    total: int


class ReputationAdjustIn(BaseModel):
    region_id: int = Field(..., ge=1)
    delta: Optional[int] = Field(None, ge=-REPUTATION_DELTA_LIMIT, le=REPUTATION_DELTA_LIMIT)
    action_code: Optional[str] = Field(None, max_length=40)
    reason: str
    echo: bool = False
    request_id: _UUID

    @validator("reason", pre=True)
    def _reason(cls, v):
        if not isinstance(v, str):
            raise ValueError("Причина обязательна")
        v = v.strip()
        if len(v) < REPUTATION_REASON_MIN:
            raise ValueError(f"Причина — не короче {REPUTATION_REASON_MIN} символов")
        if len(v) > REPUTATION_REASON_MAX:
            raise ValueError(f"Причина — не длиннее {REPUTATION_REASON_MAX} символов")
        return v

    @root_validator(skip_on_failure=True)
    def _one_of(cls, values):
        delta, code = values.get("delta"), values.get("action_code")
        if code is not None and not code.strip():
            code = values["action_code"] = None
        if (delta is None) == (code is None):
            raise ValueError("Укажите либо изменение числом, либо действие")
        if delta is not None and delta == 0:
            raise ValueError("Изменение не может быть нулевым")
        return values


class ReputationChangeOut(BaseModel):
    region_id: int
    is_echo: bool
    value_before: int
    value_after: int
    tier_before: str
    tier_after: str


class ReputationAdjustOut(BaseModel):
    changes: List[ReputationChangeOut]
    duplicate: bool


class ReputationApplyIn(BaseModel):
    """Internal (locations-service quest completion and future sources)."""
    character_id: int = Field(..., ge=1)
    region_id: int = Field(..., ge=1)
    action: str = Field(..., min_length=1, max_length=40)
    idempotency_key: str = Field(..., min_length=1, max_length=191)
    delta: Optional[int] = Field(None, ge=-REPUTATION_DELTA_LIMIT, le=REPUTATION_DELTA_LIMIT)
    reason: Optional[str] = Field(None, max_length=REPUTATION_REASON_MAX)
    echo: bool = True


class ReputationApplyOut(BaseModel):
    applied: bool
    duplicate: bool
    skipped: Optional[str]                       # npc | zero | cap


# ===========================================================================
# FEAT-198 law — wanted, guards, jail (contract §3.6; app/law_api.py)
# ===========================================================================

LAW_PAGE_MAX = 50
LAW_QUERY_MAX = 50
LAW_REASON_MIN = 3
LAW_REASON_MAX = 500
LAW_CHOICES = ("fine", "surrender", "flee", "fight")


def _law_reason(v):
    if not isinstance(v, str):
        raise ValueError("Причина обязательна")
    v = v.strip()
    if len(v) < LAW_REASON_MIN:
        raise ValueError(f"Причина — не короче {LAW_REASON_MIN} символов")
    if len(v) > LAW_REASON_MAX:
        raise ValueError(f"Причина — не длиннее {LAW_REASON_MAX} символов")
    return v


class LawEncounterOut(BaseModel):
    """Player view of a guard encounter (no raw wanted number)."""
    id: int
    region_id: int
    region_name: Optional[str]
    location_id: int
    guard_name: Optional[str]
    guard_avatar: Optional[str]
    is_outlaw: bool
    has_jail: bool
    level_name: Optional[str]
    fine: int
    jail_hours: int
    # FEAT-202: where a surrender would lead right now (pending only; null when closed / nowhere)
    jail_facility: Optional[str] = None             # station | country
    jail_name: Optional[str] = None                 # «Тюрьма страны «X»» / «Отделение стражи края «Y»»
    options: List[str]
    flee_chance_pct: Optional[float]
    status: str
    battle_id: Optional[int]
    expires_at: datetime
    by_patrol: bool = False                         # FEAT-204: noticed by a patrolling guard


class LawEncounterStaffOut(LawEncounterOut):
    character_id: int
    guard_npc_id: Optional[int]
    level_code: str
    wanted_value: int
    source: str
    from_location_id: Optional[int]
    flee_used: bool
    created_at: datetime
    fight_started_at: Optional[datetime]
    resolved_at: Optional[datetime]


class LawJailOut(BaseModel):
    id: int
    region_id: int
    region_name: Optional[str]
    location_id: int
    location_name: Optional[str]
    until: datetime
    bail_price: Optional[int]                   # FEAT-202: None when bail is not available (the country prison)
    bail_available: bool = True
    facility: str = "station"                   # station | country
    facility_name: Optional[str] = None
    country_id: Optional[int] = None
    district_id: Optional[int] = None           # the prison district (country only)
    district_name: Optional[str] = None
    allowed_location_ids: List[int] = []        # where the prisoner may be / move (station: the one location)
    can_escape_at: Optional[datetime]           # None = may try now
    escape_chance_pct: float
    escape_attempts: int


class LawJailStaffOut(LawJailOut):
    status: str
    level_code: str
    encounter_id: Optional[int]
    started_at: datetime


class LawWantedOut(BaseModel):
    region_id: int
    region_name: Optional[str]
    level_code: str
    level_name: str
    fine: int
    jail_hours: int
    decaying: bool


class LawStateOut(BaseModel):
    wanted: List[LawWantedOut]
    encounter: Optional[LawEncounterOut]
    jail: Optional[LawJailOut]


class LawEncounterWrap(BaseModel):
    encounter: Optional[LawEncounterOut]


class LawJailWrap(BaseModel):
    jail: Optional[LawJailOut]


class LawChoiceIn(BaseModel):
    choice: str
    request_id: _UUID

    @validator("choice")
    def _choice(cls, v):
        if v not in LAW_CHOICES:
            raise ValueError("Неизвестный вариант")
        return v


class LawChoiceOut(BaseModel):
    result: str                                  # fined | jailed | fled | fight | flee_failed_blocked | guard_gone
    message: str
    battle_id: Optional[int] = None
    jail: Optional[LawJailOut] = None
    encounter: Optional[LawEncounterOut] = None


class LawRequestIn(BaseModel):
    request_id: _UUID


class LawEscapeOut(BaseModel):
    success: bool
    message: str
    jail: Optional[LawJailOut] = None


class LawSelfBailOut(BaseModel):
    message: str
    jail: Optional[LawJailOut] = None


class LawPrisonerOut(BaseModel):
    character_id: int
    name: str
    avatar: Optional[str]
    region_name: Optional[str]
    location_name: Optional[str]
    until: datetime
    bail_price: int


class LawPrisonersPage(BaseModel):
    items: List[LawPrisonerOut]
    total: int


class LawBailIn(BaseModel):
    payer_character_id: int = Field(..., ge=1)
    banker_npc_id: int = Field(..., ge=1)
    prisoner_character_id: int = Field(..., ge=1)
    request_id: _UUID


class LawBailOut(BaseModel):
    message: str
    paid: int


class LawSettingsFields(BaseModel):
    max_wanted: int
    decay_per_day: float
    heavy_wanted: int
    outlaw_min_level: str = Field(..., max_length=20)
    encounter_timeout_hours: int
    guard_ko_hours: int
    flee_base_pct: float
    flee_per_point_pct: float
    flee_min_pct: float
    flee_max_pct: float
    escape_base_pct: float
    escape_per_point_pct: float
    escape_min_pct: float
    escape_max_pct: float
    escape_cooldown_hours: int
    escape_fail_extend_pct: float
    max_remaining_jail_hours: int
    bail_multiplier: float
    # FEAT-202: the country prison (optional on input: an omitted field keeps the stored value)
    country_prison_min_level: Optional[str] = Field(None, max_length=20)
    country_escape_multiplier: Optional[float] = None
    country_escape_cooldown_hours: Optional[int] = None
    # FEAT-203: the guard-detection roll (optional on input: an omitted field keeps the stored value)
    detect_enabled: Optional[bool] = None
    detect_base_safe_pct: Optional[float] = None
    detect_base_farm_pct: Optional[float] = None
    detect_base_dangerous_pct: Optional[float] = None
    detect_base_dungeon_pct: Optional[float] = None
    detect_base_default_pct: Optional[float] = None
    detect_per_guard_pct: Optional[float] = None
    detect_mask_factor_pct: Optional[float] = None
    detect_min_pct: Optional[float] = None
    detect_max_pct: Optional[float] = None
    # FEAT-204: guard patrols (optional on input: an omitted field keeps the stored value)
    patrols_enabled: Optional[bool] = None
    patrol_encounter_hold_min: Optional[int] = None


class LawLevelOut(BaseModel):
    code: str
    sort_order: int
    name: str
    min_value: int
    fine: int
    jail_hours: int
    detect_pct: float = 100.0                   # FEAT-203: × the guard-detection chance, %


class LawLevelIn(BaseModel):
    code: str = Field(..., max_length=20)
    sort_order: Optional[int] = None            # fixed per code; ignored on input
    name: str = Field(..., max_length=60)
    min_value: int
    fine: int
    jail_hours: int
    detect_pct: Optional[float] = None          # FEAT-203: None keeps the stored value (an older client)


class LawSettingsOut(BaseModel):
    settings: LawSettingsFields
    levels: List[LawLevelOut]


class LawSettingsBody(BaseModel):
    settings: LawSettingsFields
    levels: List[LawLevelIn] = Field(..., max_items=10)


class LawAdminWantedOut(BaseModel):
    region_id: int
    region_name: Optional[str]
    value: int
    level_code: Optional[str]
    level_name: Optional[str]


class LawCrimeOut(BaseModel):
    id: int
    crime_type: str
    region_id: int
    region_name: Optional[str]
    location_id: Optional[int]
    victim_character_id: Optional[int]
    battle_id: Optional[int]
    wanted_points: int
    wanted_applied: int
    status: str
    created_at: datetime
    # FEAT-199 (staff only)
    masked: bool = False
    witness_chance_pct: Optional[float] = None
    witness_roll_pct: Optional[float] = None
    stealth_reduction_pct: Optional[float] = None       # FEAT-201 reveal snapshot (NULL = 0)
    reputation_delta: Optional[int] = None
    wanted_floor: Optional[int] = None
    reveal_attempts: int = 0
    next_roll_at: Optional[datetime] = None
    reveal_until: Optional[datetime] = None
    revealed_at: Optional[datetime] = None


class LawLogOut(BaseModel):
    id: int
    created_at: datetime
    action: str
    region_id: Optional[int]
    region_name: Optional[str]
    wanted_before: Optional[int]
    wanted_after: Optional[int]
    amount: Optional[int]
    chance_pct: Optional[float]
    roll_pct: Optional[float]
    ref_id: Optional[int]
    reason: Optional[str]
    actor_user_id: Optional[int]
    actor_username: Optional[str]


class RenownAdminOut(BaseModel):
    fame: int
    fame_tier_name: str
    infamy: int
    infamy_tier_name: str


class RenownLogOut(BaseModel):
    id: int
    created_at: datetime
    scale: str
    source: str
    delta: int
    value_after: int
    tier_before: str
    tier_after: str
    ref_id: Optional[int]
    reason: Optional[str]
    actor_user_id: Optional[int]


class LawAdminCharacterOut(BaseModel):
    wanted: List[LawAdminWantedOut]
    encounter: Optional[LawEncounterStaffOut]
    jail: Optional[LawJailStaffOut]
    crimes: List[LawCrimeOut]
    log: List[LawLogOut]
    renown: Optional[RenownAdminOut] = None          # FEAT-199
    renown_log: List[RenownLogOut] = []


class LawStaffReleaseIn(BaseModel):
    reason: str
    request_id: _UUID

    _reason = validator("reason", pre=True, allow_reuse=True)(_law_reason)


class LawStaffClearIn(BaseModel):
    region_id: Optional[int] = Field(None, ge=1)  # None = every region
    reason: str
    request_id: _UUID

    _reason = validator("reason", pre=True, allow_reuse=True)(_law_reason)


class LawStaffReleaseOut(BaseModel):
    message: str
    released: bool
    cancelled: bool
    duplicate: bool


class LawStaffClearOut(BaseModel):
    message: str
    cleared_region_ids: List[int]
    duplicate: bool


class LawBattleResultIn(BaseModel):
    battle_id: int = Field(..., ge=1)
    law_encounter_id: int = Field(..., ge=1)
    winner_team: Optional[int] = None
    aborted: bool = False


class LawBattleResultOut(BaseModel):
    ok: bool
    status: str
    duplicate: bool


# =====================================================================================================================
# FEAT-199 the shadow: witnesses, hidden crimes, region suspicion, fame / infamy
# =====================================================================================================================

SHADOW_CRIME_STATUSES = ("open", "unwitnessed", "masked", "closed", "reported", "all")
RENOWN_SCALES = ("fame", "infamy")
RENOWN_ADJUST_MAX = 10_000
FAME_POINTS_MAX = 1000
SHADOW_PAGE_MAX = 50


class RenownFameOut(BaseModel):
    tier_code: str
    tier_name: str
    progress: float
    next_tier_name: Optional[str]


class RenownRumorsOut(BaseModel):
    tier_code: str
    tier_name: str


class RenownPlayerOut(BaseModel):
    fame: RenownFameOut
    rumors: RenownRumorsOut


class StealthPlayerOut(BaseModel):
    """FEAT-201 ``GET /characters/{id}/stealth`` (owner / staff)."""
    stealth: int                                # the stored total (points + gear + food + perks)
    subclass_bonus: int                         # out-of-battle subclass points, added before the cap
    subclass_name: Optional[str] = None
    effective: float                            # FEAT-195 cap of (stealth + subclass_bonus)
    reduction_pct: float                        # «−X % к шансу быть замеченным»
    pct_per_point: float
    max_reduction_pct: float


class FameTierPublicOut(BaseModel):
    code: str
    name: str
    sort_order: int


class ShadowSettingsFields(BaseModel):
    witness_enabled: bool
    witness_base_safe_pct: float
    witness_base_farm_pct: float
    witness_base_dangerous_pct: float
    witness_base_dungeon_pct: float
    witness_base_default_pct: float
    stealth_pct_per_point: float
    stealth_max_reduction_pct: float
    stealth_assassin_points: int
    stealth_trickster_points: int
    stealth_agent_points: int
    witness_group_per_extra_pct: float
    witness_min_pct: float
    witness_max_pct: float
    reveal_days: int
    reveal_base_pct: float
    reveal_per_suspicion_pct: float
    reveal_mask_factor_pct: float
    reveal_min_pct: float
    reveal_max_pct: float
    suspicion_max: int
    suspicion_unwitnessed: int
    suspicion_masked: int
    suspicion_decay_per_day: float
    suspicion_uneasy_at: int
    suspicion_alarmed_at: int
    suspicion_fear_at: int
    infamy_ratio: float
    infamy_min_gain: int
    fame_quest_default: int
    fame_rep_ratio: float
    fame_guild_ratio: float


class FameTierAdmin(BaseModel):
    code: str = Field(..., max_length=20)
    sort_order: Optional[int] = None            # fixed per code; ignored on input
    name: str = Field(..., max_length=60)
    min_value: int
    witness_pct: float = 0


class InfamyTierAdmin(BaseModel):
    code: str = Field(..., max_length=20)
    sort_order: Optional[int] = None
    name: str = Field(..., max_length=60)
    min_value: int


class ShadowSettingsOut(BaseModel):
    settings: ShadowSettingsFields
    fame_tiers: List[FameTierAdmin]
    infamy_tiers: List[InfamyTierAdmin]


class ShadowSettingsBody(BaseModel):
    settings: ShadowSettingsFields
    fame_tiers: List[FameTierAdmin] = Field(..., max_items=10)
    infamy_tiers: List[InfamyTierAdmin] = Field(..., max_items=10)


class ShadowCrimeOut(BaseModel):
    id: int
    character_id: int
    character_name: Optional[str]
    crime_type: str
    region_id: int
    region_name: Optional[str]
    location_id: Optional[int]
    location_name: Optional[str]
    victim_id: Optional[int]
    victim_name: Optional[str]
    status: str
    masked: bool
    witness_chance_pct: Optional[float]
    witness_roll_pct: Optional[float]
    stealth_reduction_pct: Optional[float] = None       # FEAT-201 reveal snapshot (NULL = 0)
    reputation_delta: Optional[int]
    wanted_points: int
    wanted_floor: Optional[int]
    reveal_attempts: int
    next_roll_at: Optional[datetime]
    reveal_until: Optional[datetime]
    created_at: datetime
    resolved_at: Optional[datetime]
    revealed_at: Optional[datetime]


class ShadowCrimesPage(BaseModel):
    items: List[ShadowCrimeOut]
    total: int


class ShadowStaffIn(BaseModel):
    reason: str
    request_id: _UUID

    _reason = validator("reason", pre=True, allow_reuse=True)(_law_reason)


class ShadowCrimeActionOut(BaseModel):
    message: str
    crime: ShadowCrimeOut


class RegionSuspicionOut(BaseModel):
    region_id: int
    region_name: Optional[str]
    value: int
    code: str
    label: str


class RenownAdjustIn(BaseModel):
    scale: str
    delta: int = Field(..., ge=-RENOWN_ADJUST_MAX, le=RENOWN_ADJUST_MAX)
    reason: str
    request_id: _UUID

    _reason = validator("reason", pre=True, allow_reuse=True)(_law_reason)

    @validator("scale")
    def _scale(cls, v):
        if v not in RENOWN_SCALES:
            raise ValueError("Шкала: fame или infamy")
        return v

    @validator("delta")
    def _delta(cls, v):
        if v == 0:
            raise ValueError("Изменение не может быть нулевым")
        return v


class RenownAdjustOut(BaseModel):
    scale: str
    value_before: int
    value_after: int
    tier_before: str
    tier_after: str
    duplicate: bool


class FameApplyIn(BaseModel):
    character_id: int = Field(..., ge=1)
    source: str
    idempotency_key: str = Field(..., min_length=1, max_length=191)
    points: Optional[int] = Field(None, ge=0, le=FAME_POINTS_MAX)
    ref_id: Optional[int] = None

    @validator("source")
    def _source(cls, v):
        if v != "quest":
            raise ValueError("Неизвестный источник славы")
        return v


class FameApplyOut(BaseModel):
    applied: bool
    duplicate: bool
    tier_changed: bool


# ========== FEAT-204: guard patrols (admin) ==========

PATROL_MAX_LIST = 200                           # hard input bound; patrol_core holds the real (Russian) limits


class PatrolIn(BaseModel):
    """PUT /characters/admin/npcs/{npc_id}/patrol. An omitted list / field keeps the stored value."""
    mode: str = Field(..., max_length=10)                       # post | route | zone
    route_style: Optional[str] = Field(None, max_length=10)     # loop | pingpong
    route_location_ids: Optional[List[int]] = Field(None, max_items=PATROL_MAX_LIST)
    zone_kind: Optional[str] = Field(None, max_length=10)       # district | locations
    zone_district_id: Optional[int] = None
    zone_location_ids: Optional[List[int]] = Field(None, max_items=PATROL_MAX_LIST)
    interval_min: Optional[int] = None
    jitter_pct: Optional[int] = None


class PatrolPointOut(BaseModel):
    location_id: int
    name: Optional[str] = None


class PatrolOut(BaseModel):
    npc_id: int
    npc_role: Optional[str] = None
    mode: str
    route_style: str
    route: List[PatrolPointOut]
    zone_kind: str
    zone_district_id: Optional[int] = None
    zone_district_name: Optional[str] = None
    zone_locations: List[PatrolPointOut]
    interval_min: int
    jitter_pct: int
    current_location_id: Optional[int] = None
    current_location_name: Optional[str] = None
    next_move_at: Optional[datetime] = None
    last_moved_at: Optional[datetime] = None
    blocked_reason: Optional[str] = None                        # not_guard | dead | ko | battle | encounter
    patrols_enabled: bool
    warnings: List[str] = []


class PatrolStepOut(BaseModel):
    outcome: str                                                # moved | stayed | blocked | not_patrolling
    blocked_reason: Optional[str] = None
    from_location_id: Optional[int] = None
    to_location_id: Optional[int] = None
    checked: int = 0
    encounters: int = 0
    slipped: int = 0
    patrol: PatrolOut
