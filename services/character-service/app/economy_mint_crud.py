"""FEAT-191 mint and season quota — DB layer (sync SQLAlchemy).

* **season period** — read straight from the shared ``game_time_config`` row (owned by locations-service, read-only),
  the math is in ``econ_mint`` (3.3);
* **capital / mint status** (3.4) — ``econ_mints`` override, else the single region of the country with the
  ``capital`` template; the mint works when the capital participates, has an ``ore_metal`` goods row, the country is
  enabled, the season limit > 0 and the calendar is available;
* **court mint** (3.6) — called by ``econ_tick._mint_pass``, one transaction per country;
* **player mint at a «Монетчик»** (3.8) — gate, view, flow (ore out of ``character_inventory`` + stock up + counter +
  ``mint_player`` posting in ONE transaction, the router commits);
* **admin reads / writes** (3.10) and the region-card flag (3.9).

Lock order (3.12, global): ``econ_regions → econ_region_goods → econ_region_events (asc id) → econ_mint_seasons →
npc_shop_items (asc id) → econ_banks (asc region_id) → bank_deposits (asc id) → bank_loans (asc id) →
character_inventory (asc id) → characters (asc id) → econ_accounts (asc id)``.
Court mint: ``econ_regions → econ_region_goods → econ_mint_seasons → econ_accounts``; player mint:
``econ_regions → econ_region_goods → econ_mint_seasons → character_inventory → characters → econ_accounts``.
``ensure_season_row`` INSERTs always run in their own short transaction, never under other locks.

Cross-ownership: the player flow writes ``character_inventory`` (owned by inventory-service) directly, in the same DB
transaction as the ledger posting — the accepted precedent of locations-service ``houses._take_materials``.
"""

import dataclasses
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import activity_lock
import econ_core as core
import econ_ledger
import econ_mint
import models
from economy_crud import EconomyApiError

logger = logging.getLogger("character-service.mint")

SOURCE_SERVICE = "character-service"
MINTER_ROLE = "minter"
NPC_DEAD = "dead"
CAPITAL_TEMPLATE = "capital"
ORE_GROUP = "ore_metal"

CAPITAL_AUTO = "auto"
CAPITAL_MANUAL = "manual"
CAPITAL_NONE = "none"

KEY_PLAYER = "mint"                 # mint:{character_id}:{request_id}
KEY_COURT = "mint_court"            # mint_court:{run_id}:c{country_id}
KEY_QUOTA = "season_quota"          # season_quota:p{period_index}

# Russian texts (contract 3.8 — tests assert them)
MSG_CHARACTER_NOT_FOUND = "Персонаж не найден"
MSG_NOT_OWNER = "Вы можете управлять только своими персонажами"
MSG_NOT_PLAYER = "Монетным двором пользуются только персонажи игроков"
MSG_MINTER_NOT_FOUND = "Монетчик не найден"
MSG_MINTER_DEAD = "Монетчик больше не принимает посетителей"
MSG_WRONG_LOCATION = "Подойдите к монетчику — он в другой локации"
MSG_GATE_CLOSED = "Нужен пост-намерение «Диалог с НПС» с этим персонажем"
MSG_GATE_UNAVAILABLE = "Не удалось проверить обращение к монетчику, попробуйте позже"
MSG_NO_MINT = "Монетный двор есть только в столице страны — этот монетчик ему не служит"
MSG_MINT_CLOSED = "Монетный двор закрыт: {reason}"
MSG_LIMIT = "Монетный двор исчерпал лимит до {date}"
MSG_PARTIAL = ("Принято {accepted} из {requested} шт. — лимит сезона исчерпан, остальная руда осталась у вас. "
               "Отчеканено {marks}: {name} × {accepted}")
MSG_ITEM_NOT_ACCEPTED = "Монетный двор не принимает этот предмет"
MSG_NOT_ENOUGH = "Не хватает: {name} — нужно {need}, есть {have} (принимаются только обычные стопки)"
MSG_DUPLICATE = "Операция уже выполнена"
MSG_RETRY = "Не удалось выполнить операцию, попробуйте ещё раз"

# closed reasons (MSG_MINT_CLOSED / view closed_reason)
REASON_NO_CAPITAL = "у страны не выбрана столица"
REASON_NOT_PARTICIPATING = "столица не участвует в экономике"
REASON_NO_ORE_STOCK = "в столице не ведётся запас руды и металла"
REASON_DISABLED = "двор выключен"
REASON_NO_LIMIT = "лимит не задан"
REASON_NO_CALENDAR = "календарь мира недоступен"

# admin texts
MSG_COUNTRY_NOT_FOUND = "Страна не найдена"
MSG_REGION_FOREIGN = "Регион не принадлежит этой стране"
MSG_ITEM_NOT_FOUND = "Предмет не найден"
MSG_ITEM_NOT_ORE = "Чеканить можно только руду и металл (группа «Руда и металл»)"

SQL_GAME_TIME = "SELECT epoch, offset_days FROM game_time_config ORDER BY id LIMIT 1"


def now_utc() -> datetime:
    """Naive UTC without microseconds."""
    return datetime.utcnow().replace(microsecond=0)


def _for_update(db: Session) -> bool:
    return core.supports_for_update(db.get_bind().dialect.name)


def _i(value) -> int:
    return int(value or 0)


def _fmt(db: Session, n: int) -> str:
    return core.format_currency(int(n), econ_ledger.get_currency_forms(db))


def load_params(db: Session):
    import econ_tick  # late: econ_tick imports this module lazily for the tick passes
    return econ_tick.load_params(db)


# =====================================================================================================================
# Season period (3.3)
# =====================================================================================================================

def current_period(db: Session, now: Optional[datetime] = None) -> Optional[econ_mint.SeasonPeriod]:
    """The current game season period; None when the calendar row (or its table) is missing."""
    try:
        row = db.execute(text(SQL_GAME_TIME)).first()
    except SQLAlchemyError:
        logger.warning("game_time_config is unavailable, the mint and the season quota are idle", exc_info=True)
        return None
    if row is None or row[0] is None:
        return None
    epoch = row[0]
    if isinstance(epoch, str):
        try:
            epoch = datetime.fromisoformat(epoch)
        except ValueError:
            return None
    return econ_mint.period_of(epoch, _i(row[1]), now or now_utc())


def period_out(period: Optional[econ_mint.SeasonPeriod]) -> Optional[dict]:
    return period.to_dict() if period is not None else None


# =====================================================================================================================
# Capital and mint status (3.4)
# =====================================================================================================================

@dataclass(frozen=True)
class RegionInfo:
    region_id: int
    name: str
    template_code: Optional[str]
    population: int

    @property
    def participating(self) -> bool:
        return self.template_code is not None and self.population > 0


@dataclass(frozen=True)
class CapitalInfo:
    region_id: Optional[int]
    region_name: Optional[str]
    source: str                          # auto | manual | none
    override_id: Optional[int]
    override_stale: bool
    participating: bool


@dataclass(frozen=True)
class MintStatus:
    country_id: int
    country_name: Optional[str]
    capital: CapitalInfo
    is_enabled: bool
    season_limit_override: Optional[int]
    season_limit: int
    period: Optional[econ_mint.SeasonPeriod]
    has_ore_row: bool
    working: bool
    closed_reason: Optional[str]
    candidates: Tuple[RegionInfo, ...] = ()


def _country_regions(db: Session, country_id: int) -> List[RegionInfo]:
    rows = db.execute(text(
        "SELECT r.id, r.name, e.template_code, e.population FROM Regions r "
        "LEFT JOIN econ_regions e ON e.region_id = r.id WHERE r.country_id = :c ORDER BY r.id"),
        {"c": int(country_id)}).fetchall()
    return [RegionInfo(int(r[0]), r[1], r[2], _i(r[3])) for r in rows]


def resolve_capital(regions: List[RegionInfo], override_id: Optional[int]) -> CapitalInfo:
    """Pure: the effective capital from the country's regions and the admin override (3.4)."""
    by_id = {r.region_id: r for r in regions}
    stale = False
    if override_id is not None:
        region = by_id.get(int(override_id))
        if region is not None:
            return CapitalInfo(region.region_id, region.name, CAPITAL_MANUAL, int(override_id), False,
                               region.participating)
        stale = True
    capitals = [r for r in regions if r.template_code == CAPITAL_TEMPLATE]
    if len(capitals) == 1:
        region = capitals[0]
        return CapitalInfo(region.region_id, region.name, CAPITAL_AUTO, override_id, stale, region.participating)
    return CapitalInfo(None, None, CAPITAL_NONE, override_id, stale, False)


def capital_of(db: Session, country_id: int) -> CapitalInfo:
    """The effective capital of a country (3.4)."""
    row = db.get(models.EconMint, int(country_id))
    return resolve_capital(_country_regions(db, country_id), row.capital_region_id if row is not None else None)


def _has_ore_row(db: Session, region_id: Optional[int]) -> bool:
    if not region_id:
        return False
    return db.execute(text("SELECT 1 FROM econ_region_goods WHERE region_id = :r AND group_code = :g"),
                      {"r": int(region_id), "g": ORE_GROUP}).first() is not None


_UNSET = object()


def mint_status(db: Session, country_id: int, *, params=None, period=_UNSET,
                country_name: Optional[str] = _UNSET, now: Optional[datetime] = None) -> MintStatus:
    """Everything that decides whether the country's mint works (no locks)."""
    params = params or load_params(db)
    if period is _UNSET:
        period = current_period(db, now)
    if country_name is _UNSET:
        country_name = db.execute(text("SELECT name FROM Countries WHERE id = :c"), {"c": int(country_id)}).scalar()
    row = db.get(models.EconMint, int(country_id))
    regions = _country_regions(db, country_id)
    capital = resolve_capital(regions, row.capital_region_id if row is not None else None)
    is_enabled = True if row is None else bool(row.is_enabled)
    override = int(row.season_limit) if row is not None and row.season_limit is not None else None
    limit = override if override is not None else int(params.mint_season_limit)
    has_ore = _has_ore_row(db, capital.region_id)
    reason = None
    if capital.region_id is None:
        reason = REASON_NO_CAPITAL
    elif not is_enabled:
        reason = REASON_DISABLED
    elif not capital.participating:
        reason = REASON_NOT_PARTICIPATING
    elif not has_ore:
        reason = REASON_NO_ORE_STOCK
    elif limit <= 0:
        reason = REASON_NO_LIMIT
    elif period is None:
        reason = REASON_NO_CALENDAR
    candidates = tuple(sorted(regions, key=lambda r: (0 if r.template_code == CAPITAL_TEMPLATE else 1,
                                                      r.name or "", r.region_id)))
    return MintStatus(
        country_id=int(country_id), country_name=country_name, capital=capital, is_enabled=is_enabled,
        season_limit_override=override, season_limit=limit, period=period, has_ore_row=has_ore,
        working=reason is None, closed_reason=reason, candidates=candidates,
    )


def all_country_ids(db: Session) -> List[Tuple[int, Optional[str]]]:
    return [(int(r[0]), r[1]) for r in db.execute(text("SELECT id, name FROM Countries ORDER BY id")).fetchall()]


def working_countries(db: Session, params, period: Optional[econ_mint.SeasonPeriod]) -> List[MintStatus]:
    """Countries whose mint works now (court pass input), ascending country id."""
    if period is None:
        return []
    statuses = [mint_status(db, cid, params=params, period=period, country_name=name)
                for cid, name in all_country_ids(db)]
    return [s for s in statuses if s.working]


def has_mint_for_region(db: Session, region_id: int) -> bool:
    """Region card flag (3.9): the region is the effective capital of its country and the mint works."""
    country_id = db.execute(text("SELECT country_id FROM Regions WHERE id = :r"), {"r": int(region_id)}).scalar()
    if country_id is None:
        return False
    status = mint_status(db, int(country_id))
    return status.working and status.capital.region_id == int(region_id)


# =====================================================================================================================
# Season counter rows and locks (3.12)
# =====================================================================================================================

def ensure_season_row(db: Session, country_id: int, period_index: int, now: Optional[datetime] = None) -> None:
    """Create the zero counter row in its OWN short transaction (commits / rolls back ``db``)."""
    db.rollback()
    exists = db.execute(text("SELECT 1 FROM econ_mint_seasons WHERE country_id = :c AND period_index = :p"),
                        {"c": int(country_id), "p": int(period_index)}).first()
    if exists is not None:
        db.rollback()
        return
    try:
        db.execute(text(
            "INSERT INTO econ_mint_seasons (country_id, period_index, minted_court, minted_players, ore_units_court, "
            "ore_units_players, created_at) VALUES (:c, :p, 0, 0, 0, 0, :now)"),
            {"c": int(country_id), "p": int(period_index), "now": now or now_utc()})
        db.commit()
    except IntegrityError:
        db.rollback()       # created by a concurrent request / runner


def season_row(db: Session, country_id: int, period_index: int) -> Optional["models.EconMintSeason"]:
    return db.get(models.EconMintSeason, (int(country_id), int(period_index)))


def season_counts(db: Session, country_id: int, period: Optional[econ_mint.SeasonPeriod]) -> Tuple[int, int]:
    if period is None:
        return 0, 0
    row = season_row(db, country_id, period.index)
    return (_i(row.minted_court), _i(row.minted_players)) if row is not None else (0, 0)


def lock_capital(db: Session, region_id: int, country_id: int, period_index: int):
    """``econ_regions → econ_region_goods('ore_metal') → econ_mint_seasons`` FOR UPDATE (3.12)."""
    fu = _for_update(db)
    q = db.query(models.EconRegion).filter(models.EconRegion.region_id == int(region_id))
    region = (q.with_for_update() if fu else q).populate_existing().first()
    q = db.query(models.EconRegionGood).filter(models.EconRegionGood.region_id == int(region_id),
                                               models.EconRegionGood.group_code == ORE_GROUP)
    goods = (q.with_for_update() if fu else q).populate_existing().first()
    q = db.query(models.EconMintSeason).filter(models.EconMintSeason.country_id == int(country_id),
                                               models.EconMintSeason.period_index == int(period_index))
    season = (q.with_for_update() if fu else q).populate_existing().first()
    return region, goods, season


def _participates(region: Optional["models.EconRegion"]) -> bool:
    return region is not None and region.template_code is not None and _i(region.population) > 0


def _dec3(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.001"))


# =====================================================================================================================
# Court mint (3.6) — called by econ_tick._mint_pass; the caller commits
# =====================================================================================================================

@dataclass(frozen=True)
class CourtResult:
    marks: int = 0
    units: Decimal = Decimal("0.000")
    operation_id: Optional[int] = None


def court_mint(db: Session, status: MintStatus, *, run_id: int, params, now: datetime) -> CourtResult:
    """Mint the capital's ore surplus above the threshold into the country treasury (one country, no commit)."""
    period = status.period
    capital_id = status.capital.region_id
    if period is None or capital_id is None:
        return CourtResult()
    region, goods, season = lock_capital(db, capital_id, status.country_id, period.index)
    if not _participates(region) or goods is None or season is None:
        return CourtResult()
    rate = Decimal(str(params.mint_court_marks_per_unit))
    remaining = econ_mint.remaining_limit(status.season_limit, _i(season.minted_court), _i(season.minted_players))
    stock_before = _dec3(goods.stock)
    norm = _dec3(goods.norm_stock)
    result = econ_mint.court_mint(stock_before, norm, params.mint_court_threshold_pct, rate, remaining)
    if result.marks <= 0:
        return CourtResult()
    goods.stock = _dec3(stock_before - result.units)
    season.minted_court = _i(season.minted_court) + result.marks
    season.ore_units_court = _dec3(_dec3(season.ore_units_court) + result.units)
    season.updated_at = now
    db.flush()
    posted = econ_ledger.post_operation(
        db, op_type=core.OP_MINT_COURT,
        legs=[core.Leg(core.AccountRef.emission(), core.AccountRef.country(status.country_id), result.marks)],
        source_service=SOURCE_SERVICE, region_id=capital_id, apply_tax=False,
        idempotency_key=f"{KEY_COURT}:{int(run_id)}:c{status.country_id}",
        metadata={"run_id": int(run_id), "period_index": period.index, "units": str(result.units),
                  "rate": float(rate), "stock_before": str(stock_before), "norm": str(norm),
                  "threshold_pct": float(params.mint_court_threshold_pct)},
    )
    return CourtResult(result.marks, result.units, posted.operation_id)


# =====================================================================================================================
# Player API — Монетчик (3.8)
# =====================================================================================================================

@dataclass(frozen=True)
class MinterContext:
    character_id: int
    user_id: int
    npc_id: int
    npc_name: str
    location_id: int
    region_id: Optional[int] = None
    country_id: Optional[int] = None


def _player_character(db: Session, character_id: int, user_id: int) -> "models.Character":
    character = db.query(models.Character).filter(models.Character.id == int(character_id)).first()
    if character is None:
        raise EconomyApiError(404, MSG_CHARACTER_NOT_FOUND)
    if character.user_id != user_id:
        raise EconomyApiError(403, MSG_NOT_OWNER)
    if character.is_npc:
        raise EconomyApiError(403, MSG_NOT_PLAYER)
    return character


def resolve_minter(db: Session, npc_id: int, character_id: int, user_id: int, *, write: bool) -> MinterContext:
    """Steps 1–4 (banker order): owner + player, minter exists / role / alive, activity lock (POST), location."""
    character = _player_character(db, character_id, user_id)
    npc = db.query(models.Character).filter(models.Character.id == int(npc_id)).first()
    if npc is None or not npc.is_npc or npc.npc_role != MINTER_ROLE:
        raise EconomyApiError(404, MSG_MINTER_NOT_FOUND)
    if npc.npc_status == NPC_DEAD:
        raise EconomyApiError(409, MSG_MINTER_DEAD)
    if write:
        message = activity_lock.lock_message(activity_lock.lock_for_character(character))
        if message:
            raise EconomyApiError(409, message)
    if npc.current_location_id is None or character.current_location_id != npc.current_location_id:
        raise EconomyApiError(400, MSG_WRONG_LOCATION)
    return MinterContext(character_id=int(character.id), user_id=int(user_id), npc_id=int(npc.id),
                         npc_name=npc.name, location_id=int(npc.current_location_id))


def with_region(db: Session, ctx: MinterContext) -> MinterContext:
    """Step 6: the minter's location -> region -> country."""
    region_id, country_id = econ_ledger.resolve_location(db, ctx.location_id)
    if not region_id or not country_id:
        raise EconomyApiError(409, MSG_NO_MINT)
    return dataclasses.replace(ctx, region_id=int(region_id), country_id=int(country_id))


def minter_context(db: Session, npc_id: int, character_id: int, user_id: int, *,
                   write: bool) -> Tuple[MinterContext, MintStatus]:
    """Steps 1–4 + 6: the context and the country's mint status. 409 MSG_NO_MINT when the country has a capital
    and it is not the minter's region (a country without a capital answers via the closed reason)."""
    ctx = with_region(db, resolve_minter(db, npc_id, character_id, user_id, write=write))
    status = mint_status(db, ctx.country_id)
    if status.capital.region_id is not None and status.capital.region_id != ctx.region_id:
        raise EconomyApiError(409, MSG_NO_MINT)
    return ctx, status


def _require_working(status: MintStatus) -> None:
    if not status.working:
        raise EconomyApiError(409, MSG_MINT_CLOSED.format(reason=status.closed_reason))


def _ore_group_base(db: Session) -> int:
    return _i(db.execute(text("SELECT base_price FROM econ_goods_groups WHERE code = :g"), {"g": ORE_GROUP}).scalar())


def _item_markets(db: Session, item_ids: List[int]) -> Dict[int, Tuple[tuple, core.ItemMarket]]:
    ids = sorted({int(i) for i in item_ids})
    if not ids:
        return {}
    placeholders, params = core.in_params("i", ids)
    rows = db.execute(text(core.sql_item_market(placeholders)), params).fetchall()
    return {int(r[0]): (tuple(r), core.item_market_from_row(r)) for r in rows}


def _plain_have(db: Session, character_id: int, item_ids: List[int]) -> Dict[int, int]:
    ids = sorted({int(i) for i in item_ids})
    if not ids:
        return {}
    placeholders, params = core.in_params("i", ids)
    rows = db.execute(text(
        f"SELECT item_id, SUM(quantity) FROM character_inventory WHERE character_id = :c AND item_id IN "
        f"({placeholders}) AND COALESCE(enhancement_points_spent, 0) = 0 AND socketed_gems IS NULL "
        f"AND current_durability IS NULL GROUP BY item_id"), {"c": int(character_id), **params}).fetchall()
    return {int(r[0]): _i(r[1]) for r in rows}


def accepted_items(db: Session) -> List[Tuple["models.EconMintItem", core.ItemMarket]]:
    """Enabled mint items whose effective group is ore_metal, ascending item id."""
    rows = (db.query(models.EconMintItem).filter(models.EconMintItem.is_enabled == True)  # noqa: E712
            .order_by(models.EconMintItem.item_id).all())
    markets = _item_markets(db, [r.item_id for r in rows])
    return [(r, markets[int(r.item_id)][1]) for r in rows
            if int(r.item_id) in markets and markets[int(r.item_id)][1].group == ORE_GROUP]


def _wallet(db: Session, character_id: int) -> int:
    return _i(db.execute(text("SELECT currency_balance FROM characters WHERE id = :id"),
                         {"id": int(character_id)}).scalar())


def build_view(db: Session, ctx: MinterContext, status: Optional[MintStatus] = None) -> dict:
    """``MintView`` (read-only)."""
    status = status or mint_status(db, ctx.country_id)
    minted_court, minted_players = season_counts(db, ctx.country_id, status.period)
    remaining = econ_mint.remaining_limit(status.season_limit, minted_court, minted_players) if status.working else 0
    items = accepted_items(db)
    have = _plain_have(db, ctx.character_id, [r.item_id for r, _ in items])
    region_name = db.execute(text("SELECT name FROM Regions WHERE id = :r"), {"r": ctx.region_id}).scalar()
    return {
        "npc_id": ctx.npc_id,
        "npc_name": ctx.npc_name,
        "country_id": ctx.country_id,
        "country_name": status.country_name,
        "region_id": ctx.region_id,
        "region_name": region_name,
        "working": status.working,
        "closed_reason": status.closed_reason,
        "period": period_out(status.period),
        "limit": int(status.season_limit),
        "minted_court": minted_court,
        "minted_players": minted_players,
        "remaining": remaining,
        "items": [{
            "item_id": int(row.item_id),
            "name": market.name,
            "image": market.image,
            "marks_per_item": int(row.marks_per_item),
            "have": have.get(int(row.item_id), 0),
            "max_by_limit": remaining // int(row.marks_per_item) if int(row.marks_per_item) > 0 else 0,
        } for row, market in items],
        "wallet": _wallet(db, ctx.character_id),
    }


def take_plain_stacks(db: Session, character_id: int, item_id: int, quantity: int, name: str,
                      need: Optional[int] = None, not_enough: str = MSG_NOT_ENOUGH) -> None:
    """Take ``quantity`` pieces from plain stacks only, rows locked in ascending id. The «not enough» check runs
    against ``need`` (the requested quantity, defaults to ``quantity``) — 400 naming what is short (``not_enough``
    template with name / need / have). No commit. Shared by the mint and the guild (FEAT-193)."""
    need = quantity if need is None else need
    rows = db.execute(text(
        "SELECT id, quantity FROM character_inventory WHERE character_id = :c AND item_id = :i "
        "AND COALESCE(enhancement_points_spent, 0) = 0 AND socketed_gems IS NULL AND current_durability IS NULL "
        "ORDER BY id" + (" FOR UPDATE" if _for_update(db) else "")),
        {"c": int(character_id), "i": int(item_id)}).fetchall()
    have = sum(_i(r[1]) for r in rows)
    if have < need:
        raise EconomyApiError(400, not_enough.format(name=name, need=need, have=have))
    left = quantity
    for row_id, qty in rows:
        if left <= 0:
            break
        qty = _i(qty)
        if qty <= left:
            db.execute(text("DELETE FROM character_inventory WHERE id = :r"), {"r": int(row_id)})
            left -= qty
        else:
            db.execute(text("UPDATE character_inventory SET quantity = quantity - :q WHERE id = :r"),
                       {"q": left, "r": int(row_id)})
            left = 0


def mint(db: Session, ctx: MinterContext, status: MintStatus, body, *, now: Optional[datetime] = None) -> dict:
    """The player flow (3.8 steps 2–8), all in the caller's transaction; the router commits.

    Partial acceptance (user decision 2026-11-01): when the requested quantity does not fit the remaining season
    limit, only ``floor(remaining / marks_per_item)`` pieces are taken and paid for, the rest of the ore stays with
    the player; 0 pieces fit -> 409 ``MSG_LIMIT``. The «not enough ore» check is against the REQUESTED quantity.

    The season counter row must already exist (``ensure_season_row`` before the transaction)."""
    _require_working(status)
    now = now or now_utc()
    period = status.period
    capital_id = status.capital.region_id
    key = f"{KEY_PLAYER}:{ctx.character_id}:{body.request_id}"
    region, goods, season = lock_capital(db, capital_id, ctx.country_id, period.index)
    if not _participates(region):
        raise EconomyApiError(409, MSG_MINT_CLOSED.format(reason=REASON_NOT_PARTICIPATING))
    if goods is None:
        raise EconomyApiError(409, MSG_MINT_CLOSED.format(reason=REASON_NO_ORE_STOCK))
    if season is None:
        raise EconomyApiError(409, MSG_RETRY)        # the season turned between ensure and lock
    if db.execute(text(core.SQL_SELECT_OPERATION_BY_KEY), {"key": key}).first() is not None:
        raise EconomyApiError(409, MSG_DUPLICATE)

    item_id = int(body.item_id)
    quantity = int(body.quantity)
    row = db.get(models.EconMintItem, item_id)
    market = _item_markets(db, [item_id]).get(item_id)
    if row is None or not row.is_enabled or market is None or market[1].group != ORE_GROUP:
        raise EconomyApiError(400, MSG_ITEM_NOT_ACCEPTED)
    market = market[1]
    marks_per_item = int(row.marks_per_item)
    remaining = econ_mint.remaining_limit(status.season_limit, _i(season.minted_court), _i(season.minted_players))
    accepted = min(quantity, remaining // marks_per_item) if marks_per_item > 0 else 0
    if accepted <= 0:
        raise EconomyApiError(409, MSG_LIMIT.format(date=econ_mint.fmt_date(period.ends_at)))
    marks = marks_per_item * accepted

    name = market.name or f"предмет #{item_id}"
    take_plain_stacks(db, ctx.character_id, item_id, accepted, name, need=quantity)

    group_base = _ore_group_base(db)
    per_item = Decimal(str(core.units_per_item(core.item_base_price(market.price, group_base), group_base)))
    units = _dec3(per_item * accepted)
    goods.stock = _dec3(_dec3(goods.stock) + units)
    season.minted_players = _i(season.minted_players) + marks
    season.ore_units_players = _dec3(_dec3(season.ore_units_players) + units)
    season.updated_at = now
    db.flush()

    try:
        posted = econ_ledger.post_operation(
            db, op_type=core.OP_MINT_PLAYER,
            legs=[core.Leg(core.AccountRef.emission(), core.AccountRef.character(ctx.character_id), marks)],
            source_service=SOURCE_SERVICE, location_id=ctx.location_id, region_id=capital_id,
            actor_user_id=ctx.user_id, apply_tax=False, idempotency_key=key,
            metadata={"item_id": item_id, "item_name": market.name, "quantity": accepted,
                      "requested": quantity, "marks_per_item": marks_per_item, "period_index": period.index, "npc_id": ctx.npc_id,
                      "units": str(units)},
        )
    except core.DuplicateOperation:
        raise EconomyApiError(409, MSG_DUPLICATE)
    partial = accepted < quantity
    if partial:
        message = MSG_PARTIAL.format(accepted=accepted, requested=quantity, marks=_fmt(db, marks), name=name)
    else:
        message = f"Отчеканено {_fmt(db, marks)}: {name} × {accepted}"
    return {
        "message": message,
        "operation_id": posted.operation_id,
        "marks": marks,
        "quantity": accepted,
        "requested": quantity,
        "partial": partial,
    }


# =====================================================================================================================
# Admin (3.10)
# =====================================================================================================================

def _minters_by_country(db: Session) -> Dict[int, List[dict]]:
    rows = db.execute(text(
        "SELECT c.id, c.name, c.npc_status, c.current_location_id, l.name FROM characters c "
        "LEFT JOIN Locations l ON l.id = c.current_location_id "
        "WHERE c.is_npc = 1 AND c.npc_role = :role ORDER BY c.id"), {"role": MINTER_ROLE}).fetchall()
    result: Dict[int, List[dict]] = {}
    cache: Dict[int, Tuple[Optional[int], Optional[int]]] = {}
    for npc_id, name, npc_status, location_id, location_name in rows:
        if not location_id:
            continue
        if location_id not in cache:
            cache[location_id] = econ_ledger.resolve_location(db, int(location_id))
        region_id, country_id = cache[location_id]
        if not country_id:
            continue
        result.setdefault(int(country_id), []).append({
            "npc_id": int(npc_id), "name": name, "npc_status": npc_status or "alive",
            "location_name": location_name, "region_id": region_id,
        })
    return result


def _country_out(db: Session, status: MintStatus, minters: List[dict]) -> dict:
    minted_court, minted_players = season_counts(db, status.country_id, status.period)
    capital = status.capital
    ore_stock = ore_norm = None
    if capital.region_id is not None:
        row = db.get(models.EconRegionGood, (capital.region_id, ORE_GROUP))
        if row is not None:
            ore_stock, ore_norm = float(row.stock or 0), float(row.norm_stock or 0)
    return {
        "country_id": status.country_id,
        "country_name": status.country_name,
        "is_enabled": status.is_enabled,
        "capital_region_id": capital.region_id,
        "capital_region_name": capital.region_name,
        "capital_source": capital.source,
        "capital_override_id": capital.override_id,
        "override_stale": capital.override_stale,
        "candidates": [{"region_id": r.region_id, "name": r.name, "template_code": r.template_code}
                       for r in status.candidates],
        "working": status.working,
        "closed_reason": status.closed_reason,
        "season_limit_override": status.season_limit_override,
        "season_limit": status.season_limit,
        "minted_court": minted_court,
        "minted_players": minted_players,
        "remaining": (econ_mint.remaining_limit(status.season_limit, minted_court, minted_players)
                      if status.working else 0),     # same rule as the player view: closed mint -> 0
        "ore_stock": ore_stock,
        "ore_norm": ore_norm,
        "minters": [{"npc_id": m["npc_id"], "name": m["name"], "npc_status": m["npc_status"],
                     "location_name": m["location_name"],
                     "in_capital": capital.region_id is not None and m["region_id"] == capital.region_id}
                    for m in minters],
    }


def admin_view(db: Session) -> dict:
    params = load_params(db)
    period = current_period(db)
    minters = _minters_by_country(db)
    countries = [_country_out(db, mint_status(db, cid, params=params, period=period, country_name=name),
                              minters.get(cid, []))
                 for cid, name in all_country_ids(db)]
    return {
        "period": period_out(period),
        "params": {
            "mint_season_limit": int(params.mint_season_limit),
            "mint_court_marks_per_unit": float(params.mint_court_marks_per_unit),
            "mint_court_threshold_pct": float(params.mint_court_threshold_pct),
            "quota_season_amount": int(params.quota_season_amount),
        },
        "countries": countries,
    }


def update_country(db: Session, country_id: int, *, capital_region_id: Optional[int], season_limit: Optional[int],
                   is_enabled: bool, actor_user_id: Optional[int]) -> dict:
    """Upsert ``econ_mints`` (full replace). The router commits."""
    country = db.execute(text("SELECT id, name FROM Countries WHERE id = :c"), {"c": int(country_id)}).first()
    if country is None:
        raise EconomyApiError(404, MSG_COUNTRY_NOT_FOUND)
    name = country[1]
    if capital_region_id is not None:
        owner = db.execute(text("SELECT country_id FROM Regions WHERE id = :r"),
                           {"r": int(capital_region_id)}).first()
        if owner is None or owner[0] is None or int(owner[0]) != int(country_id):
            raise EconomyApiError(400, MSG_REGION_FOREIGN)
    row = db.get(models.EconMint, int(country_id))
    if row is None:
        row = models.EconMint(country_id=int(country_id))
        db.add(row)
    row.capital_region_id = int(capital_region_id) if capital_region_id is not None else None
    row.season_limit = int(season_limit) if season_limit is not None else None
    row.is_enabled = bool(is_enabled)
    row.updated_at = now_utc()
    row.updated_by = actor_user_id
    db.flush()
    status = mint_status(db, country_id, country_name=name)
    return _country_out(db, status, _minters_by_country(db).get(int(country_id), []))


def _mint_item_out(row: "models.EconMintItem", raw: Optional[tuple], market: Optional[core.ItemMarket]) -> dict:
    return {
        "item_id": int(row.item_id),
        "name": market.name if market is not None else None,
        "image": market.image if market is not None else None,
        "item_type": raw[1] if raw is not None else None,
        "resource_subcategory": raw[2] if raw is not None else None,
        "effective_group": market.group if market is not None else None,
        "marks_per_item": int(row.marks_per_item),
        "is_enabled": bool(row.is_enabled),
        "valid": market is not None and market.group == ORE_GROUP,
    }


def list_items(db: Session) -> List[dict]:
    rows = db.query(models.EconMintItem).order_by(models.EconMintItem.item_id).all()
    markets = _item_markets(db, [r.item_id for r in rows])
    out = []
    for row in rows:
        raw, market = markets.get(int(row.item_id), (None, None))
        out.append(_mint_item_out(row, raw, market))
    return out


def upsert_item(db: Session, item_id: int, *, marks_per_item: int, is_enabled: bool,
                actor_user_id: Optional[int]) -> dict:
    found = _item_markets(db, [item_id]).get(int(item_id))
    if found is None:
        raise EconomyApiError(404, MSG_ITEM_NOT_FOUND)
    raw, market = found
    if market.group != ORE_GROUP:
        raise EconomyApiError(400, MSG_ITEM_NOT_ORE)
    row = db.get(models.EconMintItem, int(item_id))
    if row is None:
        row = models.EconMintItem(item_id=int(item_id))
        db.add(row)
    row.marks_per_item = int(marks_per_item)
    row.is_enabled = bool(is_enabled)
    row.updated_at = now_utc()
    row.updated_by = actor_user_id
    db.flush()
    return _mint_item_out(row, raw, market)


def delete_item(db: Session, item_id: int) -> None:
    row = db.get(models.EconMintItem, int(item_id))
    if row is None:
        raise EconomyApiError(404, MSG_ITEM_NOT_FOUND)
    db.delete(row)
    db.flush()


def list_quotas(db: Session, limit: int) -> List[dict]:
    rows = db.execute(text(
        "SELECT id, created_at, metadata FROM econ_operations WHERE op_type = :op ORDER BY id DESC LIMIT :n"),
        {"op": core.OP_SEASON_QUOTA, "n": int(limit)}).fetchall()
    out = []
    for op_id, created_at, metadata in rows:
        meta = metadata
        if isinstance(meta, (str, bytes)):
            try:
                meta = json.loads(meta)
            except ValueError:
                meta = None
        meta = meta if isinstance(meta, dict) else {}
        out.append({
            "operation_id": int(op_id),
            "created_at": created_at,
            "period_index": meta.get("period_index"),
            "year": meta.get("year"),
            "season": meta.get("season"),
            "amount": _i(meta.get("amount")),
            "regions": len(meta.get("regions") or {}),
        })
    return out
