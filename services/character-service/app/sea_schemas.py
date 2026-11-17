"""FEAT-213 sea routes — Pydantic v1 schemas of the player endpoints S1–S5 (features/FEAT-213 §3.13)."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CaptainRefOut(BaseModel):
    id: int
    name: Optional[str]
    avatar: Optional[str]


class LocationRefOut(BaseModel):
    id: int
    name: Optional[str]


class ZoneRefOut(BaseModel):
    id: int
    name: Optional[str]
    sea_name: Optional[str]               # the zone's region (a sea of the hidden «Моря» country)


class StopOut(BaseModel):
    index: int
    port_id: int
    port_name: Optional[str]


class ShipPublicOut(BaseModel):
    id: int
    name: str
    captain: Optional[CaptainRefOut]
    deck_location_id: int
    status: str                           # docked | sailing
    is_active: bool
    docked_port: Optional[LocationRefOut]
    next_port: Optional[LocationRefOut]
    current_zone: Optional[ZoneRefOut]
    departs_at: Optional[datetime]
    arrives_at: Optional[datetime]
    stops: List[StopOut]
    direction: int
    is_loop: bool
    server_now: datetime


class PassOut(BaseModel):
    id: int
    ship_id: int
    kind: str                             # ticket | sailor | stowaway
    status: str
    first_trip: int
    last_trip: int
    from_port_id: int
    from_name: Optional[str]
    to_port_id: int
    to_name: Optional[str]
    fare: int
    created_at: datetime
    valid_now: bool


class DestinationOut(BaseModel):
    to_trip: int
    stop_index: int
    port_id: int
    port_name: Optional[str]
    region_name: Optional[str]
    country_name: Optional[str]
    zones: int
    fare: int
    eta: Optional[datetime]
    seats_left: int
    can_buy: bool
    reason: Optional[str]


class SailorOfferOut(BaseModel):
    slots_left: int
    min_chars: int
    can_hire: bool
    reason: Optional[str]


class StowawayOfferOut(BaseModel):
    can_try: bool
    reason: Optional[str]


class CaptainViewOut(BaseModel):
    npc_id: int
    ship: ShipPublicOut
    balance: int
    destinations: List[DestinationOut]
    sailor: SailorOfferOut
    stowaway: StowawayOfferOut
    my_passes: List[PassOut]


class ShipNearbyOut(BaseModel):
    id: int
    name: str


class DeckViewOut(BaseModel):
    ship: ShipPublicOut
    ships_nearby: List[ShipNearbyOut]
    passengers_count: int
    my_passes: List[PassOut]
    sailor_post_min_chars: int


class TicketIn(BaseModel):
    character_id: int = Field(..., ge=1)
    npc_id: int = Field(..., ge=1)
    to_trip: int = Field(..., ge=1)


class SailorIn(BaseModel):
    character_id: int = Field(..., ge=1)
    npc_id: int = Field(..., ge=1)


class StowawayIn(BaseModel):
    character_id: int = Field(..., ge=1)


class MessageOut(BaseModel):
    message: str
