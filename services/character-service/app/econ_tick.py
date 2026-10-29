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
* **housekeeping** — economy rows of deleted regions are purged before the step, history older than
  ``history_retention_days`` and runs beyond the newest :data:`KEEP_RUNS` after it.

Lock order inside a region transaction: business rows (``econ_regions`` → ``econ_region_goods``) → ``econ_accounts``
ascending (done by ``post_operation``); no ``characters`` rows are touched.

Pure math lives in ``econ_sim``; this module only loads, stores and posts. The scheduler thread is ``econ_scheduler``.
"""

import calendar
import json
import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Dict, List, Mapping, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import econ_core as core
import econ_ledger
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
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in ("started_at", "finished_at"):
            data[key] = data[key].isoformat() if data[key] else None
        return data


@dataclass
class _RegionOutcome:
    status: str                 # done | already | skipped | failed
    posted: bool = False


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
) -> _RegionOutcome:
    session = session_factory()
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

        session.add(models.EconRegionHistory(
            run_id=run_id, region_id=region_id, created_at=now, population=int(region.population),
            stability=region.stability, prosperity=region.prosperity, hunger=region.hunger,
            purse=account_balance(session, purse_ref), treasury=account_balance(session, treasury_ref),
            income=result.income, tax=result.tax, wages=result.wages, grant_amount=result.grant,
            goods={code: {"stock": round(g.stock, _SCALE_STOCK), "price_mult": round(g.price_mult, _SCALE_PRICE),
                          "produced": round(g.last_produced, _SCALE_STOCK),
                          "consumed": round(g.last_consumed, _SCALE_STOCK)}
                   for code, g in result.goods.items()},
        ))
        session.commit()
        return _RegionOutcome("done", posted=posting.operation_id is not None)
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

    logger.info("economy tick run %s (%s, slot %s)%s: %d regions", run_id, summary.trigger, summary.slot,
                " resumed" if resumed else "", len(plan))
    for region_id, grant in sorted(plan.items()):
        outcome = _process_region(session_factory, run_id=run_id, region_id=region_id, grant=grant, groups=groups,
                                  params=params, country_tax_rate=country_tax_rate, now=start)
        if outcome.status == "failed":
            summary.regions_failed += 1
            summary.failed_region_ids.append(region_id)
        else:
            summary.regions_done += 1
            if outcome.posted:
                summary.operations_posted += 1
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
        error = None
        if summary.failed_region_ids:
            error = ("ошибка в регионах: " + ", ".join(str(r) for r in summary.failed_region_ids))[:MAX_ERROR_LEN]
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

    log = logger.warning if summary.regions_failed else logger.info
    log("economy tick run %s finished: %s, %d/%d regions done, %d failed, %d operations posted",
        run_id, summary.status, summary.regions_done, summary.regions_total, summary.regions_failed,
        summary.operations_posted)
    return summary


def run_manual(actor_user_id: Optional[int], session_factory: Optional[SessionFactory] = None) -> RunSummary:
    """Admin «Пересчитать сейчас»: an extra real step, logged as a manual run. Raises :class:`RunInProgress`."""
    summary = run_tick(session_factory, trigger=TRIGGER_MANUAL, actor_user_id=actor_user_id)
    assert summary is not None  # manual runs never return None
    return summary
