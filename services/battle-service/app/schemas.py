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
    attack_rank_id: int | None = None
    defense_rank_id: int | None = None
    support_rank_id: int | None = None
    item_id: Optional[int] = Field(
        default=None,
        description="ID предмета из fast-слота; None, если предмет не используется",
    )


class ActionRequest(BaseModel):
    participant_id: int
    skills: SkillSelection


class BattleRewardItem(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int


class BattleRewards(BaseModel):
    xp: int = 0
    gold: int = 0
    items: list[BattleRewardItem] = []


class ActionResponse(BaseModel):
    ok: bool
    turn_number: int
    next_actor: int
    deadline_at: datetime
    events: list[dict]
    battle_finished: Optional[bool] = None
    winner_team: Optional[int] = None
    rewards: Optional[BattleRewards] = None

class BattleLog(BaseModel):
    battle_id: int
    turn_number: int
    events: list[dict]
    timestamp: datetime

class LogResponse(BaseModel):                # ← новый
    logs: list[BattleLog]


# --- PvP Invitation schemas ---

class PvpInviteRequest(BaseModel):
    initiator_character_id: int
    target_character_id: int
    battle_type: str  # "pvp_training" or "pvp_death"


class PvpInviteResponse(BaseModel):
    invitation_id: int
    initiator_character_id: int
    target_character_id: int
    battle_type: str
    status: str
    expires_at: datetime


class PvpRespondRequest(BaseModel):
    action: str  # "accept" or "decline"


class PvpRespondAcceptResponse(BaseModel):
    invitation_id: int
    status: str
    battle_id: Optional[int] = None
    battle_url: Optional[str] = None


class IncomingInvitation(BaseModel):
    invitation_id: int
    initiator_character_id: int
    initiator_name: str
    initiator_avatar: Optional[str] = None
    initiator_level: int
    battle_type: str
    created_at: datetime
    expires_at: datetime


class OutgoingInvitation(BaseModel):
    invitation_id: int
    target_character_id: int
    target_name: str
    battle_type: str
    status: str
    created_at: datetime


class PendingInvitationsResponse(BaseModel):
    incoming: List[IncomingInvitation]
    outgoing: List[OutgoingInvitation]


class CancelInvitationResponse(BaseModel):
    invitation_id: int
    status: str


# --- In-battle check ---

class InBattleResponse(BaseModel):
    in_battle: bool
    battle_id: Optional[int] = None


# --- PvP Attack schemas ---

class PvpAttackRequest(BaseModel):
    attacker_character_id: int
    victim_character_id: int


class PvpAttackResponse(BaseModel):
    battle_id: int
    battle_url: str
    attacker_character_id: int
    victim_character_id: int