from pydantic import BaseModel, Field
from typing import Optional, List, Union
from datetime import datetime


# ----------------------------------------------------
# Damage / Effect entry shared shapes (byte-compatible with old SkillRank* fields — R1)
# ----------------------------------------------------
class DamageEntryRead(BaseModel):
    id: int
    damage_type: str
    amount: float
    description: Optional[str] = None
    chance: int = 100
    target_side: str = "self"
    weapon_slot: Optional[str] = "main_weapon"

    class Config:
        orm_mode = True


class EffectEntryRead(BaseModel):
    id: int
    target_side: str = "self"
    effect_name: str
    description: Optional[str] = None
    chance: int = 100
    duration: int = 1
    magnitude: float = 0.0
    attribute_key: Optional[str] = None

    class Config:
        orm_mode = True


class DamageEntryWrite(BaseModel):
    damage_type: str
    amount: float = 0.0
    description: Optional[str] = None
    chance: int = 100
    target_side: str = "self"
    weapon_slot: Optional[str] = "main_weapon"


class EffectEntryWrite(BaseModel):
    target_side: str = "self"
    effect_name: str
    description: Optional[str] = None
    chance: int = 100
    duration: int = 1
    magnitude: float = 0.0
    attribute_key: Optional[str] = None


# ----------------------------------------------------
# 1) Skill (base/admin)
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
    skill_image: Optional[str] = None

    # Numeric base stats (formerly on SkillRank rank-0)
    cost_energy: int = 0
    cost_mana: int = 0
    cooldown: int = 0
    level_requirement: int = 1


class SkillCreate(SkillBase):
    pass


class SkillUpdate(SkillBase):
    pass


class SkillRead(SkillBase):
    id: int

    class Config:
        orm_mode = True


# ----------------------------------------------------
# Perk schemas
# ----------------------------------------------------
DELTA_BOUND = 999


class SkillPerkBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None
    perk_image: Optional[str] = None
    delta_cost_energy: Optional[int] = Field(None, ge=-DELTA_BOUND, le=DELTA_BOUND)
    delta_cost_mana: Optional[int] = Field(None, ge=-DELTA_BOUND, le=DELTA_BOUND)
    delta_cooldown: Optional[int] = Field(None, ge=-DELTA_BOUND, le=DELTA_BOUND)
    sort_order: int = 0


class SkillPerkCreate(SkillPerkBase):
    damage_entries: List[DamageEntryWrite] = []
    effects: List[EffectEntryWrite] = []


class SkillPerkUpdate(SkillPerkBase):
    damage_entries: List[DamageEntryWrite] = []
    effects: List[EffectEntryWrite] = []


class SkillPerkRead(SkillPerkBase):
    id: int
    skill_id: int
    damage_entries: List[DamageEntryRead] = []
    effects: List[EffectEntryRead] = []

    class Config:
        orm_mode = True


# ----------------------------------------------------
# Skill base damage / effect (admin CRUD)
# ----------------------------------------------------
class SkillBaseDamageRead(DamageEntryRead):
    skill_id: int


class SkillBaseEffectRead(EffectEntryRead):
    skill_id: int


# ----------------------------------------------------
# SkillWithPerks (public/admin combined view)
# ----------------------------------------------------
class SkillBaseStats(BaseModel):
    cost_energy: int = 0
    cost_mana: int = 0
    cooldown: int = 0
    level_requirement: int = 1
    damage_entries: List[DamageEntryRead] = []
    effects: List[EffectEntryRead] = []


class SkillWithPerksRead(BaseModel):
    id: int
    name: str
    skill_type: str
    description: Optional[str] = None
    purchase_cost: int = 0
    upgrade_cost: int = 0
    skill_image: Optional[str] = None
    min_level: int = 1
    class_limitations: Optional[str] = None
    race_limitations: Optional[str] = None
    subrace_limitations: Optional[str] = None
    base: SkillBaseStats
    perks: List[SkillPerkRead] = []


# ----------------------------------------------------
# Resolved skill (server-authoritative for battle-service)
# ----------------------------------------------------
class ResolvedSkillRead(BaseModel):
    skill_id: int
    character_id: int
    level: int
    selected_perk_ids: List[int] = []
    skill_type: str
    cost_energy: int
    cost_mana: int
    cooldown: int
    level_requirement: int
    damage_entries: List[DamageEntryRead] = []
    effects: List[EffectEntryRead] = []


# ----------------------------------------------------
# CharacterSkill schemas (new flat shape)
# ----------------------------------------------------
class CharacterSkillSummarySkill(BaseModel):
    id: int
    name: str
    skill_type: str
    skill_image: Optional[str] = None

    class Config:
        orm_mode = True


class CharacterSkillRead(BaseModel):
    character_skill_id: int
    skill_id: int
    character_id: int
    level: int
    free_perk_points: int
    selected_perk_ids: List[int] = []
    reset_available_at: Optional[datetime] = None
    skill: Optional[CharacterSkillSummarySkill] = None


class AdminCharacterSkillUpdate(BaseModel):
    skill_id: int
    level: int = Field(0, ge=0, le=4)


class AdminCharacterSkillCreate(BaseModel):
    character_id: int
    skill_id: int
    level: int = Field(0, ge=0, le=4)


# ----------------------------------------------------
# Legacy / shared
# ----------------------------------------------------
class LegacySkillRequest(BaseModel):
    character_id: int


class UpdateActiveExperienceRequest(BaseModel):
    amount: int


class AssignSkillEntry(BaseModel):
    skill_id: int


class MultipleSkillsAssignRequest(BaseModel):
    character_id: int
    skills: List[AssignSkillEntry]



# (Legacy SkillRank schemas removed in FEAT-125)


# ====================================================================
# Class Skill Tree schemas (FEAT-056)
# ====================================================================

# --- Class Skill Tree ---

class ClassSkillTreeBase(BaseModel):
    class_id: int
    name: str
    description: Optional[str] = None
    tree_type: str = "class"
    parent_tree_id: Optional[int] = None
    subclass_name: Optional[str] = None
    tree_image: Optional[str] = None


class ClassSkillTreeCreate(ClassSkillTreeBase):
    pass


class ClassSkillTreeUpdate(ClassSkillTreeBase):
    pass


class ClassSkillTreeRead(ClassSkillTreeBase):
    id: int

    class Config:
        orm_mode = True


# --- Tree Node ---

class TreeNodeBase(BaseModel):
    level_ring: int
    position_x: float = 0.0
    position_y: float = 0.0
    name: str
    description: Optional[str] = None
    node_type: str = "regular"
    icon_image: Optional[str] = None
    sort_order: int = 0


class TreeNodeCreate(TreeNodeBase):
    tree_id: int


class TreeNodeRead(TreeNodeBase):
    id: int
    tree_id: int

    class Config:
        orm_mode = True


# --- Tree Node Skill (inside a node) ---

class TreeNodeSkillEntry(BaseModel):
    skill_id: int
    sort_order: int = 0


class TreeNodeSkillRead(BaseModel):
    id: int
    skill_id: int
    sort_order: int = 0
    # Denormalized fields from skills table
    skill_name: Optional[str] = None
    skill_type: Optional[str] = None
    skill_image: Optional[str] = None

    class Config:
        orm_mode = True


# --- Connection ---

class TreeNodeConnectionInTree(BaseModel):
    id: Optional[Union[int, str]] = None
    from_node_id: Union[int, str]
    to_node_id: Union[int, str]


# --- Node in full tree request/response ---

class TreeNodeInTree(BaseModel):
    id: Union[int, str]  # int for existing, "temp-N" for new
    level_ring: int
    position_x: float = 0.0
    position_y: float = 0.0
    name: str
    description: Optional[str] = None
    node_type: str = "regular"
    icon_image: Optional[str] = None
    sort_order: int = 0
    skills: List[TreeNodeSkillEntry] = []


class TreeNodeInTreeResponse(BaseModel):
    id: int
    tree_id: int
    level_ring: int
    position_x: float
    position_y: float
    name: str
    description: Optional[str] = None
    node_type: str
    icon_image: Optional[str] = None
    sort_order: int
    skills: List[TreeNodeSkillRead] = []

    class Config:
        orm_mode = True


# --- Full Tree ---

class FullClassTreeResponse(BaseModel):
    id: int
    class_id: int
    name: str
    description: Optional[str] = None
    tree_type: str
    parent_tree_id: Optional[int] = None
    subclass_name: Optional[str] = None
    tree_image: Optional[str] = None
    nodes: List[TreeNodeInTreeResponse] = []
    connections: List[TreeNodeConnectionInTree] = []

    class Config:
        orm_mode = True


class FullClassTreeUpdateRequest(BaseModel):
    id: int
    class_id: int
    name: str
    description: Optional[str] = None
    tree_type: str = "class"
    parent_tree_id: Optional[int] = None
    subclass_name: Optional[str] = None
    tree_image: Optional[str] = None
    nodes: List[TreeNodeInTree] = []
    connections: List[TreeNodeConnectionInTree] = []


# ====================================================================
# Player Tree Progress schemas (FEAT-057)
# ====================================================================

class ChosenNodeProgress(BaseModel):
    node_id: int
    chosen_at: Optional[str] = None


class PurchasedSkillProgress(BaseModel):
    skill_id: int
    character_skill_id: int
    level: int = 0


class CharacterTreeProgressResponse(BaseModel):
    character_id: int
    tree_id: int
    chosen_nodes: List[ChosenNodeProgress]
    purchased_skills: List[PurchasedSkillProgress]
    active_experience: int
    character_level: int


class ChooseNodeRequest(BaseModel):
    character_id: int
    node_id: int


class PurchaseSkillRequest(BaseModel):
    character_id: int
    node_id: int
    skill_id: int


class ResetTreeRequest(BaseModel):
    character_id: int