"""FEAT-213 sea routes — ships, passes and the Captain (sync SQLAlchemy; features/FEAT-213 §3.4–3.7, §3.10, §3.11).

A ship is a real location: passengers stand on its deck (``characters.current_location_id = deck``). The ship moves
by changing its own state; the only passenger moves this module makes are :func:`put_ashore` / :func:`safe_land`.

* reads of locations-service tables (``Locations``, ``LocationNeighbors``, ``Regions``, ``Countries``, ``posts``) are
  raw SQL and tolerant: a column of the sea geography that is not there yet (deploy skew) reads as «no zone»;
* the plan of a ship (:func:`plan`) — the next trips with their zone paths (manual override or BFS over the zones);
* the Captain (S1 :func:`captain_view`, S2 :func:`buy_ticket`, S3 :func:`hire_sailor`), the stowaway attempt
  (S4 :func:`sneak`) and the deck header (S5 :func:`deck_view`);
* the authoritative move check of CS ``update_location`` (:func:`lock_ships_for_move`, :func:`move_refusal`);
* landing helpers used by the sea pass / ship admin: :func:`put_ashore`, :func:`landing_target`, :func:`safe_land`,
  :func:`refund_pass`, :func:`refund_not_started`.

Lock order (§3.7): ``sea_ships (asc id) → sea_passes → characters (asc id) → econ_accounts``. Nothing here commits;
notices are returned and published by the caller after the commit.

FEAT-215 global lock order (features/FEAT-215 §3.6, supersedes the line above for these tables): ``sea_ships (asc) →
sea_passes → econ_regions → econ_region_goods → econ_region_events → econ_caravans (asc) → econ_caravan_raids →
econ_caravan_escorts (asc) → econ_caravan_sea_losses → sea_raids → … (FEAT-207 chain) … → characters (asc, ONE sorted
call per tx) → econ_accounts (asc) → character_attributes``. The ship transaction (``sea_cargo``) never takes the
region / goods / caravan-raid locks; no caravan / raid / delivery code path locks ``sea_ships``.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

import activity_lock
import econ_core as core
import econ_ledger
import law_core
import law_notify
import models
import sea_core
from economy_crud import EconomyApiError

logger = logging.getLogger("character-service.sea")

SOURCE_SERVICE = "character-service"
LOG_EVENT_TYPE = "sea"
WS_SEA = "sea"
NPC_DEAD = "dead"

SEA_TABLES = ("sea_ships", "sea_ship_stops", "sea_passes", "sea_settings")

MSG_UNAVAILABLE = "Корабли пока недоступны"
MSG_CHARACTER_NOT_FOUND = "Персонаж не найден"
MSG_NOT_OWNER = "Вы можете управлять только своими персонажами"
MSG_NOT_PLAYER = "На кораблях плавают только персонажи игроков"
MSG_CAPTAIN_NOT_FOUND = "Капитан не найден"
MSG_CAPTAIN_NO_SHIP = "Этот капитан сейчас без корабля"
MSG_NOT_AT_CAPTAIN = "Нужно находиться рядом с капитаном"
MSG_OTHER_SHIP = "Этот капитан командует другим кораблём"
MSG_GATE_CLOSED = "Нужен пост-намерение «Диалог с НПС» с капитаном"
MSG_GATE_UNAVAILABLE = "Не удалось проверить обращение к капитану, попробуйте позже"
MSG_SHIP_NOT_FOUND = "Корабль не найден"
MSG_SHIP_IDLE = "Корабль сейчас не ходит"
MSG_ALREADY_PASS = "У вас уже есть место на этом рейсе"
MSG_NO_SEATS = "Мест нет"
MSG_NO_CREW_SLOTS = "Мест для матросов нет"
MSG_HIRING_OFF = "Капитан не нанимает матросов"
MSG_BAD_TRIP = "Корабль не идёт до этого порта в ближайших рейсах"
MSG_NOT_IN_PORT = "Корабль стоит не здесь — пробраться на борт можно только у причала"
MSG_SHIP_AT_SEA = "Корабль в море"
MSG_SNEAK_DONE = "Вы пытаетесь незаметно пробраться на борт"
MSG_NOT_A_DECK = "Это не палуба корабля"
# move refusals (the same texts as the locations-service pre-check, §3.6)
MSG_OPEN_SEA = "В открытое море не выйти"
MSG_SHIP_GONE = "Корабль уже отплыл"
MSG_SHIP_OFF = "Корабль выключен — посадки нет"
MSG_NEED_PASS = "Нужен билет, место матроса или попытка пробраться зайцем — поговорите с капитаном"
MSG_AT_SEA_NO_LANDING = "Корабль в море — сойти на берег нельзя"
MSG_ONLY_TO_PORT = "С палубы можно сойти только в порт стоянки"
MSG_RETRY = "Попробуйте ещё раз"
MSG_TELEPORT_TARGET = "Туда нельзя переместиться телепортом: это палуба корабля или открытое море"


class SeaError(EconomyApiError):
    """Business error of the sea layer (HTTP status + Russian text, or a dict detail for 402)."""


def now_utc() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def _i(value) -> int:
    return int(value or 0)


def _for_update(db: Session) -> bool:
    return core.supports_for_update(db.get_bind().dialect.name)


def _locked(q, db: Session):
    return (q.with_for_update() if _for_update(db) else q).populate_existing()


def _rows(db: Session, sql: str, params: Optional[dict] = None):
    """Rows of a read of another service's table / column that may be absent (deploy skew, SQLite fixtures):
    absent → None (the caller falls back)."""
    try:
        with db.begin_nested():
            return db.execute(text(sql), params or {}).fetchall()
    except DBAPIError:
        return None


_available_cache = {"ok": False}


def sea_available(db: Session) -> bool:
    """The CS sea tables exist (052 applied). A positive answer is cached for the process."""
    if _available_cache["ok"]:
        return True
    try:
        names = set(sa_inspect(db.get_bind()).get_table_names())
    except Exception:  # noqa: BLE001 — an inspector failure means «not available», never a 500
        logger.exception("sea tables check failed")
        return False
    ok = all(t in names for t in SEA_TABLES)
    if ok:
        _available_cache["ok"] = True
    return ok


def require_available(db: Session) -> None:
    if not sea_available(db):
        raise SeaError(503, MSG_UNAVAILABLE)


# =====================================================================================================================
# locations-service reads (tolerant)
# =====================================================================================================================

@dataclass
class LocInfo:
    id: int
    name: Optional[str]
    image_url: Optional[str] = None
    is_port: bool = False
    is_sea_zone: bool = False
    port_zone_id: Optional[int] = None


def location_infos(db: Session, ids: Iterable[Optional[int]]) -> Dict[int, LocInfo]:
    ids = sorted({int(i) for i in ids if i})
    if not ids:
        return {}
    ph, params = core.in_params("l", ids)
    rows = _rows(db, f"SELECT id, name, image_url, is_port, is_sea_zone, port_sea_zone_id FROM Locations "
                     f"WHERE id IN ({ph})", params)
    if rows is not None:
        return {int(r[0]): LocInfo(int(r[0]), r[1], r[2], bool(r[3]), bool(r[4]),
                                   int(r[5]) if r[5] is not None else None) for r in rows}
    rows = _rows(db, f"SELECT id, name, image_url, is_port FROM Locations WHERE id IN ({ph})", params)
    if rows is not None:
        return {int(r[0]): LocInfo(int(r[0]), r[1], r[2], bool(r[3])) for r in rows}
    rows = _rows(db, f"SELECT id, name FROM Locations WHERE id IN ({ph})", params) or []
    return {int(r[0]): LocInfo(int(r[0]), r[1]) for r in rows}


def is_sea_zone(db: Session, location_id) -> bool:
    try:
        lid = int(location_id)
    except (TypeError, ValueError):
        return False
    info = location_infos(db, [lid]).get(lid)
    return bool(info is not None and info.is_sea_zone)


@dataclass
class ZoneGraph:
    adj: Dict[int, List[int]]
    zone_ids: Set[int]


def zone_graph(db: Session) -> ZoneGraph:
    """Adjacency of the sea zones (``LocationNeighbors`` rows between two ``is_sea_zone`` locations only)."""
    import caravan_route
    zones = _rows(db, "SELECT id FROM Locations WHERE is_sea_zone = 1")
    if not zones:
        return ZoneGraph({}, set())
    edges = _rows(db, "SELECT n.location_id, n.neighbor_id FROM LocationNeighbors n "
                      "JOIN Locations a ON a.id = n.location_id JOIN Locations b ON b.id = n.neighbor_id "
                      "WHERE a.is_sea_zone = 1 AND b.is_sea_zone = 1") or []
    return ZoneGraph(caravan_route.build_adjacency((r[0], r[1]) for r in edges), {int(r[0]) for r in zones})


def region_names(db: Session, location_ids: Iterable[Optional[int]]) -> Dict[int, Tuple[Optional[str], Optional[str]]]:
    """``{location_id: (region_name, country_name)}`` through the district / parent chain."""
    out: Dict[int, Tuple[Optional[str], Optional[str]]] = {}
    for lid in sorted({int(i) for i in location_ids if i}):
        region_id, country_id = econ_ledger.resolve_location(db, lid)
        region = country = None
        if region_id:
            row = db.execute(text("SELECT name FROM Regions WHERE id = :r"), {"r": int(region_id)}).first()
            region = row[0] if row is not None else None
        if country_id:
            row = db.execute(text("SELECT name FROM Countries WHERE id = :c"), {"c": int(country_id)}).first()
            country = row[0] if row is not None else None
        out[lid] = (region, country)
    return out


def max_post_id(db: Session) -> int:
    rows = _rows(db, "SELECT COALESCE(MAX(id), 0) FROM posts")
    return _i(rows[0][0]) if rows else 0


# =====================================================================================================================
# settings, ships, stops, passes
# =====================================================================================================================

@dataclass
class SeaParams:
    sailor_post_min_chars: int = sea_core.DEFAULT_SAILOR_POST_MIN_CHARS
    stowaway_base_pct: float = 60.0
    stowaway_wanted_points: int = 50
    path_max_zones: int = sea_core.DEFAULT_PATH_MAX_ZONES
    # FEAT-214 storms and raids (053; defaults = the migration defaults)
    storm_min_minutes: int = 60
    storm_max_minutes: int = 180
    storm_move_pct: Decimal = Decimal("30")
    storm_max_moves: int = 2
    storm_slow_mult: Decimal = Decimal("2.00")
    storm_drift_pct: Decimal = Decimal("15")
    storm_hp_pct: Decimal = Decimal("10")
    storm_stamina_pct: Decimal = Decimal("20")
    storm_postpone_minutes: int = 15
    storm_postpone_max_minutes: int = 240
    storm_sailor_relief_pct: Decimal = Decimal("50")
    season_mult_spring: Decimal = Decimal("1.00")
    season_mult_summer: Decimal = Decimal("0.50")
    season_mult_autumn: Decimal = Decimal("1.50")
    season_mult_winter: Decimal = Decimal("2.00")
    raid_chance_mult: Decimal = Decimal("1.00")
    raid_hold_max_minutes: int = 120
    raid_repelled_delay_minutes: int = 5


_PARAM_INTS = ("storm_min_minutes", "storm_max_minutes", "storm_max_moves", "storm_postpone_minutes",
               "storm_postpone_max_minutes", "raid_hold_max_minutes", "raid_repelled_delay_minutes")
_PARAM_DECIMALS = ("storm_move_pct", "storm_slow_mult", "storm_drift_pct", "storm_hp_pct", "storm_stamina_pct",
                   "storm_sailor_relief_pct", "season_mult_spring", "season_mult_summer", "season_mult_autumn",
                   "season_mult_winter", "raid_chance_mult")


def _dec(value, default: Decimal) -> Decimal:
    if value is None:
        return default
    return value if isinstance(value, Decimal) else Decimal(str(value))


def load_params(db: Session) -> SeaParams:
    row = db.get(models.SeaSetting, 1)
    if row is None:
        return SeaParams()
    defaults = SeaParams()
    extra = {name: (int(getattr(row, name)) if getattr(row, name, None) is not None else getattr(defaults, name))
             for name in _PARAM_INTS}
    extra.update({name: _dec(getattr(row, name, None), getattr(defaults, name)) for name in _PARAM_DECIMALS})
    return SeaParams(sailor_post_min_chars=_i(row.sailor_post_min_chars),
                     stowaway_base_pct=float(row.stowaway_base_pct or 0),
                     stowaway_wanted_points=_i(row.stowaway_wanted_points),
                     path_max_zones=_i(row.path_max_zones) or sea_core.DEFAULT_PATH_MAX_ZONES, **extra)


def get_ship(db: Session, ship_id: int, *, lock: bool = False) -> Optional["models.SeaShip"]:
    q = db.query(models.SeaShip).filter(models.SeaShip.id == int(ship_id))
    return (_locked(q, db) if lock else q).first()


def ship_by_deck(db: Session, location_id) -> Optional["models.SeaShip"]:
    try:
        lid = int(location_id)
    except (TypeError, ValueError):
        return None
    return db.query(models.SeaShip).filter(models.SeaShip.deck_location_id == lid).first()


def load_stops(db: Session, ship_id: int) -> List["models.SeaShipStop"]:
    return (db.query(models.SeaShipStop).filter(models.SeaShipStop.ship_id == int(ship_id))
            .order_by(models.SeaShipStop.idx).all())


def active_passes(db: Session, ship_id: int, *, lock: bool = False) -> List["models.SeaPass"]:
    q = (db.query(models.SeaPass).filter(models.SeaPass.ship_id == int(ship_id),
                                         models.SeaPass.status == sea_core.PASS_ACTIVE)
         .order_by(models.SeaPass.id))
    return (_locked(q, db) if lock else q).all()


def next_trip(ship: "models.SeaShip") -> int:
    return _i(ship.trip_no) + 1


def is_entitled(passes: Iterable["models.SeaPass"], character_id: int, trip: int) -> bool:
    return any(int(p.character_id) == int(character_id)
               and sea_core.entitled(p.kind, p.status, p.first_trip, p.last_trip, trip) for p in passes)


def character_entitled(db: Session, ship: "models.SeaShip", character_id: int) -> bool:
    """An active pass of the character covering the next departure (docked ship, §3.5)."""
    k = next_trip(ship)
    row = db.query(models.SeaPass.id).filter(
        models.SeaPass.ship_id == int(ship.id), models.SeaPass.character_id == int(character_id),
        models.SeaPass.status == sea_core.PASS_ACTIVE, models.SeaPass.first_trip <= k,
        models.SeaPass.last_trip >= k).first()
    return row is not None


def _has_open_pass(passes: Iterable["models.SeaPass"], character_id: int, from_trip: int) -> bool:
    """An active pass of the character that covers ``from_trip`` or a later trip (one pass per trip, §3.5)."""
    return any(int(p.character_id) == int(character_id) and p.status == sea_core.PASS_ACTIVE
               and _i(p.last_trip) >= int(from_trip) for p in passes)


def _taken(passes: Iterable["models.SeaPass"], kind: str) -> Dict[int, int]:
    """``{trip: active passes of that kind covering it}`` (only future trips matter to the callers)."""
    out: Dict[int, int] = {}
    for p in passes:
        if p.kind != kind or p.status != sea_core.PASS_ACTIVE:
            continue
        for t in range(_i(p.first_trip), _i(p.last_trip) + 1):
            out[t] = out.get(t, 0) + 1
    return out


# =====================================================================================================================
# the plan of a ship (next trips + zone paths)
# =====================================================================================================================

@dataclass
class PlannedLeg:
    trip: int
    from_idx: int
    to_idx: int
    from_port: int
    to_port: int
    path: List[int]
    direction: int = sea_core.DIRECTION_FORWARD     # direction of the move to ``to_idx`` (the sea pass stores it)

    @property
    def zones(self) -> int:
        return len(self.path)


@dataclass
class Plan:
    legs: List[PlannedLeg]
    problem: Optional[str]                # why the plan stopped early (blocked reason), None when complete
    stops: List["models.SeaShipStop"]
    locs: Dict[int, LocInfo]
    graph: ZoneGraph


def valid_stop_indexes(stops: Sequence["models.SeaShipStop"], locs: Dict[int, LocInfo],
                       zone_ids: Set[int]) -> List[int]:
    """Stops whose port still exists, is a port and opens to an existing sea zone (§3.10)."""
    out = []
    for i, s in enumerate(stops):
        info = locs.get(int(s.port_location_id))
        if info is not None and info.is_port and info.port_zone_id and int(info.port_zone_id) in zone_ids:
            out.append(i)
    return out


def plan(db: Session, ship: "models.SeaShip", count: int, *, params: Optional[SeaParams] = None,
         stops: Optional[List["models.SeaShipStop"]] = None, graph: Optional[ZoneGraph] = None) -> Plan:
    """The next ``count`` trips of the ship (from ``trip_no + 1``) with their zone paths; the first leg starts at
    the docked stop (docked) or at the stop the ship heads to (sailing). Invalid stops are skipped; the plan stops at
    the first leg without a path."""
    params = params or load_params(db)
    stops = stops if stops is not None else load_stops(db, ship.id)
    graph = graph or zone_graph(db)
    locs = location_infos(db, [s.port_location_id for s in stops] + [ship.current_zone_id])
    n = len(stops)
    if n < 2:
        return Plan([], sea_core.BLOCKED_NO_VALID_STOP, stops, locs, graph)
    valid = valid_stop_indexes(stops, locs, graph.zone_ids)
    if ship.status == sea_core.STATUS_SAILING and ship.next_stop_index is not None:
        start = _i(ship.next_stop_index)
    else:
        start = _i(ship.stop_index)
    start = min(max(0, start), n - 1)
    trips = sea_core.future_trips(start, _i(ship.direction) or 1, n, bool(ship.is_loop), next_trip(ship), count,
                                  valid)
    if not trips:
        return Plan([], sea_core.BLOCKED_NO_VALID_STOP, stops, locs, graph)
    overrides = {int(s.idx): s.path_override for s in stops}
    legs: List[PlannedLeg] = []
    problem = None
    for t in trips:
        from_port = int(stops[t.from_idx].port_location_id)
        to_port = int(stops[t.to_idx].port_location_id)
        from_info = locs.get(from_port)
        start_zone = from_info.port_zone_id if from_info is not None and t.from_idx in valid else None
        if start_zone is None and not legs:
            start_zone = ship.current_zone_id     # the docked port lost its zone: sail from where the ship is
        goal_zone = locs[to_port].port_zone_id if to_port in locs else None
        override = sea_core.override_for(t.from_idx, t.to_idx, n, bool(ship.is_loop), overrides) \
            if t.adjacent else None
        path, leg_problem, _used = sea_core.leg_path(graph.adj, graph.zone_ids, start_zone, goal_zone, override,
                                                     params.path_max_zones)
        if path is None:
            problem = sea_core.BLOCKED_NO_PATH
            break
        legs.append(PlannedLeg(t.trip, t.from_idx, t.to_idx, from_port, to_port, path, t.direction))
    return Plan(legs, problem, stops, locs, graph)


def first_departure(ship: "models.SeaShip", now: datetime) -> Optional[datetime]:
    """When the next trip (``trip_no + 1``) is planned to depart (None while switched off)."""
    if not ship.is_active:
        return None
    if ship.status == sea_core.STATUS_DOCKED:
        if ship.departs_at is None:
            return None
        return max(ship.departs_at, now)
    arrival = current_arrival(ship)
    if arrival is None:
        return None
    return max(arrival, now) + timedelta(minutes=_i(ship.boarding_minutes))


def current_arrival(ship: "models.SeaShip") -> Optional[datetime]:
    if ship.status != sea_core.STATUS_SAILING:
        return None
    path = ship.leg_path if isinstance(ship.leg_path, list) else []
    return sea_core.current_leg_arrival(ship.next_zone_at, len(path), _i(ship.leg_pos), _i(ship.zone_minutes))


# =====================================================================================================================
# public views
# =====================================================================================================================

def _captain_public(db: Session, ship: "models.SeaShip") -> Optional[dict]:
    if not ship.captain_npc_id:
        return None
    npc = db.get(models.Character, int(ship.captain_npc_id))
    if npc is None or not npc.is_npc or npc.npc_role != sea_core.CAPTAIN_ROLE or npc.npc_status == NPC_DEAD:
        return None
    return {"id": int(npc.id), "name": npc.name, "avatar": npc.avatar}


def _ref(locs: Dict[int, LocInfo], location_id) -> Optional[dict]:
    if not location_id:
        return None
    info = locs.get(int(location_id))
    return {"id": int(location_id), "name": info.name if info is not None else None}


def ship_public(db: Session, ship: "models.SeaShip", stops: Sequence["models.SeaShipStop"],
                now: Optional[datetime] = None) -> dict:
    now = now or now_utc()
    locs = location_infos(db, [s.port_location_id for s in stops]
                          + [ship.docked_port_id, ship.next_port_id, ship.current_zone_id])
    zone = None
    if ship.current_zone_id:
        sea_name = region_names(db, [ship.current_zone_id]).get(int(ship.current_zone_id), (None, None))[0]
        info = locs.get(int(ship.current_zone_id))
        zone = {"id": int(ship.current_zone_id), "name": info.name if info is not None else None,
                "sea_name": sea_name}
    docked = ship.status == sea_core.STATUS_DOCKED
    return {
        "id": int(ship.id),
        "name": ship.name,
        "captain": _captain_public(db, ship),
        "deck_location_id": int(ship.deck_location_id),
        "status": ship.status,
        "is_active": bool(ship.is_active),
        "docked_port": _ref(locs, ship.docked_port_id) if docked else None,
        "next_port": _ref(locs, ship.next_port_id) if not docked else None,
        "current_zone": zone,
        "departs_at": ship.departs_at if docked and ship.is_active else None,
        "arrives_at": current_arrival(ship),
        "stops": [{"index": int(s.idx), "port_id": int(s.port_location_id),
                   "port_name": (locs.get(int(s.port_location_id)) or LocInfo(0, None)).name} for s in stops],
        "direction": _i(ship.direction) or 1,
        "is_loop": bool(ship.is_loop),
        "server_now": now,
        **sea_state_public(db, ship, zone, docked, now),
    }


def sea_state_public(db: Session, ship: "models.SeaShip", zone: Optional[dict], docked: bool,
                     now: datetime) -> dict:
    """FEAT-214 §3.10: ``storm`` over the current zone, ``departure_postponed``, ``raid`` (tolerant of a missing 053:
    no storm, no raid)."""
    import sea_raid_crud  # late: both modules import this one
    import sea_weather
    storm = sea_weather.storm_at(db, ship.current_zone_id, now)
    return {
        "storm": {"zone_id": storm.zone_id, "zone_name": zone["name"] if zone else None, "ends_at": storm.ends_at}
        if storm is not None else None,
        "departure_postponed": bool(docked and getattr(ship, "storm_hold_since", None) is not None),
        "raid": sea_raid_crud.raid_state(db, ship),
    }


def pass_out(p: "models.SeaPass", ship: Optional["models.SeaShip"]) -> dict:
    valid_now = False
    if ship is not None and p.status == sea_core.PASS_ACTIVE:
        trip = _i(ship.trip_no) if ship.status == sea_core.STATUS_SAILING else next_trip(ship)
        valid_now = sea_core.covers(p.first_trip, p.last_trip, trip)
    return {
        "id": int(p.id), "ship_id": int(p.ship_id), "kind": p.kind, "status": p.status,
        "first_trip": _i(p.first_trip), "last_trip": _i(p.last_trip),
        "from_port_id": int(p.from_port_id), "from_name": p.from_name,
        "to_port_id": int(p.to_port_id), "to_name": p.to_name,
        "fare": _i(p.fare), "created_at": p.created_at, "valid_now": valid_now,
    }


def my_passes(db: Session, ship: "models.SeaShip", character_id: int) -> List[dict]:
    rows = (db.query(models.SeaPass).filter(models.SeaPass.ship_id == int(ship.id),
                                            models.SeaPass.character_id == int(character_id),
                                            models.SeaPass.status == sea_core.PASS_ACTIVE)
            .order_by(models.SeaPass.first_trip, models.SeaPass.id).all())
    return [pass_out(p, ship) for p in rows]


# =====================================================================================================================
# the Captain (S1–S3) and the stowaway attempt (S4)
# =====================================================================================================================

@dataclass(frozen=True)
class CaptainContext:
    character_id: int
    user_id: int
    npc_id: int
    location_id: int
    ship_id: int


def _player(db: Session, character_id: int, user_id: int) -> "models.Character":
    character = db.query(models.Character).filter(models.Character.id == int(character_id)).first()
    if character is None:
        raise SeaError(404, MSG_CHARACTER_NOT_FOUND)
    if character.user_id is None or int(character.user_id) != int(user_id):
        raise SeaError(403, MSG_NOT_OWNER)
    if character.is_npc:
        raise SeaError(403, MSG_NOT_PLAYER)
    return character


def require_owner(db: Session, character_id: int, user_id: int) -> "models.Character":
    return _player(db, character_id, user_id)


def resolve_captain(db: Session, npc_id: int, character_id: int, user_id: int) -> CaptainContext:
    """Owner + player, the Captain exists / role / alive / conscious / bound to a ship, the character stands at
    the Captain's location (in port while docked, on the deck at sea). Raises SeaError."""
    require_available(db)
    character = _player(db, character_id, user_id)
    npc = db.query(models.Character).filter(models.Character.id == int(npc_id)).first()
    if npc is None or not npc.is_npc or npc.npc_role != sea_core.CAPTAIN_ROLE or npc.npc_status == NPC_DEAD \
            or npc.current_location_id is None \
            or activity_lock.lock_for_character(npc)["reason"] == activity_lock.REASON_UNCONSCIOUS:
        raise SeaError(404, MSG_CAPTAIN_NOT_FOUND)
    ship = db.query(models.SeaShip).filter(models.SeaShip.captain_npc_id == int(npc.id)).first()
    if ship is None:
        raise SeaError(404, MSG_CAPTAIN_NO_SHIP)
    if character.current_location_id is None or int(character.current_location_id) != int(npc.current_location_id):
        raise SeaError(400, MSG_NOT_AT_CAPTAIN)
    return CaptainContext(int(character.id), int(user_id), int(npc.id), int(npc.current_location_id), int(ship.id))


def require_npc_tier(db: Session, ctx: CaptainContext) -> None:
    import reputation_crud
    reputation_crud.require_npc_tier(db, ctx.character_id, ctx.npc_id)


def _lock_text(character: "models.Character") -> Optional[str]:
    return activity_lock.lock_message(activity_lock.lock_for_character(character))


def _stowaway_state(ship: "models.SeaShip", character: "models.Character", legs: Sequence[PlannedLeg],
                    has_pass: bool, lock_text: Optional[str]) -> Tuple[bool, Optional[str]]:
    if lock_text:
        return False, lock_text
    if ship.status != sea_core.STATUS_DOCKED:
        return False, MSG_SHIP_AT_SEA
    loc = _i(character.current_location_id)
    if loc not in (_i(ship.docked_port_id), _i(ship.deck_location_id)):
        return False, MSG_NOT_IN_PORT
    if not ship.is_active or not legs:
        return False, MSG_SHIP_IDLE
    if has_pass:
        return False, MSG_ALREADY_PASS
    return True, None


def captain_view(db: Session, ctx: CaptainContext, now: Optional[datetime] = None) -> dict:
    """S1: the ship, its next stops with fares / ETAs / seats, the sailor job, the stowaway option, own passes."""
    now = now or now_utc()
    params = load_params(db)
    ship = get_ship(db, ctx.ship_id)
    if ship is None:
        raise SeaError(404, MSG_SHIP_NOT_FOUND)
    character = db.get(models.Character, ctx.character_id)
    stops = load_stops(db, ship.id)
    pl = plan(db, ship, max(0, len(stops) - 1), params=params, stops=stops)
    passes = active_passes(db, ship.id)
    k = next_trip(ship)
    lock_text = _lock_text(character)
    has_pass = _has_open_pass(passes, ctx.character_id, k)
    base_reason = lock_text or (MSG_SHIP_IDLE if not ship.is_active or not pl.legs else None) \
        or (MSG_ALREADY_PASS if has_pass else None)

    tickets = _taken(passes, sea_core.KIND_TICKET)
    arrival_times = sea_core.arrivals(first_departure(ship, now), [leg.zones for leg in pl.legs],
                                      _i(ship.zone_minutes), _i(ship.boarding_minutes))
    names = region_names(db, [leg.to_port for leg in pl.legs])
    start_port = pl.legs[0].from_port if pl.legs else None
    seen: Set[int] = set()
    destinations = []
    zones = 0
    for i, leg in enumerate(pl.legs):
        zones += leg.zones
        if leg.to_port == start_port or leg.to_port in seen:
            continue
        seen.add(leg.to_port)
        price = sea_core.fare(ship.fare_base, ship.fare_per_zone, zones)
        free = sea_core.seats_left(_i(ship.capacity), tickets, range(k, leg.trip + 1))
        reason = base_reason or (MSG_NO_SEATS if free <= 0 else None)
        region, country = names.get(leg.to_port, (None, None))
        info = pl.locs.get(leg.to_port)
        destinations.append({
            "to_trip": leg.trip, "stop_index": leg.to_idx, "port_id": leg.to_port,
            "port_name": info.name if info is not None else None, "region_name": region, "country_name": country,
            "zones": zones, "fare": price, "eta": arrival_times[i], "seats_left": free,
            "can_buy": reason is None, "reason": reason,
        })

    crew = _i(ship.crew_slots)
    slots_left = max(0, crew - _taken(passes, sea_core.KIND_SAILOR).get(k, 0))
    sailor_reason = base_reason or (MSG_HIRING_OFF if crew <= 0 else None) \
        or (MSG_NO_CREW_SLOTS if slots_left <= 0 else None)
    can_try, stow_reason = _stowaway_state(ship, character, pl.legs, has_pass, lock_text)
    return {
        "npc_id": ctx.npc_id,
        "ship": ship_public(db, ship, stops, now),
        "balance": _i(character.currency_balance),
        "destinations": destinations,
        "sailor": {"slots_left": slots_left, "min_chars": params.sailor_post_min_chars,
                   "can_hire": sailor_reason is None, "reason": sailor_reason},
        "stowaway": {"can_try": can_try, "reason": stow_reason},
        "my_passes": my_passes(db, ship, ctx.character_id),
    }


@dataclass
class PassResult:
    pass_row: "models.SeaPass"
    ship: "models.SeaShip"
    notices: List[law_notify.Notice] = field(default_factory=list)


def _lock_character(db: Session, character_id: int) -> "models.Character":
    character = _locked(db.query(models.Character).filter(models.Character.id == int(character_id)), db).first()
    if character is None:
        raise SeaError(404, MSG_CHARACTER_NOT_FOUND)
    return character


def _log(db: Session, character_id: int, message: str, **meta) -> None:
    db.add(models.CharacterLog(character_id=int(character_id), event_type=LOG_EVENT_TYPE, description=message,
                               metadata_=meta))


def notice(user_id, message: str, character_id: int, ship_id: int, event: str, **data) -> law_notify.Notice:
    return law_notify.Notice(user_id, message, WS_SEA, law_notify.CATEGORY_PROGRESS,
                             {"character_id": int(character_id), "ship_id": int(ship_id), "event": event, **data})


def _prepare_pass(db: Session, ctx: CaptainContext, ship_id: int) -> Tuple["models.SeaShip", Plan,
                                                                         List["models.SeaPass"]]:
    """Locks ship → passes; the common refusals of a ticket / a sailor job (§3.7 eligibility)."""
    require_available(db)
    if int(ship_id) != int(ctx.ship_id):
        raise SeaError(400, MSG_OTHER_SHIP)
    ship = get_ship(db, ship_id, lock=True)
    if ship is None:
        raise SeaError(404, MSG_SHIP_NOT_FOUND)
    passes = active_passes(db, ship.id, lock=True)
    character = db.get(models.Character, ctx.character_id)
    lock_text = _lock_text(character)
    if lock_text:
        raise SeaError(409, lock_text)
    # the Captain may have moved (departure / arrival) since the context was resolved
    npc = db.get(models.Character, ctx.npc_id)
    if npc is None or npc.current_location_id is None or character.current_location_id is None \
            or int(npc.current_location_id) != int(character.current_location_id):
        raise SeaError(400, MSG_NOT_AT_CAPTAIN)
    stops = load_stops(db, ship.id)
    pl = plan(db, ship, max(0, len(stops) - 1), stops=stops)
    if not ship.is_active or not pl.legs:
        raise SeaError(409, MSG_SHIP_IDLE)
    if _has_open_pass(passes, ctx.character_id, next_trip(ship)):
        raise SeaError(409, MSG_ALREADY_PASS)
    return ship, pl, passes


def buy_ticket(db: Session, ctx: CaptainContext, ship_id: int, to_trip: int,
               now: Optional[datetime] = None) -> PassResult:
    """S2: a ticket for trips ``trip_no+1 .. to_trip`` (no commit). Lock order ship → passes → character →
    accounts. Insufficient money → SeaError(402, {...}) (the caller rolls back)."""
    now = now or now_utc()
    ship, pl, passes = _prepare_pass(db, ctx, ship_id)
    k = next_trip(ship)
    covered = [leg for leg in pl.legs if leg.trip <= int(to_trip)]
    if not covered or covered[-1].trip != int(to_trip) or covered[-1].to_port == covered[0].from_port:
        raise SeaError(409, MSG_BAD_TRIP)
    tickets = _taken(passes, sea_core.KIND_TICKET)
    if sea_core.seats_left(_i(ship.capacity), tickets, range(k, int(to_trip) + 1)) <= 0:
        raise SeaError(409, MSG_NO_SEATS)
    zones = sum(leg.zones for leg in covered)
    price = sea_core.fare(ship.fare_base, ship.fare_per_zone, zones)
    from_port, to_port = covered[0].from_port, covered[-1].to_port
    character = _lock_character(db, ctx.character_id)
    from_info, to_info = pl.locs.get(from_port), pl.locs.get(to_port)
    row = models.SeaPass(
        ship_id=int(ship.id), character_id=int(character.id), kind=sea_core.KIND_TICKET, first_trip=k,
        last_trip=int(to_trip), from_port_id=from_port, to_port_id=to_port,
        from_name=from_info.name if from_info is not None else None,
        to_name=to_info.name if to_info is not None else None,
        zones=zones, fare=price, status=sea_core.PASS_ACTIVE, created_at=now)
    db.add(row)
    db.flush()
    balance = _i(character.currency_balance)
    if price > 0:
        if balance < price:
            raise _insufficient(db, price, balance)
        try:
            result = econ_ledger.post_operation(
                db, op_type=core.OP_SEA_FARE,
                legs=[econ_ledger.Leg(econ_ledger.AccountRef.character(character.id),
                                      econ_ledger.treasury_for_location(db, from_port), price)],
                source_service=SOURCE_SERVICE, location_id=from_port, idempotency_key=f"sea_fare:{int(row.id)}",
                metadata={"ship_id": int(ship.id), "pass_id": int(row.id), "from_port_id": from_port,
                          "to_port_id": to_port, "first_trip": k, "last_trip": int(to_trip), "zones": zones})
        except econ_ledger.InsufficientFunds:
            raise _insufficient(db, price, balance)
        row.fare_op_id = result.operation_id
    to_name = row.to_name or "—"
    message = f"Билет на корабль «{ship.name}» до «{to_name}» куплен"
    _log(db, character.id, message, ship_id=int(ship.id), pass_id=int(row.id), kind=row.kind, fare=price)
    db.flush()
    return PassResult(row, ship, [notice(character.user_id, message, character.id, ship.id, "ticket",
                                         pass_id=int(row.id))])


def _insufficient(db: Session, price: int, balance: int) -> SeaError:
    import crud
    return SeaError(402, {"error": "insufficient_gold", "message": crud.insufficient_funds_message(db),
                          "required": int(price), "balance": int(balance)})


def hire_sailor(db: Session, ctx: CaptainContext, ship_id: int, now: Optional[datetime] = None) -> PassResult:
    """S3: a free sailor job for the next trip; only posts on the deck written after the hire count (no commit)."""
    now = now or now_utc()
    ship, pl, passes = _prepare_pass(db, ctx, ship_id)
    k = next_trip(ship)
    crew = _i(ship.crew_slots)
    if crew <= 0:
        raise SeaError(409, MSG_HIRING_OFF)
    if _taken(passes, sea_core.KIND_SAILOR).get(k, 0) >= crew:
        raise SeaError(409, MSG_NO_CREW_SLOTS)
    leg = pl.legs[0]
    character = _lock_character(db, ctx.character_id)
    from_info, to_info = pl.locs.get(leg.from_port), pl.locs.get(leg.to_port)
    row = models.SeaPass(
        ship_id=int(ship.id), character_id=int(character.id), kind=sea_core.KIND_SAILOR, first_trip=k, last_trip=k,
        from_port_id=leg.from_port, to_port_id=leg.to_port,
        from_name=from_info.name if from_info is not None else None,
        to_name=to_info.name if to_info is not None else None,
        zones=leg.zones, fare=0, post_floor_id=max_post_id(db), status=sea_core.PASS_ACTIVE, created_at=now)
    db.add(row)
    db.flush()
    min_chars = load_params(db).sailor_post_min_chars
    message = (f"Вы нанялись матросом на корабль «{ship.name}» до «{row.to_name or '—'}». До отплытия напишите "
               f"на палубе пост от {min_chars} символов, иначе капитан высадит вас")
    _log(db, character.id, message, ship_id=int(ship.id), pass_id=int(row.id), kind=row.kind)
    db.flush()
    return PassResult(row, ship, [notice(character.user_id, message, character.id, ship.id, "sailor",
                                         pass_id=int(row.id))])


def sneak(db: Session, character_id: int, user_id: int, ship_id: int, now: Optional[datetime] = None) -> PassResult:
    """S4: a stowaway attempt for the next trip — no Captain, no gate; the character stands in the ship's port or
    already on its deck (no commit). The crew's check happens at departure (sea pass)."""
    now = now or now_utc()
    require_available(db)
    _player(db, character_id, user_id)
    ship = get_ship(db, ship_id, lock=True)
    if ship is None:
        raise SeaError(404, MSG_SHIP_NOT_FOUND)
    passes = active_passes(db, ship.id, lock=True)
    character = _lock_character(db, character_id)
    stops = load_stops(db, ship.id)
    pl = plan(db, ship, 1, stops=stops)
    k = next_trip(ship)
    ok, reason = _stowaway_state(ship, character, pl.legs, _has_open_pass(passes, character_id, k),
                                 _lock_text(character))
    if not ok:
        status = 400 if reason == MSG_NOT_IN_PORT else 409
        raise SeaError(status, reason)
    leg = pl.legs[0]
    from_info, to_info = pl.locs.get(leg.from_port), pl.locs.get(leg.to_port)
    row = models.SeaPass(
        ship_id=int(ship.id), character_id=int(character.id), kind=sea_core.KIND_STOWAWAY, first_trip=k, last_trip=k,
        from_port_id=leg.from_port, to_port_id=leg.to_port,
        from_name=from_info.name if from_info is not None else None,
        to_name=to_info.name if to_info is not None else None,
        zones=leg.zones, fare=0, status=sea_core.PASS_ACTIVE, created_at=now)
    db.add(row)
    db.flush()
    _log(db, character.id, f"Попытка пробраться на корабль «{ship.name}» без билета", ship_id=int(ship.id),
         pass_id=int(row.id), kind=row.kind)
    db.flush()
    return PassResult(row, ship, [])


# =====================================================================================================================
# the deck header (S5)
# =====================================================================================================================

def deck_view(db: Session, location_id: int, character_id: int, user_id: int,
              now: Optional[datetime] = None) -> dict:
    now = now or now_utc()
    require_available(db)
    _player(db, character_id, user_id)
    ship = ship_by_deck(db, location_id)
    if ship is None:
        raise SeaError(404, MSG_NOT_A_DECK)
    stops = load_stops(db, ship.id)
    S = models.SeaShip
    if ship.status == sea_core.STATUS_SAILING and ship.current_zone_id:
        near_q = db.query(S.id, S.name).filter(S.status == sea_core.STATUS_SAILING,
                                               S.current_zone_id == int(ship.current_zone_id))
    elif ship.status == sea_core.STATUS_DOCKED and ship.docked_port_id:
        near_q = db.query(S.id, S.name).filter(S.status == sea_core.STATUS_DOCKED,
                                               S.docked_port_id == int(ship.docked_port_id))
    else:
        near_q = None
    nearby = [] if near_q is None else [{"id": int(r[0]), "name": r[1]}
                                        for r in near_q.filter(S.id != int(ship.id)).order_by(S.id).all()]
    # FEAT-215 §3.9: caravan escorts ride hidden inside the wagon — not counted as passengers
    passengers = db.query(models.Character.id).filter(
        models.Character.current_location_id == int(ship.deck_location_id),
        models.Character.is_npc.is_(False), models.Character.escort_caravan_id.is_(None)).count()
    return {"ship": ship_public(db, ship, stops, now), "ships_nearby": nearby, "passengers_count": int(passengers),
            "my_passes": my_passes(db, ship, character_id),
            "sailor_post_min_chars": int(load_params(db).sailor_post_min_chars),
            "cargo": deck_cargo(db, ship)}


def deck_cargo(db: Session, ship: "models.SeaShip") -> List[dict]:
    """FEAT-215 §3.9: the caravans in the hold for the deck header — goods group and landing port only."""
    import sea_cargo  # local: sea_cargo imports this module
    ids = sea_cargo.aboard_ids(db, ship.id)
    if not ids:
        return []
    rows = (db.query(models.EconCaravan.id, models.EconCaravan.group_code, models.EconCaravan.sea_alight_port_id)
            .filter(models.EconCaravan.id.in_(ids)).order_by(models.EconCaravan.id).all())
    codes = sorted({r[1] for r in rows if r[1]})
    groups: Dict[str, Optional[str]] = {}
    if codes:
        ph, params = core.in_params("g", codes)
        groups = {r[0]: r[1] for r in db.execute(text(
            f"SELECT code, name FROM econ_goods_groups WHERE code IN ({ph})"), params).fetchall()}
    locs = location_infos(db, [r[2] for r in rows])
    return [{"caravan_id": int(r[0]), "group_name": groups.get(r[1]) or r[1],
             "alight_port_name": locs[int(r[2])].name if r[2] and int(r[2]) in locs else None} for r in rows]


# =====================================================================================================================
# moves: the authoritative passage check of CS update_location (§3.6, G1 / G2) and teleport targets (G3)
# =====================================================================================================================

def _int_or_none(value) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def lock_ships_for_move(db: Session, current_location_id, new_location_id) -> List["models.SeaShip"]:
    """Lock (asc id) the ships whose deck is the current or the new location — taken BEFORE the character row
    (lock order ship → character, the same as the departure). Empty without the sea tables."""
    ids = sorted({i for i in (_int_or_none(current_location_id), _int_or_none(new_location_id)) if i})
    if not ids or not sea_available(db):
        return []
    q = (db.query(models.SeaShip).filter(models.SeaShip.deck_location_id.in_(ids)).order_by(models.SeaShip.id))
    return _locked(q, db).all()


def move_refusal(db: Session, character: "models.Character", current_location_id, new_location_id,
                 ships: Sequence["models.SeaShip"]) -> Optional[str]:
    """Russian refusal of a player move, or None. A sea zone is never a destination; a deck is entered only from
    the port where its ship is docked, while active, with a pass for the next trip; a deck is left only to the
    docked port."""
    cur, new = _int_or_none(current_location_id), _int_or_none(new_location_id)
    if new is None or cur == new:
        return None
    if is_sea_zone(db, new):
        return MSG_OPEN_SEA
    by_deck = {int(s.deck_location_id): s for s in ships}
    if cur is not None and cur in by_deck:
        ship = by_deck[cur]
        if ship.status != sea_core.STATUS_DOCKED or not ship.docked_port_id:
            return MSG_AT_SEA_NO_LANDING
        if int(ship.docked_port_id) != new:
            return MSG_ONLY_TO_PORT
        return None
    if new in by_deck:
        ship = by_deck[new]
        if ship.status != sea_core.STATUS_DOCKED or not ship.docked_port_id or cur != int(ship.docked_port_id):
            return MSG_SHIP_GONE
        if not ship.is_active:
            return MSG_SHIP_OFF
        if not character_entitled(db, ship, int(character.id)):
            return MSG_NEED_PASS
    return None


def teleport_target_refusal(db: Session, location_id) -> Optional[str]:
    """G3: a teleport target (teleport link / home scroll) can't be a deck or a sea zone."""
    lid = _int_or_none(location_id)
    if lid is None:
        return None
    if is_sea_zone(db, lid):
        return MSG_TELEPORT_TARGET
    if sea_available(db) and ship_by_deck(db, lid) is not None:
        return MSG_TELEPORT_TARGET
    return None


# =====================================================================================================================
# landing (used by the sea pass and the ship admin, §3.9 / §3.10)
# =====================================================================================================================

@dataclass
class AshoreResult:
    character_id: int
    location_id: int
    encounter: object = None
    slipped: bool = False


def starting_location(db: Session) -> Optional[int]:
    rows = _rows(db, "SELECT id FROM Locations WHERE is_starting = 1 ORDER BY id LIMIT 1")
    return int(rows[0][0]) if rows else None


def landing_target(db: Session, ship: "models.SeaShip",
                   stops: Optional[Sequence["models.SeaShipStop"]] = None) -> Tuple[Optional[int], bool]:
    """``(location_id, is_fallback)``: the docked port (else the last port) when it still exists → any existing
    stop of the ship → the default starting location (§3.10). ``is_fallback`` = not the docked / last port."""
    stops = stops if stops is not None else load_stops(db, ship.id)
    preferred = ship.docked_port_id or ship.last_port_id
    candidates = [s.port_location_id for s in stops]
    locs = location_infos(db, [preferred] + candidates)
    if preferred and int(preferred) in locs:
        return int(preferred), False
    for pid in candidates:
        if pid and int(pid) in locs:
            return int(pid), True
    return starting_location(db), True


def put_ashore(db: Session, character: "models.Character", port_id: int, deck_id: Optional[int], reason: str,
               *, law_check: bool = True, now: Optional[datetime] = None) -> AshoreResult:
    """Move a (locked) player character from the deck to ``port_id`` (no commit): out of any house, a journal row,
    and — unless the target is a fallback — the law entry check of the port (``SOURCE_VOYAGE``) in the same
    transaction. The caller publishes the encounter / slip notices and calls the LS «left the location» cleanup
    after the commit."""
    character.current_location_id = int(port_id)
    character.house_room_id = None
    _log(db, character.id, reason, deck_location_id=_int_or_none(deck_id), port_location_id=int(port_id))
    db.flush()
    result = AshoreResult(int(character.id), int(port_id))
    if law_check:
        import law_crud  # local: law_crud imports most of the service
        entry = law_crud.check_entry(db, character, int(port_id), law_core.SOURCE_VOYAGE, now,
                                     from_location_id=_int_or_none(deck_id))
        result.encounter, result.slipped = entry.encounter, entry.slipped
    return result


def deck_players(db: Session, ship: "models.SeaShip", *, lock: bool = True) -> List["models.Character"]:
    q = (db.query(models.Character).filter(models.Character.current_location_id == int(ship.deck_location_id),
                                           models.Character.is_npc.is_(False)).order_by(models.Character.id))
    return (_locked(q, db) if lock else q).all()


def refund_pass(db: Session, row: "models.SeaPass", now: Optional[datetime] = None) -> bool:
    """Refund a (locked) active pass: every posting of its fare is reversed as one ``sea_refund`` op (untaxed,
    idempotent per pass; treasuries may go negative). Status → ``refunded``. Returns True when money moved."""
    now = now or now_utc()
    moved = False
    if row.fare_op_id:
        postings = db.execute(text(
            "SELECT fa.kind, fa.ref_id, ta.kind, ta.ref_id, p.amount FROM econ_postings p "
            "JOIN econ_accounts fa ON fa.id = p.from_account_id JOIN econ_accounts ta ON ta.id = p.to_account_id "
            "WHERE p.operation_id = :op ORDER BY p.id"), {"op": int(row.fare_op_id)}).fetchall()
        legs = [econ_ledger.Leg(econ_ledger.AccountRef(r[2], int(r[3])), econ_ledger.AccountRef(r[0], int(r[1])),
                                int(r[4]), core.LEG_REFUND) for r in postings if _i(r[4]) > 0]
        if legs:
            key = f"sea_refund:{int(row.id)}"
            try:
                result = econ_ledger.post_operation(
                    db, op_type=core.OP_SEA_REFUND, legs=legs, source_service=SOURCE_SERVICE,
                    location_id=int(row.from_port_id), idempotency_key=key, apply_tax=False,
                    metadata={"ship_id": int(row.ship_id), "pass_id": int(row.id),
                              "fare_op_id": int(row.fare_op_id)})
                row.refund_op_id = result.operation_id
                moved = True
            except econ_ledger.DuplicateOperation:
                op = db.execute(text(core.SQL_SELECT_OPERATION_BY_KEY), {"key": key}).first()
                row.refund_op_id = int(op[0]) if op is not None else row.refund_op_id
    row.status = sea_core.PASS_REFUNDED
    row.ended_at = now
    return moved


def refund_not_started(db: Session, ship: "models.SeaShip", now: Optional[datetime] = None) -> List[law_notify.Notice]:
    """Refund every active pass of the (locked) ship that has not started yet (``first_trip > trip_no``)."""
    now = now or now_utc()
    notices: List[law_notify.Notice] = []
    for row in active_passes(db, ship.id, lock=True):
        if _i(row.first_trip) <= _i(ship.trip_no):
            continue
        moved = refund_pass(db, row, now)
        if row.kind == sea_core.KIND_TICKET:
            user = db.execute(text("SELECT user_id FROM characters WHERE id = :c"), {"c": int(row.character_id)}).first()
            text_ = (f"Рейс корабля «{ship.name}» отменён — деньги за билет возвращены" if moved
                     else f"Рейс корабля «{ship.name}» отменён — ваш билет аннулирован")
            notices.append(notice(user[0] if user is not None else None, text_, row.character_id, ship.id,
                                  "refund", pass_id=int(row.id)))
    return notices


@dataclass
class LandingResult:
    ashore: List[AshoreResult] = field(default_factory=list)
    notices: List[law_notify.Notice] = field(default_factory=list)
    deck_location_id: Optional[int] = None
    kept_in_battle: List[int] = field(default_factory=list)     # FEAT-214: never moved out of a battle


def safe_land(db: Session, ship: "models.SeaShip", reason: str, now: Optional[datetime] = None,
              *, deck_location_id: Optional[int] = None) -> LandingResult:
    """Broken data (no valid stop / the deck vanished): every player on the deck → put ashore at
    :func:`landing_target`, not-started passes refunded, the ship switched off with ``blocked_reason`` (no
    commit; the ship row is locked by the caller). FEAT-214 §3.9: a player in an active battle is not moved (no
    notice; the sea pass lands him after the battle)."""
    now = now or now_utc()
    deck = int(deck_location_id or ship.deck_location_id)
    result = LandingResult(deck_location_id=deck)
    stops = load_stops(db, ship.id)
    target, fallback = landing_target(db, ship, stops)
    result.notices.extend(refund_not_started(db, ship, now))
    players = (_locked(db.query(models.Character).filter(models.Character.current_location_id == deck,
                                                         models.Character.is_npc.is_(False))
                       .order_by(models.Character.id), db).all())
    import sea_pass  # local: sea_pass imports this module
    fighting = [ch for ch in players if sea_pass.in_battle(db, ch.id)]
    if fighting:
        result.kept_in_battle = [int(ch.id) for ch in fighting]
        players = [ch for ch in players if int(ch.id) not in set(result.kept_in_battle)]
        logger.info("sea ship %s: safe landing keeps %s aboard (in a battle)", ship.id, result.kept_in_battle)
    if target is not None:
        names = location_infos(db, [target])
        port_name = names[target].name if target in names else "—"
        message = f"Корабль «{ship.name}» больше не может плыть — вас высадили в «{port_name}»"
        for ch in players:
            result.ashore.append(put_ashore(db, ch, target, deck, message, law_check=not fallback, now=now))
            result.notices.append(notice(ch.user_id, message, ch.id, ship.id, "safe_landing"))
    elif players:
        logger.error("sea ship %s: safe landing has no target for %d players", ship.id, len(players))
    ship.is_active = False
    ship.departs_at = None
    ship.blocked_reason = reason
    ship.updated_at = now
    return result
