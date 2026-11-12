"""FEAT-205 factions — DB reads and player / internal flows (sync SQLAlchemy). features/FEAT-205 §3.5, §3.9.

Every write flow runs in the caller's transaction (the API ``_write`` wrapper commits once) and returns a
:class:`FlowResult` whose ``notices`` are published AFTER the commit and whose ``deliver`` character ids get their
rank-reward outbox rows delivered after the commit (``faction_hooks.dispatch``). Rank rewards are only RECORDED here
(``faction_rank_grants`` + ``faction_reward_deliveries``); delivery lives in ``faction_rewards``.

Secrecy (§3.9): a secret faction is never named to a player in condition texts, its member count / limit is never
returned, and public reads skip it. Fame / infamy are compared by tier, numbers never leave the service.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import activity_lock
import econ_core as core
import faction_core as fc
import law_crud
import models
import renown_crud
import reputation_crud
import shadow_core as sc
from faction_notify import CATEGORY_PROGRESS, CATEGORY_SYSTEM, Notice

logger = logging.getLogger("character-service.faction_crud")

MSG_CHARACTER_NOT_FOUND = "Персонаж не найден"
MSG_FACTION_NOT_FOUND = "Фракция не найдена"
MSG_NPC = "NPC не может вступать во фракции"
MSG_INVITE_ONLY = "Вступление только по заявке"
MSG_NOT_INVITE_ONLY = "Во фракцию можно вступить без заявки"
MSG_ALREADY_MEMBER = "Вы уже состоите в этой фракции"
MSG_ALREADY_APPLIED = "Заявка уже подана"
MSG_NO_PLACES = "Во фракции нет мест"
MSG_CONDITIONS = "Условия вступления не выполнены"
MSG_REJOIN_COOLDOWN = "Повторное вступление возможно через {left}"
MSG_REAPPLY_COOLDOWN = "Повторная заявка возможна через {left}"
MSG_IRRECONCILABLE = "Нельзя состоять одновременно в этой фракции и во фракции «{name}»"
MSG_NOT_MEMBER = "Вы не состоите в этой фракции"
MSG_APP_NOT_FOUND = "Заявка не найдена"
MSG_APP_NOT_PENDING = "Заявка уже рассмотрена"
MSG_PENDING_BLOCK = "Заявка на рассмотрении"


class FactionError(Exception):
    """Business error (HTTP status + Russian text)."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = int(status_code)
        self.detail = detail


@dataclass
class FlowResult:
    data: dict = field(default_factory=dict)
    notices: List[Notice] = field(default_factory=list)
    deliver: Set[int] = field(default_factory=set)

    def merge(self, other: "FlowResult") -> "FlowResult":
        self.notices.extend(other.notices)
        self.deliver |= other.deliver
        return self


# =====================================================================================================================
# helpers
# =====================================================================================================================

def now_utc() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def for_update(db: Session) -> bool:
    return db.get_bind().dialect.name != "sqlite"


def in_clause(prefix: str, values: Sequence) -> Tuple[str, Dict[str, object]]:
    names = [f"{prefix}{i}" for i in range(len(values))]
    return ", ".join(f":{n}" for n in names), dict(zip(names, values))


def load_settings(db: Session) -> fc.FactionSettings:
    return fc.settings_from_row(db.get(models.FactionSettings, 1))


def remaining_text(until: datetime, now: datetime) -> str:
    return activity_lock.format_remaining(until, now)


@dataclass(frozen=True)
class CharacterRow:
    id: int
    user_id: Optional[int]
    is_npc: bool
    level: int
    class_id: Optional[int]
    race_id: Optional[int]
    subrace_id: Optional[int]
    name: str
    avatar: Optional[str]


def character_row(db: Session, character_id: int) -> Optional[CharacterRow]:
    row = db.execute(text(
        "SELECT id, user_id, is_npc, level, id_class, id_race, id_subrace, name, avatar FROM characters WHERE id = :c"),
        {"c": int(character_id)}).first()
    if row is None:
        return None
    return CharacterRow(int(row[0]), int(row[1]) if row[1] is not None else None, bool(row[2]), int(row[3] or 0),
                        row[4], row[5], row[6], row[7] or "", row[8])


def require_character(db: Session, character_id: int) -> CharacterRow:
    ch = character_row(db, character_id)
    if ch is None:
        raise FactionError(404, MSG_CHARACTER_NOT_FOUND)
    return ch


def completed_quests(db: Session, character_id: int) -> Set[int]:
    """Completed quests (locations-service table, shared DB). Missing table / error -> empty (logged)."""
    try:
        rows = db.execute(text("SELECT quest_id FROM character_quests WHERE character_id = :c AND status = 'completed'"),
                          {"c": int(character_id)}).fetchall()
    except SQLAlchemyError:
        logger.warning("faction: completed quests of character %s not read", character_id, exc_info=True)
        return set()
    return {int(r[0]) for r in rows}


def quest_titles(db: Session, quest_ids: Iterable[int]) -> Dict[int, str]:
    ids = sorted({int(q) for q in quest_ids if q})
    if not ids:
        return {}
    ph, params = in_clause("q", ids)
    try:
        rows = db.execute(text(f"SELECT id, title FROM quests WHERE id IN ({ph})"), params).fetchall()
    except SQLAlchemyError:
        logger.warning("faction: quest titles not read", exc_info=True)
        return {}
    return {int(r[0]): r[1] for r in rows}


def subclass_names(db: Session, keys: Iterable[str]) -> Dict[str, str]:
    """subclass_key -> display name from the skills-service ``tree_nodes`` (``subclass_choice`` nodes; the lowest
    node id wins when several trees carry the same key). Unknown keys / DB errors -> missing (the caller falls
    back to the key)."""
    wanted = sorted({str(k) for k in keys if k})
    if not wanted:
        return {}
    ph, params = in_clause("s", wanted)
    try:
        rows = db.execute(text(
            f"SELECT subclass_key, name FROM tree_nodes WHERE node_type = 'subclass_choice' "
            f"AND subclass_key IN ({ph}) ORDER BY id"), params).fetchall()
    except SQLAlchemyError:
        logger.warning("faction: subclass names not read", exc_info=True)
        return {}
    out: Dict[str, str] = {}
    for key, name in rows:
        if key and name and str(key) not in out:
            out[str(key)] = str(name)
    return out


def location_names(db: Session, location_ids: Iterable[int]) -> Dict[int, str]:
    ids = sorted({int(x) for x in location_ids if x})
    if not ids:
        return {}
    ph, params = in_clause("l", ids)
    try:
        rows = db.execute(text(f"SELECT id, name FROM Locations WHERE id IN ({ph})"), params).fetchall()
    except SQLAlchemyError:
        logger.warning("faction: location names not read", exc_info=True)
        return {}
    return {int(r[0]): r[1] for r in rows}


def character_brief(db: Session, character_ids: Iterable[int]) -> Dict[int, dict]:
    ids = sorted({int(x) for x in character_ids if x})
    if not ids:
        return {}
    ph, params = in_clause("c", ids)
    rows = db.execute(text(f"SELECT id, name, avatar, level, id_class FROM characters WHERE id IN ({ph})"),
                      params).fetchall()
    return {int(r[0]): {"id": int(r[0]), "name": r[1], "avatar": r[2], "level": int(r[3] or 0), "class_id": r[4]}
            for r in rows}


# =====================================================================================================================
# structure loads
# =====================================================================================================================

def load_conditions(db: Session, faction_ids: Iterable[int]) -> Dict[int, List[Tuple[str, dict]]]:
    ids = sorted({int(f) for f in faction_ids})
    out: Dict[int, List[Tuple[str, dict]]] = {fid: [] for fid in ids}
    if not ids:
        return out
    rows = (db.query(models.FactionCondition).filter(models.FactionCondition.faction_id.in_(ids))
            .order_by(models.FactionCondition.faction_id, models.FactionCondition.sort_order,
                      models.FactionCondition.id).all())
    for row in rows:
        out[int(row.faction_id)].append((row.cond_type, dict(row.params or {})))
    return out


def hostility_rows(db: Session) -> List["models.FactionHostility"]:
    return db.query(models.FactionHostility).order_by(models.FactionHostility.id).all()


def hostile_map(db: Session, *, irreconcilable_only: bool = False) -> Dict[int, Set[int]]:
    out: Dict[int, Set[int]] = {}
    for row in hostility_rows(db):
        if irreconcilable_only and not row.irreconcilable:
            continue
        a, b = int(row.faction_a_id), int(row.faction_b_id)
        out.setdefault(a, set()).add(b)
        out.setdefault(b, set()).add(a)
    return out


def load_ranks(db: Session, faction_ids: Iterable[int]) -> Dict[int, List["models.FactionRank"]]:
    ids = sorted({int(f) for f in faction_ids})
    out: Dict[int, List[models.FactionRank]] = {fid: [] for fid in ids}
    if not ids:
        return out
    rows = (db.query(models.FactionRank).filter(models.FactionRank.faction_id.in_(ids))
            .order_by(models.FactionRank.faction_id, models.FactionRank.sort_order, models.FactionRank.id).all())
    for row in rows:
        out[int(row.faction_id)].append(row)
    return out


def rank_defs(ranks: Sequence["models.FactionRank"]) -> List[fc.RankDef]:
    return [fc.RankDef(id=int(r.id), sort_order=int(r.sort_order), name=r.name, min_points=int(r.min_points or 0),
                       min_level=int(r.min_level or 0),
                       required_quest_id=int(r.required_quest_id) if r.required_quest_id else None) for r in ranks]


def entry_conditions(faction_id: int, conds: Dict[int, List[Tuple[str, dict]]],
                     irr: Dict[int, Set[int]]) -> List[Tuple[str, dict]]:
    return fc.entry_conditions(faction_id, conds.get(int(faction_id), []), sorted(irr.get(int(faction_id), set())))


def active_faction_ids(db: Session, character_id: int) -> Set[int]:
    rows = db.execute(text("SELECT faction_id FROM faction_members WHERE character_id = :c AND status = :s"),
                      {"c": int(character_id), "s": fc.STATUS_ACTIVE}).fetchall()
    return {int(r[0]) for r in rows}


def _tier_map(tiers) -> Dict[str, Tuple[int, str]]:
    return {t.code: (int(t.sort_order), t.name) for t in tiers}


def load_refs(db: Session, conditions: Iterable[Tuple[str, dict]], *, extra_faction_ids: Iterable[int] = (),
              extra_quest_ids: Iterable[int] = ()) -> fc.Refs:
    conditions = list(conditions)
    types = {t for t, _p in conditions}
    refs = fc.Refs()
    if fc.COND_REGION in types:
        refs.rep_tiers = _tier_map(reputation_crud.load_tiers(db))
        infos = reputation_crud.region_infos(db, [p.get("region_id") for t, p in conditions if t == fc.COND_REGION])
        refs.regions = {rid: info.name for rid, info in infos.items()}
    if fc.COND_FAME in types:
        refs.fame_tiers = _tier_map(renown_crud.load_renown_tiers(db, sc.SCALE_FAME))
    if fc.COND_INFAMY in types:
        refs.infamy_tiers = _tier_map(renown_crud.load_renown_tiers(db, sc.SCALE_INFAMY))
    class_ids = {int(x) for t, p in conditions if t == fc.COND_CLASS for x in p.get("class_ids") or []}
    if class_ids:
        refs.classes = {int(r.id_class): r.name for r in
                        db.query(models.Class).filter(models.Class.id_class.in_(sorted(class_ids))).all()}
    race_ids = {int(x) for t, p in conditions if t == fc.COND_RACE for x in p.get("race_ids") or []}
    if race_ids:
        refs.races = {int(r.id_race): r.name for r in
                      db.query(models.Race).filter(models.Race.id_race.in_(sorted(race_ids))).all()}
    subrace_ids = {int(x) for t, p in conditions if t == fc.COND_RACE for x in p.get("subrace_ids") or []}
    if subrace_ids:
        refs.subraces = {int(r.id_subrace): r.name for r in
                         db.query(models.Subrace).filter(models.Subrace.id_subrace.in_(sorted(subrace_ids))).all()}
    subclass_keys = {str(k) for t, p in conditions if t == fc.COND_SUBCLASS for k in p.get("subclass_keys") or []}
    if subclass_keys:
        refs.subclasses = subclass_names(db, subclass_keys)
    qids = {int(p.get("quest_id") or 0) for t, p in conditions if t == fc.COND_QUEST} | {int(q) for q in
                                                                                       extra_quest_ids if q}
    refs.quests = quest_titles(db, qids)
    fids = {int(p.get("faction_id") or 0) for t, p in conditions if t == fc.COND_NOT_IN} | {int(f) for f in
                                                                                          extra_faction_ids}
    fids.discard(0)
    if fids:
        refs.factions = {int(f.id): (f.name, bool(f.is_secret)) for f in
                         db.query(models.Faction).filter(models.Faction.id.in_(sorted(fids))).all()}
    return refs


def load_facts(db: Session, ch: CharacterRow, conditions: Iterable[Tuple[str, dict]], refs: fc.Refs, *,
               with_quests: bool = False) -> fc.Facts:
    """Facts of ONE character, loading only what the given conditions need (+ completed quests on demand)."""
    conditions = list(conditions)
    types = {t for t, _p in conditions}
    facts = fc.Facts(level=ch.level, class_id=ch.class_id, race_id=ch.race_id, subrace_id=ch.subrace_id)
    facts.active_factions = active_faction_ids(db, ch.id)
    if fc.COND_FAME in types or fc.COND_INFAMY in types:
        fame, infamy = renown_crud.renown_of(db, ch.id)
        if fc.COND_FAME in types:
            facts.fame_rank = int(sc.renown_tier_for(fame, renown_crud.load_renown_tiers(db, sc.SCALE_FAME)).sort_order)
        if fc.COND_INFAMY in types:
            facts.infamy_rank = int(sc.renown_tier_for(
                infamy, renown_crud.load_renown_tiers(db, sc.SCALE_INFAMY)).sort_order)
    if fc.COND_REGION in types:
        tiers = reputation_crud.load_tiers(db)
        for region_id in {int(p.get("region_id") or 0) for t, p in conditions if t == fc.COND_REGION}:
            if region_id:
                facts.region_ranks[region_id] = int(
                    reputation_crud.tier_of(db, ch.id, region_id, tiers=tiers).sort_order)
    if fc.COND_SUBCLASS in types:
        try:
            facts.subclass_key = law_crud.subclass_of(db, ch.id)
        except SQLAlchemyError:
            logger.warning("faction: subclass of character %s not read", ch.id, exc_info=True)
    if with_quests or fc.COND_QUEST in types:
        facts.completed_quests = completed_quests(db, ch.id)
    return facts


# =====================================================================================================================
# rows
# =====================================================================================================================

def faction_or_404(db: Session, faction_id: int, *, lock: bool = False) -> "models.Faction":
    query = db.query(models.Faction).filter(models.Faction.id == int(faction_id))
    if lock and for_update(db):
        query = query.with_for_update().populate_existing()
    faction = query.first()
    if faction is None:
        raise FactionError(404, MSG_FACTION_NOT_FOUND)
    return faction


def member_row(db: Session, character_id: int, faction_id: int, *, lock: bool = False):
    query = db.query(models.FactionMember).filter(models.FactionMember.character_id == int(character_id),
                                                  models.FactionMember.faction_id == int(faction_id))
    if lock and for_update(db):
        query = query.with_for_update().populate_existing()
    return query.first()


def active_count(db: Session, faction_id: int) -> int:
    return int(db.query(func.count(models.FactionMember.id)).filter(
        models.FactionMember.faction_id == int(faction_id),
        models.FactionMember.status == fc.STATUS_ACTIVE).scalar() or 0)


def pending_application(db: Session, character_id: int, faction_id: int):
    return db.query(models.FactionApplication).filter(
        models.FactionApplication.character_id == int(character_id),
        models.FactionApplication.faction_id == int(faction_id),
        models.FactionApplication.status == fc.APP_PENDING).first()


def last_rejection(db: Session, character_id: int, faction_id: int):
    return (db.query(models.FactionApplication)
            .filter(models.FactionApplication.character_id == int(character_id),
                    models.FactionApplication.faction_id == int(faction_id),
                    models.FactionApplication.status == fc.APP_REJECTED)
            .order_by(models.FactionApplication.decided_at.desc(), models.FactionApplication.id.desc()).first())


def log_event(db: Session, *, character_id: int, faction_id: int, event_type: str, now: datetime,
              points_delta: Optional[int] = None, points_after: Optional[int] = None, rank_id: Optional[int] = None,
              event_key: Optional[str] = None, reason: Optional[str] = None,
              actor_user_id: Optional[int] = None) -> "models.FactionLog":
    row = models.FactionLog(character_id=int(character_id), faction_id=int(faction_id), event_type=event_type,
                            points_delta=points_delta, points_after=points_after, rank_id=rank_id,
                            event_key=event_key, reason=(reason or None) and str(reason)[:500],
                            actor_user_id=actor_user_id, created_at=now)
    db.add(row)
    return row


def log_key_exists(db: Session, event_key: str, faction_id: int) -> bool:
    return db.query(models.FactionLog.id).filter(models.FactionLog.event_key == event_key,
                                                 models.FactionLog.faction_id == int(faction_id)).first() is not None


# =====================================================================================================================
# rank rewards (recording only; delivery = faction_rewards)
# =====================================================================================================================

def reward_parts(db: Session, rank: "models.FactionRank") -> List[str]:
    parts = []
    if int(rank.reward_xp or 0) > 0:
        parts.append(f"+{int(rank.reward_xp)} опыта")
    if rank.reward_title_id:
        title = db.query(models.Title).filter(models.Title.id_title == int(rank.reward_title_id)).first()
        if title is not None:
            parts.append(f"титул «{title.name}»")
    qty = sum(int(i.get("quantity") or 0) for i in rank.reward_items or [])
    if qty:
        parts.append(f"предметы ×{qty}")
    names = location_names(db, [rank.reward_house_location_id, rank.reward_plot_location_id])
    if rank.reward_house_location_id:
        parts.append(f"право на дом в «{names.get(int(rank.reward_house_location_id), '—')}»")
    if rank.reward_plot_location_id:
        parts.append(f"право на участок в «{names.get(int(rank.reward_plot_location_id), '—')}»")
    marks = int(getattr(rank, "reward_marks", 0) or 0)
    if marks > 0:                                   # FEAT-206: paid from the treasury (or owed, see faction_debts)
        parts.append(f"+{core.format_currency(marks)} из казны фракции")
    return parts


def grant_rank(db: Session, character_id: int, rank: "models.FactionRank", now: datetime) -> bool:
    """Record the rank reward once per (character, rank), forever. False = already granted earlier."""
    exists = db.query(models.FactionRankGrant.id).filter(
        models.FactionRankGrant.character_id == int(character_id),
        models.FactionRankGrant.rank_id == int(rank.id)).first()
    if exists is not None:
        return False
    grant = models.FactionRankGrant(character_id=int(character_id), faction_id=int(rank.faction_id),
                                    rank_id=int(rank.id), granted_at=now)
    db.add(grant)
    db.flush()                                  # UNIQUE(character, rank) -> IntegrityError on a race (409 upstream)
    payloads: List[Tuple[str, dict]] = []
    if int(rank.reward_xp or 0) > 0:
        payloads.append((fc.KIND_XP, {"xp": int(rank.reward_xp)}))
    if rank.reward_title_id:
        payloads.append((fc.KIND_TITLE, {"title_id": int(rank.reward_title_id)}))
    for item in rank.reward_items or []:
        if int(item.get("item_id") or 0) > 0 and int(item.get("quantity") or 0) > 0:
            payloads.append((fc.KIND_ITEM, {"item_id": int(item["item_id"]), "quantity": int(item["quantity"])}))
    if rank.reward_house_location_id:
        payloads.append((fc.KIND_VOUCHER, {"location_id": int(rank.reward_house_location_id),
                                           "kind": fc.VOUCHER_READY}))
    if rank.reward_plot_location_id:
        payloads.append((fc.KIND_VOUCHER, {"location_id": int(rank.reward_plot_location_id),
                                           "kind": fc.VOUCHER_EMPTY}))
    for kind, payload in payloads:
        db.add(models.FactionRewardDelivery(grant_id=int(grant.id), character_id=int(character_id), kind=kind,
                                            payload=payload, status=fc.DLV_PENDING, attempts=0,
                                            next_attempt_at=now, updated_at=now))
    # FEAT-206 §3.5: marks always go through the debt queue (paid post-commit by faction_econ_crud.settle_debts,
    # triggered from faction_rewards.deliver_pending). Only new grants create rows: no retroactive pay.
    marks = int(getattr(rank, "reward_marks", 0) or 0)
    if marks > 0:
        db.add(models.FactionDebt(character_id=int(character_id), faction_id=int(rank.faction_id), source="rank",
                                  source_key=f"rank:g{int(grant.id)}", amount=marks, paid=0, status="open",
                                  unpaid_notified=False, created_at=now))
    return True


def _rank_notice(db: Session, ch: CharacterRow, faction: "models.Faction", rank: "models.FactionRank",
                 granted: bool) -> Notice:
    message = f"Новое звание «{rank.name}» во фракции «{faction.name}»"
    parts = reward_parts(db, rank) if granted else []
    if parts:
        message += ": " + ", ".join(parts)
    return Notice(ch.user_id, message, CATEGORY_PROGRESS,
                  {"faction_id": int(faction.id), "character_id": ch.id, "event": fc.EV_RANK_UP})


def climb_member(db: Session, ch: CharacterRow, faction: "models.Faction", member: "models.FactionMember",
                 ranks: Sequence["models.FactionRank"], level: int, completed: Set[int], now: datetime, *,
                 from_entry: bool = False, notify_each: bool = True) -> Tuple[List["models.FactionRank"], FlowResult]:
    """Walk the member up the ladder; record grants for newly reached ranks; log ``rank_up``.

    ``from_entry`` = a (re)join: the walk starts at the entry rank (logged as part of ``joined``, not ``rank_up``).
    Returns (reached rank rows, result with notices / deliver ids).
    """
    result = FlowResult()
    by_id = {int(r.id): r for r in ranks}
    reached_defs = fc.climb(rank_defs(ranks), None if from_entry else member.rank_id, int(member.points), level,
                            completed)
    if not reached_defs:
        return [], result
    reached = [by_id[d.id] for d in reached_defs]
    for index, rank in enumerate(reached):
        granted = grant_rank(db, ch.id, rank, now)
        if granted:
            result.deliver.add(ch.id)
        is_entry_of_join = from_entry and index == 0
        if not is_entry_of_join:
            log_event(db, character_id=ch.id, faction_id=faction.id, event_type=fc.EV_RANK_UP, now=now,
                      points_after=int(member.points), rank_id=int(rank.id))
            if notify_each:
                result.notices.append(_rank_notice(db, ch, faction, rank, granted))
        elif granted and notify_each:
            parts = reward_parts(db, rank)
            if parts:
                result.notices.append(Notice(ch.user_id, f"Награда за звание «{rank.name}» во фракции "
                                                         f"«{faction.name}»: " + ", ".join(parts),
                                             CATEGORY_PROGRESS, {"faction_id": int(faction.id),
                                                                 "character_id": ch.id, "event": fc.EV_RANK_UP}))
    member.rank_id = int(reached[-1].id)
    return reached, result


def recheck_ranks(db: Session, character_id: int, now: Optional[datetime] = None) -> FlowResult:
    """Rank re-check for ALL active memberships of a character (points / quest / level changes). DB only."""
    now = now or now_utc()
    result = FlowResult()
    members = (db.query(models.FactionMember)
               .filter(models.FactionMember.character_id == int(character_id),
                       models.FactionMember.status == fc.STATUS_ACTIVE)
               .order_by(models.FactionMember.id).all())
    if not members:
        return result
    ch = character_row(db, character_id)
    if ch is None:
        return result
    completed = completed_quests(db, character_id)
    ranks = load_ranks(db, [m.faction_id for m in members])
    factions = {int(f.id): f for f in db.query(models.Faction).filter(
        models.Faction.id.in_(sorted({int(m.faction_id) for m in members}))).all()}
    for member in members:
        faction = factions.get(int(member.faction_id))
        if faction is None:
            continue
        reached, sub = climb_member(db, ch, faction, member, ranks.get(int(faction.id), []), ch.level, completed, now)
        result.merge(sub)
        if reached:
            result.data["rank_ups"] = int(result.data.get("rank_ups", 0)) + len(reached)
    db.flush()
    return result


# =====================================================================================================================
# entry checks
# =====================================================================================================================

MODE_JOIN = "join"
MODE_APPLY = "apply"
MODE_APPROVE = "approve"


def entry_check(db: Session, ch: CharacterRow, faction: "models.Faction", member, s: fc.FactionSettings,
                now: datetime, *, mode: str, conditions: List[Tuple[str, dict]], irreconcilable: Set[int],
                facts: fc.Facts, refs: fc.Refs) -> Optional[FactionError]:
    """The first reason the character cannot join / apply (None = allowed). Never raises."""
    if ch.is_npc:
        return FactionError(403, MSG_NPC)
    if mode != MODE_APPROVE and not faction.is_active:
        return FactionError(404, MSG_FACTION_NOT_FOUND)
    if mode == MODE_JOIN and faction.is_invite_only:
        return FactionError(409, MSG_INVITE_ONLY)
    if mode == MODE_APPLY and not faction.is_invite_only:
        return FactionError(409, MSG_NOT_INVITE_ONLY)
    if member is not None and member.status == fc.STATUS_ACTIVE:
        return FactionError(409, MSG_ALREADY_MEMBER)
    if mode == MODE_APPLY and pending_application(db, ch.id, faction.id) is not None:
        return FactionError(409, MSG_ALREADY_APPLIED)
    if member is not None and member.rejoin_after is not None and member.rejoin_after > now:
        return FactionError(409, MSG_REJOIN_COOLDOWN.format(left=remaining_text(member.rejoin_after, now)))
    if mode == MODE_APPLY:
        rejected = last_rejection(db, ch.id, faction.id)
        if rejected is not None and rejected.decided_at is not None and s.reapply_cooldown_hours > 0:
            until = rejected.decided_at + _hours(s.reapply_cooldown_hours)
            if until > now:
                return FactionError(409, MSG_REAPPLY_COOLDOWN.format(left=remaining_text(until, now)))
    for other in sorted(irreconcilable):
        if other in facts.active_factions:
            name = refs.factions.get(int(other), (f"#{other}", False))[0]
            return FactionError(409, MSG_IRRECONCILABLE.format(name=name))
    unmet = fc.unmet_texts(fc.evaluate(conditions, facts, refs))
    if unmet:
        return FactionError(409 if mode == MODE_APPROVE else 403, f"{MSG_CONDITIONS}: " + "; ".join(unmet))
    if faction.member_limit is not None and active_count(db, faction.id) >= int(faction.member_limit):
        return FactionError(409, MSG_NO_PLACES)
    return None


def _hours(hours: int) -> timedelta:
    return timedelta(hours=int(hours))


def _entry_context(db: Session, ch: CharacterRow, faction_id: int):
    conds = load_conditions(db, [faction_id])
    irr = hostile_map(db, irreconcilable_only=True)
    own = conds.get(int(faction_id), [])
    irreconcilable = set(irr.get(int(faction_id), set()))
    refs = load_refs(db, own, extra_faction_ids=irreconcilable)
    facts = load_facts(db, ch, own, refs, with_quests=True)
    return own, irreconcilable, refs, facts


# =====================================================================================================================
# player flows
# =====================================================================================================================

def admit(db: Session, ch: CharacterRow, faction: "models.Faction", member, now: datetime, *,
          facts: fc.Facts, actor_user_id: Optional[int] = None, event_reason: Optional[str] = None) -> FlowResult:
    """Insert / reactivate the membership, walk from the entry rank, record grants, log, notify (shared by join and
    application approval). Caller has done every check."""
    if member is None:
        member = models.FactionMember(character_id=ch.id, faction_id=int(faction.id), status=fc.STATUS_ACTIVE,
                                      points=0, joined_at=now)
        db.add(member)
    else:
        member.status = fc.STATUS_ACTIVE
        member.joined_at = now
        member.left_at = None
        member.rejoin_after = None
        member.warning_at = None
        member.warning_reasons = None
        member.rank_id = None
    db.flush()
    ranks = load_ranks(db, [faction.id]).get(int(faction.id), [])
    reached, result = climb_member(db, ch, faction, member, ranks, ch.level, facts.completed_quests, now,
                                   from_entry=True)
    entry = reached[0] if reached else None
    log_event(db, character_id=ch.id, faction_id=faction.id, event_type=fc.EV_JOINED, now=now,
              points_after=int(member.points), rank_id=int(entry.id) if entry else None, reason=event_reason,
              actor_user_id=actor_user_id)
    final = reached[-1] if reached else None
    rank_name = final.name if final else None
    message = f"Вы вступили во фракцию «{faction.name}»"
    if rank_name:
        message += f". Звание: «{rank_name}»"
    join_notice = Notice(ch.user_id, message, CATEGORY_PROGRESS,
                         {"faction_id": int(faction.id), "character_id": ch.id, "event": fc.EV_JOINED})
    result.notices.insert(0, join_notice)
    db.flush()
    result.data = {"membership_id": int(member.id), "rank_name": rank_name,
                   "notices_text": [n.message for n in result.notices]}
    return result


def join(db: Session, character_id: int, faction_id: int, now: Optional[datetime] = None) -> FlowResult:
    now = now or now_utc()
    ch = require_character(db, character_id)
    faction = faction_or_404(db, faction_id, lock=True)          # FOR UPDATE: the member limit
    member = member_row(db, ch.id, faction.id, lock=True)
    own, irreconcilable, refs, facts = _entry_context(db, ch, faction.id)
    error = entry_check(db, ch, faction, member, load_settings(db), now, mode=MODE_JOIN, conditions=own,
                        irreconcilable=irreconcilable, facts=facts, refs=refs)
    if error is not None:
        raise error
    return admit(db, ch, faction, member, now, facts=facts)


def apply(db: Session, character_id: int, faction_id: int, message: Optional[str],
          now: Optional[datetime] = None) -> FlowResult:
    now = now or now_utc()
    ch = require_character(db, character_id)
    faction = faction_or_404(db, faction_id)
    member = member_row(db, ch.id, faction.id)
    own, irreconcilable, refs, facts = _entry_context(db, ch, faction.id)
    error = entry_check(db, ch, faction, member, load_settings(db), now, mode=MODE_APPLY, conditions=own,
                        irreconcilable=irreconcilable, facts=facts, refs=refs)
    if error is not None:
        raise error
    text_message = (message or "").strip() or None
    application = models.FactionApplication(character_id=ch.id, faction_id=int(faction.id), status=fc.APP_PENDING,
                                            message=text_message[:500] if text_message else None,
                                            pending_key=f"{ch.id}:{int(faction.id)}", created_at=now)
    db.add(application)
    db.flush()                                                  # UNIQUE pending_key -> 409 on a double click
    log_event(db, character_id=ch.id, faction_id=faction.id, event_type=fc.EV_APPLIED, now=now)
    return FlowResult(data={"application_id": int(application.id)})


def cancel_application(db: Session, character_id: int, application_id: int,
                       now: Optional[datetime] = None) -> FlowResult:
    now = now or now_utc()
    application = db.query(models.FactionApplication).filter(
        models.FactionApplication.id == int(application_id),
        models.FactionApplication.character_id == int(character_id)).first()
    if application is None:
        raise FactionError(404, MSG_APP_NOT_FOUND)
    updated = db.execute(text(
        "UPDATE faction_applications SET status = :c, pending_key = NULL, decided_at = :now "
        "WHERE id = :id AND status = :p"),
        {"c": fc.APP_CANCELLED, "p": fc.APP_PENDING, "now": now, "id": int(application_id)}).rowcount
    if not updated:
        raise FactionError(409, MSG_APP_NOT_PENDING)
    return FlowResult(data={"ok": True})


def depart(db: Session, member: "models.FactionMember", status: str, now: datetime, s: fc.FactionSettings, *,
           reason: Optional[str] = None, actor_user_id: Optional[int] = None) -> int:
    """Leave / expel (§3.4): burn points, cooldown, clear the warning; the rank stays in the row (history)."""
    before = int(member.points)
    member.points = fc.burn(before, s.leave_burn_pct)
    member.status = status
    member.left_at = now
    member.rejoin_after = fc.rejoin_after(now, s)
    member.warning_at = None
    member.warning_reasons = None
    log_event(db, character_id=member.character_id, faction_id=member.faction_id,
              event_type=fc.EV_EXPELLED if status == fc.STATUS_EXPELLED else fc.EV_LEFT, now=now,
              points_delta=int(member.points) - before, points_after=int(member.points), rank_id=member.rank_id,
              reason=reason, actor_user_id=actor_user_id)
    db.flush()
    return int(member.points)


def leave(db: Session, character_id: int, faction_id: int, now: Optional[datetime] = None) -> FlowResult:
    now = now or now_utc()
    require_character(db, character_id)
    faction_or_404(db, faction_id)
    member = member_row(db, character_id, faction_id, lock=True)
    if member is None or member.status != fc.STATUS_ACTIVE:
        raise FactionError(409, MSG_NOT_MEMBER)
    s = load_settings(db)
    points_after = depart(db, member, fc.STATUS_LEFT, now, s)
    return FlowResult(data={"points_after": points_after,
                            "rejoin_in_seconds": fc.remaining_seconds(member.rejoin_after, now)})


def expel_notice(ch: CharacterRow, faction: "models.Faction", reason: Optional[str]) -> Notice:
    message = f"Вас исключили из фракции «{faction.name}»"
    if reason:
        message += f": {reason}"
    return Notice(ch.user_id, message, CATEGORY_SYSTEM,
                  {"faction_id": int(faction.id), "character_id": ch.id, "event": fc.EV_EXPELLED})


# =====================================================================================================================
# points (internal quest hook)
# =====================================================================================================================

def change_points(db: Session, member: "models.FactionMember", delta: int, event_type: str, now: datetime, *,
                  event_key: Optional[str] = None, reason: Optional[str] = None,
                  actor_user_id: Optional[int] = None) -> int:
    """Apply ``delta`` clamped at 0; logs the ACTUAL change. Returns the actual delta."""
    before = int(member.points)
    member.points = fc.apply_points(before, delta)
    actual = int(member.points) - before
    log_event(db, character_id=member.character_id, faction_id=member.faction_id, event_type=event_type, now=now,
              points_delta=actual, points_after=int(member.points), rank_id=member.rank_id, event_key=event_key,
              reason=reason, actor_user_id=actor_user_id)
    return actual


def quest_completed(db: Session, character_id: int, quest_id: int, cq_id: int, rewards: Sequence[Tuple[int, int]],
                    now: Optional[datetime] = None) -> FlowResult:
    """Internal hook of quest completion (idempotent per ``cq_id``; §3.5)."""
    import crud                                               # late: crud imports this module's hook lazily too
    import faction_hooks

    now = now or now_utc()
    ch = require_character(db, character_id)
    result = FlowResult(data={"applied": [], "duplicate": False, "rank_ups": 0})

    # Quest XP from locations-service is not levelled immediately: close the gap for members first.
    with faction_hooks.collecting() as collected:
        if active_faction_ids(db, ch.id):
            try:
                row = db.execute(text("SELECT passive_experience FROM character_attributes WHERE character_id = :c"),
                                 {"c": ch.id}).first()
                if row is not None and row[0] is not None:
                    crud.check_and_update_level(db, ch.id, int(row[0]))
            except SQLAlchemyError:
                db.rollback()
                logger.warning("faction quest hook: level check of character %s failed", ch.id, exc_info=True)
    result.merge(collected)
    ch = require_character(db, character_id)                  # the level may have changed

    s = load_settings(db)
    base_key = f"faction:quest:cq:{int(cq_id)}"
    hostile = hostile_map(db)
    for faction_id, points in rewards:
        member = member_row(db, ch.id, faction_id, lock=True)
        if member is None or member.status != fc.STATUS_ACTIVE:
            continue
        if log_key_exists(db, base_key, faction_id):
            result.data["duplicate"] = True
            continue
        actual = change_points(db, member, int(points), fc.EV_POINTS, now, event_key=base_key,
                               reason=f"quest:{int(quest_id)}")
        result.data["applied"].append({"faction_id": int(faction_id), "points_delta": actual,
                                       "points_after": int(member.points)})
        if int(points) > 0:
            penalty = fc.hostile_penalty(int(points), s.hostile_penalty_pct)
            for other in sorted(hostile.get(int(faction_id), set())):
                if penalty <= 0:
                    break
                other_member = member_row(db, ch.id, other, lock=True)
                if other_member is None or other_member.status != fc.STATUS_ACTIVE:
                    continue
                key = f"{base_key}:hostile:{int(faction_id)}"
                if log_key_exists(db, key, other):
                    continue
                change_points(db, other_member, -penalty, fc.EV_HOSTILE, now, event_key=key,
                              reason=f"faction:{int(faction_id)}")
    db.flush()
    rechecked = recheck_ranks(db, ch.id, now)
    result.merge(rechecked)
    result.data["rank_ups"] = int(rechecked.data.get("rank_ups", 0))
    return result


# =====================================================================================================================
# read models (player)
# =====================================================================================================================

def _faction_public_item(faction: "models.Faction", *, conditions: List[dict], ranks: Sequence["models.FactionRank"],
                         hq_names: Dict[int, str], leaders: Dict[int, dict], counts: Dict[int, int]) -> dict:
    secret = bool(faction.is_secret)
    hq = None
    if faction.hq_location_id:
        hq = {"id": int(faction.hq_location_id), "name": hq_names.get(int(faction.hq_location_id))}
    return {
        "id": int(faction.id),
        "name": faction.name,
        "description": faction.description,
        "emblem_url": faction.emblem_url,
        "hq_location": hq,
        "leaders": [{"id": lid, "name": leaders[lid]["name"], "avatar": leaders[lid]["avatar"]}
                    for lid in (int(x) for x in faction.leader_npc_ids or []) if lid in leaders],
        "is_invite_only": bool(faction.is_invite_only),
        "is_secret": secret,
        "member_count": None if secret else int(counts.get(int(faction.id), 0)),
        "member_limit": None if secret else (int(faction.member_limit) if faction.member_limit is not None else None),
        "ranks": [{"id": int(r.id), "name": r.name, "sort_order": int(r.sort_order), "passive": _rank_passive(r)}
                  for r in ranks],
        "conditions": conditions,
    }


def _rank_passive(rank: "models.FactionRank") -> Optional[dict]:
    """FEAT-207: the rank's passive for players (None = none)."""
    mods = fc.clean_modifiers(getattr(rank, "passive_modifiers", None))
    if not mods:
        return None
    return {"name": rank.passive_name or rank.name, "description": rank.passive_description, "modifiers": mods}


def _outlaw_regions(db: Session, faction_ids: Sequence[int]) -> Dict[int, List[dict]]:
    """FEAT-207: {faction_id: [{region_id, region_name, level_name}]}; unreadable tables -> nothing (logged)."""
    import faction_territory  # late: it imports this module
    try:
        raw = faction_territory.outlaw_regions_of(db, faction_ids)
    except SQLAlchemyError:
        db.rollback()
        logger.warning("faction: outlaw regions not read", exc_info=True)
        return {}
    return {fid: [{"region_id": r["region_id"], "region_name": r["region_name"], "level_name": r["level_name"]}
                  for r in rows] for fid, rows in raw.items()}


def _active_counts(db: Session, faction_ids: Sequence[int]) -> Dict[int, int]:
    if not faction_ids:
        return {}
    rows = (db.query(models.FactionMember.faction_id, func.count(models.FactionMember.id))
            .filter(models.FactionMember.faction_id.in_(list(faction_ids)),
                    models.FactionMember.status == fc.STATUS_ACTIVE)
            .group_by(models.FactionMember.faction_id).all())
    return {int(r[0]): int(r[1]) for r in rows}


def _catalog_items(db: Session, factions: Sequence["models.Faction"], ch: Optional[CharacterRow],
                   now: datetime) -> List[dict]:
    ids = [int(f.id) for f in factions]
    conds = load_conditions(db, ids)
    irr = hostile_map(db, irreconcilable_only=True)
    all_conditions = {fid: entry_conditions(fid, conds, irr) for fid in ids}
    flat = [c for lst in all_conditions.values() for c in lst]
    refs = load_refs(db, flat)
    facts = load_facts(db, ch, flat, refs, with_quests=True) if ch is not None else None
    ranks = load_ranks(db, ids)
    hq_names = location_names(db, [f.hq_location_id for f in factions])
    leaders = character_brief(db, [int(x) for f in factions for x in (f.leader_npc_ids or [])])
    counts = _active_counts(db, ids)
    s = load_settings(db) if ch is not None else None
    import faction_econ_crud  # late: it imports this module
    words = faction_econ_crud.wealth_words(db, ids)
    outlaw = _outlaw_regions(db, ids)                          # FEAT-207: not membership data
    mine = facts.active_factions if facts is not None else set()
    out = []
    for faction in factions:
        fid = int(faction.id)
        item = _faction_public_item(faction, conditions=fc.evaluate(all_conditions[fid], facts, refs),
                                    ranks=ranks.get(fid, []), hq_names=hq_names, leaders=leaders, counts=counts)
        item["outlaw_regions"] = outlaw.get(fid, [])
        # FEAT-206 §3.9: wealth words only; a secret faction's wealth only for its active members
        item["wealth"] = words.get(fid) if (not faction.is_secret or fid in mine) else None
        if ch is not None:
            item.update(_my_state(db, ch, faction, s, now, conds.get(fid, []), set(irr.get(fid, set())), facts, refs,
                                  ranks.get(fid, [])))
        out.append(item)
    return out


def _my_state(db: Session, ch: CharacterRow, faction: "models.Faction", s: fc.FactionSettings, now: datetime,
              own: List[Tuple[str, dict]], irreconcilable: Set[int], facts: fc.Facts, refs: fc.Refs,
              ranks: Sequence["models.FactionRank"]) -> dict:
    member = member_row(db, ch.id, faction.id)
    pending = pending_application(db, ch.id, faction.id)
    rank_names = {int(r.id): r.name for r in ranks}
    status = "none"
    if member is not None:
        status = member.status
    if pending is not None and status != fc.STATUS_ACTIVE:
        status = fc.APP_PENDING
    reapply_in = None
    rejected = last_rejection(db, ch.id, faction.id)
    if rejected is not None and rejected.decided_at is not None and s.reapply_cooldown_hours > 0:
        reapply_in = fc.remaining_seconds(rejected.decided_at + _hours(s.reapply_cooldown_hours), now) or None
    my = {
        "status": status,
        "rank_name": rank_names.get(int(member.rank_id)) if member is not None and member.rank_id else None,
        "rejoin_in_seconds": (fc.remaining_seconds(member.rejoin_after, now) or None)
        if member is not None and member.status != fc.STATUS_ACTIVE and member.rejoin_after else None,
        "application_id": int(pending.id) if pending is not None else None,
        "reapply_in_seconds": reapply_in,
    }
    if pending is not None:
        return {"my": my, "can_join": False, "join_block_reason": MSG_PENDING_BLOCK}
    mode = MODE_APPLY if faction.is_invite_only else MODE_JOIN
    error = entry_check(db, ch, faction, member, s, now, mode=mode, conditions=own, irreconcilable=irreconcilable,
                        facts=facts, refs=refs)
    return {"my": my, "can_join": error is None, "join_block_reason": error.detail if error is not None else None}


def catalog(db: Session, character_id: Optional[int], now: Optional[datetime] = None) -> List[dict]:
    """``GET /characters/factions/catalog``: active factions; ``my`` / ``met`` / ``can_join`` with a character."""
    now = now or now_utc()
    ch = require_character(db, character_id) if character_id is not None else None
    factions = (db.query(models.Faction).filter(models.Faction.is_active.is_(True))
                .order_by(models.Faction.sort_order, models.Faction.id).all())
    items = _catalog_items(db, factions, ch, now)
    if ch is None:
        for item in items:
            item.update({"my": None, "can_join": False, "join_block_reason": None})
    return items


def faction_public(db: Session, faction_id: int) -> dict:
    faction = faction_or_404(db, faction_id)
    if not faction.is_active:
        raise FactionError(404, MSG_FACTION_NOT_FOUND)
    item = _catalog_items(db, [faction], None, now_utc())[0]
    for cond in item["conditions"]:
        cond.pop("met", None)
    return item


def _title_names(db: Session, title_ids: Iterable[int]) -> Dict[int, str]:
    ids = sorted({int(t) for t in title_ids if t})
    if not ids:
        return {}
    return {int(t.id_title): t.name for t in db.query(models.Title).filter(models.Title.id_title.in_(ids)).all()}


def private_view(db: Session, character_id: int, now: Optional[datetime] = None) -> dict:
    """``GET /characters/{cid}/factions`` (owner / staff): memberships (active first) + applications."""
    now = now or now_utc()
    ch = require_character(db, character_id)
    s = load_settings(db)
    members = db.query(models.FactionMember).filter(models.FactionMember.character_id == ch.id).all()
    fids = sorted({int(m.faction_id) for m in members})
    factions = {int(f.id): f for f in db.query(models.Faction).filter(models.Faction.id.in_(fids)).all()} \
        if fids else {}
    ranks = load_ranks(db, fids)
    rank_by_id = {int(r.id): r for lst in ranks.values() for r in lst}
    titles = _title_names(db, [r.reward_title_id for r in rank_by_id.values()])
    quests = quest_titles(db, [r.required_quest_id for r in rank_by_id.values()])
    completed = completed_quests(db, ch.id) if any(m.status == fc.STATUS_ACTIVE for m in members) else set()

    def sort_key(m):
        return (0 if m.status == fc.STATUS_ACTIVE else 1, -(m.joined_at.timestamp() if m.joined_at else 0), m.id)

    out = []
    for member in sorted(members, key=sort_key):
        faction = factions.get(int(member.faction_id))
        if faction is None:
            continue
        rank = rank_by_id.get(int(member.rank_id)) if member.rank_id else None
        entry = {
            "membership_id": int(member.id),
            "faction": {"id": int(faction.id), "name": faction.name, "emblem_url": faction.emblem_url,
                        "is_secret": bool(faction.is_secret)},
            "status": member.status,
            "points": int(member.points),
            "rank": {"id": int(rank.id), "name": rank.name} if rank else None,
            "rank_title": ({"id": int(rank.reward_title_id), "name": titles.get(int(rank.reward_title_id))}
                           if rank and rank.reward_title_id and int(rank.reward_title_id) in titles else None),
            "next_rank": None,
            "warning": None,
            "joined_at": member.joined_at,
            "rejoin_in_seconds": None,
        }
        if member.status == fc.STATUS_ACTIVE:
            nxt = fc.next_rank(rank_defs(ranks.get(int(faction.id), [])), member.rank_id)
            if nxt is not None:
                entry["next_rank"] = {"id": nxt.id, "name": nxt.name,
                                      "conditions": fc.rank_requirements(nxt, int(member.points), ch.level,
                                                                         completed, quests)}
            if member.warning_at is not None:
                entry["warning"] = {"reasons": list(member.warning_reasons or []),
                                    "remaining_seconds": fc.remaining_seconds(
                                        fc.warning_deadline(member.warning_at, s), now)}
        elif member.rejoin_after is not None:
            entry["rejoin_in_seconds"] = fc.remaining_seconds(member.rejoin_after, now)
        out.append(entry)

    import faction_econ_crud  # late: it imports this module
    faction_econ_crud.member_extras(db, ch.id, out, now)       # FEAT-206: wealth / debt / donation info

    # FEAT-207: passives (cumulative up to the held rank) + outlaw regions of active memberships
    import faction_kills  # late: it imports this module
    active_fids = [e["faction"]["id"] for e in out if e["status"] == fc.STATUS_ACTIVE]
    outlaw = _outlaw_regions(db, active_fids)
    held = {int(m.faction_id): m.rank_id for m in members}
    passive_groups = []
    for entry in out:
        fid = int(entry["faction"]["id"])
        if entry["status"] != fc.STATUS_ACTIVE:
            entry["passives"] = []
            entry["outlaw_regions"] = []
            continue
        entry["passives"] = faction_kills.member_passives(ranks.get(fid, []), held.get(fid))
        entry["outlaw_regions"] = outlaw.get(fid, [])
        passive_groups.extend(p["modifiers"] for p in entry["passives"])

    apps = (db.query(models.FactionApplication)
            .filter(models.FactionApplication.character_id == ch.id,
                    models.FactionApplication.status != fc.APP_CANCELLED)
            .order_by(models.FactionApplication.id.desc()).limit(20).all())
    app_fids = sorted({int(a.faction_id) for a in apps} - set(factions))
    if app_fids:
        factions.update({int(f.id): f for f in
                         db.query(models.Faction).filter(models.Faction.id.in_(app_fids)).all()})
    apps = sorted(apps, key=lambda a: (0 if a.status == fc.APP_PENDING else 1, -int(a.id)))
    applications = [{"id": int(a.id), "faction_id": int(a.faction_id),
                     "faction_name": factions[int(a.faction_id)].name if int(a.faction_id) in factions else None,
                     "status": a.status, "created_at": a.created_at, "reject_reason": a.reject_reason}
                    for a in apps]
    return {"memberships": out, "applications": applications, "settings": {
        "rejoin_cooldown_days": s.rejoin_cooldown_days, "leave_burn_pct": s.leave_burn_pct,
        "warning_days": s.warning_days}, "passive_total": fc.sum_modifiers(passive_groups)}


def history_text(row: "models.FactionLog", faction_name: str, rank_name: Optional[str],
                 other_names: Dict[int, str]) -> str:
    f = f"«{faction_name}»"
    delta = int(row.points_delta or 0)
    signed = f"+{delta}" if delta > 0 else (f"−{abs(delta)}" if delta < 0 else "0")
    t = row.event_type
    if t == fc.EV_JOINED:
        return f"Вступление во фракцию {f}" + (f", звание «{rank_name}»" if rank_name else "")
    if t == fc.EV_LEFT:
        return f"Выход из фракции {f}" + (f" (сгорело очков: {abs(delta)})" if delta else "")
    if t == fc.EV_EXPELLED:
        text_ = f"Исключение из фракции {f}"
        if row.reason:
            text_ += f": {row.reason}"
        return text_ + (f" (сгорело очков: {abs(delta)})" if delta else "")
    if t == fc.EV_RANK_UP:
        return f"Новое звание во фракции {f}: «{rank_name or '—'}»"
    if t == fc.EV_POINTS:
        return f"Очки фракции {f}: {signed} за задание"
    if t == fc.EV_HOSTILE:
        other = None
        if row.reason and row.reason.startswith("faction:"):
            try:
                other = other_names.get(int(row.reason.split(":", 1)[1]))
            except ValueError:
                other = None
        return f"Очки фракции {f}: {signed} — помощь враждебной фракции" + (f" «{other}»" if other else "")
    if t == fc.EV_ADMIN_POINTS:
        return f"Очки фракции {f}: {signed}" + (f" ({row.reason})" if row.reason else "")
    if t == fc.EV_DONATION and row.reason and row.reason.startswith("items:"):     # FEAT-207 «items:<n>:<value>»
        try:
            _tag, count, value = row.reason.split(":", 2)
            text_ = f"Пожертвование предметов фракции {f} ({int(count)} шт.) на {core.format_currency(int(value))}"
        except ValueError:
            text_ = f"Пожертвование предметов фракции {f}"
        return text_ + (f", {signed} очков" if delta > 0 else "")
    if t == fc.EV_DONATION:
        marks = None
        if row.reason and row.reason.startswith("marks:"):
            try:
                marks = int(row.reason.split(":", 1)[1])
            except ValueError:
                marks = None
        what = f"Пожертвование фракции {f}" + (f": {core.format_currency(marks)}" if marks is not None else "")
        return what + (f", {signed} очков" if delta > 0 else "")
    if t == fc.EV_KILL:                                     # FEAT-207: victims are never named
        if delta > 0:
            return f"Победа над врагами фракции {f}: {signed} очков"
        return f"Победа над врагами фракции {f}: очков нет — лимит на сегодня исчерпан"
    if t in (fc.EV_CARAVAN_ESCORT, fc.EV_CARAVAN_RAID):    # FEAT-212: caravan deeds
        what = "Охрана каравана" if t == fc.EV_CARAVAN_ESCORT else "Налёт на караван"
        if delta > 0:
            return f"{what} — дело фракции {f}: {signed} очков"
        return f"{what} — дело фракции {f}: очков нет — лимит на сегодня исчерпан"
    if t == fc.EV_EJECTED:
        return f"Выдворение с территории фракции {f}"
    if t == fc.EV_WARNING:
        return f"Предупреждение во фракции {f}: вы перестали соответствовать условиям вступления"
    if t == fc.EV_WARNING_CLEARED:
        return f"Предупреждение во фракции {f} снято"
    if t == fc.EV_APPLIED:
        return f"Подана заявка во фракцию {f}"
    if t == fc.EV_APP_APPROVED:
        return f"Заявка во фракцию {f} одобрена"
    if t == fc.EV_APP_REJECTED:
        return f"Заявка во фракцию {f} отклонена" + (f": {row.reason}" if row.reason else "")
    return f"Событие во фракции {f}"


def history(db: Session, character_id: int, page: int, page_size: int, *, include_hidden: bool = False) -> dict:
    require_character(db, character_id)
    query = db.query(models.FactionLog).filter(models.FactionLog.character_id == int(character_id))
    if not include_hidden:
        query = query.filter(models.FactionLog.event_type.notin_(fc.PLAYER_HIDDEN_EVENTS))
    total = query.count()
    rows = query.order_by(models.FactionLog.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    fids = {int(r.faction_id) for r in rows}
    for r in rows:
        if r.event_type == fc.EV_HOSTILE and r.reason and r.reason.startswith("faction:"):
            try:
                fids.add(int(r.reason.split(":", 1)[1]))
            except ValueError:
                pass
    names = {int(f.id): f.name for f in db.query(models.Faction).filter(models.Faction.id.in_(sorted(fids))).all()} \
        if fids else {}
    rank_ids = sorted({int(r.rank_id) for r in rows if r.rank_id})
    rank_names = {int(r.id): r.name for r in db.query(models.FactionRank).filter(
        models.FactionRank.id.in_(rank_ids)).all()} if rank_ids else {}
    items = []
    for row in rows:
        items.append({
            "id": int(row.id),
            "faction_id": int(row.faction_id),
            "faction_name": names.get(int(row.faction_id)),
            "event_type": row.event_type,
            "text": history_text(row, names.get(int(row.faction_id), "—"),
                                 rank_names.get(int(row.rank_id)) if row.rank_id else None, names),
            "points_delta": row.points_delta,
            "points_after": row.points_after,
            "created_at": row.created_at,
        })
    return {"items": items, "total": int(total), "page": page, "page_size": page_size}


def public_memberships(db: Session, character_id: int) -> List[dict]:
    """``GET /characters/{cid}/factions/public``: active memberships of NON-secret factions only."""
    require_character(db, character_id)
    rows = (db.query(models.FactionMember, models.Faction)
            .join(models.Faction, models.Faction.id == models.FactionMember.faction_id)
            .filter(models.FactionMember.character_id == int(character_id),
                    models.FactionMember.status == fc.STATUS_ACTIVE,
                    models.Faction.is_secret.is_(False))
            .order_by(models.Faction.sort_order, models.Faction.id).all())
    rank_ids = sorted({int(m.rank_id) for m, _f in rows if m.rank_id})
    rank_names = {int(r.id): r.name for r in db.query(models.FactionRank).filter(
        models.FactionRank.id.in_(rank_ids)).all()} if rank_ids else {}
    return [{"faction_id": int(f.id), "name": f.name, "emblem_url": f.emblem_url,
             "rank_name": rank_names.get(int(m.rank_id)) if m.rank_id else None} for m, f in rows]
