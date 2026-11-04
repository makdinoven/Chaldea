"""FEAT-199 renown — fame (public as a tier) and infamy (owner + staff only). Sync SQLAlchemy; pure maths in
``shadow_core``.

:func:`add_renown` is THE single write path (quests via the internal fame endpoint, the reputation hook in
``reputation_crud.apply_reputation``, every crime row in ``law_crud.record_crime``, staff adjust). It runs in the
caller's transaction, never commits, is idempotent per ``event_key`` (pre-check + UNIQUE) and returns the tier change
for the caller to publish after its commit (:func:`fame_notices`; only a fame tier UP is announced — infamy changes
are silent, §3.14 Q3).

Lock order: the ``character_renown`` row is locked after reputation / wanted rows of the same transaction (it is the
last row any transaction touches), so no cycle with the economy / reputation lock orders is possible.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

import models
import shadow_core as sc

logger = logging.getLogger("character-service.renown")

MAX_EVENT_KEY = 191
MAX_REASON = 500

DIRECTION_UP = "up"
DIRECTION_DOWN = "down"


def now_utc() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def _is_mysql(db: Session) -> bool:
    return db.get_bind().dialect.name == "mysql"


def _for_update(db: Session) -> bool:
    return db.get_bind().dialect.name != "sqlite"


def load_shadow_settings(db: Session) -> sc.ShadowSettings:
    return sc.settings_from_row(db.execute(text(sc.SQL_SELECT_SETTINGS)).first())


def load_renown_tiers(db: Session, scale: Optional[str] = None) -> List[sc.RenownTier]:
    tiers = sc.tiers_from_rows(db.execute(text(sc.SQL_SELECT_TIERS)).fetchall())
    return sc.scale_tiers(tiers, scale) if scale else tiers


def renown_of(db: Session, character_id: int) -> Tuple[int, int]:
    """(fame, infamy); (0, 0) without a row."""
    row = db.execute(text("SELECT fame, infamy FROM character_renown WHERE character_id = :c"),
                     {"c": int(character_id)}).first()
    if row is None:
        return 0, 0
    return int(row[0] or 0), int(row[1] or 0)


def fame_tier_of(db: Session, character_id: int, tiers: Optional[Sequence[sc.RenownTier]] = None) -> sc.RenownTier:
    tiers = tiers if tiers is not None else load_renown_tiers(db, sc.SCALE_FAME)
    return sc.renown_tier_for(renown_of(db, character_id)[0], tiers)


@dataclass(frozen=True)
class RenownChange:
    """A tier change of one scale (published after the commit)."""
    character_id: int
    user_id: Optional[int]
    scale: str
    tier_before: str
    tier_before_name: str
    tier_after: str
    tier_after_name: str
    direction: str


@dataclass
class RenownResult:
    duplicate: bool = False
    skipped: bool = False
    value_before: int = 0
    value_after: int = 0
    tier_before: Optional[str] = None
    tier_after: Optional[str] = None
    change: Optional[RenownChange] = None


def _ensure_row(db: Session, character_id: int, now: datetime) -> None:
    if db.execute(text("SELECT 1 FROM character_renown WHERE character_id = :c"),
                  {"c": int(character_id)}).first() is not None:
        return
    if _is_mysql(db):
        sql = ("INSERT INTO character_renown (character_id, fame, infamy, updated_at) VALUES (:c, 0, 0, :now) "
               "ON DUPLICATE KEY UPDATE character_id = character_id")
    else:
        sql = "INSERT OR IGNORE INTO character_renown (character_id, fame, infamy, updated_at) VALUES (:c, 0, 0, :now)"
    db.execute(text(sql), {"c": int(character_id), "now": now})


def _lock_row(db: Session, character_id: int, now: datetime) -> "models.CharacterRenown":
    _ensure_row(db, character_id, now)
    query = db.query(models.CharacterRenown).filter(models.CharacterRenown.character_id == int(character_id))
    if _for_update(db):
        query = query.with_for_update()
    return query.populate_existing().one()


def add_renown(db: Session, *, character_id: int, scale: str, delta: int, source: str, event_key: str,
               ref_id: Optional[int] = None, reason: Optional[str] = None, actor_user_id: Optional[int] = None,
               now: Optional[datetime] = None) -> RenownResult:
    """Change fame / infamy by ``delta`` (clamped at 0). NPC / zero delta -> skipped; repeated key -> duplicate."""
    if scale not in sc.SCALES:
        raise ValueError(f"unknown renown scale {scale!r}")
    if not event_key or len(event_key) > MAX_EVENT_KEY:
        raise ValueError("renown event key is empty or too long")
    now = now or now_utc()
    delta = int(delta or 0)
    char = db.execute(text("SELECT is_npc, user_id FROM characters WHERE id = :id"), {"id": int(character_id)}).first()
    if char is None or bool(char[0]) or delta == 0:
        return RenownResult(skipped=True)
    if db.execute(text("SELECT 1 FROM renown_log WHERE event_key = :k"), {"k": event_key}).first() is not None:
        return RenownResult(duplicate=True)
    tiers = load_renown_tiers(db, scale)
    row = _lock_row(db, character_id, now)
    old = int(getattr(row, scale) or 0)
    new = max(0, old + delta)
    before, after = sc.renown_tier_for(old, tiers), sc.renown_tier_for(new, tiers)
    setattr(row, scale, new)
    row.updated_at = now
    db.add(models.RenownLog(
        event_key=event_key, character_id=int(character_id), scale=scale, source=source, delta=new - old,
        value_after=new, tier_before=before.code, tier_after=after.code, ref_id=ref_id,
        reason=(reason[:MAX_REASON] if reason else None), actor_user_id=actor_user_id, created_at=now))
    db.flush()
    result = RenownResult(value_before=old, value_after=new, tier_before=before.code, tier_after=after.code)
    if before.code != after.code:
        user_id = int(char[1]) if char[1] is not None else None
        result.change = RenownChange(int(character_id), user_id, scale, before.code, before.name, after.code,
                                     after.name, DIRECTION_UP if after.sort_order > before.sort_order
                                     else DIRECTION_DOWN)
    return result


def add_fame(db: Session, *, character_id: int, points: int, source: str, event_key: str, **kwargs) -> RenownResult:
    return add_renown(db, character_id=character_id, scale=sc.SCALE_FAME, delta=points, source=source,
                      event_key=event_key, **kwargs)


def add_infamy(db: Session, *, character_id: int, points: int, event_key: str, ref_id: Optional[int] = None,
               now: Optional[datetime] = None) -> RenownResult:
    return add_renown(db, character_id=character_id, scale=sc.SCALE_INFAMY, delta=points, source=sc.SOURCE_CRIME,
                      event_key=event_key, ref_id=ref_id, now=now)


def changes_of(results: Iterable[Optional[RenownResult]]) -> List[RenownChange]:
    return [r.change for r in results or () if r is not None and r.change is not None]


def fame_message(tier_name: str) -> str:
    return f"Ваша слава растёт: теперь вы — «{tier_name}»"


def fame_notices(changes: Iterable[RenownChange]) -> list:
    """«Ваша слава растёт…» for fame tiers going UP (infamy is silent, §3.14 Q3)."""
    import law_notify
    out = []
    for change in changes or ():
        if change is None or not change.user_id or change.scale != sc.SCALE_FAME or change.direction != DIRECTION_UP:
            continue
        out.append(law_notify.Notice(change.user_id, fame_message(change.tier_after_name), law_notify.WS_FAME_TIER,
                                     law_notify.CATEGORY_PROGRESS,
                                     {"character_id": change.character_id, "tier_code": change.tier_after}))
    return out


def publish_fame_changes(changes: Iterable[RenownChange]) -> int:
    import law_notify
    return law_notify.publish(fame_notices(changes))


# --------------------------------------------------------------------------------------------------- read models

def player_renown(db: Session, character_id: int) -> dict:
    """``GET /characters/{id}/renown`` — tier names only, never the numbers (§3.7)."""
    fame, infamy = renown_of(db, character_id)
    fame_tiers = load_renown_tiers(db, sc.SCALE_FAME)
    infamy_tiers = load_renown_tiers(db, sc.SCALE_INFAMY)
    ft = sc.renown_tier_for(fame, fame_tiers)
    nxt = sc.next_tier(ft, fame_tiers)
    it = sc.renown_tier_for(infamy, infamy_tiers)
    return {
        "fame": {"tier_code": ft.code, "tier_name": ft.name, "progress": sc.renown_progress(fame, ft, fame_tiers),
                 "next_tier_name": nxt.name if nxt else None},
        "rumors": {"tier_code": it.code, "tier_name": it.name},
    }


def fame_tiers_public(db: Session) -> List[dict]:
    return [{"code": t.code, "name": t.name, "sort_order": t.sort_order}
            for t in load_renown_tiers(db, sc.SCALE_FAME)]


def admin_renown(db: Session, character_id: int) -> dict:
    fame, infamy = renown_of(db, character_id)
    return {
        "fame": fame,
        "fame_tier_name": sc.renown_tier_for(fame, load_renown_tiers(db, sc.SCALE_FAME)).name,
        "infamy": infamy,
        "infamy_tier_name": sc.renown_tier_for(infamy, load_renown_tiers(db, sc.SCALE_INFAMY)).name,
    }


def admin_renown_log(db: Session, character_id: int, limit: int = 50) -> List[dict]:
    rows = (db.query(models.RenownLog).filter(models.RenownLog.character_id == int(character_id))
            .order_by(models.RenownLog.created_at.desc(), models.RenownLog.id.desc()).limit(limit).all())
    return [{"id": int(r.id), "created_at": r.created_at, "scale": r.scale, "source": r.source, "delta": int(r.delta),
             "value_after": int(r.value_after), "tier_before": r.tier_before, "tier_after": r.tier_after,
             "ref_id": r.ref_id, "reason": r.reason, "actor_user_id": r.actor_user_id} for r in rows]
