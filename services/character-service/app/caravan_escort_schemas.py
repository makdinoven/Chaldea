"""FEAT-212 player caravan escorts — Pydantic v1 schemas of C1–C6 (features/FEAT-212 §3.12, PM decision 1)."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------------------------- C1 caravaneer view

class CaravaneerCaravanOut(BaseModel):
    id: int
    group_code: str
    group_name: Optional[str]
    departs_in_sec: Optional[int]
    has_seats: bool                       # «есть места» / «мест нет» — never the counts (PM decision 1)
    pay_estimate: int                     # guaranteed pay per head when every seat is taken
    can_hire: bool
    reason: Optional[str]                 # Russian refusal text when can_hire is false


class CaravaneerViewOut(BaseModel):
    npc_id: int
    location_id: int
    my_escort_caravan_id: Optional[int]
    seats_enabled: bool
    caravans: List[CaravaneerCaravanOut]


class EscortHireIn(BaseModel):
    character_id: int = Field(..., ge=1)
    npc_id: int = Field(..., ge=1)


# --------------------------------------------------------------------------------------------- C3 own job

class EscortRoutePointOut(BaseModel):
    index: int
    location_id: int
    name: Optional[str]


class EscortMateOut(BaseModel):
    character_id: int
    name: Optional[str]
    avatar: Optional[str]


class EscortJobOut(BaseModel):
    caravan_id: int
    group_code: str
    group_name: Optional[str]
    from_region_name: Optional[str]
    to_region_name: Optional[str]
    route: List[EscortRoutePointOut]
    route_index: int
    current_location_id: Optional[int]
    current_location_name: Optional[str]
    state: str                            # preparing | on_road | held | under_attack | arrived
    next_move_in_sec: Optional[int]
    seats_total: int
    escorts: List[EscortMateOut]
    pay_estimate: int                     # per head now (fee + bonus when the raid was repelled)
    raid_status: Optional[str]            # null | starting | fighting | won | repelled | aborted | expired
    battle_id: Optional[int]              # the raid battle when this escort fights in it
    joined_at: datetime


class EscortJobWrapOut(BaseModel):
    escort: Optional[EscortJobOut]


# --------------------------------------------------------------------------------------------- C4 leave

class EscortCharacterIn(BaseModel):
    character_id: int = Field(..., ge=1)


class EscortLeaveOut(BaseModel):
    left: bool
    location_id: Optional[int]


# --------------------------------------------------------------------------------------------- C5 / C6 channel

class EscortMessageOut(BaseModel):
    id: int
    character_id: int
    name: Optional[str]
    avatar: Optional[str]
    body: str
    created_at: datetime


class EscortMessagesOut(BaseModel):
    caravan_id: int
    messages: List[EscortMessageOut]


class EscortMessageIn(BaseModel):
    character_id: int = Field(..., ge=1)
    text: str = Field(..., max_length=2000)   # the 1..500 rule (after strip) is a Russian 400 from the crud
