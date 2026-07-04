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
