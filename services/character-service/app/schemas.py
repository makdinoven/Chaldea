from inspect import classify_class_attrs
from typing import Optional, Dict
from pydantic import BaseModel
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
        user_id: Optional[int] = None
        user_nickname: Optional[str] = None

        class Config:
            orm_mode = True

class CharacterShort(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True