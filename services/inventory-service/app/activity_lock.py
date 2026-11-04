"""Activity lock (FEAT-175): a character inside a dungeon run, or knocked out
after a wipe, cannot act in the outside world.

Source of truth: two nullable columns on `characters`, owned by this service:
  * `dungeon_session_id` — set while the character is in a dungeon run;
  * `unconscious_until`  — naive UTC; a value in the past means "not locked",
    so no cleanup job is needed.

FEAT-198 (law) adds two more columns on `characters`:
  * `jailed_until`     — naive UTC; in jail while in the future (lazy, like
    `unconscious_until`);
  * `law_encounter_id` — set while the guards have stopped the character and
    the player has not chosen what to do yet.

Other services read the same columns from the shared DB (the established
pattern for battle/gathering locks) and only character-service writes them.
"""

from datetime import datetime, timedelta
from typing import Optional

# Players are Russian-speaking; messages show Moscow time (fixed UTC+3).
MSK_OFFSET = timedelta(hours=3)

REASON_DUNGEON = "dungeon"
REASON_UNCONSCIOUS = "unconscious"
# FEAT-180: asleep in a house bedroom (`characters.asleep_since`), until woken.
REASON_ASLEEP = "asleep"
# FEAT-180 stage 6b: reading in a house library (`characters.reading_since`), until stopped.
REASON_READING = "reading"
# FEAT-198: serving a jail term (`characters.jailed_until` in the future).
REASON_JAIL = "jail"
# FEAT-198: stopped by the guards, a choice is pending (`characters.law_encounter_id`).
REASON_LAW_ENCOUNTER = "law_encounter"


def _as_naive_utc(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        value = (value - value.utcoffset()).replace(tzinfo=None)
    return value


def _lock(reason, until=None, dungeon_session_id=None, law_encounter_id=None) -> dict:
    return {
        "locked": reason is not None,
        "reason": reason,
        "until": until,
        "dungeon_session_id": dungeon_session_id,
        "law_encounter_id": law_encounter_id,
    }


def compute_lock(dungeon_session_id, unconscious_until, now: Optional[datetime] = None,
                 asleep_since=None, reading_since=None,
                 jailed_until=None, law_encounter_id=None) -> dict:
    """Build the public lock object from the raw column values.

    Priority: jail > law_encounter > unconscious > dungeon > asleep > reading.
    Unconsciousness wins over the dungeon lock (a knocked-out character never
    holds a dungeon lock anyway — the knock-out clears it).
    """
    now = now or datetime.utcnow()
    jail_until = _as_naive_utc(jailed_until)
    if jail_until is not None and jail_until > now:
        return _lock(REASON_JAIL, until=jail_until.isoformat())
    if isinstance(law_encounter_id, int) and law_encounter_id > 0:
        return _lock(REASON_LAW_ENCOUNTER, law_encounter_id=law_encounter_id)
    until = _as_naive_utc(unconscious_until)
    if until is not None and until > now:
        return _lock(REASON_UNCONSCIOUS, until=until.isoformat())
    if isinstance(dungeon_session_id, int) and dungeon_session_id > 0:
        return _lock(REASON_DUNGEON, dungeon_session_id=dungeon_session_id)
    if _as_naive_utc(asleep_since) is not None:
        return _lock(REASON_ASLEEP)
    if _as_naive_utc(reading_since) is not None:
        return _lock(REASON_READING)
    return _lock(None)


def lock_for_character(character) -> dict:
    return compute_lock(
        getattr(character, "dungeon_session_id", None),
        getattr(character, "unconscious_until", None),
        asleep_since=getattr(character, "asleep_since", None),
        reading_since=getattr(character, "reading_since", None),
        jailed_until=getattr(character, "jailed_until", None),
        law_encounter_id=getattr(character, "law_encounter_id", None),
    )


def format_remaining(until: datetime, now: Optional[datetime] = None) -> str:
    """Relative time left, e.g. «2 д 5 ч», «3 ч 10 мин», «12 мин» (never «0 мин»)."""
    now = now or datetime.utcnow()
    minutes = max(1, int((until - now).total_seconds() + 59) // 60)
    days, rest = divmod(minutes, 24 * 60)
    hours, mins = divmod(rest, 60)
    if days:
        return f"{days} д {hours} ч" if hours else f"{days} д"
    if hours:
        return f"{hours} ч {mins} мин" if mins else f"{hours} ч"
    return f"{mins} мин"


def lock_message(lock: dict, subject: str = "Персонаж") -> Optional[str]:
    """Russian refusal text, identical in every service."""
    if not lock or not lock.get("locked"):
        return None
    if lock.get("reason") == REASON_JAIL:
        until = _as_naive_utc(lock.get("until"))
        if until is not None:
            return f"{subject} в тюрьме — осталось {format_remaining(until)}"
        return f"{subject} в тюрьме"
    if lock.get("reason") == REASON_LAW_ENCOUNTER:
        return f"{subject} остановлен стражей — сначала нужно решить, как поступить"
    if lock.get("reason") == REASON_UNCONSCIOUS:
        until = _as_naive_utc(lock.get("until"))
        if until is not None:
            return f"{subject} без сознания — осталось {format_remaining(until)}"
        return f"{subject} без сознания"
    if lock.get("reason") == REASON_ASLEEP:
        return f"{subject} спит — сначала нужно проснуться"
    if lock.get("reason") == REASON_READING:
        return f"{subject} читает — сначала нужно закончить чтение"
    return f"{subject} находится в подземелье"


# ---------------------------------------------------------------------------
# Shared-DB read (sync). Same pattern as check_not_in_battle: the columns
# belong to character-service, this service only reads them.
# ---------------------------------------------------------------------------

import logging  # noqa: E402

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

LOCK_STATUS_CODE = 409

logger = logging.getLogger(__name__)

_LOCK_SQL = text(
    "SELECT dungeon_session_id, unconscious_until, asleep_since, reading_since, "
    "jailed_until, law_encounter_id FROM characters WHERE id = :cid"
)
# FEAT-198 deploy skew: character-service migration 039 not applied yet.
_LOCK_SQL_LEGACY = text(
    "SELECT dungeon_session_id, unconscious_until, asleep_since, reading_since "
    "FROM characters WHERE id = :cid"
)


def _is_missing_law_column(exc: Exception) -> bool:
    msg = str(exc).lower()
    return ("jailed_until" in msg or "law_encounter_id" in msg) and (
        "unknown column" in msg or "no such column" in msg
    )


def _col(row, index: int):
    return row[index] if len(row) > index else None


def _lock_from_row(row) -> dict:
    if not row:
        return compute_lock(None, None)
    return compute_lock(row[0], row[1], asleep_since=_col(row, 2), reading_since=_col(row, 3),
                        jailed_until=_col(row, 4), law_encounter_id=_col(row, 5))


def get_activity_lock(db, character_id: int) -> dict:
    try:
        result = db.execute(_LOCK_SQL, {"cid": character_id})
    except Exception as e:
        if not _is_missing_law_column(e):
            raise
        logger.warning("characters.jailed_until/law_encounter_id ещё нет (миграция character-service 039 "
                       "не применена) — блокировка читается без закона")
        result = db.execute(_LOCK_SQL_LEGACY, {"cid": character_id})
    return _lock_from_row(result.fetchone())


def check_not_activity_locked(db, character_id: int, subject: str = "Персонаж") -> None:
    """Raise 409 with the shared Russian wording if the character is in a
    dungeon run, knocked out, asleep, reading, jailed or stopped by the guards."""
    message = lock_message(get_activity_lock(db, character_id), subject=subject)
    if message:
        raise HTTPException(status_code=LOCK_STATUS_CODE, detail=message)
