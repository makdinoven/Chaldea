from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# ----- вход / выход -----
class BattleCreate(BaseModel):
    players: List[int]  # список character_id; [A,B] = 1×1, [A,B,C] = FFA


class BattleCreated(BaseModel):
    battle_id: int
    participants: List[int]
    next_actor: int
    deadline_at: datetime


class SkillSelection(BaseModel):
    attack_rank_id: Optional[int] = None
    defense_rank_id: Optional[int] = None
    support_rank_id: Optional[int] = None
    item_id: Optional[int] = None


class ActionRequest(BaseModel):
    participant_id: int
    skills: SkillSelection


class ActionResponse(BaseModel):
    ok: bool
    turn_number: int
    next_actor: int
    deadline_at: datetime
