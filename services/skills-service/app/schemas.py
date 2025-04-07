from pydantic import BaseModel
from typing import Optional, List, Union


# -----------------------
# 1) Skill
# -----------------------
class SkillBase(BaseModel):
    name: str
    skill_type: str
    description: Optional[str] = None

    # Новые поля
    class_limitations: Optional[str] = None
    race_limitations: Optional[str] = None
    subrace_limitations: Optional[str] = None
    min_level: int = 1
    purchase_cost: int = 0
    skill_image: Optional[str] = None  # base64 или URL

class SkillCreate(SkillBase):
    pass

class SkillUpdate(SkillBase):
    pass

class SkillRead(SkillBase):
    id: int
    class Config:
        orm_mode = True

# -----------------------
# 2) SkillRank
# -----------------------
class SkillRankBase(BaseModel):
    skill_id: int
    # Новые поля
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

# -----------------------
# 3) SkillRankDamage
# -----------------------
class SkillRankDamageBase(BaseModel):
    skill_rank_id: int
    damage_type: str
    amount: float = 0.0
    description: Optional[str] = None

class SkillRankDamageCreate(SkillRankDamageBase):
    pass

class SkillRankDamageUpdate(SkillRankDamageBase):
    pass

class SkillRankDamageRead(SkillRankDamageBase):
    id: int
    class Config:
        orm_mode = True

# -----------------------
# 4) SkillRankEffect
# -----------------------
class SkillRankEffectBase(BaseModel):
    skill_rank_id: int
    target_side: str = "self"
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

# -----------------------
# 5) CharacterSkill
# -----------------------
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

# -----------------------
# 6) LegacySkillRequest
# -----------------------
class LegacySkillRequest(BaseModel):
    character_id: int

# -----------------------
# 7) Upgrade (прокачка)
# -----------------------
class SkillUpgradeRequest(BaseModel):
    character_id: int
    next_rank_id: int

# -----------------------
# 8) UpdateActiveExperienceRequest
# -----------------------
class UpdateActiveExperienceRequest(BaseModel):
    amount: int

# -----------------------
# 9) Full tree responses
# -----------------------
class SkillRankDamageInTree(BaseModel):
    id: Optional[int]
    damage_type: str
    amount: float
    description: Optional[str]

class SkillRankEffectInTree(BaseModel):
    id: Optional[int]
    target_side: str
    effect_name: str
    description: Optional[str]
    chance: int
    duration: int
    magnitude: float
    attribute_key: Optional[str]

class SkillRankInTree(BaseModel):
    id: Union[int, str]  # Если None => создаём
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
