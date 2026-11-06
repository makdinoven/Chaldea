"""FEAT-207 factions stage 3 — item donations + the faction item stock. features/FEAT-207 §3.8. Sync SQLAlchemy.

* eligibility: an active member of a faction whose economy ticks (206 ``not_ticking_reason`` is None); per item:
  plain stacks only (no enhancement / gems / durability), not a quest item, on-market with a goods group present in
  the HQ region and a positive wholesale price there;
* value = the HQ region wholesale price (the same price the tick sale will receive) x quantity, counted as marks on the
  206 donation day row (same 10:1 rate, same daily cap);
* the flow moves NO money (no ledger op): items leave the bag (direct ``character_inventory`` writes, guild / mint
  precedent) and wait in ``faction_item_stock``; the 6 h tick sells them to the HQ market inside the faction's
  ``faction_tick`` op (``purse(hq) -> faction``), so marks never appear from nowhere.

Lock order (§3.10): faction_members (asc id) -> faction_item_stock (asc item_id) -> faction_donation_days ->
character_inventory (asc id). Idempotency: ``faction_log`` UNIQUE(event_key, faction_id) with the key
``faction:donate_items:c<cid>:<request_id>``.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import econ_core as core
import faction_core as fc
import faction_crud as fcr
import faction_econ as fe
import faction_econ_crud as fec
import models
from faction_crud import FactionError, FlowResult

logger = logging.getLogger("character-service.faction_items")

MAX_LINES = 20
MAX_QTY = 9999

MSG_NPC = "NPC не может жертвовать фракциям"
MSG_DONE = "Это пожертвование уже выполнено"
MSG_NOT_TICKING = "Фракция сейчас не принимает предметы: {reason}"
MSG_ITEM = "Предмет «{name}» нельзя пожертвовать: {reason}"
MSG_NOT_ENOUGH = "Недостаточно предметов «{name}»"
MSG_DUP = "Предметы в пожертвовании не должны повторяться"
MSG_LINES = "Предметов в пожертвовании: от 1 до 20 видов"
MSG_QTY = "Количество предмета: от 1 до 9999"
REASON_QUEST = "квестовый предмет"
REASON_MARKET = "не продаётся на рынке края штаба"
REASON_NOT_PLAIN = "улучшенный или повреждённый предмет"
REASON_MISSING = "предмет не найден"

SQL_PLAIN_STACKS = (
    "SELECT item_id, SUM(quantity) FROM character_inventory WHERE character_id = :c "
    "AND COALESCE(enhancement_points_spent, 0) = 0 AND socketed_gems IS NULL AND current_durability IS NULL "
    "GROUP BY item_id"
)


def donation_key(character_id: int, request_id: str) -> str:
    return f"faction:donate_items:c{int(character_id)}:{request_id}"


# =====================================================================================================================
# pricing in the HQ region
# =====================================================================================================================

@dataclass(frozen=True)
class Quote:
    item_id: int
    name: Optional[str]
    image: Optional[str]
    rarity: Optional[str]
    group: Optional[str]
    item_price: int
    unit_value: int                 # 0 = cannot be sold here
    reason: Optional[str]           # why it cannot be donated (None = ok)


def quotes(db: Session, region_id: Optional[int], item_ids: Iterable[int]) -> Dict[int, Quote]:
    """Per item: the wholesale price in ``region_id`` (the tick sale price) or the reason it cannot be donated."""
    import econ_tick
    import economy_guild_crud
    ids = sorted({int(i) for i in item_ids})
    if not ids:
        return {}
    markets = econ_tick.load_item_markets(db, ids)
    quest = economy_guild_crud.quest_item_ids(db, ids)
    rarity = {}
    ph, params = fcr.in_clause("i", ids)
    for row in db.execute(text(f"SELECT id, item_rarity FROM items WHERE id IN ({ph})"), params).fetchall():
        rarity[int(row[0])] = row[1]
    group_base = {g.code: int(g.base_price or 0) for g in db.query(models.EconGoodsGroup).all()}
    mults: Dict[str, Decimal] = {}
    if region_id:
        mults = {g.group_code: Decimal(str(g.price_mult or 1)) for g in db.query(models.EconRegionGood).filter(
            models.EconRegionGood.region_id == int(region_id)).all()}
    share = Decimal(str(econ_tick.load_params(db).merchant_wholesale_share))
    out: Dict[int, Quote] = {}
    for iid in ids:
        m = markets.get(iid)
        if m is None:
            out[iid] = Quote(iid, None, None, None, None, 0, 0, REASON_MISSING)
            continue
        value, reason = 0, None
        if iid in quest:
            reason = REASON_QUEST
        elif m.off_market or not m.group or m.group not in mults:
            reason = REASON_MARKET
        else:
            gb = group_base.get(m.group, 0)
            base = core.item_base_price(m.price, gb)
            if base <= 0 or core.units_per_item(base, gb) <= 0:
                reason = REASON_MARKET
            else:
                value = core.wholesale_price(base, mults[m.group], share)
                if value <= 0:
                    reason = REASON_MARKET
        out[iid] = Quote(iid, m.name, m.image, rarity.get(iid), m.group, int(m.price or 0), int(value), reason)
    return out


def _ticking(db: Session, faction: "models.Faction") -> Tuple[Optional[str], Optional[int]]:
    """(reason the faction cannot take items | None, HQ region id)."""
    s = fec.load_econ_settings(db)
    econ = fec.economy_row(db, faction.id)
    reason, region_id, _sim = fec.not_ticking_reason(db, faction, econ, s)
    return reason, region_id


def items_status(db: Session, faction: "models.Faction") -> Tuple[bool, Optional[str]]:
    """For the private view: (items_enabled, items_disabled_reason)."""
    reason, _region = _ticking(db, faction)
    return reason is None, reason


def _plain_stacks(db: Session, character_id: int) -> Dict[int, int]:
    return {int(r[0]): int(r[1] or 0) for r in db.execute(text(SQL_PLAIN_STACKS), {"c": int(character_id)}).fetchall()
            if int(r[1] or 0) > 0}


# =====================================================================================================================
# player
# =====================================================================================================================

def _require_member(db: Session, character_id: int, faction_id: int):
    ch = fcr.require_character(db, character_id)
    if ch.is_npc:
        raise FactionError(403, MSG_NPC)
    faction = fcr.faction_or_404(db, faction_id)
    member = fcr.member_row(db, ch.id, faction.id)
    if member is None or member.status != fc.STATUS_ACTIVE:
        raise FactionError(404, fcr.MSG_NOT_MEMBER)
    return ch, faction, member


def options(db: Session, character_id: int, faction_id: int, now: Optional[datetime] = None) -> dict:
    """``GET /{cid}/factions/{fid}/donate-items``: eligible plain stacks with their unit value."""
    now = now or fcr.now_utc()
    ch, faction, _member = _require_member(db, character_id, faction_id)
    s = fec.load_econ_settings(db)
    day = db.query(models.FactionDonationDay).filter(
        models.FactionDonationDay.character_id == ch.id, models.FactionDonationDay.faction_id == int(faction.id),
        models.FactionDonationDay.day == fec.today_utc(now)).first()
    reason, region_id = _ticking(db, faction)
    items: List[dict] = []
    if reason is None:
        stacks = _plain_stacks(db, ch.id)
        q = quotes(db, region_id, stacks)
        for iid in sorted(stacks, key=lambda i: ((q[i].name or "") if i in q else "", i)):
            quote = q.get(iid)
            if quote is None or quote.reason is not None or quote.unit_value <= 0:
                continue
            items.append({"item_id": iid, "name": quote.name, "image": quote.image, "item_rarity": quote.rarity,
                          "quantity": stacks[iid], "unit_value": quote.unit_value})
    return {"enabled": reason is None, "reason": reason, "marks_per_point": int(s.donation_marks_per_point),
            "daily_cap": int(s.donation_points_daily_cap), "points_today": int(day.points) if day else 0,
            "marks_today": int(day.marks) if day else 0, "resets_in_seconds": fec.seconds_to_next_day(now),
            "items": items}


def ensure_stock_rows(db: Session, faction_id: int, item_ids: Sequence[int], now: datetime) -> None:
    """Zero stock rows in their OWN short transaction (commits / rolls back ``db``)."""
    db.rollback()
    ph, params = fcr.in_clause("i", list(item_ids))
    have = {int(r[0]) for r in db.execute(text(
        f"SELECT item_id FROM faction_item_stock WHERE faction_id = :f AND item_id IN ({ph})"),
        {"f": int(faction_id), **params}).fetchall()}
    missing = [i for i in item_ids if int(i) not in have]
    if not missing:
        db.rollback()
        return
    try:
        for iid in missing:
            db.add(models.FactionItemStock(faction_id=int(faction_id), item_id=int(iid), quantity=0, updated_at=now))
        db.commit()
    except IntegrityError:
        db.rollback()        # a concurrent donation created them


def donate_items(db: Session, character_id: int, faction_id: int, lines, request_id: str,
                 now: Optional[datetime] = None) -> FlowResult:
    """§3.8. Raises FactionError (Russian). The caller (API ``_write``) commits."""
    import economy_mint_crud
    from economy_crud import EconomyApiError
    now = now or fcr.now_utc()
    wanted: Dict[int, int] = {}
    if not 1 <= len(lines) <= MAX_LINES:
        raise FactionError(422, MSG_LINES)
    for line in lines:
        iid, qty = int(line.item_id), int(line.quantity)
        if iid in wanted:
            raise FactionError(422, MSG_DUP)
        if not 1 <= qty <= MAX_QTY:
            raise FactionError(422, MSG_QTY)
        wanted[iid] = qty
    ch, faction, _member = _require_member(db, character_id, faction_id)
    key = donation_key(ch.id, request_id)
    if fcr.log_key_exists(db, key, faction.id):
        raise FactionError(409, MSG_DONE)
    reason, region_id = _ticking(db, faction)
    if reason is not None:
        raise FactionError(409, MSG_NOT_TICKING.format(reason=reason))
    q = quotes(db, region_id, wanted)
    for iid in sorted(wanted):
        quote = q.get(iid)
        if quote is None or quote.reason is not None:
            raise FactionError(400, MSG_ITEM.format(name=(quote.name if quote else None) or f"#{iid}",
                                                    reason=quote.reason if quote else REASON_MISSING))
    item_ids = sorted(wanted)
    day = fec.today_utc(now)
    fec.ensure_day_row(db, ch.id, faction.id, day)           # commits / rolls back: nothing open before
    ensure_stock_rows(db, faction.id, item_ids, now)

    s_core = fcr.load_settings(db)
    s = fec.load_econ_settings(db)
    hostile = sorted(fcr.hostile_map(db).get(int(faction.id), set()))
    members = fec._lock_members(db, ch.id, [faction.id, *hostile])
    member = members.get(int(faction.id))
    if member is None or member.status != fc.STATUS_ACTIVE:
        raise FactionError(404, fcr.MSG_NOT_MEMBER)
    stock = {int(r.item_id): r for r in fec._lock(db, db.query(models.FactionItemStock).filter(
        models.FactionItemStock.faction_id == int(faction.id), models.FactionItemStock.item_id.in_(item_ids))
        .order_by(models.FactionItemStock.item_id)).all()}
    day_row = fec._lock(db, db.query(models.FactionDonationDay).filter(
        models.FactionDonationDay.character_id == ch.id, models.FactionDonationDay.faction_id == int(faction.id),
        models.FactionDonationDay.day == day)).first()
    if day_row is None:
        day_row = models.FactionDonationDay(character_id=ch.id, faction_id=int(faction.id), day=day, marks=0,
                                            points=0, kill_points=0)
        db.add(day_row)
        db.flush()
    value_total = 0
    given = 0
    for iid in item_ids:
        qty = wanted[iid]
        name = q[iid].name or f"#{iid}"
        try:
            economy_mint_crud.take_plain_stacks(db, ch.id, iid, qty, name, not_enough=MSG_NOT_ENOUGH)
        except EconomyApiError as exc:
            raise FactionError(exc.status_code, exc.detail)
        row = stock.get(iid)
        if row is None:
            row = models.FactionItemStock(faction_id=int(faction.id), item_id=iid, quantity=0, updated_at=now)
            db.add(row)
        row.quantity = int(row.quantity or 0) + qty
        row.updated_at = now
        value_total += q[iid].unit_value * qty
        given += qty

    gain, points_today = fe.donation_points(int(day_row.marks), value_total, s.donation_marks_per_point,
                                            s.donation_points_daily_cap, int(day_row.points))
    day_row.marks = int(day_row.marks) + value_total
    day_row.points = points_today
    reason_text = f"items:{given}:{value_total}"
    if gain > 0:
        actual = fcr.change_points(db, member, gain, fc.EV_DONATION, now, event_key=key, reason=reason_text)
        penalty = fc.hostile_penalty(gain, s_core.hostile_penalty_pct)
        for other in hostile:
            if penalty <= 0:
                break
            other_member = members.get(int(other))
            if other_member is None or other_member.status != fc.STATUS_ACTIVE:
                continue
            fcr.change_points(db, other_member, -penalty, fc.EV_HOSTILE, now,
                              event_key=f"{key}:hostile:{int(faction.id)}", reason=f"faction:{int(faction.id)}")
    else:
        actual = 0
        fcr.log_event(db, character_id=ch.id, faction_id=faction.id, event_type=fc.EV_DONATION, now=now,
                      points_delta=0, points_after=int(member.points), rank_id=member.rank_id, event_key=key,
                      reason=reason_text)
    db.flush()
    rechecked = fcr.recheck_ranks(db, ch.id, now)
    result = FlowResult()
    result.merge(rechecked)
    result.data = {"points_delta": int(actual), "points_after": int(member.points), "points_today": int(points_today),
                   "daily_cap": int(s.donation_points_daily_cap), "value_total": int(value_total),
                   "items_given": int(given), "rank_ups": int(rechecked.data.get("rank_ups", 0))}
    return result


# =====================================================================================================================
# tick sale + admin view
# =====================================================================================================================

def stock_rows(db: Session, faction_id: int) -> List[Tuple[int, int]]:
    """(item_id, quantity > 0) ascending item id (plain read)."""
    return [(int(r[0]), int(r[1])) for r in db.execute(text(
        "SELECT item_id, quantity FROM faction_item_stock WHERE faction_id = :f AND quantity > 0 ORDER BY item_id"),
        {"f": int(faction_id)}).fetchall()]


def stock_value(db: Session, faction_id: int, region_id: int) -> int:
    """The marks the faction's stock would fetch in ``region_id`` now (the tick's sales want)."""
    rows = stock_rows(db, faction_id)
    if not rows:
        return 0
    q = quotes(db, region_id, [i for i, _n in rows])
    return sum(q[i].unit_value * n for i, n in rows if i in q and q[i].reason is None)


def stock_view(db: Session, faction: "models.Faction") -> List[dict]:
    """Admin economy view: every stock row with quantity > 0 and its current unit value (None = cannot be sold)."""
    rows = stock_rows(db, faction.id)
    if not rows:
        return []
    _reason, region_id = _ticking(db, faction)
    q = quotes(db, region_id, [i for i, _n in rows])
    out = []
    for iid, n in rows:
        quote = q.get(iid)
        out.append({"item_id": iid, "name": quote.name if quote else None, "quantity": n,
                    "unit_value": quote.unit_value if quote is not None and quote.reason is None else None})
    return out
