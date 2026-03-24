from inspect import classify_class_attrs
from typing import Optional, Dict, List
from pydantic import BaseModel, validator
from datetime import datetime

# Базовая схема для заявки на создание персонажа
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
    avatar : str

# Схема для создания заявки на персонажа
class CharacterRequestCreate(CharacterRequestBase):
    pass

# Схема для возврата заявки
class CharacterRequest(CharacterRequestBase):
    id: int
    status: str

    class Config:
        orm_mode = True

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

class LevelProgress(BaseModel):
    current_exp_in_level: int
    exp_to_next_level: int
    progress_fraction: float

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
    avatar: Optional[str]


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
    user_id: Optional[int] = None

class CharacterProfileResponse(BaseModel):
        character_photo: str
        character_title: str
        character_name: str
        character_level: Optional[int] = None
        user_id: Optional[int] = None
        user_nickname: Optional[str] = None

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
    limit: int


# Starter Kit schemas
class StarterKitItem(BaseModel):
    item_id: int
    quantity: int = 1


class StarterKitSkill(BaseModel):
    skill_id: int


class StarterKitResponse(BaseModel):
    id: int
    class_id: int
    items: List[StarterKitItem]
    skills: List[StarterKitSkill]
    currency_amount: int

    class Config:
        orm_mode = True


class StarterKitUpdate(BaseModel):
    items: List[StarterKitItem] = []
    skills: List[StarterKitSkill] = []
    currency_amount: int = 0


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

class SubraceUpdate(BaseModel):
    id_race: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    stat_preset: Optional[StatPreset] = None

class SubraceResponse(BaseModel):
    id_subrace: int
    id_race: int
    name: str
    description: Optional[str] = None
    stat_preset: Optional[Dict] = None
    image: Optional[str] = None

    class Config:
        orm_mode = True


# ========== Race with Subraces (for public endpoint) ==========

class SubraceWithPreset(BaseModel):
    id_subrace: int
    name: str
    description: Optional[str] = None
    stat_preset: Optional[Dict] = None
    image: Optional[str] = None

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
    skill_rank_id: int

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
    skill_rank_ids: List[int]


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


class MobInLocation(BaseModel):
    active_mob_id: int
    character_id: int
    name: str
    level: int
    tier: str
    avatar: Optional[str] = None
    status: str


class AddRewardsRequest(BaseModel):
    xp: int = 0
    gold: int = 0

    @validator("xp", "gold")
    def validate_non_negative(cls, v):
        if v < 0:
            raise ValueError("Значение награды не может быть отрицательным")
        return v


class AddRewardsResponse(BaseModel):
    ok: bool
    new_balance: int
    new_xp: Optional[int] = None


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
    skill_rank_id: int
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