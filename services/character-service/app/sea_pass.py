"""FEAT-213 §3.8–3.10: the sea pass of the character-service scheduler.

Called from ``econ_scheduler.run_scheduled_once`` right after the faction pass. Ships are not economy: the pass runs
even when the economy tick is switched off in the DB. Throttle: a conditional UPDATE claim on
``sea_settings.pass_last_run_at`` (>= :data:`RUN_INTERVAL_SECONDS`), so several processes never double-run; a missing
table / row (deploy skew) → ``None``.

One short transaction per ship (lock order ship → passes → characters, as everywhere in ``sea_crud``); a failure is
logged and the ship is retried on the next pass. Per ship, in order:

1. sanity — the deck location vanished → safe landing of everyone still standing on the old deck id, ship off;
2. docked & active & ``departs_at <= now`` → **departure** (:func:`depart`): entitlement of everyone on the deck
   (ticket / sailor post / stowaway roll), put ashore of the unentitled (players in a battle are never moved), burn /
   expire passes of holders not aboard, the leg path is frozen, the Captain goes on deck;
3. sailing & ``next_zone_at <= now`` → zone stepping with offline catch-up, then **arrival** (:func:`arrive`) with the
   skip of an invalid stop and the safe landing when no valid stop is left;
4. Captain placement — an alive Captain standing elsewhere than expected (port while docked, deck at sea) is moved
   back (admin manual moves are reverted).

FEAT-214 (§3.6) adds, in the same ship transaction (no HTTP): the **raid hold** release / expiry before anything else;
the **storm postpone** of a departure from a port whose zone is stormy; **zone effects** on the effective zone entry
(slowdown ``storm_extra``, storm damage targets, drift, the monster roll — steps skipped through by an offline catch-up
are quiet); the **sailor relief** of a storm delay; the re-landing of players kept aboard by a battle. The weather step
runs once per pass before the ships, the raid fallbacks after them. After the commit: the CAS storm damage and the raid
start (``sea_raid_crud.start_pending``).

After the commit (best effort): LS «character left the location» cleanup + gathering cancel for everyone put ashore,
law encounter / slip / wanted notices, the sea notices (``ws_type="sea"``). :func:`after_commit` is shared with the
ship admin (delete ship). Never started under pytest by the scheduler; tests call :func:`run_pass` directly
(``now=`` / ``force=``) and :func:`process_ship`.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

import law_core as lc
import law_notify
import models
import sea_core
import sea_crud
import sea_raid_crud
import sea_weather

logger = logging.getLogger("character-service.sea_pass")

RUN_INTERVAL_SECONDS = 25
GATHER_CANCEL_REASON = "sea"

_CENT = Decimal("0.01")

EV_DEPARTED = "departed"
EV_ARRIVED = "arrived"
EV_ASHORE = "ashore"
EV_SAILOR_ASHORE = "sailor_ashore"
EV_CAUGHT = "caught"
EV_BURNT = "burnt"
EV_REROUTED = "rerouted"
EV_SAFE_LANDING = "safe_landing"
# FEAT-214
EV_STORM = "storm"
EV_DRIFT = "drift"
EV_STORM_DELAY = "storm_delay"
EV_STORM_RELIEF = "storm_relief"
EV_RAID = sea_raid_crud.EV_RAID
EV_RAID_REPELLED = sea_raid_crud.EV_RAID_REPELLED
EV_RAID_WON = sea_raid_crud.EV_RAID_WON
EV_RAID_LOST = sea_raid_crud.EV_RAID_LOST
EV_HOLD_RELEASED = "hold_released"
EV_HOLD_EXPIRED = "hold_expired"


# =====================================================================================================================
# outcome of one ship (collected inside the transaction, acted upon after the commit)
# =====================================================================================================================

@dataclass
class ShipOutcome:
    ship_id: int
    events: List[str] = field(default_factory=list)
    notices: List[law_notify.Notice] = field(default_factory=list)
    ashore: List[sea_crud.AshoreResult] = field(default_factory=list)
    deck_location_id: Optional[int] = None
    gathering_ids: Set[int] = field(default_factory=set)       # put ashore while gathering (cancel after commit)
    wanted_changes: list = field(default_factory=list)
    # FEAT-214 (acted upon after the commit)
    now: Optional[datetime] = None
    storm_damage_ids: List[int] = field(default_factory=list)  # rocked deck players (never those in a battle)
    storm_hp_pct: Decimal = Decimal("0")
    storm_stamina_pct: Decimal = Decimal("0")
    raids_planned: bool = False                                 # starting raid rows to start


def claim_run(db: Session, now: datetime) -> bool:
    """Conditional claim (commits). False when another run is recent, or there is no settings table / row."""
    cutoff = now - timedelta(seconds=RUN_INTERVAL_SECONDS)
    try:
        result = db.execute(text(
            "UPDATE sea_settings SET pass_last_run_at = :now WHERE id = 1 "
            "AND (pass_last_run_at IS NULL OR pass_last_run_at <= :cutoff)"), {"now": now, "cutoff": cutoff})
        db.commit()
    except DBAPIError:
        db.rollback()
        logger.warning("sea pass: sea_settings is not available", exc_info=True)
        return False
    return (result.rowcount or 0) == 1


def _probe(db: Session, sql: str, params: dict) -> bool:
    rows = sea_crud._rows(db, sql, params)
    return bool(rows)


def in_battle(db: Session, character_id: int) -> bool:
    """An active battle of the character (battle-service tables; absent → False)."""
    return _probe(db, "SELECT 1 FROM battles b JOIN battle_participants bp ON b.id = bp.battle_id "
                      "WHERE bp.character_id = :c AND b.status IN ('pending', 'in_progress') "
                      "AND bp.dropped_out_at IS NULL LIMIT 1", {"c": int(character_id)})


def gathering(db: Session, character_id: int) -> bool:
    return _probe(db, "SELECT 1 FROM gathering_sessions WHERE character_id = :c AND status = 'active' LIMIT 1",
                  {"c": int(character_id)})


def sailor_worked(db: Session, character_id: int, deck_id: int, floor_id: Optional[int], min_chars: int) -> bool:
    """A post on the deck written after the hire (``posts.id > post_floor_id``) with a plain length ≥ ``min_chars``
    (the boarding post counts)."""
    rows = sea_crud._rows(db, "SELECT content FROM posts WHERE character_id = :c AND location_id = :l AND id > :f",
                          {"c": int(character_id), "l": int(deck_id), "f": int(floor_id or 0)}) or []
    return any(sea_core.plain_length(r[0]) >= int(min_chars) for r in rows)


def _name(locs: Dict[int, sea_crud.LocInfo], location_id) -> str:
    if not location_id:
        return "—"
    info = locs.get(int(location_id))
    return (info.name if info is not None and info.name else None) or "—"


def _minutes_until(when: Optional[datetime], now: datetime) -> int:
    if when is None:
        return 0
    return max(1, int((when - now).total_seconds() + 59) // 60)


# =====================================================================================================================
# the Captain
# =====================================================================================================================

def expected_captain_location(db: Session, ship: "models.SeaShip") -> Optional[int]:
    """Where the Captain must stand: the docked port, or the deck at sea (None = nowhere valid)."""
    target = ship.docked_port_id if ship.status == sea_core.STATUS_DOCKED else ship.deck_location_id
    if not target:
        return None
    return int(target) if int(target) in sea_crud.location_infos(db, [target]) else None


def place_captain(db: Session, ship: "models.SeaShip", reason: str) -> bool:
    """Move an alive Captain NPC of the ship to where he must stand (no commit). Missing / dead / role removed / in a
    battle → nothing (retried by the next pass). Returns True when he was moved."""
    if not ship.captain_npc_id:
        return False
    target = expected_captain_location(db, ship)
    if target is None:
        return False
    npc = db.get(models.Character, int(ship.captain_npc_id))
    if npc is None or not npc.is_npc or npc.npc_role != sea_core.CAPTAIN_ROLE or npc.npc_status == sea_crud.NPC_DEAD:
        return False
    if npc.current_location_id is not None and int(npc.current_location_id) == target:
        return False
    if in_battle(db, npc.id):
        logger.info("sea ship %s: captain %s is in a battle, placement postponed", ship.id, npc.id)
        return False
    logger.info("sea ship %s: captain %s moved %s -> %s (%s)", ship.id, npc.id, npc.current_location_id, target,
                reason)
    npc.current_location_id = target
    db.flush()
    return True


# =====================================================================================================================
# the stowaway roll (FEAT-199 / FEAT-201 machinery)
# =====================================================================================================================

@dataclass
class StowawayRoll:
    caught: bool
    masked: bool
    chance: Decimal
    roll: Optional[Decimal]
    reduction_pct: Decimal


def stowaway_roll(db: Session, character_id: int, base_pct, law_settings) -> StowawayRoll:
    """The crew's notice roll: ``member_chance(stowaway_base_pct, stealth reduction, mask, fame)`` clamped to the
    law detection bounds, rolled with the law detection RNG (tests patch ``law_crud.detection_rng``)."""
    import law_crud
    import renown_crud
    import shadow_core as sc
    import shadow_crud
    shadow_s = shadow_crud.load_settings(db)
    info = law_crud.stealth_info(db, character_id, shadow_s)
    masked = shadow_crud.wears_mask(db, character_id)
    fame = Decimal(0) if masked else shadow_crud.fame_witness_pct(
        db, character_id, renown_crud.load_renown_tiers(db, sc.SCALE_FAME))
    raw = sc.member_chance(base_pct, info.reduction_pct, masked, fame)
    lo, hi = Decimal(str(law_settings.detect_min_pct)), Decimal(str(law_settings.detect_max_pct))
    chance = max(lo, min(hi, Decimal(str(raw)))).quantize(_CENT, rounding=ROUND_HALF_UP)
    caught, roll = lc.roll_succeeds(chance, law_crud.detection_rng())
    return StowawayRoll(bool(caught), bool(masked), chance, roll, Decimal(str(info.reduction_pct)))


def register_stowaway_crime(db: Session, pass_row: "models.SeaPass", port_id: Optional[int], result: StowawayRoll,
                            points: int, now: datetime, out: ShipOutcome) -> None:
    """The crime of a caught stowaway in the port's region (§3.9 step 4) — the single-member branch of
    ``shadow_crud.npc_kill_consequences``: not masked → reported (wanted at once); masked → a deferred masked crime +
    the region's suspicion. No region (port gone) → nothing."""
    import law_crud
    import reputation_crud
    import shadow_crud
    region_id = reputation_crud.location_region(db, port_id) if port_id else None
    if not region_id:
        logger.warning("sea pass %s: caught stowaway, port %s has no region — no crime", pass_row.id, port_id)
        return
    shadow_s = shadow_crud.load_settings(db)
    masked = result.masked and bool(shadow_s.witness_enabled)
    cid = int(pass_row.character_id)
    common = dict(crime_type=lc.CRIME_STOWAWAY, character_id=cid, region_id=int(region_id), points=int(points),
                  event_key=f"law:stowaway:{int(pass_row.id)}", location_id=int(port_id), now=now, masked=masked,
                  witness_chance_pct=result.chance, witness_roll_pct=result.roll,
                  stealth_reduction_pct=result.reduction_pct)
    if not masked:
        crime = law_crud.register_crime(db, status=lc.CRIME_REPORTED, **common)
        if crime.change is not None:
            out.wanted_changes.append(crime.change)
        return
    crime = law_crud.register_crime(db, status=lc.CRIME_MASKED,
                                    reveal_until=now + timedelta(days=int(shadow_s.reveal_days)),
                                    next_roll_at=now + shadow_crud.REVEAL_STEP, **common)
    if crime.crime is None:
        return
    shadow_crud.add_suspicion(db, int(region_id), shadow_s.suspicion_masked, shadow_s, now)
    user_id = law_crud.character_user_ids(db, [cid]).get(cid)
    out.notices.append(law_notify.Notice(user_id, law_notify.MSG_MASKED, law_notify.WS_MASKED,
                                         law_notify.CATEGORY_PROGRESS, {"character_id": cid}))


# =====================================================================================================================
# departure (§3.9)
# =====================================================================================================================

def _ashore(db: Session, out: ShipOutcome, ch: "models.Character", target: int, law_check: bool, deck_id: int,
            reason: str, now: datetime) -> None:
    if gathering(db, ch.id):
        out.gathering_ids.add(int(ch.id))
    out.ashore.append(sea_crud.put_ashore(db, ch, target, deck_id, reason, law_check=law_check, now=now))


def depart(db: Session, ship: "models.SeaShip", now: datetime, out: ShipOutcome) -> bool:
    """Departure of trip ``k = trip_no + 1`` of a locked, docked, active ship (no commit). False = stays docked
    (no valid next stop / no path; ``blocked_reason`` set, retried every pass)."""
    params = sea_crud.load_params(db)
    stops = sea_crud.load_stops(db, ship.id)
    pl = sea_crud.plan(db, ship, 1, params=params, stops=stops)
    if not pl.legs:
        reason = pl.problem or sea_core.BLOCKED_NO_VALID_STOP
        if ship.blocked_reason != reason:
            logger.warning("sea ship %s can't depart: %s", ship.id, reason)
            ship.blocked_reason = reason
            ship.updated_at = now
        return False
    leg = pl.legs[0]
    k = sea_crud.next_trip(ship)
    deck = int(ship.deck_location_id)
    port_id = int(ship.docked_port_id) if ship.docked_port_id else None
    locs = sea_crud.location_infos(db, [port_id, leg.to_port])
    port_name, next_name = _name(locs, port_id), _name(locs, leg.to_port)
    target, fallback = sea_crud.landing_target(db, ship, stops)

    passes = sea_crud.active_passes(db, ship.id, lock=True)
    players = sea_crud.deck_players(db, ship, lock=True)
    covering: Dict[int, "models.SeaPass"] = {}
    rank = {sea_core.KIND_TICKET: 0, sea_core.KIND_SAILOR: 1, sea_core.KIND_STOWAWAY: 2}
    for p in passes:
        if sea_core.covers(p.first_trip, p.last_trip, k):
            cur = covering.get(int(p.character_id))
            if cur is None or rank.get(p.kind, 9) < rank.get(cur.kind, 9):
                covering[int(p.character_id)] = p

    import law_crud
    law_s = law_crud.load_settings(db)
    aboard: Set[int] = set()
    sailing_ids: List["models.Character"] = []
    ship_name = ship.name
    for ch in players:
        cid = int(ch.id)
        aboard.add(cid)
        if in_battle(db, cid):
            logger.info("sea ship %s departure: character %s is in a battle and stays aboard", ship.id, cid)
            sailing_ids.append(ch)
            continue
        p = covering.get(cid)
        if p is not None and p.kind == sea_core.KIND_TICKET:
            sailing_ids.append(ch)
            continue
        if p is not None and p.kind == sea_core.KIND_SAILOR:
            if sailor_worked(db, cid, deck, p.post_floor_id, params.sailor_post_min_chars):
                sailing_ids.append(ch)
                continue
            p.status, p.ended_at = sea_core.PASS_ASHORE, now
            if target is None:
                sailing_ids.append(ch)
                continue
            msg = (f"Капитан корабля «{ship_name}» высадил вас в «{_name(sea_crud.location_infos(db, [target]), target)}»"
                   f": вы не отработали матросом (нужен пост на палубе от {params.sailor_post_min_chars} символов)")
            _ashore(db, out, ch, target, not fallback, deck, msg, now)
            out.notices.append(sea_crud.notice(ch.user_id, msg, cid, ship.id, EV_SAILOR_ASHORE, pass_id=int(p.id)))
            continue
        if p is not None and p.kind == sea_core.KIND_STOWAWAY:
            roll = stowaway_roll(db, cid, params.stowaway_base_pct, law_s)
            logger.info("sea ship %s stowaway %s (pass %s): chance=%s roll=%s caught=%s masked=%s", ship.id, cid,
                        p.id, roll.chance, roll.roll, roll.caught, roll.masked)
            if not roll.caught:
                sailing_ids.append(ch)
                continue
            p.status, p.ended_at = sea_core.PASS_CAUGHT, now
            register_stowaway_crime(db, p, port_id, roll, params.stowaway_wanted_points, now, out)
            if target is None:
                sailing_ids.append(ch)
                continue
            msg = (f"Команда корабля «{ship_name}» поймала вас без билета и высадила в "
                   f"«{_name(sea_crud.location_infos(db, [target]), target)}»")
            _ashore(db, out, ch, target, not fallback, deck, msg, now)
            out.notices.append(sea_crud.notice(ch.user_id, msg, cid, ship.id, EV_CAUGHT, pass_id=int(p.id)))
            continue
        # no right for this trip (no pass / the ticket ended): put ashore without consequences (user decision)
        if target is None:
            logger.error("sea ship %s departure: nowhere to put character %s ashore", ship.id, cid)
            sailing_ids.append(ch)
            continue
        msg = (f"Корабль «{ship_name}» отплыл без вас: вас высадили в "
               f"«{_name(sea_crud.location_infos(db, [target]), target)}» (нет билета на этот рейс)")
        _ashore(db, out, ch, target, not fallback, deck, msg, now)
        out.notices.append(sea_crud.notice(ch.user_id, msg, cid, ship.id, EV_ASHORE))

    # passes covering k whose holder is not aboard: tickets burn, sailor / stowaway attempts expire
    for p in passes:
        if p.status != sea_core.PASS_ACTIVE:
            continue
        if _i(p.last_trip) < k:                      # stale (should have completed at arrival)
            p.status, p.ended_at = sea_core.PASS_COMPLETED, now
            continue
        if not sea_core.covers(p.first_trip, p.last_trip, k) or int(p.character_id) in aboard:
            continue
        if p.kind == sea_core.KIND_TICKET:
            p.status, p.ended_at = sea_core.PASS_BURNT, now
            user = db.execute(text("SELECT user_id FROM characters WHERE id = :c"),
                              {"c": int(p.character_id)}).first()
            out.notices.append(sea_crud.notice(user[0] if user is not None else None,
                                               f"Корабль «{ship_name}» ушёл без вас — билет сгорел",
                                               p.character_id, ship.id, EV_BURNT, pass_id=int(p.id)))
        else:
            p.status, p.ended_at = sea_core.PASS_EXPIRED, now

    # the ship sails
    zone_minutes = max(1, _i(ship.zone_minutes))
    ship.status = sea_core.STATUS_SAILING
    ship.trip_no = k
    ship.stop_index = int(leg.from_idx)
    ship.next_stop_index = int(leg.to_idx)
    ship.direction = int(leg.direction)
    ship.next_port_id = int(leg.to_port)
    ship.leg_path = [int(z) for z in leg.path]
    ship.leg_pos = 0
    ship.current_zone_id = int(leg.path[0])
    ship.next_zone_at = now + timedelta(minutes=zone_minutes)
    ship.last_port_id = port_id or ship.last_port_id
    ship.docked_port_id = None
    ship.departs_at = None
    ship.blocked_reason = None
    _clear_storm_state(ship)
    ship.updated_at = now
    db.flush()
    place_captain(db, ship, "departure")

    eta = _minutes_until(now + timedelta(minutes=sea_core.leg_minutes(len(leg.path), zone_minutes)), now)
    for ch in sailing_ids:
        out.notices.append(sea_crud.notice(
            ch.user_id, f"Корабль «{ship_name}» отплыл из «{port_name}». Следующая остановка — «{next_name}», "
                        f"прибытие ≈ через {eta} мин", ch.id, ship.id, EV_DEPARTED))
    out.events.append(EV_DEPARTED)
    logger.info("sea ship %s departed (trip %s) %s -> %s, %d zones, %d aboard, %d put ashore", ship.id, k, port_id,
                leg.to_port, len(leg.path), len(sailing_ids), len(out.ashore))
    return True


# =====================================================================================================================
# zone stepping, arrival, invalid stops (§3.8 step 3, §3.10)
# =====================================================================================================================

def _i(value) -> int:
    return int(value or 0)


def _clear_storm_state(ship: "models.SeaShip") -> None:
    """Leg-bound FEAT-214 state: raid hold, storm delay of the zone, pending relief, departure postpone."""
    ship.hold_until = None
    ship.storm_extra_minutes = 0
    ship.storm_post_floor_id = None
    ship.storm_hold_since = None


def _dock(db: Session, ship: "models.SeaShip", stop_idx: int, port_id: int, zone_id: int, now: datetime,
          out: ShipOutcome) -> None:
    trip = _i(ship.trip_no)
    ship.status = sea_core.STATUS_DOCKED
    ship.stop_index = int(stop_idx)
    ship.next_stop_index = None
    ship.docked_port_id = int(port_id)
    ship.next_port_id = None
    ship.current_zone_id = int(zone_id)
    ship.leg_path = None
    ship.leg_pos = 0
    ship.next_zone_at = None
    ship.last_port_id = int(port_id)
    ship.departs_at = now + timedelta(minutes=max(1, _i(ship.boarding_minutes))) if ship.is_active else None
    if ship.is_active:
        ship.blocked_reason = None
    _clear_storm_state(ship)
    ship.updated_at = now
    completed: Set[int] = set()
    still_covered: Set[int] = set()
    for p in sea_crud.active_passes(db, ship.id, lock=True):
        if _i(p.last_trip) <= trip:
            p.status, p.ended_at = sea_core.PASS_COMPLETED, now
            completed.add(int(p.character_id))
        else:
            still_covered.add(int(p.character_id))
    db.flush()
    place_captain(db, ship, "arrival")
    port_name = _name(sea_crud.location_infos(db, [port_id]), port_id)
    for ch in sea_crud.deck_players(db, ship, lock=False):
        msg = f"Корабль «{ship.name}» прибыл в «{port_name}»"
        if int(ch.id) in completed and int(ch.id) not in still_covered:
            msg += (f". Ваш билет до «{port_name}» использован. Чтобы плыть дальше, купите новый у капитана до "
                    f"отплытия, иначе вас высадят")
        out.notices.append(sea_crud.notice(ch.user_id, msg, ch.id, ship.id, EV_ARRIVED))
    out.events.append(EV_ARRIVED)
    logger.info("sea ship %s arrived at %s (trip %s)", ship.id, port_id, trip)


def _land_broken(db: Session, ship: "models.SeaShip", reason: str, now: datetime, out: ShipOutcome) -> None:
    """Safe landing at sea (no valid stop / no path): everyone ashore, ship off and docked where it last was (so the
    admin can edit its stops)."""
    result = sea_crud.safe_land(db, ship, reason, now)
    # active_passes() below re-reads with populate_existing() and the session does not
    # autoflush: flush so the passes safe_land just refunded stay 'refunded'.
    db.flush()
    _collect_landing(db, result, out)
    stops = sea_crud.load_stops(db, ship.id)
    last = ship.last_port_id
    ship.status = sea_core.STATUS_DOCKED
    ship.next_stop_index = None
    ship.next_port_id = None
    ship.leg_path = None
    ship.leg_pos = 0
    ship.next_zone_at = None
    _clear_storm_state(ship)
    ship.docked_port_id = int(last) if last and int(last) in sea_crud.location_infos(db, [last]) else None
    for s in stops:
        if ship.docked_port_id and int(s.port_location_id) == int(ship.docked_port_id):
            ship.stop_index = int(s.idx)
            break
    for p in sea_crud.active_passes(db, ship.id, lock=True):
        p.status, p.ended_at = sea_core.PASS_COMPLETED, now
    db.flush()
    place_captain(db, ship, "safe landing")
    out.events.append(EV_SAFE_LANDING)
    logger.warning("sea ship %s: safe landing (%s), %d players put ashore", ship.id, reason, len(result.ashore))


def _collect_landing(db: Session, result: "sea_crud.LandingResult", out: ShipOutcome) -> None:
    out.notices.extend(result.notices)
    out.ashore.extend(result.ashore)
    out.deck_location_id = result.deck_location_id or out.deck_location_id
    for a in result.ashore:
        if gathering(db, a.character_id):
            out.gathering_ids.add(int(a.character_id))


def arrive(db: Session, ship: "models.SeaShip", now: datetime, out: ShipOutcome) -> None:
    """The end of the current leg: dock at the next stop when it is still valid; else sail on to the following valid
    stop from the current zone (tickets ending at the skipped stop end at the real arrival); no valid stop / no
    path → safe landing."""
    params = sea_crud.load_params(db)
    stops = sea_crud.load_stops(db, ship.id)
    graph = sea_crud.zone_graph(db)
    locs = sea_crud.location_infos(db, [s.port_location_id for s in stops])
    valid = sea_crud.valid_stop_indexes(stops, locs, graph.zone_ids)
    n = len(stops)
    j = ship.next_stop_index
    if j is not None and 0 <= int(j) < n and int(j) in valid:
        port = int(stops[int(j)].port_location_id)
        _dock(db, ship, int(j), port, int(locs[port].port_zone_id), now, out)
        return
    nxt = sea_core.next_valid_stop(int(j if j is not None else ship.stop_index), _i(ship.direction) or 1, n,
                                   bool(ship.is_loop), valid) if n >= 2 else None
    if nxt is None:
        _land_broken(db, ship, sea_core.BLOCKED_NO_VALID_STOP, now, out)
        return
    to_idx, direction, _skipped = nxt
    to_port = int(stops[to_idx].port_location_id)
    path, _problem, _used = sea_core.leg_path(graph.adj, graph.zone_ids, ship.current_zone_id,
                                              locs[to_port].port_zone_id, None, params.path_max_zones)
    if path is None:
        _land_broken(db, ship, sea_core.BLOCKED_NO_PATH, now, out)
        return
    skipped_port = ship.next_port_id
    skipped_name = _name(sea_crud.location_infos(db, [skipped_port]), skipped_port)
    ship.next_stop_index = int(to_idx)
    ship.direction = int(direction)
    ship.next_port_id = to_port
    ship.leg_path = [int(z) for z in path]
    ship.leg_pos = 0
    ship.current_zone_id = int(path[0])
    ship.next_zone_at = now + timedelta(minutes=max(1, _i(ship.zone_minutes)))
    ship.updated_at = now
    db.flush()
    to_name = _name(locs, to_port)
    for ch in sea_crud.deck_players(db, ship, lock=False):
        out.notices.append(sea_crud.notice(
            ch.user_id, f"Корабль «{ship.name}» не может зайти в «{skipped_name}» и идёт дальше — в «{to_name}»",
            ch.id, ship.id, EV_REROUTED))
    out.events.append(EV_REROUTED)
    logger.warning("sea ship %s: stop %s is invalid, rerouted to stop %s (%s)", ship.id, j, to_idx, to_port)


def _deck_notice(db: Session, ship: "models.SeaShip", message: str, event: str, out: ShipOutcome,
                 players: Optional[Sequence["models.Character"]] = None, **data) -> None:
    for ch in players if players is not None else sea_crud.deck_players(db, ship, lock=False):
        out.notices.append(sea_crud.notice(ch.user_id, message, ch.id, ship.id, event, **data))


def _zone_effects(db: Session, ship: "models.SeaShip", storm: Optional["sea_weather.StormInfo"],
                  params: "sea_crud.SeaParams", now: datetime, out: ShipOutcome) -> bool:
    """The effective entry into ``current_zone_id`` (§3.6.2): storm damage targets + notice, the drift roll, the
    monster roll. True = stop the stepping loop (a drift or an attack happened)."""
    rng = sea_core.weather_rng()
    players = sea_crud.deck_players(db, ship, lock=False)
    stop = False
    if storm is not None:
        zone_name = _name(sea_crud.location_infos(db, [ship.current_zone_id]), ship.current_zone_id)
        out.storm_damage_ids.extend(int(ch.id) for ch in players if not in_battle(db, ch.id))
        out.storm_hp_pct, out.storm_stamina_pct = params.storm_hp_pct, params.storm_stamina_pct
        _deck_notice(db, ship, f"Корабль «{ship.name}» попал в шторм в «{zone_name}»: качка выматывает всех на "
                               f"палубе, корабль идёт медленнее", EV_STORM, out, players,
                     zone_id=int(storm.zone_id), storm_ends_at=storm.ends_at.isoformat())
        out.events.append(EV_STORM)
        if rng.random() * 100 < float(params.storm_drift_pct or 0):
            stop = _drift(db, ship, params, rng, now, out, players)
    if sea_raid_crud.has_active_raid(db, ship.id):
        return stop
    pick = sea_raid_crud.roll_monster(db, _i(ship.current_zone_id), params, rng)
    if pick is None:
        return stop
    eligible = sea_raid_crud.eligible_players(db, players)
    if not eligible:
        delay = sea_core.clamp(params.raid_repelled_delay_minutes, sea_core.RAID_REPELLED_DELAY_MINUTES_RANGE)
        ship.next_zone_at = ship.next_zone_at + timedelta(minutes=delay)
        _deck_notice(db, ship, sea_raid_crud.MSG_REPELLED.format(ship=ship.name, monster=pick.name),
                     EV_RAID_REPELLED, out, players)
        out.events.append(EV_RAID_REPELLED)
        logger.info("sea ship %s: «%s» attacked in zone %s, nobody could fight — repelled (+%s min)", ship.id,
                    pick.name, ship.current_zone_id, delay)
        return stop
    rows = sea_raid_crud.plan_raid(db, ship, pick, eligible, now)
    if not rows:
        return stop
    hold = sea_core.clamp(params.raid_hold_max_minutes, sea_core.RAID_HOLD_MAX_MINUTES_RANGE)
    if hold > 0:
        ship.hold_until = now + timedelta(minutes=hold)
        ship.next_zone_at = ship.next_zone_at + timedelta(minutes=hold)
    out.raids_planned = True
    _deck_notice(db, ship, sea_raid_crud.MSG_RAID.format(ship=ship.name, monster=pick.name), EV_RAID, out, players)
    out.events.append(EV_RAID)
    logger.info("sea ship %s: «%s» attacks in zone %s — %d battle group(s) for %s", ship.id, pick.name,
                ship.current_zone_id, len(rows), eligible)
    return True


def _drift(db: Session, ship: "models.SeaShip", params: "sea_crud.SeaParams", rng, now: datetime,
           out: ShipOutcome, players: Sequence["models.Character"]) -> bool:
    """The storm blows the ship into a neighbour zone (not the next one on the path); the course is re-laid from
    there to the same port zone (the zone timer is unchanged). False when there is no neighbour / no path."""
    path = ship.leg_path if isinstance(ship.leg_path, list) else []
    if not path:
        return False
    pos = _i(ship.leg_pos)
    graph = sea_crud.zone_graph(db)
    nxt = int(path[pos + 1]) if pos + 1 < len(path) else None
    drift_zone = sea_core.pick_drift(graph.adj, _i(ship.current_zone_id), nxt, rng)
    if drift_zone is None:
        return False
    new_path, _problem, _used = sea_core.leg_path(graph.adj, graph.zone_ids, drift_zone, int(path[-1]), None,
                                                  params.path_max_zones)
    if new_path is None:
        return False
    old_zone = ship.current_zone_id
    ship.leg_path = [int(z) for z in new_path]
    ship.leg_pos = 0
    ship.current_zone_id = int(drift_zone)
    ship.updated_at = now
    zone_name = _name(sea_crud.location_infos(db, [drift_zone]), drift_zone)
    _deck_notice(db, ship, f"Шторм снёс корабль «{ship.name}» с курса — в «{zone_name}». Капитан прокладывает "
                           f"путь заново", EV_DRIFT, out, players, zone_id=int(drift_zone))
    out.events.append(EV_DRIFT)
    logger.info("sea ship %s: drifted %s -> %s, new path %s", ship.id, old_zone, drift_zone, new_path)
    return True


def step(db: Session, ship: "models.SeaShip", now: datetime, out: ShipOutcome) -> None:
    """Zone stepping of a sailing ship with offline catch-up (bounded by the path length), then the arrival.
    FEAT-214: a stormy zone takes ``storm_extra`` minutes longer; only the effective entry (the ship really is in that
    zone now) applies the storm damage, the drift and the monster roll — a drift or an attack ends the loop."""
    path = ship.leg_path if isinstance(ship.leg_path, list) else []
    zone_minutes = max(1, _i(ship.zone_minutes))
    guard = len(path) + 2
    params: Optional[sea_crud.SeaParams] = None
    weather = sea_weather.weather_available(db)
    while ship.status == sea_core.STATUS_SAILING and ship.next_zone_at is not None and ship.next_zone_at <= now \
            and guard > 0:
        guard -= 1
        pos = _i(ship.leg_pos) + 1
        if pos < len(path):
            ship.leg_pos = pos
            ship.current_zone_id = int(path[pos])
            ship.updated_at = now
            storm = sea_weather.storm_at(db, ship.current_zone_id, now) if weather else None
            extra = 0
            if storm is not None:
                params = params or sea_crud.load_params(db)
                extra = sea_core.storm_extra(zone_minutes, params.storm_slow_mult)
            ship.next_zone_at = ship.next_zone_at + timedelta(minutes=zone_minutes + extra)
            ship.storm_extra_minutes = extra
            ship.storm_post_floor_id = sea_crud.max_post_id(db) if extra > 0 else None
            out.events.append("zone")
            if weather and ship.next_zone_at > now:     # the effective entry (pos >= 1: never at the pier)
                params = params or sea_crud.load_params(db)
                if _zone_effects(db, ship, storm, params, now, out):
                    break
            continue
        arrive(db, ship, now, out)
        return
    if ship.status == sea_core.STATUS_SAILING and ship.next_zone_at is None:
        arrive(db, ship, now, out)                     # broken state: no timer at sea → finish the leg


# =====================================================================================================================
# one ship
# =====================================================================================================================

def _free_players(db: Session, deck_id: int) -> int:
    """Players standing on the deck id who are not in an active battle."""
    ids = [int(r[0]) for r in db.query(models.Character.id).filter(
        models.Character.current_location_id == int(deck_id), models.Character.is_npc.is_(False)).all()]
    return sum(1 for cid in ids if not in_battle(db, cid))


# =====================================================================================================================
# FEAT-214: departure postpone, raid hold, sailor relief (§3.6)
# =====================================================================================================================

def postpone_departure(db: Session, ship: "models.SeaShip", now: datetime, out: ShipOutcome) -> bool:
    """A storm over the port's zone postpones a due departure by ``storm_postpone_minutes`` (tickets keep their trip),
    at most ``storm_postpone_max_minutes`` in total; the deck is told once. True = postponed (no departure now)."""
    if not sea_weather.weather_available(db):
        return False
    params = sea_crud.load_params(db)
    cap = sea_core.clamp(params.storm_postpone_max_minutes, sea_core.STORM_POSTPONE_MAX_MINUTES_RANGE)
    port = sea_crud.location_infos(db, [ship.docked_port_id]).get(_i(ship.docked_port_id))
    storm = sea_weather.storm_at(db, port.port_zone_id if port is not None else None, now)
    since = ship.storm_hold_since
    if storm is None or cap <= 0 or (since is not None and now - since >= timedelta(minutes=cap)):
        if storm is not None and since is not None:
            logger.info("sea ship %s: storm postpone cap reached — sails anyway", ship.id)
        return False
    step_minutes = sea_core.clamp(params.storm_postpone_minutes, sea_core.STORM_POSTPONE_MINUTES_RANGE)
    ship.departs_at = now + timedelta(minutes=step_minutes)
    ship.updated_at = now
    if since is None:
        ship.storm_hold_since = now
        _deck_notice(db, ship, f"Капитан корабля «{ship.name}» откладывает отплытие: в море шторм. Билеты "
                               f"остаются в силе", EV_STORM_DELAY, out)
        logger.info("sea ship %s: departure postponed by storm %s", ship.id, storm.storm_id)
    out.events.append(EV_STORM_DELAY)
    return True


def release_hold(db: Session, ship: "models.SeaShip", now: datetime, out: ShipOutcome) -> None:
    """The raid hold (§3.6.4): no active raid left → the unused hold is given back (``next_zone_at`` earlier); the
    hold ran out while raids still fight → the ship sails on, the battles go on aboard."""
    try:
        active = sea_raid_crud.has_active_raid(db, ship.id)
    except DBAPIError:
        active = False
    if not active:
        if ship.next_zone_at is not None:
            shift = max(timedelta(0), ship.hold_until - now)
            ship.next_zone_at = ship.next_zone_at - shift
        ship.hold_until = None
        ship.updated_at = now
        out.events.append(EV_HOLD_RELEASED)
        return
    if ship.hold_until <= now:
        ship.hold_until = None
        ship.updated_at = now
        _deck_notice(db, ship, f"Корабль «{ship.name}» идёт дальше — бой на палубе продолжается", EV_HOLD_EXPIRED,
                     out)
        out.events.append(EV_HOLD_EXPIRED)


def sailor_relief(db: Session, ship: "models.SeaShip", now: datetime, out: ShipOutcome) -> None:
    """Sailors «hold the sails» (§3.6.3): an aboard sailor of this trip with a deck post written after the stormy
    entry (plain length ≥ ``sailor_post_min_chars``) wins back ``storm_sailor_relief_pct`` of the storm delay. Once per
    zone."""
    extra = _i(ship.storm_extra_minutes)
    if extra <= 0:
        ship.storm_post_floor_id = None
        return
    params = sea_crud.load_params(db)
    deck = int(ship.deck_location_id)
    aboard = {int(ch.id) for ch in sea_crud.deck_players(db, ship, lock=False)}
    worked = False
    for p in sea_crud.active_passes(db, ship.id, lock=False):
        if p.kind != sea_core.KIND_SAILOR or int(p.character_id) not in aboard \
                or not sea_core.covers(p.first_trip, p.last_trip, _i(ship.trip_no)):
            continue
        if sailor_worked(db, int(p.character_id), deck, ship.storm_post_floor_id, params.sailor_post_min_chars):
            worked = True
            break
    if not worked:
        return
    minutes = sea_core.relief(extra, params.storm_sailor_relief_pct)
    ship.storm_post_floor_id = None
    if minutes <= 0 or ship.next_zone_at is None:
        return
    ship.next_zone_at = max(now, ship.next_zone_at - timedelta(minutes=minutes))
    ship.updated_at = now
    _deck_notice(db, ship, f"Матросы удержали паруса — корабль «{ship.name}» идёт быстрее", EV_STORM_RELIEF, out)
    out.events.append(EV_STORM_RELIEF)
    logger.info("sea ship %s: sailors won back %s min of the storm delay", ship.id, minutes)


def process_ship(db: Session, ship_id: int, now: datetime) -> Optional[ShipOutcome]:
    """One ship in the caller's transaction (no commit). None = the ship is gone."""
    ship = sea_crud.get_ship(db, ship_id, lock=True)
    if ship is None:
        return None
    out = ShipOutcome(int(ship.id), deck_location_id=int(ship.deck_location_id), now=now)
    deck_ok = int(ship.deck_location_id) in sea_crud.location_infos(db, [ship.deck_location_id])
    if not deck_ok:
        on_old_deck = _free_players(db, int(ship.deck_location_id))
        if ship.is_active or on_old_deck or ship.blocked_reason != sea_core.BLOCKED_NO_DECK:
            result = sea_crud.safe_land(db, ship, sea_core.BLOCKED_NO_DECK, now)
            _collect_landing(db, result, out)
            out.events.append(EV_SAFE_LANDING)
            logger.warning("sea ship %s: deck %s is gone — safe landing of %d players, ship off", ship.id,
                           ship.deck_location_id, len(result.ashore))
    elif not ship.is_active and ship.blocked_reason and ship.status == sea_core.STATUS_DOCKED \
            and not ship.docked_port_id and _free_players(db, int(ship.deck_location_id)):
        # FEAT-214 §3.9: players a battle kept aboard a broken ship (no port to step off to) — land them now
        result = sea_crud.safe_land(db, ship, ship.blocked_reason, now)
        _collect_landing(db, result, out)
        out.events.append(EV_SAFE_LANDING)
        logger.warning("sea ship %s: %d players kept aboard by a battle landed", ship.id, len(result.ashore))
    if ship.status == sea_core.STATUS_SAILING and ship.hold_until is not None:
        release_hold(db, ship, now, out)
    if ship.status == sea_core.STATUS_DOCKED and ship.is_active and deck_ok and ship.departs_at is not None \
            and ship.departs_at <= now:
        if not postpone_departure(db, ship, now, out):
            depart(db, ship, now, out)
    elif ship.status == sea_core.STATUS_SAILING and (ship.next_zone_at is None or ship.next_zone_at <= now) \
            and not (ship.hold_until is not None and ship.hold_until > now):
        step(db, ship, now, out)
    if ship.status == sea_core.STATUS_SAILING and ship.storm_post_floor_id is not None:
        sailor_relief(db, ship, now, out)
    if place_captain(db, ship, "placement"):
        out.events.append("captain_moved")
    return out


def after_commit(db: Session, out: Optional[ShipOutcome]) -> None:
    """Best effort after the commit: LS cleanup of the deck for everyone put ashore (gathering cancel first), the law
    encounter / slip / wanted notices and the sea notices. Never raises."""
    if out is None:
        return
    import law_crud
    import locations_client
    notices: List[law_notify.Notice] = []
    for a in out.ashore:
        cid = int(a.character_id)
        if cid in out.gathering_ids:
            try:
                asyncio.run(locations_client.cancel_gathering(cid, reason=GATHER_CANCEL_REASON))
            except Exception:
                logger.warning("sea: gathering cancel of character %s failed", cid, exc_info=True)
        if out.deck_location_id:
            locations_client.notify_character_left_location_sync(cid, int(out.deck_location_id))
        try:
            if a.encounter is not None:
                notices.append(law_crud.encounter_notice(db, a.encounter))
            elif a.slipped:
                notices.append(law_crud.slip_notice(db, cid, int(a.location_id)))
        except Exception:
            db.rollback()
            logger.exception("sea: law notice of character %s failed", cid)
    db.rollback()
    notices.extend(law_notify.wanted_notices(out.wanted_changes))
    notices.extend(out.notices)
    law_notify.publish(notices)
    if out.storm_damage_ids:                       # FEAT-214 §3.7: CAS, after the ship commit
        try:
            sea_weather.apply_storm_damage(out.storm_damage_ids, out.storm_hp_pct, out.storm_stamina_pct)
        except Exception:
            logger.warning("sea ship %s: storm damage failed", out.ship_id, exc_info=True)
    if out.raids_planned:                          # FEAT-214 §3.8: spawn + battle-service, after the ship commit
        try:
            sea_raid_crud.start_pending(db, out.ship_id, out.now)
        except Exception:
            db.rollback()
            logger.exception("sea ship %s: raid start failed (the pass retries)", out.ship_id)


def _ship_ids(db: Session) -> List[int]:
    rows = db.execute(text("SELECT id FROM sea_ships ORDER BY id")).fetchall()
    db.rollback()
    return [int(r[0]) for r in rows]


def run_pass(factory: Callable[[], Session], now: Optional[datetime] = None, *, force: bool = False) -> Optional[dict]:
    """One pass over every ship (None = throttled / no sea tables)."""
    now = now or sea_crud.now_utc()
    db = factory()
    try:
        if not sea_crud.sea_available(db):
            return None
        if not force and not claim_run(db, now):
            return None
        ids = _ship_ids(db)
    finally:
        db.close()
    weather = sea_weather.weather_step(factory, now)   # FEAT-214 §3.5: own transaction, never stops the ships
    stats: Dict[str, int] = {"ships": len(ids), "failed": 0, EV_DEPARTED: 0, EV_ARRIVED: 0, EV_REROUTED: 0,
                             EV_SAFE_LANDING: 0, "zone": 0, "ashore": 0, "captain_moved": 0}
    for ship_id in ids:
        db = factory()
        try:
            try:
                out = process_ship(db, ship_id, now)
                db.commit()
            except Exception:
                db.rollback()
                stats["failed"] += 1
                logger.exception("sea pass: ship %s not processed", ship_id)
                continue
            if out is None:
                continue
            for ev in out.events:
                stats[ev] = stats.get(ev, 0) + 1
            stats["ashore"] += len(out.ashore)
            try:
                after_commit(db, out)
            except Exception:
                logger.exception("sea pass: post-commit work of ship %s failed", ship_id)
        finally:
            db.close()
    for key, value in (weather or {}).items():
        stats[f"storm_{key}"] = value
    try:
        db = factory()
        try:
            raids = sea_weather.weather_available(db)
        finally:
            db.close()
        if raids:
            stats.update(sea_raid_crud.raid_followups(factory, now))
    except Exception:
        logger.exception("sea pass: raid follow-ups failed")
    return stats
