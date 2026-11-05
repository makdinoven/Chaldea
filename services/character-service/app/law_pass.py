"""FEAT-198 §3.7: the law pass of the character-service scheduler.

Called from ``econ_scheduler.run_scheduled_once`` BEFORE the economy ``tick_enabled`` switch (the law is not economy).
Throttle: a conditional UPDATE claim on ``law_settings.pass_last_run_at`` (>= :data:`RUN_INTERVAL_SECONDS`), so
several processes never double-run. Every item is its own transaction; an item failure is logged and skipped.
Steps:

1. expired encounters (``pending``, ``expires_at <= now``) -> auto-surrender / forced fine (``law_flows``);
2. lost callbacks (``fighting`` for more than :data:`FIGHT_POLL_AFTER`) -> poll battle-service, apply the result;
3. served terms (``serving``, ``until <= now``) -> ``served`` + «Срок заключения окончен» (the lock is already free);
4. guard recovery: KO ended -> full heal + ``unconscious_until`` cleared; any alive, idle guard below max HP -> heal;
5. FEAT-199 reveal rolls: unwitnessed / masked crimes whose ``next_roll_at <= now`` -> one roll each (chance grows with
   the region's suspicion, masked × factor) -> reveal (reputation + wanted + «раскрыто») or ``next_roll_at += 1 d``;
   past ``reveal_until`` the case is closed forever.
6. FEAT-204 guard patrols (between 4 and 5): due patrol guards (``next_move_at <= now``) take one step each
   (``patrol_crud.step_guard``: own transactions, blocked guards retry in 2 min, the arrival sweep checks every
   player present); skipped entirely when ``law_settings.patrols_enabled`` is off.

Wanted decay is not materialised here: readers compute it lazily and exactly. The async flows run through
``asyncio.run`` (the scheduler thread has no event loop).
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

import battle_client
import law_core as lc
import law_crud
import law_flows
import law_notify
import patrol_crud
import shadow_crud

logger = logging.getLogger("character-service.law_pass")

RUN_INTERVAL_SECONDS = 55
FIGHT_POLL_AFTER = timedelta(minutes=2)
BATCH_SIZE = 200
MSG_SERVED = "Срок заключения окончен — вы свободны"
FINISHED_STATUSES = ("finished", "forfeit")


def claim_run(db: Session, now: datetime) -> bool:
    """Conditional claim (commits). False when another run is recent or there is no settings row."""
    cutoff = now - timedelta(seconds=RUN_INTERVAL_SECONDS)
    result = db.execute(text(
        "UPDATE law_settings SET pass_last_run_at = :now WHERE id = 1 "
        "AND (pass_last_run_at IS NULL OR pass_last_run_at <= :cutoff)"), {"now": now, "cutoff": cutoff})
    db.commit()
    return (result.rowcount or 0) == 1


def _ids(db: Session, sql: str, params: dict) -> List[int]:
    rows = db.execute(text(sql), {**params, "n": BATCH_SIZE}).fetchall()
    db.rollback()
    return [int(r[0]) for r in rows]


def _expired_encounters(db: Session, now: datetime, stats: dict) -> None:
    for encounter_id in _ids(db, "SELECT id FROM law_encounters WHERE status = :s AND expires_at <= :now "
                                 "ORDER BY id LIMIT :n", {"s": lc.ENC_PENDING, "now": now}):
        try:
            notices = asyncio.run(law_flows.auto_resolve(db, encounter_id))
        except Exception:
            db.rollback()
            logger.exception("law pass: auto-resolution of encounter %s failed", encounter_id)
            continue
        stats["auto_resolved"] += 1
        law_notify.publish(notices)


def _reset_to_pending(db: Session, encounter_id: int) -> None:
    db.execute(text("UPDATE law_encounters SET status = :p, battle_id = NULL, fight_started_at = NULL "
                    "WHERE id = :id AND status = :f"),
               {"p": lc.ENC_PENDING, "f": lc.ENC_FIGHTING, "id": int(encounter_id)})
    db.commit()


def _lost_callbacks(db: Session, now: datetime, stats: dict) -> None:
    rows = db.execute(text(
        "SELECT id, battle_id FROM law_encounters WHERE status = :s AND fight_started_at <= :cut ORDER BY id LIMIT :n"),
        {"s": lc.ENC_FIGHTING, "cut": now - FIGHT_POLL_AFTER, "n": BATCH_SIZE}).fetchall()
    db.rollback()
    for encounter_id, battle_id in rows:
        try:
            if not battle_id:                   # the create call never stored a battle: offer the choice again
                _reset_to_pending(db, encounter_id)
                stats["fights_reset"] += 1
                continue
            result = battle_client.get_battle_result(int(battle_id))
            if result == battle_client.BATTLE_NOT_FOUND:
                _reset_to_pending(db, encounter_id)
                stats["fights_reset"] += 1
                continue
            if result.get("status") not in FINISHED_STATUSES:
                continue
            _out, notices = asyncio.run(law_flows.battle_result(
                db, battle_id=int(battle_id), encounter_id=int(encounter_id), winner_team=result.get("winner_team"),
                aborted=bool(result.get("aborted"))))
            stats["fights_applied"] += 1
            law_notify.publish(notices)
        except battle_client.BattleServiceError as exc:
            db.rollback()
            logger.warning("law pass: battle %s of encounter %s not polled: %s", battle_id, encounter_id, exc)
        except Exception:
            db.rollback()
            logger.exception("law pass: battle result of encounter %s failed", encounter_id)


def _served_terms(db: Session, now: datetime, stats: dict) -> None:
    for term_id in _ids(db, "SELECT id FROM law_jail_terms WHERE status = :s AND until <= :now ORDER BY id LIMIT :n",
                        {"s": lc.JAIL_SERVING, "now": now}):
        try:
            term = (db.query(law_crud.models.LawJailTerm).filter(law_crud.models.LawJailTerm.id == term_id)
                    .with_for_update().populate_existing().first())
            if term is None or term.status != lc.JAIL_SERVING or law_crud._dt(term.until) > now:
                db.rollback()
                continue
            term.status = lc.JAIL_SERVED
            term.resolved_at = now
            term.notified = True
            db.execute(text("UPDATE characters SET jail_region_id = NULL, jail_district_id = NULL "
                            "WHERE id = :c AND (jailed_until IS NULL OR jailed_until <= :now)"),
                       {"c": int(term.character_id), "now": now})
            law_crud._log(db, key=f"law:served:{term.id}", character_id=int(term.character_id),
                          action=lc.LOG_SERVED, region_id=int(term.region_id), ref_id=int(term.id), now=now)
            character_id = int(term.character_id)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("law pass: served term %s failed", term_id)
            continue
        stats["served"] += 1
        user_id = law_crud.character_user_ids(db, [character_id]).get(character_id)
        law_notify.publish([law_notify.Notice(user_id, MSG_SERVED, law_notify.WS_RELEASED,
                                              data={"character_id": character_id})])


_SQL_IDLE_GUARDS = (
    "SELECT c.id FROM characters c WHERE c.is_npc = 1 AND c.npc_role = :role AND c.npc_status = 'alive' "
    "AND (c.unconscious_until IS NULL OR c.unconscious_until <= :now) "
    "AND NOT EXISTS (SELECT 1 FROM battle_participants bp JOIN battles b ON b.id = bp.battle_id "
    "WHERE bp.character_id = c.id AND b.status IN ('pending', 'in_progress') AND bp.dropped_out_at IS NULL)"
)


def _guard_recovery(db: Session, now: datetime, stats: dict) -> None:
    try:
        ids = _ids(db, _SQL_IDLE_GUARDS + " AND EXISTS (SELECT 1 FROM character_attributes ca WHERE "
                       "ca.character_id = c.id AND ca.current_health < ca.max_health) ORDER BY c.id LIMIT :n",
                   {"role": lc.GUARD_ROLE, "now": now})
        for guard_id in ids:
            law_crud.heal_guard(db, guard_id)
        cleared = db.execute(text(
            "UPDATE characters SET unconscious_until = NULL WHERE is_npc = 1 AND npc_role = :role "
            "AND unconscious_until IS NOT NULL AND unconscious_until <= :now"), {"role": lc.GUARD_ROLE, "now": now})
        db.commit()
        stats["guards_healed"] += len(ids)
        stats["guards_recovered"] += int(cleared.rowcount or 0)
    except Exception:
        db.rollback()
        logger.exception("law pass: guard recovery failed")


def _guard_patrols(db: Session, now: datetime, stats: dict) -> None:
    settings = law_crud.load_settings(db)
    db.rollback()
    if not settings.patrols_enabled:
        return
    for npc_id in patrol_crud.due_guards(db, now, BATCH_SIZE):
        try:
            outcome = patrol_crud.step_guard(db, npc_id, now)
        except Exception:
            db.rollback()
            logger.exception("law pass: patrol step of guard %s failed", npc_id)
            continue
        if outcome.outcome == patrol_crud.OUT_MOVED:
            stats["patrol_moves"] += 1
        elif outcome.outcome == patrol_crud.OUT_BLOCKED:
            stats["patrol_blocked"] += 1
        stats["patrol_checked"] += outcome.checked
        stats["patrol_encounters"] += outcome.encounters
        stats["patrol_slips"] += outcome.slipped


def _reveal_crimes(db: Session, now: datetime, stats: dict) -> None:
    for crime_id in _ids(db, "SELECT id FROM law_crimes WHERE status IN (:u, :m) AND next_roll_at <= :now "
                             "ORDER BY next_roll_at, id LIMIT :n",
                         {"u": lc.CRIME_UNWITNESSED, "m": lc.CRIME_MASKED, "now": now}):
        try:
            result = shadow_crud.roll_reveal(db, crime_id, now)
            closed = result is None and law_crud.log_exists(db, f"law:closed:{crime_id}")
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("law pass: reveal roll of crime %s failed", crime_id)
            continue
        stats["reveal_rolls"] += 1
        if result is not None:
            stats["revealed"] += 1
            result.publish()
        elif closed:
            stats["closed"] += 1


def run_pass(session_factory: Callable[[], Session], now: Optional[datetime] = None, *, claim: bool = True) -> dict:
    """One law pass. Never raises for one bad item."""
    stats = {"ran": False, "auto_resolved": 0, "fights_applied": 0, "fights_reset": 0, "served": 0,
             "guards_healed": 0, "guards_recovered": 0, "patrol_moves": 0, "patrol_blocked": 0, "patrol_checked": 0,
             "patrol_encounters": 0, "patrol_slips": 0, "reveal_rolls": 0, "revealed": 0, "closed": 0}
    db = session_factory()
    try:
        now = now or law_crud.now_utc()
        if claim and not claim_run(db, now):
            return stats
        stats["ran"] = True
        for step in (_expired_encounters, _lost_callbacks, _served_terms, _guard_recovery, _guard_patrols,
                     _reveal_crimes):
            try:
                step(db, now, stats)
            except Exception:
                db.rollback()
                logger.exception("law pass step %s failed", step.__name__)
        if any(v for k, v in stats.items() if k != "ran"):
            logger.info("law pass: %s", stats)
        return stats
    finally:
        db.close()
