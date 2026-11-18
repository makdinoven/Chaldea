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


class StormRefOut(BaseModel):
    """FEAT-214 §3.10: the active storm over the ship's current zone."""
    zone_id: int
    zone_name: Optional[str]
    ends_at: datetime


class RaidBattleRefOut(BaseModel):
    battle_id: int


class RaidStateOut(BaseModel):
    """FEAT-214 §3.10: the ship's active monster raid (one or more deck battles)."""
    monster_name: Optional[str]
    hold_until: Optional[datetime]        # the ship holds (does not sail on) until then; None = sails on
    battles: List[RaidBattleRefOut]       # fighting groups only (a just-rolled raid may have none yet)


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
    # FEAT-214 (additive)
    storm: Optional[StormRefOut] = None
    departure_postponed: bool = False     # docked and the departure is postponed by a storm
    raid: Optional[RaidStateOut] = None


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


class DeckCargoOut(BaseModel):
    """FEAT-215 §3.9: a caravan in the hold (never value / origin / destination region)."""
    caravan_id: int
    group_name: Optional[str]
    alight_port_name: Optional[str]


class DeckViewOut(BaseModel):
    ship: ShipPublicOut
    ships_nearby: List[ShipNearbyOut]
    passengers_count: int                  # FEAT-215: without the hidden caravan escorts
    my_passes: List[PassOut]
    sailor_post_min_chars: int
    cargo: List[DeckCargoOut] = []         # FEAT-215


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


# ---------------------------------------------------------------------------------------------------- FEAT-214

class SeaRaidResultIn(BaseModel):
    """battle-service → ``POST /characters/internal/sea/raid-result`` (X-Internal-Token)."""
    battle_id: int = Field(..., ge=1)
    sea_raid_id: int = Field(..., ge=1)
    winner_team: Optional[int] = None
    aborted: bool = False


class SeaRaidResultOut(BaseModel):
    status: str                           # won | lost | aborted | expired | already | unknown
