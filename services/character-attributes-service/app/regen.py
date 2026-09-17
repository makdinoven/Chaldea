"""
FEAT-164: lazy passive regeneration in rest + satiety (food effect) expiry.

Nothing runs in the background. Every read/write path of a character's
attributes calls ``settle_regen`` under the row lock; it credits the rest time
elapsed since ``regen_anchor_at`` and removes an expired satiety.

Rest time = settle window minus the union of "busy" intervals (battle,
active dungeon, gathering) read from the shared DB. All timestamps are naive
UTC; ``now``/``window_start`` are always passed as bind parameters (no
NOW()/UTC_TIMESTAMP() in these queries).
"""
import logging
import math
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

import models
from constants import REGEN_PERCENT_PER_HOUR, REGEN_RESOURCES

logger = logging.getLogger(__name__)

BUSY_BATTLE = "battle"
BUSY_DUNGEON = "dungeon"
BUSY_GATHERING = "gathering"
# Order in which busy reasons are reported by rest-status.
BUSY_REASON_ORDER = (BUSY_BATTLE, BUSY_DUNGEON, BUSY_GATHERING)

SECONDS_PER_HOUR = 3600.0
REGEN_FLOAT_EPSILON = 1e-9

Interval = Tuple[datetime, datetime]

_BATTLE_INTERVALS_SQL = sa_text(
    """
    SELECT bp.joined_at, b.created_at, bp.dropped_out_at
    FROM battle_participants bp
    JOIN battles b ON b.id = bp.battle_id
    WHERE bp.character_id = :cid
      AND ( b.status IN ('pending', 'in_progress')
            OR (bp.dropped_out_at IS NOT NULL AND bp.dropped_out_at > :ws) )
    """
)

_DUNGEON_INTERVALS_SQL = sa_text(
    """
    SELECT ds.started_at, ds.finished_at, ds.status
    FROM dungeon_session_members dsm
    JOIN dungeon_sessions ds ON ds.id = dsm.session_id
    WHERE dsm.character_id = :cid
      AND ds.started_at IS NOT NULL
      AND ds.started_at < :now
      AND ( ds.status = 'active' OR ds.finished_at > :ws )
    """
)

_GATHERING_INTERVALS_SQL = sa_text(
    """
    SELECT started_at, status, complete_at, finished_at
    FROM gathering_sessions
    WHERE character_id = :cid
      AND started_at < :now
      AND COALESCE(finished_at, complete_at) > :ws
    """
)

_IS_NPC_SQL = sa_text("SELECT is_npc FROM characters WHERE id = :cid")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def to_datetime(value) -> Optional[datetime]:
    """Normalize a DB value to a naive datetime (SQLite returns strings)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, str):
        return datetime.fromisoformat(value.strip().replace(" ", "T", 1))
    raise TypeError(f"Unsupported datetime value: {value!r}")


def merge_intervals(intervals) -> List[Interval]:
    """Merge overlapping/touching intervals; drops empty/inverted ones."""
    cleaned = sorted((s, e) for s, e in intervals if s is not None and e is not None and e > s)
    merged: List[Interval] = []
    for start, end in cleaned:
        if merged and start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def overlap_seconds(window_start: datetime, window_end: datetime, intervals) -> float:
    """Seconds of [window_start, window_end] covered by the union of intervals."""
    if window_end <= window_start:
        return 0.0
    total = 0.0
    for start, end in merge_intervals(intervals):
        s = max(start, window_start)
        e = min(end, window_end)
        if e > s:
            total += (e - s).total_seconds()
    return total


def _rest_hours(window_start: datetime, window_end: datetime, intervals) -> float:
    if window_end <= window_start:
        return 0.0
    elapsed = (window_end - window_start).total_seconds()
    return max(0.0, elapsed - overlap_seconds(window_start, window_end, intervals)) / SECONDS_PER_HOUR


# ---------------------------------------------------------------------------
# Shared-DB lookups
# ---------------------------------------------------------------------------

def load_busy_intervals_raw(
    db: Session, character_id: int, window_start: datetime, now: datetime
) -> List[Tuple[datetime, datetime, str]]:
    """Busy intervals as (start, end, kind), NOT clipped; ``end <= now``.

    Raises on DB errors — callers decide how to handle (never swallowed here).
    """
    params = {"cid": character_id, "ws": window_start, "now": now}
    result: List[Tuple[datetime, datetime, str]] = []

    for joined_at, created_at, dropped_out_at in db.execute(_BATTLE_INTERVALS_SQL, params).fetchall():
        start = to_datetime(joined_at) or to_datetime(created_at)
        end = to_datetime(dropped_out_at) or now
        if start is not None:
            result.append((start, min(end, now), BUSY_BATTLE))

    for started_at, finished_at, status in db.execute(_DUNGEON_INTERVALS_SQL, params).fetchall():
        start = to_datetime(started_at)
        end = to_datetime(finished_at)
        if end is None:
            # Legacy wiped rows without finished_at collapse to zero length.
            end = now if status == "active" else start
        result.append((start, min(end, now), BUSY_DUNGEON))

    for started_at, status, complete_at, finished_at in db.execute(_GATHERING_INTERVALS_SQL, params).fetchall():
        start = to_datetime(started_at)
        complete = to_datetime(complete_at)
        finished = to_datetime(finished_at)
        if status == "active":
            end = min(complete, now)
        else:
            end = finished or complete
        result.append((start, min(end, now), BUSY_GATHERING))

    return result


def load_busy_intervals(
    db: Session, character_id: int, window_start: datetime, now: datetime
) -> List[Interval]:
    """Busy intervals clipped to [window_start, now]."""
    clipped: List[Interval] = []
    for start, end, _kind in load_busy_intervals_raw(db, character_id, window_start, now):
        s = max(start, window_start)
        e = min(end, now)
        if e > s:
            clipped.append((s, e))
    return clipped


def get_busy_reason(db: Session, character_id: int, now: datetime) -> Optional[str]:
    """Current busy state: 'battle' | 'dungeon' | 'gathering' | None.

    Raises on DB errors (caller logs and reports).
    """
    kinds = {
        kind
        for _start, end, kind in load_busy_intervals_raw(db, character_id, now, now)
        if end >= now
    }
    for kind in BUSY_REASON_ORDER:
        if kind in kinds:
            return kind
    return None


def is_regen_eligible(db: Session, character_id: int) -> bool:
    """False for NPCs/mobs and for characters without a `characters` row.

    Raises on DB errors.
    """
    row = db.execute(_IS_NPC_SQL, {"cid": character_id}).fetchone()
    if row is None:
        return False
    return not bool(row[0])


def get_satiety(db: Session, character_id: int) -> Optional[models.CharacterSatiety]:
    return (
        db.query(models.CharacterSatiety)
        .filter(models.CharacterSatiety.character_id == character_id)
        .first()
    )


def negate_modifiers(modifiers) -> dict:
    return {k: -v for k, v in (modifiers or {}).items() if v}


# ---------------------------------------------------------------------------
# Settle
# ---------------------------------------------------------------------------

def _credit_regen(attr, bonus_hours: float, plain_hours: float, regen_bonus: float) -> None:
    for resource in REGEN_RESOURCES:
        cur_name = f"current_{resource}"
        carry_name = f"regen_carry_{resource}"
        current = int(getattr(attr, cur_name) or 0)
        maximum = int(getattr(attr, f"max_{resource}") or 0)
        carry = float(getattr(attr, carry_name) or 0.0)
        if maximum <= 0 or current >= maximum:
            setattr(attr, carry_name, 0.0)
            continue
        effective_hours = bonus_hours * (1.0 + regen_bonus) + plain_hours
        gain = maximum * REGEN_PERCENT_PER_HOUR / 100.0 * effective_hours + carry
        # Epsilon absorbs float error (e.g. 3599.9999999999995 s of rest) so a
        # whole point is not deferred by one read; carry is clamped at >= 0.
        whole = int(math.floor(gain + REGEN_FLOAT_EPSILON))
        new_current = min(maximum, current + whole)
        setattr(attr, cur_name, new_current)
        setattr(attr, carry_name, 0.0 if new_current >= maximum else max(0.0, gain - whole))


def _all_full(attr) -> bool:
    return all(
        int(getattr(attr, f"current_{r}") or 0) >= int(getattr(attr, f"max_{r}") or 0)
        for r in REGEN_RESOURCES
    )


def settle_regen(db: Session, attr, now: Optional[datetime] = None) -> bool:
    """Credit passive regen up to ``now`` and remove an expired satiety.

    The caller MUST hold ``attr`` via ``with_for_update()`` inside a transaction
    and commits afterwards. Idempotent: a second call with the same ``now`` is a
    no-op. Returns True when stats changed because a satiety expired (the caller
    should reconcile perks after commit).
    """
    if now is None:
        now = datetime.utcnow()
    character_id = attr.character_id

    try:
        eligible = is_regen_eligible(db, character_id)
    except Exception:
        logger.exception(
            "settle_regen: не удалось проверить is_npc для персонажа %s — восстановление пропущено",
            character_id,
        )
        eligible = False

    satiety = get_satiety(db, character_id)

    if eligible:
        anchor = to_datetime(attr.regen_anchor_at)
        if anchor is None:
            # Clock starts now — no retroactive heal on deploy/creation.
            attr.regen_anchor_at = now
            for resource in REGEN_RESOURCES:
                setattr(attr, f"regen_carry_{resource}", 0.0)
        elif now > anchor:
            if _all_full(attr):
                for resource in REGEN_RESOURCES:
                    setattr(attr, f"regen_carry_{resource}", 0.0)
                attr.regen_anchor_at = now
            else:
                try:
                    busy = load_busy_intervals(db, character_id, anchor, now)
                except Exception:
                    # Safe direction: no credit, anchor not moved.
                    logger.exception(
                        "settle_regen: ошибка чтения интервалов занятости персонажа %s — "
                        "восстановление не начислено",
                        character_id,
                    )
                    busy = None
                if busy is not None:
                    if satiety is not None:
                        expires = to_datetime(satiety.expires_at)
                        t1 = min(max(expires, anchor), now)
                        regen_bonus = float(satiety.regen_bonus or 0.0)
                    else:
                        t1 = anchor
                        regen_bonus = 0.0
                    bonus_hours = _rest_hours(anchor, t1, busy)
                    plain_hours = _rest_hours(t1, now, busy)
                    _credit_regen(attr, bonus_hours, plain_hours, regen_bonus)
                    attr.regen_anchor_at = now

    # Expiry: subtract the satiety modifiers exactly once (row deleted in the
    # same transaction).
    if satiety is not None and to_datetime(satiety.expires_at) <= now:
        import crud  # local import: crud does not import regen at module level

        db.flush()
        reverse = negate_modifiers(satiety.modifiers)
        if reverse:
            crud._apply_modifiers_internal(db, character_id, reverse, propagate_derived=False)
        db.delete(satiety)
        db.flush()
        logger.info("Сытость персонажа %s истекла, бонусы сняты", character_id)
        return True

    return False


def lock_attributes(db: Session, character_id: int):
    return (
        db.query(models.CharacterAttributes)
        .filter(models.CharacterAttributes.character_id == character_id)
        .with_for_update()
        .first()
    )


def reconcile_perks_after_expiry(db: Session, character_id: int) -> None:
    """Best-effort perk reconcile after satiety modifiers changed the stats.

    Call only after the settle transaction was committed.
    """
    try:
        from perk_evaluator import reconcile_perks
        reconcile_perks(db, character_id)
    except Exception as e:
        db.rollback()
        logger.warning(
            "reconcile-perks после изменения сытости персонажа %s не выполнен: %s",
            character_id, e,
        )


def settle_character(db: Session, character_id: int, now: Optional[datetime] = None):
    """Lock → settle → commit → (perk reconcile). Returns the attributes row or None."""
    attr = lock_attributes(db, character_id)
    if attr is None:
        db.rollback()
        return None
    try:
        stats_changed = settle_regen(db, attr, now)
        db.commit()
    except Exception:
        db.rollback()
        raise
    if stats_changed:
        reconcile_perks_after_expiry(db, character_id)
    db.refresh(attr)
    return attr


def satiety_expires_at(now: datetime, hours: int) -> datetime:
    return now + timedelta(hours=hours)
