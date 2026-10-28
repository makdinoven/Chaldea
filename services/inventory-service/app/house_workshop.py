"""House rooms seen from inventory-service (FEAT-180, stage 2).

Houses live in locations-service's tables; this module reads them straight
from the shared DB. A room being built for the first time has level 0; an
upgrade finishes by itself once `upgrade_complete_at` has passed (the same lazy
rule locations-service applies), so the level is read through `ROOM_LEVEL_SQL`.

A workshop specialised in the character's profession gives a bonus to crafting
and refining when the character stands in the house's location and may enter
the workshop (its owner, or a resident let in).

Furniture standing in a room (`house_furniture`, stage 3) adds its item's
bonus: storage stacks in a storage, experience and refining double chance in
a workshop (on top of the level's bonus, for the workshop's profession).

Stage 6a: the workshop is one of six profession rooms (`PROFESSION_ROOM_TYPES`,
the profession in `workshop_profession_id`); a cellar holds stacks like a
storage, only more; a kitchen the character may use where it stands makes food
last longer (`kitchen_satiety_hours`).

Stage 6b: house blessings (`house_buffs`, written by locations-service: a
library's bonus to all character experience, a shrine's to gathering or post
experience) and elite trophies hanging in trophy halls (battle experience for the
owner and the residents, wherever they are) add to the XP multiplier
(`house_xp_bonus`); return circles are where the home teleport scroll leads
(`return_circles`).
"""

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# The room's level now: a finished upgrade counts even before locations-service settles it.
ROOM_LEVEL_SQL = (
    "CASE WHEN r.upgrade_complete_at IS NOT NULL AND r.upgrade_complete_at <= CURRENT_TIMESTAMP "
    "THEN r.upgrade_to_level ELSE r.level END"
)

STORAGE_STACKS_BY_LEVEL = {1: 30, 2: 45, 3: 60}
CELLAR_STACKS_BY_LEVEL = {1: 50, 2: 75, 3: 100}
PROFESSION_ROOM_TYPES = ("forge", "alchemy_lab", "kitchen", "jewelry", "enchanting", "study")
# Satiety hours of food eaten with a kitchen of the level at hand; without one, the default.
DEFAULT_SATIETY_HOURS = 24
KITCHEN_SATIETY_HOURS = {1: 30, 2: 36, 3: 48}
WORKSHOP_XP_BONUS_BY_LEVEL = {1: 0.10, 2: 0.20, 3: 0.30}
WORKSHOP_REFINE_DOUBLE_BONUS_BY_LEVEL = {1: 0.05, 2: 0.10, 3: 0.15}


def _furniture_sum(db: Session, room_id: int, column: str) -> float:
    try:
        value = db.execute(text(
            f"SELECT SUM(i.{column}) FROM house_furniture f JOIN items i ON i.id = f.item_id "
            "WHERE f.room_id = :r"), {"r": room_id}).scalar()
    except Exception:
        # Stand-in schemas without the furniture table: nothing stands there.
        return 0.0
    return float(value or 0)


def storage_capacity(db: Session, house_id: int) -> int:
    """Stacks the built storages and cellars of the house hold, with their furniture."""
    rooms = db.execute(
        text(f"SELECT r.id, r.room_type, {ROOM_LEVEL_SQL} FROM house_rooms r "
             "WHERE r.house_id = :hid AND r.room_type IN ('storage', 'cellar')"),
        {"hid": house_id},
    ).fetchall()
    total = 0
    for room_id, room_type, level in rooms:
        if int(level or 0) >= 1:
            by_level = CELLAR_STACKS_BY_LEVEL if room_type == "cellar" else STORAGE_STACKS_BY_LEVEL
            total += by_level.get(int(level), 0)
            total += int(_furniture_sum(db, room_id, "furniture_storage_stacks"))
    return total


def _usable_rooms(db: Session, character_id: int, room_types, profession_id: Optional[int] = None,
                  in_room: bool = False):
    """(room id, level) of the built rooms of these types (and profession) the character may use where they stand:
    an active house in its location, owned or with the room let to it. With `in_room` (stage 7) only the
    room the character stands in (`characters.house_room_id`)."""
    types = ", ".join(f"'{t}'" for t in room_types)
    params = {"cid": character_id}
    profession = ""
    if profession_id is not None:
        profession = "AND r.workshop_profession_id = :prof "
        params["prof"] = profession_id
    if in_room:
        profession += "AND c.house_room_id = r.id "
    try:
        rows = db.execute(text(
            f"SELECT r.id, {ROOM_LEVEL_SQL} FROM house_rooms r "
            "JOIN houses h ON h.id = r.house_id "
            "JOIN house_plots p ON p.id = h.plot_id "
            "JOIN characters c ON c.id = :cid AND c.current_location_id = p.location_id "
            f"WHERE r.room_type IN ({types}) {profession}AND h.status = 'active' "
            "AND (h.owner_character_id = :cid OR EXISTS ("
            "  SELECT 1 FROM house_residents hr JOIN house_resident_rooms rr ON rr.resident_id = hr.id "
            "  WHERE hr.house_id = h.id AND hr.character_id = :cid AND rr.room_id = r.id))"
        ), params).fetchall()
    except Exception:
        # Stand-in schemas without the house tables (tests of other features): no such room.
        return []
    return [(room_id, int(level or 0)) for room_id, level in rows if int(level or 0) >= 1]


def _usable_workshops(db: Session, character_id: int, profession_id: int):
    """(room id, level) of the built profession room of this profession the character stands in
    (stage 7: being in the house's location is not enough)."""
    return _usable_rooms(db, character_id, PROFESSION_ROOM_TYPES, profession_id, in_room=True)


def kitchen_satiety_hours(db: Session, character_id: int) -> int:
    """How long food eaten now lasts: the best usable kitchen's hours, or the default.
    Stage 7 left it as it was: a kitchen of a house in the character's location that it may use
    counts wherever in that location the character eats (inside the house or not)."""
    level = max((lvl for _, lvl in _usable_rooms(db, character_id, ("kitchen",))), default=0)
    return KITCHEN_SATIETY_HOURS.get(level, DEFAULT_SATIETY_HOURS)


def workshop_level(db: Session, character_id: int, profession_id: int) -> int:
    """The best workshop level of this profession the character may use where they stand, or 0."""
    return max((level for _, level in _usable_workshops(db, character_id, profession_id)), default=0)


def workshop_bonus(db: Session, character_id: int, profession_id: int) -> dict:
    """The best usable workshop's bonus: level plus its furniture. xp and refine are fractions."""
    best = {"level": 0, "xp": 0.0, "refine": 0.0}
    for room_id, level in _usable_workshops(db, character_id, profession_id):
        xp = WORKSHOP_XP_BONUS_BY_LEVEL.get(level, 0.0) + _furniture_sum(db, room_id, "furniture_xp_bonus_pct") / 100
        refine = (WORKSHOP_REFINE_DOUBLE_BONUS_BY_LEVEL.get(level, 0.0)
                  + _furniture_sum(db, room_id, "furniture_refine_bonus_pct") / 100)
        if (xp, refine) > (best["xp"], best["refine"]):
            best = {"level": level, "xp": xp, "refine": refine}
    return best


def workshop_for(db: Session, cp) -> dict:
    """Workshop bonus for a character profession row (None → no bonus)."""
    if cp is None:
        return {"level": 0, "xp": 0.0, "refine": 0.0}
    return workshop_bonus(db, cp.character_id, cp.profession_id)


# ---------------------------------------------------------------------------
# Stage 6b: house blessings, trophies, return circles
# ---------------------------------------------------------------------------

# Character XP sources a library blessing speeds up (the umbrella and the five granular ones).
CHARACTER_XP_TYPES = frozenset({
    "character_xp_bonus", "character_xp_battle_bonus", "character_xp_post_bonus",
    "character_xp_quest_bonus", "character_xp_title_bonus", "character_xp_pass_bonus",
})
# XP source -> the shrine blessing kind that speeds it up.
SHRINE_XP_KINDS = {"character_xp_post_bonus": "post_xp", "gathering_xp_bonus": "gathering_xp"}
BATTLE_XP_TYPE = "character_xp_battle_bonus"
# Mirror of locations-service houses.TROPHY_SLOTS / TROPHY_BONUS_PER_PIECE / TROPHY_BONUS_CAP.
TROPHY_SLOTS = {1: 5, 2: 10, 3: 15}
TROPHY_BONUS_PER_PIECE = 0.01
TROPHY_BONUS_CAP = 0.15
# The chance a home teleport scroll is kept, by the target's return circle level.
CIRCLE_KEEP_CHANCE = {1: 0.0, 2: 0.15, 3: 0.30}


def house_buffs(db: Session, character_id: int, now: Optional[datetime] = None) -> Dict[tuple, float]:
    """The character's running house blessings: {(source, kind): value}."""
    try:
        rows = db.execute(text(
            "SELECT source, kind, value FROM house_buffs WHERE character_id = :cid AND expires_at > :now"),
            {"cid": character_id, "now": now or datetime.utcnow()}).fetchall()
    except Exception:
        # Stand-in schemas without the house tables: no blessing.
        return {}
    return {(source, kind): float(value or 0) for source, kind, value in rows}


def trophy_bonus(db: Session, character_id: int) -> float:
    """Battle experience from elite trophies: the best active house the character owns or lives in
    (+1 % a trophy, a hall counting at most its slots), at most 15 %."""
    try:
        rows = db.execute(text(
            f"SELECT h.id, r.id, {ROOM_LEVEL_SQL}, "
            "(SELECT COUNT(*) FROM house_furniture f JOIN items i ON i.id = f.item_id "
            " WHERE f.room_id = r.id AND i.is_elite_trophy = 1) "
            "FROM house_rooms r JOIN houses h ON h.id = r.house_id "
            "WHERE r.room_type = 'trophy_hall' AND h.status = 'active' AND h.plot_id IS NOT NULL "
            "AND (h.owner_character_id = :cid OR EXISTS ("
            "  SELECT 1 FROM house_residents hr WHERE hr.house_id = h.id AND hr.character_id = :cid))"
        ), {"cid": character_id}).fetchall()
    except Exception:
        return 0.0
    by_house: Dict[int, int] = {}
    for house_id, _room_id, level, count in rows:
        by_house[house_id] = by_house.get(house_id, 0) + min(int(count or 0), TROPHY_SLOTS.get(int(level or 0), 0))
    best = max(by_house.values(), default=0)
    return round(min(best * TROPHY_BONUS_PER_PIECE, TROPHY_BONUS_CAP), 4)


def house_xp_bonus(db: Session, character_id: int, buff_type: str) -> float:
    """What the character's house adds to one XP source's multiplier (a fraction):
    the library blessing to every character-XP source, the shrine's to post or
    gathering experience, the trophies to battle experience."""
    if buff_type not in CHARACTER_XP_TYPES and buff_type not in SHRINE_XP_KINDS:
        return 0.0
    buffs = house_buffs(db, character_id)
    total = 0.0
    if buff_type in CHARACTER_XP_TYPES:
        total += buffs.get(("library", "character_xp"), 0.0)
    if buff_type in SHRINE_XP_KINDS:
        total += buffs.get(("shrine", SHRINE_XP_KINDS[buff_type]), 0.0)
    if buff_type == BATTLE_XP_TYPE:
        total += trophy_bonus(db, character_id)
    return total


def return_circles(db: Session, character_id: int) -> List[dict]:
    """Houses the home teleport scroll may carry the character to: active houses it owns,
    or where it is let into a built return circle; the best circle of each house (`room_id` —
    stage 7: the character arrives standing in it)."""
    try:
        rows = db.execute(text(
            f"SELECT h.id, h.name, p.location_id, {ROOM_LEVEL_SQL}, r.id FROM house_rooms r "
            "JOIN houses h ON h.id = r.house_id JOIN house_plots p ON p.id = h.plot_id "
            "WHERE r.room_type = 'return_circle' AND h.status = 'active' "
            "AND (h.owner_character_id = :cid OR EXISTS ("
            "  SELECT 1 FROM house_residents hr JOIN house_resident_rooms rr ON rr.resident_id = hr.id "
            "  WHERE hr.house_id = h.id AND hr.character_id = :cid AND rr.room_id = r.id)) "
            "ORDER BY h.id"
        ), {"cid": character_id}).fetchall()
    except Exception:
        return []
    out: Dict[int, dict] = {}
    for house_id, name, location_id, level, room_id in rows:
        level = int(level or 0)
        if level < 1:
            continue
        entry = out.setdefault(house_id, {"house_id": house_id, "name": name, "location_id": location_id,
                                          "circle_level": 0, "room_id": room_id})
        if level > entry["circle_level"]:
            entry["circle_level"], entry["room_id"] = level, room_id
    for entry in out.values():
        entry["keep_chance"] = CIRCLE_KEEP_CHANCE.get(entry["circle_level"], 0.0)
    return list(out.values())
