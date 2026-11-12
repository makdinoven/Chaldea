"""FEAT-192 NPC caravans — DB layer (sync SQLAlchemy).

* **tick** (3.7 / 3.8) — called by ``econ_tick._caravan_pass``: :func:`advance_and_finish` (arrivals: advance the
  travel counter, deliver or cancel), then :func:`load_snapshot` → ``econ_caravan.plan_caravans`` (pure) →
  :func:`dispatch` per plan. Every dispatch / advance / finish is its own transaction (opened from the session
  factory, committed here); a failure rolls back that caravan only;
* **money** (3.4) — the buyer pays at dispatch into the singleton ``caravan_escrow`` («Караваны в пути»), the escrow
  pays the seller's purse (+ the duty to the buyer's country) on delivery, or refunds the payers in full on a cancel.
  Fallbacks when an account owner is gone: a deleted region's purse / treasury → its country treasury (stored on the
  row), a deleted country → the world treasury. All postings ``apply_tax=False``; no source accounts are touched;
* **admin reads / writes** (3.11), the region-card lines (3.12) and the escrow sub-invariant (summary).

Lock order (3.9, global): ``econ_regions (asc region_id) → econ_region_goods (asc region_id, group_code) →
econ_region_events (asc id) → econ_caravans (asc id) → econ_mint_seasons → npc_shop_items (asc id) → econ_banks
(asc region_id) → bank_deposits (asc id) → bank_loans (asc id) → character_inventory (asc id) → characters (asc id) →
econ_accounts (asc id)``. Dispatch: ``econ_regions ×2 asc → econ_region_goods(seller) → [INSERT econ_caravans] →
econ_accounts``; finish: ``econ_regions ×≤2 asc → econ_region_goods ×≤2 asc → econ_caravans(row) → econ_accounts``;
advance: ``econ_caravans(row)`` only. Runs are serial (``RunInProgress``) and nobody else inserts caravans, so the
dispatch INSERT under the region locks cannot meet another inserter. ``econ_trade_pairs`` is never locked.

FEAT-211 physical caravans: :class:`RoutePlanner` (built once per caravan pass of the tick) decides at dispatch whether
a caravan goes by road (``econ_caravan.choose_physical``) and stores its BFS route between the two regions' trade
gates; the caravan pass (``caravan_pass.py``, every ~55 s) steps it one location per interval and calls
:func:`deliver_physical` on arrival (no run-id logic). Global lock order (FEAT-211 3.16, supersedes the FEAT-207 one):
``econ_regions (asc region_id) → econ_region_goods (asc region_id, group_code) → econ_region_events → econ_caravans
(asc id) → econ_caravan_raids (asc id) → econ_caravan_raid_shares → econ_guild_orders → … (unchanged FEAT-207 chain) …
→ character_inventory → characters (asc id) → econ_accounts (asc id) → character_attributes``. The step transaction
locks only ``econ_caravans(row)``; delivery takes regions → goods → caravan (never the caravan first).
``econ_fences``, ``econ_caravan_guard_templates`` and the locations-service gate tables are plain reads, never locked.
The escrow sub-invariant is ``escrow == Σ (paid_purse + paid_treasury − raid_paid)`` of caravans in transit.

FEAT-212 player escorts (global lock order 3.15, supersedes the FEAT-211 one): ``econ_regions → econ_region_goods →
econ_region_events → econ_caravans (asc) → econ_caravan_raids → econ_caravan_escorts (asc id) →
econ_caravan_raid_shares → … → characters (asc id, ONE sorted lock call per tx) → econ_accounts (asc) →
character_attributes``. Delivery: regions → goods → caravan → escorts → their characters → accounts; the escort pay
is extra legs ``escrow → character`` of the same ``caravan_delivery`` op, carved out of the seller part (so the escrow
sub-invariant is unchanged). The step transaction: caravan → escorts → characters (``caravan_escort_crud``).
"""

import json
import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import caravan_route
import econ_caravan
import econ_core as core
import econ_events
import econ_ledger
import econ_sim
import models
import patrol_core
from economy_crud import EconomyApiError

logger = logging.getLogger("character-service.caravans")

SOURCE_SERVICE = "character-service"

STATUS_IN_TRANSIT = "in_transit"
STATUS_DELIVERED = "delivered"
STATUS_CANCELLED = "cancelled"
STATUSES = (STATUS_IN_TRANSIT, STATUS_DELIVERED, STATUS_CANCELLED)

REASON_DESTINATION_LEFT = "destination_left"
REASON_DESTINATION_DELETED = "destination_deleted"

KEY_PAY = "pay"
KEY_DONE = "done"
KEY_BACK = "back"

DEFAULT_DUTY_PCT = 10.0

CARD_RECENT_HOURS = 24
CARD_MAX_LINES = 6

CARAVAN_PARAM_KEYS = (
    "caravans_enabled", "caravan_surplus_share", "caravan_purse_share", "caravan_treasury_food_share",
    "caravan_travel_domestic", "caravan_travel_foreign", "caravan_min_value", "caravan_max_per_run",
    # FEAT-211 physical caravans and raids (3.14)
    "caravan_physical_enabled", "caravan_physical_min_value", "caravan_physical_small_chance",
    "caravan_physical_max_active", "caravan_step_minutes", "caravan_route_max_steps", "caravan_post_hold_max_min",
    "caravan_raid_battle_max_hours", "caravan_raid_marks_share", "caravan_raid_goods_share",
    "caravan_guard_count_base", "caravan_guard_value_per_extra", "caravan_guard_count_max",
    "caravan_guard_mult_per_1000", "caravan_guard_mult_max", "caravan_guard_mult_dangerous",
    "caravan_rep_trade_share", "fence_purse_share",
    # FEAT-212 player escorts (3.4)
    "caravan_departure_minutes", "caravan_escort_seats", "caravan_escort_fee_share", "caravan_escort_bonus_share",
    "caravan_escort_defense_fame",
)

# FEAT-211 physical caravans
STEP_JITTER_PCT = 25                       # ± jitter of caravan_step_minutes (patrol_core.next_delay)
RAID_ACTIVE_STATUSES = ("starting", "fighting")
GATE_ACTION_CARAVAN = "caravan"            # locations-service action_gates.action_type / post gate requests
MARKER_DUNGEON = "dungeon"
KIND_ALL, KIND_PHYSICAL, KIND_ABSTRACT = "all", "physical", "abstract"
GUARD_POOL_MAX = 20

MSG_REGION_NOT_FOUND = "Край не найден"
MSG_GATE_WRONG_REGION = "Локация не принадлежит этому краю"
MSG_GATE_DUNGEON = "Подземелье не может быть торговыми воротами"
MSG_CARAVAN_NOT_FOUND = "Караван не найден"
MSG_MOB_TEMPLATE_NOT_FOUND = "Шаблон моба не найден: {id}"

# Russian texts (contract 3.11)
MSG_SAME_COUNTRY = "Страна не может торговать сама с собой"
MSG_COUNTRY_NOT_FOUND = "Страна не найдена"
MSG_UNKNOWN_GROUP = "Неизвестная группа товаров"

SessionFactory = Callable[[], Session]

_THOUSANDTH = Decimal("0.001")


def caravan_key(caravan_id: int, part: str) -> str:
    return f"caravan:c{int(caravan_id)}:{part}"


def _for_update(db: Session) -> bool:
    return core.supports_for_update(db.get_bind().dialect.name)


def _i(value) -> int:
    return int(value or 0)


def _f(value) -> float:
    return float(value or 0)


def _dec3(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(_THOUSANDTH)


def caravans_available(db: Session) -> bool:
    """True when migration 035 is applied (the tick and the summary tolerate its absence)."""
    names = set(sa_inspect(db.get_bind()).get_table_names())
    return "econ_caravans" in names and "econ_trade_pairs" in names


def _participates(region: Optional["models.EconRegion"]) -> bool:
    return region is not None and region.template_code is not None and _i(region.population) > 0


def _region_exists(db: Session, region_id: int) -> bool:
    return db.execute(text("SELECT 1 FROM Regions WHERE id = :r"), {"r": int(region_id)}).first() is not None


def _country_exists(db: Session, country_id: Optional[int]) -> bool:
    if not country_id:
        return False
    return db.execute(text("SELECT 1 FROM Countries WHERE id = :c"), {"c": int(country_id)}).first() is not None


def _region_country(db: Session, region_id: int) -> Optional[int]:
    value = db.execute(text("SELECT country_id FROM Regions WHERE id = :r"), {"r": int(region_id)}).scalar()
    return int(value) if value is not None else None


# =====================================================================================================================
# Escrow sub-invariant (summary)
# =====================================================================================================================

def escrow_expected(db: Session) -> int:
    """Σ (paid_purse + paid_treasury − raid_paid) of caravans on the road (FEAT-211: a raid pays raiders out of the
    escrow); 0 before migration 035."""
    if not caravans_available(db):
        return 0
    return _i(db.execute(text(
        "SELECT COALESCE(SUM(paid_purse + paid_treasury - raid_paid), 0) FROM econ_caravans WHERE status = :s"),
        {"s": STATUS_IN_TRANSIT}).scalar())


def escrow_balance(db: Session) -> int:
    return _i(db.execute(text("SELECT balance FROM econ_accounts WHERE kind = :k AND ref_id = 0"),
                         {"k": core.KIND_CARAVAN_ESCROW}).scalar())


# =====================================================================================================================
# Trade pairs
# =====================================================================================================================

def enabled_pairs(db: Session) -> Dict[Tuple[int, int], econ_caravan.PairRule]:
    rows = db.execute(text(
        "SELECT country_a, country_b, is_enabled, duty_pct FROM econ_trade_pairs WHERE is_enabled = 1")).fetchall()
    return {econ_caravan.pair_key(r[0], r[1]): econ_caravan.PairRule(*econ_caravan.pair_key(r[0], r[1]), True, _f(r[3]))
            for r in rows}


def _pair_rule(db: Session, country_a: int, country_b: int) -> Optional[econ_caravan.PairRule]:
    a, b = econ_caravan.pair_key(country_a, country_b)
    row = db.execute(text(
        "SELECT is_enabled, duty_pct FROM econ_trade_pairs WHERE country_a = :a AND country_b = :b"),
        {"a": a, "b": b}).first()
    if row is None:
        return None
    return econ_caravan.PairRule(a, b, bool(row[0]), _f(row[1]))


# =====================================================================================================================
# Snapshot (3.7) — plain reads, no locks
# =====================================================================================================================

@dataclass
class Snapshot:
    markets: Dict[int, econ_caravan.RegionMarket] = field(default_factory=dict)
    inbound: Dict[Tuple[int, str], float] = field(default_factory=dict)
    pairs: Dict[Tuple[int, int], econ_caravan.PairRule] = field(default_factory=dict)


def _halted_regions(active_map: Mapping[int, Sequence], group_codes: Sequence[str], params) -> set:
    """Regions with an active «Набег» / «Бунт» (merchants_halt) — they do not export."""
    halted = set()
    for region_id, rows in (active_map or {}).items():
        if not rows:
            continue
        effects = econ_events.aggregate([econ_events.parse_effects(e) for e in rows], list(group_codes), params)
        if effects.merchants_halt:
            halted.add(int(region_id))
    return halted


def load_snapshot(db: Session, run_id: int, params, groups: Mapping[str, econ_sim.GroupDef],
                  active_map: Optional[Mapping[int, Sequence]] = None) -> Snapshot:
    """Participating regions with a country that have not ticked in this run, their goods, purse / treasury
    balances, goods on the road to them and the enabled country pairs."""
    import econ_tick  # late: econ_tick imports this module lazily for the pass
    snap = Snapshot()
    regions = [(rid, country) for rid, _pop, country in econ_tick.participating_regions(db) if country is not None]
    if not regions:
        return snap
    ids = [rid for rid, _country in regions]
    placeholders, params_in = core.in_params("r", ids)
    ticked = {int(r[0]) for r in db.execute(text(
        f"SELECT region_id FROM econ_regions WHERE region_id IN ({placeholders}) AND last_run_id = :run"),
        {**params_in, "run": int(run_id)}).fetchall()}
    goods: Dict[int, Dict[str, econ_caravan.GoodMarket]] = {}
    for rid, code, stock, norm, mult in db.execute(text(
            "SELECT region_id, group_code, stock, norm_stock, price_mult FROM econ_region_goods "
            f"WHERE region_id IN ({placeholders})"), params_in).fetchall():
        if code in groups:
            goods.setdefault(int(rid), {})[code] = econ_caravan.GoodMarket(_f(stock), _f(norm), _f(mult))
    balances: Dict[Tuple[str, int], int] = {}
    for kind, ref_id, balance in db.execute(text(
            "SELECT kind, ref_id, balance FROM econ_accounts WHERE kind IN ('population_purse', 'region_treasury') "
            f"AND ref_id IN ({placeholders})"), params_in).fetchall():
        balances[(kind, int(ref_id))] = _i(balance)
    # A resumed run re-plans from the already reduced stock: a seller that already sent a group in this run
    # must not ship a second share of it, or the «X % of surplus per recount» cap would not hold. Capping the
    # snapshot stock at norm removes it from the sellers (and needs nothing as a buyer either).
    for rid, code in db.execute(text(
            "SELECT DISTINCT from_region_id, group_code FROM econ_caravans WHERE dispatch_run_id = :run"),
            {"run": int(run_id)}).fetchall():
        market = goods.get(int(rid), {}).get(code)
        if market is not None and market.stock > market.norm_stock:
            goods[int(rid)][code] = econ_caravan.GoodMarket(market.norm_stock, market.norm_stock, market.price_mult)
    halted = _halted_regions(active_map or {}, list(groups), params)
    for rid, country in regions:
        if rid in ticked:
            continue
        snap.markets[rid] = econ_caravan.RegionMarket(
            region_id=rid, country_id=int(country), halted=rid in halted,
            purse=balances.get((core.KIND_POPULATION_PURSE, rid), 0),
            treasury=balances.get((core.KIND_REGION_TREASURY, rid), 0),
            goods=goods.get(rid, {}),
        )
    for rid, code, units in db.execute(text(
            "SELECT to_region_id, group_code, SUM(units - stolen_units) FROM econ_caravans WHERE status = :s "
            "GROUP BY to_region_id, group_code"), {"s": STATUS_IN_TRANSIT}).fetchall():
        snap.inbound[(int(rid), code)] = _f(units)
    snap.pairs = enabled_pairs(db)
    return snap


# =====================================================================================================================
# Dispatch (3.7) — one transaction per plan
# =====================================================================================================================

def _lock_regions(db: Session, region_ids: Sequence[int]) -> Dict[int, "models.EconRegion"]:
    """``econ_regions`` FOR UPDATE, ascending region_id (3.9)."""
    ids = sorted({int(r) for r in region_ids})
    q = (db.query(models.EconRegion).filter(models.EconRegion.region_id.in_(ids))
         .order_by(models.EconRegion.region_id))
    rows = (q.with_for_update() if _for_update(db) else q).populate_existing().all()
    return {int(r.region_id): r for r in rows}


def _lock_goods(db: Session, keys: Sequence[Tuple[int, str]]) -> Dict[Tuple[int, str], "models.EconRegionGood"]:
    """``econ_region_goods`` rows FOR UPDATE one by one, ascending (region_id, group_code) (3.9)."""
    found: Dict[Tuple[int, str], models.EconRegionGood] = {}
    for region_id, code in sorted(set(keys)):
        q = db.query(models.EconRegionGood).filter(models.EconRegionGood.region_id == int(region_id),
                                                   models.EconRegionGood.group_code == code)
        row = (q.with_for_update() if _for_update(db) else q).populate_existing().first()
        if row is not None:
            found[(int(region_id), code)] = row
    return found


def _lock_balances(db: Session, refs: Sequence[core.AccountRef]) -> Dict[core.AccountRef, int]:
    """Create the accounts if needed, then lock them ascending id (the ledger posts into them next)."""
    ids = {ref: econ_ledger.get_or_create_account(db, ref) for ref in refs}
    placeholders, params = core.in_params("a", sorted(set(ids.values())))
    rows = db.execute(text(
        f"SELECT id, balance FROM econ_accounts WHERE id IN ({placeholders}) ORDER BY id"
        + (" FOR UPDATE" if _for_update(db) else "")), params).fetchall()
    by_id = {int(r[0]): _i(r[1]) for r in rows}
    return {ref: by_id.get(acc_id, 0) for ref, acc_id in ids.items()}


@dataclass(frozen=True)
class DispatchResult:
    status: str                         # sent | already | skipped
    caravan_id: Optional[int] = None
    value: int = 0
    is_physical: bool = False


# =====================================================================================================================
# FEAT-211 roads (3.2): graph, trade gates, route planner
# =====================================================================================================================

def _json_list(value) -> List:
    if value is None:
        return []
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return list(value) if isinstance(value, (list, tuple)) else []


@dataclass
class RoadGraph:
    adj: Dict[int, List[int]] = field(default_factory=dict)
    blocked: set = field(default_factory=set)              # dungeon locations: never walked through
    markers: Dict[int, Optional[str]] = field(default_factory=dict)


def load_road_graph(db: Session) -> RoadGraph:
    """``LocationNeighbors`` edges + ``Locations.marker_type`` (two plain SELECTs)."""
    graph = RoadGraph()
    graph.adj = caravan_route.build_adjacency(
        (r[0], r[1]) for r in db.execute(text("SELECT location_id, neighbor_id FROM LocationNeighbors")).fetchall())
    for loc_id, marker in db.execute(text("SELECT id, marker_type FROM Locations")).fetchall():
        graph.markers[int(loc_id)] = marker
        if marker == MARKER_DUNGEON:
            graph.blocked.add(int(loc_id))
    return graph


def region_gates(db: Session, region_ids: Optional[Sequence[int]] = None) -> Dict[int, dict]:
    """``{region_id: {override, station, gate, source}}`` of the simulated regions (``econ_regions`` rows that still
    exist in ``Regions``): override = ``econ_regions.trade_gate_location_id``, station = ``Regions.jail_location_id``."""
    rows = db.execute(text(
        "SELECT e.region_id, e.trade_gate_location_id, r.jail_location_id FROM econ_regions e "
        "JOIN Regions r ON r.id = e.region_id ORDER BY e.region_id")).fetchall()
    wanted = {int(r) for r in region_ids} if region_ids is not None else None
    out: Dict[int, dict] = {}
    for rid, override, station in rows:
        rid = int(rid)
        if wanted is not None and rid not in wanted:
            continue
        gate, source = caravan_route.effective_gate(override, station)
        out[rid] = {"override": int(override) if override else None, "station": int(station) if station else None,
                    "gate": gate, "source": source}
    return out


def active_physical_count(db: Session) -> int:
    return _i(db.execute(text("SELECT COUNT(*) FROM econ_caravans WHERE is_physical = 1 AND status = :s"),
                         {"s": STATUS_IN_TRANSIT}).scalar())


class RoutePlanner:
    """Graph + gates + the number of physical caravans on the road; built once per caravan pass of the tick."""

    def __init__(self, graph: RoadGraph, gates: Mapping[int, dict], active: int, max_steps: int):
        self.graph = graph
        self.gates = dict(gates)
        self.active = int(active)
        self.max_steps = int(max_steps)
        self._cache: Dict[Tuple[int, int], Tuple[Optional[List[int]], Optional[str]]] = {}

    def gate(self, region_id: int) -> Optional[int]:
        info = self.gates.get(int(region_id))
        return info["gate"] if info else None

    def route(self, from_region_id: int, to_region_id: int) -> Tuple[Optional[List[int]], Optional[str]]:
        key = (int(from_region_id), int(to_region_id))
        if key not in self._cache:
            start, goal = self.gate(key[0]), self.gate(key[1])
            if not start or not goal:
                self._cache[key] = (None, caravan_route.NO_ROAD_NO_GATE)
            else:
                self._cache[key] = caravan_route.shortest_route(self.graph.adj, self.graph.blocked, start, goal,
                                                                self.max_steps)
        return self._cache[key]


def build_planner(db: Session, params) -> RoutePlanner:
    return RoutePlanner(load_road_graph(db), region_gates(db), active_physical_count(db),
                        int(params.caravan_route_max_steps))


def step_delay(params, u: float) -> timedelta:
    """Time on one location: ``caravan_step_minutes`` ± 25 % (``patrol_core.next_delay``)."""
    return patrol_core.next_delay(int(params.caravan_step_minutes), STEP_JITTER_PCT, u)


def departure_delay(params, u: float) -> timedelta:
    """FEAT-212 3.2: a newborn physical caravan stands at the seller gate ``caravan_departure_minutes`` (the escort
    hire window, «сборы»); 0 = the old behaviour (one ordinary ``step_delay``)."""
    minutes = int(getattr(params, "caravan_departure_minutes", 0) or 0)
    if minutes > 0:
        return timedelta(minutes=minutes)
    return step_delay(params, u)


def dispatch(db: Session, plan: econ_caravan.CaravanPlan, *, run_id: int, params, now: datetime,
             planner: Optional[RoutePlanner] = None) -> DispatchResult:
    """Send one planned caravan (no commit; the caller commits / rolls back). FEAT-211: with a ``planner`` the
    caravan may go by road (3.2) — the route is stored on the row and the planner is NOT updated here (the caller
    counts it after the commit)."""
    regions = _lock_regions(db, [plan.from_region_id, plan.to_region_id])
    seller, buyer = regions.get(plan.from_region_id), regions.get(plan.to_region_id)
    for region in (seller, buyer):
        if not _participates(region):
            return DispatchResult("skipped")
        if region.last_run_id is not None and int(region.last_run_id) == int(run_id):
            return DispatchResult("skipped")
    goods = _lock_goods(db, [(plan.from_region_id, plan.group_code)]).get((plan.from_region_id, plan.group_code))
    if goods is None:
        return DispatchResult("skipped")
    from_country = _region_country(db, plan.from_region_id)
    to_country = _region_country(db, plan.to_region_id)
    if from_country is None or to_country is None:
        return DispatchResult("skipped")
    pairs = {}
    if from_country != to_country:
        rule = _pair_rule(db, from_country, to_country)
        if rule is not None:
            pairs[(rule.country_a, rule.country_b)] = rule
    way = econ_caravan.route(from_country, to_country, pairs, params)
    if way is None:
        return DispatchResult("skipped")
    if (way.duty_pct != plan.duty_pct or way.travel_runs != plan.travel_runs or from_country != plan.from_country_id
            or to_country != plan.to_country_id):
        plan = replace(plan, duty_pct=way.duty_pct, travel_runs=way.travel_runs, from_country_id=from_country,
                       to_country_id=to_country)

    purse_ref = core.AccountRef.purse(plan.to_region_id)
    treasury_ref = core.AccountRef.region(plan.to_region_id)
    escrow_ref = core.AccountRef.caravan_escrow()
    balances = _lock_balances(db, [purse_ref, treasury_ref, escrow_ref])
    final = econ_caravan.clamp_dispatch(plan, _f(goods.stock), _f(goods.norm_stock), balances[purse_ref],
                                        balances[treasury_ref], min_value=int(params.caravan_min_value))
    if final is None:
        return DispatchResult("skipped")

    row = models.EconCaravan(
        dispatch_run_id=int(run_id), from_region_id=final.from_region_id, to_region_id=final.to_region_id,
        from_country_id=final.from_country_id, to_country_id=final.to_country_id, group_code=final.group_code,
        units=_dec3(final.units), unit_price=Decimal(str(final.unit_price)), value=final.value, duty=final.duty,
        duty_pct=Decimal(str(round(final.duty_pct, 2))), paid_purse=final.paid_purse,
        paid_treasury=final.paid_treasury, travel_runs=final.travel_runs, runs_left=final.travel_runs,
        last_run_id=int(run_id), status=STATUS_IN_TRANSIT, created_at=now,
    )
    physical = False
    if planner is not None:
        road, _reason = planner.route(final.from_region_id, final.to_region_id)
        u = econ_caravan.physical_roll(run_id, final.from_region_id, final.to_region_id, final.group_code)
        physical = econ_caravan.choose_physical(final.value, final.from_country_id, final.to_country_id,
                                                road is not None, planner.active, params, u)
        if physical:
            row.is_physical = True
            row.route = [int(x) for x in road]
            row.route_index = 0
            row.current_location_id = int(road[0])
            row.next_move_at = now + departure_delay(params, u)
            row.guard_count = econ_caravan.guard_count(final.value, params)
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        raise _AlreadyDispatched()
    goods.stock = _dec3(_dec3(goods.stock) - _dec3(final.units))
    db.flush()
    posted = econ_ledger.post_operation(
        db, op_type=core.OP_CARAVAN_DISPATCH,
        legs=[core.Leg(purse_ref, escrow_ref, final.paid_purse), core.Leg(treasury_ref, escrow_ref, final.paid_treasury)],
        source_service=SOURCE_SERVICE, region_id=final.to_region_id, apply_tax=False,
        idempotency_key=caravan_key(row.id, KEY_PAY),
        metadata={"run_id": int(run_id), "caravan_id": int(row.id), "from_region_id": final.from_region_id,
                  "to_region_id": final.to_region_id, "group_code": final.group_code, "units": str(_dec3(final.units)),
                  "unit_price": final.unit_price, "value": final.value, "duty": final.duty,
                  "duty_pct": final.duty_pct},
    )
    row.dispatch_op_id = posted.operation_id
    return DispatchResult("sent", int(row.id), final.value, physical)


class _AlreadyDispatched(Exception):
    """UNIQUE dispatch key hit: this caravan was sent by an earlier attempt of the same run."""


def dispatch_tx(session_factory: SessionFactory, plan: econ_caravan.CaravanPlan, *, run_id: int, params,
                now: datetime, planner: Optional[RoutePlanner] = None) -> DispatchResult:
    """:func:`dispatch` in its own transaction. Exceptions other than "already" propagate (the pass counts them)."""
    session = session_factory()
    try:
        result = dispatch(session, plan, run_id=run_id, params=params, now=now, planner=planner)
        if result.status == "sent":
            session.commit()
            if result.is_physical and planner is not None:
                planner.active += 1
        else:
            session.rollback()
        return result
    except (_AlreadyDispatched, core.DuplicateOperation):
        session.rollback()
        return DispatchResult("already")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# =====================================================================================================================
# Arrivals (3.8)
# =====================================================================================================================

@dataclass(frozen=True)
class FinishResult:
    status: str        # advanced | delivered | cancelled | postponed | already
    value: int = 0
    notices: list = field(default_factory=list)     # FEAT-212: escort notices, published after the commit


def in_transit_rows(db: Session) -> List[Tuple[int, int, int]]:
    """[(id, runs_left, last_run_id)] of ABSTRACT caravans on the road, ascending id (plain read). FEAT-211: physical
    caravans arrive by road (``caravan_pass`` → :func:`deliver_physical`), never by the tick."""
    return [(int(r[0]), _i(r[1]), _i(r[2])) for r in db.execute(text(
        "SELECT id, runs_left, last_run_id FROM econ_caravans WHERE status = :s AND is_physical = 0 ORDER BY id"),
        {"s": STATUS_IN_TRANSIT}).fetchall()]


def _lock_caravan(db: Session, caravan_id: int) -> Optional["models.EconCaravan"]:
    q = db.query(models.EconCaravan).filter(models.EconCaravan.id == int(caravan_id))
    return (q.with_for_update() if _for_update(db) else q).populate_existing().first()


def advance(db: Session, caravan_id: int, *, run_id: int) -> FinishResult:
    """Only decrement the travel counter (no commit)."""
    row = _lock_caravan(db, caravan_id)
    if row is None or row.status != STATUS_IN_TRANSIT or _i(row.last_run_id) == int(run_id) or row.is_physical:
        return FinishResult("already")
    row.runs_left = max(0, _i(row.runs_left) - 1)
    row.last_run_id = int(run_id)
    return FinishResult("advanced")


def _country_or_world(db: Session, country_id: Optional[int]) -> core.AccountRef:
    return core.AccountRef.country(int(country_id)) if _country_exists(db, country_id) else core.AccountRef.world()


def finish(db: Session, caravan_id: int, *, run_id: int, now: datetime) -> FinishResult:
    """Deliver or cancel a caravan whose travel ends in this run (no commit)."""
    probe = db.execute(text("SELECT from_region_id, to_region_id, group_code FROM econ_caravans WHERE id = :id"),
                       {"id": int(caravan_id)}).first()
    if probe is None:
        return FinishResult("already")
    from_id, to_id, code = int(probe[0]), int(probe[1]), probe[2]
    regions = _lock_regions(db, [from_id, to_id])
    goods = _lock_goods(db, [(rid, code) for rid in (from_id, to_id) if rid in regions])
    row = _lock_caravan(db, caravan_id)
    if row is None or row.status != STATUS_IN_TRANSIT or row.is_physical:
        return FinishResult("already")
    run_id = int(run_id)
    if _i(row.last_run_id) == run_id and _i(row.runs_left) > 0:
        return FinishResult("already")          # already advanced in this run
    left = _i(row.runs_left) - (1 if _i(row.last_run_id) != run_id else 0)
    if left > 0:
        row.runs_left = left
        row.last_run_id = run_id
        return FinishResult("advanced")

    for region in regions.values():
        if region.last_run_id is not None and int(region.last_run_id) == run_id:
            row.runs_left = 0               # a resumed run: this region already ticked — finish next run
            row.last_run_id = run_id
            return FinishResult("postponed")

    units = _dec3(row.units)
    escrow_ref = core.AccountRef.caravan_escrow()
    dest_exists = _region_exists(db, to_id)
    dest_goods = goods.get((to_id, code))
    if dest_exists and _participates(regions.get(to_id)) and dest_goods is not None:
        dest_goods.stock = _dec3(_dec3(dest_goods.stock) + units)
        seller_ref = (core.AccountRef.purse(from_id) if _region_exists(db, from_id)
                      else _country_or_world(db, row.from_country_id))
        duty_ref = _country_or_world(db, row.to_country_id)
        legs = [core.Leg(escrow_ref, seller_ref, _i(row.value)), core.Leg(escrow_ref, duty_ref, _i(row.duty))]
        op_type, key, status = core.OP_CARAVAN_DELIVERY, KEY_DONE, STATUS_DELIVERED
        row.cancel_reason = None
    else:
        origin_goods = goods.get((from_id, code))
        if origin_goods is not None and _region_exists(db, from_id):
            origin_goods.stock = _dec3(_dec3(origin_goods.stock) + units)
            row.goods_returned = True
        else:
            row.goods_returned = False
            logger.warning("caravan %s cancelled: both regions %s and %s are gone, %s units of %s written off",
                           row.id, from_id, to_id, units, code)
        if dest_exists:
            purse_ref, treasury_ref = core.AccountRef.purse(to_id), core.AccountRef.region(to_id)
        else:
            purse_ref = treasury_ref = _country_or_world(db, row.to_country_id)
        legs = [core.Leg(escrow_ref, purse_ref, _i(row.paid_purse)),
                core.Leg(escrow_ref, treasury_ref, _i(row.paid_treasury))]
        op_type, key, status = core.OP_CARAVAN_CANCEL, KEY_BACK, STATUS_CANCELLED
        row.cancel_reason = REASON_DESTINATION_LEFT if dest_exists else REASON_DESTINATION_DELETED

    db.flush()
    posted = econ_ledger.post_operation(
        db, op_type=op_type, legs=legs, source_service=SOURCE_SERVICE, region_id=to_id, apply_tax=False,
        idempotency_key=caravan_key(row.id, key),
        metadata={"run_id": run_id, "caravan_id": int(row.id), "from_region_id": from_id, "to_region_id": to_id,
                  "group_code": code, "units": str(units), "value": _i(row.value), "duty": _i(row.duty),
                  "cancel_reason": row.cancel_reason},
    )
    row.status = status
    row.runs_left = 0
    row.last_run_id = run_id
    row.finished_at = now
    row.finished_run_id = run_id
    row.finish_op_id = posted.operation_id
    return FinishResult(status, _i(row.value))


def advance_and_finish(session_factory: SessionFactory, run_id: int, now: datetime,
                       on_error: Optional[Callable[[int, Exception], None]] = None) -> Dict[str, int]:
    """Arrival phase: every caravan on the road advances or finishes, each in its own transaction (best effort)."""
    counts = {"advanced": 0, "delivered": 0, "cancelled": 0, "postponed": 0, "failed": 0, "delivered_value": 0}
    session = session_factory()
    try:
        rows = in_transit_rows(session)
    finally:
        session.rollback()
        session.close()
    for caravan_id, runs_left, last_run_id in rows:
        if last_run_id == int(run_id) and runs_left > 0:
            continue                        # dispatched or advanced by this very run
        session = session_factory()
        try:
            if runs_left > 1:
                result = advance(session, caravan_id, run_id=run_id)
            else:
                result = finish(session, caravan_id, run_id=run_id, now=now)
            session.commit()
        except core.DuplicateOperation:
            session.rollback()
            continue
        except Exception as exc:
            session.rollback()
            counts["failed"] += 1
            logger.error("economy tick run %s: caravan %s failed to advance / arrive (%s), retried next run",
                         run_id, caravan_id, type(exc).__name__, exc_info=True)
            if on_error is not None:
                on_error(caravan_id, exc)
            continue
        finally:
            session.close()
        if result.status in counts:
            counts[result.status] += 1
        if result.status == STATUS_DELIVERED:
            counts["delivered_value"] += result.value
    return counts


# =====================================================================================================================
# FEAT-211 physical delivery (3.3 step 5) — on arrival, outside the tick, no run-id logic
# =====================================================================================================================

def deliver_physical(db: Session, caravan_id: int, now: datetime) -> FinishResult:
    """Deliver (or cancel) an arrived physical caravan (no commit). Lock order = :func:`finish`: ``econ_regions ×≤2
    asc → econ_region_goods ×≤2 asc → econ_caravans(row) → [FEAT-212 econ_caravan_escorts → characters] →
    econ_accounts``. Only ``units − stolen_units`` arrive (or go back); the money is the rest of the escrow
    ``paid − raid_paid`` (``econ_caravan.remaining_payout`` / ``refund_split``). FEAT-212: active escorts are paid
    out of the seller part inside the same op (delivered) or get nothing (cancelled); notices ride on the result."""
    import caravan_escort_crud as escorts               # late: it imports this module
    probe = db.execute(text("SELECT from_region_id, to_region_id, group_code FROM econ_caravans WHERE id = :id"),
                       {"id": int(caravan_id)}).first()
    if probe is None:
        return FinishResult("already")
    from_id, to_id, code = int(probe[0]), int(probe[1]), probe[2]
    regions = _lock_regions(db, [from_id, to_id])
    goods = _lock_goods(db, [(rid, code) for rid in (from_id, to_id) if rid in regions])
    row = _lock_caravan(db, caravan_id)
    if row is None or row.status != STATUS_IN_TRANSIT or not row.is_physical or row.arrived_at is None:
        return FinishResult("already")

    units = max(Decimal(0), _dec3(row.units) - _dec3(row.stolen_units))
    paid_purse, paid_treasury, raid_paid = _i(row.paid_purse), _i(row.paid_treasury), _i(row.raid_paid)
    escrow_ref = core.AccountRef.caravan_escrow()
    dest_exists = _region_exists(db, to_id)
    dest_goods = goods.get((to_id, code))
    if dest_exists and _participates(regions.get(to_id)) and dest_goods is not None:
        dest_goods.stock = _dec3(_dec3(dest_goods.stock) + units)
        seller_part, duty_part = econ_caravan.remaining_payout(_i(row.value), _i(row.duty),
                                                               paid_purse + paid_treasury, raid_paid)
        seller_ref = (core.AccountRef.purse(from_id) if _region_exists(db, from_id)
                      else _country_or_world(db, row.from_country_id))
        duty_ref = _country_or_world(db, row.to_country_id)
        plan = escorts.pay_plan(db, row, seller_part)
        seller_part -= plan.total
        legs = [core.Leg(escrow_ref, seller_ref, seller_part), core.Leg(escrow_ref, duty_ref, duty_part)]
        legs += plan.legs(escrow_ref)
        op_type, key, status, paid_out = core.OP_CARAVAN_DELIVERY, KEY_DONE, STATUS_DELIVERED, seller_part
        row.cancel_reason = None
    else:
        plan = None
        notices = escorts.cancel_escorts(db, row, now)      # escort rows + characters locked before the accounts
        origin_goods = goods.get((from_id, code))
        if origin_goods is not None and _region_exists(db, from_id):
            origin_goods.stock = _dec3(_dec3(origin_goods.stock) + units)
            row.goods_returned = True
        else:
            row.goods_returned = False
            logger.warning("physical caravan %s cancelled: both regions %s and %s are gone, %s units of %s written "
                           "off", row.id, from_id, to_id, units, code)
        if dest_exists:
            purse_ref, treasury_ref = core.AccountRef.purse(to_id), core.AccountRef.region(to_id)
        else:
            purse_ref = treasury_ref = _country_or_world(db, row.to_country_id)
        purse_back, treasury_back = econ_caravan.refund_split(paid_purse, paid_treasury, raid_paid)
        legs = [core.Leg(escrow_ref, purse_ref, purse_back), core.Leg(escrow_ref, treasury_ref, treasury_back)]
        op_type, key, status, paid_out = core.OP_CARAVAN_CANCEL, KEY_BACK, STATUS_CANCELLED, 0
        row.cancel_reason = REASON_DESTINATION_LEFT if dest_exists else REASON_DESTINATION_DELETED

    db.flush()
    posted = econ_ledger.post_operation(
        db, op_type=op_type, legs=legs, source_service=SOURCE_SERVICE, region_id=to_id, apply_tax=False,
        idempotency_key=caravan_key(row.id, key),
        metadata={"caravan_id": int(row.id), "from_region_id": from_id, "to_region_id": to_id, "group_code": code,
                  "units": str(units), "value": _i(row.value), "duty": _i(row.duty),
                  "cancel_reason": row.cancel_reason, "physical": True, "stolen_units": str(_dec3(row.stolen_units)),
                  "raid_paid": raid_paid, "escorts": plan.metadata() if plan is not None else []},
    )
    row.status = status
    row.runs_left = 0
    row.next_move_at = None
    row.finished_at = now
    row.finished_run_id = None
    row.finish_op_id = posted.operation_id
    if plan is not None:
        notices = escorts.finish_paid(db, row, plan, posted.operation_id, now)
    return FinishResult(status, paid_out, notices)


def deliver_physical_tx(session_factory: SessionFactory, caravan_id: int, now: datetime) -> FinishResult:
    """:func:`deliver_physical` in its own transaction; a duplicate op = already. Other errors propagate."""
    session = session_factory()
    try:
        result = deliver_physical(session, caravan_id, now)
        if result.status in (STATUS_DELIVERED, STATUS_CANCELLED):
            session.commit()
        else:
            session.rollback()
        return result
    except core.DuplicateOperation:
        session.rollback()
        return FinishResult("already")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# =====================================================================================================================
# FEAT-211 holds (3.4) — plain reads (raw SQL on locations-service tables)
# =====================================================================================================================

def active_raid_status(db: Session, caravan_id: int) -> Optional[str]:
    """Status of the caravan's raid row (None = never raided)."""
    value = db.execute(text("SELECT status FROM econ_caravan_raids WHERE caravan_id = :c"),
                       {"c": int(caravan_id)}).scalar()
    return value


def gate_tables_available(db: Session) -> bool:
    names = set(sa_inspect(db.get_bind()).get_table_names())
    return "action_gates" in names and "post_gate_requests" in names


def post_hold(db: Session, caravan_id: int, location_id: Optional[int]) -> bool:
    """An open ``caravan`` gate naming this caravan at its location, or a pending post-gate request at the location
    whose gates name it (3.4)."""
    if not location_id:
        return False
    if db.execute(text(
            "SELECT 1 FROM action_gates WHERE action_type = :a AND target_ref = :c AND location_id = :l "
            "AND status = 'open' LIMIT 1"),
            {"a": GATE_ACTION_CARAVAN, "c": int(caravan_id), "l": int(location_id)}).first() is not None:
        return True
    for (gates,) in db.execute(text(
            "SELECT gates FROM post_gate_requests WHERE status = 'pending' AND location_id = :l"),
            {"l": int(location_id)}).fetchall():
        for gate in _json_list(gates):
            if not isinstance(gate, dict) or gate.get("action_type") != GATE_ACTION_CARAVAN:
                continue
            try:
                targets = {int(t) for t in (gate.get("targets") or [])}
            except (TypeError, ValueError):
                continue
            if int(caravan_id) in targets:
                return True
    return False


def post_window_open(row, now: datetime, params) -> bool:
    """The one post-hold window per caravan: not started yet, or started less than ``caravan_post_hold_max_min``
    ago."""
    if row.hold_started_at is None:
        return int(params.caravan_post_hold_max_min) > 0
    return now < row.hold_started_at + timedelta(minutes=int(params.caravan_post_hold_max_min))


def held_by(db: Session, row, now: datetime, params, gates_available: bool = True) -> Optional[str]:
    """``"raid"`` (raid starting / fighting), ``"post"`` (3.4 post hold inside the window, never after a raid) or
    None."""
    raid = active_raid_status(db, int(row.id))
    if raid in RAID_ACTIVE_STATUSES:
        return "raid"
    if raid is None and gates_available and post_window_open(row, now, params) \
            and post_hold(db, int(row.id), row.current_location_id):
        return "post"
    return None


# =====================================================================================================================
# Admin reads / writes (3.11)
# =====================================================================================================================

def _countries(db: Session) -> List[Tuple[int, Optional[str]]]:
    return [(int(r[0]), r[1]) for r in db.execute(text("SELECT id, name FROM Countries ORDER BY name, id")).fetchall()]


def _pair_out(a: int, b: int, names: Mapping[int, Optional[str]], row) -> dict:
    return {
        "country_a": a, "country_b": b, "name_a": names.get(a), "name_b": names.get(b),
        "is_enabled": bool(row[0]) if row is not None else False,
        "duty_pct": round(_f(row[1]), 2) if row is not None else DEFAULT_DUTY_PCT,
        "updated_at": row[2] if row is not None else None,
    }


def overview(db: Session) -> dict:
    import econ_tick
    params = econ_tick.load_params(db).to_dict()
    countries = _countries(db)
    names = dict(countries)
    participating: Dict[int, int] = {}
    for _rid, _pop, country in econ_tick.participating_regions(db):
        if country is not None:
            participating[country] = participating.get(country, 0) + 1
    stored = {(int(r[0]), int(r[1])): (r[2], r[3], r[4]) for r in db.execute(text(
        "SELECT country_a, country_b, is_enabled, duty_pct, updated_at FROM econ_trade_pairs")).fetchall()}
    pairs = []
    for i, (cid_i, _name_i) in enumerate(countries):
        for cid_j, _name_j in countries[i + 1:]:
            a, b = econ_caravan.pair_key(cid_i, cid_j)
            pairs.append(_pair_out(a, b, names, stored.get((a, b))))

    transit = db.execute(text(
        "SELECT COUNT(*), COALESCE(SUM(value), 0), COALESCE(SUM(duty), 0) FROM econ_caravans WHERE status = :s"),
        {"s": STATUS_IN_TRANSIT}).first()
    last = db.execute(text(
        "SELECT id FROM econ_tick_runs WHERE status <> 'running' AND finished_at IS NOT NULL "
        "ORDER BY id DESC LIMIT 1")).scalar()
    last_run = None
    if last is not None:
        run = {"run": int(last)}
        last_run = {
            "run_id": int(last),
            "dispatched": _i(db.execute(text("SELECT COUNT(*) FROM econ_caravans WHERE dispatch_run_id = :run"),
                                        run).scalar()),
            "delivered": _i(db.execute(text("SELECT COUNT(*) FROM econ_caravans WHERE finished_run_id = :run "
                                            "AND status = 'delivered'"), run).scalar()),
            "cancelled": _i(db.execute(text("SELECT COUNT(*) FROM econ_caravans WHERE finished_run_id = :run "
                                            "AND status = 'cancelled'"), run).scalar()),
        }
    balance, expected = escrow_balance(db), escrow_expected(db)
    return {
        "params": {key: params[key] for key in CARAVAN_PARAM_KEYS},
        "escrow": {"balance": balance, "expected": expected, "ok": balance == expected},
        "in_transit": {"count": _i(transit[0]), "value": _i(transit[1]), "duty": _i(transit[2])},
        "last_run": last_run,
        "countries": [{"country_id": cid, "name": name, "participating_regions": participating.get(cid, 0)}
                      for cid, name in countries],
        "pairs": pairs,
    }


def upsert_pair(db: Session, *, country_a: int, country_b: int, is_enabled: bool, duty_pct: float,
                user_id: Optional[int], now: Optional[datetime] = None) -> dict:
    if int(country_a) == int(country_b):
        raise EconomyApiError(400, MSG_SAME_COUNTRY)
    a, b = econ_caravan.pair_key(country_a, country_b)
    names = {int(r[0]): r[1] for r in db.execute(text("SELECT id, name FROM Countries WHERE id IN (:a, :b)"),
                                                 {"a": a, "b": b}).fetchall()}
    if a not in names or b not in names:
        raise EconomyApiError(404, MSG_COUNTRY_NOT_FOUND)
    duty = Decimal(str(duty_pct)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    row = db.get(models.EconTradePair, (a, b))
    if row is None:
        row = models.EconTradePair(country_a=a, country_b=b)
        db.add(row)
    row.is_enabled = bool(is_enabled)
    row.duty_pct = duty
    row.updated_at = now or datetime.utcnow().replace(microsecond=0)
    row.updated_by = user_id
    db.flush()
    return _pair_out(a, b, names, (row.is_enabled, row.duty_pct, row.updated_at))


SQL_CARAVAN_LIST = """
SELECT c.id, c.status, c.group_code, g.name, c.from_region_id, rf.name, c.from_country_id, cf.name,
       c.to_region_id, rt.name, c.to_country_id, ct.name, c.units, c.unit_price, c.value, c.duty, c.duty_pct,
       c.paid_purse, c.paid_treasury, c.travel_runs, c.runs_left, c.dispatch_run_id, c.finished_run_id,
       c.cancel_reason, c.goods_returned, c.created_at, c.finished_at,
       c.is_physical, c.current_location_id, lc.name, c.route_index, c.route, c.next_move_at, c.arrived_at,
       c.hold_started_at, c.guard_count, c.stolen_units, c.raid_paid, cr.status,
       (SELECT COUNT(*) FROM econ_caravan_escorts ce WHERE ce.caravan_id = c.id AND ce.status = 'active')
FROM econ_caravans c
LEFT JOIN econ_goods_groups g ON g.code = c.group_code
LEFT JOIN Regions rf ON rf.id = c.from_region_id
LEFT JOIN Regions rt ON rt.id = c.to_region_id
LEFT JOIN Countries cf ON cf.id = c.from_country_id
LEFT JOIN Countries ct ON ct.id = c.to_country_id
LEFT JOIN Locations lc ON lc.id = c.current_location_id
LEFT JOIN econ_caravan_raids cr ON cr.caravan_id = c.id
"""


def _caravan_out(r) -> dict:
    return {
        "id": int(r[0]), "status": r[1], "group_code": r[2], "group_name": r[3],
        "from_region_id": int(r[4]), "from_region_name": r[5], "from_country_id": int(r[6]),
        "from_country_name": r[7], "to_region_id": int(r[8]), "to_region_name": r[9],
        "to_country_id": int(r[10]), "to_country_name": r[11], "units": round(_f(r[12]), 3),
        "unit_price": round(_f(r[13]), 4), "value": _i(r[14]), "duty": _i(r[15]), "duty_pct": round(_f(r[16]), 2),
        "paid_purse": _i(r[17]), "paid_treasury": _i(r[18]), "travel_runs": _i(r[19]), "runs_left": _i(r[20]),
        "dispatch_run_id": int(r[21]), "finished_run_id": int(r[22]) if r[22] is not None else None,
        "cancel_reason": r[23], "goods_returned": bool(r[24]) if r[24] is not None else None,
        "created_at": r[25], "finished_at": r[26],
        # FEAT-211 (A4)
        "is_physical": bool(r[27]), "current_location_id": int(r[28]) if r[28] is not None else None,
        "current_location_name": r[29], "route_index": _i(r[30]), "route_len": len(_json_list(r[31])),
        "next_move_at": r[32], "arrived_at": r[33], "hold_started_at": r[34], "guard_count": _i(r[35]),
        "stolen_units": round(_f(r[36]), 3), "raid_paid": _i(r[37]), "raid_status": r[38],
        # FEAT-212 (A4): active player escorts
        "escort_count": _i(r[39]),
    }


def list_caravans(db: Session, *, status: str = "all", region_id: Optional[int] = None,
                  group_code: Optional[str] = None, limit: int = 50, offset: int = 0, kind: str = KIND_ALL) -> dict:
    where, params = [], {}
    if status and status != "all":
        where.append("c.status = :status")
        params["status"] = status
    if kind == KIND_PHYSICAL:
        where.append("c.is_physical = 1")
    elif kind == KIND_ABSTRACT:
        where.append("c.is_physical = 0")
    if region_id is not None:
        where.append("(c.from_region_id = :rid OR c.to_region_id = :rid)")
        params["rid"] = int(region_id)
    if group_code:
        if db.get(models.EconGoodsGroup, group_code) is None:
            raise EconomyApiError(400, MSG_UNKNOWN_GROUP)
        where.append("c.group_code = :code")
        params["code"] = group_code
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    total = _i(db.execute(text(f"SELECT COUNT(*) FROM econ_caravans c{clause}"), params).scalar())
    rows = db.execute(text(SQL_CARAVAN_LIST + clause + " ORDER BY c.id DESC LIMIT :limit OFFSET :offset"),
                      {**params, "limit": int(limit), "offset": int(offset)}).fetchall()
    return {"total": total, "items": [_caravan_out(r) for r in rows]}


# =====================================================================================================================
# Player card (3.12) — words only
# =====================================================================================================================

def empty_card() -> dict:
    return {"incoming": [], "outgoing": []}


def card_caravans(db: Session, region_id: int, now: Optional[datetime] = None) -> dict:
    """Caravans to / from the region: on the road, or delivered within CARD_RECENT_HOURS. No numbers."""
    if not caravans_available(db):
        return empty_card()
    now = now or datetime.utcnow().replace(microsecond=0)
    since = now - timedelta(hours=CARD_RECENT_HOURS)
    own_country = _region_country(db, region_id)
    order = {row.code: i for i, row in enumerate(
        db.query(models.EconGoodsGroup).order_by(models.EconGoodsGroup.sort_order, models.EconGoodsGroup.code).all())}
    rows = db.execute(text(
        "SELECT c.id, c.status, c.group_code, g.name, c.from_region_id, c.to_region_id, "
        "r.id, r.name, r.country_id, co.name "
        "FROM econ_caravans c "
        "LEFT JOIN econ_goods_groups g ON g.code = c.group_code "
        "LEFT JOIN Regions r ON r.id = CASE WHEN c.to_region_id = :rid THEN c.from_region_id ELSE c.to_region_id END "
        "LEFT JOIN Countries co ON co.id = r.country_id "
        "WHERE (c.to_region_id = :rid OR c.from_region_id = :rid) AND c.is_physical = 0 "
        "AND (c.status = :transit OR (c.status = :delivered AND c.finished_at >= :since)) "
        "ORDER BY c.id DESC"),
        {"rid": int(region_id), "transit": STATUS_IN_TRANSIT, "delivered": STATUS_DELIVERED,
         "since": since}).fetchall()
    lines: Dict[str, Dict[Tuple[str, int], dict]] = {"incoming": {}, "outgoing": {}}
    for _id, status, code, group_name, from_id, to_id, other_id, other_name, other_country, country_name in rows:
        if other_id is None or int(from_id) == int(to_id):
            continue                        # the other region was deleted -> dropped
        side = "incoming" if int(to_id) == int(region_id) else "outgoing"
        foreign = other_country is not None and own_country is not None and int(other_country) != own_country
        in_transit = status == STATUS_IN_TRANSIT
        key = (code, int(other_id))
        current = lines[side].get(key)
        if current is not None and (current["in_transit"] or not in_transit):
            continue
        lines[side][key] = {
            "group_code": code, "group_name": group_name or code, "region_id": int(other_id),
            "region_name": other_name, "country_name": country_name if foreign else None,
            "foreign": bool(foreign), "in_transit": in_transit,
        }
    out = {}
    for side, entries in lines.items():
        items = sorted(entries.values(), key=lambda e: (0 if e["in_transit"] else 1,
                                                        order.get(e["group_code"], len(order)), e["region_id"]))
        out[side] = items[:CARD_MAX_LINES]
    return out


# =====================================================================================================================
# FEAT-211 admin (A5–A9): caravan detail, roads / gates, guard pool
# =====================================================================================================================

def _location_names(db: Session, ids: Sequence[int]) -> Dict[int, Optional[str]]:
    ids = sorted({int(i) for i in ids if i})
    if not ids:
        return {}
    placeholders, params = core.in_params("l", ids)
    return {int(r[0]): r[1] for r in db.execute(
        text(f"SELECT id, name FROM Locations WHERE id IN ({placeholders})"), params).fetchall()}


def _region_names(db: Session, ids: Sequence[int]) -> Dict[int, Optional[str]]:
    ids = sorted({int(i) for i in ids if i})
    if not ids:
        return {}
    placeholders, params = core.in_params("r", ids)
    return {int(r[0]): r[1] for r in db.execute(
        text(f"SELECT id, name FROM Regions WHERE id IN ({placeholders})"), params).fetchall()}


def _character_names(db: Session, ids: Sequence[int]) -> Dict[int, Optional[str]]:
    ids = sorted({int(i) for i in ids if i})
    if not ids:
        return {}
    placeholders, params = core.in_params("c", ids)
    return {int(r[0]): r[1] for r in db.execute(
        text(f"SELECT id, name FROM characters WHERE id IN ({placeholders})"), params).fetchall()}


def _raid_out(db: Session, raid: "models.EconCaravanRaid") -> dict:
    shares = {int(s.character_id): s for s in db.query(models.EconCaravanRaidShare)
              .filter(models.EconCaravanRaidShare.raid_id == int(raid.id)).all()}
    attacker_ids = [int(a) for a in _json_list(raid.attacker_ids)] or sorted(shares)
    names = _character_names(db, attacker_ids + [int(raid.leader_character_id)])
    template_name = None
    if raid.guard_template_id is not None:
        template_name = db.execute(text("SELECT name FROM mob_templates WHERE id = :t"),
                                   {"t": int(raid.guard_template_id)}).scalar()
    return {
        "id": int(raid.id), "status": raid.status, "leader_id": int(raid.leader_character_id),
        "leader_name": names.get(int(raid.leader_character_id)), "is_group": bool(raid.is_group),
        "battle_id": int(raid.battle_id) if raid.battle_id is not None else None,
        "attackers": [{"id": cid, "name": names.get(cid),
                       "marks": _i(shares[cid].marks) if cid in shares else 0,
                       "bales": _i(shares[cid].bales) if cid in shares else 0} for cid in attacker_ids],
        "marks": _i(raid.marks), "stolen_units": round(_f(raid.stolen_units), 3),
        "stolen_value": _i(raid.stolen_value), "bales": _i(raid.bales),
        "guard_template_id": int(raid.guard_template_id) if raid.guard_template_id is not None else None,
        "guard_template_name": template_name,
        "guard_mult": round(_f(raid.guard_mult), 3) if raid.guard_mult is not None else None,
        "created_at": raid.created_at, "finished_at": raid.finished_at,
        # FEAT-212 (A5): player escorts placed on the guard team
        "escort_ids": [int(x) for x in _json_list(raid.escort_ids) if isinstance(x, int) or str(x).isdigit()],
    }


def _escorts_out(db: Session, caravan_id: int) -> List[dict]:
    """FEAT-212 A5: every escort row of the caravan (admin only), in hire order."""
    rows = db.execute(text(
        "SELECT e.character_id, ch.name, e.status, e.joined_at, e.ended_at, e.fee, e.bonus, e.in_raid "
        "FROM econ_caravan_escorts e LEFT JOIN characters ch ON ch.id = e.character_id "
        "WHERE e.caravan_id = :c ORDER BY e.id"), {"c": int(caravan_id)}).fetchall()
    return [{"character_id": int(r[0]), "name": r[1], "status": r[2], "joined_at": r[3], "ended_at": r[4],
             "fee": _i(r[5]), "bonus": _i(r[6]), "in_raid": bool(r[7])} for r in rows]


def caravan_detail(db: Session, caravan_id: int, now: Optional[datetime] = None) -> dict:
    """A5: the A4 list item + the route with names / regions, the current hold reason and the raid card."""
    import econ_tick
    row = db.execute(text(SQL_CARAVAN_LIST + " WHERE c.id = :id"), {"id": int(caravan_id)}).first()
    if row is None:
        raise EconomyApiError(404, MSG_CARAVAN_NOT_FOUND)
    out = _caravan_out(row)
    caravan = db.get(models.EconCaravan, int(caravan_id))
    route_ids = [int(x) for x in _json_list(caravan.route)]
    names = _location_names(db, route_ids)
    regions = {loc: econ_ledger.resolve_location(db, loc)[0] for loc in set(route_ids)}
    region_names = _region_names(db, [r for r in regions.values() if r])
    out["route"] = [{"index": i, "location_id": loc, "name": names.get(loc), "region_id": regions.get(loc),
                     "region_name": region_names.get(regions.get(loc)) if regions.get(loc) else None}
                    for i, loc in enumerate(route_ids)]
    out["held_by"] = None
    if caravan.is_physical and caravan.status == STATUS_IN_TRANSIT and caravan.arrived_at is None:
        now = now or datetime.utcnow().replace(microsecond=0)
        out["held_by"] = held_by(db, caravan, now, econ_tick.load_params(db), gate_tables_available(db))
    raid = db.query(models.EconCaravanRaid).filter(models.EconCaravanRaid.caravan_id == int(caravan_id)).first()
    out["raid"] = _raid_out(db, raid) if raid is not None else None
    out["escorts"] = _escorts_out(db, caravan_id)
    return out


_NO_GATE = {"override": None, "station": None, "gate": None, "source": caravan_route.GATE_NONE}


def _gate_region_item(region_id: int, info: dict, region_row, loc_names: Mapping[int, Optional[str]]) -> dict:
    return {
        "region_id": int(region_id), "name": region_row[1] if region_row else None,
        "country_name": region_row[2] if region_row else None,
        "station_location_id": info["station"], "station_location_name": loc_names.get(info["station"]),
        "gate_override_id": info["override"], "gate_override_name": loc_names.get(info["override"]),
        "gate_location_id": info["gate"], "gate_location_name": loc_names.get(info["gate"]),
        "gate_source": info["source"],
    }


def _region_rows(db: Session, ids: Sequence[int]) -> Dict[int, tuple]:
    ids = sorted({int(i) for i in ids})
    if not ids:
        return {}
    placeholders, params = core.in_params("r", ids)
    return {int(r[0]): (int(r[0]), r[1], r[2]) for r in db.execute(text(
        "SELECT r.id, r.name, co.name FROM Regions r LEFT JOIN Countries co ON co.id = r.country_id "
        f"WHERE r.id IN ({placeholders})"), params).fetchall()}


def roads(db: Session) -> dict:
    """A6: trade gates of the participating regions + the pairs that have no road (same-country pairs and enabled
    foreign pairs, unordered; the graph is undirected, so one direction is enough)."""
    import econ_tick
    params = econ_tick.load_params(db)
    participating = [(rid, country) for rid, _pop, country in econ_tick.participating_regions(db)]
    ids = [rid for rid, _c in participating]
    gates = region_gates(db, ids)
    region_rows = _region_rows(db, ids)
    loc_ids = []
    for info in gates.values():
        loc_ids += [info["override"], info["station"], info["gate"]]
    loc_names = _location_names(db, [x for x in loc_ids if x])
    regions_out = [_gate_region_item(rid, gates.get(rid, _NO_GATE), region_rows.get(rid), loc_names) for rid in ids]
    pairs = enabled_pairs(db)
    planner = RoutePlanner(load_road_graph(db), gates, 0, int(params.caravan_route_max_steps))
    no_road = []
    for i, (a, country_a) in enumerate(participating):
        for b, country_b in participating[i + 1:]:
            if country_a is None or country_b is None:
                continue
            if country_a != country_b and econ_caravan.pair_key(country_a, country_b) not in pairs:
                continue
            road, reason = planner.route(a, b)
            if road is None:
                no_road.append({"from_region_id": a, "from_name": (region_rows.get(a) or (a, None))[1],
                                "to_region_id": b, "to_name": (region_rows.get(b) or (b, None))[1],
                                "reason": reason})
    return {"regions": regions_out, "no_road": no_road}


def set_gate(db: Session, region_id: int, location_id: Optional[int]) -> dict:
    """A7: set / clear the region's trade gate override (caller commits)."""
    q = db.query(models.EconRegion).filter(models.EconRegion.region_id == int(region_id))
    region = (q.with_for_update() if _for_update(db) else q).first()
    if region is None or not _region_exists(db, region_id):
        raise EconomyApiError(404, MSG_REGION_NOT_FOUND)
    if location_id is not None:
        loc = db.execute(text("SELECT id, marker_type FROM Locations WHERE id = :l"), {"l": int(location_id)}).first()
        if loc is None or econ_ledger.resolve_location(db, int(location_id))[0] != int(region_id):
            raise EconomyApiError(400, MSG_GATE_WRONG_REGION)
        if loc[1] == MARKER_DUNGEON:
            raise EconomyApiError(400, MSG_GATE_DUNGEON)
    region.trade_gate_location_id = int(location_id) if location_id is not None else None
    db.flush()
    info = region_gates(db, [int(region_id)]).get(int(region_id), _NO_GATE)
    loc_names = _location_names(db, [x for x in (info["override"], info["station"], info["gate"]) if x])
    return _gate_region_item(int(region_id), info, _region_rows(db, [int(region_id)]).get(int(region_id)),
                             loc_names)


def guard_pool(db: Session) -> dict:
    """A8: the guard mob templates (level ascending)."""
    rows = db.execute(text(
        "SELECT t.id, t.name, t.level FROM econ_caravan_guard_templates g JOIN mob_templates t "
        "ON t.id = g.mob_template_id ORDER BY t.level, t.id")).fetchall()
    return {"templates": [{"mob_template_id": int(r[0]), "name": r[1], "level": _i(r[2])} for r in rows]}


def set_guard_pool(db: Session, template_ids: Sequence[int], now: Optional[datetime] = None) -> dict:
    """A9: replace the pool (caller commits). Unknown template -> 400."""
    ids: List[int] = []
    for tid in template_ids:
        if int(tid) not in ids:
            ids.append(int(tid))
    for tid in ids:
        if db.get(models.MobTemplate, tid) is None:
            raise EconomyApiError(400, MSG_MOB_TEMPLATE_NOT_FOUND.format(id=tid))
    now = now or datetime.utcnow().replace(microsecond=0)
    current = {int(r.mob_template_id): r for r in db.query(models.EconCaravanGuardTemplate).all()}
    for tid, row in current.items():
        if tid not in ids:
            db.delete(row)
    for tid in ids:
        if tid not in current:
            db.add(models.EconCaravanGuardTemplate(mob_template_id=tid, created_at=now))
    db.flush()
    return guard_pool(db)
