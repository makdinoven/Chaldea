"""FEAT-211 §3.3: the physical caravan pass of the character-service scheduler.

Called from ``econ_scheduler.run_scheduled_once`` after the faction pass and before the economy tick. Throttle: a
conditional UPDATE claim on ``econ_sim_settings.caravan_pass_last_run_at`` (>= :data:`RUN_INTERVAL_SECONDS`), so
several processes never double-run. Skipped while the economy tick is switched off in the DB (economy frozen →
caravans frozen) or before migration 035. Every step is best effort, every caravan its own short transaction:

1. ``_stale_raids``     — raids stuck in ``starting`` (no battle) → guards despawned, raid row deleted;
2. ``_raid_battles``    — ``fighting`` raids: poll the battle result (lost callbacks), expire overlong battles;
3. ``_raid_followups``  — won raids: law step, bale deliveries, guard despawn;
   (steps 1–3 are the raid stage — ``caravan_raid_crud`` (FEAT-211 task 3) provides them; until it exists they are
   no-ops);
4. ``_step_caravans``   — due physical caravans move one location along their route unless held (3.4);
5. ``_deliver_arrived`` — arrived caravans are delivered / cancelled (``economy_caravan_crud.deliver_physical``);
   skipped entirely while an economy run is ``running`` (a region never changes in the middle of a resumable run);
   FEAT-212: escorts are paid / cancelled inside that op, their notices published after the commit;
6. ``_escort_rewards``  — FEAT-212: reputation / fame / faction points of delivered escorts
   (``caravan_escort_crud.escort_rewards``, own transaction per escort);
7. ``_escort_housekeeping`` — FEAT-212: stale escort rows / dangling columns, old caravan-channel messages.

The step transaction locks ``econ_caravans(row)`` and, after it moved, its active escort rows and their characters
(FEAT-212 3.15: caravan → escorts → characters; escorts ride with the caravan). Never started under pytest by the
scheduler; tests call :func:`run_pass` directly (``now=`` / ``force=`` / ``rng=``).
"""

import logging
import random
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

import caravan_escort_crud as escort_crud
import econ_tick
import economy_caravan_crud as caravan_crud
import law_notify

logger = logging.getLogger("character-service.caravan_pass")

RUN_INTERVAL_SECONDS = 55
BATCH_SIZE = 200

# names of the raid-stage functions (``caravan_raid_crud``, FEAT-211 task 3): fn(factory, now, params) -> int
RAID_STEP_STALE = "expire_stale_raids"
RAID_STEP_BATTLES = "poll_raid_battles"
RAID_STEP_FOLLOWUPS = "raid_followups"


def now_utc() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def claim_run(db: Session, now: datetime) -> bool:
    """Conditional claim (commits). False when another run is recent or there is no settings row."""
    cutoff = now - timedelta(seconds=RUN_INTERVAL_SECONDS)
    result = db.execute(text(
        "UPDATE econ_sim_settings SET caravan_pass_last_run_at = :now WHERE id = 1 "
        "AND (caravan_pass_last_run_at IS NULL OR caravan_pass_last_run_at <= :cutoff)"),
        {"now": now, "cutoff": cutoff})
    db.commit()
    return (result.rowcount or 0) == 1


# --------------------------------------------------------------------------------------------- steps 1-3 (raids)

def _raid_step(name: str, factory: Callable[[], Session], now: datetime, params) -> int:
    """Run one raid-stage step of ``caravan_raid_crud`` when that module provides it (task 3); else 0."""
    try:
        import caravan_raid_crud  # noqa: F401  (FEAT-211 task 3)
    except ImportError:
        return 0
    fn = getattr(caravan_raid_crud, name, None)
    if fn is None:
        return 0
    return int(fn(factory, now, params) or 0)


def _stale_raids(factory: Callable[[], Session], now: datetime, params) -> int:
    return _raid_step(RAID_STEP_STALE, factory, now, params)


def _raid_battles(factory: Callable[[], Session], now: datetime, params) -> int:
    return _raid_step(RAID_STEP_BATTLES, factory, now, params)


def _raid_followups(factory: Callable[[], Session], now: datetime, params) -> int:
    return _raid_step(RAID_STEP_FOLLOWUPS, factory, now, params)


# --------------------------------------------------------------------------------------------- step 4 (moving)

def _due_ids(db: Session, now: datetime, after_id: int) -> List[int]:
    rows = db.execute(text(
        "SELECT id FROM econ_caravans WHERE is_physical = 1 AND status = :s AND arrived_at IS NULL "
        "AND next_move_at IS NOT NULL AND next_move_at <= :now AND id > :after ORDER BY id LIMIT :n"),
        {"s": caravan_crud.STATUS_IN_TRANSIT, "now": now, "after": int(after_id), "n": BATCH_SIZE}).fetchall()
    db.rollback()
    return [int(r[0]) for r in rows]


def step_caravan(db: Session, caravan_id: int, now: datetime, params, u: float,
                 gates_available: bool = True) -> Optional[str]:
    """One caravan (caller commits). Returns ``held`` | ``moved`` | ``arrived`` | None (not due / gone)."""
    row = caravan_crud._lock_caravan(db, caravan_id)
    if (row is None or not row.is_physical or row.status != caravan_crud.STATUS_IN_TRANSIT
            or row.arrived_at is not None or row.next_move_at is None or row.next_move_at > now):
        return None
    route = [int(x) for x in caravan_crud._json_list(row.route)]
    if caravan_crud.held_by(db, row, now, params, gates_available) is not None:
        if row.hold_started_at is None:
            row.hold_started_at = now
        return "held"
    index = int(row.route_index or 0)
    if len(route) < 2 or index >= len(route) - 1:
        row.route_index = max(0, len(route) - 1)
        row.arrived_at = now
        row.next_move_at = None
        return "arrived"
    index += 1
    row.route_index = index
    row.current_location_id = route[index]
    escort_crud.move_escorts(db, row)          # FEAT-212: escorts ride inside the wagon
    if index == len(route) - 1:
        row.arrived_at = now
        row.next_move_at = None
        return "arrived"
    row.next_move_at = now + caravan_crud.step_delay(params, u)
    return "moved"


def _step_caravans(factory: Callable[[], Session], now: datetime, params, rng: Callable[[], float],
                   stats: Dict[str, int]) -> None:
    db = factory()
    try:
        try:
            gates_available = caravan_crud.gate_tables_available(db)
        except Exception:
            gates_available = False
        last = 0
        while True:
            ids = _due_ids(db, now, last)
            if not ids:
                return
            for caravan_id in ids:
                last = caravan_id
                try:
                    outcome = step_caravan(db, caravan_id, now, params, rng(), gates_available)
                    db.commit()
                except Exception:
                    db.rollback()
                    stats["failed"] += 1
                    logger.exception("caravan pass: caravan %s not stepped", caravan_id)
                    continue
                if outcome:
                    stats[outcome] += 1
            if len(ids) < BATCH_SIZE:
                return
    finally:
        db.close()


# --------------------------------------------------------------------------------------------- step 5 (delivery)

def _economy_run_in_progress(db: Session) -> bool:
    try:
        return db.execute(text("SELECT 1 FROM econ_tick_runs WHERE status = 'running' LIMIT 1")).first() is not None
    finally:
        db.rollback()


def _arrived_ids(db: Session, after_id: int) -> List[int]:
    rows = db.execute(text(
        "SELECT id FROM econ_caravans WHERE is_physical = 1 AND status = :s AND arrived_at IS NOT NULL "
        "AND id > :after ORDER BY id LIMIT :n"),
        {"s": caravan_crud.STATUS_IN_TRANSIT, "after": int(after_id), "n": BATCH_SIZE}).fetchall()
    db.rollback()
    return [int(r[0]) for r in rows]


def _deliver_arrived(factory: Callable[[], Session], now: datetime, stats: Dict[str, int]) -> None:
    db = factory()
    try:
        if _economy_run_in_progress(db):
            stats["delivery_postponed"] = 1
            return
        last = 0
        while True:
            ids = _arrived_ids(db, last)
            if not ids:
                return
            for caravan_id in ids:
                last = caravan_id
                try:
                    result = caravan_crud.deliver_physical_tx(factory, caravan_id, now)
                except Exception:
                    stats["failed"] += 1
                    logger.exception("caravan pass: caravan %s not delivered, retried next pass", caravan_id)
                    continue
                if result.status in (caravan_crud.STATUS_DELIVERED, caravan_crud.STATUS_CANCELLED):
                    stats[result.status] += 1
                    if result.notices:
                        law_notify.publish(result.notices)
            if len(ids) < BATCH_SIZE:
                return
    finally:
        db.close()


# --------------------------------------------------------------------------------------------- the pass

def run_pass(factory: Callable[[], Session], now: Optional[datetime] = None, *, force: bool = False,
             rng: Callable[[], float] = random.random) -> Optional[dict]:
    """One pass (None = throttled / economy switched off / caravans unavailable / no settings row)."""
    now = now or now_utc()
    db = factory()
    try:
        if not caravan_crud.caravans_available(db) or not econ_tick.is_tick_enabled(db):
            return None
        params = econ_tick.load_params(db)
        db.rollback()
        if not force and not claim_run(db, now):
            return None
    finally:
        db.close()
    stats = {"stale_raids": 0, "raid_battles": 0, "raid_followups": 0, "held": 0, "moved": 0, "arrived": 0,
             "delivered": 0, "cancelled": 0, "escort_rewards": 0, "escort_housekeeping": 0, "failed": 0}
    for key, step in (("stale_raids", _stale_raids), ("raid_battles", _raid_battles),
                      ("raid_followups", _raid_followups)):
        try:
            stats[key] = step(factory, now, params)
        except Exception:
            stats["failed"] += 1
            logger.exception("caravan pass: raid step %s failed", key)
    try:
        _step_caravans(factory, now, params, rng, stats)
    except Exception:
        stats["failed"] += 1
        logger.exception("caravan pass: stepping failed")
    try:
        _deliver_arrived(factory, now, stats)
    except Exception:
        stats["failed"] += 1
        logger.exception("caravan pass: deliveries failed")
    for key, step in (("escort_rewards", lambda: escort_crud.escort_rewards(factory, now, params)),
                      ("escort_housekeeping", lambda: escort_crud.escort_housekeeping(factory, now))):
        try:
            stats[key] = int(step() or 0)
        except Exception:
            stats["failed"] += 1
            logger.exception("caravan pass: %s failed", key)
    return stats
