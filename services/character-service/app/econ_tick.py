"""Living-regions tick runner (FEAT-182, section 3.5).

One run = one simulation step of every participating region:

* **claim** — an auto run inserts ``econ_tick_runs(slot = floor(unix / 21600))``; ``UNIQUE(slot)`` makes every
  other process (``--reload`` restarts, a second replica) a no-op for that slot. A run that died mid-way (status
  ``running``, heartbeat older than :data:`STALE_AFTER`) is resumed by the next auto call of the same slot. Missed
  slots are never caught up: only the current slot is ever claimed. A manual run (admin «Пересчитать сейчас») has
  ``slot = NULL`` — it is a real extra step that does not shift the schedule, and it is refused with
  :class:`RunInProgress` while any run is alive;
* **grant plan** — every participating region with its country grant (25 % of the country's positive balance split by
  population, :func:`econ_sim.country_grants`) is fixed in the run row at claim time, so a resumed run grants the same;
* **regions** — one transaction per region: ``econ_regions`` row FOR UPDATE (skipped when ``last_run_id`` is this run)
  → its goods rows FOR UPDATE → :func:`econ_sim.simulate_region` → rows updated → one ``region_tick`` ledger operation
  (``purse → region`` tax, +10 % ``region → country`` by the ledger, ``country → region`` grant, ``region → purse``
  wages; key ``region_tick:<run_id>:r:<region_id>``) → history row → COMMIT. A failing region is rolled back, logged and
  counted; the others go on;
* **merchants** (FEAT-183, 3.4) — inside the same region transaction, after the ``region_tick`` posting, a SAVEPOINT
  runs the background trade of the region's living NPC merchants (:func:`econ_merchant.merchant_step`): shop row
  stocks and region goods stocks are updated, player-origin rows sold out are deleted and one ``merchant_trade``
  operation is posted (key ``merchant_trade:<run_id>:r:<region_id>``). A failing merchant step is rolled back alone,
  logged and counted; the region step still commits. Which NPCs are living merchants of which region is computed once
  per run (:func:`build_merchant_map`) and re-checked under the locks;
* **housekeeping** — economy rows of deleted regions and shop rows of deleted NPCs are purged before the step,
  history older than ``history_retention_days`` and runs beyond the newest :data:`KEEP_RUNS` after it.

Lock order inside a region transaction (FEAT-183 3.5, shared with the player shop flows of locations-service):
``econ_regions`` → ``econ_region_goods`` → ``npc_shop_items`` of the region's merchants (ascending id) → their
``characters`` rows (ascending id) → ``econ_accounts`` ascending (done by ``post_operation``). The shop rows and NPC
rows are locked **before** the ``region_tick`` posting so no account is held while waiting for them.

Pure math lives in ``econ_sim`` / ``econ_merchant``; this module only loads, stores and posts. The scheduler thread is
``econ_scheduler``.
"""

import calendar
import json
import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import econ_core as core
import econ_ledger
import econ_merchant
import econ_sim
import models

logger = logging.getLogger("character-service.econ_tick")

SOURCE_SERVICE = "character-service"

TICK_SECONDS = 6 * 60 * 60                 # one simulation step per 6 h slot (UTC 00/06/12/18)
STALE_AFTER = timedelta(minutes=10)        # a 'running' run without a heartbeat for this long is dead
KEEP_RUNS = 500                            # newest runs kept; older ones (and their history) are purged
MAX_ERROR_LEN = 500

TRIGGER_AUTO = "auto"
TRIGGER_MANUAL = "manual"

STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"

INTERRUPTED_ERROR = "прерван: процесс остановился во время пересчёта"
# Run error text for regions whose merchant step failed (the region itself ticked); parsed back by
# merchant_failures_from_error for the runs list (econ_tick_runs has no merchant columns — no migration).
MERCHANT_ERROR_PREFIX = "торговцы — ошибка в регионах: "

# Column scales of econ_regions / econ_region_goods (Numeric(p, s)) — values are rounded before storing.
_SCALE_STOCK = 3
_SCALE_PRICE = 3
_SCALE_STAB = 2
_SCALE_SHARE = 4

SessionFactory = Callable[[], Session]


class RunInProgress(Exception):
    """A manual run was requested while another run is alive (B6 answers 409)."""

    def __init__(self, run_id: int):
        self.run_id = run_id
        super().__init__(f"economy tick run {run_id} is still running")


@dataclass
class RunSummary:
    """Outcome of one :func:`run_tick` call (``to_dict`` is JSON-ready for the admin API)."""

    run_id: int
    trigger: str
    slot: Optional[int]
    status: str
    resumed: bool = False
    regions_total: int = 0
    regions_done: int = 0
    regions_failed: int = 0
    operations_posted: int = 0
    failed_region_ids: List[int] = field(default_factory=list)
    # FEAT-183 NPC merchants
    merchants_processed: int = 0          # living merchants that went through the background trade
    merchant_items_sold: int = 0          # items residents bought from merchants
    merchant_items_restocked: int = 0     # items merchants bought from the region stock
    merchant_ops_posted: int = 0          # merchant_trade operations (one per region with money movement)
    merchant_failures: int = 0            # regions whose merchant step was rolled back (the region still ticked)
    merchant_failed_region_ids: List[int] = field(default_factory=list)
    shop_rows_purged: int = 0             # orphan rows of deleted NPCs + sold-out player-origin rows
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in ("started_at", "finished_at"):
            data[key] = data[key].isoformat() if data[key] else None
        return data


@dataclass
class _MerchantOutcome:
    processed: int = 0
    items_sold: int = 0
    items_restocked: int = 0
    posted: bool = False
    failed: bool = False
    rows_purged: int = 0


@dataclass
class _RegionOutcome:
    status: str                 # done | already | skipped | failed
    posted: bool = False
    merchants: Optional[_MerchantOutcome] = None


# --------------------------------------------------------------------------------------------- time

def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _naive_utc(moment: Optional[datetime]) -> datetime:
    """Naive UTC datetime (the DATETIME columns are naive UTC)."""
    if moment is None:
        return _utcnow()
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment.replace(microsecond=0)


def slot_of(moment: Optional[datetime] = None) -> int:
    """Wall-clock slot number: floor(unix_time / 21600)."""
    return calendar.timegm(_naive_utc(moment).timetuple()) // TICK_SECONDS


def slot_start(slot: int) -> datetime:
    return datetime(1970, 1, 1) + timedelta(seconds=int(slot) * TICK_SECONDS)


# --------------------------------------------------------------------------------------------- loaders

def _float(value) -> float:
    return float(value or 0)


def _json(value):
    if isinstance(value, (str, bytes)):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def load_params(session: Session) -> econ_sim.SimParams:
    """Global simulation params from ``econ_sim_settings`` (defaults when the row is missing or broken)."""
    row = session.get(models.EconSimSettings, 1)
    if row is None:
        return econ_sim.DEFAULT_PARAMS
    try:
        return econ_sim.SimParams.from_mapping(_json(row.params))
    except (TypeError, ValueError):
        logger.warning("econ_sim_settings.params is invalid, using defaults", exc_info=True)
        return econ_sim.DEFAULT_PARAMS


def is_tick_enabled(session: Session) -> bool:
    """DB switch ``econ_sim_settings.tick_enabled`` (missing row = enabled, as the migration default)."""
    row = session.get(models.EconSimSettings, 1)
    return True if row is None else bool(row.tick_enabled)


def load_groups(session: Session) -> Dict[str, econ_sim.GroupDef]:
    """Goods groups with their production chains, in ``sort_order``."""
    inputs: Dict[str, Dict[str, float]] = {}
    for row in session.query(models.EconGroupInput).all():
        inputs.setdefault(row.group_code, {})[row.input_code] = _float(row.ratio)
    groups: Dict[str, econ_sim.GroupDef] = {}
    for row in session.query(models.EconGoodsGroup).order_by(models.EconGoodsGroup.sort_order,
                                                              models.EconGoodsGroup.code).all():
        groups[row.code] = econ_sim.GroupDef(
            code=row.code, name=row.name, base_price=_float(row.base_price),
            norm_per_1000=_float(row.norm_per_1000), norm_days=_float(row.norm_days),
            prosperity_elasticity=_float(row.prosperity_elasticity), price_elasticity=_float(row.price_elasticity),
            is_food=bool(row.is_food), inputs=inputs.get(row.code, {}),
        )
    return groups


def region_state(row: "models.EconRegion") -> econ_sim.RegionState:
    return econ_sim.RegionState(
        population=int(row.population or 0), tax_rate=_float(row.tax_rate), stability=_float(row.stability),
        prosperity=_float(row.prosperity), hunger=_float(row.hunger), satisfaction=_float(row.satisfaction),
        treasury_target=int(row.treasury_target or 0),
    )


def good_state(row: "models.EconRegionGood") -> econ_sim.GoodState:
    return econ_sim.GoodState(
        group_code=row.group_code, production_per_1000=_float(row.production_per_1000),
        consumption_mult=_float(row.consumption_mult), stock=_float(row.stock), norm_stock=_float(row.norm_stock),
        price_mult=_float(row.price_mult), prev_price_mult=_float(row.prev_price_mult),
        last_produced=_float(row.last_produced), last_consumed=_float(row.last_consumed),
        last_demand=_float(row.last_demand), last_spoiled=_float(row.last_spoiled),
    )


def account_balance(session: Session, ref: core.AccountRef) -> int:
    """Balance of a non-character account; 0 when the account does not exist yet."""
    value = session.execute(
        text("SELECT balance FROM econ_accounts WHERE kind = :kind AND ref_id = :ref_id"),
        {"kind": ref.kind, "ref_id": ref.ref_id},
    ).scalar()
    return int(value or 0)


SQL_PARTICIPATING = (
    "SELECT e.region_id, e.population, r.country_id FROM econ_regions e "
    "JOIN Regions r ON r.id = e.region_id "
    "WHERE e.template_code IS NOT NULL AND e.population > 0 ORDER BY e.region_id"
)


def participating_regions(session: Session) -> List[Tuple[int, int, Optional[int]]]:
    """[(region_id, population, country_id)] of simulated regions that still exist, ascending by id."""
    return [(int(r[0]), int(r[1]), int(r[2]) if r[2] is not None else None)
            for r in session.execute(text(SQL_PARTICIPATING)).fetchall()]


def build_grant_plan(session: Session, params: econ_sim.SimParams) -> Dict[str, int]:
    """{str(region_id): grant} for every participating region (grant 0 included — the plan is the region list too)."""
    by_country: Dict[Optional[int], Dict[int, int]] = {}
    for region_id, population, country_id in participating_regions(session):
        by_country.setdefault(country_id, {})[region_id] = population
    plan: Dict[str, int] = {}
    for country_id, populations in by_country.items():
        if country_id is None:
            grants = {rid: 0 for rid in populations}
        else:
            balance = account_balance(session, core.AccountRef.country(country_id))
            grants = econ_sim.country_grants(balance, populations, params)
        for region_id, grant in grants.items():
            plan[str(region_id)] = int(grant)
    return dict(sorted(plan.items(), key=lambda kv: int(kv[0])))


# --------------------------------------------------------------------------------------------- housekeeping

def purge_orphans(session: Session) -> List[int]:
    """Delete economy rows of regions whose ``Regions`` row is gone (the caller commits)."""
    ids = [int(r[0]) for r in session.execute(text(
        "SELECT e.region_id FROM econ_regions e LEFT JOIN Regions r ON r.id = e.region_id WHERE r.id IS NULL"
    )).fetchall()]
    if not ids:
        return []
    placeholders, params = core.in_params("r", ids)
    # Explicit goods delete: SQLite test databases may run without FK cascades.
    session.execute(text(f"DELETE FROM econ_region_goods WHERE region_id IN ({placeholders})"), params)
    session.execute(text(f"DELETE FROM econ_regions WHERE region_id IN ({placeholders})"), params)
    logger.info("economy tick: purged economy rows of deleted regions %s", ids)
    return ids


def purge_old(session: Session, params: econ_sim.SimParams, now: datetime) -> None:
    """History older than the retention, runs beyond the newest KEEP_RUNS (the caller commits)."""
    cutoff = now - timedelta(days=max(1, int(params.history_retention_days)))
    session.execute(text("DELETE FROM econ_region_history WHERE created_at < :cutoff"), {"cutoff": cutoff})
    oldest_kept = session.execute(
        text("SELECT id FROM econ_tick_runs ORDER BY id DESC LIMIT 1 OFFSET :offset"), {"offset": KEEP_RUNS - 1}
    ).scalar()
    if oldest_kept is not None:
        bound = {"bound": int(oldest_kept)}
        session.execute(text("DELETE FROM econ_region_history WHERE run_id < :bound"), bound)
        session.execute(text("DELETE FROM econ_tick_runs WHERE id < :bound AND status <> 'running'"), bound)


def _close_dead_runs(session: Session, now: datetime, keep_slot: Optional[int]) -> None:
    """Runs left 'running' by a dead process that nobody will resume (manual runs, past slots) get closed."""
    stale = now - STALE_AFTER
    rows = (session.query(models.EconTickRun)
            .filter(models.EconTickRun.status == STATUS_RUNNING, models.EconTickRun.heartbeat_at < stale)
            .all())
    for run in rows:
        if keep_slot is not None and run.slot == keep_slot:
            continue
        run.status = STATUS_PARTIAL if (run.regions_done or 0) > 0 else STATUS_FAILED
        run.error = INTERRUPTED_ERROR
        run.finished_at = now
        logger.warning("economy tick: run %s (slot %s) was interrupted, closed as %s", run.id, run.slot, run.status)


# --------------------------------------------------------------------------------------------- merchants (FEAT-183)

# NPCs that have at least one active shop row — the merchant candidates of a run.
SQL_MERCHANT_NPCS = "SELECT DISTINCT npc_id FROM npc_shop_items WHERE is_active = 1 ORDER BY npc_id"

# Shop rows whose NPC no longer exists (character deleted; locations-service keeps no FK).
SQL_PURGE_ORPHAN_SHOP_ROWS = (
    "DELETE FROM npc_shop_items WHERE NOT EXISTS (SELECT 1 FROM characters c WHERE c.id = npc_shop_items.npc_id)"
)


@dataclass(frozen=True)
class MerchantPlace:
    """Where an NPC merchant trades: :func:`econ_core.merchant_status` over his location's region."""

    npc_id: int
    living: bool
    reason: Optional[str]              # legacy reason (econ_core.MERCHANT_REASON_*) or None
    location_id: Optional[int]
    region_id: Optional[int]           # region the location resolves to (also for legacy merchants, when any)
    tax_rate: float                    # econ_regions.tax_rate of that region (0 when none)


@dataclass
class MerchantContext:
    """The locked state of one region's living merchants (input of the merchant step)."""

    merchants: List[econ_merchant.MerchantIn]
    rows: Dict[int, tuple]             # row id -> SHOP_ROW_COLUMNS tuple of every row of those merchants
    dropped: List[int]                 # NPCs of the run map that stopped being living merchants of this region


def merchant_place(session: Session, npc_id: int) -> MerchantPlace:
    """Living / legacy status of one NPC (SQL_NPC_PLACE → SQL_RESOLVE_LOCATION → SQL_REGION_ECON)."""
    npc_row = session.execute(text(core.SQL_NPC_PLACE), {"id": int(npc_id)}).first()
    location_id = int(npc_row[3]) if npc_row is not None and npc_row[3] else None
    region_id: Optional[int] = None
    region_row = None
    if location_id is not None:
        region_id, _country_id = econ_ledger.resolve_location(session, location_id)
        if region_id is not None:
            region_row = session.execute(text(core.SQL_REGION_ECON), {"region_id": region_id}).first()
    living, reason = core.merchant_status(npc_row, region_row)
    tax_rate = float(region_row[3]) if region_row is not None and region_row[3] is not None else 0.0
    return MerchantPlace(npc_id=int(npc_id), living=living, reason=reason, location_id=location_id,
                         region_id=region_id, tax_rate=tax_rate)


def build_merchant_map(session: Session) -> Dict[int, List[int]]:
    """{region_id: [npc_id ascending]} of the living merchants (NPCs with active shop rows) of the run."""
    result: Dict[int, List[int]] = {}
    for (npc_id,) in session.execute(text(SQL_MERCHANT_NPCS)).fetchall():
        place = merchant_place(session, int(npc_id))
        if place.living and place.region_id is not None:
            result.setdefault(place.region_id, []).append(place.npc_id)
    return result


def purge_orphan_shop_rows(session: Session) -> int:
    """Delete shop rows of deleted NPCs (the caller commits); returns the number of rows removed."""
    removed = int(session.execute(text(SQL_PURGE_ORPHAN_SHOP_ROWS)).rowcount or 0)
    if removed:
        logger.info("economy tick: purged %d shop rows of deleted NPCs", removed)
    return removed


def load_item_markets(session: Session, item_ids) -> Dict[int, core.ItemMarket]:
    """{item_id: ItemMarket} (effective goods group, off-market flag) of the given items."""
    ids = sorted({int(i) for i in item_ids})
    if not ids:
        return {}
    placeholders, params = core.in_params("i", ids)
    rows = session.execute(text(core.sql_item_market(placeholders)), params).fetchall()
    return {int(r[0]): core.item_market_from_row(r) for r in rows}


def shop_row_input(row, item: Optional[core.ItemMarket]) -> econ_merchant.ShopRow:
    """A SHOP_ROW_COLUMNS tuple → econ_merchant.ShopRow (a row whose item is gone is off-market)."""
    group, off_market = (item.group, item.off_market) if item is not None else (None, True)
    return econ_merchant.ShopRow(
        row_id=int(row[0]), group=group, off_market=bool(off_market), origin=row[7] or core.SHOP_ORIGIN_ADMIN,
        base_ask=int(row[3] or 0), base_bid=int(row[4] or 0),
        stock=int(row[5]) if row[5] is not None else None, restock_target=int(row[6] or 0),
    )


def lock_merchants(session: Session, region_id: int, npc_ids, for_update: bool) -> MerchantContext:
    """Lock the merchants' shop rows (ascending id) and NPC rows (ascending id), re-check that each NPC is still a
    living merchant of this region (an admin may have moved him since the run map was built) and build the inputs."""
    ids = sorted({int(i) for i in npc_ids})
    placeholders, params = core.in_params("n", ids)
    all_rows = session.execute(text(core.sql_lock_shop_rows(placeholders, for_update, "npc_id")), params).fetchall()
    cash = econ_ledger.lock_characters(session, ids)

    kept, dropped = [], []
    for npc_id in ids:
        place = merchant_place(session, npc_id)
        if npc_id in cash and place.living and place.region_id == region_id:
            kept.append(npc_id)
        else:
            dropped.append(npc_id)
    rows = [r for r in all_rows if int(r[1]) in kept]
    items = load_item_markets(session, [r[2] for r in rows if r[8]])
    merchants = [
        econ_merchant.MerchantIn(
            npc_id=npc_id, cash=cash[npc_id],
            rows=[shop_row_input(r, items.get(int(r[2]))) for r in rows if int(r[1]) == npc_id and r[8]],
        )
        for npc_id in kept
    ]
    return MerchantContext(merchants=merchants, rows={int(r[0]): tuple(r) for r in rows}, dropped=dropped)


def merchant_failures_from_error(error: Optional[str]) -> int:
    """Number of regions listed after MERCHANT_ERROR_PREFIX in a run's error text (0 when none)."""
    if not error or MERCHANT_ERROR_PREFIX not in error:
        return 0
    tail = error.split(MERCHANT_ERROR_PREFIX, 1)[1].split(";", 1)[0]
    return len([part for part in tail.split(",") if part.strip().isdigit()])


def _merchant_step(session: Session, *, run_id: int, region_id: int, region: "models.EconRegion",
                   goods_rows, result: econ_sim.SimResult, groups: Mapping[str, econ_sim.GroupDef],
                   params: econ_sim.SimParams, ctx: MerchantContext,
                   outcome: _MerchantOutcome) -> Dict[str, float]:
    """Background trade of the region's living merchants (inside the caller's SAVEPOINT).

    Returns {group: new region stock} of the goods the merchants moved (for the history row).
    """
    purse = account_balance(session, core.AccountRef.purse(region_id))
    market = econ_merchant.market_from_sim(
        region_id, _float(region.tax_rate), purse, result.goods,
        {code: g.base_price for code, g in groups.items()},
    )
    step = econ_merchant.merchant_step(market, ctx.merchants, params)

    # 1. shop rows: new stock (a living merchant's NULL becomes a number), sold-out player-origin rows go away
    new_stock = step.new_row_stock
    purge_ids = []
    for row_id, row in sorted(ctx.rows.items()):
        stored = row[5]
        stock = new_stock.get(row_id, int(stored) if stored is not None else 0)
        if (row[7] or core.SHOP_ORIGIN_ADMIN) == core.SHOP_ORIGIN_PLAYER and stock <= 0:
            purge_ids.append(row_id)
        elif row_id in new_stock and (stored is None or int(stored) != stock):
            session.execute(text(core.SQL_SHOP_STOCK_SET), {"stock": int(stock), "id": row_id})
    if purge_ids:
        placeholders, id_params = core.in_params("p", purge_ids)
        session.execute(text(f"DELETE FROM npc_shop_items WHERE id IN ({placeholders})"), id_params)

    # 2. region goods (rows already locked by the region step)
    stock_after: Dict[str, float] = {}
    for row in goods_rows:
        delta = step.stock_delta.get(row.group_code)
        if delta is None:
            continue
        row.stock = _round(max(0.0, _float(row.stock) + delta), _SCALE_STOCK)
        stock_after[row.group_code] = float(row.stock)
    session.flush()

    # 3. one merchant_trade operation for the region
    if step.legs:
        posting = econ_ledger.post_operation(
            session, op_type=core.OP_MERCHANT_TRADE, legs=step.legs, source_service=SOURCE_SERVICE,
            region_id=region_id, idempotency_key=f"merchant_trade:{run_id}:r:{region_id}",
            metadata={"run_id": run_id, "sold_value": step.sold_value, "tax": step.tax,
                      "purse_budget": step.purse_budget, **step.metadata()},
        )
        outcome.posted = posting.operation_id is not None

    outcome.processed = len(step.merchants)
    outcome.items_sold = sum(m.sold_items for m in step.merchants)
    outcome.items_restocked = sum(m.restock_items for m in step.merchants)
    outcome.rows_purged = len(purge_ids)
    return stock_after


# --------------------------------------------------------------------------------------------- claim

def _lock_settings_row(session: Session) -> None:
    """Serialise claims on the single ``econ_sim_settings`` row (no-op on SQLite / when the row is missing)."""
    if core.supports_for_update(session.get_bind().dialect.name):
        session.execute(text("SELECT id FROM econ_sim_settings WHERE id = 1 FOR UPDATE"))


def _new_run(session: Session, *, slot: Optional[int], trigger: str, actor_user_id: Optional[int],
             now: datetime) -> "models.EconTickRun":
    run = models.EconTickRun(slot=slot, trigger_kind=trigger, actor_user_id=actor_user_id, status=STATUS_RUNNING,
                             regions_total=0, regions_done=0, regions_failed=0, started_at=now, heartbeat_at=now)
    session.add(run)
    session.flush()  # UNIQUE(slot) fires here for a second auto claim of the slot
    return run


def _fill_plan(session: Session, run: "models.EconTickRun", params: econ_sim.SimParams) -> None:
    purge_orphans(session)
    plan = build_grant_plan(session, params)
    run.grant_plan = plan
    run.regions_total = len(plan)


def _claim_auto(session: Session, now: datetime, params: econ_sim.SimParams) -> Optional[Tuple[int, bool]]:
    """(run_id, resumed) or None when the slot is already done / owned by a live process."""
    slot = slot_of(now)
    # Read first: the scheduler polls every minute, and a failed INSERT would burn an AUTO_INCREMENT id each time.
    # The INSERT below stays the real claim (UNIQUE(slot)) for the race between two processes.
    existing = session.query(models.EconTickRun).filter(models.EconTickRun.slot == slot).first()
    if existing is None:
        try:
            run = _new_run(session, slot=slot, trigger=TRIGGER_AUTO, actor_user_id=None, now=now)
            _fill_plan(session, run, params)
            _close_dead_runs(session, now, keep_slot=slot)
            session.commit()
            return int(run.id), False
        except IntegrityError:
            session.rollback()
        existing = session.query(models.EconTickRun).filter(models.EconTickRun.slot == slot).first()
    if existing is None or existing.status != STATUS_RUNNING:
        session.rollback()
        return None
    # Resume a dead run: the conditional UPDATE lets exactly one process take it over.
    result = session.execute(
        text("UPDATE econ_tick_runs SET heartbeat_at = :now WHERE id = :id AND status = :running "
             "AND heartbeat_at < :stale"),
        {"now": now, "id": int(existing.id), "running": STATUS_RUNNING, "stale": now - STALE_AFTER},
    )
    session.commit()
    if result.rowcount != 1:
        return None
    logger.warning("economy tick: resuming interrupted run %s of slot %s", existing.id, slot)
    return int(existing.id), True


def _claim_manual(session: Session, now: datetime, params: econ_sim.SimParams,
                  actor_user_id: Optional[int]) -> int:
    _lock_settings_row(session)
    _close_dead_runs(session, now, keep_slot=slot_of(now))
    alive = (session.query(models.EconTickRun)
             .filter(models.EconTickRun.status == STATUS_RUNNING,
                     models.EconTickRun.heartbeat_at >= now - STALE_AFTER)
             .order_by(models.EconTickRun.id.desc())
             .first())
    if alive is not None:
        session.rollback()
        raise RunInProgress(int(alive.id))
    run = _new_run(session, slot=None, trigger=TRIGGER_MANUAL, actor_user_id=actor_user_id, now=now)
    _fill_plan(session, run, params)
    session.commit()
    return int(run.id)


# --------------------------------------------------------------------------------------------- one region

def _round(value: float, scale: int) -> Decimal:
    if value != value or math.isinf(value):  # NaN / inf never reach the DB
        value = 0.0
    return Decimal(str(round(float(value), scale)))


def _process_region(
    session_factory: SessionFactory,
    *,
    run_id: int,
    region_id: int,
    grant: int,
    groups: Mapping[str, econ_sim.GroupDef],
    params: econ_sim.SimParams,
    country_tax_rate: float,
    now: datetime,
    merchant_npcs: Sequence[int] = (),
) -> _RegionOutcome:
    session = session_factory()
    merchants: Optional[_MerchantOutcome] = None
    try:
        for_update = core.supports_for_update(session.get_bind().dialect.name)
        query = session.query(models.EconRegion).filter(models.EconRegion.region_id == region_id)
        region = (query.with_for_update() if for_update else query).first()
        if region is None or region.template_code is None or int(region.population or 0) <= 0:
            session.rollback()
            logger.info("economy tick run %s: region %s left the simulation, skipped", run_id, region_id)
            return _RegionOutcome("skipped")
        if region.last_run_id is not None and int(region.last_run_id) == run_id:
            session.rollback()
            return _RegionOutcome("already")

        goods_query = (session.query(models.EconRegionGood)
                       .filter(models.EconRegionGood.region_id == region_id)
                       .order_by(models.EconRegionGood.group_code))
        goods_rows = (goods_query.with_for_update() if for_update else goods_query).all()

        # FEAT-183: shop rows → NPC rows are locked now (lock order 3.5), before region_tick locks any account.
        merchant_ctx: Optional[MerchantContext] = None
        if merchant_npcs:
            merchants = _MerchantOutcome()
            try:
                merchant_ctx = lock_merchants(session, region_id, merchant_npcs, for_update)
            except Exception as exc:  # reads only: nothing to undo, the region goes on without merchants
                merchants.failed = True
                logger.error("economy tick run %s: region %s merchants could not be loaded (%s), skipped",
                             run_id, region_id, type(exc).__name__, exc_info=True)
            if merchant_ctx is not None and merchant_ctx.dropped:
                logger.info("economy tick run %s: region %s — NPCs %s are no longer its living merchants",
                            run_id, region_id, merchant_ctx.dropped)

        country_id = session.execute(text("SELECT country_id FROM Regions WHERE id = :id"),
                                     {"id": region_id}).scalar()
        country_id = int(country_id) if country_id is not None else None
        if country_id is None:
            grant = 0
        purse_ref = core.AccountRef.purse(region_id)
        treasury_ref = core.AccountRef.region(region_id)
        purse = account_balance(session, purse_ref)
        treasury = account_balance(session, treasury_ref)

        result = econ_sim.simulate_region(
            region_state(region), {row.group_code: good_state(row) for row in goods_rows}, groups,
            purse=purse, treasury=treasury, grant=grant,
            country_tax_rate=country_tax_rate if country_id is not None else 0.0, params=params,
        )

        state = result.region
        region.stability = _round(state.stability, _SCALE_STAB)
        region.prosperity = _round(state.prosperity, _SCALE_STAB)
        region.hunger = _round(state.hunger, _SCALE_SHARE)
        region.satisfaction = _round(state.satisfaction, _SCALE_SHARE)
        region.treasury_target = int(state.treasury_target)
        region.last_income = result.income
        region.last_tax = result.tax
        region.last_wages = result.wages
        region.last_grant = result.grant
        region.last_run_id = run_id
        region.last_tick_at = now
        for row in goods_rows:
            good = result.goods.get(row.group_code)
            if good is None:
                continue
            row.stock = _round(good.stock, _SCALE_STOCK)
            row.norm_stock = _round(good.norm_stock, _SCALE_STOCK)
            row.price_mult = _round(good.price_mult, _SCALE_PRICE)
            row.prev_price_mult = _round(good.prev_price_mult, _SCALE_PRICE)
            row.last_produced = _round(good.last_produced, _SCALE_STOCK)
            row.last_consumed = _round(good.last_consumed, _SCALE_STOCK)
            row.last_demand = _round(good.last_demand, _SCALE_STOCK)
            row.last_spoiled = _round(good.last_spoiled, _SCALE_STOCK)

        legs = [core.Leg(purse_ref, treasury_ref, result.tax)]
        if country_id is not None:
            legs.append(core.Leg(core.AccountRef.country(country_id), treasury_ref, result.grant))
        legs.append(core.Leg(treasury_ref, purse_ref, result.wages))
        posting = econ_ledger.post_operation(
            session, op_type=core.OP_REGION_TICK, legs=legs, source_service=SOURCE_SERVICE, region_id=region_id,
            idempotency_key=f"region_tick:{run_id}:r:{region_id}",
            metadata={"run_id": run_id, "tax": result.tax, "grant": result.grant, "wages": result.wages,
                      "income": result.income, "hunger": round(state.hunger, _SCALE_SHARE)},
        )
        if purse == 0 and result.wages == 0:
            logger.warning(
                "economy tick run %s: region %s is stuck — empty population purse, no country grant and no treasury "
                "surplus: no tax, no wages, people cannot buy (hunger %.2f); fill the purse or fund the treasury",
                run_id, region_id, state.hunger,
            )

        merchant_stock: Dict[str, float] = {}
        if merchant_ctx is not None and merchant_ctx.merchants:
            step_outcome = _MerchantOutcome()
            session.flush()  # region updates hit the DB before the SAVEPOINT (also starts pysqlite's transaction)
            try:
                with session.begin_nested():
                    merchant_stock = _merchant_step(
                        session, run_id=run_id, region_id=region_id, region=region, goods_rows=goods_rows,
                        result=result, groups=groups, params=params, ctx=merchant_ctx, outcome=step_outcome)
                merchants = step_outcome
            except core.DuplicateOperation:
                logger.info("economy tick run %s: region %s merchants already posted by another runner",
                            run_id, region_id)
                merchant_stock = {}
            except Exception as exc:  # a broken merchant must not roll the region back
                merchant_stock = {}
                merchants = _MerchantOutcome(failed=True)
                logger.error("economy tick run %s: region %s merchant step failed (%s), rolled back; the region "
                             "ticked without merchants", run_id, region_id, type(exc).__name__, exc_info=True)

        session.add(models.EconRegionHistory(
            run_id=run_id, region_id=region_id, created_at=now, population=int(region.population),
            stability=region.stability, prosperity=region.prosperity, hunger=region.hunger,
            purse=account_balance(session, purse_ref), treasury=account_balance(session, treasury_ref),
            income=result.income, tax=result.tax, wages=result.wages, grant_amount=result.grant,
            goods={code: {"stock": round(merchant_stock.get(code, g.stock), _SCALE_STOCK),
                          "price_mult": round(g.price_mult, _SCALE_PRICE),
                          "produced": round(g.last_produced, _SCALE_STOCK),
                          "consumed": round(g.last_consumed, _SCALE_STOCK)}
                   for code, g in result.goods.items()},
        ))
        session.commit()
        return _RegionOutcome("done", posted=posting.operation_id is not None, merchants=merchants)
    except core.DuplicateOperation:
        # Posted by an overlapping runner of the same run: the region is done, nothing moved twice.
        session.rollback()
        logger.info("economy tick run %s: region %s already posted by another runner", run_id, region_id)
        return _RegionOutcome("already")
    except Exception as exc:  # one broken region must not stop the others
        session.rollback()
        logger.error("economy tick run %s: region %s failed (%s), will be retried next tick",
                     run_id, region_id, type(exc).__name__, exc_info=True)
        return _RegionOutcome("failed")
    finally:
        session.close()


# --------------------------------------------------------------------------------------------- the run

def _heartbeat(session_factory: SessionFactory, run_id: int, now: datetime, done: int, failed: int) -> None:
    session = session_factory()
    try:
        session.execute(
            text("UPDATE econ_tick_runs SET heartbeat_at = :now, regions_done = :done, regions_failed = :failed "
                 "WHERE id = :id"),
            {"now": now, "done": done, "failed": failed, "id": run_id},
        )
        session.commit()
    except Exception:
        session.rollback()
        logger.warning("economy tick run %s: heartbeat failed", run_id, exc_info=True)
    finally:
        session.close()


def run_tick(
    session_factory: Optional[SessionFactory] = None,
    *,
    trigger: str = TRIGGER_AUTO,
    actor_user_id: Optional[int] = None,
    now: Optional[datetime] = None,
    clock: Optional[Callable[[], datetime]] = None,
) -> Optional[RunSummary]:
    """Run (or resume) one simulation step of every participating region.

    ``trigger='auto'`` claims the current 6 h slot and returns ``None`` when the slot is already done or owned by a
    live process. ``trigger='manual'`` always runs an extra step (slot NULL) and raises :class:`RunInProgress` while
    another run is alive. ``now`` fixes the run's clock (tests); ``clock`` overrides the heartbeat clock.
    Never commits on the caller's behalf: it opens its own sessions from ``session_factory``
    (default ``database.SessionLocal``).
    """
    if trigger not in (TRIGGER_AUTO, TRIGGER_MANUAL):
        raise ValueError(f"unknown trigger {trigger!r}")
    if session_factory is None:
        import database  # late: tests patch database.SessionLocal before use
        session_factory = database.SessionLocal
    start = _naive_utc(now)
    tick_clock = clock or ((lambda: start) if now is not None else _utcnow)

    session = session_factory()
    try:
        params = load_params(session)
        session.rollback()  # the claim must start a fresh transaction (MySQL REPEATABLE READ snapshot)
        if trigger == TRIGGER_AUTO:
            claimed = _claim_auto(session, start, params)
            if claimed is None:
                return None
            run_id, resumed = claimed
        else:
            run_id, resumed = _claim_manual(session, start, params, actor_user_id), False
        run = session.get(models.EconTickRun, run_id)
        plan = {int(k): int(v) for k, v in (_json(run.grant_plan) or {}).items()}
        summary = RunSummary(run_id=run_id, trigger=run.trigger_kind, slot=run.slot, status=STATUS_RUNNING,
                             resumed=resumed, regions_total=len(plan), started_at=run.started_at)
        groups = load_groups(session)
        country_tax_rate = float(econ_ledger.get_economy_settings(session).country_tax_rate)
        session.rollback()  # release the read snapshot; the run row is not held
    finally:
        session.close()

    merchant_map, summary.shop_rows_purged = _prepare_merchants(session_factory, run_id)

    logger.info("economy tick run %s (%s, slot %s)%s: %d regions, %d living merchants", run_id, summary.trigger,
                summary.slot, " resumed" if resumed else "", len(plan), sum(len(v) for v in merchant_map.values()))
    for region_id, grant in sorted(plan.items()):
        outcome = _process_region(session_factory, run_id=run_id, region_id=region_id, grant=grant, groups=groups,
                                  params=params, country_tax_rate=country_tax_rate, now=start,
                                  merchant_npcs=merchant_map.get(region_id, ()))
        if outcome.status == "failed":
            summary.regions_failed += 1
            summary.failed_region_ids.append(region_id)
        else:
            summary.regions_done += 1
            if outcome.posted:
                summary.operations_posted += 1
        m = outcome.merchants
        if m is not None and outcome.status == "done":
            if m.failed:
                summary.merchant_failures += 1
                summary.merchant_failed_region_ids.append(region_id)
            summary.merchants_processed += m.processed
            summary.merchant_items_sold += m.items_sold
            summary.merchant_items_restocked += m.items_restocked
            summary.shop_rows_purged += m.rows_purged
            if m.posted:
                summary.merchant_ops_posted += 1
        _heartbeat(session_factory, run_id, tick_clock(), summary.regions_done, summary.regions_failed)

    if summary.regions_failed == 0:
        summary.status = STATUS_DONE
    elif summary.regions_done == 0:
        summary.status = STATUS_FAILED
    else:
        summary.status = STATUS_PARTIAL
    summary.finished_at = tick_clock()

    session = session_factory()
    try:
        parts = []
        if summary.failed_region_ids:
            parts.append("ошибка в регионах: " + ", ".join(str(r) for r in summary.failed_region_ids))
        if summary.merchant_failed_region_ids:
            parts.append(MERCHANT_ERROR_PREFIX + ", ".join(str(r) for r in summary.merchant_failed_region_ids))
        error = "; ".join(parts)[:MAX_ERROR_LEN] or None
        session.execute(
            text("UPDATE econ_tick_runs SET status = :status, regions_done = :done, regions_failed = :failed, "
                 "error = :error, heartbeat_at = :now, finished_at = :now WHERE id = :id"),
            {"status": summary.status, "done": summary.regions_done, "failed": summary.regions_failed,
             "error": error, "now": summary.finished_at, "id": run_id},
        )
        session.commit()
        try:
            purge_old(session, params, start)
            session.commit()
        except Exception:
            session.rollback()
            logger.warning("economy tick run %s: housekeeping failed", run_id, exc_info=True)
    finally:
        session.close()

    log = logger.warning if (summary.regions_failed or summary.merchant_failures) else logger.info
    log("economy tick run %s finished: %s, %d/%d regions done, %d failed, %d operations posted; merchants: %d "
        "processed, %d sold, %d restocked, %d operations, %d failed regions",
        run_id, summary.status, summary.regions_done, summary.regions_total, summary.regions_failed,
        summary.operations_posted, summary.merchants_processed, summary.merchant_items_sold,
        summary.merchant_items_restocked, summary.merchant_ops_posted, summary.merchant_failures)
    return summary


def _prepare_merchants(session_factory: SessionFactory, run_id: int) -> Tuple[Dict[int, List[int]], int]:
    """Run start (FEAT-183): purge shop rows of deleted NPCs, then map the living merchants to their regions.

    Both are best effort: a failure (e.g. ``npc_shop_items`` not migrated yet) is logged and the run goes on
    without merchants — regions must tick regardless.
    """
    purged = 0
    merchant_map: Dict[int, List[int]] = {}
    session = session_factory()
    try:
        try:
            purged = purge_orphan_shop_rows(session)
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.warning("economy tick run %s: orphan shop rows purge failed (%s)", run_id, type(exc).__name__)
        try:
            merchant_map = build_merchant_map(session)
        except Exception as exc:
            logger.warning("economy tick run %s: NPC merchants unavailable (%s), regions tick without them",
                           run_id, type(exc).__name__)
            merchant_map = {}
        session.rollback()
    finally:
        session.close()
    return merchant_map, purged


def run_manual(actor_user_id: Optional[int], session_factory: Optional[SessionFactory] = None) -> RunSummary:
    """Admin «Пересчитать сейчас»: an extra real step, logged as a manual run. Raises :class:`RunInProgress`."""
    summary = run_tick(session_factory, trigger=TRIGGER_MANUAL, actor_user_id=actor_user_id)
    assert summary is not None  # manual runs never return None
    return summary
