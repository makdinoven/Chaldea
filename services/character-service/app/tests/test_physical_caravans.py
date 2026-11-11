"""FEAT-211 QA (#11): physical caravans, stage 1 (movement) on SQLite.

Covers (feature file 3.2–3.4, 3.9, 3.13 A4–A9):
* pure helpers — ``caravan_route`` (BFS, blocked dungeons, too long, gates) and ``econ_caravan`` (physical roll and
  rule, guard formulas, payout / refund splits after a raid, stolen units, bales, loot split);
* dispatch of the economy tick: physical (large / foreign / chance) vs abstract (off / no road / cap / planner down);
  physical caravans are never advanced or finished by the tick;
* ``caravan_pass``: claim / throttle, frozen economy, raid-stage stub contract (task 3 module absent → 0), stepping one
  location per pass, holds (open ``caravan`` gate, pending post-gate request, the one 2 h window, an active raid);
* delivery on arrival and cancel (destination left / deleted) with and without a raid, postponed while an economy
  run is ``running``; after every step the world money sum is 0 and the escrow equals
  ``Σ (paid − raid_paid)`` of caravans in transit;
* inbound ("on the road") minus stolen units; the public region card never shows physical caravans;
* admin A4–A9: permissions (401 / 403 / read vs settings) and validation.

World = ``test_econ_tick.factory`` (countries 1 «Мидденгерд», 2 «Пустошь») + ``Locations.marker_type``,
``LocationNeighbors`` and the locations-service gate tables (``action_gates``, ``post_gate_requests``) in their real
column shapes. The raid itself (task 3) is simulated: a ``caravan_raid`` ledger leg escrow → raider plus the
``raid_paid`` / ``stolen_units`` / raid row it leaves behind.
"""

import json
import sys
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import caravan_pass
import caravan_route as route
import econ_caravan as ec
import econ_core as core
import econ_ledger
import econ_sim
import econ_tick
import economy_api
import economy_caravan_crud as crud
import models
from auth_http import UserRead, get_current_user_via_http
from main import app
from tests.econ_contract_cases import WORLD_SUM_SQL
from tests.test_econ_tick import T0, _balance, _rows, _scalar, factory  # noqa: F401
from tests.test_econ_tick_caravans import (
    _exec, _fund, _good, _groups, _pair, _params, _region, _set_params, _stock,
)
from tests.test_econ_tick_events import calendar  # noqa: F401  (autouse: no calendar HTTP)

P = econ_sim.DEFAULT_PARAMS

# ---- geography: region 1 {101 station, 102, 190 dungeon}, region 2 {201 station, 202}, region 3 {301 station}
L_GATE1, L_ROAD1, L_DUNGEON, L_GATE2, L_ROAD2, L_GATE3, L_LONE = 101, 102, 190, 201, 202, 301, 199
LOCATIONS = {
    L_GATE1: ("Застава Пашен", 1, None), L_ROAD1: ("Тракт", 1, None), L_DUNGEON: ("Логово", 1, "dungeon"),
    L_LONE: ("Глушь", 1, None),
    L_GATE2: ("Застава Оста", 2, None), L_ROAD2: ("Перевал", 2, "dangerous"), L_GATE3: ("Застава Пустоши", 3, None),
}
# the dungeon is a 2-hop shortcut 101-190-201 that roads must avoid; the real road is 101-102-202-201 (3 hops)
EDGES = ((L_GATE1, L_ROAD1), (L_ROAD1, L_ROAD2), (L_ROAD2, L_GATE2), (L_GATE1, L_DUNGEON), (L_DUNGEON, L_GATE2),
         (L_GATE2, L_GATE3))
ROAD_1_2 = [L_GATE1, L_ROAD1, L_ROAD2, L_GATE2]
RAIDER = 501

BASE = "/characters/admin/economy"
CARAVANS = f"{BASE}/caravans"
READ = ["economy:read"]
SETTINGS = ["economy:read", "economy:settings"]

LS_GATE_DDL = [
    """CREATE TABLE IF NOT EXISTS action_gates (id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER NOT NULL,
        location_id BIGINT NOT NULL, post_id INTEGER NULL, action_type VARCHAR(20) NOT NULL, target_ref INTEGER NULL,
        status VARCHAR(12) NOT NULL DEFAULT 'open', created_at TIMESTAMP NULL, consumed_at TIMESTAMP NULL)""",
    """CREATE TABLE IF NOT EXISTS post_gate_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER NULL,
        character_id INTEGER NOT NULL, location_id BIGINT NOT NULL, gates JSON NULL,
        status VARCHAR(12) NOT NULL DEFAULT 'pending', created_at TIMESTAMP NULL)""",
]


# ===================================================================================================================
# fixtures / helpers
# ===================================================================================================================

@pytest.fixture
def world(factory, monkeypatch):
    """factory + locations with markers, roads, the LS gate tables; the raid stage (task 3) is kept out."""
    cols = {r[1] for r in _rows(factory, "PRAGMA table_info(Locations)")}
    for col, ddl in (("marker_type", "VARCHAR(20) NULL"), ("recommended_level", "INTEGER NULL")):
        if col not in cols:
            _exec(factory, f"ALTER TABLE Locations ADD COLUMN {col} {ddl}")
    _exec(factory, "CREATE TABLE IF NOT EXISTS LocationNeighbors (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                   "location_id INTEGER NOT NULL, neighbor_id INTEGER NOT NULL, energy_cost INTEGER DEFAULT 0, "
                   "path_data TEXT NULL, is_auto_arrow INTEGER NOT NULL DEFAULT 0)")
    for ddl in LS_GATE_DDL:
        _exec(factory, ddl)
    for lid, (name, region, marker) in LOCATIONS.items():
        _exec(factory, "INSERT INTO Locations (id, name, region_id, marker_type) VALUES (:i, :n, :r, :m)",
              i=lid, n=name, r=region, m=marker)
    for a, b in EDGES:
        _exec(factory, "INSERT INTO LocationNeighbors (location_id, neighbor_id) VALUES (:a, :b), (:b, :a)", a=a, b=b)
    # stage 1 only: the raid-stage module (task 3) must not be imported by the pass
    monkeypatch.setitem(sys.modules, "caravan_raid_crud", None)
    yield factory


def _stations(f, **by_region):
    for rid, loc in by_region.items():
        _exec(f, "UPDATE Regions SET jail_location_id = :l WHERE id = :r", l=loc, r=int(rid[1:]))


def _physical_world(f, *, seller_country=1, buyer_country=1, treasury=0, **params):
    """Seller 1 → buyer 2 (food 200 units x 2 = 400 marks), stations 101 / 201, physical on by default."""
    _region(f, 1, country=seller_country)
    _region(f, 2, country=buyer_country)
    _good(f, 1, "food", 1000, 200)
    _good(f, 2, "food", 100, 300)
    if treasury:
        _fund(f, core.AccountRef.region(2), treasury)
    if seller_country != buyer_country:
        _pair(f, seller_country, buyer_country, duty=10)
    _stations(f, r1=L_GATE1, r2=L_GATE2)
    values = {"caravan_physical_min_value": 1}
    values.update(params)
    _set_params(f, **values)


def _dispatch(f, run_id=1):
    summary = econ_tick.RunSummary(run_id=run_id, trigger="manual", slot=None, status="running")
    econ_tick._caravan_pass(f, run_id, summary, _params(f), T0 + timedelta(hours=6 * run_id), _groups(f), {})
    _check(f)
    return summary


def _row(f, caravan_id=None):
    db = f()
    try:
        q = db.query(models.EconCaravan)
        row = db.get(models.EconCaravan, caravan_id) if caravan_id else q.order_by(models.EconCaravan.id).first()
        db.expunge(row)
        return row
    finally:
        db.close()


def _check(f):
    """World sum 0, nothing negative, escrow == Σ (paid − raid_paid) of caravans in transit (summary helper too)."""
    assert int(_scalar(f, WORLD_SUM_SQL)) == 0                               # characters + accounts
    assert _rows(f, "SELECT kind, ref_id FROM econ_accounts WHERE allow_negative = 0 AND balance < 0 "
                    "AND kind <> 'character'") == []
    expected = int(_scalar(f, "SELECT COALESCE(SUM(paid_purse + paid_treasury - raid_paid), 0) FROM econ_caravans "
                              "WHERE status = 'in_transit'"))
    assert _balance(f, "caravan_escrow", 0) == expected
    db = f()
    try:
        assert crud.escrow_expected(db) == expected == crud.escrow_balance(db)
    finally:
        db.close()


def _pass(f, now, **kw):
    kw.setdefault("force", True)
    kw.setdefault("rng", lambda: 0.5)          # 18 min exactly
    stats = caravan_pass.run_pass(f, now=now, **kw)
    _check(f)
    return stats


START = T0 + timedelta(hours=6, minutes=30)     # dispatch at 06:05, first move due ≤ 06:28


def _walk(f, passes, start=START):
    return [_pass(f, start + timedelta(minutes=30 * i)) for i in range(passes)]


@pytest.fixture
def raider(world, seed_fk_data):
    """A player character (raid receiver); conftest's seeder via its fixture (importing conftest re-runs it)."""
    _add_raider(world, seed_fk_data)
    return RAIDER


def _add_raider(f, seed, cid=RAIDER):
    db = f()
    try:
        seed(db)
        with econ_ledger.allow_direct_balance_write(db):
            db.add(models.Character(id=cid, name="Налётчик", user_id=None, id_subrace=1, id_class=1, id_race=1,
                                    appearance="-", avatar="-", is_npc=False, current_location_id=L_ROAD1, level=5,
                                    currency_balance=0))
            db.commit()
    finally:
        db.close()


def _fake_raid(f, caravan_id, *, marks, stolen_units, status="won", raider=RAIDER):
    """What a won raid (task 3) leaves: escrow → raider (op caravan_raid), raid_paid / stolen_units, the raid row."""
    db = f()
    try:
        if marks:
            econ_ledger.post_operation(
                db, op_type=core.OP_CARAVAN_RAID, source_service="character-service", apply_tax=False,
                idempotency_key=f"caravan:c{caravan_id}:raid",
                legs=[core.Leg(core.AccountRef.caravan_escrow(), core.AccountRef.character(raider), marks)])
        row = db.get(models.EconCaravan, caravan_id)
        row.raid_paid = marks
        row.stolen_units = Decimal(str(stolen_units))
        _insert_raid(db, caravan_id, status, raider)
        db.commit()
    finally:
        db.close()


def _insert_raid(db, caravan_id, status, raider=RAIDER):
    db.add(models.EconCaravanRaid(caravan_id=caravan_id, leader_character_id=raider, location_id=L_ROAD1,
                                  region_id=1, status=status, attacker_ids=[raider], created_at=T0))


def _raid_only(f, caravan_id, status):
    db = f()
    try:
        _insert_raid(db, caravan_id, status)
        db.commit()
    finally:
        db.close()


def _gate(f, caravan_id, *, location=L_GATE1, action="caravan", status="open"):
    _exec(f, "INSERT INTO action_gates (character_id, location_id, action_type, target_ref, status) "
             "VALUES (1, :l, :a, :t, :s)", l=location, a=action, t=caravan_id, s=status)


def _request(f, caravan_id, *, location=L_GATE1, status="pending", action="caravan"):
    gates = json.dumps([{"action_type": "combat", "targets": [999]},
                        {"action_type": action, "targets": [caravan_id]}])
    _exec(f, "INSERT INTO post_gate_requests (character_id, location_id, gates, status) VALUES (1, :l, :g, :s)",
          l=location, g=gates, s=status)


# ===================================================================================================================
# pure: caravan_route
# ===================================================================================================================

ADJ = route.build_adjacency(EDGES)


def test_build_adjacency_is_undirected_sorted_and_drops_self_loops():
    adj = route.build_adjacency([(3, 1), (1, 2), (2, 2), (None, 5), (1, 3)])
    assert adj == {1: [2, 3], 2: [1], 3: [1]}


def test_shortest_route_avoids_dungeons_in_the_middle():
    assert route.shortest_route(ADJ, set(), L_GATE1, L_GATE2, 40) == ([L_GATE1, L_DUNGEON, L_GATE2], None)
    assert route.shortest_route(ADJ, {L_DUNGEON}, L_GATE1, L_GATE2, 40) == (ROAD_1_2, None)


def test_shortest_route_endpoints_may_be_blocked():
    assert route.shortest_route(ADJ, {L_DUNGEON}, L_DUNGEON, L_GATE2, 40) == ([L_DUNGEON, L_GATE2], None)


def test_shortest_route_is_deterministic_by_ascending_id():
    adj = route.build_adjacency([(1, 5), (1, 3), (5, 9), (3, 9)])
    assert route.shortest_route(adj, (), 1, 9, 10)[0] == [1, 3, 9]


@pytest.mark.parametrize("start,goal", [(None, L_GATE2), (L_GATE1, None), (0, L_GATE2), (L_GATE1, L_GATE1)])
def test_shortest_route_no_gate(start, goal):
    assert route.shortest_route(ADJ, (), start, goal, 40) == (None, route.NO_ROAD_NO_GATE)


def test_shortest_route_no_path_and_too_long():
    assert route.shortest_route(ADJ, (), L_GATE1, L_LONE, 40) == (None, route.NO_ROAD_NO_PATH)
    assert route.shortest_route(ADJ, {L_DUNGEON}, L_GATE1, L_GATE2, 3) == (ROAD_1_2, None)        # exactly 3 hops
    assert route.shortest_route(ADJ, {L_DUNGEON}, L_GATE1, L_GATE2, 2) == (None, route.NO_ROAD_TOO_LONG)


def test_effective_gate():
    assert route.effective_gate(7, 9) == (7, route.GATE_OVERRIDE)
    assert route.effective_gate(None, 9) == (9, route.GATE_STATION)
    assert route.effective_gate(None, None) == (None, route.GATE_NONE)


# ===================================================================================================================
# pure: econ_caravan helpers
# ===================================================================================================================

def _p(**kw):
    from dataclasses import replace
    return replace(P, **kw)


def test_physical_roll_is_stable_and_in_unit_interval():
    a = ec.physical_roll(5, 1, 2, "food")
    assert a == ec.physical_roll(5, 1, 2, "food") and 0.0 <= a < 1.0
    assert a != ec.physical_roll(6, 1, 2, "food")
    assert len({ec.physical_roll(r, 1, 2, "ore_metal") for r in range(50)}) == 50


@pytest.mark.parametrize("kw,expected", [
    (dict(value=5000, frm=1, to=1, road=True, active=0, u=0.99), True),                 # large
    (dict(value=10, frm=1, to=2, road=True, active=0, u=0.99), True),                   # foreign
    (dict(value=10, frm=1, to=1, road=True, active=0, u=0.05), True),                   # small, lucky
    (dict(value=10, frm=1, to=1, road=True, active=0, u=0.10), False),                  # u == chance -> no
    (dict(value=5000, frm=1, to=2, road=False, active=0, u=0.0), False),                # no road
    (dict(value=5000, frm=1, to=2, road=True, active=30, u=0.0), False),                # cap reached
    (dict(value=10, frm=None, to=2, road=True, active=0, u=0.99), False),               # unknown country
])
def test_choose_physical_rule(kw, expected):
    assert ec.choose_physical(kw["value"], kw["frm"], kw["to"], kw["road"], kw["active"], P, kw["u"]) is expected


def test_choose_physical_switched_off():
    assert ec.choose_physical(10 ** 6, 1, 2, True, 0, _p(caravan_physical_enabled=0), 0.0) is False
    assert ec.choose_physical(10, 1, 1, True, 0, _p(caravan_physical_small_chance=1.0), 0.999) is True
    assert ec.choose_physical(10 ** 6, 1, 2, True, 0, _p(caravan_physical_max_active=0), 0.0) is False


@pytest.mark.parametrize("value,expected", [(0, 2), (999, 2), (1000, 3), (2999, 4), (10 ** 7, 5)])
def test_guard_count_formula(value, expected):
    assert ec.guard_count(value, P) == expected


def test_guard_count_clamped_to_one_and_max():
    assert ec.guard_count(0, _p(caravan_guard_count_base=0)) == 1
    assert ec.guard_count(10 ** 6, _p(caravan_guard_count_max=3)) == 3


def test_guard_multiplier_formula():
    assert ec.guard_multiplier(0, None, P) == 1.0
    assert ec.guard_multiplier(5000, None, P) == 1.5
    assert ec.guard_multiplier(5000, "dangerous", P) == 1.875
    assert ec.guard_multiplier(50_000, None, P) == 2.0                       # capped
    assert ec.guard_multiplier(50_000, "dangerous", P) == 2.5                # cap x dangerous
    assert ec.guard_multiplier(1234, "safe", P) == 1.123                     # 3 decimals


@pytest.mark.parametrize("value,duty,paid,raid", [(400, 40, 440, 0), (400, 40, 440, 88), (1000, 0, 1000, 333),
                                                  (7, 3, 10, 9), (0, 0, 0, 0), (400, 40, 440, 440)])
def test_remaining_payout_spends_exactly_the_rest(value, duty, paid, raid):
    seller, duty_part = ec.remaining_payout(value, duty, paid, raid)
    assert seller + duty_part == paid - raid
    assert seller >= 0 and 0 <= duty_part <= duty


def test_remaining_payout_values():
    assert ec.remaining_payout(400, 40, 440, 0) == (400, 40)
    assert ec.remaining_payout(400, 40, 440, 88) == (320, 32)                # duty' = floor(40 x 352 / 440)


@pytest.mark.parametrize("purse,treasury,raid", [(300, 140, 88), (440, 0, 88), (0, 440, 1), (100, 100, 0),
                                                 (7, 3, 10), (5, 5, 999)])
def test_refund_split_spends_exactly_the_rest(purse, treasury, raid):
    back_purse, back_treasury = ec.refund_split(purse, treasury, raid)
    assert back_purse + back_treasury == purse + treasury - min(raid, purse + treasury)
    assert 0 <= back_purse <= purse and 0 <= back_treasury <= treasury


def test_refund_split_pro_rata():
    assert ec.refund_split(300, 100, 100) == (225, 75)
    assert ec.refund_split(0, 0, 50) == (0, 0)


def test_stolen_and_bales():
    assert ec.stolen(200, 2, 0.3) == (60.0, 120)
    assert ec.stolen(1.2345, 3, 0.5) == (0.617, 1)                            # floor3, floor value
    assert ec.stolen(10, 2, 0) == (0.0, 0)
    assert ec.bale_count(120, 50) == 2 and ec.bale_count(125, 50) == 3        # half up
    assert ec.bale_count(120, 0) == 0 and ec.bale_count(0, 50) == 0


def test_split_loot():
    assert ec.split_loot(10, 5, [3, 1, 2], leader_id=1) == {1: (4, 2), 3: (3, 2), 2: (3, 1)}
    assert ec.split_loot(10, 0, [3, 3], leader_id=9) == {3: (10, 0)}
    assert ec.split_loot(5, 2, [], leader_id=1) == {}


# ===================================================================================================================
# dispatch: physical vs abstract
# ===================================================================================================================

def test_large_caravan_goes_by_road(world):
    _physical_world(world)
    s = _dispatch(world)
    assert (s.caravans_dispatched, s.caravans_failed) == (1, 0)
    row = _row(world)
    assert row.is_physical and [int(x) for x in row.route] == ROAD_1_2
    assert (row.route_index, row.current_location_id, row.arrived_at, row.hold_started_at) == (0, L_GATE1, None, None)
    assert row.guard_count == ec.guard_count(400, _params(world)) == 2
    dispatched = T0 + timedelta(hours=6)
    assert dispatched + timedelta(minutes=13) <= row.next_move_at <= dispatched + timedelta(minutes=23)
    assert row.value == 400 and row.status == "in_transit"


def test_foreign_caravan_goes_by_road_even_when_small(world):
    _physical_world(world, seller_country=2, caravan_physical_min_value=10 ** 6, caravan_physical_small_chance=0)
    _dispatch(world)
    row = _row(world)
    assert row.is_physical and row.duty > 0 and (row.from_country_id, row.to_country_id) == (2, 1)


def test_small_domestic_caravan_by_chance(world):
    _physical_world(world, caravan_physical_min_value=10 ** 6, caravan_physical_small_chance=1)
    _dispatch(world)
    assert _row(world).is_physical


@pytest.mark.parametrize("setup", ["off", "small", "no_station", "no_path", "cap", "no_graph"])
def test_abstract_cases(world, setup):
    params = {"off": {"caravan_physical_enabled": 0},
              "small": {"caravan_physical_min_value": 10 ** 6, "caravan_physical_small_chance": 0},
              "cap": {"caravan_physical_max_active": 0}}.get(setup, {})
    _physical_world(world, **params)
    if setup == "no_station":
        _exec(world, "UPDATE Regions SET jail_location_id = NULL WHERE id = 2")
    elif setup == "no_path":
        _exec(world, "DELETE FROM LocationNeighbors WHERE location_id = :l OR neighbor_id = :l", l=L_GATE2)
    elif setup == "no_graph":
        _exec(world, "DROP TABLE LocationNeighbors")              # planner unavailable -> abstract, tick not failed
    s = _dispatch(world)
    assert (s.caravans_dispatched, s.caravans_failed) == (1, 0)
    row = _row(world)
    assert not row.is_physical and row.route is None and row.current_location_id is None
    assert row.next_move_at is None and row.guard_count == 0


def test_cap_counts_caravans_already_on_the_road(world):
    _physical_world(world, caravan_physical_max_active=1)
    db = world()
    try:
        db.add(models.EconCaravan(dispatch_run_id=99, from_region_id=1, to_region_id=2, from_country_id=1,
                                  to_country_id=1, group_code="wood", units=1, unit_price=1, value=0, travel_runs=1,
                                  runs_left=1, last_run_id=99, status="in_transit", created_at=T0, is_physical=True,
                                  route=ROAD_1_2, current_location_id=L_GATE1, next_move_at=T0 + timedelta(days=9)))
        db.commit()
    finally:
        db.close()
    _dispatch(world)
    assert not _row(world, 2).is_physical


def test_trade_gate_override_wins_over_the_station(world):
    _physical_world(world)
    _exec(world, "UPDATE econ_regions SET trade_gate_location_id = :l WHERE region_id = 1", l=L_ROAD1)
    _dispatch(world)
    assert [int(x) for x in _row(world).route] == ROAD_1_2[1:]


def test_tick_never_advances_or_finishes_a_physical_caravan(world):
    _physical_world(world)
    _dispatch(world, 1)
    for run in (2, 3, 4):
        s = _dispatch(world, run)
        assert (s.caravans_delivered, s.caravans_cancelled) == (0, 0)
    row = _row(world)
    assert row.status == "in_transit" and row.runs_left == row.travel_runs and row.last_run_id == 1


def test_abstract_caravan_still_delivered_by_the_tick(world):
    _physical_world(world, caravan_physical_enabled=0)
    _dispatch(world, 1)
    _dispatch(world, 2)
    row = _row(world)
    assert not row.is_physical and row.status == "delivered" and row.finished_run_id == 2


# ===================================================================================================================
# the caravan pass: claim, frozen economy, raid-stage stubs
# ===================================================================================================================

def test_pass_claim_throttles(world):
    _physical_world(world)
    assert caravan_pass.run_pass(world, now=START, rng=lambda: 0.5) is not None
    assert caravan_pass.run_pass(world, now=START + timedelta(seconds=30)) is None
    assert caravan_pass.run_pass(world, now=START + timedelta(minutes=1)) is not None


def test_pass_skipped_when_economy_frozen(world):
    _physical_world(world)
    _dispatch(world)
    _exec(world, "UPDATE econ_sim_settings SET tick_enabled = 0")
    assert _pass(world, START) is None
    assert _row(world).route_index == 0


def test_raid_steps_are_noops_without_the_raid_module(world):
    _physical_world(world)
    stats = _pass(world, START)
    assert (stats["stale_raids"], stats["raid_battles"], stats["raid_followups"], stats["failed"]) == (0, 0, 0, 0)


def test_raid_steps_call_the_raid_module_when_present(world, monkeypatch):
    import types
    calls = []
    fake = types.SimpleNamespace(
        expire_stale_raids=lambda f, now, params: calls.append("stale") or 2,
        poll_raid_battles=lambda f, now, params: calls.append("battles") or 0,
        raid_followups=lambda f, now, params: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setitem(sys.modules, "caravan_raid_crud", fake)
    _physical_world(world)
    stats = _pass(world, START)
    assert calls == ["stale", "battles"]
    assert (stats["stale_raids"], stats["raid_battles"], stats["failed"]) == (2, 0, 1)   # one failing step isolated


# ===================================================================================================================
# stepping, holds
# ===================================================================================================================

def test_steps_one_location_per_pass_then_delivers(world):
    _physical_world(world)
    _dispatch(world)
    seller_purse = _balance(world, "population_purse", 1)
    stats = _walk(world, 3)
    assert [(s["moved"], s["arrived"], s["delivered"]) for s in stats] == [(1, 0, 0), (1, 0, 0), (0, 1, 1)]
    row = _row(world)
    assert (row.status, row.route_index, row.current_location_id) == ("delivered", 3, L_GATE2)
    assert row.arrived_at is not None and row.finished_run_id is None and row.next_move_at is None
    assert _stock(world, 2, "food") == Decimal("300")
    assert _balance(world, "population_purse", 1) == seller_purse + 400
    [(op_id, meta)] = _rows(world, "SELECT id, metadata FROM econ_operations WHERE op_type = 'caravan_delivery'")
    meta = json.loads(meta) if isinstance(meta, str) else meta
    assert meta["physical"] is True and meta["raid_paid"] == 0


def test_not_due_caravan_does_not_move(world):
    _physical_world(world)
    _dispatch(world)
    assert _pass(world, T0 + timedelta(hours=6, minutes=10))["moved"] == 0
    assert _row(world).route_index == 0


def test_next_move_follows_the_step_interval(world):
    _physical_world(world, caravan_step_minutes=60)
    _dispatch(world)
    _exec(world, "UPDATE econ_caravans SET next_move_at = :t", t=START - timedelta(minutes=1))
    _pass(world, START, rng=lambda: 0.0)                                       # -25 %
    assert _row(world).next_move_at == START + timedelta(minutes=45)


@pytest.mark.parametrize("hold", ["gate", "request"])
def test_post_hold_then_window_expires(world, hold):
    _physical_world(world)
    _dispatch(world)
    cid = _row(world).id
    (_gate if hold == "gate" else _request)(world, cid)
    s = _pass(world, START)
    row = _row(world)
    assert (s["held"], s["moved"], row.route_index, row.hold_started_at) == (1, 0, 0, START)
    s = _pass(world, START + timedelta(minutes=119))
    assert (s["held"], _row(world).hold_started_at) == (1, START)              # window not reset
    s = _pass(world, START + timedelta(minutes=121))
    row = _row(world)
    assert (s["held"], s["moved"], row.route_index, row.hold_started_at) == (0, 1, 1, START)


def test_one_window_per_caravan_for_the_whole_route(world):
    _physical_world(world)
    _dispatch(world)
    cid = _row(world).id
    _gate(world, cid)
    _pass(world, START)
    _pass(world, START + timedelta(minutes=125))                              # leaves 101 after the window
    _gate(world, cid, location=L_ROAD1)                                       # a new post on the next location
    s = _pass(world, START + timedelta(minutes=150))
    assert (s["held"], s["moved"], _row(world).route_index) == (0, 1, 2)


@pytest.mark.parametrize("kind", ["other_caravan", "other_location", "consumed", "combat", "request_done",
                                  "request_elsewhere", "request_combat"])
def test_irrelevant_gates_do_not_hold(world, kind):
    _physical_world(world)
    _dispatch(world)
    cid = _row(world).id
    {"other_caravan": lambda: _gate(world, cid + 1),
     "other_location": lambda: _gate(world, cid, location=L_ROAD1),
     "consumed": lambda: _gate(world, cid, status="consumed"),
     "combat": lambda: _gate(world, cid, action="combat"),
     "request_done": lambda: _request(world, cid, status="approved"),
     "request_elsewhere": lambda: _request(world, cid, location=L_ROAD1),
     "request_combat": lambda: _request(world, cid, action="combat")}[kind]()
    s = _pass(world, START)
    assert (s["held"], s["moved"]) == (0, 1)


def test_zero_window_disables_post_holds(world):
    _physical_world(world, caravan_post_hold_max_min=0)
    _dispatch(world)
    _gate(world, _row(world).id)
    assert _pass(world, START)["moved"] == 1


def test_missing_gate_tables_do_not_block(world):
    _physical_world(world)
    _dispatch(world)
    _exec(world, "DROP TABLE post_gate_requests")
    s = _pass(world, START)
    assert (s["moved"], s["failed"]) == (1, 0)


@pytest.mark.parametrize("status", ["starting", "fighting"])
def test_active_raid_holds_without_time_cap(world, status):
    _physical_world(world)
    _dispatch(world)
    _raid_only(world, _row(world).id, status)
    for minutes in (0, 600, 3000):
        assert _pass(world, START + timedelta(minutes=minutes))["held"] == 1
    assert _row(world).route_index == 0


@pytest.mark.parametrize("status", ["won", "repelled", "aborted", "expired"])
def test_finished_raid_releases_and_ignores_post_holds(world, status):
    _physical_world(world)
    _dispatch(world)
    cid = _row(world).id
    _raid_only(world, cid, status)
    _gate(world, cid)                                                         # a post after the raid: no stalling
    s = _pass(world, START)
    assert (s["held"], s["moved"]) == (0, 1)


def test_admin_detail_reports_the_hold(world, api_admin):
    _physical_world(world)
    _dispatch(world)
    cid = _row(world).id
    assert api_admin.get(f"{CARAVANS}/{cid}").json()["held_by"] is None
    _gate(world, cid)
    assert api_admin.get(f"{CARAVANS}/{cid}").json()["held_by"] == "post"
    _raid_only(world, cid, "fighting")
    assert api_admin.get(f"{CARAVANS}/{cid}").json()["held_by"] == "raid"


# ===================================================================================================================
# delivery / cancel, with and without a raid; invariants
# ===================================================================================================================

def _arrive(f):
    """Put the caravan on its last location, arrived (no step needed)."""
    _exec(f, "UPDATE econ_caravans SET route_index = 3, current_location_id = :l, arrived_at = :t, next_move_at = NULL",
          l=L_GATE2, t=START - timedelta(minutes=5))


def test_delivery_after_raid_pays_only_the_rest(world, raider):
    _physical_world(world, seller_country=2)
    _dispatch(world)
    row = _row(world)
    assert (row.value, row.duty, row.paid_purse + row.paid_treasury) == (400, 40, 440)
    _fake_raid(world, row.id, marks=88, stolen_units=60)
    _check(world)                                                             # escrow == 440 - 88
    assert _balance(world, "caravan_escrow", 0) == 352
    seller, country = _balance(world, "population_purse", 1), _balance(world, "country_treasury", 1)
    _arrive(world)
    s = _pass(world, START)
    assert s["delivered"] == 1
    assert _balance(world, "population_purse", 1) == seller + 320
    assert _balance(world, "country_treasury", 1) == country + 32
    assert _scalar(world, "SELECT currency_balance FROM characters WHERE id = :c", c=RAIDER) == 88
    assert _balance(world, "caravan_escrow", 0) == 0
    assert _stock(world, 2, "food") == Decimal("240")                         # 100 + 200 - 60
    meta = _scalar(world, "SELECT metadata FROM econ_operations WHERE op_type = 'caravan_delivery'")
    meta = json.loads(meta) if isinstance(meta, str) else meta
    assert (meta["raid_paid"], Decimal(meta["stolen_units"])) == (88, Decimal("60"))


def test_cancel_destination_left_refunds_all_without_raid(world):
    _physical_world(world, treasury=1000)
    _dispatch(world)
    row = _row(world)
    buyer_purse, buyer_treasury = _balance(world, "population_purse", 2), _balance(world, "region_treasury", 2)
    _exec(world, "UPDATE econ_regions SET population = 0 WHERE region_id = 2")
    _arrive(world)
    assert _pass(world, START)["cancelled"] == 1
    after = _row(world)
    assert (after.status, after.cancel_reason, after.goods_returned) == ("cancelled", "destination_left", True)
    assert _balance(world, "population_purse", 2) == buyer_purse + row.paid_purse
    assert _balance(world, "region_treasury", 2) == buyer_treasury + row.paid_treasury
    assert _stock(world, 1, "food") == Decimal("1000")                       # all goods back to the origin


def test_cancel_after_raid_refunds_the_rest_pro_rata(world, raider):
    _physical_world(world, treasury=1000)
    _dispatch(world)
    row = _row(world)
    _fake_raid(world, row.id, marks=100, stolen_units=50)
    buyer_purse, buyer_treasury = _balance(world, "population_purse", 2), _balance(world, "region_treasury", 2)
    _exec(world, "UPDATE econ_regions SET population = 0 WHERE region_id = 2")
    _arrive(world)
    assert _pass(world, START)["cancelled"] == 1
    back_purse, back_treasury = ec.refund_split(row.paid_purse, row.paid_treasury, 100)
    assert back_purse + back_treasury == row.paid_purse + row.paid_treasury - 100
    assert _balance(world, "population_purse", 2) == buyer_purse + back_purse
    assert _balance(world, "region_treasury", 2) == buyer_treasury + back_treasury
    assert _stock(world, 1, "food") == Decimal("950")                        # 800 + 200 - 50 stolen


def test_cancel_destination_deleted_refunds_to_the_country(world):
    _physical_world(world)
    _dispatch(world)
    row = _row(world)
    country = _balance(world, "country_treasury", 1)
    _exec(world, "DELETE FROM Regions WHERE id = 2")
    _arrive(world)
    assert _pass(world, START)["cancelled"] == 1
    assert _row(world).cancel_reason == "destination_deleted"
    assert _balance(world, "country_treasury", 1) == country + row.paid_purse + row.paid_treasury


def test_delivery_postponed_while_an_economy_run_is_running(world):
    _physical_world(world)
    _dispatch(world)
    _arrive(world)
    db = world()
    try:
        db.add(models.EconTickRun(trigger_kind="manual", status="running", started_at=T0, heartbeat_at=T0))
        db.commit()
    finally:
        db.close()
    s = _pass(world, START)
    assert (s["delivered"], s.get("delivery_postponed")) == (0, 1)
    assert _row(world).status == "in_transit"
    _exec(world, "UPDATE econ_tick_runs SET status = 'done'")
    assert _pass(world, START + timedelta(minutes=5))["delivered"] == 1


def test_delivery_is_idempotent(world):
    _physical_world(world)
    _dispatch(world)
    _arrive(world)
    cid = _row(world).id
    assert crud.deliver_physical_tx(world, cid, START).status == "delivered"
    assert crud.deliver_physical_tx(world, cid, START).status == "already"
    assert _scalar(world, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'caravan_delivery'") == 1
    _check(world)


def test_abstract_caravan_is_never_delivered_by_the_pass(world):
    _physical_world(world, caravan_physical_enabled=0)
    _dispatch(world)
    _exec(world, "UPDATE econ_caravans SET arrived_at = :t", t=T0)
    db = world()
    try:
        assert crud.deliver_physical(db, _row(world).id, START).status == "already"
    finally:
        db.rollback()
        db.close()
    assert _pass(world, START)["delivered"] == 0


# ===================================================================================================================
# inbound / region card
# ===================================================================================================================

def test_inbound_subtracts_stolen_units(world, raider):
    import economy_guild_crud
    _physical_world(world)
    _dispatch(world)
    _fake_raid(world, _row(world).id, marks=10, stolen_units=60)
    db = world()
    try:
        snap = crud.load_snapshot(db, 99, _params(world), econ_tick.load_groups(db), {})
        assert snap.inbound[(2, "food")] == pytest.approx(140.0)
        assert economy_guild_crud.inbound_units(db, 2)["food"] == pytest.approx(140.0)
    finally:
        db.close()


def test_region_card_hides_physical_caravans(world, api_admin):
    _physical_world(world)
    _dispatch(world)
    assert _row(world).is_physical
    for rid in (1, 2):
        card = api_admin.get(f"/characters/economy/regions/{rid}/card").json()
        assert card["caravans"] == {"incoming": [], "outgoing": []}
    # delivered physical caravans stay hidden too, and no route / location leaks anywhere in the card
    _arrive(world)
    _pass(world, START)
    body = api_admin.get("/characters/economy/regions/2/card").text
    assert json.loads(body)["caravans"] == {"incoming": [], "outgoing": []}
    for leak in ("route", "current_location", "Застава", "Тракт", "Перевал"):
        assert leak not in body


def test_region_card_still_shows_abstract_caravans(world, api_admin):
    _physical_world(world, caravan_physical_enabled=0)
    db = world()
    try:
        db.add(models.EconCaravan(dispatch_run_id=1, from_region_id=1, to_region_id=2, from_country_id=1,
                                  to_country_id=1, group_code="food", units=1, unit_price=1, value=1, travel_runs=1,
                                  runs_left=1, last_run_id=1, status="in_transit", created_at=T0))
        db.commit()
    finally:
        db.close()
    assert [l["region_id"] for l in api_admin.get("/characters/economy/regions/2/card").json()["caravans"]
            ["incoming"]] == [1]


# ===================================================================================================================
# admin A4–A9
# ===================================================================================================================

@pytest.fixture
def api_admin(world):
    def override_get_db():
        session = world()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[economy_api.get_db] = override_get_db
    _as(["economy:read", "economy:emit", "economy:adjust", "economy:settings"], role="admin")
    core.invalidate_settings_cache()
    yield TestClient(app)
    app.dependency_overrides.pop(economy_api.get_db, None)
    app.dependency_overrides.pop(get_current_user_via_http, None)
    core.invalidate_settings_cache()


def _as(permissions, role="moderator"):
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=7, username="tester", role=role, permissions=list(permissions))


def _mob_templates(f, *ids):
    db = f()
    try:
        for tid, level in ids:
            db.add(models.MobTemplate(id=tid, name=f"Охранник {tid}", level=level, id_race=1, id_subrace=1,
                                      id_class=1))
        db.commit()
    finally:
        db.close()


ADMIN_GETS = [f"{CARAVANS}/roads", f"{CARAVANS}/guards", f"{CARAVANS}/1", f"{CARAVANS}?kind=physical"]


def _admin_puts(c):
    return [c.put(f"{CARAVANS}/gates/1", json={"location_id": None}),
            c.put(f"{CARAVANS}/guards", json={"mob_template_ids": []})]


def test_admin_unauthenticated_is_401(api_admin):
    app.dependency_overrides.pop(get_current_user_via_http, None)
    c = TestClient(app)
    assert [c.get(u).status_code for u in ADMIN_GETS] == [401] * 4
    assert [r.status_code for r in _admin_puts(c)] == [401, 401]


def test_admin_plain_user_is_403(api_admin):
    _as([], role="user")
    c = TestClient(app)
    assert [c.get(u).status_code for u in ADMIN_GETS] == [403] * 4
    assert [r.status_code for r in _admin_puts(c)] == [403, 403]


def test_admin_read_permission_cannot_write(world, api_admin):
    _physical_world(world)
    _dispatch(world)
    _as(READ)
    c = TestClient(app)
    assert [c.get(u).status_code for u in ADMIN_GETS] == [200] * 4
    assert [r.status_code for r in _admin_puts(c)] == [403, 403]
    _as(SETTINGS)
    assert [r.status_code for r in _admin_puts(TestClient(app))] == [200, 200]


def test_a4_list_kind_filter_and_fields(world, api_admin):
    _physical_world(world)
    _dispatch(world)
    _set_params(world, caravan_physical_enabled=0)
    _region(world, 3)
    _good(world, 3, "food", 50, 300)
    _dispatch(world, 2)
    all_items = api_admin.get(CARAVANS).json()["items"]
    phys = api_admin.get(f"{CARAVANS}?kind=physical").json()["items"]
    abstract = api_admin.get(f"{CARAVANS}?kind=abstract").json()["items"]
    assert len(all_items) == len(phys) + len(abstract) and len(phys) == 1 and abstract
    [p] = phys
    assert (p["is_physical"], p["current_location_id"], p["current_location_name"], p["route_index"],
            p["route_len"], p["guard_count"], p["stolen_units"], p["raid_paid"], p["raid_status"]) == \
        (True, L_GATE1, "Застава Пашен", 0, 4, 2, 0, 0, None)
    assert all(not a["is_physical"] and a["route_len"] == 0 for a in abstract)
    for bad in ("bogus", "'; DROP TABLE econ_caravans; --"):
        assert api_admin.get(CARAVANS, params={"kind": bad}).status_code == 422
    assert _scalar(world, "SELECT COUNT(*) FROM econ_caravans") == len(all_items)


def test_a5_detail(world, api_admin, raider):
    _physical_world(world)
    _dispatch(world)
    cid = _row(world).id
    data = api_admin.get(f"{CARAVANS}/{cid}").json()
    assert [(s["index"], s["location_id"], s["name"], s["region_id"]) for s in data["route"]] == [
        (0, L_GATE1, "Застава Пашен", 1), (1, L_ROAD1, "Тракт", 1), (2, L_ROAD2, "Перевал", 2),
        (3, L_GATE2, "Застава Оста", 2)]
    assert data["route"][0]["region_name"] == "Регион 1" and data["raid"] is None
    _fake_raid(world, cid, marks=50, stolen_units=10)
    raid = api_admin.get(f"{CARAVANS}/{cid}").json()["raid"]
    assert (raid["status"], raid["leader_id"], raid["leader_name"]) == ("won", RAIDER, "Налётчик")
    assert raid["attackers"][0]["id"] == RAIDER


def test_a5_unknown_and_invalid(api_admin):
    resp = api_admin.get(f"{CARAVANS}/987654")
    assert resp.status_code == 404 and resp.json()["detail"] == "Караван не найден"
    assert api_admin.get(f"{CARAVANS}/0").status_code == 422
    assert api_admin.get(f"{CARAVANS}/abc").status_code == 422


def test_a6_roads_and_no_road_reasons(world, api_admin):
    _physical_world(world)
    data = api_admin.get(f"{CARAVANS}/roads").json()
    assert [(r["region_id"], r["gate_location_id"], r["gate_source"], r["station_location_name"])
            for r in data["regions"]] == [(1, L_GATE1, "station", "Застава Пашен"), (2, L_GATE2, "station",
                                                                                     "Застава Оста")]
    assert data["no_road"] == []
    _set_params(world, caravan_route_max_steps=2)
    assert [n["reason"] for n in api_admin.get(f"{CARAVANS}/roads").json()["no_road"]] == ["too_long"]
    _set_params(world, caravan_route_max_steps=40)
    _exec(world, "DELETE FROM LocationNeighbors WHERE location_id = :l OR neighbor_id = :l", l=L_ROAD2)
    assert [n["reason"] for n in api_admin.get(f"{CARAVANS}/roads").json()["no_road"]] == ["no_path"]
    _exec(world, "UPDATE Regions SET jail_location_id = NULL WHERE id = 2")
    road = api_admin.get(f"{CARAVANS}/roads").json()
    assert road["no_road"] == [{"from_region_id": 1, "from_name": "Регион 1", "to_region_id": 2,
                                "to_name": "Регион 2", "reason": "no_gate"}]
    assert road["regions"][1]["gate_source"] == "none"


def test_a6_foreign_pairs_only_when_enabled(world, api_admin):
    _physical_world(world, seller_country=2)
    _exec(world, "UPDATE Regions SET jail_location_id = NULL WHERE id = 2")
    assert len(api_admin.get(f"{CARAVANS}/roads").json()["no_road"]) == 1
    _pair(world, 1, 2, enabled=False)
    assert api_admin.get(f"{CARAVANS}/roads").json()["no_road"] == []


def test_a7_gate_override_set_and_clear(world, api_admin):
    _physical_world(world)
    resp = api_admin.put(f"{CARAVANS}/gates/1", json={"location_id": L_ROAD1})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["gate_override_id"], body["gate_location_id"], body["gate_source"], body["gate_override_name"]) == \
        (L_ROAD1, L_ROAD1, "override", "Тракт")
    assert _scalar(world, "SELECT trade_gate_location_id FROM econ_regions WHERE region_id = 1") == L_ROAD1
    body = api_admin.put(f"{CARAVANS}/gates/1", json={"location_id": None}).json()
    assert (body["gate_override_id"], body["gate_location_id"], body["gate_source"]) == (None, L_GATE1, "station")


@pytest.mark.parametrize("region,payload,status,detail", [
    (1, {"location_id": L_GATE2}, 400, "Локация не принадлежит этому краю"),
    (1, {"location_id": L_DUNGEON}, 400, "Подземелье не может быть торговыми воротами"),
    (1, {"location_id": 99999}, 400, "Локация не принадлежит этому краю"),
    (77, {"location_id": None}, 404, "Край не найден"),
    (1, {"location_id": 0}, 422, None),
    (1, {"location_id": "101"}, 422, None),
    (1, {"location_id": L_ROAD1, "extra": 1}, 422, None),
    (0, {"location_id": None}, 422, None),
])
def test_a7_validation(world, api_admin, region, payload, status, detail):
    _physical_world(world)
    resp = api_admin.put(f"{CARAVANS}/gates/{region}", json=payload)
    assert resp.status_code == status, resp.text
    if detail:
        assert resp.json()["detail"] == detail
    assert _scalar(world, "SELECT trade_gate_location_id FROM econ_regions WHERE region_id = 1") is None


def test_a8_a9_guard_pool(world, api_admin):
    _mob_templates(world, (11, 5), (12, 1), (13, 9))
    assert api_admin.get(f"{CARAVANS}/guards").json() == {"templates": []}
    resp = api_admin.put(f"{CARAVANS}/guards", json={"mob_template_ids": [11, 12]})
    assert resp.status_code == 200, resp.text
    assert [(t["mob_template_id"], t["level"], t["name"]) for t in resp.json()["templates"]] == \
        [(12, 1, "Охранник 12"), (11, 5, "Охранник 11")]                    # level ascending
    resp = api_admin.put(f"{CARAVANS}/guards", json={"mob_template_ids": [13, 11]})
    assert [t["mob_template_id"] for t in resp.json()["templates"]] == [11, 13]
    assert api_admin.put(f"{CARAVANS}/guards", json={"mob_template_ids": []}).json() == {"templates": []}


@pytest.mark.parametrize("payload,status,detail", [
    ({"mob_template_ids": [11, 999]}, 400, "Шаблон моба не найден: 999"),
    ({"mob_template_ids": [11, 11]}, 422, None),
    ({"mob_template_ids": list(range(1, 22))}, 422, None),
    ({"mob_template_ids": [0]}, 422, None),
    ({"mob_template_ids": ["11"]}, 422, None),
    ({"mob_template_ids": [11], "x": 1}, 422, None),
])
def test_a9_validation_keeps_the_pool(world, api_admin, payload, status, detail):
    _mob_templates(world, (11, 5), (12, 1))
    api_admin.put(f"{CARAVANS}/guards", json={"mob_template_ids": [12]})
    resp = api_admin.put(f"{CARAVANS}/guards", json=payload)
    assert resp.status_code == status, resp.text
    if detail:
        assert resp.json()["detail"] == detail
    assert [t["mob_template_id"] for t in api_admin.get(f"{CARAVANS}/guards").json()["templates"]] == [12]
