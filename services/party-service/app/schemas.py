from typing import List, Optional

from pydantic import BaseModel, constr


class PartyCreate(BaseModel):
    leader_character_id: int
    name: constr(strip_whitespace=True, min_length=1, max_length=60)
    avatar: Optional[str] = None


class PartyInvite(BaseModel):
    character_id: int


class PartyRespond(BaseModel):
    character_id: int
    accept: bool


class PartyLeave(BaseModel):
    character_id: int


class PartyUpdate(BaseModel):
    name: Optional[constr(strip_whitespace=True, min_length=1, max_length=60)] = None
    avatar: Optional[str] = None


class MemberOut(BaseModel):
    character_id: int
    user_id: int
    name: Optional[str] = None
    avatar: Optional[str] = None
    is_leader: bool
    status: str
    # Current location of the member; the client colours 🟢/🔴 by comparing it to
    # its own character's location (FEAT-144 §4).
    current_location_id: Optional[int] = None
    # FEAT-151 — additive enrichment (all Optional → backward compatible):
    level: Optional[int] = None
    class_name: Optional[str] = None
    current_health: Optional[int] = None
    max_health: Optional[int] = None
    current_mana: Optional[int] = None
    max_mana: Optional[int] = None

    class Config:
        orm_mode = True


class PartyOut(BaseModel):
    id: int
    name: str
    avatar: Optional[str] = None
    leader_character_id: int
    members: List[MemberOut] = []

    class Config:
        orm_mode = True


class IncomingInvite(BaseModel):
    party_id: int
    party_name: str
    party_avatar: Optional[str] = None
    leader_character_id: int
    leader_name: Optional[str] = None


class XpBonusRequest(BaseModel):
    """Service-to-service: an XP-earning event by a party member (FEAT-144 §5)."""
    character_id: int
    base_xp: int
    source: str  # "post" | "combat" | "dungeon"
    location_id: Optional[int] = None
    # Party members who already earned base XP from this same event (a group
    # fight/dungeon). They are excluded from the passive trickle so they don't
    # double-dip. For a solo kill this is just [character_id].
    participant_character_ids: List[int] = []


class XpBonusResult(BaseModel):
    applied: bool = False
    bonus_per_member: int = 0
    self_bonus: int = 0
    trickle: List[dict] = []


class ActiveMembersResult(BaseModel):
    """Co-located accepted squadmates — the roster for a party activity (Ф3)."""
    party_id: Optional[int] = None
    leader_character_id: Optional[int] = None
    member_character_ids: List[int] = []  # includes the queried character if co-located


class PartyOnLocationMember(BaseModel):
    character_id: int
    name: Optional[str] = None
    avatar: Optional[str] = None
    is_leader: bool


class PartyOnLocation(BaseModel):
    """A squad visible on a location — only its co-located members are shown (Ф5)."""
    id: int
    name: str
    avatar: Optional[str] = None
    leader_character_id: int
    members: List[PartyOnLocationMember] = []

