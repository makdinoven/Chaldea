"""FEAT-193 guild orders — DB layer (sync SQLAlchemy). Pure maths: ``econ_guild``.

* **region step** (3.2 / 3.3) — called by ``econ_tick._process_region`` inside its SAVEPOINT: the guild's budget for
  the recount (``econ_regions.guild_budget`` / ``guild_food_budget``) and the refresh / insert / close of the region's
  order rows (``econ_guild_orders``); the open rows were locked earlier by :func:`lock_open_orders`;
* **sweep** (3.2) — after the region loop: orders of regions that left the economy are closed, their budgets zeroed,
  guild XP day rows older than :data:`XP_DAYS_KEEP` deleted;
* **merchant quotes** (3.5) — the best bid / cheapest ask of the region's merchants (living and legacy, not dead) for
  the price floor / cap (plain reads, no locks);
* **player flow at the «Гильдия торговцев»** (3.6 / 3.6a) — gate, view, hand-in (items out of ``character_inventory``
  + stock up + order / budget down + XP day counter + ``guild_order`` posting + ``character_attributes`` XP in ONE
  transaction, the router commits);
* **admin read** (3.10) and the region-card list (3.9).

Lock order (3.7, global): ``econ_regions → econ_region_goods → econ_region_events (asc id) → econ_caravans (asc id) →
econ_guild_orders (asc id) → econ_guild_xp_days → econ_mint_seasons → npc_shop_items (asc id) → econ_banks →
bank_deposits → bank_loans → character_inventory (asc id) → characters (asc id) → econ_accounts (asc id) →
character_attributes``. Hand-in: ``econ_regions → econ_region_goods(group) → econ_guild_orders(open row) →
econ_guild_xp_days(character, day) → character_inventory → characters → econ_accounts → character_attributes``; the
merchants' ``npc_shop_items`` / ``characters`` rows are read without locks. Order rows are INSERTed only by the region
step under the region's ``econ_regions`` lock; ``ensure_xp_day_row`` INSERTs run in their own short transaction.

Cross-ownership: the hand-in writes ``character_inventory`` (owned by inventory-service) and
``character_attributes.passive_experience`` (owned by character-attributes-service) directly, in the same DB
transaction as the ledger posting — the accepted precedents of the mint (FEAT-191) and ``add_rewards_to_character``.
"""

import dataclasses
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import activity_lock
import econ_core as core
import econ_guild
import econ_ledger
import econ_sim
import models
from economy_crud import EconomyApiError
from economy_mint_crud import take_plain_stacks
import reputation_core
import reputation_crud

logger = logging.getLogger("character-service.guild")

SOURCE_SERVICE = "character-service"
GUILD_ROLE = "guild"
NPC_DEAD = "dead"
KEY_HAND_IN = "guild"               # guild:{character_id}:{request_id}
XP_DAYS_KEEP = 7                    # guild XP day rows older than this are deleted by the sweep
CARD_MAX_GROUPS = 12
QUEST_ITEM_OBJECTIVES = ("collect", "deliver")

# Russian texts (contract 3.6 — tests assert them)
MSG_CHARACTER_NOT_FOUND = "Персонаж не найден"
MSG_NOT_OWNER = "Вы можете управлять только своими персонажами"
MSG_NOT_PLAYER = "Гильдией пользуются только персонажи игроков"
MSG_GUILD_NOT_FOUND = "Гильдия торговцев не найдена"
MSG_GUILD_DEAD = "Гильдия торговцев закрыта — её представитель больше не принимает посетителей"
MSG_WRONG_LOCATION = "Подойдите к представителю гильдии — он в другой локации"
MSG_GATE_CLOSED = "Нужен пост-намерение «Диалог с НПС» с этим персонажем"
MSG_GATE_UNAVAILABLE = "Не удалось проверить обращение к гильдии, попробуйте позже"
MSG_GUILD_CLOSED = "Гильдия не принимает заказы: {reason}"
MSG_NO_ORDER = "Гильдии сейчас не нужны такие товары — заказ закрыт или выполнен"
MSG_NO_MONEY = "У жителей сейчас нет денег на этот заказ — загляните после пересчёта"
MSG_ITEM_NOT_ACCEPTED = "Гильдия не принимает этот предмет (свитки, рецепты, легендарное и выше — вне рынка)"
MSG_QUEST_ITEM = "Квестовые предметы гильдия не принимает"
MSG_NOT_WORTH = "Гильдия не может заплатить за этот предмет: торговцы региона продают его слишком дёшево"
MSG_NOT_ENOUGH = "Не хватает: {name} — нужно {need}, есть {have} (принимаются только обычные стопки)"
MSG_PARTIAL = "Принято {accepted} из {requested} шт. — {why}, остальное осталось у вас. Получено {total}"
MSG_SUCCESS = "Гильдия приняла {name} × {accepted} — получено {total}"
MSG_XP_SUFFIX = " и {xp} опыта"
MSG_XP_CAPPED = " (дневной лимит опыта гильдии исчерпан)"
MSG_DUPLICATE = "Операция уже выполнена"
MSG_RETRY = "Не удалось выполнить операцию, попробуйте ещё раз"
MSG_RETRY_MONEY = "Деньги жителей изменились во время сделки, попробуйте ещё раз"
MSG_UNKNOWN_GROUP = "Неизвестная группа товаров"

WHY_VOLUME = "заказ почти закрыт"
WHY_MONEY = "у жителей не хватает денег"

# closed reasons (MSG_GUILD_CLOSED / view closed_reason)
REASON_NOT_PARTICIPATING = "регион не участвует в экономике"
REASON_DISABLED = "заказы гильдии выключены"

REFUSAL_TEXTS = {
    econ_guild.REFUSE_OFF_MARKET: MSG_ITEM_NOT_ACCEPTED,
    econ_guild.REFUSE_QUEST: MSG_QUEST_ITEM,
    econ_guild.REFUSE_NO_ORDER: MSG_NO_ORDER,
    econ_guild.REFUSE_NOT_WORTH: MSG_NOT_WORTH,
}
REFUSAL_STATUS = {
    econ_guild.REFUSE_OFF_MARKET: 400,
    econ_guild.REFUSE_QUEST: 400,
    econ_guild.REFUSE_NO_ORDER: 409,
    econ_guild.REFUSE_NOT_WORTH: 400,
}

SQL_QUEST_ITEMS = (
    "SELECT DISTINCT target_id FROM quest_objectives WHERE target_id IN ({ph}) "
    "AND objective_type IN ('collect', 'deliver')"
)
# NPCs with an active shop row, with their place (econ_core.merchant_status input columns).
SQL_MERCHANT_PLACES = (
    "SELECT c.id, c.is_npc, c.npc_status, c.current_location_id, l.marker_type FROM characters c "
    "LEFT JOIN Locations l ON l.id = c.current_location_id "
    "WHERE c.id IN (SELECT DISTINCT npc_id FROM npc_shop_items WHERE is_active = 1) ORDER BY c.id"
)


def now_utc() -> datetime:
    """Naive UTC without microseconds."""
    return datetime.utcnow().replace(microsecond=0)


def today_utc(now: Optional[datetime] = None) -> date:
    return (now or now_utc()).date()


def _for_update(db: Session) -> bool:
    return core.supports_for_update(db.get_bind().dialect.name)


def _i(value) -> int:
    return int(value or 0)


def _f(value) -> float:
    return float(value or 0)


def _dec3(value) -> Decimal:
    return econ_guild.round3(value)


def _fmt(db: Session, n: int) -> str:
    return core.format_currency(int(n), econ_ledger.get_currency_forms(db))


def load_params(db: Session) -> econ_sim.SimParams:
    import econ_tick  # late: econ_tick imports this module lazily for the tick step
    return econ_tick.load_params(db)


def _balance(db: Session, ref: core.AccountRef) -> int:
    value = db.execute(text("SELECT balance FROM econ_accounts WHERE kind = :kind AND ref_id = :ref_id"),
                       {"kind": ref.kind, "ref_id": ref.ref_id}).scalar()
    return _i(value)


def guild_available(db: Session) -> bool:
    """True when migration 036 is applied (the tick tolerates its absence)."""
    names = set(sa_inspect(db.get_bind()).get_table_names())
    return "econ_guild_orders" in names and "econ_guild_xp_days" in names


def _participates(region: Optional["models.EconRegion"]) -> bool:
    return region is not None and region.template_code is not None and _i(region.population) > 0


def _open_key(region_id: int, group_code: str) -> str:
    return f"r{int(region_id)}:{group_code}"


# =====================================================================================================================
# Region step (3.2 / 3.3) — inside econ_tick._process_region; the caller commits
# =====================================================================================================================

@dataclass
class StepOutcome:
    opened: int = 0
    refreshed: int = 0
    closed: int = 0
    failed: bool = False


def lock_open_orders(session: Session, region_id: int, for_update: bool) -> List["models.EconGuildOrder"]:
    """The region's open order rows, ascending id, FOR UPDATE (right after the event rows, lock order 3.7)."""
    query = (session.query(models.EconGuildOrder)
             .filter(models.EconGuildOrder.region_id == int(region_id),
                     models.EconGuildOrder.status == econ_guild.STATUS_OPEN)
             .order_by(models.EconGuildOrder.id))
    return (query.with_for_update() if for_update else query).all()


def inbound_units(session: Session, region_id: int) -> Dict[str, float]:
    """{group_code: units} of caravans on the road to the region (decision 6)."""
    rows = session.execute(text(
        "SELECT group_code, SUM(units) FROM econ_caravans WHERE status = 'in_transit' AND to_region_id = :r "
        "GROUP BY group_code"), {"r": int(region_id)}).fetchall()
    return {r[0]: _f(r[1]) for r in rows}


def _close(order: "models.EconGuildOrder", reason: str, *, run_id: Optional[int], now: datetime,
           status: str = econ_guild.STATUS_CLOSED) -> None:
    order.status = status
    order.open_key = None
    order.close_reason = reason
    order.closed_at = now
    order.closed_run_id = run_id
    order.updated_at = now


def guild_step(session: Session, *, run_id: int, region_id: int, region: "models.EconRegion",
               goods_rows: Sequence["models.EconRegionGood"], groups: Mapping[str, econ_sim.GroupDef],
               params: econ_sim.SimParams, orders: Sequence["models.EconGuildOrder"], now: datetime) -> StepOutcome:
    """Budget + order recompute of one region (3.3). Reads the FINAL stock of the step (after merchants) and the
    balances after every posting of the step. No commit."""
    outcome = StepOutcome()
    purse = _balance(session, core.AccountRef.purse(region_id))
    treasury = _balance(session, core.AccountRef.region(region_id))
    budget, food_budget = econ_guild.budgets(purse, treasury, params)
    region.guild_budget = budget
    region.guild_food_budget = food_budget

    inbound = inbound_units(session, region_id)
    shortages = []
    prices: Dict[str, Decimal] = {}
    for row in goods_rows:
        group = groups.get(row.group_code)
        if group is None:
            continue
        prices[row.group_code] = Decimal(str(row.price_mult or 1))
        shortages.append(econ_guild.GroupShortage(
            group_code=row.group_code, stock=_f(row.stock), norm_stock=_f(row.norm_stock),
            price_mult=_f(row.price_mult), base_price=float(group.base_price), is_food=bool(group.is_food),
            inbound=inbound.get(row.group_code, 0.0)))
    plans = econ_guild.plan_orders(shortages, params, budget, food_budget)

    markup = Decimal(str(params.guild_markup_pct)).quantize(Decimal("0.01"))
    open_rows = {o.group_code: o for o in orders if o.status == econ_guild.STATUS_OPEN}
    for code, plan in plans.items():
        existing = open_rows.pop(code, None)
        if plan.open:
            volume = _dec3(plan.volume)
            mult = prices[code].quantize(Decimal("0.001"))
            if existing is not None:
                existing.units_total = volume
                existing.units_left = volume
                existing.price_mult = mult
                existing.markup_pct = markup
                existing.last_run_id = run_id
                existing.updated_at = now
                outcome.refreshed += 1
            else:
                session.add(models.EconGuildOrder(
                    region_id=int(region_id), group_code=code, open_key=_open_key(region_id, code),
                    status=econ_guild.STATUS_OPEN, units_total=volume, units_left=volume, units_filled=Decimal("0"),
                    price_mult=mult, markup_pct=markup, pieces=0, paid_total=0, paid_treasury=0, hand_ins=0,
                    opened_run_id=run_id, last_run_id=run_id, opened_at=now, updated_at=now))
                outcome.opened += 1
        elif existing is not None:
            _close(existing, plan.close_reason or econ_guild.CLOSE_NO_SHORTAGE, run_id=run_id, now=now)
            outcome.closed += 1
    for leftover in open_rows.values():          # group without a goods row in the region any more
        _close(leftover, econ_guild.CLOSE_DISABLED, run_id=run_id, now=now)
        outcome.closed += 1
    session.flush()
    return outcome


def sweep(session: Session, run_id: int, now: datetime) -> int:
    """Close the open orders of regions that left the economy, zero their budgets, drop old XP day rows (3.2).
    Regions first (ascending), then their orders. No commit; returns the number of orders closed."""
    session.execute(text(
        "UPDATE econ_regions SET guild_budget = 0, guild_food_budget = 0 "
        "WHERE (template_code IS NULL OR population <= 0) AND (guild_budget <> 0 OR guild_food_budget <> 0)"))
    ids = [int(r[0]) for r in session.execute(text(
        "SELECT o.id FROM econ_guild_orders o LEFT JOIN econ_regions e ON e.region_id = o.region_id "
        "WHERE o.status = :open AND (e.region_id IS NULL OR e.template_code IS NULL OR e.population <= 0) "
        "ORDER BY o.id"), {"open": econ_guild.STATUS_OPEN}).fetchall()]
    if ids:
        placeholders, params = core.in_params("o", ids)
        session.execute(text(
            "UPDATE econ_guild_orders SET status = :closed, open_key = NULL, close_reason = :reason, "
            f"closed_at = :now, closed_run_id = :run, updated_at = :now WHERE id IN ({placeholders})"),
            {"closed": econ_guild.STATUS_CLOSED, "reason": econ_guild.CLOSE_REGION_LEFT, "now": now,
             "run": int(run_id), **params})
    session.execute(text("DELETE FROM econ_guild_xp_days WHERE day < :cutoff"),
                    {"cutoff": today_utc(now) - timedelta(days=XP_DAYS_KEEP)})
    return len(ids)


# =====================================================================================================================
# Merchant quotes (3.5) — plain reads
# =====================================================================================================================

@dataclass(frozen=True)
class Quote:
    best_bid: int = 0                     # the most a merchant of the region pays for the item now (0 = nobody)
    cheapest_ask: Optional[int] = None    # the cheapest price a merchant of the region sells it at (None = nobody)


def _item_markets(db: Session, item_ids: Iterable[int]) -> Dict[int, core.ItemMarket]:
    ids = sorted({int(i) for i in item_ids})
    if not ids:
        return {}
    placeholders, params = core.in_params("i", ids)
    rows = db.execute(text(core.sql_item_market(placeholders)), params).fetchall()
    return {int(r[0]): core.item_market_from_row(r) for r in rows}


def _region_market(db: Session, region_id: int) -> Tuple[Dict[str, Decimal], Dict[str, int]]:
    rows = db.execute(text(core.SQL_REGION_MARKET), {"region_id": int(region_id)}).fetchall()
    return core.region_goods_from_rows(rows)


def region_merchants(db: Session, region_id: int) -> List[Tuple[int, bool]]:
    """[(npc_id, living)] of the not-dead NPCs with active shop rows whose location resolves to the region
    (living merchants and legacy ones located there, e.g. in a dungeon of the region)."""
    rows = db.execute(text(SQL_MERCHANT_PLACES)).fetchall()
    region_row = db.execute(text(core.SQL_REGION_ECON), {"region_id": int(region_id)}).first()
    places: Dict[int, Optional[int]] = {}
    result = []
    for row in rows:
        location_id = row[3]
        if not row[1] or row[2] == NPC_DEAD or not location_id:
            continue
        if location_id not in places:
            places[location_id] = econ_ledger.resolve_location(db, int(location_id))[0]
        if places[location_id] is None or int(places[location_id]) != int(region_id):
            continue
        living, _reason = core.merchant_status(tuple(row), region_row)
        result.append((int(row[0]), living))
    return result


def region_quotes(db: Session, region_id: int, item_markets: Mapping[int, core.ItemMarket]) -> Dict[int, Quote]:
    """{item_id: Quote} for the given items over the region's merchants (3.5)."""
    if not item_markets:
        return {}
    merchants = region_merchants(db, region_id)
    if not merchants:
        return {item_id: Quote() for item_id in item_markets}
    placeholders, params = core.in_params("n", [npc_id for npc_id, _ in merchants])
    rows = db.execute(text(core.sql_lock_shop_rows(placeholders, for_update=False)), params).fetchall()
    rows_by_npc: Dict[int, List[tuple]] = {}
    for r in rows:
        rows_by_npc.setdefault(int(r[1]), []).append(tuple(r))
    items = dict(item_markets)
    missing = {int(r[2]) for r in rows} - set(items)
    items.update(_item_markets(db, missing))
    mults, bases = _region_market(db, region_id)
    params_row = db.execute(text(core.SQL_SIM_PARAMS)).first()
    bid_share = core.merchant_bid_share(params_row[0] if params_row is not None else None)

    out: Dict[int, Quote] = {}
    for item_id, item in item_markets.items():
        best_bid = 0
        cheapest: Optional[int] = None
        for npc_id, living in merchants:
            npc_rows = rows_by_npc.get(npc_id, [])
            row = next((r for r in npc_rows if int(r[2]) == int(item_id)), None)
            if row is not None and row[8]:
                stock = core.effective_shop_stock(living, row[5])
                if not (row[7] == core.SHOP_ORIGIN_PLAYER and not stock):
                    ask = core.shop_row_prices(living, item, row[3], row[4], mults)["ask"]
                    cheapest = ask if cheapest is None else min(cheapest, ask)
            buys = core.merchant_buys_groups(npc_rows, items) if living else []
            bid = core.shop_row_bid(living, item, row, buys, mults, bases, bid_share)
            best_bid = max(best_bid, bid)
        out[int(item_id)] = Quote(best_bid=best_bid, cheapest_ask=cheapest)
    return out


# =====================================================================================================================
# Player API — «Гильдия торговцев» (3.6)
# =====================================================================================================================

@dataclass(frozen=True)
class GuildContext:
    character_id: int
    user_id: int
    npc_id: int
    npc_name: str
    location_id: int
    region_id: Optional[int] = None


def _player_character(db: Session, character_id: int, user_id: int) -> "models.Character":
    character = db.query(models.Character).filter(models.Character.id == int(character_id)).first()
    if character is None:
        raise EconomyApiError(404, MSG_CHARACTER_NOT_FOUND)
    if character.user_id != user_id:
        raise EconomyApiError(403, MSG_NOT_OWNER)
    if character.is_npc:
        raise EconomyApiError(403, MSG_NOT_PLAYER)
    return character


def resolve_guild(db: Session, npc_id: int, character_id: int, user_id: int, *, write: bool) -> GuildContext:
    """Steps 1–4 (banker / minter order): owner + player, guild NPC exists / role / alive, activity lock (POST),
    location."""
    character = _player_character(db, character_id, user_id)
    npc = db.query(models.Character).filter(models.Character.id == int(npc_id)).first()
    if npc is None or not npc.is_npc or npc.npc_role != GUILD_ROLE:
        raise EconomyApiError(404, MSG_GUILD_NOT_FOUND)
    if npc.npc_status == NPC_DEAD:
        raise EconomyApiError(409, MSG_GUILD_DEAD)
    if write:
        message = activity_lock.lock_message(activity_lock.lock_for_character(character))
        if message:
            raise EconomyApiError(409, message)
    if npc.current_location_id is None or character.current_location_id != npc.current_location_id:
        raise EconomyApiError(400, MSG_WRONG_LOCATION)
    return GuildContext(character_id=int(character.id), user_id=int(user_id), npc_id=int(npc.id),
                        npc_name=npc.name, location_id=int(npc.current_location_id))


def guild_context(db: Session, npc_id: int, character_id: int, user_id: int, *, write: bool) -> GuildContext:
    """Steps 1–4 + 6: the context with the NPC's region (None when the location resolves to no region)."""
    ctx = resolve_guild(db, npc_id, character_id, user_id, write=write)
    region_id, _country_id = econ_ledger.resolve_location(db, ctx.location_id)
    ctx = dataclasses.replace(ctx, region_id=int(region_id) if region_id else None)
    if write:
        # FEAT-197: the NPC reputation gate, then «Вне закона» closes the guild (§3.14 A4)
        lock = reputation_crud.guild_lock_reason(db, ctx.character_id, ctx.npc_id, ctx.region_id)
        if lock:
            raise EconomyApiError(403, lock)
    return ctx


def closed_reason(region: Optional["models.EconRegion"], params: econ_sim.SimParams) -> Optional[str]:
    if not _participates(region):
        return REASON_NOT_PARTICIPATING
    if not int(params.guild_enabled):
        return REASON_DISABLED
    return None


def _plain_bag(db: Session, character_id: int) -> Dict[int, int]:
    rows = db.execute(text(
        "SELECT item_id, SUM(quantity) FROM character_inventory WHERE character_id = :c "
        "AND COALESCE(enhancement_points_spent, 0) = 0 AND socketed_gems IS NULL AND current_durability IS NULL "
        "GROUP BY item_id ORDER BY item_id"), {"c": int(character_id)}).fetchall()
    return {int(r[0]): _i(r[1]) for r in rows if _i(r[1]) > 0}


def quest_item_ids(db: Session, item_ids: Iterable[int]) -> set:
    ids = sorted({int(i) for i in item_ids})
    if not ids:
        return set()
    placeholders, params = core.in_params("q", ids)
    rows = db.execute(text(SQL_QUEST_ITEMS.format(ph=placeholders)), params).fetchall()
    return {int(r[0]) for r in rows}


def _groups(db: Session) -> Dict[str, "models.EconGoodsGroup"]:
    return {g.code: g for g in db.query(models.EconGoodsGroup)
            .order_by(models.EconGoodsGroup.sort_order, models.EconGoodsGroup.code).all()}


def _wallet(db: Session, character_id: int) -> int:
    return _i(db.execute(text("SELECT currency_balance FROM characters WHERE id = :id"),
                         {"id": int(character_id)}).scalar())


def xp_used_today(db: Session, character_id: int, day: date) -> int:
    return _i(db.execute(text("SELECT xp FROM econ_guild_xp_days WHERE character_id = :c AND day = :d"),
                         {"c": int(character_id), "d": day}).scalar())


def money_left(db: Session, region: "models.EconRegion") -> Tuple[int, int]:
    """(purse_left, treasury_left): the stored budgets bounded by the live balances (no account locks)."""
    purse = _balance(db, core.AccountRef.purse(int(region.region_id)))
    treasury = _balance(db, core.AccountRef.region(int(region.region_id)))
    return (min(_i(region.guild_budget), max(0, purse)), min(_i(region.guild_food_budget), max(0, treasury)))


def xp_rate(params: econ_sim.SimParams, quote: Quote) -> float:
    """5 % for items a merchant of the region sells, else 10 % (3.6a)."""
    if quote.cheapest_ask is not None:
        return float(params.guild_xp_per_mark_merchant_items)
    return float(params.guild_xp_per_mark)


def _filled_pct(order: "models.EconGuildOrder") -> int:
    total = Decimal(str(order.units_total or 0))
    if total <= 0:
        return 100
    done = total - Decimal(str(order.units_left or 0))
    return max(0, min(100, int(done * 100 / total)))


def build_view(db: Session, ctx: GuildContext, *, xp_multiplier: float = 1.0,
               params: Optional[econ_sim.SimParams] = None, now: Optional[datetime] = None) -> dict:
    """``GuildView`` (read-only; no budget / purse / treasury numbers exposed)."""
    params = params or load_params(db)
    region = db.get(models.EconRegion, ctx.region_id) if ctx.region_id else None
    region_name = (db.execute(text("SELECT name FROM Regions WHERE id = :r"), {"r": ctx.region_id}).scalar()
                   if ctx.region_id else None)
    reason = closed_reason(region, params)
    reputation_lock = reputation_crud.guild_lock_reason(db, ctx.character_id, ctx.npc_id, ctx.region_id)
    if reputation_lock and reason is None:
        reason = reputation_lock                                 # FEAT-197: no orders shown to a locked character
    used = xp_used_today(db, ctx.character_id, today_utc(now))
    cap = _i(params.guild_xp_daily_cap)
    view = {
        "npc_id": ctx.npc_id,
        "npc_name": ctx.npc_name,
        "region_id": ctx.region_id,
        "region_name": region_name,
        "working": reason is None,
        "closed_reason": reason,
        "markup_pct": float(params.guild_markup_pct),
        "orders": [],
        "offers": [],
        "refused": [],
        "xp": {
            "per_mark": float(params.guild_xp_per_mark),
            "per_mark_merchant_items": float(params.guild_xp_per_mark_merchant_items),
            "daily_cap": cap,
            "left_today": max(0, cap - used),
            "multiplier": float(xp_multiplier or 1.0),
        },
        "wallet": _wallet(db, ctx.character_id),
        "reputation_lock": reputation_lock,
    }
    if reason is not None:
        return view

    groups = _groups(db)
    orders = (db.query(models.EconGuildOrder)
              .filter(models.EconGuildOrder.region_id == ctx.region_id,
                      models.EconGuildOrder.status == econ_guild.STATUS_OPEN)
              .order_by(models.EconGuildOrder.id).all())
    order_rank = {code: i for i, code in enumerate(groups)}
    orders.sort(key=lambda o: (order_rank.get(o.group_code, len(order_rank)), o.id))
    purse_left, treasury_left = money_left(db, region)
    by_group: Dict[str, "models.EconGuildOrder"] = {}
    for order in orders:
        group = groups.get(order.group_code)
        is_food = bool(group.is_food) if group is not None else False
        by_group[order.group_code] = order
        view["orders"].append({
            "order_id": int(order.id),
            "group_code": order.group_code,
            "group_name": group.name if group is not None else order.group_code,
            "is_food": is_food,
            "units_total": _f(order.units_total),
            "units_left": _f(order.units_left),
            "filled_pct": _filled_pct(order),
            "payable": econ_guild.payable(is_food, purse_left, treasury_left),
        })
    if not by_group:
        return view

    bag = _plain_bag(db, ctx.character_id)
    markets = _item_markets(db, bag)
    wanted = {item_id: m for item_id, m in markets.items() if m.group in by_group}
    if not wanted:
        return view
    quests = quest_item_ids(db, wanted)
    quotes = region_quotes(db, ctx.region_id, wanted)
    for item_id, market in sorted(wanted.items(), key=lambda kv: (kv[1].name or "", kv[0])):
        order = by_group[market.group]
        group = groups.get(market.group)
        group_base = _i(group.base_price) if group is not None else 0
        is_food = bool(group.is_food) if group is not None else False
        item_base = core.item_base_price(market.price, group_base)
        per_item = core.units_per_item(item_base, group_base)
        quote = quotes.get(item_id, Quote())
        price = None
        capped = False
        if not market.off_market and item_id not in quests:
            priced = econ_guild.unit_price(item_base, order.price_mult, order.markup_pct, quote.cheapest_ask,
                                           quote.best_bid)
            price, capped = (priced.unit_price if per_item > 0 else 0), priced.capped_by_merchants
        code = econ_guild.refusal(market.group, market.off_market, item_id in quests,
                                  _f(order.units_left) > 0, price)
        base = {"item_id": item_id, "name": market.name, "image": market.image, "group_code": market.group,
                "have": bag.get(item_id, 0)}
        if code is not None:
            view["refused"].append({**base, "reason": REFUSAL_TEXTS[code]})
            continue
        view["offers"].append({
            **base,
            "order_id": int(order.id),
            "unit_price": int(price),
            "units_per_item": round(per_item, 3),
            "max_accept": econ_guild.max_accept(bag.get(item_id, 0), order.units_left, per_item, price,
                                                purse_left, treasury_left, is_food),
            "capped_by_merchants": bool(capped),
            "xp_rate": xp_rate(params, quote),
        })
    return view


def ensure_xp_day_row(db: Session, character_id: int, day: Optional[date] = None) -> None:
    """Create the zero XP day row in its OWN short transaction (commits / rolls back ``db``)."""
    day = day or today_utc()
    db.rollback()
    exists = db.execute(text("SELECT 1 FROM econ_guild_xp_days WHERE character_id = :c AND day = :d"),
                        {"c": int(character_id), "d": day}).first()
    if exists is not None:
        db.rollback()
        return
    try:
        db.execute(text("INSERT INTO econ_guild_xp_days (character_id, day, xp) VALUES (:c, :d, 0)"),
                   {"c": int(character_id), "d": day})
        db.commit()
    except IntegrityError:
        db.rollback()       # created by a concurrent request


def _lock_one(db: Session, query):
    return (query.with_for_update() if _for_update(db) else query).populate_existing().first()


def hand_in(db: Session, ctx: GuildContext, body, *, xp_multiplier: float = 1.0,
            now: Optional[datetime] = None) -> dict:
    """The player flow (3.6 steps 1–10a), all in the caller's transaction; the router commits.

    The XP day row must already exist (``ensure_xp_day_row`` before the transaction)."""
    now = now or now_utc()
    day = today_utc(now)
    params = load_params(db)
    if not ctx.region_id:
        raise EconomyApiError(409, MSG_GUILD_CLOSED.format(reason=REASON_NOT_PARTICIPATING))
    region_id = int(ctx.region_id)
    key = f"{KEY_HAND_IN}:{ctx.character_id}:{body.request_id}"

    # 1. region row lock + participation / switch
    region = _lock_one(db, db.query(models.EconRegion).filter(models.EconRegion.region_id == region_id))
    reason = closed_reason(region, params)
    if reason is not None:
        raise EconomyApiError(409, MSG_GUILD_CLOSED.format(reason=reason))
    # 2. duplicate pre-check
    if db.execute(text(core.SQL_SELECT_OPERATION_BY_KEY), {"key": key}).first() is not None:
        raise EconomyApiError(409, MSG_DUPLICATE)

    # 3. item market + rules that need no order
    item_id = int(body.item_id)
    quantity = int(body.quantity)
    market = _item_markets(db, [item_id]).get(item_id)
    if market is None or market.group is None or market.off_market:
        raise EconomyApiError(400, MSG_ITEM_NOT_ACCEPTED)
    if item_id in quest_item_ids(db, [item_id]):
        raise EconomyApiError(400, MSG_QUEST_ITEM)
    group = db.get(models.EconGoodsGroup, market.group)
    if group is None:
        raise EconomyApiError(400, MSG_ITEM_NOT_ACCEPTED)
    group_base = _i(group.base_price)
    is_food = bool(group.is_food)

    # 4. goods row -> open order row
    goods = _lock_one(db, db.query(models.EconRegionGood).filter(models.EconRegionGood.region_id == region_id,
                                                                  models.EconRegionGood.group_code == market.group))
    order = _lock_one(db, db.query(models.EconGuildOrder).filter(
        models.EconGuildOrder.open_key == _open_key(region_id, market.group)))
    if goods is None or order is None or order.status != econ_guild.STATUS_OPEN or _f(order.units_left) <= 0:
        raise EconomyApiError(409, MSG_NO_ORDER)

    # 5. price (3.5)
    item_base = core.item_base_price(market.price, group_base)
    per_item = core.units_per_item(item_base, group_base)
    quote = region_quotes(db, region_id, {item_id: market}).get(item_id, Quote())
    priced = econ_guild.unit_price(item_base, order.price_mult, order.markup_pct, quote.cheapest_ask, quote.best_bid)
    price = priced.unit_price
    if per_item <= 0 or price <= 0:
        raise EconomyApiError(400, MSG_NOT_WORTH)

    # 6-7. money (plain reads, no account pre-lock) and acceptance
    purse_left, treasury_left = money_left(db, region)
    acc = econ_guild.accept(quantity, order.units_left, per_item, price, purse_left, treasury_left, is_food)
    if acc.accepted <= 0:
        raise EconomyApiError(409, MSG_NO_MONEY)
    accepted = acc.accepted

    # 8. items out of the bag (not-enough checked against the REQUESTED quantity)
    name = market.name or f"предмет #{item_id}"
    take_plain_stacks(db, ctx.character_id, item_id, accepted, name, need=quantity, not_enough=MSG_NOT_ENOUGH)

    # 9. stock / order / budget
    units = _dec3(Decimal(str(per_item)) * accepted)
    goods.stock = _dec3(Decimal(str(goods.stock or 0)) + units)
    left = Decimal(str(order.units_left or 0)) - units
    order.units_left = _dec3(max(Decimal(0), left))
    order.units_filled = _dec3(Decimal(str(order.units_filled or 0)) + units)
    order.pieces = _i(order.pieces) + accepted
    order.paid_total = _i(order.paid_total) + acc.total
    order.paid_treasury = _i(order.paid_treasury) + acc.paid_treasury
    order.hand_ins = _i(order.hand_ins) + 1
    order.updated_at = now
    if order.units_left <= 0:
        _close(order, econ_guild.CLOSE_FILLED, run_id=None, now=now, status=econ_guild.STATUS_FILLED)
    region.guild_budget = max(0, _i(region.guild_budget) - acc.paid_purse)
    region.guild_food_budget = max(0, _i(region.guild_food_budget) - acc.paid_treasury)

    # 9a. XP day counter (3.6a)
    rate = xp_rate(params, quote)
    has_attributes = db.execute(text("SELECT 1 FROM character_attributes WHERE character_id = :c"),
                                {"c": ctx.character_id}).first() is not None
    xp_day = _lock_one(db, db.query(models.EconGuildXpDay).filter(
        models.EconGuildXpDay.character_id == ctx.character_id, models.EconGuildXpDay.day == day))
    used = _i(xp_day.xp) if xp_day is not None else 0
    xp = econ_guild.guild_xp(acc.total, rate, _i(params.guild_xp_daily_cap), used, xp_multiplier)
    if not has_attributes or xp_day is None:
        if xp.base > 0:
            logger.warning("guild XP not granted: character=%s attributes=%s day_row=%s", ctx.character_id,
                           has_attributes, xp_day is not None)
        xp = econ_guild.GuildXp(0, 0, xp.capped)
    if xp_day is not None and xp.base > 0:
        xp_day.xp = used + xp.base
    db.flush()

    # 10. the posting — the LAST money step
    character = core.AccountRef.character(ctx.character_id)
    try:
        posted = econ_ledger.post_operation(
            db, op_type=core.OP_GUILD_ORDER,
            legs=[core.Leg(core.AccountRef.purse(region_id), character, acc.paid_purse),
                  core.Leg(core.AccountRef.region(region_id), character, acc.paid_treasury)],
            source_service=SOURCE_SERVICE, location_id=ctx.location_id, region_id=region_id,
            actor_user_id=ctx.user_id, apply_tax=False, idempotency_key=key,
            metadata={"order_id": int(order.id), "npc_id": ctx.npc_id, "item_id": item_id, "item_name": market.name,
                      "group": market.group, "quantity": accepted, "requested": quantity, "unit_price": price,
                      "units": str(units), "price_mult": str(order.price_mult), "markup_pct": str(order.markup_pct),
                      "best_bid": quote.best_bid, "cheapest_ask": quote.cheapest_ask,
                      "paid_purse": acc.paid_purse, "paid_treasury": acc.paid_treasury,
                      "xp_base": xp.base, "xp": xp.granted, "xp_rate": rate,
                      "xp_multiplier": float(xp_multiplier or 1.0)},
        )
    except core.DuplicateOperation:
        raise EconomyApiError(409, MSG_DUPLICATE)
    except core.InsufficientFunds:
        raise EconomyApiError(409, MSG_RETRY_MONEY)

    # 10a. XP into character_attributes (after the ledger, like add_rewards_to_character)
    if xp.granted > 0:
        db.execute(text("UPDATE character_attributes SET passive_experience = COALESCE(passive_experience, 0) + :x "
                        "WHERE character_id = :c"), {"x": xp.granted, "c": ctx.character_id})

    # 10b. FEAT-197 reputation (same transaction, same idempotency key as the posting; daily cap per region)
    try:
        rep = reputation_crud.apply_reputation(
            db, character_id=ctx.character_id, region_id=region_id, action=reputation_core.ACTION_GUILD,
            idem_key=key, now=now)
    except reputation_crud.ReputationError as exc:      # unknown region row: the delivery itself still counts
        logger.warning("guild reputation skipped: character=%s region=%s: %s", ctx.character_id, region_id,
                       exc.detail)
        rep = reputation_crud.ApplyResult()

    total_fmt = _fmt(db, acc.total)
    partial = accepted < quantity
    if partial:
        why = WHY_VOLUME if acc.limited_by == econ_guild.LIMIT_VOLUME else WHY_MONEY
        message = MSG_PARTIAL.format(accepted=accepted, requested=quantity, why=why, total=total_fmt)
    else:
        message = MSG_SUCCESS.format(name=name, accepted=accepted, total=total_fmt)
    if xp.granted > 0:
        message += MSG_XP_SUFFIX.format(xp=xp.granted)
    elif xp.capped:
        message += MSG_XP_CAPPED
    return {
        "message": message,
        "operation_id": posted.operation_id,
        "quantity": accepted,
        "requested": quantity,
        "partial": partial,
        "unit_price": price,
        "total": acc.total,
        "xp": xp.granted,
        "xp_capped": bool(xp.capped),
        "wallet": posted.balances.get(ctx.character_id, _wallet(db, ctx.character_id)),
        "reputation_tier_changes": rep.tier_changes,     # popped by the router, published after the commit
    }


def passive_experience(db: Session, character_id: int) -> Optional[int]:
    row = db.execute(text("SELECT passive_experience FROM character_attributes WHERE character_id = :c"),
                     {"c": int(character_id)}).first()
    return _i(row[0]) if row is not None else None


# =====================================================================================================================
# Region card (3.9) — words only
# =====================================================================================================================

def guild_masters_by_region(db: Session, *, alive_only: bool) -> Dict[int, List[dict]]:
    """NPCs with the «Гильдия торговцев» role grouped by the region their location resolves to."""
    rows = db.execute(text(
        "SELECT c.id, c.name, c.npc_status, c.current_location_id, l.name FROM characters c "
        "LEFT JOIN Locations l ON l.id = c.current_location_id "
        "WHERE c.is_npc = 1 AND c.npc_role = :role AND c.current_location_id IS NOT NULL ORDER BY c.id"),
        {"role": GUILD_ROLE}).fetchall()
    places: Dict[int, Optional[int]] = {}
    result: Dict[int, List[dict]] = {}
    for npc_id, name, npc_status, location_id, location_name in rows:
        if alive_only and npc_status == NPC_DEAD:
            continue
        if location_id not in places:
            places[location_id] = econ_ledger.resolve_location(db, int(location_id))[0]
        region_id = places[location_id]
        if region_id:
            result.setdefault(int(region_id), []).append({
                "npc_id": int(npc_id), "name": name, "npc_status": npc_status or "alive",
                "location_name": location_name})
    return result


def card_guild_wants(db: Session, region_id: int) -> List[dict]:
    """Open, payable orders of the region — only when a living guild NPC stands in it. No numbers."""
    if not guild_available(db):
        return []
    region = db.get(models.EconRegion, int(region_id))
    if not _participates(region):
        return []
    rows = (db.query(models.EconGuildOrder)
            .filter(models.EconGuildOrder.region_id == int(region_id),
                    models.EconGuildOrder.status == econ_guild.STATUS_OPEN).all())
    if not rows or int(region_id) not in guild_masters_by_region(db, alive_only=True):
        return []
    groups = _groups(db)
    rank = {code: i for i, code in enumerate(groups)}
    budget, food_budget = _i(region.guild_budget), _i(region.guild_food_budget)
    wants = []
    for order in sorted(rows, key=lambda o: (rank.get(o.group_code, len(rank)), o.id)):
        group = groups.get(order.group_code)
        if group is None or _f(order.units_left) <= 0:
            continue
        if not econ_guild.payable(bool(group.is_food), budget, food_budget):
            continue
        wants.append({"group_code": order.group_code, "group_name": group.name})
    return wants[:CARD_MAX_GROUPS]


# =====================================================================================================================
# Admin (3.10)
# =====================================================================================================================

def params_out(params: econ_sim.SimParams) -> dict:
    return {
        "guild_enabled": int(params.guild_enabled),
        "guild_markup_pct": float(params.guild_markup_pct),
        "guild_open_threshold_pct": float(params.guild_open_threshold_pct),
        "guild_min_order_value": int(params.guild_min_order_value),
        "guild_purse_share": float(params.guild_purse_share),
        "guild_treasury_food_share": float(params.guild_treasury_food_share),
        "guild_xp_per_mark": float(params.guild_xp_per_mark),
        "guild_xp_per_mark_merchant_items": float(params.guild_xp_per_mark_merchant_items),
        "guild_xp_daily_cap": int(params.guild_xp_daily_cap),
    }


SQL_ORDER_LIST = (
    "SELECT o.id, o.region_id, r.name, o.group_code, g.name, o.status, o.close_reason, o.units_total, o.units_left, "
    "o.units_filled, o.price_mult, o.markup_pct, o.pieces, o.paid_total, o.paid_treasury, o.hand_ins, o.opened_at, "
    "o.updated_at, o.closed_at FROM econ_guild_orders o "
    "LEFT JOIN Regions r ON r.id = o.region_id LEFT JOIN econ_goods_groups g ON g.code = o.group_code"
)


def _order_out(r) -> dict:
    return {
        "id": int(r[0]), "region_id": int(r[1]), "region_name": r[2], "group_code": r[3], "group_name": r[4],
        "status": r[5], "close_reason": r[6], "units_total": _f(r[7]), "units_left": _f(r[8]),
        "units_filled": _f(r[9]), "price_mult": _f(r[10]), "markup_pct": _f(r[11]), "pieces": _i(r[12]),
        "paid_total": _i(r[13]), "paid_treasury": _i(r[14]), "hand_ins": _i(r[15]), "opened_at": r[16],
        "updated_at": r[17], "closed_at": r[18],
    }


def admin_view(db: Session, *, status: str = "open", region_id: Optional[int] = None,
               group_code: Optional[str] = None, limit: int = 50, offset: int = 0,
               now: Optional[datetime] = None) -> dict:
    now = now or now_utc()
    params = load_params(db)
    groups = _groups(db)
    if group_code and group_code not in groups:
        raise EconomyApiError(400, MSG_UNKNOWN_GROUP)

    # totals
    open_rows = db.execute(text(
        "SELECT o.units_left, o.price_mult, g.base_price FROM econ_guild_orders o "
        "LEFT JOIN econ_goods_groups g ON g.code = o.group_code WHERE o.status = :open"),
        {"open": econ_guild.STATUS_OPEN}).fetchall()
    left_value = sum(int(Decimal(str(r[0] or 0)) * Decimal(str(r[1] or 0)) * Decimal(str(r[2] or 0)))
                     for r in open_rows)
    since = now - timedelta(days=7)
    paid = db.execute(text(
        "SELECT COUNT(DISTINCT o.id), COALESCE(SUM(p.amount), 0) FROM econ_operations o "
        "JOIN econ_postings p ON p.operation_id = o.id WHERE o.op_type = :op AND o.created_at >= :since"),
        {"op": core.OP_GUILD_ORDER, "since": since}).first()
    xp_7d = _i(db.execute(text("SELECT COALESCE(SUM(xp), 0) FROM econ_guild_xp_days WHERE day >= :d"),
                          {"d": today_utc(now) - timedelta(days=6)}).scalar())

    # regions (participating) with budgets, open orders and guild masters
    masters = guild_masters_by_region(db, alive_only=False)
    open_counts = {int(r[0]): _i(r[1]) for r in db.execute(text(
        "SELECT region_id, COUNT(*) FROM econ_guild_orders WHERE status = :open GROUP BY region_id"),
        {"open": econ_guild.STATUS_OPEN}).fetchall()}
    regions = []
    for rid, name, budget, food_budget in db.execute(text(
            "SELECT e.region_id, r.name, e.guild_budget, e.guild_food_budget FROM econ_regions e "
            "JOIN Regions r ON r.id = e.region_id WHERE e.template_code IS NOT NULL AND e.population > 0 "
            "ORDER BY r.name, e.region_id")).fetchall():
        regions.append({"region_id": int(rid), "region_name": name, "guild_budget": _i(budget),
                        "guild_food_budget": _i(food_budget), "open_orders": open_counts.get(int(rid), 0),
                        "masters": masters.get(int(rid), [])})

    # orders list
    where, qp = [], {}
    if status == "closed":                       # «закрытые» tab: closed and filled alike
        where.append("o.status IN (:st_closed, :st_filled)")
        qp.update(st_closed=econ_guild.STATUS_CLOSED, st_filled=econ_guild.STATUS_FILLED)
    elif status and status != "all":
        where.append("o.status = :status")
        qp["status"] = status
    if region_id is not None:
        where.append("o.region_id = :rid")
        qp["rid"] = int(region_id)
    if group_code:
        where.append("o.group_code = :code")
        qp["code"] = group_code
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    total = _i(db.execute(text(f"SELECT COUNT(*) FROM econ_guild_orders o{clause}"), qp).scalar())
    rows = db.execute(text(SQL_ORDER_LIST + clause + " ORDER BY o.id DESC LIMIT :limit OFFSET :offset"),
                      {**qp, "limit": int(limit), "offset": int(offset)}).fetchall()
    return {
        "params": params_out(params),
        "totals": {"open": len(open_rows), "units_left_value": left_value, "paid_last_7d": _i(paid[1]),
                   "hand_ins_last_7d": _i(paid[0]), "xp_last_7d": xp_7d},
        "regions": regions,
        "total": total,
        "items": [_order_out(r) for r in rows],
    }
