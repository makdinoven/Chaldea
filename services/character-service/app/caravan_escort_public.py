"""FEAT-212 3.6 — what strangers may see of a caravan escort.

While a player escorts a physical caravan (``characters.escort_caravan_id`` set) he rides hidden inside the wagon:
public cards show the location where he was hired (``econ_caravan_escorts.hire_location_id``, "frozen") and no
activity lock at all (the escort lock is the only one dropped — other reasons stay visible as before). Owner-facing
reads (``/users/me`` via the internal short_info) keep the real values.
"""

from typing import Dict, Iterable, Optional

from sqlalchemy.orm import Session

import activity_lock
import models

STATUS_ACTIVE = "active"  # = caravan_escort_crud.STATUS_ACTIVE (kept local: this module is imported by main early)


def _escort_caravan(ch) -> Optional[int]:
    value = getattr(ch, "escort_caravan_id", None)
    # ints only, like activity_lock.compute_lock (mocked characters in tests carry MagicMock attributes)
    return int(value) if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def public_location_id(db: Session, ch):
    """The location strangers see: the hire location while the character is an active escort, else the real one."""
    caravan_id = _escort_caravan(ch)
    if caravan_id is None:
        return ch.current_location_id
    row = db.query(models.EconCaravanEscort.hire_location_id).filter(
        models.EconCaravanEscort.caravan_id == caravan_id,
        models.EconCaravanEscort.character_id == int(ch.id),
        models.EconCaravanEscort.status == STATUS_ACTIVE,
    ).first()
    if row is not None and row[0] is not None:
        return int(row[0])
    return ch.current_location_id  # dangling column (housekeeping clears it): nothing better to show


def public_locations(db: Session, characters: Iterable) -> Dict[int, Optional[int]]:
    """Batch :func:`public_location_id` for a list of loaded characters (one query): ``{character_id: location}``."""
    chars = list(characters)
    out: Dict[int, Optional[int]] = {int(ch.id): ch.current_location_id for ch in chars}
    escorts = {int(ch.id): _escort_caravan(ch) for ch in chars if _escort_caravan(ch) is not None}
    if not escorts:
        return out
    rows = db.query(models.EconCaravanEscort.character_id, models.EconCaravanEscort.caravan_id,
                    models.EconCaravanEscort.hire_location_id).filter(
        models.EconCaravanEscort.character_id.in_(list(escorts)),
        models.EconCaravanEscort.status == STATUS_ACTIVE,
    ).all()
    for character_id, caravan_id, hire_location_id in rows:
        cid = int(character_id)
        if escorts.get(cid) == int(caravan_id) and hire_location_id is not None:
            out[cid] = int(hire_location_id)
    return out


def public_lock(ch) -> dict:
    """The activity lock strangers see: computed without the escort column (an escort looks unlocked)."""
    return activity_lock.compute_lock(
        getattr(ch, "dungeon_session_id", None),
        getattr(ch, "unconscious_until", None),
        asleep_since=getattr(ch, "asleep_since", None),
        reading_since=getattr(ch, "reading_since", None),
        jailed_until=getattr(ch, "jailed_until", None),
        law_encounter_id=getattr(ch, "law_encounter_id", None),
    )


def mask_body(db: Session, ch, body: dict) -> dict:
    """Apply the stranger view to a card dict carrying ``current_location_id`` / ``activity_lock`` (in place)."""
    if _escort_caravan(ch) is None:
        return body
    if "current_location_id" in body:
        body["current_location_id"] = public_location_id(db, ch)
    if "activity_lock" in body:
        body["activity_lock"] = public_lock(ch)
    return body
