"""FEAT-213 §3.10, §3.12, §3.13 — the ship admin (crud + router A1–A7, prefix ``/characters/admin/sea``).

* A1 ``GET    /ships``            (locations:read)   — every ship with its state, Captain, deck, stops, legs, passengers;
* A2 ``POST   /ships``            (locations:create) — create: docked at stop 0, departure in ``boarding_minutes``,
  the Captain is moved to the port in the same transaction;
* A3 ``PATCH  /ships/{id}``       (locations:update) — edit (the deck is immutable; stops / loop only while docked;
  a route change refunds not-started passes and completes started ones; switching off refunds not-started passes);
* A4 ``DELETE /ships/{id}``       (locations:delete) — only while docked: everyone on the deck is put ashore, passes
  refunded / completed, the ship and its stops are deleted (the deck location stays);
* A5 ``POST   /legs/preview``     (locations:read)   — zone paths of the legs of a stop list (with problems);
* A6 ``GET    /candidates``       (locations:read)   — free decks (locations of hidden countries without links) and
  free Captains (NPCs with the role «captain»);
* A7 ``GET/PUT /settings``        (locations:read / locations:update) — the sea numbers (+ FEAT-214 storm / raid
  numbers, optional on PUT);
* FEAT-214 §3.11: ``GET /weather`` (locations:read) — season, seas with their storm config, active storms, raids;
  ``PUT /seas/{region_id}``, ``POST /storms``, ``DELETE /storms/{id}`` (locations:update).

Existing permissions only (no RBAC migration, §3.16). Russian ``detail`` on every error; DB errors → 500 with a generic
text (details logged). Lock order ship → passes → characters (``sea_crud``). Notices and the LS cleanup of the deck
are done after the commit (``sea_pass.after_commit``).
"""

import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from pydantic import BaseModel, Field, validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import econ_core
import econ_ledger
import law_notify
import models
import sea_core
import sea_crud
import sea_pass
import sea_weather
from auth_http import UserRead, require_permission
from economy_api import get_db
from economy_crud import EconomyApiError
from sea_crud import SeaError

logger = logging.getLogger("character-service.sea_admin")

router = APIRouter(prefix="/characters", tags=["sea-admin"])

MSG_LOAD_FAILED = "Не удалось загрузить корабли"
MSG_WRITE_FAILED = "Не удалось сохранить корабль"
MSG_CONFLICT = "Корабль сейчас меняется, попробуйте ещё раз"
MSG_NAME = "Название корабля: от 1 до 100 символов"
MSG_DECK_NOT_FOUND = "Локация палубы не найдена"
MSG_DECK_ZONE = "Палубой не может быть морская зона"
MSG_DECK_PORT = "Палубой не может быть порт"
MSG_DECK_NOT_HIDDEN = "Палуба должна быть локацией скрытой страны (например, «Моря»)"
MSG_DECK_LINKED = "У палубы не должно быть переходов (соседей и стрелок) — уберите их в редакторе локаций"
MSG_DECK_BOUND = "Эта локация уже палуба корабля «{name}»"
MSG_DECK_IMMUTABLE = "Палубу корабля менять нельзя"
MSG_CAPTAIN_NOT_FOUND = "НПС-капитан не найден"
MSG_CAPTAIN_ROLE = "У НПС должна быть роль «Капитан»"
MSG_CAPTAIN_DEAD = "Этот капитан мёртв"
MSG_CAPTAIN_BOUND = "Этот капитан уже командует кораблём «{name}»"
MSG_STOPS_COUNT = "В маршруте должно быть от 2 до 30 портов"
MSG_STOPS_SAME = "Соседние остановки маршрута не могут быть одним портом (остановка {n})"
MSG_STOP_NOT_PORT = "«{name}» — не порт или у порта не задан выход в море (морская зона)"
MSG_NO_PATH = "Нет морского пути между «{a}» и «{b}» (участок {n})"
MSG_BAD_OVERRIDE = "Ручной путь участка {n} («{a}» → «{b}») неверен: нужна цепочка соседних морских зон от выхода в море порта «{a}» до выхода порта «{b}»"
MSG_ROUTE_AT_SEA = "Маршрут меняется только когда корабль у причала"
MSG_DOCKED_PORT_KEPT = "Порт, где корабль сейчас стоит («{name}»), должен остаться в маршруте"
MSG_DELETE_AT_SEA = "Корабль в море — выключите его и дождитесь швартовки"
MSG_DELETE_BATTLE = "На палубе идёт бой — списать корабль можно после его окончания"
MSG_STORM_MINUTES = "Максимальная длительность шторма меньше минимальной"
MSG_WEATHER_UNAVAILABLE = "Шторма пока недоступны"
MSG_SEA_NOT_FOUND = "Море не найдено"
MSG_NOT_SEA_ZONE = "Это не морская зона"
MSG_STORM_NOT_FOUND = "Шторм не найден или уже закончился"

RAIDS_FINAL_LIMIT = 20                     # finished raids shown in the weather view

PROBLEM_TEXTS = {
    sea_core.LEG_NO_ZONE: "У порта нет выхода в море (морской зоны)",
    sea_core.LEG_NO_PATH: "Нет морского пути между портами",
    sea_core.LEG_BAD_OVERRIDE: "Ручной путь неверен (используется кратчайший)",
    "same_port": "Соседние остановки совпадают",
    "not_port": "Локация не порт",
}


# =====================================================================================================================
# schemas (Pydantic v1)
# =====================================================================================================================

class StopIn(BaseModel):
    port_location_id: int = Field(..., ge=1)
    path_override: Optional[List[int]] = Field(None, max_items=sea_core.PATH_MAX_ZONES_RANGE[1])

    @validator("path_override")
    def _override_ids(cls, value):
        if value is not None and any(int(z) < 1 for z in value):
            raise ValueError("id морских зон должны быть положительными")
        return value or None


_R = sea_core


class ShipCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=_R.NAME_MAX)
    captain_npc_id: Optional[int] = Field(None, ge=1)
    deck_location_id: int = Field(..., ge=1)
    capacity: int = Field(10, ge=_R.CAPACITY_RANGE[0], le=_R.CAPACITY_RANGE[1])
    crew_slots: int = Field(2, ge=_R.CREW_SLOTS_RANGE[0], le=_R.CREW_SLOTS_RANGE[1])
    boarding_minutes: int = Field(30, ge=_R.BOARDING_MINUTES_RANGE[0], le=_R.BOARDING_MINUTES_RANGE[1])
    zone_minutes: int = Field(10, ge=_R.ZONE_MINUTES_RANGE[0], le=_R.ZONE_MINUTES_RANGE[1])
    fare_base: int = Field(10, ge=_R.FARE_RANGE[0], le=_R.FARE_RANGE[1])
    fare_per_zone: int = Field(5, ge=_R.FARE_RANGE[0], le=_R.FARE_RANGE[1])
    is_loop: bool = False
    is_active: bool = True
    stops: List[StopIn] = Field(..., min_items=_R.STOPS_RANGE[0], max_items=_R.STOPS_RANGE[1])


class ShipUpdate(BaseModel):
    """All optional; ``captain_npc_id: null`` unbinds the Captain; ``deck_location_id`` is refused."""
    name: Optional[str] = Field(None, min_length=1, max_length=_R.NAME_MAX)
    captain_npc_id: Optional[int] = Field(None, ge=1)
    deck_location_id: Optional[int] = None
    capacity: Optional[int] = Field(None, ge=_R.CAPACITY_RANGE[0], le=_R.CAPACITY_RANGE[1])
    crew_slots: Optional[int] = Field(None, ge=_R.CREW_SLOTS_RANGE[0], le=_R.CREW_SLOTS_RANGE[1])
    boarding_minutes: Optional[int] = Field(None, ge=_R.BOARDING_MINUTES_RANGE[0], le=_R.BOARDING_MINUTES_RANGE[1])
    zone_minutes: Optional[int] = Field(None, ge=_R.ZONE_MINUTES_RANGE[0], le=_R.ZONE_MINUTES_RANGE[1])
    fare_base: Optional[int] = Field(None, ge=_R.FARE_RANGE[0], le=_R.FARE_RANGE[1])
    fare_per_zone: Optional[int] = Field(None, ge=_R.FARE_RANGE[0], le=_R.FARE_RANGE[1])
    is_loop: Optional[bool] = None
    is_active: Optional[bool] = None
    stops: Optional[List[StopIn]] = Field(None, min_items=_R.STOPS_RANGE[0], max_items=_R.STOPS_RANGE[1])


class LegsPreviewIn(BaseModel):
    stops: List[StopIn] = Field(..., min_items=1, max_items=_R.STOPS_RANGE[1])
    is_loop: bool = False
    zone_minutes: Optional[int] = Field(None, ge=_R.ZONE_MINUTES_RANGE[0], le=_R.ZONE_MINUTES_RANGE[1])


class RefOut(BaseModel):
    id: int
    name: Optional[str]


class LegOut(BaseModel):
    index: int
    from_: Optional[RefOut] = Field(None, alias="from")
    to: Optional[RefOut]
    zones: List[RefOut]
    minutes_per_zone_hint: Optional[int]
    minutes: Optional[int]
    override: bool
    ok: bool
    problem: Optional[str]                 # code: no_zone | no_path | bad_override | same_port | not_port
    problem_text: Optional[str]

    class Config:
        allow_population_by_field_name = True


class AdminStopOut(BaseModel):
    index: int
    port_id: int
    port_name: Optional[str]
    path_override: Optional[List[int]]


class CaptainAdminOut(BaseModel):
    id: int
    name: Optional[str]
    avatar: Optional[str]
    location_id: Optional[int]
    location_name: Optional[str]


class ZoneAdminOut(BaseModel):
    id: int
    name: Optional[str]
    sea_name: Optional[str]


class ShipAdminOut(BaseModel):
    id: int
    name: str
    captain_npc_id: Optional[int]
    captain: Optional[CaptainAdminOut]
    captain_problem: Optional[str]         # «капитана нет» reasons (sales closed)
    deck: RefOut
    capacity: int
    crew_slots: int
    boarding_minutes: int
    zone_minutes: int
    fare_base: int
    fare_per_zone: int
    is_loop: bool
    is_active: bool
    status: str
    stop_index: int
    next_stop_index: Optional[int]
    direction: int
    trip_no: int
    docked_port: Optional[RefOut]
    next_port: Optional[RefOut]
    current_zone: Optional[ZoneAdminOut]
    leg_path: Optional[List[int]]
    leg_pos: int
    departs_at: Optional[datetime]
    next_zone_at: Optional[datetime]
    arrives_at: Optional[datetime]
    blocked_reason: Optional[str]
    stops: List[AdminStopOut]
    legs: List[LegOut]
    passengers_count: int
    active_passes: int
    server_now: datetime
    created_at: datetime
    updated_at: datetime


class DeckCandidateOut(BaseModel):
    id: int
    name: Optional[str]
    region_name: Optional[str]
    country_name: Optional[str]


class CaptainCandidateOut(BaseModel):
    id: int
    name: Optional[str]
    avatar: Optional[str]
    location_name: Optional[str]


class CandidatesOut(BaseModel):
    decks: List[DeckCandidateOut]
    captains: List[CaptainCandidateOut]


# FEAT-214 storm / raid numbers of ``sea_settings``: name → (bounds, is_decimal).
STORM_SETTING_FIELDS: Dict[str, Tuple[Tuple[int, int], bool]] = {
    "storm_min_minutes": (_R.STORM_MINUTES_RANGE, False),
    "storm_max_minutes": (_R.STORM_MINUTES_RANGE, False),
    "storm_move_pct": (_R.STORM_MOVE_PCT_RANGE, True),
    "storm_max_moves": (_R.STORM_MAX_MOVES_RANGE, False),
    "storm_slow_mult": (_R.STORM_SLOW_MULT_RANGE, True),
    "storm_drift_pct": (_R.STORM_DRIFT_PCT_RANGE, True),
    "storm_hp_pct": (_R.STORM_HP_PCT_RANGE, True),
    "storm_stamina_pct": (_R.STORM_STAMINA_PCT_RANGE, True),
    "storm_postpone_minutes": (_R.STORM_POSTPONE_MINUTES_RANGE, False),
    "storm_postpone_max_minutes": (_R.STORM_POSTPONE_MAX_MINUTES_RANGE, False),
    "storm_sailor_relief_pct": (_R.STORM_SAILOR_RELIEF_PCT_RANGE, True),
    "season_mult_spring": (_R.SEASON_MULT_RANGE, True),
    "season_mult_summer": (_R.SEASON_MULT_RANGE, True),
    "season_mult_autumn": (_R.SEASON_MULT_RANGE, True),
    "season_mult_winter": (_R.SEASON_MULT_RANGE, True),
    "raid_chance_mult": (_R.RAID_CHANCE_MULT_RANGE, True),
    "raid_hold_max_minutes": (_R.RAID_HOLD_MAX_MINUTES_RANGE, False),
    "raid_repelled_delay_minutes": (_R.RAID_REPELLED_DELAY_MINUTES_RANGE, False),
}


def _opt(name: str):
    """An optional bounded FEAT-214 settings field (omitted / null = keep the saved value)."""
    lo, hi = STORM_SETTING_FIELDS[name][0]
    return Field(None, ge=lo, le=hi)


class SeaSettingsOut(BaseModel):
    sailor_post_min_chars: int
    stowaway_base_pct: float
    stowaway_wanted_points: int
    path_max_zones: int
    # FEAT-214
    storm_min_minutes: int
    storm_max_minutes: int
    storm_move_pct: float
    storm_max_moves: int
    storm_slow_mult: float
    storm_drift_pct: float
    storm_hp_pct: float
    storm_stamina_pct: float
    storm_postpone_minutes: int
    storm_postpone_max_minutes: int
    storm_sailor_relief_pct: float
    season_mult_spring: float
    season_mult_summer: float
    season_mult_autumn: float
    season_mult_winter: float
    raid_chance_mult: float
    raid_hold_max_minutes: int
    raid_repelled_delay_minutes: int


class SeaSettingsIn(BaseModel):
    """The FEAT-213 four are required; the FEAT-214 numbers are optional (omitted / null = keep the saved value)."""
    sailor_post_min_chars: int = Field(..., ge=_R.SAILOR_POST_MIN_CHARS_RANGE[0], le=_R.SAILOR_POST_MIN_CHARS_RANGE[1])
    stowaway_base_pct: float = Field(..., ge=_R.STOWAWAY_BASE_PCT_RANGE[0], le=_R.STOWAWAY_BASE_PCT_RANGE[1])
    stowaway_wanted_points: int = Field(..., ge=_R.STOWAWAY_WANTED_POINTS_RANGE[0],
                                        le=_R.STOWAWAY_WANTED_POINTS_RANGE[1])
    path_max_zones: int = Field(..., ge=_R.PATH_MAX_ZONES_RANGE[0], le=_R.PATH_MAX_ZONES_RANGE[1])
    storm_min_minutes: Optional[int] = _opt("storm_min_minutes")
    storm_max_minutes: Optional[int] = _opt("storm_max_minutes")
    storm_move_pct: Optional[float] = _opt("storm_move_pct")
    storm_max_moves: Optional[int] = _opt("storm_max_moves")
    storm_slow_mult: Optional[float] = _opt("storm_slow_mult")
    storm_drift_pct: Optional[float] = _opt("storm_drift_pct")
    storm_hp_pct: Optional[float] = _opt("storm_hp_pct")
    storm_stamina_pct: Optional[float] = _opt("storm_stamina_pct")
    storm_postpone_minutes: Optional[int] = _opt("storm_postpone_minutes")
    storm_postpone_max_minutes: Optional[int] = _opt("storm_postpone_max_minutes")
    storm_sailor_relief_pct: Optional[float] = _opt("storm_sailor_relief_pct")
    season_mult_spring: Optional[float] = _opt("season_mult_spring")
    season_mult_summer: Optional[float] = _opt("season_mult_summer")
    season_mult_autumn: Optional[float] = _opt("season_mult_autumn")
    season_mult_winter: Optional[float] = _opt("season_mult_winter")
    raid_chance_mult: Optional[float] = _opt("raid_chance_mult")
    raid_hold_max_minutes: Optional[int] = _opt("raid_hold_max_minutes")
    raid_repelled_delay_minutes: Optional[int] = _opt("raid_repelled_delay_minutes")


# ---------------------------------------------------------------------------------------------------- FEAT-214 weather

class StormSeaIn(BaseModel):
    is_enabled: bool
    chance_per_hour_pct: float = Field(..., ge=_R.STORM_CHANCE_PER_HOUR_RANGE[0], le=_R.STORM_CHANCE_PER_HOUR_RANGE[1])
    radius: int = Field(..., ge=_R.STORM_RADIUS_RANGE[0], le=_R.STORM_RADIUS_RANGE[1])


class StormCreateIn(BaseModel):
    zone_id: int = Field(..., ge=1)
    minutes: int = Field(..., ge=_R.STORM_MINUTES_RANGE[0], le=_R.STORM_MINUTES_RANGE[1])


class StormSeaOut(BaseModel):
    region_id: int
    name: Optional[str]
    zones_count: int
    is_enabled: bool
    chance_per_hour_pct: float
    radius: int


class StormAdminOut(BaseModel):
    id: int
    region_id: Optional[int]
    sea_name: Optional[str]
    center_zone: RefOut
    zones: List[RefOut]
    started_at: datetime
    ends_at: datetime
    moves: int
    source: str                            # auto | admin


class RaidAdminOut(BaseModel):
    id: int
    ship_id: int
    ship_name: Optional[str]               # None when the ship was deleted
    zone: RefOut
    monster_name: Optional[str]
    players: List[RefOut]                  # placed players (planned group until BS placed them)
    battle_id: Optional[int]
    status: str                            # starting | fighting | won | lost | aborted | expired
    created_at: datetime


class SeaWeatherOut(BaseModel):
    season: Optional[str]                  # spring | summer | autumn | winter; None = no game calendar
    season_mult: float
    seas: List[StormSeaOut]
    storms: List[StormAdminOut]
    raids: List[RaidAdminOut]              # active first (newest first), then the last 20 finished


# =====================================================================================================================
# legs (A5 and the save validation)
# =====================================================================================================================

def _minutes(value: int) -> timedelta:
    return timedelta(minutes=max(1, int(value)))


def _ports(stops: Sequence[StopIn]) -> List[int]:
    return [int(s.port_location_id) for s in stops]


def legs_preview(db: Session, stops: Sequence[StopIn], is_loop: bool, *, zone_minutes: Optional[int] = None,
                 params: Optional[sea_crud.SeaParams] = None,
                 graph: Optional[sea_crud.ZoneGraph] = None) -> List[dict]:
    """Every leg of the line (i → i+1, plus last → first for a loop): zone path (override or BFS) and its problem."""
    params = params or sea_crud.load_params(db)
    graph = graph or sea_crud.zone_graph(db)
    ports = _ports(stops)
    n = len(ports)
    locs = sea_crud.location_infos(db, ports + [z for s in stops for z in (s.path_override or [])])
    pairs = [(i, i + 1) for i in range(n - 1)]
    if is_loop and n >= 2:
        pairs.append((n - 1, 0))
    out = []
    for i, j in pairs:
        a, b = ports[i], ports[j]
        ia, ib = locs.get(a), locs.get(b)
        override = stops[i].path_override
        row = {"index": i, "from": {"id": a, "name": ia.name if ia else None},
               "to": {"id": b, "name": ib.name if ib else None}, "zones": [], "minutes_per_zone_hint": zone_minutes,
               "minutes": None, "override": False, "ok": False, "problem": None, "problem_text": None}
        if a == b:
            problem = "same_port"
        elif ia is None or ib is None or not ia.is_port or not ib.is_port:
            problem = "not_port"
        else:
            path, problem, used = sea_core.leg_path(graph.adj, graph.zone_ids, ia.port_zone_id, ib.port_zone_id,
                                                    override, params.path_max_zones)
            if path is not None:
                zone_locs = sea_crud.location_infos(db, path)
                row["zones"] = [{"id": z, "name": zone_locs[z].name if z in zone_locs else None} for z in path]
                row["override"] = bool(used)
                row["minutes"] = sea_core.leg_minutes(len(path), zone_minutes) if zone_minutes else None
                row["ok"] = problem is None
        row["problem"] = problem
        row["problem_text"] = PROBLEM_TEXTS.get(problem) if problem else None
        out.append(row)
    return out


def validate_route(db: Session, stops: Sequence[StopIn], is_loop: bool) -> Tuple[List[dict], Dict[int, sea_crud.LocInfo]]:
    """409 on the first problem of the line (§3.12 CS)."""
    n = len(stops)
    if n < sea_core.STOPS_RANGE[0] or n > sea_core.STOPS_RANGE[1]:
        raise SeaError(400, MSG_STOPS_COUNT)
    ports = _ports(stops)
    for i in range(1, n):
        if ports[i] == ports[i - 1]:
            raise SeaError(409, MSG_STOPS_SAME.format(n=i + 1))
    if is_loop and ports[0] == ports[-1]:
        raise SeaError(409, MSG_STOPS_SAME.format(n=n))
    graph = sea_crud.zone_graph(db)
    locs = sea_crud.location_infos(db, ports)
    for p in ports:
        info = locs.get(p)
        if info is None or not info.is_port or not info.port_zone_id or int(info.port_zone_id) not in graph.zone_ids:
            raise SeaError(409, MSG_STOP_NOT_PORT.format(name=(info.name if info else None) or f"#{p}"))
    legs = legs_preview(db, stops, is_loop, graph=graph)
    for leg in legs:
        a, b, num = leg["from"]["name"] or "—", leg["to"]["name"] or "—", leg["index"] + 1
        if leg["problem"] == sea_core.LEG_BAD_OVERRIDE:
            raise SeaError(409, MSG_BAD_OVERRIDE.format(n=num, a=a, b=b))
        if not leg["ok"]:
            raise SeaError(409, MSG_NO_PATH.format(a=a, b=b, n=num))
    return legs, locs


# =====================================================================================================================
# deck / Captain validation
# =====================================================================================================================

def _ship_name(db: Session, ship_id) -> str:
    row = db.get(models.SeaShip, int(ship_id))
    return row.name if row is not None else "—"


def validate_deck(db: Session, deck_id: int, ship_id: Optional[int] = None) -> None:
    info = sea_crud.location_infos(db, [deck_id]).get(int(deck_id))
    if info is None:
        raise SeaError(404, MSG_DECK_NOT_FOUND)
    if info.is_sea_zone:
        raise SeaError(409, MSG_DECK_ZONE)
    if info.is_port:
        raise SeaError(409, MSG_DECK_PORT)
    _region, country = econ_ledger.resolve_location(db, deck_id)
    hidden = sea_crud._rows(db, "SELECT is_hidden FROM Countries WHERE id = :c", {"c": int(country)}) \
        if country else None
    if not hidden or not bool(hidden[0][0]):
        raise SeaError(409, MSG_DECK_NOT_HIDDEN)
    linked = sea_crud._rows(db, "SELECT 1 FROM LocationNeighbors WHERE location_id = :l OR neighbor_id = :l LIMIT 1",
                            {"l": int(deck_id)})
    arrows = sea_crud._rows(db, "SELECT 1 FROM arrow_neighbors WHERE location_id = :l LIMIT 1", {"l": int(deck_id)})
    if linked or arrows:
        raise SeaError(409, MSG_DECK_LINKED)
    other = db.query(models.SeaShip).filter(models.SeaShip.deck_location_id == int(deck_id)).first()
    if other is not None and (ship_id is None or int(other.id) != int(ship_id)):
        raise SeaError(409, MSG_DECK_BOUND.format(name=other.name))


def validate_captain(db: Session, npc_id: int, ship_id: Optional[int] = None) -> None:
    npc = db.get(models.Character, int(npc_id))
    if npc is None or not npc.is_npc:
        raise SeaError(404, MSG_CAPTAIN_NOT_FOUND)
    if npc.npc_role != sea_core.CAPTAIN_ROLE:
        raise SeaError(409, MSG_CAPTAIN_ROLE)
    if npc.npc_status == sea_crud.NPC_DEAD:
        raise SeaError(409, MSG_CAPTAIN_DEAD)
    other = db.query(models.SeaShip).filter(models.SeaShip.captain_npc_id == int(npc_id)).first()
    if other is not None and (ship_id is None or int(other.id) != int(ship_id)):
        raise SeaError(409, MSG_CAPTAIN_BOUND.format(name=other.name))


def captain_problem(db: Session, ship: "models.SeaShip") -> Optional[str]:
    if not ship.captain_npc_id:
        return "Капитан не назначен — продажа билетов закрыта"
    npc = db.get(models.Character, int(ship.captain_npc_id))
    if npc is None or not npc.is_npc:
        return "Капитан удалён — назначьте нового"
    if npc.npc_role != sea_core.CAPTAIN_ROLE:
        return "У НПС больше нет роли «Капитан» — продажа билетов закрыта"
    if npc.npc_status == sea_crud.NPC_DEAD:
        return "Капитан мёртв — назначьте нового"
    return None


# =====================================================================================================================
# output
# =====================================================================================================================

def _stop_ins(stops: Sequence["models.SeaShipStop"]) -> List[StopIn]:
    return [StopIn(port_location_id=int(s.port_location_id), path_override=s.path_override or None) for s in stops]


def ship_admin_out(db: Session, ship: "models.SeaShip", *, graph: Optional[sea_crud.ZoneGraph] = None,
                   params: Optional[sea_crud.SeaParams] = None, now: Optional[datetime] = None) -> dict:
    now = now or sea_crud.now_utc()
    stops = sea_crud.load_stops(db, ship.id)
    public = sea_crud.ship_public(db, ship, stops, now)
    deck_info = sea_crud.location_infos(db, [ship.deck_location_id]).get(int(ship.deck_location_id))
    captain = None
    if ship.captain_npc_id:
        npc = db.get(models.Character, int(ship.captain_npc_id))
        if npc is not None:
            loc = sea_crud.location_infos(db, [npc.current_location_id]).get(int(npc.current_location_id or 0))
            captain = {"id": int(npc.id), "name": npc.name, "avatar": npc.avatar,
                       "location_id": int(npc.current_location_id) if npc.current_location_id else None,
                       "location_name": loc.name if loc is not None else None}
    passengers = db.query(models.Character.id).filter(
        models.Character.current_location_id == int(ship.deck_location_id),
        models.Character.is_npc.is_(False)).count()
    active = db.query(models.SeaPass.id).filter(models.SeaPass.ship_id == int(ship.id),
                                                models.SeaPass.status == sea_core.PASS_ACTIVE).count()
    names = {s["index"]: s["port_name"] for s in public["stops"]}
    return {
        "id": int(ship.id), "name": ship.name, "captain_npc_id": ship.captain_npc_id, "captain": captain,
        "captain_problem": captain_problem(db, ship),
        "deck": {"id": int(ship.deck_location_id), "name": deck_info.name if deck_info else None},
        "capacity": int(ship.capacity), "crew_slots": int(ship.crew_slots),
        "boarding_minutes": int(ship.boarding_minutes), "zone_minutes": int(ship.zone_minutes),
        "fare_base": int(ship.fare_base), "fare_per_zone": int(ship.fare_per_zone), "is_loop": bool(ship.is_loop),
        "is_active": bool(ship.is_active), "status": ship.status, "stop_index": int(ship.stop_index or 0),
        "next_stop_index": ship.next_stop_index, "direction": int(ship.direction or 1),
        "trip_no": int(ship.trip_no or 0), "docked_port": public["docked_port"], "next_port": public["next_port"],
        "current_zone": public["current_zone"],
        "leg_path": ship.leg_path if isinstance(ship.leg_path, list) else None, "leg_pos": int(ship.leg_pos or 0),
        "departs_at": ship.departs_at, "next_zone_at": ship.next_zone_at, "arrives_at": public["arrives_at"],
        "blocked_reason": ship.blocked_reason,
        "stops": [{"index": int(s.idx), "port_id": int(s.port_location_id), "port_name": names.get(int(s.idx)),
                   "path_override": s.path_override or None} for s in stops],
        "legs": legs_preview(db, _stop_ins(stops), bool(ship.is_loop), zone_minutes=int(ship.zone_minutes),
                             params=params, graph=graph) if len(stops) >= 1 else [],
        "passengers_count": int(passengers), "active_passes": int(active), "server_now": now,
        "created_at": ship.created_at, "updated_at": ship.updated_at,
    }


def list_ships(db: Session) -> List[dict]:
    sea_crud.require_available(db)
    params, graph, now = sea_crud.load_params(db), sea_crud.zone_graph(db), sea_crud.now_utc()
    ships = db.query(models.SeaShip).order_by(models.SeaShip.id).all()
    return [ship_admin_out(db, s, graph=graph, params=params, now=now) for s in ships]


# =====================================================================================================================
# writes
# =====================================================================================================================

def _write_stops(db: Session, ship_id: int, stops: Sequence[StopIn], is_loop: bool) -> None:
    db.query(models.SeaShipStop).filter(models.SeaShipStop.ship_id == int(ship_id)).delete(synchronize_session=False)
    db.flush()
    n = len(stops)
    for i, s in enumerate(stops):
        override = s.path_override if (i < n - 1 or is_loop) else None
        db.add(models.SeaShipStop(ship_id=int(ship_id), idx=i, port_location_id=int(s.port_location_id),
                                  path_override=[int(z) for z in override] if override else None))
    db.flush()


def create_ship(db: Session, body: ShipCreate, now: Optional[datetime] = None) -> "models.SeaShip":
    now = now or sea_crud.now_utc()
    sea_crud.require_available(db)
    name = body.name.strip()
    if not name or len(name) > sea_core.NAME_MAX:
        raise SeaError(400, MSG_NAME)
    validate_deck(db, body.deck_location_id)
    if body.captain_npc_id:
        validate_captain(db, body.captain_npc_id)
    _legs, locs = validate_route(db, body.stops, body.is_loop)
    port0 = int(body.stops[0].port_location_id)
    ship = models.SeaShip(
        name=name, captain_npc_id=body.captain_npc_id, deck_location_id=int(body.deck_location_id),
        capacity=body.capacity, crew_slots=body.crew_slots, boarding_minutes=body.boarding_minutes,
        zone_minutes=body.zone_minutes, fare_base=body.fare_base, fare_per_zone=body.fare_per_zone,
        is_loop=body.is_loop, is_active=body.is_active, status=sea_core.STATUS_DOCKED, stop_index=0,
        next_stop_index=None, direction=sea_core.DIRECTION_FORWARD, trip_no=0, docked_port_id=port0,
        next_port_id=None, current_zone_id=int(locs[port0].port_zone_id), leg_path=None, leg_pos=0,
        departs_at=now + _minutes(body.boarding_minutes) if body.is_active else None,
        next_zone_at=None, last_port_id=port0, blocked_reason=None, created_at=now, updated_at=now)
    db.add(ship)
    db.flush()
    _write_stops(db, ship.id, body.stops, body.is_loop)
    sea_pass.place_captain(db, ship, "ship created")
    logger.info("sea ship %s «%s» created (deck %s, %d stops)", ship.id, name, ship.deck_location_id, len(body.stops))
    return ship


def _end_passes_for_route_change(db: Session, ship: "models.SeaShip", now: datetime) -> List[law_notify.Notice]:
    """Not-started passes refunded, started ones completed (holders must buy again)."""
    notices = sea_crud.refund_not_started(db, ship, now)
    # Flush first: active_passes() re-reads with populate_existing() and the session
    # does not autoflush, so a just-refunded pass would come back as 'active'.
    db.flush()
    for p in sea_crud.active_passes(db, ship.id, lock=True):
        p.status, p.ended_at = sea_core.PASS_COMPLETED, now
    return notices


def update_ship(db: Session, ship_id: int, body: ShipUpdate,
                now: Optional[datetime] = None) -> Tuple["models.SeaShip", List[law_notify.Notice]]:
    now = now or sea_crud.now_utc()
    sea_crud.require_available(db)
    fields = body.__fields_set__
    ship = sea_crud.get_ship(db, ship_id, lock=True)
    if ship is None:
        raise SeaError(404, sea_crud.MSG_SHIP_NOT_FOUND)
    notices: List[law_notify.Notice] = []
    if "deck_location_id" in fields and body.deck_location_id is not None \
            and int(body.deck_location_id) != int(ship.deck_location_id):
        raise SeaError(409, MSG_DECK_IMMUTABLE)
    if "name" in fields and body.name is not None:
        name = body.name.strip()
        if not name:
            raise SeaError(400, MSG_NAME)
        ship.name = name
    for key in ("capacity", "crew_slots", "boarding_minutes", "zone_minutes", "fare_base", "fare_per_zone"):
        if key in fields and getattr(body, key) is not None:
            setattr(ship, key, int(getattr(body, key)))
    if "captain_npc_id" in fields:
        if body.captain_npc_id:
            validate_captain(db, body.captain_npc_id, ship.id)
            ship.captain_npc_id = int(body.captain_npc_id)
        else:
            ship.captain_npc_id = None

    # route (stops / loop) — only while docked
    old_stops = sea_crud.load_stops(db, ship.id)
    new_loop = bool(body.is_loop) if "is_loop" in fields and body.is_loop is not None else bool(ship.is_loop)
    new_stops = body.stops if "stops" in fields and body.stops is not None else _stop_ins(old_stops)
    old_sig = ([(int(s.port_location_id), list(s.path_override or [])) for s in old_stops], bool(ship.is_loop))
    new_sig = ([(int(s.port_location_id), list(s.path_override or []) if (i < len(new_stops) - 1 or new_loop) else [])
                for i, s in enumerate(new_stops)], new_loop)
    if old_sig != new_sig:
        if ship.status != sea_core.STATUS_DOCKED:
            raise SeaError(409, MSG_ROUTE_AT_SEA)
        _legs, locs = validate_route(db, new_stops, new_loop)
        ports = _ports(new_stops)
        if ship.docked_port_id and int(ship.docked_port_id) in ports:
            ship.stop_index = ports.index(int(ship.docked_port_id))
        elif ship.docked_port_id and int(ship.docked_port_id) in sea_crud.location_infos(db, [ship.docked_port_id]):
            name = sea_crud.location_infos(db, [ship.docked_port_id])[int(ship.docked_port_id)].name or "—"
            raise SeaError(409, MSG_DOCKED_PORT_KEPT.format(name=name))
        else:                                    # the docked port vanished (broken landing): restart at stop 0
            ship.stop_index = 0
            ship.docked_port_id = ports[0]
            ship.last_port_id = ports[0]
            ship.current_zone_id = int(locs[ports[0]].port_zone_id)
        ship.is_loop = new_loop
        if new_loop:
            ship.direction = sea_core.DIRECTION_FORWARD
        _write_stops(db, ship.id, new_stops, new_loop)
        notices.extend(_end_passes_for_route_change(db, ship, now))
        ship.blocked_reason = None
        logger.info("sea ship %s: route changed (%d stops, loop=%s)", ship.id, len(new_stops), new_loop)

    if "is_active" in fields and body.is_active is not None and bool(body.is_active) != bool(ship.is_active):
        if body.is_active:
            ship.is_active = True
            ship.blocked_reason = None
            if ship.status == sea_core.STATUS_DOCKED:
                ship.departs_at = now + _minutes(ship.boarding_minutes)
        else:
            ship.is_active = False
            if ship.status == sea_core.STATUS_DOCKED:
                ship.departs_at = None
            notices.extend(sea_crud.refund_not_started(db, ship, now))
    ship.updated_at = now
    db.flush()
    sea_pass.place_captain(db, ship, "ship edited")
    return ship, notices


def _deck_battle(db: Session, ship: "models.SeaShip") -> bool:
    """FEAT-214 §3.9: a deck player in an active battle, or an active monster raid of the ship."""
    if any(sea_pass.in_battle(db, ch.id) for ch in sea_crud.deck_players(db, ship, lock=False)):
        return True
    rows = sea_crud._rows(db, "SELECT 1 FROM sea_raids WHERE ship_id = :s AND status IN (:a, :b) LIMIT 1",
                          {"s": int(ship.id), "a": sea_core.RAID_STARTING, "b": sea_core.RAID_FIGHTING})
    return bool(rows)


def delete_ship(db: Session, ship_id: int, now: Optional[datetime] = None) -> sea_pass.ShipOutcome:
    now = now or sea_crud.now_utc()
    sea_crud.require_available(db)
    ship = sea_crud.get_ship(db, ship_id, lock=True)
    if ship is None:
        raise SeaError(404, sea_crud.MSG_SHIP_NOT_FOUND)
    if ship.status != sea_core.STATUS_DOCKED:
        raise SeaError(409, MSG_DELETE_AT_SEA)
    if _deck_battle(db, ship):
        raise SeaError(409, MSG_DELETE_BATTLE)
    out = sea_pass.ShipOutcome(int(ship.id), deck_location_id=int(ship.deck_location_id))
    stops = sea_crud.load_stops(db, ship.id)
    out.notices.extend(sea_crud.refund_not_started(db, ship, now))
    db.flush()                                   # see _end_passes_for_route_change
    for p in sea_crud.active_passes(db, ship.id, lock=True):
        p.status, p.ended_at = sea_core.PASS_COMPLETED, now
    target, fallback = sea_crud.landing_target(db, ship, stops)
    players = sea_crud.deck_players(db, ship, lock=True)
    if target is not None:
        port_name = sea_pass._name(sea_crud.location_infos(db, [target]), target)
        message = f"Корабль «{ship.name}» списан — вас высадили в «{port_name}»"
        for ch in players:
            if sea_pass.gathering(db, ch.id):
                out.gathering_ids.add(int(ch.id))
            out.ashore.append(sea_crud.put_ashore(db, ch, target, ship.deck_location_id, message,
                                                  law_check=not fallback, now=now))
            out.notices.append(sea_crud.notice(ch.user_id, message, ch.id, ship.id, "ship_deleted"))
    elif players:
        logger.error("sea ship %s delete: nowhere to put %d players ashore", ship.id, len(players))
    db.query(models.SeaShipStop).filter(models.SeaShipStop.ship_id == int(ship.id)).delete(synchronize_session=False)
    db.delete(ship)
    db.flush()
    logger.info("sea ship %s «%s» deleted, %d players put ashore", ship_id, ship.name, len(out.ashore))
    return out


def candidates(db: Session, ship_id: Optional[int] = None) -> dict:
    sea_crud.require_available(db)
    own_deck = own_captain = None
    if ship_id:
        own = db.get(models.SeaShip, int(ship_id))
        if own is not None:
            own_deck, own_captain = own.deck_location_id, own.captain_npc_id
    bound_decks = {int(r[0]) for r in db.query(models.SeaShip.deck_location_id).all()}
    bound_captains = {int(r[0]) for r in db.query(models.SeaShip.captain_npc_id).all() if r[0]}
    rows = sea_crud._rows(db, (
        "SELECT l.id, l.name, r.name, c.name FROM Locations l "
        "LEFT JOIN Districts d ON d.id = l.district_id "
        "JOIN Regions r ON r.id = COALESCE(d.region_id, l.region_id) "
        "JOIN Countries c ON c.id = r.country_id "
        "WHERE c.is_hidden = 1 AND l.is_sea_zone = 0 AND l.is_port = 0 "
        "AND NOT EXISTS (SELECT 1 FROM LocationNeighbors n WHERE n.location_id = l.id OR n.neighbor_id = l.id) "
        "AND NOT EXISTS (SELECT 1 FROM arrow_neighbors a WHERE a.location_id = l.id) ORDER BY l.id")) or []
    decks = [{"id": int(r[0]), "name": r[1], "region_name": r[2], "country_name": r[3]} for r in rows
             if int(r[0]) not in bound_decks or (own_deck and int(r[0]) == int(own_deck))]
    npcs = (db.query(models.Character).filter(models.Character.is_npc.is_(True),
                                              models.Character.npc_role == sea_core.CAPTAIN_ROLE)
            .order_by(models.Character.id).all())
    npcs = [n for n in npcs if n.npc_status != sea_crud.NPC_DEAD
            and (int(n.id) not in bound_captains or (own_captain and int(n.id) == int(own_captain)))]
    locs = sea_crud.location_infos(db, [n.current_location_id for n in npcs])
    captains = [{"id": int(n.id), "name": n.name, "avatar": n.avatar,
                 "location_name": (locs.get(int(n.current_location_id)) or sea_crud.LocInfo(0, None)).name
                 if n.current_location_id else None} for n in npcs]
    return {"decks": decks, "captains": captains}


def settings_out(db: Session) -> dict:
    sea_crud.require_available(db)
    p = sea_crud.load_params(db)
    out = {"sailor_post_min_chars": p.sailor_post_min_chars, "stowaway_base_pct": float(p.stowaway_base_pct),
           "stowaway_wanted_points": p.stowaway_wanted_points, "path_max_zones": p.path_max_zones}
    for name, (_bounds, is_dec) in STORM_SETTING_FIELDS.items():
        value = getattr(p, name)
        out[name] = float(value) if is_dec else int(value)
    return out


def save_settings(db: Session, body: SeaSettingsIn) -> None:
    sea_crud.require_available(db)
    current = sea_crud.load_params(db)
    lo = body.storm_min_minutes if body.storm_min_minutes is not None else current.storm_min_minutes
    hi = body.storm_max_minutes if body.storm_max_minutes is not None else current.storm_max_minutes
    if int(hi) < int(lo):
        raise SeaError(400, MSG_STORM_MINUTES)
    row = db.get(models.SeaSetting, 1)
    if row is None:
        row = models.SeaSetting(id=1)
        db.add(row)
    row.sailor_post_min_chars = int(body.sailor_post_min_chars)
    row.stowaway_base_pct = round(float(body.stowaway_base_pct), 2)
    row.stowaway_wanted_points = int(body.stowaway_wanted_points)
    row.path_max_zones = int(body.path_max_zones)
    for name, (_bounds, is_dec) in STORM_SETTING_FIELDS.items():
        value = getattr(body, name)
        if value is not None:
            setattr(row, name, Decimal(str(round(float(value), 2))) if is_dec else int(value))
    db.flush()


# =====================================================================================================================
# FEAT-214 weather admin (§3.11)
# =====================================================================================================================

def _require_weather(db: Session) -> None:
    sea_crud.require_available(db)
    if not sea_weather.weather_available(db):
        raise SeaError(503, MSG_WEATHER_UNAVAILABLE)


def _region_names(db: Session, ids) -> Dict[int, Optional[str]]:
    ids = sorted({int(i) for i in ids if i})
    if not ids:
        return {}
    ph, params = econ_core.in_params("r", ids)
    rows = sea_crud._rows(db, f"SELECT id, name FROM Regions WHERE id IN ({ph})", params) or []
    return {int(r[0]): r[1] for r in rows}


def _sea_zones(db: Session) -> Tuple[sea_crud.ZoneGraph, Dict[int, Optional[int]]]:
    """The sea-zone graph and ``{zone_id: region_id}`` (the sea of every zone)."""
    graph = sea_crud.zone_graph(db)
    return graph, sea_weather.zone_seas(db, graph.zone_ids)


def _sea_out(region_id: int, name: Optional[str], zones_count: int, row: Optional["models.SeaStormSea"]) -> dict:
    """A sea without a config row reads as «off, 0 %, default radius»."""
    return {"region_id": int(region_id), "name": name, "zones_count": int(zones_count),
            "is_enabled": bool(row.is_enabled) if row is not None else False,
            "chance_per_hour_pct": float(row.chance_per_hour_pct or 0) if row is not None else 0.0,
            "radius": int(row.radius) if row is not None and row.radius is not None else sea_weather.DEFAULT_RADIUS}


def _storms_out(db: Session, storms: Sequence["models.SeaStorm"]) -> List[dict]:
    if not storms:
        return []
    ids = [int(s.id) for s in storms]
    zone_rows = (db.query(models.SeaStormZone).filter(models.SeaStormZone.storm_id.in_(ids))
                 .order_by(models.SeaStormZone.zone_id).all())
    by_storm: Dict[int, List[int]] = {}
    for z in zone_rows:
        by_storm.setdefault(int(z.storm_id), []).append(int(z.zone_id))
    locs = sea_crud.location_infos(db, [z.zone_id for z in zone_rows] + [s.center_zone_id for s in storms])
    seas = _region_names(db, [s.region_id for s in storms])

    def ref(zone_id) -> dict:
        info = locs.get(int(zone_id))
        return {"id": int(zone_id), "name": info.name if info is not None else None}

    return [{"id": int(s.id), "region_id": int(s.region_id) if s.region_id is not None else None,
             "sea_name": seas.get(int(s.region_id)) if s.region_id is not None else None,
             "center_zone": ref(s.center_zone_id), "zones": [ref(z) for z in by_storm.get(int(s.id), [])],
             "started_at": s.started_at, "ends_at": s.ends_at, "moves": int(s.moves or 0), "source": s.source}
            for s in storms]


def _id_list(value) -> List[int]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return [int(v) for v in value] if isinstance(value, list) else []


def _raids_out(db: Session, raids: Sequence["models.SeaRaid"]) -> List[dict]:
    if not raids:
        return []
    ship_ids = sorted({int(r.ship_id) for r in raids})
    ships = {int(s.id): s.name for s in db.query(models.SeaShip).filter(models.SeaShip.id.in_(ship_ids)).all()}
    players = {int(r.id): _id_list(r.placed_ids) if r.placed_ids is not None else _id_list(r.player_ids)
               for r in raids}
    char_ids = sorted({c for ids in players.values() for c in ids})
    names = {int(row[0]): row[1] for row in db.query(models.Character.id, models.Character.name)
             .filter(models.Character.id.in_(char_ids)).all()} if char_ids else {}
    locs = sea_crud.location_infos(db, [r.zone_id for r in raids])
    return [{"id": int(r.id), "ship_id": int(r.ship_id), "ship_name": ships.get(int(r.ship_id)),
             "zone": {"id": int(r.zone_id), "name": (locs.get(int(r.zone_id)) or sea_crud.LocInfo(0, None)).name},
             "monster_name": r.monster_name,
             "players": [{"id": c, "name": names.get(c)} for c in players[int(r.id)]],
             "battle_id": int(r.battle_id) if r.battle_id else None, "status": r.status,
             "created_at": r.created_at} for r in raids]


def weather_out(db: Session, now: Optional[datetime] = None) -> dict:
    """§3.11 ``GET /admin/sea/weather``: seas = regions holding ≥ 1 sea zone; raids = active + the last 20 final."""
    now = now or sea_crud.now_utc()
    _require_weather(db)
    params = sea_crud.load_params(db)
    season = sea_weather.current_season(db, now)
    _graph, zone_sea = _sea_zones(db)
    counts: Dict[int, int] = {}
    for region_id in zone_sea.values():
        if region_id:
            counts[int(region_id)] = counts.get(int(region_id), 0) + 1
    names = _region_names(db, counts)
    rows = {int(r.region_id): r for r in db.query(models.SeaStormSea).all()}
    seas = [_sea_out(rid, names.get(rid), counts[rid], rows.get(rid)) for rid in sorted(counts)]
    storms = (db.query(models.SeaStorm).filter(models.SeaStorm.status == sea_core.STORM_ACTIVE)
              .order_by(models.SeaStorm.id).all())
    active = (db.query(models.SeaRaid).filter(models.SeaRaid.status.in_(sea_core.RAID_ACTIVE_STATUSES))
              .order_by(models.SeaRaid.id.desc()).all())
    final = (db.query(models.SeaRaid).filter(models.SeaRaid.status.in_(sea_core.RAID_FINAL_STATUSES))
             .order_by(models.SeaRaid.id.desc()).limit(RAIDS_FINAL_LIMIT).all())
    return {"season": season, "season_mult": float(sea_core.season_mult(season, params)), "seas": seas,
            "storms": _storms_out(db, storms), "raids": _raids_out(db, list(active) + list(final))}


def _sea_count(zone_sea: Dict[int, Optional[int]], region_id: int) -> int:
    return sum(1 for r in zone_sea.values() if r and int(r) == int(region_id))


def save_sea(db: Session, region_id: int, body: StormSeaIn, now: Optional[datetime] = None) -> None:
    now = now or sea_crud.now_utc()
    _require_weather(db)
    _graph, zone_sea = _sea_zones(db)
    if not _sea_count(zone_sea, region_id):
        raise SeaError(404, MSG_SEA_NOT_FOUND)
    row = db.get(models.SeaStormSea, int(region_id))
    if row is None:
        row = models.SeaStormSea(region_id=int(region_id))
        db.add(row)
    row.is_enabled = bool(body.is_enabled)
    row.chance_per_hour_pct = Decimal(str(round(float(body.chance_per_hour_pct), 2)))
    row.radius = int(body.radius)
    row.updated_at = now
    db.flush()


def sea_one(db: Session, region_id: int) -> dict:
    _graph, zone_sea = _sea_zones(db)
    return _sea_out(region_id, _region_names(db, [region_id]).get(int(region_id)), _sea_count(zone_sea, region_id),
                    db.get(models.SeaStormSea, int(region_id)))


def start_storm(db: Session, body: StormCreateIn, now: Optional[datetime] = None) -> int:
    """An admin storm over ``zone_id`` + its sea's radius (bypasses the one-storm-per-sea rule). Returns its id."""
    now = now or sea_crud.now_utc()
    _require_weather(db)
    graph, zone_sea = _sea_zones(db)
    zone_id = int(body.zone_id)
    if zone_id not in graph.zone_ids:
        raise SeaError(400, MSG_NOT_SEA_ZONE)
    region_id = zone_sea.get(zone_id)
    zones = sea_core.storm_zones(graph.adj, zone_sea, zone_id, sea_weather.sea_radius(db, region_id))
    storm = sea_weather.create_storm(db, region_id=region_id, center_zone_id=zone_id, zones=zones,
                                     minutes=int(body.minutes), now=now, source=sea_core.STORM_ADMIN)
    logger.info("sea storm %s started over zone %s (%d zones, %d min)", storm.id, zone_id, len(zones), body.minutes)
    return int(storm.id)


def storm_one(db: Session, storm_id: int) -> dict:
    storm = db.get(models.SeaStorm, int(storm_id))
    if storm is None:
        raise SeaError(404, MSG_STORM_NOT_FOUND)
    return _storms_out(db, [storm])[0]


def stop_storm(db: Session, storm_id: int, now: Optional[datetime] = None) -> None:
    now = now or sea_crud.now_utc()
    _require_weather(db)
    storm = sea_crud._locked(db.query(models.SeaStorm).filter(models.SeaStorm.id == int(storm_id)), db).first()
    if storm is None or storm.status != sea_core.STORM_ACTIVE:
        raise SeaError(404, MSG_STORM_NOT_FOUND)
    sea_weather.end_storm(db, storm, now)


# =====================================================================================================================
# router
# =====================================================================================================================

def _read(db: Session, action):
    try:
        return action()
    except EconomyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except SQLAlchemyError:
        logger.exception("sea admin read failed")
        raise HTTPException(status_code=500, detail=MSG_LOAD_FAILED)
    finally:
        db.rollback()


def _write(db: Session, action):
    try:
        result = action()
        db.commit()
        return result
    except EconomyApiError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except IntegrityError:
        db.rollback()
        logger.warning("sea admin write conflict", exc_info=True)
        raise HTTPException(status_code=409, detail=MSG_CONFLICT)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("sea admin write failed")
        raise HTTPException(status_code=500, detail=MSG_WRITE_FAILED)


def _one(db: Session, ship_id: int) -> dict:
    ship = db.get(models.SeaShip, int(ship_id))
    if ship is None:
        raise SeaError(404, sea_crud.MSG_SHIP_NOT_FOUND)
    return ship_admin_out(db, ship)


@router.get("/admin/sea/ships", response_model=List[ShipAdminOut])
def get_ships(db: Session = Depends(get_db), user: UserRead = Depends(require_permission("locations:read"))):
    return _read(db, lambda: list_ships(db))


@router.post("/admin/sea/ships", response_model=ShipAdminOut, status_code=201)
def post_ship(body: ShipCreate, db: Session = Depends(get_db),
              user: UserRead = Depends(require_permission("locations:create"))):
    ship = _write(db, lambda: create_ship(db, body))
    logger.info("sea ship %s created by user=%s", ship.id, user.id)
    return _read(db, lambda: _one(db, ship.id))


@router.patch("/admin/sea/ships/{ship_id}", response_model=ShipAdminOut)
def patch_ship(body: ShipUpdate, ship_id: int = Path(..., ge=1), db: Session = Depends(get_db),
               user: UserRead = Depends(require_permission("locations:update"))):
    ship, notices = _write(db, lambda: update_ship(db, ship_id, body))
    law_notify.publish(notices)
    logger.info("sea ship %s edited by user=%s (%s)", ship_id, user.id, sorted(body.__fields_set__))
    return _read(db, lambda: _one(db, ship_id))


@router.delete("/admin/sea/ships/{ship_id}", status_code=204)
def remove_ship(ship_id: int = Path(..., ge=1), db: Session = Depends(get_db),
                user: UserRead = Depends(require_permission("locations:delete"))):
    out = _write(db, lambda: delete_ship(db, ship_id))
    try:
        sea_pass.after_commit(db, out)
    except Exception:
        logger.exception("sea ship %s delete: post-commit work failed", ship_id)
    logger.info("sea ship %s deleted by user=%s", ship_id, user.id)
    return Response(status_code=204)


@router.post("/admin/sea/legs/preview", response_model=List[LegOut])
def post_legs_preview(body: LegsPreviewIn, db: Session = Depends(get_db),
                      user: UserRead = Depends(require_permission("locations:read"))):
    def run():
        sea_crud.require_available(db)
        return legs_preview(db, body.stops, body.is_loop, zone_minutes=body.zone_minutes)
    return _read(db, run)


@router.get("/admin/sea/candidates", response_model=CandidatesOut)
def get_candidates(ship_id: Optional[int] = Query(None, ge=1), db: Session = Depends(get_db),
                   user: UserRead = Depends(require_permission("locations:read"))):
    return _read(db, lambda: candidates(db, ship_id))


@router.get("/admin/sea/settings", response_model=SeaSettingsOut)
def get_settings(db: Session = Depends(get_db), user: UserRead = Depends(require_permission("locations:read"))):
    return _read(db, lambda: settings_out(db))


@router.put("/admin/sea/settings", response_model=SeaSettingsOut)
def put_settings(body: SeaSettingsIn, db: Session = Depends(get_db),
                 user: UserRead = Depends(require_permission("locations:update"))):
    _write(db, lambda: save_settings(db, body))
    logger.info("sea settings saved by user=%s", user.id)
    return _read(db, lambda: settings_out(db))


# ---------------------------------------------------------------------------------------------------- FEAT-214 weather

@router.get("/admin/sea/weather", response_model=SeaWeatherOut)
def get_weather(db: Session = Depends(get_db), user: UserRead = Depends(require_permission("locations:read"))):
    return _read(db, lambda: weather_out(db))


@router.put("/admin/sea/seas/{region_id}", response_model=StormSeaOut)
def put_sea(body: StormSeaIn, region_id: int = Path(..., ge=1), db: Session = Depends(get_db),
            user: UserRead = Depends(require_permission("locations:update"))):
    _write(db, lambda: save_sea(db, region_id, body))
    logger.info("sea %s storm config saved by user=%s", region_id, user.id)
    return _read(db, lambda: sea_one(db, region_id))


@router.post("/admin/sea/storms", response_model=StormAdminOut, status_code=201)
def post_storm(body: StormCreateIn, db: Session = Depends(get_db),
               user: UserRead = Depends(require_permission("locations:update"))):
    storm_id = _write(db, lambda: start_storm(db, body))
    logger.info("sea storm %s started by user=%s", storm_id, user.id)
    return _read(db, lambda: storm_one(db, storm_id))


@router.delete("/admin/sea/storms/{storm_id}", status_code=204)
def delete_storm(storm_id: int = Path(..., ge=1), db: Session = Depends(get_db),
                 user: UserRead = Depends(require_permission("locations:update"))):
    _write(db, lambda: stop_storm(db, storm_id))
    logger.info("sea storm %s ended by user=%s", storm_id, user.id)
    return Response(status_code=204)
