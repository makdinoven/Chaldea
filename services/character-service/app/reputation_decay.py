"""FEAT-197 §3.6: the hourly pass that materialises the negative reputation decay and notifies tier changes.

Called from ``econ_scheduler.run_scheduled_once`` BEFORE the economy ``tick_enabled`` switch (decay is not economy);
manual economy runs never call it. Readers always use ``reputation_core.effective_value``, so gates and prices are
exact even when this pass does not run — it only writes the journal and sends the «забывают» notifications.

Throttle: ``reputation_settings.decay_last_run_at`` is claimed with a conditional UPDATE, so several processes /
restarts never run it twice within :data:`RUN_INTERVAL_SECONDS`. Rows are processed in batches of
:data:`BATCH_SIZE` in ``(character_id, region_id)`` order (the global reputation lock order), each batch its own
transaction; notifications go out after each batch commit.
"""

import logging
from datetime import datetime, timedelta
from typing import Callable, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

import models
import reputation_core as rc
import reputation_crud
import reputation_notify

logger = logging.getLogger("character-service.reputation_decay")

RUN_INTERVAL_SECONDS = 3600
BATCH_SIZE = 500


def claim_run(db: Session, now: datetime) -> bool:
    """Conditional claim of the hourly slot (commits). False when another run is recent or there is no settings row."""
    cutoff = now - timedelta(seconds=RUN_INTERVAL_SECONDS)
    result = db.execute(text(
        "UPDATE reputation_settings SET decay_last_run_at = :now WHERE id = 1 "
        "AND (decay_last_run_at IS NULL OR decay_last_run_at <= :cutoff)"), {"now": now, "cutoff": cutoff})
    db.commit()
    return (result.rowcount or 0) == 1


def _batch_keys(db: Session, after: tuple) -> List[tuple]:
    c, r = after
    rows = db.execute(text(
        "SELECT character_id, region_id FROM character_reputation WHERE value < 0 AND decay_at IS NOT NULL "
        "AND (character_id > :c OR (character_id = :c AND region_id > :r)) "
        "ORDER BY character_id, region_id LIMIT :n"), {"c": c, "r": r, "n": BATCH_SIZE}).fetchall()
    return [(int(x[0]), int(x[1])) for x in rows]


def _process_batch(db: Session, keys: List[tuple], settings: rc.Settings, tiers, now: datetime) -> list:
    changes = []
    by_char = {}
    for character_id, region_id in keys:
        by_char.setdefault(character_id, []).append(region_id)
    for character_id in sorted(by_char):
        for row in reputation_crud.lock_rows(db, character_id, by_char[character_id]):
            change = reputation_crud.materialise_row(db, row, settings=settings, tiers=tiers, now=now, force=False)
            if change is not None:
                changes.append(change)
    db.flush()
    return changes


def _with_names(db: Session, changes: list) -> list:
    if not changes:
        return []
    infos = reputation_crud.region_infos(db, {c.region_id for c in changes})
    ids = sorted({c.character_id for c in changes})
    users = {int(ch.id): ch.user_id for ch in
             db.query(models.Character.id, models.Character.user_id).filter(models.Character.id.in_(ids)).all()}
    out = []
    for c in changes:
        info = infos.get(c.region_id)
        out.append(reputation_crud.TierChange(
            c.character_id, users.get(c.character_id), c.region_id, info.name if info else None, c.tier_before,
            c.tier_before_name, c.tier_after, c.tier_after_name, c.direction))
    return out


def run_pass(session_factory: Callable[[], Session], now: Optional[datetime] = None, *, claim: bool = True) -> dict:
    """One decay pass. Returns ``{"ran": bool, "rows": n, "tier_changes": n}``. Never raises for one bad batch."""
    now = now or reputation_crud.now_utc()
    stats = {"ran": False, "rows": 0, "tier_changes": 0}
    db = session_factory()
    try:
        if claim and not claim_run(db, now):
            return stats
        stats["ran"] = True
        settings, tiers = reputation_crud.load_settings(db), reputation_crud.load_tiers(db)
        db.rollback()
        if settings.decay_per_day <= 0:
            return stats
        after = (0, 0)
        while True:
            keys = _batch_keys(db, after)
            if not keys:
                break
            after = keys[-1]
            try:
                changes = _process_batch(db, keys, settings, tiers, now)
                changes = _with_names(db, changes)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("reputation decay batch failed (after %s)", after)
                continue
            stats["rows"] += len(keys)
            stats["tier_changes"] += len(changes)
            reputation_notify.publish_tier_changes(changes)
        if stats["rows"]:
            logger.info("reputation decay pass: rows=%s tier_changes=%s", stats["rows"], stats["tier_changes"])
        return stats
    finally:
        db.close()
