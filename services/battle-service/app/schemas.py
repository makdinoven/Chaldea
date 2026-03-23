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
    battle_type: Optional[str] = None


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


# --- Battle History schemas ---

class BattleHistoryItem(BaseModel):
    battle_id: int
    opponent_names: List[str]
    opponent_character_ids: List[int]
    battle_type: str
    result: str
    finished_at: datetime

    class Config:
        orm_mode = True


class BattleStats(BaseModel):
    total: int
    wins: int
    losses: int
    winrate: float


class BattleHistoryResponse(BaseModel):
    history: List[BattleHistoryItem]
    stats: BattleStats
    page: int
    per_page: int
    total_count: int
    total_pages: int


# --- Admin Battle Monitor schemas ---

class AdminBattleParticipant(BaseModel):
    participant_id: int
    character_id: int
    character_name: str
    level: int
    team: int
    is_npc: bool


class AdminBattleListItem(BaseModel):
    id: int
    status: str
    battle_type: str
    created_at: datetime
    updated_at: datetime
    participants: List[AdminBattleParticipant]


class AdminBattleListResponse(BaseModel):
    battles: List[AdminBattleListItem]
    total: int
    page: int
    per_page: int


class AdminBattleStateResponse(BaseModel):
    battle: dict
    snapshot: Optional[list] = None
    runtime: Optional[dict] = None
    has_redis_state: bool


class AdminForceFinishResponse(BaseModel):
    ok: bool
    battle_id: int
    message: str


# --- Location Battles schemas ---

class LocationBattleParticipant(BaseModel):
    participant_id: int
    character_id: int
    character_name: str
    level: int
    team: int
    is_npc: bool


class LocationBattleItem(BaseModel):
    id: int
    status: str
    battle_type: str
    is_paused: bool
    created_at: datetime
    participants: List[LocationBattleParticipant]


class LocationBattlesResponse(BaseModel):
    battles: List[LocationBattleItem]


# --- Spectate schemas ---

class SpectateStateResponse(BaseModel):
    snapshot: Optional[list] = None
    runtime: Optional[dict] = None


# --- Join Request schemas ---

class JoinRequestCreate(BaseModel):
    character_id: int
    team: int


class JoinRequestResponse(BaseModel):
    id: int
    battle_id: int
    character_id: int
    team: int
    status: str
    created_at: datetime


class JoinRequestListItem(BaseModel):
    id: int
    character_id: int
    character_name: str
    character_level: int
    character_avatar: Optional[str] = None
    team: int
    status: str
    created_at: datetime


class JoinRequestListResponse(BaseModel):
    requests: List[JoinRequestListItem]


# --- Admin Join Request schemas ---

class AdminJoinRequestItem(BaseModel):
    id: int
    battle_id: int
    character_id: int
    character_name: str
    character_level: int
    team: int
    status: str
    created_at: datetime
    battle_type: str
    battle_participants_count: int


class AdminJoinRequestListResponse(BaseModel):
    requests: List[AdminJoinRequestItem]
    total: int
    page: int
    per_page: int


class AdminJoinRequestActionResponse(BaseModel):
    ok: bool
    request_id: int
    message: str