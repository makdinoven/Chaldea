"""Activity lock (FEAT-175): a character inside a dungeon run, or knocked out
after a wipe, cannot act in the outside world.

Source of truth: two nullable columns on `characters`, owned by this service:
  * `dungeon_session_id` — set while the character is in a dungeon run;
  * `unconscious_until`  — naive UTC; a value in the past means "not locked",
    so no cleanup job is needed.

Other services read the same two columns from the shared DB (the established
pattern for battle/gathering locks) and only character-service writes them.
"""

from datetime import datetime, timedelta
from typing import Optional

# Players are Russian-speaking; messages show Moscow time (fixed UTC+3).
MSK_OFFSET = timedelta(hours=3)

REASON_DUNGEON = "dungeon"
REASON_UNCONSCIOUS = "unconscious"


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


def compute_lock(dungeon_session_id, unconscious_until, now: Optional[datetime] = None) -> dict:
    """Build the public lock object from the two raw column values.

    Unconsciousness wins over the dungeon lock (a knocked-out character never
    holds a dungeon lock anyway — the knock-out clears it).
    """
    now = now or datetime.utcnow()
    until = _as_naive_utc(unconscious_until)
    if until is not None and until > now:
        return {
            "locked": True,
            "reason": REASON_UNCONSCIOUS,
            "until": until.isoformat(),
            "dungeon_session_id": None,
        }
    if isinstance(dungeon_session_id, int) and dungeon_session_id > 0:
        return {
            "locked": True,
            "reason": REASON_DUNGEON,
            "until": None,
            "dungeon_session_id": dungeon_session_id,
        }
    return {"locked": False, "reason": None, "until": None, "dungeon_session_id": None}


def lock_for_character(character) -> dict:
    return compute_lock(
        getattr(character, "dungeon_session_id", None),
        getattr(character, "unconscious_until", None),
    )


def lock_message(lock: dict, subject: str = "Персонаж") -> Optional[str]:
    """Russian refusal text, identical in every service."""
    if not lock or not lock.get("locked"):
        return None
    if lock.get("reason") == REASON_UNCONSCIOUS:
        until = _as_naive_utc(lock.get("until"))
        if until is not None:
            return f"{subject} без сознания до {(until + MSK_OFFSET).strftime('%H:%M')} МСК"
        return f"{subject} без сознания"
    return f"{subject} находится в подземелье"


# ---------------------------------------------------------------------------
# Shared-DB read (sync). Same pattern as check_not_in_battle: the columns
# belong to character-service, this service only reads them.
# ---------------------------------------------------------------------------

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

LOCK_STATUS_CODE = 409


def get_activity_lock(db, character_id: int) -> dict:
    row = db.execute(
        text("SELECT dungeon_session_id, unconscious_until FROM characters WHERE id = :cid"),
        {"cid": character_id},
    ).fetchone()
    if not row:
        return compute_lock(None, None)
    return compute_lock(row[0], row[1])


def check_not_activity_locked(db, character_id: int, subject: str = "Персонаж") -> None:
    """Raise 409 with the shared Russian wording if the character is in a
    dungeon run or knocked out (FEAT-175)."""
    message = lock_message(get_activity_lock(db, character_id), subject=subject)
    if message:
        raise HTTPException(status_code=LOCK_STATUS_CODE, detail=message)
