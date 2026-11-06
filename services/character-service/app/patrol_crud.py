"""FEAT-204 guard patrols — DB layer (sync SQLAlchemy). Pure maths: ``patrol_core``.

* config reads / writes for the admin API (:func:`patrol_out`, :func:`save_patrol`) — caller's transaction, no commit;
* :func:`step_guard` — ONE patrol step of one guard; a flow that COMMITS (like the law-pass items):
    Txn A   patrol row FOR UPDATE → guard row FOR UPDATE → blocked? (retry in 2 min) → target → move → COMMIT;
    Txn B_i for each player in the new location (≤ :data:`PATROL_SWEEP_LIMIT`): player row FOR UPDATE →
            ``law_crud.check_patrol_arrival`` → COMMIT → «Вас заметил патруль стражи…» published after the commit.
  A sweep failure never undoes the move; one player's failure never stops the others.
* :func:`departure_hints` — the 3-value bucket of the public NPC list.

Lock order: ``guard_patrols`` row → the guard's ``characters`` row; the players are locked in their own transactions
afterwards (never together with the guard), so no cycle with a moving player (who locks only his own row).
Foreign tables (``Locations``, ``Districts``, ``LocationNeighbors``) are read by raw SQL.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

import law_core as lc
import law_crud
import law_facility
import law_notify
import models
import patrol_core as pc
import reputation_core as rc
import reputation_crud

logger = logging.getLogger("character-service.patrol")

PATROL_SWEEP_LIMIT = 200

MSG_NPC_NOT_FOUND = "NPC не найден"
MSG_ONLY_GUARDS = "Патруль доступен только стражникам"
MSG_UNKNOWN_LOCATION = "Локация не найдена: {ids}"
MSG_UNKNOWN_DISTRICT = "Район не найден"
MSG_SMALL_DISTRICT = "В районе должно быть хотя бы 2 локации"

# step outcomes
OUT_MOVED = "moved"
OUT_STAYED = "stayed"
OUT_BLOCKED = "blocked"
OUT_NOT_PATROLLING = "not_patrolling"
OUT_NOT_DUE = "not_due"


def patrol_rng():
    """THE seam of the patrol randomness (zone pick + interval jitter); tests patch it. Defaults to the law RNG."""
    return law_crud.rng()


def _pick(values: Sequence[int]) -> int:
    values = list(values)
    index = int(patrol_rng().random() * len(values))
    return values[min(max(index, 0), len(values) - 1)]


def _delay(patrol: "models.GuardPatrol"):
    return pc.next_delay(int(patrol.interval_min or pc.DEFAULT_INTERVAL_MIN), int(patrol.jitter_pct or 0),
                         patrol_rng().random())


# =====================================================================================================================
# readers
# =====================================================================================================================

def get_patrol(db: Session, npc_id: int, *, lock: bool = False) -> Optional["models.GuardPatrol"]:
    query = db.query(models.GuardPatrol).filter(models.GuardPatrol.npc_id == int(npc_id))
    if lock and law_crud._for_update(db):
        query = query.with_for_update()
    return query.populate_existing().first()


def points_of(db: Session, npc_id: int, kind: str) -> List[int]:
    rows = db.execute(text("SELECT location_id FROM guard_patrol_points WHERE npc_id = :n AND kind = :k "
                           "ORDER BY position"), {"n": int(npc_id), "k": kind}).fetchall()
    return [int(r[0]) for r in rows]


def existing_locations(db: Session, location_ids: Iterable[int]) -> set:
    ids = sorted({int(x) for x in location_ids if x})
    if not ids:
        return set()
    ph, params = law_crud._in("l", ids)
    rows = db.execute(text(f"SELECT id FROM Locations WHERE id IN ({ph})"), params).fetchall()
    return {int(r[0]) for r in rows}


def neighbours_of(db: Session, location_id: Optional[int]) -> List[int]:
    """``LocationNeighbors`` is stored in both directions, so one side is enough."""
    if not location_id:
        return []
    rows = db.execute(text("SELECT neighbor_id FROM LocationNeighbors WHERE location_id = :l"),
                      {"l": int(location_id)}).fetchall()
    return sorted({int(r[0]) for r in rows})


def district_name(db: Session, district_id: Optional[int]) -> Optional[str]:
    if not district_id:
        return None
    row = db.execute(text("SELECT name FROM Districts WHERE id = :d"), {"d": int(district_id)}).first()
    return row[0] if row is not None else None


def zone_locations(db: Session, patrol: "models.GuardPatrol") -> List[int]:
    """The live zone: the district subtree or the stored list, without deleted locations."""
    if patrol.zone_kind == pc.ZONE_DISTRICT:
        ids = law_facility.prison_location_ids(db, patrol.zone_district_id)
    else:
        ids = points_of(db, patrol.npc_id, pc.KIND_ZONE)
    alive = existing_locations(db, ids)
    return [x for x in ids if x in alive]


def route_locations(db: Session, patrol: "models.GuardPatrol") -> List[int]:
    ids = points_of(db, patrol.npc_id, pc.KIND_ROUTE)
    alive = existing_locations(db, ids)
    return [x for x in ids if x in alive]


def blocked_reason(db: Session, guard: Optional["models.Character"], now: datetime,
                   settings: Optional[lc.LawSettings] = None) -> Optional[str]:
    """Why the guard cannot step now (None = free). The same checks as the step."""
    if guard is None or not bool(guard.is_npc) or guard.npc_role != lc.GUARD_ROLE:
        return pc.BLOCK_NOT_GUARD
    if guard.npc_status == "dead":
        return pc.BLOCK_DEAD
    ko_until = law_crud._dt(guard.unconscious_until)
    if ko_until is not None and ko_until > now:
        return pc.BLOCK_KO
    if law_crud.in_active_battle(db, guard.id):
        return pc.BLOCK_BATTLE
    if law_crud.guard_held(db, guard.id, now, settings):
        return pc.BLOCK_ENCOUNTER
    return None


# =====================================================================================================================
# the step
# =====================================================================================================================

@dataclass
class StepOutcome:
    outcome: str
    blocked_reason: Optional[str] = None
    from_location_id: Optional[int] = None
    to_location_id: Optional[int] = None
    checked: int = 0
    encounters: int = 0
    slipped: int = 0


def _override_target(db: Session, patrol: "models.GuardPatrol", now: datetime) -> Optional[int]:
    """The pursuit seam (FEAT-204 P6, «погоня» — not implemented): a future feature returns a forced target here
    (e.g. the location a character fled to) and the rest of the step is reused unchanged. Always None now."""
    return None


def _route_target(db: Session, patrol: "models.GuardPatrol", current: Optional[int]):
    points = route_locations(db, patrol)
    if len(points) < pc.MIN_POINTS:
        logger.warning("patrol: guard %s has fewer than 2 live route points — no move", patrol.npc_id)
        return None, {}
    target, index, direction = pc.route_step(points, int(patrol.route_index or 0), int(patrol.route_dir or 1),
                                             patrol.route_style, current)
    return target, {"route_index": index, "route_dir": direction}


def _zone_target(db: Session, patrol: "models.GuardPatrol", current: Optional[int]):
    zone = zone_locations(db, patrol)
    if len(zone) < pc.MIN_POINTS:
        logger.warning("patrol: the zone of guard %s has fewer than 2 locations — no move", patrol.npc_id)
        return None, {}
    target, jumped = pc.zone_step(current, zone, neighbours_of(db, current), patrol.last_location_id, _pick)
    if jumped:
        logger.info("patrol: guard %s jumped inside its zone %s -> %s (no passage)", patrol.npc_id, current, target)
    return target, {}


_SQL_PRESENT = "SELECT c.id FROM characters c WHERE c.is_npc = 0 AND c.current_location_id = :l"
# Only a player wanted in the region (stored value > 0) or with a negative reputation there can be stopped:
# both decay towards zero, so the stored row is a superset of the effective one.
_SQL_SUSPECTS = (
    " AND (EXISTS (SELECT 1 FROM character_wanted w WHERE w.character_id = c.id AND w.region_id = :r AND w.value > 0)"
    " OR EXISTS (SELECT 1 FROM character_reputation p WHERE p.character_id = c.id AND p.region_id = :r"
    " AND p.value < 0)"
    # FEAT-207 §3.7: an active member of a faction outlawed in the region (even with zero wanted)
    " OR EXISTS (SELECT 1 FROM faction_members m JOIN faction_outlaw_regions o ON o.faction_id = m.faction_id"
    " WHERE m.character_id = c.id AND m.status = 'active' AND o.region_id = :r))")


def _sweep_candidates(db: Session, location_id: int) -> List[int]:
    """Present players worth the full (locking) arrival check. Prefilters out everyone who cannot be stopped,
    instead of locking and re-reading every player in a busy hub."""
    region_id = reputation_crud.location_region(db, location_id)
    if not region_id:
        return []                               # no region = no law here (law_crud._check exits the same way)
    params = {"l": int(location_id), "r": int(region_id), "n": PATROL_SWEEP_LIMIT}
    sql = _SQL_PRESENT
    # A neutral standing (no reputation row) is never «outlaw» unless an admin moved the tiers so; then no prefilter.
    if rc.tier_for(0, reputation_crud.load_tiers(db)).code != rc.OUTLAW_TIER:
        sql += _SQL_SUSPECTS
    return [int(r[0]) for r in db.execute(text(sql + " ORDER BY c.id LIMIT :n"), params).fetchall()]


def _sweep(db: Session, npc_id: int, location_id: int, now: datetime, outcome: StepOutcome) -> None:
    """Txn B_i: every present player gets the arrival check in his own transaction (offline players included)."""
    ids = _sweep_candidates(db, location_id)
    db.rollback()
    for character_id in ids:
        try:
            character = law_crud.lock_character(db, character_id)
            result = law_crud.check_patrol_arrival(db, character, location_id, guard_id=npc_id, now=now)
            notice = law_crud.encounter_notice(db, result.encounter) if result.encounter is not None else None
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("patrol: arrival check of character %s by guard %s failed", character_id, npc_id)
            continue
        outcome.checked += 1
        if result.encounter is not None:
            outcome.encounters += 1
            law_notify.publish([notice])
        elif result.slipped:
            outcome.slipped += 1               # PM: a slip past a patrol is silent (law_log row only)


def step_guard(db: Session, npc_id: int, now: Optional[datetime] = None, *, force: bool = False) -> StepOutcome:
    """One patrol step (COMMITS). Idempotent: not due (``next_move_at > now``) → nothing, so a second runner or a
    replay after «Шаг сейчас» does nothing. ``force`` ignores the schedule, never a block."""
    now = now or law_crud.now_utc()
    patrol = get_patrol(db, npc_id, lock=True)
    if patrol is None or patrol.mode not in pc.MOVING_MODES:
        db.rollback()
        return StepOutcome(OUT_NOT_PATROLLING)
    due_at = law_crud._dt(patrol.next_move_at)
    if not force and (due_at is None or due_at > now):
        db.rollback()
        return StepOutcome(OUT_NOT_DUE)
    guard = law_crud.lock_character(db, npc_id)
    if guard is None:                           # an orphan (the NPC row is gone): drop the config
        db.execute(text("DELETE FROM guard_patrol_points WHERE npc_id = :n"), {"n": int(npc_id)})
        db.delete(patrol)
        db.commit()
        logger.warning("patrol: guard %s no longer exists — its patrol was removed", npc_id)
        return StepOutcome(OUT_NOT_PATROLLING)
    current = int(guard.current_location_id) if guard.current_location_id else None
    reason = blocked_reason(db, guard, now)
    if reason is not None:
        patrol.next_move_at = now + pc.BLOCKED_RETRY
        db.commit()
        return StepOutcome(OUT_BLOCKED, blocked_reason=reason, from_location_id=current)

    target = _override_target(db, patrol, now)
    updates: Dict[str, int] = {}
    if target is None:
        if patrol.mode == pc.MODE_ROUTE:
            target, updates = _route_target(db, patrol, current)
        else:
            target, updates = _zone_target(db, patrol, current)
    patrol.next_move_at = now + _delay(patrol)
    for name, value in updates.items():
        setattr(patrol, name, value)
    if target is None or target == current:
        db.commit()
        return StepOutcome(OUT_STAYED, from_location_id=current, to_location_id=current)

    guard.current_location_id = int(target)
    patrol.last_location_id = current
    patrol.last_moved_at = now
    db.commit()
    logger.info("patrol: guard %s moved %s -> %s", npc_id, current, target)
    outcome = StepOutcome(OUT_MOVED, from_location_id=current, to_location_id=int(target))
    try:
        _sweep(db, npc_id, int(target), now, outcome)
    except Exception:
        db.rollback()
        logger.exception("patrol: arrival sweep of guard %s at %s failed", npc_id, target)
    return outcome


def due_guards(db: Session, now: datetime, limit: int) -> List[int]:
    ph, params = law_crud._in("m", list(pc.MOVING_MODES))
    rows = db.execute(text(
        f"SELECT npc_id FROM guard_patrols WHERE mode IN ({ph}) AND next_move_at IS NOT NULL "
        "AND next_move_at <= :now ORDER BY next_move_at, npc_id LIMIT :n"),
        {**params, "now": now, "n": int(limit)}).fetchall()
    db.rollback()
    return [int(r[0]) for r in rows]


# =====================================================================================================================
# the public hint
# =====================================================================================================================

def departure_hints(db: Session, npc_ids: Iterable[int], now: Optional[datetime] = None,
                    settings: Optional[lc.LawSettings] = None) -> Dict[int, Optional[str]]:
    """``{npc_id: 'soon' | 'short' | 'long'}`` for the patrolling guards of ``npc_ids`` (others absent). Nothing when
    the global switch is off. Two queries whatever the number of guards."""
    ids = sorted({int(x) for x in npc_ids if x})
    if not ids:
        return {}
    settings = settings or law_crud.load_settings(db)
    if not settings.patrols_enabled:
        return {}
    now = now or law_crud.now_utc()
    ph, params = law_crud._in("g", ids)
    mph, mparams = law_crud._in("m", list(pc.MOVING_MODES))
    rows = db.execute(text(f"SELECT npc_id, next_move_at FROM guard_patrols WHERE npc_id IN ({ph}) "
                           f"AND mode IN ({mph})"), {**params, **mparams}).fetchall()
    if not rows:
        return {}
    held = law_crud.held_guards(db, [r[0] for r in rows], now, settings)
    return {int(r[0]): pc.departure_bucket(law_crud._dt(r[1]), now, int(r[0]) in held) for r in rows}


# =====================================================================================================================
# admin config
# =====================================================================================================================

def require_npc(db: Session, npc_id: int) -> "models.Character":
    npc = db.query(models.Character).filter(models.Character.id == int(npc_id)).first()
    if npc is None or not bool(npc.is_npc) or npc.npc_role == "mob":
        raise law_crud.LawError(404, MSG_NPC_NOT_FOUND)
    return npc


def _names(db: Session, ids: Iterable[int]) -> Dict[int, Optional[str]]:
    return law_crud.location_names(db, ids)


def _warnings(db: Session, mode: str, style: str, route: List[int], zone: List[int]) -> List[str]:
    """Soft (Russian) warnings of a config: non-adjacent route steps; a zone over several regions / without passages."""
    import reputation_crud
    out: List[str] = []
    if mode == pc.MODE_ROUTE and len(route) >= pc.MIN_POINTS:
        names = _names(db, route)
        pairs = list(zip(route, route[1:]))
        if style == pc.STYLE_LOOP and len(route) > 2:
            pairs.append((route[-1], route[0]))
        seen = set()
        for a, b in pairs:
            key = tuple(sorted((a, b)))
            if key in seen:
                continue
            seen.add(key)
            if b not in neighbours_of(db, a):
                out.append(f"«{names.get(a) or a}» и «{names.get(b) or b}» не соседние — "
                           "стражник перейдёт напрямую")
    if mode == pc.MODE_ZONE and len(zone) >= pc.MIN_POINTS:
        regions = {reputation_crud.location_region(db, x) for x in zone}
        regions.discard(None)
        if len(regions) > 1:
            out.append("Локации зоны находятся в разных регионах")
        zone_set = set(zone)
        if not any(set(neighbours_of(db, x)) & (zone_set - {x}) for x in zone):
            out.append("Между локациями зоны нет переходов — стражник будет перемещаться напрямую")
    return out


def patrol_out(db: Session, npc_id: int, now: Optional[datetime] = None) -> dict:
    """``PatrolOut``: the stored config (defaults without a row) + the live state."""
    now = now or law_crud.now_utc()
    npc = require_npc(db, npc_id)
    patrol = get_patrol(db, npc_id)
    settings = law_crud.load_settings(db)
    route = points_of(db, npc_id, pc.KIND_ROUTE)
    zone = points_of(db, npc_id, pc.KIND_ZONE)
    current = int(npc.current_location_id) if npc.current_location_id else None
    names = _names(db, list(route) + list(zone) + ([current] if current else []))
    mode = patrol.mode if patrol is not None else pc.MODE_POST
    style = patrol.route_style if patrol is not None else pc.STYLE_LOOP
    zone_kind = patrol.zone_kind if patrol is not None else pc.ZONE_DISTRICT
    district_id = int(patrol.zone_district_id) if patrol is not None and patrol.zone_district_id else None
    moving = mode in pc.MOVING_MODES
    if moving and zone_kind == pc.ZONE_DISTRICT and mode == pc.MODE_ZONE:
        warn_zone = zone_locations(db, patrol)
    else:
        warn_zone = zone
    return {
        "npc_id": int(npc.id),
        "npc_role": npc.npc_role,
        "mode": mode,
        "route_style": style,
        "route": [{"location_id": x, "name": names.get(x)} for x in route],
        "zone_kind": zone_kind,
        "zone_district_id": district_id,
        "zone_district_name": district_name(db, district_id),
        "zone_locations": [{"location_id": x, "name": names.get(x)} for x in zone],
        "interval_min": int(patrol.interval_min) if patrol is not None else pc.DEFAULT_INTERVAL_MIN,
        "jitter_pct": int(patrol.jitter_pct) if patrol is not None else pc.DEFAULT_JITTER_PCT,
        "current_location_id": current,
        "current_location_name": names.get(current) if current else None,
        "next_move_at": law_crud._dt(patrol.next_move_at) if patrol is not None and moving else None,
        "last_moved_at": law_crud._dt(patrol.last_moved_at) if patrol is not None else None,
        "blocked_reason": blocked_reason(db, npc, now, settings) if moving else None,
        "patrols_enabled": bool(settings.patrols_enabled),
        "warnings": _warnings(db, mode, style, route, warn_zone) if moving else [],
    }


def _replace_points(db: Session, npc_id: int, kind: str, ids: List[int]) -> None:
    db.execute(text("DELETE FROM guard_patrol_points WHERE npc_id = :n AND kind = :k"),
               {"n": int(npc_id), "k": kind})
    db.flush()
    for position, location_id in enumerate(ids):
        db.add(models.GuardPatrolPoint(npc_id=int(npc_id), kind=kind, position=position,
                                       location_id=int(location_id)))
    db.flush()


def save_patrol(db: Session, npc_id: int, body, *, user_id: Optional[int] = None,
                now: Optional[datetime] = None) -> dict:
    """Validate + store a patrol config (caller commits). An omitted list keeps the stored one."""
    now = now or law_crud.now_utc()
    npc = require_npc(db, npc_id)
    patrol = get_patrol(db, npc_id, lock=True)
    mode = body.mode
    style = body.route_style or (patrol.route_style if patrol is not None else pc.STYLE_LOOP)
    zone_kind = body.zone_kind or (patrol.zone_kind if patrol is not None else pc.ZONE_DISTRICT)
    stored_route = points_of(db, npc_id, pc.KIND_ROUTE)
    stored_zone = points_of(db, npc_id, pc.KIND_ZONE)
    route = [int(x) for x in body.route_location_ids] if body.route_location_ids is not None else stored_route
    zone = [int(x) for x in body.zone_location_ids] if body.zone_location_ids is not None else stored_zone
    district_id = body.zone_district_id if "zone_district_id" in body.__fields_set__ else (
        patrol.zone_district_id if patrol is not None else None)
    district_id = int(district_id) if district_id else None
    interval = int(body.interval_min) if body.interval_min is not None else (
        int(patrol.interval_min) if patrol is not None else pc.DEFAULT_INTERVAL_MIN)
    jitter = int(body.jitter_pct) if body.jitter_pct is not None else (
        int(patrol.jitter_pct) if patrol is not None else pc.DEFAULT_JITTER_PCT)

    if mode != pc.MODE_POST and npc.npc_role != lc.GUARD_ROLE:
        raise law_crud.LawError(400, MSG_ONLY_GUARDS)
    errors = pc.validate(mode, style, zone_kind, route, zone, district_id, interval, jitter)
    if errors:
        raise law_crud.LawError(400, "; ".join(errors))
    active = route if mode == pc.MODE_ROUTE else (zone if mode == pc.MODE_ZONE and
                                                  zone_kind == pc.ZONE_LOCATIONS else [])
    known = existing_locations(db, set(route) | set(zone))
    unknown = sorted({x for x in active if x not in known})
    if unknown:
        raise law_crud.LawError(400, MSG_UNKNOWN_LOCATION.format(ids=", ".join(str(x) for x in unknown)))
    # the inactive list keeps only existing locations (it is not validated strictly)
    route = [x for x in route if x in known]
    zone = [x for x in zone if x in known]
    if mode == pc.MODE_ZONE and zone_kind == pc.ZONE_DISTRICT:
        if db.execute(text("SELECT 1 FROM Districts WHERE id = :d"), {"d": district_id}).first() is None:
            raise law_crud.LawError(400, MSG_UNKNOWN_DISTRICT)
        subtree = existing_locations(db, law_facility.prison_location_ids(db, district_id))
        if len(subtree) < pc.MIN_POINTS:
            raise law_crud.LawError(400, MSG_SMALL_DISTRICT)

    created = patrol is None
    if created:
        patrol = models.GuardPatrol(npc_id=int(npc_id), updated_at=now)
        db.add(patrol)
    old = None if created else (patrol.mode, patrol.route_style, patrol.zone_kind,
                                int(patrol.zone_district_id) if patrol.zone_district_id else None,
                                int(patrol.interval_min), int(patrol.jitter_pct), stored_route, stored_zone)
    new = (mode, style, zone_kind, district_id, interval, jitter, route, zone)
    patrol.mode, patrol.route_style, patrol.zone_kind = mode, style, zone_kind
    patrol.zone_district_id = district_id
    patrol.interval_min, patrol.jitter_pct = interval, jitter
    patrol.updated_at = now
    patrol.updated_by_user_id = int(user_id) if user_id else None
    if route != stored_route:
        _replace_points(db, npc_id, pc.KIND_ROUTE, route)
    if zone != stored_zone:
        _replace_points(db, npc_id, pc.KIND_ZONE, zone)

    if mode == pc.MODE_POST:
        patrol.next_move_at = None
    elif old != new or patrol.next_move_at is None:
        patrol.next_move_at = now + _delay(patrol)
        current = int(npc.current_location_id) if npc.current_location_id else None
        patrol.route_index = route.index(current) if current in route else 0
        patrol.route_dir = 1
    db.flush()
    return patrol_out(db, npc_id, now)


def disable_patrol(db: Session, npc_id: int) -> None:
    """The NPC stopped being a guard: back to a post (the points are kept). Caller's transaction."""
    db.execute(text("UPDATE guard_patrols SET mode = :post, next_move_at = NULL WHERE npc_id = :n"),
               {"post": pc.MODE_POST, "n": int(npc_id)})


def delete_patrol(db: Session, npc_id: int) -> None:
    """The NPC is deleted: drop its config and points. Caller's transaction."""
    db.execute(text("DELETE FROM guard_patrol_points WHERE npc_id = :n"), {"n": int(npc_id)})
    db.execute(text("DELETE FROM guard_patrols WHERE npc_id = :n"), {"n": int(npc_id)})
