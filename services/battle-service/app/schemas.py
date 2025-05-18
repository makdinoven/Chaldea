from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class BattleCreated(BaseModel):
    battle_id: int
    participants: List[int]
    next_actor: int
    deadline_at: datetime

class PlayerIn(BaseModel):
    character_id: int
    team: int | None = None


class BattleCreate(BaseModel):
    players: List[PlayerIn]


class SkillSelection(BaseModel):
    attack_rank_id: Optional[int] = None
    defense_rank_id: Optional[int] = None
    support_rank_id: Optional[int] = None
    item_id: Optional[int] = Field(
        default=None,
        description="ID предмета из fast-слота; None, если предмет не используется",
    )


class ActionRequest(BaseModel):
    participant_id: int
    skills: SkillSelection


class ActionResponse(BaseModel):
    ok: bool
    turn_number: int
    next_actor: int
    deadline_at: datetime

