"""FEAT-199 fame — read side of locations-service (§3.7 «Мин. слава» quest gate).

The renown tables (``character_renown``, ``renown_tiers``) belong to character-service; this module only
READS them with raw parameterised SQL. Fame never decays (FEAT-199 Q1), so the stored value is the effective
one. An empty ``renown_tiers`` falls back to the seed ladder below (same codes / names / thresholds as the
character-service seed of ``040_shadow_renown``).

Read only when some quest of the list actually has ``min_fame_tier`` set — no fame read otherwise.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

SCALE_FAME = "fame"

# Fixed fame tier codes, lowest first (the names / thresholds are editable in character-service).
FAME_TIER_CODES = ("nameless", "familiar", "known", "famous", "legend")

MSG_FAME_GATE = "Нужна слава: {name}"

SQL_SELECT_FAME_TIERS = (
    "SELECT code, name, min_value, sort_order FROM renown_tiers "
    "WHERE scale = :scale ORDER BY sort_order"
)
SQL_SELECT_FAME = "SELECT fame FROM character_renown WHERE character_id = :character_id"


@dataclass(frozen=True)
class FameTier:
    code: str
    name: str
    min_value: int
    sort_order: int


DEFAULT_FAME_TIERS: List[FameTier] = [
    FameTier("nameless", "Безвестный", 0, 1),
    FameTier("familiar", "Знакомое имя", 50, 2),
    FameTier("known", "Известный", 200, 3),
    FameTier("famous", "Знаменитый", 600, 4),
    FameTier("legend", "Легенда", 1500, 5),
]


def tiers_from_rows(rows) -> List[FameTier]:
    """Rows (code, name, min_value, sort_order) -> ladder sorted by threshold; empty -> the seed ladder."""
    tiers = [FameTier(str(r[0]), str(r[1]), int(r[2]), int(r[3])) for r in rows or []]
    if not tiers:
        return list(DEFAULT_FAME_TIERS)
    return sorted(tiers, key=lambda t: (t.min_value, t.sort_order))


def tier_by_code(code: Optional[str], tiers: Sequence[FameTier]) -> Optional[FameTier]:
    for tier in tiers:
        if tier.code == code:
            return tier
    return None


def tier_for(value: int, tiers: Sequence[FameTier]) -> FameTier:
    """The highest tier whose threshold the value reaches (the first tier for anything below)."""
    current = tiers[0]
    for tier in tiers:
        if value >= tier.min_value:
            current = tier
    return current


def meets(value: int, min_code: Optional[str], tiers: Sequence[FameTier]) -> bool:
    """No code / unknown code = open (same rule as the reputation gate)."""
    needed = tier_by_code(min_code, tiers)
    if needed is None:
        return True
    return value >= needed.min_value


def fame_gate_message(code: str, tiers: Sequence[FameTier]) -> str:
    tier = tier_by_code(code, tiers)
    return MSG_FAME_GATE.format(name=tier.name if tier else code)


# --------------------------------------------------------------------------------------------------- raw reads

async def load_fame_tiers(session: AsyncSession) -> List[FameTier]:
    rows = (await session.execute(text(SQL_SELECT_FAME_TIERS), {"scale": SCALE_FAME})).fetchall()
    return tiers_from_rows(rows)


async def fame_value(session: AsyncSession, character_id: int) -> int:
    """Stored fame of the character; 0 without a row."""
    row = (await session.execute(text(SQL_SELECT_FAME), {"character_id": int(character_id)})).first()
    return max(0, int(row[0])) if row is not None and row[0] is not None else 0


async def fame_tier(session: AsyncSession, character_id: int) -> FameTier:
    tiers = await load_fame_tiers(session)
    return tier_for(await fame_value(session, character_id), tiers)


class FameGates:
    """The character's fame, read once for a quest list / accept."""

    def __init__(self, value: int, tiers: Sequence[FameTier]):
        self.value = value
        self.tiers = tiers

    def reason(self, quest_min_code: Optional[str]) -> Optional[str]:
        """«Нужна слава: X» when the quest's fame gate is not met, else None."""
        if not quest_min_code or meets(self.value, quest_min_code, self.tiers):
            return None
        return fame_gate_message(quest_min_code, self.tiers)


OPEN_FAME_GATES = FameGates(0, DEFAULT_FAME_TIERS)


async def quest_fame_gates(session: AsyncSession, character_id: int,
                           quest_codes: Sequence[Optional[str]]) -> FameGates:
    """Reads nothing when no quest has a fame gate (§3.7)."""
    if not any(quest_codes):
        return OPEN_FAME_GATES
    tiers = await load_fame_tiers(session)
    return FameGates(await fame_value(session, character_id), tiers)
