"""FEAT-215 sea caravans — cargo of NPC caravans on ships (sync SQLAlchemy; features/FEAT-215 §3.3, §3.5).

* **reachability** (§3.3, this part): :func:`sea_pairs` — per tick run, which port pairs (A → B) the active ships
  carry cargo between, with the minimal zones and the ship ids. Plain reads, no locks; used by
  ``economy_caravan_crud.RoutePlanner`` (``sea_route`` / ``reach``) for planning and dispatch.
* **the sea pass** (§3.5, §3.7) — all inside the ship transaction (ship row already locked by the caller), notices
  go to ``sea_pass.ShipOutcome.notices``: :func:`board` (called by ``sea_pass.depart``: waiting caravans of the docked
  port board a serving ship within its hold, escorts go on deck), :func:`dock_cargo` (every pass for every docked
  ship and from ``sea_pass._dock``: unload at the landing port + :func:`charge_freight`, else strand when the ship no
  longer serves the landing port), :func:`strand_all` (safe landing / vanished deck / ship deleted). Escorts ride
  inside the wagon: moved by plain column writes on rows locked here, never put ashore by the ticket check.
  :func:`aboard_ids` (plain read) feeds the monster raid rows (``sea_raids.caravan_ids``).

Global lock order (§3.6, supersedes FEAT-212 3.15 / FEAT-213 3.7 for these tables): ``sea_ships (asc) → sea_passes →
econ_regions → econ_region_goods → econ_region_events → econ_caravans (asc) → econ_caravan_raids →
econ_caravan_escorts (asc) → econ_caravan_sea_losses → sea_raids → … (FEAT-207 chain) … → characters (asc, ONE sorted
call per tx) → econ_accounts (asc) → character_attributes``. The ship transaction never takes the region / goods /
caravan-raid locks; no caravan / raid / delivery code path locks ``sea_ships``.
"""

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

import caravan_escort_crud as escort_crud
import econ_core as core
import econ_ledger
import economy_caravan_crud as caravan_crud
import models
import sea_core
import sea_crud

logger = logging.getLogger("character-service.sea-cargo")


@dataclass
class SeaPair:
    """Cargo can sail from ``board_port`` to ``alight_port`` on one ship (no transfers)."""

    board_port: int
    alight_port: int
    zones: int
    ship_ids: List[int] = field(default_factory=list)


def plan_horizon(stops_count: int) -> int:
    """Trips looked at for cargo: ``2 × stops`` covers one full there-and-back (or loop) cycle from any stop."""
    return 2 * max(0, int(stops_count))


def ship_pairs(legs) -> Dict[Tuple[int, int], int]:
    """``{(A, B): minimal zones}`` of one ship's plan: for every leg departing from A, every port B reached after it
    without revisiting A (``sea_core.reached_from``)."""
    out: Dict[Tuple[int, int], int] = {}
    for i, leg in enumerate(legs):
        a = int(leg.from_port)
        for b, zones in sea_core.reached_from(legs[i:], a).items():
            key = (a, int(b))
            if key not in out or zones < out[key]:
                out[key] = zones
    return out


def sea_pairs(db: Session) -> Dict[Tuple[int, int], SeaPair]:
    """``{(board port, alight port): SeaPair}`` over all active ships with a cargo hold (``cargo_capacity > 0``).
    Missing sea tables → ``{}``. Plain reads, no locks."""
    if not sea_crud.sea_available(db):
        return {}
    ships = (db.query(models.SeaShip)
             .filter(models.SeaShip.is_active == True, models.SeaShip.cargo_capacity > 0)  # noqa: E712
             .order_by(models.SeaShip.id).all())
    if not ships:
        return {}
    params = sea_crud.load_params(db)
    graph = sea_crud.zone_graph(db)
    out: Dict[Tuple[int, int], SeaPair] = {}
    for ship in ships:
        stops = sea_crud.load_stops(db, ship.id)
        if len(stops) < 2:
            continue
        pl = sea_crud.plan(db, ship, plan_horizon(len(stops)), params=params, stops=stops, graph=graph)
        for key, zones in ship_pairs(pl.legs).items():
            pair = out.get(key)
            if pair is None:
                out[key] = SeaPair(key[0], key[1], zones, [int(ship.id)])
                continue
            if int(ship.id) not in pair.ship_ids:
                pair.ship_ids.append(int(ship.id))
            pair.zones = min(pair.zones, zones)
    return out


# =====================================================================================================================
# the sea pass (§3.5): boarding, unloading, stranding — inside the ship transaction
# =====================================================================================================================

KEY_FREIGHT = "freight"
EV_CARGO_BOARDED = "cargo_boarded"
EV_CARGO_UNLOADED = "cargo_unloaded"
EV_CARGO_STRANDED = "cargo_stranded"

MSG_BOARDED = "Караван погружен на корабль «{ship}» — вы плывёте с грузом до «{port}»"
MSG_UNLOADED = "Груз выгружен в «{port}» — караван идёт дальше по суше"
MSG_STRANDED = "Корабль «{ship}» потерян — караван высажен в «{port}» и возвращается"


def _i(value) -> int:
    return int(value or 0)


def _caravan_q(db: Session):
    return db.query(models.EconCaravan).filter(models.EconCaravan.status == caravan_crud.STATUS_IN_TRANSIT,
                                               models.EconCaravan.is_physical == True)  # noqa: E712


def aboard_ids(db: Session, ship_id: int) -> List[int]:
    """Ids of the caravans in the ship's hold (plain read, ascending)."""
    rows = (_caravan_q(db).with_entities(models.EconCaravan.id)
            .filter(models.EconCaravan.sea_ship_id == int(ship_id),
                    models.EconCaravan.sea_stage == caravan_crud.SEA_ABOARD)
            .order_by(models.EconCaravan.id).all())
    return [int(r[0]) for r in rows]


def cargo_aboard(db: Session, ship_id: int) -> int:
    """How many caravans the ship carries now (plain COUNT; ship admin, cheap pre-check of the pass)."""
    return int(_caravan_q(db).filter(models.EconCaravan.sea_ship_id == int(ship_id),
                                     models.EconCaravan.sea_stage == caravan_crud.SEA_ABOARD).count())


def _lock_caravans(db: Session, ship: "models.SeaShip", port_id: Optional[int] = None) -> List["models.EconCaravan"]:
    """Lock (asc id) the ship's hold and — with ``port_id`` — the caravans waiting at that port for any ship."""
    C = models.EconCaravan
    cond = (C.sea_ship_id == int(ship.id)) & (C.sea_stage == caravan_crud.SEA_ABOARD)
    if port_id:
        cond = or_(cond, (C.sea_board_port_id == int(port_id)) & (C.sea_stage == caravan_crud.SEA_WAITING))
    return sea_crud._locked(_caravan_q(db).filter(cond).order_by(C.id), db).all()


def _lock_escorts(db: Session, caravan_ids: Sequence[int]) -> Dict[int, List[int]]:
    """Lock the active escort rows (asc id) → ``{caravan_id: [character ids]}``."""
    ids = sorted({int(c) for c in caravan_ids})
    out: Dict[int, List[int]] = {c: [] for c in ids}
    if not ids:
        return out
    E = models.EconCaravanEscort
    rows = sea_crud._locked(db.query(E).filter(E.caravan_id.in_(ids), E.status == escort_crud.STATUS_ACTIVE)
                            .order_by(E.id), db).all()
    for r in rows:
        out.setdefault(int(r.caravan_id), []).append(int(r.character_id))
    return out


def lock_characters(db: Session, ids: Sequence[int], deck_id: Optional[int] = None) -> List["models.Character"]:
    """THE sorted characters lock of a ship transaction (§3.6): the given ids ∪ (with ``deck_id``) every player on the
    deck, in one ``FOR UPDATE`` ordered by id."""
    Ch = models.Character
    ids = sorted({int(i) for i in ids})
    conds = []
    if ids:
        conds.append(Ch.id.in_(ids))
    if deck_id:
        conds.append((Ch.current_location_id == int(deck_id)) & Ch.is_npc.is_(False))
    if not conds:
        return []
    return sea_crud._locked(db.query(Ch).filter(or_(*conds)).order_by(Ch.id), db).all()


def _move_escorts(chars: Dict[int, "models.Character"], escort_ids: Sequence[int], caravan: "models.EconCaravan",
                  location_id: int) -> List["models.Character"]:
    """Escorts ride inside the wagon (same rule as ``caravan_escort_crud.move_escorts``): no law entry check."""
    moved = []
    for cid in escort_ids:
        ch = chars.get(int(cid))
        if ch is None or ch.escort_caravan_id is None or int(ch.escort_caravan_id) != int(caravan.id):
            continue
        ch.current_location_id = int(location_id)
        ch.house_room_id = None
        moved.append(ch)
    return moved


def _escort_notices(out, moved: Sequence["models.Character"], message: str, caravan_id: int, event: str) -> None:
    for ch in moved:
        out.notices.append(escort_crud._notice(ch.user_id, message, int(ch.id), int(caravan_id), event=event))


def _econ_params(db: Session):
    import econ_tick                                     # late: econ_tick imports most of the service
    return econ_tick.load_params(db)


def _plan_legs(db: Session, ship: "models.SeaShip"):
    stops = sea_crud.load_stops(db, ship.id)
    if len(stops) < 2:
        return []
    return sea_crud.plan(db, ship, plan_horizon(len(stops)), stops=stops).legs


def _port_name(db: Session, location_id) -> str:
    if not location_id:
        return "—"
    info = sea_crud.location_infos(db, [location_id]).get(int(location_id))
    return (info.name if info is not None and info.name else None) or "—"


def charge_freight(db: Session, caravan: "models.EconCaravan", ship_id: Optional[int], now: datetime) -> Optional[int]:
    """§3.7: the reserved freight leaves the escrow at unloading — to the boarding port's region treasury minus the
    country tax (an explicit leg: ``caravan_escrow`` is not a tax source), or wholly to the region / world treasury
    when the port has no country / region. Idempotent (``caravan:c<id>:freight``); F = 0 or already charged →
    nothing. Returns the op id."""
    amount = _i(caravan.freight)
    if amount <= 0 or _i(caravan.freight_paid) > 0:
        return None
    board = caravan.sea_board_port_id
    region_id, country_id = econ_ledger.resolve_location(db, board)
    escrow = core.AccountRef.caravan_escrow()
    tax = 0
    if region_id and country_id:
        tax = min(amount, core.tax_amount(amount, econ_ledger.get_economy_settings(db).country_tax_rate))
        legs = [core.Leg(escrow, core.AccountRef.region(region_id), amount - tax),
                core.Leg(escrow, core.AccountRef.country(country_id), tax)]
    else:
        legs = [core.Leg(escrow, core.AccountRef.region(region_id) if region_id else core.AccountRef.world(), amount)]
    legs = [leg for leg in legs if leg.amount > 0]
    key = caravan_crud.caravan_key(caravan.id, KEY_FREIGHT)
    try:
        result = econ_ledger.post_operation(
            db, op_type=core.OP_CARAVAN_FREIGHT, legs=legs, source_service=caravan_crud.SOURCE_SERVICE,
            location_id=int(board) if board else None, region_id=region_id, idempotency_key=key, apply_tax=False,
            metadata={"caravan_id": int(caravan.id), "ship_id": int(ship_id) if ship_id else None,
                      "board_port_id": int(board) if board else None,
                      "alight_port_id": int(caravan.sea_alight_port_id) if caravan.sea_alight_port_id else None,
                      "freight": amount, "tax": tax})
        op_id = result.operation_id
    except econ_ledger.DuplicateOperation as exc:
        op_id = exc.operation_id
    caravan.freight_paid = amount
    caravan.freight_op_id = op_id
    return op_id


def _unload(caravan: "models.EconCaravan", now: datetime, params) -> None:
    """Landing port reached: the land leg 2 starts (``route[sea_split_index + 1]`` is the landing port)."""
    route = [int(x) for x in caravan_crud._json_list(caravan.route)]
    index = _i(caravan.sea_split_index) + 1
    caravan.current_location_id = int(caravan.sea_alight_port_id)
    caravan.route_index = min(index, max(0, len(route) - 1))
    caravan.sea_stage = caravan_crud.SEA_LANDED
    caravan.sea_unloaded_at = now
    if not route or index >= len(route) - 1:
        caravan.arrived_at = now
        caravan.next_move_at = None
    else:
        caravan.next_move_at = now + caravan_crud.step_delay(params, random.random())


def _strand(caravan: "models.EconCaravan", target: int) -> None:
    caravan.current_location_id = int(target)
    caravan.sea_stage = caravan_crud.SEA_STRANDED
    caravan.next_move_at = None


def _raided(db: Session, caravan_id: int) -> bool:
    return caravan_crud.active_raid_status(db, int(caravan_id)) in caravan_crud.RAID_ACTIVE_STATUSES


UNLOAD = "unload"
STRAND = "strand"


def _settle_hold(db: Session, ship: "models.SeaShip", caravans: Sequence["models.EconCaravan"],
                 decide: Callable, now: datetime, out, deck_id: Optional[int] = None) -> int:
    """Shared tail of :func:`dock_cargo` / :func:`strand_all`: ``decide(caravan) -> (UNLOAD | STRAND, location)`` or
    None (stays aboard). Lock order: escorts → characters (one sorted call; with ``deck_id`` the deck players too, so
    a later put-ashore of the deck only re-locks held rows) → accounts (freight). Returns the number of caravans that
    left the hold."""
    todo: List[Tuple["models.EconCaravan", str, int]] = []
    for c in caravans:
        if c.sea_stage != caravan_crud.SEA_ABOARD or _i(c.sea_ship_id) != int(ship.id):
            continue
        verdict = decide(c)
        if verdict is not None:
            todo.append((c, verdict[0], int(verdict[1])))
    if not todo:
        return 0
    escorts = _lock_escorts(db, [c.id for c, _a, _l in todo])
    chars = {int(ch.id): ch for ch in lock_characters(db, [cid for ids in escorts.values() for cid in ids],
                                                      deck_id)}
    params = _econ_params(db) if any(a == UNLOAD for _c, a, _l in todo) else None
    unloaded: List["models.EconCaravan"] = []
    for c, action, loc in todo:
        port_name = _port_name(db, loc)
        if action == UNLOAD:
            _unload(c, now, params)
            unloaded.append(c)
            moved = _move_escorts(chars, escorts.get(int(c.id), []), c, loc)
            _escort_notices(out, moved, MSG_UNLOADED.format(port=port_name), c.id, EV_CARGO_UNLOADED)
            logger.info("sea ship %s: caravan %s unloaded at %s", ship.id, c.id, loc)
        else:
            _strand(c, loc)
            moved = _move_escorts(chars, escorts.get(int(c.id), []), c, loc)
            _escort_notices(out, moved, MSG_STRANDED.format(ship=ship.name, port=port_name), c.id, EV_CARGO_STRANDED)
            logger.warning("sea ship %s: caravan %s stranded at %s", ship.id, c.id, loc)
    db.flush()
    for c in unloaded:                                   # accounts last (§3.6)
        charge_freight(db, c, ship.id, now)
    db.flush()
    return len(todo)


def dock_cargo(db: Session, ship: "models.SeaShip", now: datetime, out) -> int:
    """§3.5: the hold of a (locked) docked ship. A caravan whose landing port is the docked port is unloaded (not while
    a caravan raid is active — it waits; freight charged); any other caravan is stranded at the docked port when the
    ship is off or its plan no longer carries cargo from here to the landing port. A docked ship without a port (a
    broken landing) strands everything at ``sea_crud.landing_target``. Returns the number of caravans that left the
    hold (their escorts' character rows were locked and moved). Lock order: passes → caravans → escorts → characters
    → accounts."""
    if ship.status != sea_core.STATUS_DOCKED or cargo_aboard(db, ship.id) == 0:
        return 0
    sea_crud.active_passes(db, ship.id, lock=True)     # ship → passes → caravans (§3.6)
    caravans = _lock_caravans(db, ship)
    if not caravans:
        return 0
    port = int(ship.docked_port_id) if ship.docked_port_id else None
    if port is None:
        target, _fallback = sea_crud.landing_target(db, ship)
        if target is None:
            logger.error("sea ship %s: %d caravans aboard and nowhere to land them", ship.id, len(caravans))
            return 0
        return _settle_hold(db, ship, caravans, lambda c: None if _raided(db, c.id) else (STRAND, target), now, out)
    legs: List = []
    planned = False

    def decide(c):
        nonlocal legs, planned
        if _raided(db, c.id):
            return None
        if c.sea_alight_port_id and int(c.sea_alight_port_id) == port:
            return UNLOAD, port
        if not ship.is_active:
            return STRAND, port
        if not planned:
            legs, planned = _plan_legs(db, ship), True
        if sea_core.serves(legs, port, c.sea_alight_port_id) is None:
            return STRAND, port
        return None

    return _settle_hold(db, ship, caravans, decide, now, out)


def strand_all(db: Session, ship: "models.SeaShip", target: Optional[int], now: datetime, out) -> int:
    """§3.5: the ship is lost (safe landing / vanished deck / deleted): every caravan of the hold without an active
    caravan raid leaves it at ``target`` — unloaded normally when ``target`` is its landing port, else ``stranded``
    (the caravan pass cancels it). A raided caravan stays aboard (the next pass's :func:`dock_cargo` handles it). No
    target → nothing moves (logged). Call it BEFORE ``sea_crud.safe_land`` / the deck put-ashore so the escorts land
    with their caravan; it takes the passes lock first (ship → passes → caravans → escorts → characters)."""
    if cargo_aboard(db, ship.id) == 0:
        return 0
    if target is None:
        logger.error("sea ship %s: caravans aboard and nowhere to land them", ship.id)
        return 0
    sea_crud.active_passes(db, ship.id, lock=True)
    caravans = _lock_caravans(db, ship)

    def decide(c):
        if _raided(db, c.id):
            return None
        if c.sea_alight_port_id and int(c.sea_alight_port_id) == int(target):
            return UNLOAD, int(target)
        return STRAND, int(target)

    return _settle_hold(db, ship, caravans, decide, now, out, deck_id=int(ship.deck_location_id))


def raided_aboard(db: Session, ship_id: int) -> bool:
    """A caravan in the ship's hold is under an active caravan raid (plain read; ship delete refuses)."""
    return any(_raided(db, cid) for cid in aboard_ids(db, ship_id))


@dataclass
class Boarding:
    """Result of :func:`board` for ``sea_pass.depart``."""

    players: List["models.Character"] = field(default_factory=list)   # locked, standing on the deck after boarding
    escort_ids: Set[int] = field(default_factory=set)                 # sail with their cargo, no pass needed
    boarded: List[int] = field(default_factory=list)


def board(db: Session, ship: "models.SeaShip", now: datetime, out) -> Boarding:
    """§3.5 boarding at the departure of a (locked) docked ship — call after the passes lock, INSTEAD of the deck
    players lock. Waiting caravans of the docked port (asc id; skipped while a raid / post hold holds them) board while
    the hold has room (``cargo_capacity − aboard``) and the ship's plan carries cargo from here to their landing port
    without coming back to it. Then ONE sorted characters lock (deck players ∪ escorts of every caravan in the hold)
    and the escorts of the boarded caravans step on deck. Returns the locked players standing on the deck after
    boarding (for the ticket check) and the escort ids exempt from it."""
    deck = int(ship.deck_location_id)
    port = int(ship.docked_port_id) if ship.docked_port_id else None
    caravans = _lock_caravans(db, ship, port)
    hold = [c for c in caravans if c.sea_stage == caravan_crud.SEA_ABOARD and _i(c.sea_ship_id) == int(ship.id)]
    waiting = [c for c in caravans if c.sea_stage == caravan_crud.SEA_WAITING]
    boarded: List["models.EconCaravan"] = []
    free = max(0, _i(ship.cargo_capacity) - len(hold))
    if waiting and free > 0 and port is not None:
        params = _econ_params(db)
        try:
            gates = caravan_crud.gate_tables_available(db)
        except Exception:
            gates = False
        legs = _plan_legs(db, ship)
        for c in waiting:
            if len(boarded) >= free:
                break
            if sea_core.serves(legs, port, c.sea_alight_port_id) is None:
                continue
            if caravan_crud.held_by(db, c, now, params, gates) is not None:
                continue
            c.sea_stage = caravan_crud.SEA_ABOARD
            c.sea_ship_id = int(ship.id)
            c.sea_boarded_at = now
            c.current_location_id = deck
            c.next_move_at = None
            boarded.append(c)
    in_hold = hold + boarded
    escorts = _lock_escorts(db, [c.id for c in in_hold])
    chars = lock_characters(db, [cid for ids in escorts.values() for cid in ids], deck)
    by_id = {int(ch.id): ch for ch in chars}
    boarded_ids = {int(c.id) for c in boarded}
    exempt: Set[int] = set()
    for c in in_hold:
        ids = escorts.get(int(c.id), [])
        if int(c.id) in boarded_ids:
            moved = _move_escorts(by_id, ids, c, deck)
            _escort_notices(out, moved, MSG_BOARDED.format(ship=ship.name, port=_port_name(db, c.sea_alight_port_id)),
                            c.id, EV_CARGO_BOARDED)
            logger.info("sea ship %s: caravan %s boarded at %s for %s", ship.id, c.id, port, c.sea_alight_port_id)
        for cid in ids:
            ch = by_id.get(int(cid))
            if ch is not None and ch.escort_caravan_id is not None and int(ch.escort_caravan_id) == int(c.id):
                exempt.add(int(cid))
    db.flush()
    players = [ch for ch in chars if not ch.is_npc and ch.current_location_id is not None
               and int(ch.current_location_id) == deck]
    return Boarding(players, exempt, sorted(boarded_ids))
