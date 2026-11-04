"""FEAT-199 the shadow (reputation stage 2b) — DB layer (sync SQLAlchemy). Pure maths: ``shadow_core``.

Everything runs in the CALLER's transaction and never commits (``main.update_npc_status``, ``law_pass`` and
``shadow_api`` commit and publish after the commit).

* :func:`npc_kill_consequences` — THE crime orchestrator of an NPC kill: classifies the kill, rolls the witnesses
  BEFORE both the reputation and the wanted, and either applies both at once (witnessed) or records a deferred crime
  snapshot (unwitnessed / masked) + region suspicion;
* :func:`reveal_crime` / :func:`close_crime` — idempotent (conditional status UPDATE) resolution of a deferred crime
  (the law pass and staff);
* region suspicion (lazy linear decay, ``law_core.materialise`` maths), readers of other services' tables,
  settings and the staff read models.

Readers of foreign tables are parameterised ``text()`` and fail loudly; the only tolerated error is the missing
``items.is_mask`` column (inventory-service migration 034 not applied yet) -> WARNING + "no mask".
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

import law_core as lc
import law_crud
import law_notify
import models
import renown_crud
import reputation_core as rc
import reputation_crud
import shadow_core as sc

logger = logging.getLogger("character-service.shadow")

REVEAL_STEP = timedelta(hours=24)
ADMIN_PAGE_MAX = 50
RENOWN_ADJUST_MAX = 10_000

MSG_CRIME_NOT_FOUND = "Преступление не найдено"
MSG_CRIME_RESOLVED = "Дело уже раскрыто или закрыто"
MSG_NPC_RENOWN = "У NPC нет славы"

STATUS_FILTER_OPEN = "open"
STATUS_FILTER_ALL = "all"
STATUS_FILTERS = (STATUS_FILTER_OPEN, lc.CRIME_UNWITNESSED, lc.CRIME_MASKED, lc.CRIME_CLOSED, lc.CRIME_REPORTED,
                  STATUS_FILTER_ALL)


def now_utc() -> datetime:
    return law_crud.now_utc()


load_settings = renown_crud.load_shadow_settings


# =====================================================================================================================
# readers (foreign tables, raw SQL)
# =====================================================================================================================

def location_marker(db: Session, location_id: Optional[int]) -> Optional[str]:
    """``Locations.marker_type`` (locations-service): safe | farm | dangerous | dungeon; None without a location."""
    if not location_id:
        return None
    row = db.execute(text("SELECT marker_type FROM Locations WHERE id = :l"), {"l": int(location_id)}).first()
    return str(row[0]) if row is not None and row[0] is not None else None


def subclass_of(db: Session, character_id: int) -> Optional[str]:
    """The chosen subclass key (skills-service tables; the same SQL as inventory-service equipment_rules)."""
    row = db.execute(text(
        "SELECT tn.subclass_key FROM character_tree_progress ctp JOIN tree_nodes tn ON tn.id = ctp.node_id "
        "WHERE ctp.character_id = :cid AND tn.node_type = 'subclass_choice' AND tn.subclass_key IS NOT NULL "
        "ORDER BY ctp.id DESC LIMIT 1"), {"cid": int(character_id)}).first()
    return str(row[0]) if row is not None and row[0] else None


def _missing_mask_column(exc: Exception) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return "is_mask" in message and ("unknown column" in message or "no such column" in message)


def wears_mask(db: Session, character_id: int) -> bool:
    """A worn item flagged ``items.is_mask`` (inventory-service). Only the missing column (deploy skew) -> False."""
    try:
        with db.begin_nested():
            row = db.execute(text(
                "SELECT 1 FROM equipment_slots es JOIN items i ON i.id = es.item_id "
                "WHERE es.character_id = :c AND es.item_id IS NOT NULL AND i.is_mask = 1 LIMIT 1"),
                {"c": int(character_id)}).first()
    except DBAPIError as exc:
        if _missing_mask_column(exc):
            logger.warning("items.is_mask is missing (inventory migration 034 not applied?) — treating as no mask")
            return False
        raise
    return row is not None


def is_guard_encounter_battle(db: Session, battle_id: Optional[int]) -> bool:
    """``battles.law_encounter_id`` (battle-service) is set: a fight of a guard encounter."""
    if not battle_id:
        return False
    row = db.execute(text("SELECT law_encounter_id FROM battles WHERE id = :b"), {"b": int(battle_id)}).first()
    return row is not None and row[0] is not None


def fame_witness_pct(db: Session, character_id: int, tiers: Sequence[sc.RenownTier]) -> Decimal:
    fame = renown_crud.renown_of(db, character_id)[0]
    return sc.renown_tier_for(fame, tiers).witness_pct


# =====================================================================================================================
# region suspicion
# =====================================================================================================================

def effective_suspicion(db: Session, region_id: Optional[int], s: sc.ShadowSettings, now: datetime) -> int:
    if not region_id:
        return 0
    row = db.execute(text("SELECT value, decay_at FROM region_suspicion WHERE region_id = :r"),
                     {"r": int(region_id)}).first()
    if row is None:
        return 0
    return lc.effective_wanted(int(row[0] or 0), row[1], now, s.suspicion_decay_per_day)


def _lock_suspicion(db: Session, region_id: int, s: sc.ShadowSettings, now: datetime) -> "models.RegionSuspicion":
    if db.execute(text("SELECT 1 FROM region_suspicion WHERE region_id = :r"), {"r": int(region_id)}).first() is None:
        if law_crud._is_mysql(db):
            sql = ("INSERT INTO region_suspicion (region_id, value, decay_at, updated_at) VALUES (:r, 0, NULL, :now) "
                   "ON DUPLICATE KEY UPDATE region_id = region_id")
        else:
            sql = ("INSERT OR IGNORE INTO region_suspicion (region_id, value, decay_at, updated_at) "
                   "VALUES (:r, 0, NULL, :now)")
        db.execute(text(sql), {"r": int(region_id), "now": now})
    query = db.query(models.RegionSuspicion).filter(models.RegionSuspicion.region_id == int(region_id))
    if law_crud._for_update(db):
        query = query.with_for_update()
    row = query.populate_existing().one()
    value, anchor = lc.materialise(int(row.value or 0), row.decay_at, now, s.suspicion_decay_per_day)
    if value != int(row.value or 0) or anchor != law_crud._dt(row.decay_at):
        row.value, row.decay_at, row.updated_at = value, anchor, now
    return row


def add_suspicion(db: Session, region_id: int, gain: int, s: sc.ShadowSettings, now: datetime) -> int:
    """Raise the region's suspicion (materialised, clamped to ``suspicion_max``). Returns the new value."""
    row = _lock_suspicion(db, region_id, s, now)
    old = int(row.value or 0)
    new = sc.add_suspicion(old, gain, s)
    row.decay_at = lc.next_decay_at(old, new, row.decay_at, now)
    row.value = new
    row.updated_at = now
    db.flush()
    return new


def region_suspicion_state(db: Session, region_id: Optional[int], *, s: Optional[sc.ShadowSettings] = None,
                           now: Optional[datetime] = None) -> Optional[dict]:
    """``{"code", "label"}`` for the public region card; None when calm (no numbers)."""
    s = s or load_settings(db)
    state = sc.suspicion_state(effective_suspicion(db, region_id, s, now or now_utc()), s)
    return {"code": state[0], "label": state[1]} if state else None


def _materialise_all_suspicion(db: Session, old_rate, now: datetime) -> None:
    query = db.query(models.RegionSuspicion).filter(models.RegionSuspicion.value > 0) \
        .order_by(models.RegionSuspicion.region_id)
    if law_crud._for_update(db):
        query = query.with_for_update()
    for row in query.populate_existing().all():
        value, anchor = lc.materialise(int(row.value or 0), row.decay_at, now, old_rate)
        row.value, row.decay_at, row.updated_at = value, anchor, now
        if value > 0 and (Decimal(str(old_rate)) <= 0 or anchor is None):
            row.decay_at = now


# =====================================================================================================================
# the crime orchestrator
# =====================================================================================================================

@dataclass
class KillOutcome:
    tier_changes: list = field(default_factory=list)      # reputation_crud.TierChange
    wanted_changes: list = field(default_factory=list)    # law_crud.WantedChange
    fame_changes: list = field(default_factory=list)      # renown_crud.RenownChange
    notices: list = field(default_factory=list)           # law_notify.Notice

    def publish(self) -> None:
        """After the commit: reputation tiers, wanted levels, fame tiers, the «никто не видел» hints."""
        import reputation_notify
        reputation_notify.publish_tier_changes(self.tier_changes)
        law_notify.publish(law_notify.wanted_notices(self.wanted_changes)
                           + renown_crud.fame_notices(self.fame_changes) + list(self.notices))


@dataclass(frozen=True)
class _Member:
    character_id: int
    masked: bool
    chance: Decimal


def _players(db: Session, npc_id: int, killer_ids: Iterable[int]) -> List[int]:
    ids = sorted({int(k) for k in killer_ids or () if k and int(k) != int(npc_id)})
    if not ids:
        return []
    ph, params = law_crud._in("k", ids)
    return [int(r[0]) for r in db.execute(text(
        f"SELECT id FROM characters WHERE id IN ({ph}) AND is_npc = 0 ORDER BY id"), params).fetchall()]


def npc_kill_consequences(db: Session, npc: "models.Character", *, battle_id: Optional[int],
                          killer_ids: Iterable[int], now: Optional[datetime] = None) -> KillOutcome:
    """Reputation + crime of an NPC kill (or a guard knock-out) for every PLAYER of the winning side (§3.4).

    Not a crime (bandit +20 …) -> the kill reputation as before, no roll. A guard-encounter fight or the kill switch
    -> always witnessed. Otherwise ONE group roll: witnessed members without a mask get everything at once;
    unseen / masked members get a deferred crime (snapshot) and the region's suspicion rises once per event."""
    now = now or now_utc()
    outcome = KillOutcome()
    players = _players(db, npc.id, killer_ids)
    if not players:
        return outcome
    region_id = reputation_crud.location_region(db, npc.current_location_id)
    if not region_id:
        return outcome
    points = reputation_crud.npc_kill_points(db, npc)
    is_guard = (npc.npc_role or "") == lc.GUARD_ROLE
    crime_points = lc.crime_weight(points)
    law_settings = law_crud.load_settings(db)
    floor = int(law_settings.heavy_wanted) if is_guard else None
    stamp = reputation_crud.kill_stamp(battle_id, now)

    # 3. not a crime: reputation exactly as before (positive -> fame via the reputation hook)
    if crime_points <= 0 and not floor:
        results = reputation_crud.apply_npc_kill(db, npc, battle_id=battle_id, killer_ids=players, now=now)
        outcome.tier_changes = reputation_crud.tier_changes_of(results)
        outcome.fame_changes = reputation_crud.fame_changes_of(results)
        return outcome

    s = load_settings(db)
    forced = (not s.witness_enabled) or is_guard_encounter_battle(db, battle_id)
    members: Dict[int, _Member] = {}
    if forced:
        witnessed, chance, roll = True, Decimal(100), None
        for cid in players:
            members[cid] = _Member(cid, False, Decimal(100))
    else:
        base = sc.base_pct(location_marker(db, npc.current_location_id), s)
        fame_tiers = renown_crud.load_renown_tiers(db, sc.SCALE_FAME)
        for cid in players:
            agility, luck = law_crud.effective_attributes_of(db, cid)
            masked = wears_mask(db, cid)
            members[cid] = _Member(cid, masked, sc.member_chance(
                base, s, agility, luck, subclass_of(db, cid), masked, fame_witness_pct(db, cid, fame_tiers)))
        chance = sc.group_chance([m.chance for m in members.values()], len(players), s)
        witnessed, roll = lc.roll_succeeds(chance, law_crud.rng())

    levels = law_crud.load_levels(db)
    location_id = int(npc.current_location_id) if npc.current_location_id else None
    crime_type = lc.CRIME_GUARD_DEFEAT if is_guard else lc.CRIME_NPC_KILL
    reason = reputation_crud.npc_kill_reason(npc, battle_id)
    user_ids = law_crud.character_user_ids(db, players)
    deferred_masked = deferred_any = False
    for cid in players:
        member = members[cid]
        rep_key = reputation_crud.npc_kill_key(npc.id, stamp, cid)
        common = dict(crime_type=crime_type, character_id=cid, region_id=region_id, points=crime_points,
                      event_key=f"crime:npc_kill:{npc.id}:{stamp}:{cid}", location_id=location_id,
                      victim_id=int(npc.id), battle_id=battle_id, floor=floor, now=now,
                      reputation_delta=points or None, reputation_key=rep_key, reputation_reason=reason,
                      masked=member.masked, witness_chance_pct=chance, witness_roll_pct=roll)
        if witnessed and (forced or not member.masked):
            rep = reputation_crud.apply_npc_kill_for(db, npc, cid, region_id, points, stamp, battle_id=battle_id,
                                                     now=now)
            outcome.tier_changes.extend(rep.tier_changes)
            outcome.fame_changes.extend(rep.fame_changes)
            crime = law_crud.register_crime(db, settings=law_settings, levels=levels, status=lc.CRIME_REPORTED,
                                            **common)
            if crime.change is not None:
                outcome.wanted_changes.append(crime.change)
            continue
        status = lc.CRIME_MASKED if witnessed else lc.CRIME_UNWITNESSED
        crime = law_crud.register_crime(db, status=status, reveal_until=now + timedelta(days=int(s.reveal_days)),
                                        next_roll_at=now + REVEAL_STEP, **common)
        if crime.crime is None:
            continue                                    # duplicate / skipped: nothing new happened
        deferred_any = True
        deferred_masked = deferred_masked or member.masked
        if status == lc.CRIME_MASKED:
            outcome.notices.append(law_notify.Notice(user_ids.get(cid), law_notify.MSG_MASKED, law_notify.WS_MASKED,
                                                     law_notify.CATEGORY_PROGRESS, {"character_id": cid}))
        else:
            outcome.notices.append(law_notify.Notice(user_ids.get(cid), law_notify.MSG_UNSEEN, law_notify.WS_UNSEEN,
                                                     law_notify.CATEGORY_PROGRESS, {"character_id": cid}))
    if deferred_any:
        add_suspicion(db, region_id, s.suspicion_masked if deferred_masked else s.suspicion_unwitnessed, s, now)
    logger.info("npc kill %s battle=%s players=%s forced=%s chance=%s roll=%s witnessed=%s", npc.id, battle_id,
                players, forced, chance, roll, witnessed)
    return outcome


# =====================================================================================================================
# reveal / close
# =====================================================================================================================

@dataclass
class RevealResult:
    crime_id: int
    character_id: int
    user_id: Optional[int]
    region_id: int
    region_name: Optional[str]
    tier_changes: list = field(default_factory=list)
    fame_changes: list = field(default_factory=list)
    wanted_change: Optional[object] = None

    def notices(self) -> list:
        out = [law_notify.Notice(self.user_id, law_notify.revealed_message(self.region_name), law_notify.WS_REVEALED,
                                 law_notify.CATEGORY_SYSTEM,
                                 {"character_id": self.character_id, "region_id": self.region_id})]
        if self.wanted_change is not None:
            out.extend(law_notify.wanted_notices([self.wanted_change]))
        return out

    def publish(self) -> None:
        import reputation_notify
        reputation_notify.publish_tier_changes(self.tier_changes)
        law_notify.publish(self.notices())


def _crime(db: Session, crime_id: int, *, lock: bool = False) -> Optional["models.LawCrime"]:
    query = db.query(models.LawCrime).filter(models.LawCrime.id == int(crime_id))
    if lock and law_crud._for_update(db):
        query = query.with_for_update()
    return query.populate_existing().first()


def reveal_crime(db: Session, crime_id: int, *, now: Optional[datetime] = None, chance=None, roll=None,
                 actor_user_id: Optional[int] = None, reason: Optional[str] = None) -> Optional[RevealResult]:
    """Apply a deferred crime (stored reputation key + wanted floor). Conditional: None when it is no longer open."""
    now = now or now_utc()
    updated = db.execute(text(
        "UPDATE law_crimes SET status = :rep, revealed_at = :now WHERE id = :id AND status IN (:u, :m)"),
        {"rep": lc.CRIME_REPORTED, "now": now, "id": int(crime_id), "u": lc.CRIME_UNWITNESSED,
         "m": lc.CRIME_MASKED})
    if (updated.rowcount or 0) != 1:
        return None
    crime = _crime(db, crime_id)
    character_id, region_id = int(crime.character_id), int(crime.region_id)
    user_id = law_crud.character_user_ids(db, [character_id]).get(character_id)
    result = RevealResult(int(crime.id), character_id, user_id, region_id,
                          law_crud.region_names(db, [region_id]).get(region_id))
    if crime.reputation_delta and crime.reputation_key:
        rep = reputation_crud.apply_reputation(
            db, character_id=character_id, region_id=region_id, action=rc.ACTION_NPC_KILL, idem_key=crime.reputation_key,
            delta=int(crime.reputation_delta), reason=crime.reputation_reason, now=now)
        result.tier_changes, result.fame_changes = list(rep.tier_changes), list(rep.fame_changes)
    result.wanted_change = law_crud.apply_crime_wanted(
        db, crime, floor=crime.wanted_floor, settings=law_crud.load_settings(db), levels=law_crud.load_levels(db),
        now=now, user_id=user_id)
    if actor_user_id is None:
        law_crud._log(db, key=f"law:reveal:{crime.id}", character_id=character_id, action=lc.LOG_REVEAL,
                      region_id=region_id, chance_pct=chance, roll_pct=roll, ref_id=int(crime.id), now=now)
    else:
        law_crud._log(db, key=f"law:staff_reveal:{crime.id}", character_id=character_id, action=lc.LOG_STAFF_REVEAL,
                      region_id=region_id, ref_id=int(crime.id), reason=reason, actor_user_id=actor_user_id, now=now)
    db.flush()
    return result


def close_crime(db: Session, crime_id: int, *, now: Optional[datetime] = None, actor_user_id: Optional[int] = None,
                reason: Optional[str] = None) -> bool:
    """Close a deferred crime forever (no reputation, no wanted, no player notice). False when no longer open."""
    now = now or now_utc()
    updated = db.execute(text(
        "UPDATE law_crimes SET status = :c, resolved_at = :now WHERE id = :id AND status IN (:u, :m)"),
        {"c": lc.CRIME_CLOSED, "now": now, "id": int(crime_id), "u": lc.CRIME_UNWITNESSED, "m": lc.CRIME_MASKED})
    if (updated.rowcount or 0) != 1:
        return False
    crime = _crime(db, crime_id)
    if actor_user_id is None:
        law_crud._log(db, key=f"law:closed:{crime.id}", character_id=int(crime.character_id),
                      action=lc.LOG_CRIME_CLOSED, region_id=int(crime.region_id), ref_id=int(crime.id), now=now)
    else:
        law_crud._log(db, key=f"law:staff_close:{crime.id}", character_id=int(crime.character_id),
                      action=lc.LOG_STAFF_CLOSE, region_id=int(crime.region_id), ref_id=int(crime.id), reason=reason,
                      actor_user_id=actor_user_id, now=now)
    db.flush()
    return True


def roll_reveal(db: Session, crime_id: int, now: datetime) -> Optional[RevealResult]:
    """One daily reveal roll of the law pass (caller commits). Locks the row and re-checks it is due."""
    crime = _crime(db, crime_id, lock=True)
    if crime is None or crime.status not in lc.CRIME_OPEN:
        return None
    next_at = law_crud._dt(crime.next_roll_at)
    if next_at is None or next_at > now:
        return None
    s = load_settings(db)
    chance = sc.reveal_chance(effective_suspicion(db, crime.region_id, s, now), bool(crime.masked), s)
    ok, roll = lc.roll_succeeds(chance, law_crud.rng())
    if ok:
        return reveal_crime(db, crime.id, now=now, chance=chance, roll=roll)
    crime.reveal_attempts = int(crime.reveal_attempts or 0) + 1
    law_crud._log(db, key=f"law:reveal_roll:{crime.id}:{crime.reveal_attempts}", character_id=int(crime.character_id),
                  action=lc.LOG_REVEAL_FAIL, region_id=int(crime.region_id), chance_pct=chance, roll_pct=roll,
                  ref_id=int(crime.id), now=now)
    crime.next_roll_at = next_at + REVEAL_STEP
    db.flush()
    until = law_crud._dt(crime.reveal_until)
    if until is None or crime.next_roll_at > until:
        close_crime(db, crime.id, now=now)
    return None


# =====================================================================================================================
# staff
# =====================================================================================================================

def _crime_out(c: "models.LawCrime", names: dict) -> dict:
    return {
        "id": int(c.id), "character_id": int(c.character_id),
        "character_name": names["chars"].get(int(c.character_id)), "crime_type": c.crime_type,
        "region_id": int(c.region_id), "region_name": names["regions"].get(int(c.region_id)),
        "location_id": c.location_id,
        "location_name": names["locations"].get(int(c.location_id)) if c.location_id else None,
        "victim_id": c.victim_character_id,
        "victim_name": names["chars"].get(int(c.victim_character_id)) if c.victim_character_id else None,
        "status": c.status, "masked": bool(c.masked),
        "witness_chance_pct": float(c.witness_chance_pct) if c.witness_chance_pct is not None else None,
        "witness_roll_pct": float(c.witness_roll_pct) if c.witness_roll_pct is not None else None,
        "reputation_delta": c.reputation_delta, "wanted_points": int(c.wanted_points),
        "wanted_floor": c.wanted_floor, "reveal_attempts": int(c.reveal_attempts or 0),
        "next_roll_at": c.next_roll_at, "reveal_until": c.reveal_until, "created_at": c.created_at,
        "resolved_at": c.resolved_at, "revealed_at": c.revealed_at,
    }


def _names(db: Session, crimes: Sequence["models.LawCrime"]) -> dict:
    char_ids = {int(c.character_id) for c in crimes} | {int(c.victim_character_id) for c in crimes
                                                        if c.victim_character_id}
    chars = {}
    if char_ids:
        ph, params = law_crud._in("c", sorted(char_ids))
        chars = {int(r[0]): r[1] for r in db.execute(text(f"SELECT id, name FROM characters WHERE id IN ({ph})"),
                                                      params).fetchall()}
    return {"chars": chars, "regions": law_crud.region_names(db, {int(c.region_id) for c in crimes}),
            "locations": law_crud.location_names(db, {int(c.location_id) for c in crimes if c.location_id})}


def crimes_out(db: Session, crimes: Sequence["models.LawCrime"]) -> List[dict]:
    names = _names(db, crimes)
    return [_crime_out(c, names) for c in crimes]


def admin_crimes(db: Session, *, status: str = STATUS_FILTER_OPEN, region_id: Optional[int] = None,
                 character_id: Optional[int] = None, page: int = 1, page_size: int = 20) -> dict:
    query = db.query(models.LawCrime)
    if status == STATUS_FILTER_OPEN:
        query = query.filter(models.LawCrime.status.in_(lc.CRIME_OPEN))
    elif status != STATUS_FILTER_ALL:
        query = query.filter(models.LawCrime.status == status)
    if region_id is not None:
        query = query.filter(models.LawCrime.region_id == int(region_id))
    if character_id is not None:
        query = query.filter(models.LawCrime.character_id == int(character_id))
    total = query.count()
    page_size = max(1, min(int(page_size), ADMIN_PAGE_MAX))
    crimes = (query.order_by(models.LawCrime.created_at.desc(), models.LawCrime.id.desc())
              .offset((max(1, int(page)) - 1) * page_size).limit(page_size).all())
    return {"items": crimes_out(db, crimes), "total": int(total)}


def crime_detail(db: Session, crime_id: int) -> dict:
    crime = _crime(db, crime_id)
    if crime is None:
        raise law_crud.LawError(404, MSG_CRIME_NOT_FOUND)
    return crimes_out(db, [crime])[0]


def staff_reveal(db: Session, crime_id: int, *, reason: str, actor_user_id: int) -> RevealResult:
    if _crime(db, crime_id) is None:
        raise law_crud.LawError(404, MSG_CRIME_NOT_FOUND)
    result = reveal_crime(db, crime_id, actor_user_id=actor_user_id, reason=reason)
    if result is None:
        raise law_crud.LawError(409, MSG_CRIME_RESOLVED)
    return result


def staff_close(db: Session, crime_id: int, *, reason: str, actor_user_id: int) -> None:
    if _crime(db, crime_id) is None:
        raise law_crud.LawError(404, MSG_CRIME_NOT_FOUND)
    if not close_crime(db, crime_id, actor_user_id=actor_user_id, reason=reason):
        raise law_crud.LawError(409, MSG_CRIME_RESOLVED)


def regions_suspicion(db: Session) -> List[dict]:
    s, now = load_settings(db), now_utc()
    rows = db.execute(text("SELECT region_id, value, decay_at FROM region_suspicion WHERE value > 0 "
                           "ORDER BY region_id")).fetchall()
    out = []
    for region_id, value, decay_at in rows:
        effective = lc.effective_wanted(int(value or 0), decay_at, now, s.suspicion_decay_per_day)
        if effective <= 0:
            continue
        code = sc.suspicion_code(effective, s)
        out.append({"region_id": int(region_id), "value": effective, "code": code,
                    "label": sc.SUSPICION_LABELS[code]})
    names = law_crud.region_names(db, [x["region_id"] for x in out])
    for x in out:
        x["region_name"] = names.get(x["region_id"])
    return out


def staff_renown_adjust(db: Session, character_id: int, *, scale: str, delta: int, reason: str, request_id: str,
                        actor_user_id: int) -> dict:
    row = db.execute(text("SELECT is_npc FROM characters WHERE id = :c"), {"c": int(character_id)}).first()
    if row is None:
        raise law_crud.LawError(404, law_crud.MSG_CHARACTER_NOT_FOUND)
    if bool(row[0]):
        raise law_crud.LawError(400, MSG_NPC_RENOWN)
    key = f"renown:staff:{request_id}"
    result = renown_crud.add_renown(db, character_id=character_id, scale=scale, delta=delta, source=sc.SOURCE_STAFF,
                                    event_key=key, reason=reason, actor_user_id=actor_user_id)
    if result.duplicate:
        prev = db.execute(text("SELECT value_after, delta, tier_before, tier_after FROM renown_log "
                               "WHERE event_key = :k"), {"k": key}).first()
        return {"scale": scale, "value_before": int(prev[0]) - int(prev[1]), "value_after": int(prev[0]),
                "tier_before": prev[2], "tier_after": prev[3], "duplicate": True, "change": None}
    if result.skipped:
        raise law_crud.LawError(400, MSG_NPC_RENOWN)
    return {"scale": scale, "value_before": result.value_before, "value_after": result.value_after,
            "tier_before": result.tier_before, "tier_after": result.tier_after, "duplicate": False,
            "change": result.change}


# =====================================================================================================================
# settings
# =====================================================================================================================

def _settings_dict(s: sc.ShadowSettings) -> dict:
    out = {}
    for name in sc.SETTINGS_FIELDS:
        value = getattr(s, name)
        out[name] = float(value) if isinstance(value, Decimal) else value
    return out


def settings_out(db: Session) -> dict:
    tiers = renown_crud.load_renown_tiers(db)
    return {
        "settings": _settings_dict(load_settings(db)),
        "fame_tiers": [{"code": t.code, "sort_order": t.sort_order, "name": t.name, "min_value": t.min_value,
                        "witness_pct": float(t.witness_pct)} for t in sc.scale_tiers(tiers, sc.SCALE_FAME)],
        "infamy_tiers": [{"code": t.code, "sort_order": t.sort_order, "name": t.name, "min_value": t.min_value}
                         for t in sc.scale_tiers(tiers, sc.SCALE_INFAMY)],
    }


def update_settings(db: Session, body) -> dict:
    """Validate and store the settings + both 5-tier ladders (``reputation:settings``). A changed suspicion decay
    first materialises every region at the OLD rate (same transaction), so the change is not retroactive."""
    old = load_settings(db)
    values = {}
    for name in sc.SETTINGS_FIELDS:
        value = getattr(body.settings, name)
        if name in sc.BOOL_FIELDS:
            values[name] = bool(value)
        elif name in sc.INT_FIELDS:
            values[name] = int(value)
        else:
            values[name] = Decimal(str(value))
    new = sc.ShadowSettings(**values)
    tiers = []
    for scale, items in ((sc.SCALE_FAME, body.fame_tiers), (sc.SCALE_INFAMY, body.infamy_tiers)):
        codes = sc.TIER_CODES[scale]
        for x in items:
            tiers.append(sc.RenownTier(scale, x.code, codes.index(x.code) + 1 if x.code in codes else 0,
                                       (x.name or "").strip(), int(x.min_value),
                                       Decimal(str(getattr(x, "witness_pct", 0) or 0))
                                       if scale == sc.SCALE_FAME else Decimal(0)))
    error = sc.validate(new, tiers)
    if error:
        raise law_crud.LawError(400, error)
    now = now_utc()
    if Decimal(str(new.suspicion_decay_per_day)) != Decimal(str(old.suspicion_decay_per_day)):
        _materialise_all_suspicion(db, old.suspicion_decay_per_day, now)
    row = db.get(models.ShadowSettings, 1)
    if row is None:
        row = models.ShadowSettings(id=1, updated_at=now)
        db.add(row)
    for name, value in values.items():
        setattr(row, name, value)
    row.updated_at = now
    existing = {(x.scale, x.code): x for x in db.query(models.RenownTier).all()}
    # two passes so the UNIQUE(scale, sort_order) never collides while orders are being rewritten
    for target in existing.values():
        target.sort_order = -target.sort_order - 100
    db.flush()
    for tier in tiers:
        target = existing.get((tier.scale, tier.code))
        if target is None:
            target = models.RenownTier(scale=tier.scale, code=tier.code)
            db.add(target)
        target.sort_order = tier.sort_order
        target.name = tier.name
        target.min_value = tier.min_value
        target.witness_pct = tier.witness_pct
    db.flush()
    return settings_out(db)
