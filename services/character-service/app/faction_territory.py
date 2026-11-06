"""FEAT-207 factions stage 3 — closed territories (locations / dungeons), eject, outlaw membership reads.
features/FEAT-207 §3.4, §3.7. Sync SQLAlchemy (the eject itself is async: it calls locations-service through
``main._prepare_move``).

* one rule per target in ``faction_access_rules`` (kind location | dungeon); the decision is
  :func:`faction_core.access_decision` (a hidden faction opens its territories; a secret faction is never named to a
  non-member);
* the authoritative location gate (:func:`location_refusal`) is called by ``update_location`` and the teleport
  master; forced moves (admin, jail, home scroll, dungeon return) are never gated — the eject sweep moves the player
  out afterwards;
* the eject (:func:`eject`) picks the first open neighbour (ascending id), else the faction HQ, else the region guard
  station; it skips characters in battle / a dungeon run / under any activity lock (retried by the 5-min faction pass).
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

import activity_lock
import faction_core as fc
import faction_crud as fcr
import faction_notify
import models
from faction_crud import FactionError
from faction_notify import CATEGORY_SYSTEM, Notice

logger = logging.getLogger("character-service.faction_territory")

MAX_CHECK_CHARACTERS = 20
MAX_LABEL_TARGETS = 200
EJECT_BATCH = 200

MSG_KIND = "Неизвестный тип территории"
MSG_LOCATION_NOT_FOUND = "Локация не найдена"
MSG_DUNGEON_NOT_FOUND = "Подземелье не найдено"
MSG_RANK_OTHER_FACTION = "Звание должно принадлежать выбранной фракции"
MSG_EJECT_REASON = "Выдворен с закрытой территории"


# =====================================================================================================================
# reads
# =====================================================================================================================

def _check_kind(kind: str) -> str:
    if kind not in fc.ACCESS_KINDS:
        raise FactionError(422, MSG_KIND)
    return kind


def rules_for(db: Session, kind: str, target_ids: Iterable[int]) -> Dict[int, "models.FactionAccessRule"]:
    ids = sorted({int(t) for t in target_ids if t})
    if not ids:
        return {}
    rows = (db.query(models.FactionAccessRule)
            .filter(models.FactionAccessRule.kind == kind, models.FactionAccessRule.target_id.in_(ids)).all())
    return {int(r.target_id): r for r in rows}


def _factions(db: Session, faction_ids: Iterable[int]) -> Dict[int, fc.AccessFaction]:
    ids = sorted({int(f) for f in faction_ids})
    if not ids:
        return {}
    rows = db.query(models.Faction).filter(models.Faction.id.in_(ids)).all()
    return {int(f.id): fc.AccessFaction(int(f.id), f.name, bool(f.is_secret), bool(f.is_active)) for f in rows}


def _ranks(db: Session, rank_ids: Iterable[int]) -> Dict[int, fc.AccessRank]:
    ids = sorted({int(r) for r in rank_ids if r})
    if not ids:
        return {}
    rows = db.query(models.FactionRank).filter(models.FactionRank.id.in_(ids)).all()
    return {int(r.id): fc.AccessRank(int(r.id), r.name, int(r.sort_order)) for r in rows}


def _memberships(db: Session, character_ids: Sequence[int],
                 faction_ids: Sequence[int]) -> Dict[Tuple[int, int], Optional[int]]:
    """(character, faction) -> held rank sort_order (None = no rank) for ACTIVE memberships only."""
    cids = sorted({int(c) for c in character_ids})
    fids = sorted({int(f) for f in faction_ids})
    if not cids or not fids:
        return {}
    cph, cparams = fcr.in_clause("c", cids)
    fph, fparams = fcr.in_clause("f", fids)
    rows = db.execute(text(
        f"SELECT m.character_id, m.faction_id, r.sort_order FROM faction_members m "
        f"LEFT JOIN faction_ranks r ON r.id = m.rank_id "
        f"WHERE m.status = :s AND m.character_id IN ({cph}) AND m.faction_id IN ({fph})"),
        {"s": fc.STATUS_ACTIVE, **cparams, **fparams}).fetchall()
    return {(int(r[0]), int(r[1])): (int(r[2]) if r[2] is not None else None) for r in rows}


@dataclass
class _Context:
    rules: Dict[int, "models.FactionAccessRule"]
    factions: Dict[int, fc.AccessFaction]
    ranks: Dict[int, fc.AccessRank]
    members: Dict[Tuple[int, int], Optional[int]]

    def decide(self, target_id: int, character_id: Optional[int]) -> fc.AccessDecision:
        rule = self.rules.get(int(target_id))
        if rule is None:
            return fc.OPEN_DECISION
        faction = self.factions.get(int(rule.faction_id))
        rank = self.ranks.get(int(rule.min_rank_id)) if rule.min_rank_id else None
        if character_id is None:
            return fc.access_decision(faction, rank, viewer_known=False)
        key = (int(character_id), int(rule.faction_id))
        return fc.access_decision(faction, rank, viewer_known=True, is_member=key in self.members,
                                  member_rank_order=self.members.get(key))


def _context(db: Session, kind: str, target_ids: Iterable[int], character_ids: Sequence[int] = ()) -> _Context:
    rules = rules_for(db, kind, target_ids)
    if not rules:
        return _Context({}, {}, {}, {})
    fids = [int(r.faction_id) for r in rules.values()]
    return _Context(rules, _factions(db, fids), _ranks(db, [r.min_rank_id for r in rules.values()]),
                    _memberships(db, character_ids, fids) if character_ids else {})


def decision(db: Session, kind: str, target_id: int, character_id: Optional[int]) -> fc.AccessDecision:
    ctx = _context(db, kind, [target_id], [character_id] if character_id else ())
    return ctx.decide(int(target_id), character_id)


def location_refusal(db: Session, character, location_id) -> Optional[str]:
    """The authoritative gate of a player move (None = may enter). NPCs are never gated."""
    if character is None or bool(getattr(character, "is_npc", False)) or not location_id:
        return None
    d = decision(db, fc.ACCESS_LOCATION, int(location_id), int(character.id))
    return d.refusal if d.allowed is False else None


# =====================================================================================================================
# internal API (dungeon-service)
# =====================================================================================================================

def access_check(db: Session, kind: str, target_id: int, character_ids: Sequence[int]) -> dict:
    """``POST /internal/factions/access/check``: the whole group must pass (§3.4). NPCs always pass."""
    _check_kind(kind)
    ids = list(dict.fromkeys(int(c) for c in character_ids))[:MAX_CHECK_CHARACTERS]
    ctx = _context(db, kind, [target_id], ids)
    rule = ctx.rules.get(int(target_id))
    faction = ctx.factions.get(int(rule.faction_id)) if rule is not None else None
    if rule is None or faction is None or not faction.is_active:
        return {"rule": False, "allowed": True, "failed_character_ids": [], "detail": None}
    brief = fcr.character_brief(db, ids)
    npc_ids = _npc_ids(db, ids)
    failed = [cid for cid in ids if cid not in npc_ids and ctx.decide(int(target_id), cid).allowed is False]
    if not failed:
        return {"rule": True, "allowed": True, "failed_character_ids": [], "detail": None}
    rank = ctx.ranks.get(int(rule.min_rank_id)) if rule.min_rank_id else None
    party = len(ids) > 1
    if kind == fc.ACCESS_DUNGEON:
        detail = fc.dungeon_refusal(faction, rank, [brief.get(c, {}).get("name") or f"#{c}" for c in failed],
                                    party=party)
    else:
        detail = ctx.decide(int(target_id), failed[0]).refusal
    return {"rule": True, "allowed": False, "failed_character_ids": failed, "detail": detail}


def _npc_ids(db: Session, ids: Sequence[int]) -> set:
    if not ids:
        return set()
    ph, params = fcr.in_clause("c", list(ids))
    rows = db.execute(text(f"SELECT id FROM characters WHERE is_npc = 1 AND id IN ({ph})"), params).fetchall()
    return {int(r[0]) for r in rows}


def viewer_character(db: Session, character_id: Optional[int], user_id: Optional[int]) -> Optional[int]:
    """The character id only when it belongs to ``user_id`` (else None = public labels)."""
    if not character_id or not user_id:
        return None
    row = db.execute(text("SELECT user_id FROM characters WHERE id = :c"), {"c": int(character_id)}).first()
    if row is None or row[0] is None or int(row[0]) != int(user_id):
        return None
    return int(character_id)


def access_labels(db: Session, kind: str, target_ids: Sequence[int], character_id: Optional[int],
                  user_id: Optional[int]) -> dict:
    """``POST /internal/factions/access/labels``: only targets with an effective rule are returned."""
    _check_kind(kind)
    targets = list(dict.fromkeys(int(t) for t in target_ids))[:MAX_LABEL_TARGETS]
    viewer = viewer_character(db, character_id, user_id)
    ctx = _context(db, kind, targets, [viewer] if viewer else ())
    items = []
    for tid in targets:
        d = ctx.decide(tid, viewer)
        if not d.rule:
            continue
        items.append({"target_id": tid, "access_label": d.label, "access_allowed": d.allowed})
    return {"items": items}


# =====================================================================================================================
# admin
# =====================================================================================================================

def _target_exists(db: Session, kind: str, target_id: int) -> bool:
    table = "Locations" if kind == fc.ACCESS_LOCATION else "dungeons"
    return db.execute(text(f"SELECT 1 FROM {table} WHERE id = :t"), {"t": int(target_id)}).first() is not None


def _target_names(db: Session, kind: str, ids: Iterable[int]) -> Dict[int, str]:
    ids = sorted({int(i) for i in ids})
    if not ids:
        return {}
    table = "Locations" if kind == fc.ACCESS_LOCATION else "dungeons"
    ph, params = fcr.in_clause("t", ids)
    try:
        rows = db.execute(text(f"SELECT id, name FROM {table} WHERE id IN ({ph})"), params).fetchall()
    except Exception:                                    # pragma: no cover - a missing table of another service
        db.rollback()
        logger.warning("faction territory: %s names not read", table, exc_info=True)
        return {}
    return {int(r[0]): r[1] for r in rows}


def _rule_out(db: Session, rule: Optional["models.FactionAccessRule"]) -> dict:
    if rule is None:
        return {"rule": None}
    faction = db.get(models.Faction, int(rule.faction_id))
    rank = db.get(models.FactionRank, int(rule.min_rank_id)) if rule.min_rank_id else None
    return {"rule": {"faction_id": int(rule.faction_id), "faction_name": faction.name if faction else None,
                     "min_rank_id": int(rule.min_rank_id) if rule.min_rank_id else None,
                     "min_rank_name": rank.name if rank else None}}


def get_rule(db: Session, kind: str, target_id: int) -> dict:
    _check_kind(kind)
    return _rule_out(db, rules_for(db, kind, [target_id]).get(int(target_id)))


def put_rule(db: Session, kind: str, target_id: int, body, now: Optional[datetime] = None) -> dict:
    now = now or fcr.now_utc()
    _check_kind(kind)
    if not _target_exists(db, kind, target_id):
        raise FactionError(404, MSG_LOCATION_NOT_FOUND if kind == fc.ACCESS_LOCATION else MSG_DUNGEON_NOT_FOUND)
    faction = db.get(models.Faction, int(body.faction_id))
    if faction is None:
        raise FactionError(422, fcr.MSG_FACTION_NOT_FOUND)
    rank_id = int(body.min_rank_id) if body.min_rank_id else None
    if rank_id is not None:
        rank = db.get(models.FactionRank, rank_id)
        if rank is None or int(rank.faction_id) != int(faction.id):
            raise FactionError(422, MSG_RANK_OTHER_FACTION)
    rule = rules_for(db, kind, [target_id]).get(int(target_id))
    if rule is None:
        rule = models.FactionAccessRule(kind=kind, target_id=int(target_id), faction_id=int(faction.id),
                                        min_rank_id=rank_id, created_at=now, updated_at=now)
        db.add(rule)
    else:
        rule.faction_id, rule.min_rank_id, rule.updated_at = int(faction.id), rank_id, now
    db.flush()
    return _rule_out(db, rule)


def delete_rule(db: Session, kind: str, target_id: int) -> dict:
    _check_kind(kind)
    db.query(models.FactionAccessRule).filter(models.FactionAccessRule.kind == kind,
                                              models.FactionAccessRule.target_id == int(target_id)).delete(
        synchronize_session=False)
    db.flush()
    return {"ok": True}


def faction_territory(db: Session, faction_id: int) -> List[dict]:
    faction = fcr.faction_or_404(db, faction_id)
    rules = (db.query(models.FactionAccessRule).filter(models.FactionAccessRule.faction_id == int(faction.id))
             .order_by(models.FactionAccessRule.kind, models.FactionAccessRule.target_id).all())
    names = {kind: _target_names(db, kind, [r.target_id for r in rules if r.kind == kind]) for kind in fc.ACCESS_KINDS}
    ranks = _ranks(db, [r.min_rank_id for r in rules])
    out = []
    for r in rules:
        rank = ranks.get(int(r.min_rank_id)) if r.min_rank_id else None
        out.append({"kind": r.kind, "target_id": int(r.target_id),
                    "target_name": names.get(r.kind, {}).get(int(r.target_id)),
                    "min_rank": {"id": rank.id, "name": rank.name} if rank else None})
    return out


# =====================================================================================================================
# outlaw membership (law_crud._check hook, §3.7)
# =====================================================================================================================

@dataclass(frozen=True)
class OutlawMembership:
    level_code: str
    open: bool                     # True = a non-secret faction (recognised without a roll)


def outlaw_membership(db: Session, character_id: int, region_id: Optional[int],
                      level_order: Optional[Dict[str, int]] = None) -> Optional[OutlawMembership]:
    """The character's ACTIVE memberships of factions outlawed in ``region_id``; an open (non-secret) one wins over
    secret ones; among them the most severe level. Hidden factions count too (members keep working, 205 §3.0 #6)."""
    if not region_id:
        return None
    rows = db.execute(text(
        "SELECT o.level_code, f.is_secret FROM faction_members m "
        "JOIN faction_outlaw_regions o ON o.faction_id = m.faction_id "
        "JOIN factions f ON f.id = m.faction_id "
        "WHERE m.character_id = :c AND m.status = :s AND o.region_id = :r"),
        {"c": int(character_id), "s": fc.STATUS_ACTIVE, "r": int(region_id)}).fetchall()
    if not rows:
        return None
    order = level_order or {}

    def severity(code):
        return order.get(code, 0)

    open_rows = [r[0] for r in rows if not bool(r[1])]
    pool = open_rows or [r[0] for r in rows]
    best = max(pool, key=severity)
    return OutlawMembership(level_code=str(best), open=bool(open_rows))


def membership_crime_recent(db: Session, character_id: int, region_id: int, now: datetime, hours: int,
                            crime_type: str) -> bool:
    cutoff = now - timedelta(hours=max(1, int(hours)))
    return db.execute(text(
        "SELECT 1 FROM law_crimes WHERE character_id = :c AND region_id = :r AND crime_type = :t "
        "AND created_at > :cut LIMIT 1"),
        {"c": int(character_id), "r": int(region_id), "t": crime_type, "cut": cutoff}).first() is not None


def outlaw_regions_of(db: Session, faction_ids: Iterable[int]) -> Dict[int, List[dict]]:
    """faction id -> [{region_id, region_name, level_code, level_name}] (outlaw regions are not membership data)."""
    ids = sorted({int(f) for f in faction_ids})
    out: Dict[int, List[dict]] = {fid: [] for fid in ids}
    if not ids:
        return out
    rows = (db.query(models.FactionOutlawRegion).filter(models.FactionOutlawRegion.faction_id.in_(ids))
            .order_by(models.FactionOutlawRegion.faction_id, models.FactionOutlawRegion.region_id).all())
    if not rows:
        return out
    region_ids = sorted({int(r.region_id) for r in rows})
    ph, params = fcr.in_clause("r", region_ids)
    regions = {int(r[0]): r[1] for r in db.execute(text(f"SELECT id, name FROM Regions WHERE id IN ({ph})"),
                                                   params).fetchall()}
    levels = _level_names(db)
    for r in rows:
        out[int(r.faction_id)].append({"region_id": int(r.region_id), "region_name": regions.get(int(r.region_id)),
                                       "level_code": r.level_code, "level_name": levels.get(r.level_code)})
    return out


def _level_names(db: Session) -> Dict[str, str]:
    import law_crud  # local: law_crud imports this module lazily
    return {lv.code: lv.name for lv in law_crud.load_levels(db)}


# =====================================================================================================================
# eject
# =====================================================================================================================

def players_in_closed(db: Session, location_id: Optional[int] = None, limit: int = EJECT_BATCH) -> List[int]:
    """Player characters standing in a closed location they may not stand in (checked in Python)."""
    sql = ("SELECT c.id, c.current_location_id FROM characters c "
           "JOIN faction_access_rules r ON r.kind = :k AND r.target_id = c.current_location_id "
           "JOIN factions f ON f.id = r.faction_id AND f.is_active = 1 "
           "WHERE c.is_npc = 0")
    params = {"k": fc.ACCESS_LOCATION, "n": int(limit), "after": 0}
    if location_id is not None:
        sql += " AND c.current_location_id = :l"
        params["l"] = int(location_id)
    sql += " AND c.id > :after ORDER BY c.id LIMIT :n"
    out: List[int] = []
    # Keyset pages: allowed members standing in closed locations must not hide the refused ones behind the limit.
    while len(out) < limit:
        rows = db.execute(text(sql), params).fetchall()
        if not rows:
            break
        by_location: Dict[int, List[int]] = {}
        for cid, loc in rows:
            by_location.setdefault(int(loc), []).append(int(cid))
        for loc, cids in by_location.items():
            ctx = _context(db, fc.ACCESS_LOCATION, [loc], cids)
            out.extend(cid for cid in cids if ctx.decide(loc, cid).allowed is False)
        params["after"] = int(rows[-1][0])
        if len(rows) < limit:
            break
    return sorted(out)[:limit]


def pick_target(db: Session, character_id: int, location_id: int) -> Optional[int]:
    """(1) open neighbours (ascending id), (2) the rule faction's HQ, (3) the region guard station; None = nowhere."""
    import law_facility
    import patrol_crud
    import reputation_crud
    for neighbour in patrol_crud.neighbours_of(db, location_id):
        if decision(db, fc.ACCESS_LOCATION, neighbour, character_id).allowed is not False:
            return int(neighbour)
    rule = rules_for(db, fc.ACCESS_LOCATION, [location_id]).get(int(location_id))
    if rule is not None:
        faction = db.get(models.Faction, int(rule.faction_id))
        hq = int(faction.hq_location_id) if faction is not None and faction.hq_location_id else None
        if hq and hq != int(location_id) and decision(db, fc.ACCESS_LOCATION, hq, character_id).allowed is not False:
            return hq
    station = law_facility.station_location(db, reputation_crud.location_region(db, location_id))
    if station and int(station) != int(location_id) and \
            decision(db, fc.ACCESS_LOCATION, station, character_id).allowed is not False:
        return int(station)
    return None


def _main():
    import main  # late: main includes the faction router, a top-level import would be circular
    return main


def _busy(db: Session, character: "models.Character") -> bool:
    if activity_lock.lock_for_character(character).get("locked"):
        return True
    main = _main()
    return main._is_in_battle(db, character.id) or main._is_in_dungeon_run(db, character.id)


async def eject(db: Session, character_id: int, now: Optional[datetime] = None) -> List[Notice]:
    """Move one player out of a closed location he may not stand in (§3.4). Returns the notices (publish them after
    this call); [] when nothing to do / skipped (busy, nowhere to go — retried by the faction pass)."""
    import crud
    character = db.query(models.Character).filter(models.Character.id == int(character_id)).first()
    if character is None or bool(character.is_npc) or not character.current_location_id:
        db.rollback()
        return []
    from_location = int(character.current_location_id)
    d = decision(db, fc.ACCESS_LOCATION, from_location, character.id)
    if d.allowed is not False:
        db.rollback()
        return []
    if _busy(db, character):
        db.rollback()
        return []
    target = pick_target(db, character.id, from_location)
    if target is None:
        logger.warning("faction eject: no open location around %s for character %s", from_location, character.id)
        db.rollback()
        return []
    rule = rules_for(db, fc.ACCESS_LOCATION, [from_location]).get(from_location)
    faction = db.get(models.Faction, int(rule.faction_id)) if rule is not None else None
    member = fcr.member_row(db, character.id, faction.id) if faction is not None else None
    from_name = crud._get_location_name(db, from_location)
    to_name = crud._get_location_name(db, target)
    user_id = character.user_id
    db.rollback()                                   # nothing held across the HTTP calls
    try:
        gathering_cancelled = await _main()._prepare_move(db, int(character_id), from_location, "faction")
    except HTTPException as exc:
        logger.info("faction eject of character %s postponed: %s", character_id, exc.detail)
        db.rollback()
        return []
    try:
        locked = (db.query(models.Character).filter(models.Character.id == int(character_id))
                  .with_for_update().populate_existing().first())
        if locked is None or int(locked.current_location_id or 0) != from_location:
            db.rollback()
            return []
        d = decision(db, fc.ACCESS_LOCATION, from_location, int(character_id))
        if d.allowed is not False:
            db.rollback()
            return []
        now = now or fcr.now_utc()
        crud.apply_admin_move(
            db, character_id=int(character_id), from_location_id=from_location, from_location_name=from_name,
            to_location_id=target, to_location_name=to_name, gathering_cancelled=gathering_cancelled,
            event_type="faction_eject",
            description=f"{MSG_EJECT_REASON}: «{from_name or '—'}» → «{to_name or '—'}»", commit=False)
        if faction is not None:
            fcr.log_event(db, character_id=int(character_id), faction_id=int(faction.id), event_type=fc.EV_EJECTED,
                          now=now, points_after=int(member.points) if member is not None else None,
                          rank_id=member.rank_id if member is not None else None,
                          event_key=f"faction:eject:c{int(character_id)}:l{from_location}:{now:%Y%m%d%H%M%S}",
                          reason=f"loc:{from_location}:{target}")
        db.commit()
    except Exception:
        db.rollback()
        raise
    secret_outsider = faction is not None and bool(faction.is_secret) and \
        (member is None or member.status != fc.STATUS_ACTIVE)
    why = "это закрытая территория" if secret_outsider or faction is None else \
        f"это территория фракции «{faction.name}»"
    message = f"Вас выдворили из «{from_name or '—'}» в «{to_name or '—'}»: {why}"
    return [Notice(user_id, message, CATEGORY_SYSTEM,
                   {"character_id": int(character_id), "event": fc.EV_EJECTED, "location_id": target})]


async def eject_many(factory: Callable[[], Session], character_ids: Sequence[int]) -> int:
    """Post-commit best effort (async routes): own session, errors only logged."""
    done = 0
    for cid in character_ids:
        db = factory()
        try:
            notices = await eject(db, int(cid))
        except Exception:
            db.rollback()
            logger.exception("faction eject of character %s failed", cid)
            continue
        finally:
            db.close()
        if notices:
            done += 1
            faction_notify.publish(notices)
    return done


async def eject_location(factory: Callable[[], Session], location_id: int) -> int:
    db = factory()
    try:
        ids = players_in_closed(db, location_id)
    finally:
        db.rollback()
        db.close()
    return await eject_many(factory, ids)


def sweep(factory: Callable[[], Session]) -> int:
    """The faction pass step (sync thread): every player standing where he may not stand."""
    db = factory()
    try:
        ids = players_in_closed(db)
    finally:
        db.rollback()
        db.close()
    if not ids:
        return 0
    return asyncio.run(eject_many(factory, ids))
