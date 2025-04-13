from pydantic import BaseModel
from typing import Optional, List, Union


# ----------------------------------------------------
# 1) Skill
# ----------------------------------------------------
class SkillBase(BaseModel):
    name: str
    skill_type: str
    description: Optional[str] = None

    class_limitations: Optional[str] = None
    race_limitations: Optional[str] = None
    subrace_limitations: Optional[str] = None
    min_level: int = 1
    purchase_cost: int = 0
    skill_image: Optional[str] = None  # может быть URL


class SkillCreate(SkillBase):
    pass


class SkillUpdate(SkillBase):
    pass


class SkillRead(SkillBase):
    id: int

    class Config:
        orm_mode = True


# ----------------------------------------------------
# 2) SkillRank
# ----------------------------------------------------
class SkillRankBase(BaseModel):
    # Если skill_id обязателен в БД, оставляем
    skill_id: int

    rank_name: Optional[str] = None
    rank_image: Optional[str] = None
    rank_number: int = 1
    left_child_id: Optional[int] = None
    right_child_id: Optional[int] = None

    cost_energy: int = 0
    cost_mana: int = 0
    cooldown: int = 0
    level_requirement: int = 1
    upgrade_cost: int = 0

    class_limitations: Optional[str] = None
    race_limitations: Optional[str] = None
    subrace_limitations: Optional[str] = None

    rank_description: Optional[str] = None


class SkillRankCreate(SkillRankBase):
    pass


class SkillRankUpdate(SkillRankBase):
    pass


class SkillRankRead(SkillRankBase):
    id: int

    class Config:
        orm_mode = True


# ----------------------------------------------------
# 3) SkillRankDamage (CRUD-модели)
# ----------------------------------------------------
class SkillRankDamageBase(BaseModel):
    skill_rank_id: int
    damage_type: str
    amount: float = 0.0
    description: Optional[str] = None
    target_side: str
    chance: int = 100  # не забудь, если у тебя есть chance


class SkillRankDamageCreate(SkillRankDamageBase):
    pass


class SkillRankDamageUpdate(SkillRankDamageBase):
    pass


class SkillRankDamageRead(SkillRankDamageBase):
    id: int

    class Config:
        orm_mode = True


# ----------------------------------------------------
# 4) SkillRankEffect (CRUD-модели)
# ----------------------------------------------------
class SkillRankEffectBase(BaseModel):
    skill_rank_id: int
    target_side: str
    effect_name: str
    description: Optional[str] = None
    chance: int = 100
    duration: int = 1
    magnitude: float = 0.0
    attribute_key: Optional[str] = None


class SkillRankEffectCreate(SkillRankEffectBase):
    pass


class SkillRankEffectUpdate(SkillRankEffectBase):
    pass


class SkillRankEffectRead(SkillRankEffectBase):
    id: int

    class Config:
        orm_mode = True


# ----------------------------------------------------
# 5) CharacterSkill
# ----------------------------------------------------
class CharacterSkillBase(BaseModel):
    character_id: int
    skill_rank_id: int


class CharacterSkillCreate(CharacterSkillBase):
    pass


class CharacterSkillUpdate(CharacterSkillBase):
    pass


class CharacterSkillRead(CharacterSkillBase):
    id: int

    class Config:
        orm_mode = True


# ----------------------------------------------------
# 6) LegacySkillRequest
# ----------------------------------------------------
class LegacySkillRequest(BaseModel):
    character_id: int


# ----------------------------------------------------
# 7) Upgrade (прокачка)
# ----------------------------------------------------
class SkillUpgradeRequest(BaseModel):
    character_id: int
    next_rank_id: int


# ----------------------------------------------------
# 8) Request для апдейта ActiveExperience (пример)
# ----------------------------------------------------
class UpdateActiveExperienceRequest(BaseModel):
    amount: int


# ----------------------------------------------------
# 9) Модели для полного дерева (InTree)
# ----------------------------------------------------
class SkillRankDamageInTree(BaseModel):
    id: Optional[int]
    # Добавляем skill_rank_id, чтобы бэкенд точно знал,
    # к какому рангу относится урон (или он сам возьмет rank.id)
    skill_rank_id: Optional[int] = None

    damage_type: str
    amount: float
    description: Optional[str]
    chance: int = 100
    target_side: str


class SkillRankEffectInTree(BaseModel):
    id: Optional[int]
    # Аналогично, чтобы не терялось
    skill_rank_id: Optional[int] = None

    target_side: str
    effect_name: str
    description: Optional[str] = None
    chance: int = 100
    duration: int = 1
    magnitude: float = 0.0
    attribute_key: Optional[str] = None


class SkillRankInTree(BaseModel):
    # ID может быть int или str (например, "temp-1")
    id: Union[int, str]

    # Если нужно skill_id, делаем опциональным
    skill_id: Optional[int] = None

    rank_name: Optional[str]
    rank_image: Optional[str]
    rank_number: int
    left_child_id: Optional[Union[int, str]] = None
    right_child_id: Optional[Union[int, str]] = None

    cost_energy: int
    cost_mana: int
    cooldown: int
    level_requirement: int
    upgrade_cost: int
    class_limitations: Optional[str]
    race_limitations: Optional[str]
    subrace_limitations: Optional[str]
    rank_description: Optional[str]

    damage_entries: List[SkillRankDamageInTree]
    effects: List[SkillRankEffectInTree]


class FullSkillTreeResponse(BaseModel):
    id: int
    name: str
    skill_type: str
    description: Optional[str]
    class_limitations: Optional[str]
    race_limitations: Optional[str]
    subrace_limitations: Optional[str]
    min_level: int
    purchase_cost: int
    skill_image: Optional[str]

    ranks: List[SkillRankInTree]


class FullSkillTreeUpdateRequest(BaseModel):
    id: int
    name: str
    skill_type: str
    description: Optional[str]

    class_limitations: Optional[str] = None
    race_limitations: Optional[str] = None
    subrace_limitations: Optional[str] = None
    min_level: int = 1
    purchase_cost: int = 0
    skill_image: Optional[str] = None

    ranks: List[SkillRankInTree]

class AssignSkillEntry(BaseModel):
    skill_id: int
    rank_number: int

class MultipleSkillsAssignRequest(BaseModel):
    character_id: int
    skills: List[AssignSkillEntry]