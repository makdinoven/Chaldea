"""FEAT-205 factions — read side of locations-service (§3.9 quest gating, §3.10 quest validation).

The faction tables (``factions``, ``faction_ranks``, ``faction_members``, ``faction_conditions``) belong to
character-service (migration ``045_factions_core``); this module only READS them with raw parameterised SQL.

Deploy-order tolerance (§3.14): every read treats a missing table / SQL error as "no faction data" and logs a
warning. For quest gating that means *fail closed* — a faction quest whose faction cannot be read is hidden from
the list and cannot be accepted; ``in_any_faction`` answers True on an error (the post-completion call is then
sent anyway, character-service decides). Nothing is read when no quest of a list has a faction.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

STATUS_ACTIVE = "active"
COND_QUEST = "quest"

MSG_MEMBERS_ONLY = "Только для членов фракции «{name}»"
MSG_RANK_NEEDED = "Нужно звание «{rank}» во фракции «{name}»"
MSG_QUEST_NOT_FOUND = "Задание не найдено"
MSG_QUEST_IN_USE = "Задание используется как условие фракции"
GATE_STATUS = 403
HIDDEN_STATUS = 404

SQL_FACTIONS = text("SELECT id, name, is_secret FROM factions WHERE id IN :ids").bindparams(
    bindparam("ids", expanding=True))
SQL_RANKS = text("SELECT id, faction_id, name, sort_order FROM faction_ranks WHERE id IN :ids").bindparams(
    bindparam("ids", expanding=True))
SQL_MEMBERSHIPS = text(
    "SELECT faction_id, rank_id FROM faction_members "
    "WHERE character_id = :cid AND status = :status AND faction_id IN :ids"
).bindparams(bindparam("ids", expanding=True))
SQL_ANY_MEMBERSHIP = text(
    "SELECT 1 FROM faction_members WHERE character_id = :cid AND status = :status LIMIT 1")
SQL_RANK_REFERENCES = text("SELECT 1 FROM faction_ranks WHERE required_quest_id = :qid LIMIT 1")
SQL_QUEST_CONDITIONS = text("SELECT params FROM faction_conditions WHERE cond_type = :cond_type")


@dataclass(frozen=True)
class FactionInfo:
    id: int
    name: str
    is_secret: bool


@dataclass(frozen=True)
class RankInfo:
    id: int
    faction_id: int
    name: str
    sort_order: int


def _ids(values: Iterable) -> List[int]:
    return sorted({int(v) for v in values if v is not None})


async def _rows(session: AsyncSession, stmt, params: dict, what: str) -> Optional[list]:
    """Rows of a raw read, or None when the faction tables are not there / the read failed."""
    try:
        return (await session.execute(stmt, params)).fetchall()
    except SQLAlchemyError as exc:
        logger.warning("Faction read (%s) failed, treated as no faction data: %s", what, exc)
        return None


# --------------------------------------------------------------------------------------------------- raw reads

async def factions_by_ids(session: AsyncSession, ids: Iterable) -> Dict[int, FactionInfo]:
    ids = _ids(ids)
    if not ids:
        return {}
    rows = await _rows(session, SQL_FACTIONS, {"ids": ids}, "factions") or []
    return {int(r[0]): FactionInfo(int(r[0]), str(r[1]), bool(r[2])) for r in rows}


async def ranks_by_ids(session: AsyncSession, ids: Iterable) -> Dict[int, RankInfo]:
    ids = _ids(ids)
    if not ids:
        return {}
    rows = await _rows(session, SQL_RANKS, {"ids": ids}, "ranks") or []
    return {int(r[0]): RankInfo(int(r[0]), int(r[1]), str(r[2]), int(r[3] or 0)) for r in rows}


async def active_memberships(session: AsyncSession, character_id: int,
                             faction_ids: Iterable) -> Dict[int, Optional[int]]:
    """{faction_id: rank_id | None} of the character's ACTIVE memberships among the given factions."""
    ids = _ids(faction_ids)
    if not ids:
        return {}
    rows = await _rows(session, SQL_MEMBERSHIPS,
                       {"cid": int(character_id), "status": STATUS_ACTIVE, "ids": ids}, "memberships") or []
    return {int(r[0]): (int(r[1]) if r[1] is not None else None) for r in rows}


async def in_any_faction(session: AsyncSession, character_id: int) -> bool:
    """Is the character an active member anywhere? A failed read answers True (the call is then sent anyway)."""
    rows = await _rows(session, SQL_ANY_MEMBERSHIP,
                       {"cid": int(character_id), "status": STATUS_ACTIVE}, "any membership")
    if rows is None:
        return True
    return bool(rows)


def _param_quest_id(params) -> Optional[int]:
    if isinstance(params, (str, bytes)):
        import json
        try:
            params = json.loads(params)
        except (TypeError, ValueError):
            return None
    if not isinstance(params, dict):
        return None
    try:
        return int(params.get("quest_id"))
    except (TypeError, ValueError):
        return None


async def quest_referenced(session: AsyncSession, quest_id: int) -> bool:
    """Is the quest an entry condition of some faction or a rank condition? A failed read answers False
    (no faction tables yet = nothing can reference it)."""
    rows = await _rows(session, SQL_RANK_REFERENCES, {"qid": int(quest_id)}, "rank quest references")
    if rows:
        return True
    rows = await _rows(session, SQL_QUEST_CONDITIONS, {"cond_type": COND_QUEST}, "quest conditions") or []
    return any(_param_quest_id(r[0]) == int(quest_id) for r in rows)


# --------------------------------------------------------------------------------------------------- gating

@dataclass(frozen=True)
class QuestGate:
    hidden: bool = False             # removed from the list / 404 on accept
    reason: Optional[str] = None     # locked_reason / 403 on accept


OPEN_GATE = QuestGate()
HIDDEN_GATE = QuestGate(hidden=True)


class FactionGates:
    """The character's faction standing, read once for a quest list / accept (§3.9)."""

    def __init__(self, factions: Dict[int, FactionInfo], ranks: Dict[int, RankInfo],
                 memberships: Dict[int, Optional[int]]):
        self.factions = factions
        self.ranks = ranks
        self.memberships = memberships

    def gate(self, faction_id: Optional[int], min_rank_id: Optional[int]) -> QuestGate:
        if not faction_id:
            return OPEN_GATE
        faction = self.factions.get(int(faction_id))
        if faction is None:  # unknown faction / unreadable tables: fail closed
            return HIDDEN_GATE
        if faction.id not in self.memberships:
            if faction.is_secret:
                return HIDDEN_GATE
            return QuestGate(reason=MSG_MEMBERS_ONLY.format(name=faction.name))
        needed = self.ranks.get(int(min_rank_id)) if min_rank_id else None
        if needed is None or needed.faction_id != faction.id:  # no rank gate / a rank that no longer exists
            return OPEN_GATE
        held = self.ranks.get(self.memberships[faction.id] or 0)
        if held is None or held.faction_id != faction.id or held.sort_order < needed.sort_order:
            return QuestGate(reason=MSG_RANK_NEEDED.format(rank=needed.name, name=faction.name))
        return OPEN_GATE


OPEN_FACTION_GATES = FactionGates({}, {}, {})


async def quest_faction_gates(session: AsyncSession, character_id: int,
                              quests: Sequence[tuple]) -> FactionGates:
    """`quests` = [(faction_id, min_faction_rank_id)]. Reads nothing when no quest has a faction."""
    faction_ids = _ids(q[0] for q in quests)
    if not faction_ids:
        return OPEN_FACTION_GATES
    factions = await factions_by_ids(session, faction_ids)
    memberships = await active_memberships(session, character_id, factions.keys())
    rank_ids = [q[1] for q in quests if q[0]] + list(memberships.values())
    ranks = await ranks_by_ids(session, rank_ids)
    return FactionGates(factions, ranks, memberships)


# --------------------------------------------------------------------------------------------------- FEAT-207 territory

ACCESS_LOCATION = "location"
LABEL_CLOSED = "Закрыто"
REFUSAL_SECRET = "Сюда вас не пускают"

SQL_ACCESS_RULES = text(
    "SELECT target_id, faction_id, min_rank_id FROM faction_access_rules WHERE kind = :kind AND target_id IN :ids"
).bindparams(bindparam("ids", expanding=True))
SQL_ACCESS_FACTIONS = text("SELECT id, name, is_secret, is_active FROM factions WHERE id IN :ids").bindparams(
    bindparam("ids", expanding=True))
SQL_CHARACTER_OWNER = text("SELECT user_id FROM characters WHERE id = :cid")


@dataclass(frozen=True)
class AccessMark:
    label: Optional[str]
    allowed: Optional[bool]          # None = viewer unknown (public label)
    refusal: Optional[str] = None


def access_decision(name: str, is_secret: bool, rank: Optional[RankInfo], *, viewer_known: bool,
                    is_member: bool = False, held_order: Optional[int] = None) -> AccessMark:
    """Mirror of character-service ``faction_core.access_decision`` for an ACTIVE faction (parity tested by QA)."""
    if not viewer_known:
        return AccessMark(LABEL_CLOSED if is_secret else f"Закрыто: {name}", None)
    if is_member:
        if rank is None or (held_order is not None and held_order >= rank.sort_order):
            return AccessMark(f"Территория фракции «{name}»", True)
        return AccessMark(f"Закрыто: нужно звание «{rank.name}» во фракции «{name}»", False,
                          f"Нужно звание «{rank.name}» во фракции «{name}»")
    if is_secret:
        return AccessMark(LABEL_CLOSED, False, REFUSAL_SECRET)
    return AccessMark(f"Закрыто: {name}", False, f"Вход только для членов фракции «{name}»")


async def access_marks(session: AsyncSession, kind: str, target_ids: Iterable,
                       character_id: Optional[int] = None) -> Dict[int, AccessMark]:
    """{target_id: mark} of the targets with an effective rule (hidden factions open their territories). Missing
    tables / a failed read -> {} (no marks; the authoritative check in character-service still runs)."""
    try:
        return await _access_marks(session, kind, target_ids, character_id)
    except Exception as exc:  # never break a move / a page over the marks
        logger.warning("Faction access marks not read, treated as none: %s", exc)
        return {}


async def _access_marks(session: AsyncSession, kind: str, target_ids: Iterable,
                        character_id: Optional[int]) -> Dict[int, AccessMark]:
    ids = _ids(target_ids)
    if not ids:
        return {}
    rules = await _rows(session, SQL_ACCESS_RULES, {"kind": kind, "ids": ids}, "access rules")
    if not rules:
        return {}
    faction_ids = _ids(r[1] for r in rules)
    frows = await _rows(session, SQL_ACCESS_FACTIONS, {"ids": faction_ids}, "access factions")
    if frows is None:
        return {}
    factions = {int(r[0]): (str(r[1]), bool(r[2]), bool(r[3])) for r in frows}
    memberships: Dict[int, Optional[int]] = {}
    if character_id:
        memberships = await active_memberships(session, int(character_id), faction_ids)
    ranks = await ranks_by_ids(session, [r[2] for r in rules] + list(memberships.values()))
    out: Dict[int, AccessMark] = {}
    for target_id, faction_id, min_rank_id in rules:
        info = factions.get(int(faction_id))
        if info is None or not info[2]:
            continue                                     # deleted / hidden faction: open
        name, secret, _active = info
        rank = ranks.get(int(min_rank_id)) if min_rank_id else None
        is_member = int(faction_id) in memberships
        held = ranks.get(memberships.get(int(faction_id)) or 0) if is_member else None
        out[int(target_id)] = access_decision(name, secret, rank, viewer_known=bool(character_id),
                                              is_member=is_member, held_order=held.sort_order if held else None)
    return out


async def location_access(session: AsyncSession, character_id: int, location_id: int) -> Optional[str]:
    """The move pre-check (before the post is created): the refusal text, or None (may enter / unknown)."""
    marks = await access_marks(session, ACCESS_LOCATION, [location_id], character_id)
    mark = marks.get(int(location_id))
    return mark.refusal if mark is not None and mark.allowed is False else None


async def owned_character(session: AsyncSession, character_id: Optional[int], user_id: Optional[int]) -> Optional[int]:
    """The character id only when it belongs to ``user_id`` (viewer-aware marks), else None."""
    if not character_id or not user_id:
        return None
    try:
        rows = await _rows(session, SQL_CHARACTER_OWNER, {"cid": int(character_id)}, "character owner")
    except Exception as exc:  # a mocked / broken session: public labels
        logger.warning("Character owner not read, public marks: %s", exc)
        return None
    if not rows or rows[0][0] is None or int(rows[0][0]) != int(user_id):
        return None
    return int(character_id)
