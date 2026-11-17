"""FEAT-213 ships — read side of locations-service (§3.6 port <-> deck passage, §3.12 validations).

Ships, their stops and the boarding passes belong to character-service (migration ``052_sea_ships``:
``sea_ships``, ``sea_ship_stops``, ``sea_passes``); this module only READS them with raw parameterised SQL.

* A ship's **deck** is an ordinary location (``sea_ships.deck_location_id``) with no LocationNeighbors rows.
  While the ship is ``docked`` at ``docked_port_id`` a passage port <-> deck exists: boarding needs an active
  ship and an entitled pass for the next trip (``trip_no + 1``); disembarking is open to anyone.
* The passage is not a LocationNeighbors row, so caravans, patrols, faction eject and the world graph never
  see it. A move through it costs ``PASSAGE_ENERGY_COST`` (no stamina, no travel cooldown) and is allowed only
  by a post (``move_and_post``); ``quick_move`` refuses it.

Deploy-order tolerance (§3.15): every read treats a missing table / SQL error as "no ships" and logs a warning
(pattern of ``faction_read._rows``). character-service re-checks every move authoritatively under the ship lock.
"""

import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# A passage move costs nothing: no stamina, no travel cooldown.
PASSAGE_ENERGY_COST = 0

STATUS_DOCKED = "docked"
PASS_ACTIVE = "active"
PASS_KINDS = ("ticket", "sailor", "stowaway")

PASSAGE_BOARD = "board"
PASSAGE_DISEMBARK = "disembark"

MSG_NO_RIGHT = "Нужен билет, место матроса или попытка пробраться зайцем — поговорите с капитаном"
MSG_SHIP_INACTIVE = "Корабль выключен — посадки нет"
MSG_AT_SEA = "Корабль в море — сойти на берег нельзя"
MSG_OPEN_SEA = "В открытое море не выйти"
MSG_POST_ONLY = "На борт и на берег сходят только постом"
SHIP_NAME_TEMPLATE = "Корабль «{name}»"

SQL_SHIPS_BY_DECKS = text(
    "SELECT id, name, deck_location_id, is_active, status, trip_no, docked_port_id "
    "FROM sea_ships WHERE deck_location_id IN :ids ORDER BY id"
).bindparams(bindparam("ids", expanding=True))
SQL_SHIPS_DOCKED_AT = text(
    "SELECT id, name, deck_location_id, is_active, status, trip_no, docked_port_id "
    "FROM sea_ships WHERE docked_port_id = :port AND status = :docked ORDER BY id"
)
SQL_PASSES_OF = text(
    "SELECT ship_id, first_trip, last_trip FROM sea_passes "
    "WHERE character_id = :cid AND status = :status AND kind IN :kinds AND ship_id IN :ships"
).bindparams(bindparam("kinds", expanding=True), bindparam("ships", expanding=True))
SQL_SHIPS_STOPPING_AT = text(
    "SELECT DISTINCT s.id, s.name FROM sea_ship_stops st JOIN sea_ships s ON s.id = st.ship_id "
    "WHERE st.port_location_id IN :ids ORDER BY s.id"
).bindparams(bindparam("ids", expanding=True))
# FEAT-214: storms belong to character-service (migration ``053_sea_storms_raids``). ``ends_at > now`` is checked in
# Python (naive UTC, as CS writes it) like CS ``sea_weather.storms_for``.
STORM_ACTIVE = "active"
SQL_STORM_ENDS_OVER_ZONE = text(
    "SELECT s.ends_at FROM sea_storm_zones z JOIN sea_storms s ON s.id = z.storm_id "
    "WHERE z.zone_id = :zone AND s.status = :active"
)
SQL_LOCATIONS = text(
    "SELECT id, name, image_url, recommended_level FROM Locations WHERE id IN :ids"
).bindparams(bindparam("ids", expanding=True))


@dataclass(frozen=True)
class ShipInfo:
    id: int
    name: str
    deck_location_id: int
    is_active: bool
    status: str
    trip_no: int
    docked_port_id: Optional[int]

    @property
    def docked(self) -> bool:
        return self.status == STATUS_DOCKED and self.docked_port_id is not None

    @property
    def next_trip(self) -> int:
        return self.trip_no + 1


@dataclass(frozen=True)
class Passage:
    """Outcome of a move between a port and a deck (``allowed`` False → ``refusal`` with ``status_code``)."""
    kind: Optional[str]          # board | disembark | None (a refusal not tied to a direction)
    ship_id: int
    allowed: bool
    refusal: Optional[str] = None
    status_code: int = 403


@dataclass
class LocationSea:
    """Sea data of the location page (§3.6): extra neighbour entries and the top-level additions."""
    ship_id: Optional[int] = None                     # this location is the deck of that ship
    disembark: List[dict] = field(default_factory=list)
    board: List[dict] = field(default_factory=list)
    docked_ships: List[dict] = field(default_factory=list)
    sea_unrest: bool = False                          # FEAT-214: the port's sea zone is under an active storm


def _ids(values: Iterable) -> List[int]:
    return sorted({int(v) for v in values if v is not None})


async def _rows(session: AsyncSession, stmt, params: dict, what: str) -> Optional[list]:
    """Rows of a raw read, or None when the ship tables are not there / the read failed."""
    try:
        return (await session.execute(stmt, params)).fetchall()
    except SQLAlchemyError as exc:
        logger.warning("Sea read (%s) failed, treated as no ships: %s", what, exc)
        return None


def _as_dt(value) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _ship(row) -> ShipInfo:
    return ShipInfo(
        id=int(row[0]),
        name=str(row[1]),
        deck_location_id=int(row[2]),
        is_active=bool(row[3]),
        status=str(row[4] or ""),
        trip_no=int(row[5] or 0),
        docked_port_id=int(row[6]) if row[6] is not None else None,
    )


# --------------------------------------------------------------------------------------------------- raw reads

async def ships_by_decks(session: AsyncSession, location_ids: Iterable) -> Dict[int, ShipInfo]:
    """{deck location id: ship} for those of the given locations that are ship decks."""
    ids = _ids(location_ids)
    if not ids:
        return {}
    rows = await _rows(session, SQL_SHIPS_BY_DECKS, {"ids": ids}, "ships by deck") or []
    return {int(r[2]): _ship(r) for r in rows}


async def ship_by_deck(session: AsyncSession, location_id: int) -> Optional[ShipInfo]:
    return (await ships_by_decks(session, [location_id])).get(int(location_id))


async def ships_docked_at(session: AsyncSession, port_id: int) -> List[ShipInfo]:
    rows = await _rows(session, SQL_SHIPS_DOCKED_AT,
                       {"port": int(port_id), "docked": STATUS_DOCKED}, "ships docked at port") or []
    return [_ship(r) for r in rows]


async def entitled_ship_ids(session: AsyncSession, character_id: Optional[int],
                            ships: Iterable[ShipInfo]) -> set:
    """Ids of the ships on which the character holds an active pass covering the ship's next trip."""
    ships = list(ships)
    if character_id is None or not ships:
        return set()
    rows = await _rows(session, SQL_PASSES_OF, {
        "cid": int(character_id), "status": PASS_ACTIVE, "kinds": list(PASS_KINDS),
        "ships": _ids(s.id for s in ships),
    }, "passes") or []
    next_trip = {s.id: s.next_trip for s in ships}
    out = set()
    for ship_id, first_trip, last_trip in rows:
        k = next_trip.get(int(ship_id))
        if k is not None and int(first_trip) <= k <= int(last_trip):
            out.add(int(ship_id))
    return out


async def ships_stopping_at(session: AsyncSession, port_ids: Iterable) -> List[ShipInfo]:
    """Ships (id, name only) whose route has a stop at one of the given ports."""
    ids = _ids(port_ids)
    if not ids:
        return []
    rows = await _rows(session, SQL_SHIPS_STOPPING_AT, {"ids": ids}, "ship stops") or []
    return [ShipInfo(int(r[0]), str(r[1]), 0, False, "", 0, None) for r in rows]


async def zone_in_storm(session: AsyncSession, zone_id: Optional[int], now: Optional[datetime] = None) -> bool:
    """FEAT-214: True when an active, not yet expired storm covers the sea zone. Missing tables → False."""
    if not zone_id:
        return False
    now = now or datetime.utcnow()
    rows = await _rows(session, SQL_STORM_ENDS_OVER_ZONE,
                       {"zone": int(zone_id), "active": STORM_ACTIVE}, "storms over zone") or []
    for (ends_at,) in rows:
        ends_at = _as_dt(ends_at)
        if ends_at is not None and ends_at > now:
            return True
    return False


# --------------------------------------------------------------------------------------------------- passages

async def passage(session: AsyncSession, character_id: int, current_id: int,
                  dest_id: int) -> Optional[Passage]:
    """The port <-> deck passage between ``current_id`` and ``dest_id``, if any.

    None = not a passage (the caller keeps its own "not a neighbour" answer). Otherwise ``allowed`` tells
    whether this character may take it now; refusals: no right / ship off (403), deck at sea (400)."""
    current_id, dest_id = int(current_id), int(dest_id)
    ships = await ships_by_decks(session, [current_id, dest_id])

    dest_ship = ships.get(dest_id)
    if dest_ship is not None and dest_ship.docked and dest_ship.docked_port_id == current_id:
        if not dest_ship.is_active:
            return Passage(PASSAGE_BOARD, dest_ship.id, False, MSG_SHIP_INACTIVE, 403)
        if dest_ship.id in await entitled_ship_ids(session, character_id, [dest_ship]):
            return Passage(PASSAGE_BOARD, dest_ship.id, True)
        return Passage(PASSAGE_BOARD, dest_ship.id, False, MSG_NO_RIGHT, 403)

    cur_ship = ships.get(current_id)
    if cur_ship is not None:
        if cur_ship.docked and cur_ship.docked_port_id == dest_id:
            return Passage(PASSAGE_DISEMBARK, cur_ship.id, True)
        if not cur_ship.docked:
            return Passage(None, cur_ship.id, False, MSG_AT_SEA, 400)
    return None


async def _location_cards(session: AsyncSession, ids: Iterable) -> Dict[int, dict]:
    ids = _ids(ids)
    if not ids:
        return {}
    rows = await _rows(session, SQL_LOCATIONS, {"ids": ids}, "locations") or []
    return {
        int(r[0]): {"id": int(r[0]), "name": r[1], "image_url": r[2], "recommended_level": int(r[3] or 1)}
        for r in rows
    }


async def passages_for(session: AsyncSession, location_id: int,
                       viewer_character_id: Optional[int],
                       port_sea_zone_id: Optional[int] = None) -> LocationSea:
    """Sea data of the location page.

    * On a deck of a docked ship: a «disembark» entry to the port, for any viewer.
    * In a port: «board» entries only for docked ACTIVE ships on which the viewer is entitled (others don't see
      them), plus the public list of every ship at the pier.
    * FEAT-214: ``sea_unrest`` — the port's sea zone (``port_sea_zone_id``, pass it only for a port) is in a storm.
    """
    location_id = int(location_id)
    out = LocationSea()
    deck_ship = await ship_by_deck(session, location_id)
    docked = await ships_docked_at(session, location_id)

    card_ids = [s.deck_location_id for s in docked]
    if deck_ship is not None:
        out.ship_id = deck_ship.id
        if deck_ship.docked:
            card_ids.append(deck_ship.docked_port_id)
    cards = await _location_cards(session, card_ids)

    if deck_ship is not None and deck_ship.docked:
        port = cards.get(deck_ship.docked_port_id)
        if port is not None:
            out.disembark.append({
                **port, "energy_cost": PASSAGE_ENERGY_COST,
                "passage": PASSAGE_DISEMBARK, "ship_id": deck_ship.id,
            })

    out.docked_ships = [{"id": s.id, "name": s.name} for s in docked]
    out.sea_unrest = await zone_in_storm(session, port_sea_zone_id)
    entitled = await entitled_ship_ids(session, viewer_character_id, [s for s in docked if s.is_active])
    for ship in docked:
        deck = cards.get(ship.deck_location_id)
        if ship.id not in entitled or deck is None or ship.deck_location_id == location_id:
            continue
        out.board.append({
            **deck, "name": SHIP_NAME_TEMPLATE.format(name=ship.name), "energy_cost": PASSAGE_ENERGY_COST,
            "passage": PASSAGE_BOARD, "ship_id": ship.id, "access_label": None, "access_allowed": True,
        })
    return out
