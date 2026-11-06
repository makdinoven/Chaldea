"""FEAT-205 §3.8: the faction pass of the character-service scheduler.

Called from ``econ_scheduler.run_scheduled_once`` (after the law pass, before the economy switch — factions are not
economy). Throttle: a conditional UPDATE claim on ``faction_settings.pass_last_run_at`` (>= :data:`RUN_INTERVAL_SECONDS`),
so several processes never double-run. Every member is its own transaction; a failure is logged and skipped.

1. Condition watch over every ACTIVE membership (active or hidden factions): entry conditions incl. the implicit
   irreconcilable ones are re-evaluated —
   * unmet, no warning        -> ``warning_at = now`` + reasons, log ``warning``, notify;
   * met, warned              -> warning cleared, log ``warning_cleared``, notify;
   * unmet, warning expired   -> expelled (same consequences as leaving), log ``expelled``, notify.
2. Outbox: stale ``sending`` rows and due ``pending`` deliveries (``faction_rewards.retry_due``).
3. FEAT-207: eject sweep (``faction_territory.sweep``) — players in a closed territory they may not stand in.

Never started under pytest by the scheduler; tests call :func:`run_pass` directly (``now=`` / ``force=``).
"""

import logging
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

import faction_core as fc
import faction_crud
import faction_notify
import faction_rewards
import models
from faction_notify import CATEGORY_SYSTEM, Notice

logger = logging.getLogger("character-service.faction_pass")

RUN_INTERVAL_SECONDS = 300
BATCH_SIZE = 200
EXPEL_REASON = "Не соответствует условиям вступления"


def claim_run(db: Session, now: datetime) -> bool:
    """Conditional claim (commits). False when another run is recent or there is no settings row."""
    cutoff = now - timedelta(seconds=RUN_INTERVAL_SECONDS)
    result = db.execute(text(
        "UPDATE faction_settings SET pass_last_run_at = :now WHERE id = 1 "
        "AND (pass_last_run_at IS NULL OR pass_last_run_at <= :cutoff)"), {"now": now, "cutoff": cutoff})
    db.commit()
    return (result.rowcount or 0) == 1


class _Structure:
    """Per-run cache of conditions / irreconcilable pairs / names."""

    def __init__(self, db: Session):
        self.irr = faction_crud.hostile_map(db, irreconcilable_only=True)
        self.conds: Dict[int, List[Tuple[str, dict]]] = {}
        self.refs: Dict[int, fc.Refs] = {}

    def conditions(self, db: Session, faction_id: int) -> Tuple[List[Tuple[str, dict]], fc.Refs]:
        if faction_id not in self.conds:
            own = faction_crud.load_conditions(db, [faction_id])
            self.conds[faction_id] = faction_crud.entry_conditions(faction_id, own, self.irr)
            self.refs[faction_id] = faction_crud.load_refs(db, self.conds[faction_id])
        return self.conds[faction_id], self.refs[faction_id]


def check_member(db: Session, member_id: int, now: datetime, s: fc.FactionSettings,
                 structure: _Structure) -> Tuple[Optional[str], List[Notice]]:
    """One membership (caller commits). Returns (outcome: warned | cleared | expelled | None, notices)."""
    query = db.query(models.FactionMember).filter(models.FactionMember.id == int(member_id))
    if faction_crud.for_update(db):
        query = query.with_for_update().populate_existing()
    member = query.first()
    if member is None or member.status != fc.STATUS_ACTIVE:
        return None, []
    faction = db.get(models.Faction, int(member.faction_id))
    ch = faction_crud.character_row(db, member.character_id)
    if faction is None or ch is None:
        return None, []
    conditions, refs = structure.conditions(db, int(faction.id))
    facts = faction_crud.load_facts(db, ch, conditions, refs)
    unmet = fc.unmet_texts(fc.evaluate(conditions, facts, refs))
    data = {"faction_id": int(faction.id), "character_id": ch.id}
    if not unmet:
        if member.warning_at is None:
            return None, []
        member.warning_at = None
        member.warning_reasons = None
        faction_crud.log_event(db, character_id=ch.id, faction_id=faction.id, event_type=fc.EV_WARNING_CLEARED,
                               now=now, points_after=int(member.points), rank_id=member.rank_id)
        return "cleared", [Notice(ch.user_id, f"Вы снова соответствуете условиям фракции «{faction.name}» — "
                                              f"угроза исключения снята", CATEGORY_SYSTEM,
                                  {**data, "event": fc.EV_WARNING_CLEARED})]
    if member.warning_at is None:
        member.warning_at = now
        member.warning_reasons = unmet
        faction_crud.log_event(db, character_id=ch.id, faction_id=faction.id, event_type=fc.EV_WARNING, now=now,
                               points_after=int(member.points), rank_id=member.rank_id,
                               reason="; ".join(unmet)[:500])
        left = faction_crud.remaining_text(fc.warning_deadline(now, s), now)
        return "warned", [Notice(ch.user_id, f"Вы перестали соответствовать условиям фракции «{faction.name}»: "
                                             f"{'; '.join(unmet)}. Исправьте в течение {left}, иначе вас исключат",
                                 CATEGORY_SYSTEM, {**data, "event": fc.EV_WARNING})]
    if fc.warning_deadline(member.warning_at, s) <= now:
        faction_crud.depart(db, member, fc.STATUS_EXPELLED, now, s, reason=EXPEL_REASON)
        return "expelled", [faction_crud.expel_notice(ch, faction, EXPEL_REASON)]
    if list(member.warning_reasons or []) != unmet:            # keep the shown reasons current
        member.warning_reasons = unmet
    return None, []


def _active_member_ids(db: Session, after_id: int) -> List[int]:
    rows = db.execute(text("SELECT id FROM faction_members WHERE status = :s AND id > :after ORDER BY id LIMIT :n"),
                      {"s": fc.STATUS_ACTIVE, "after": int(after_id), "n": BATCH_SIZE}).fetchall()
    db.rollback()
    return [int(r[0]) for r in rows]


def watch_conditions(db: Session, now: datetime, stats: dict) -> None:
    s = faction_crud.load_settings(db)
    structure = _Structure(db)
    db.rollback()
    last = 0
    while True:
        ids = _active_member_ids(db, last)
        if not ids:
            return
        for member_id in ids:
            last = member_id
            try:
                outcome, notices = check_member(db, member_id, now, s, structure)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("faction pass: membership %s not checked", member_id)
                continue
            if outcome:
                stats[outcome] += 1
            faction_notify.publish(notices)


def run_pass(factory: Callable[[], Session], now: Optional[datetime] = None, *, force: bool = False) -> Optional[dict]:
    """One pass (None = throttled / no settings row)."""
    now = now or faction_crud.now_utc()
    db = factory()
    try:
        if not force and not claim_run(db, now):
            return None
        stats = {"warned": 0, "cleared": 0, "expelled": 0}
        watch_conditions(db, now, stats)
    finally:
        db.close()
    try:
        stats["deliveries"] = faction_rewards.retry_due(factory, now)
    except Exception:
        logger.exception("faction pass: outbox retries failed")
    # FEAT-206: quartermaster item deliveries (retries / stale claims), then the debt queue of every faction with
    # open debts (covers admin adjustments / emissions). Never economic simulation (that is the 6 h tick).
    try:
        import faction_qm_crud
        stats["qm_deliveries"] = faction_qm_crud.retry_due(factory, now)
    except Exception:
        logger.exception("faction pass: quartermaster deliveries failed")
    try:
        import faction_econ_crud
        stats["debts_settled"] = faction_econ_crud.sweep_debts(factory, now)
    except Exception:
        logger.exception("faction pass: debt settle sweep failed")
    # FEAT-207 §3.4: players standing in a closed territory they may not stand in (left / expelled / rule added /
    # forced move) are moved out; busy ones (battle, dungeon, jail, encounter) are retried next pass.
    try:
        import faction_territory
        stats["ejected"] = faction_territory.sweep(factory)
    except Exception:
        logger.exception("faction pass: eject sweep failed")
    return stats
