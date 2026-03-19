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
    character_name: str
    character_title: str
    character_photo: str

class CharacterProfileResponse(BaseModel):
        character_photo: str
        character_title: str
        character_name: str
        user_id: Optional[int] = None
        user_nickname: Optional[str] = None

        class Config:
            orm_mode = True

class CharacterShort(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True


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