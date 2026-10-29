from inspect import classify_class_attrs
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field, validator
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
    "charisma", "luck",
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

    @validator(*STAT_PRESET_KEYS)
    def values_non_negative(cls, v):
        if v < 0:
            raise ValueError("Значение стата не может быть отрицательным")
        return v

    @validator("luck", always=True)
    def preset_sum_must_be_100(cls, v, values):
        total = v
        for key in STAT_PRESET_KEYS[:-1]:  # all except luck (already counted as v)
            total += values.get(key, 0)
        if total != 100:
            raise ValueError(f"Сумма пресета должна быть равна 100, получено {total}")
        return v


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


class UpdateNpcStatusRequest(BaseModel):
    status: str

    @validator("status")
    def validate_status(cls, v):
        if v not in ("alive", "dead"):
            raise ValueError("Статус NPC должен быть alive или dead")
        return v


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

    class Config:
        orm_mode = True


class TeleportOption(BaseModel):
    link_id: int
    to_npc_id: int
    to_npc_name: str
    to_location_id: Optional[int] = None
    to_location_name: Optional[str] = None
    cost_gold: int


class TeleportOptionsResponse(BaseModel):
    from_npc_id: int
    cooldown_seconds_remaining: int
    options: List[TeleportOption]


class TeleportRequest(BaseModel):
    link_id: int


class TeleportResult(BaseModel):
    new_location_id: int
    new_location_name: Optional[str] = None
    currency_balance: int
    last_teleport_at: datetime


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

ECON_MAX_POPULATION = 10_000_000
ECON_MAX_PRODUCTION = 100_000
ECON_MAX_CONSUMPTION_MULT = 10
ECON_MAX_STOCK = 10 ** 12                  # econ_region_goods.stock DECIMAL(16,3)
ECON_MAX_BASE_PRICE = 1_000_000
ECON_MAX_NORM_PER_1000 = 100_000
ECON_MIN_NORM_DAYS, ECON_MAX_NORM_DAYS = 0.5, 365
ECON_MAX_ELASTICITY = 3
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
}
ECON_SIM_INT_PARAMS = frozenset({"treasury_release_ticks", "history_retention_days"})


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
    comment: str

    _comment = validator("comment", pre=True, allow_reuse=True)(_econ_comment)

    @validator("region_ids")
    def _ids(cls, v):
        return None if v is None else _econ_bulk_ids(v, "регионы")


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
