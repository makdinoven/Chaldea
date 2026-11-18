"""FEAT-215 QA (#9): sea caravans end to end on SQLite (features/FEAT-215 §3.3–3.9).

World = the FEAT-214 ``storm`` world (:mod:`tests.sea_storm_world` on :mod:`tests.sea_world`: ship 1 «Морская дева»
103 «Тракт» (region 10, country 1) → 200 «Оазис» (region 20, country 2) → 110 «Нива», deck 600, docked at 103) plus
the economy of :mod:`tests.test_econ_tick` grafted on it: econ regions 10 (seller, gate 100 «Рынок») and 20 (buyer,
gate 210 «Караван-сарай»), land roads 100–103 and 200–210 only (no land path 10 ↔ 20), trade pair 1–2 (duty 10 %).
A sea caravan therefore goes 100 → 103 ⚓ 200 → 210 (``sea_split_index`` 1).

Covers: dispatch of a sea row (route / split / ports / freight, escrow), «no land and no sea path → no deal», the
stages (to_port → waiting → aboard → landed → delivered), the hold capacity and the serving-ship check, escorts
sailing without a ticket and landing with the cargo, the ``caravan_freight`` op (port region treasury + country tax
leg), the 24 h wait limit and the strand cases (safe landing / ship delete / route change) → cancel with refund,
``delete_ship`` 409 under an active caravan raid, the raid on a deck (crime region = departure port, loot without the
freight and sunk units), monster cargo loss (2 groups: 1 won 1 lost → half the share; applied once; empty deck → no
attack), escorts in monster fights, the deck view cargo / passenger count, ship admin ``cargo_capacity`` and the
admin caravans ``kind=sea``. After every money step the world money sum is unchanged and the escrow equals
``Σ (paid − raid_paid − freight_paid)`` of caravans in transit.
"""

from datetime import timedelta
from decimal import Decimal

import pytest

import caravan_pass
import caravan_raid_crud as raids
import econ_caravan as ec
import econ_core as core
import econ_ledger
import econ_tick
import economy_caravan_crud as crud
import models
import sea_admin
import sea_crud
import sea_pass
import sea_raid_crud
from tests.sea_storm_world import MONSTER_TPL, add_monster, raids as sea_raids, storm  # noqa: F401
from tests.sea_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, CAPTAIN, DECK, GAMMA, INTERNAL, P_A, P_B, P_C, R_A, USER_ALPHA, Z2, api, as_user, client, depart,
    exec_, law_world, loc, money_total, now, op, passes, place, postings, q, rep_world, rows, run_ship, sea, set_ship,
    ship,
)
from tests.test_econ_tick import SCALE, _add_region, mig
from tests.test_econ_tick_caravans import _good, _groups, _pair, _params, _set_params, _stock
from tests.test_econ_tick_events import calendar  # noqa: F401  (autouse: no calendar HTTP)

GATE_A, GATE_B = 100, 210                     # trade gates of regions 10 (seller) and 20 (buyer)
R_SELL, R_BUY = 10, 20
ROUTE = [GATE_A, P_A, P_B, GATE_B]
ECON_READ = ["economy:read"]
SHIP_PERMS = ["locations:read", "locations:create", "locations:update", "locations:delete"]
RESULT = "/characters/internal/sea/raid-result"
CARAVANS = "/characters/admin/economy/caravans"
SHIPS = "/characters/admin/sea/ships"


# ===================================================================================================================
# world
# ===================================================================================================================

def _seed_econ(f):
    """The migration-028 economy defaults (as ``test_econ_tick.factory``) on the law/sea world."""
    db = f()
    try:
        for i, g in enumerate(mig.GROUPS, 1):
            db.add(models.EconGoodsGroup(code=g[0], name=g[1], sort_order=i, base_price=g[2], norm_per_1000=g[3],
                                         norm_days=g[4], prosperity_elasticity=g[5], price_elasticity=g[6],
                                         is_food=bool(g[7])))
        db.flush()
        for group_code, inputs in mig.INPUTS.items():
            for input_code, ratio in inputs:
                db.add(models.EconGroupInput(group_code=group_code, input_code=input_code, ratio=ratio))
        for i, t in enumerate(mig.TEMPLATES, 1):
            db.add(models.EconRegionTemplate(code=t[0], name=t[1], description=t[2], settlement_noun=t[3],
                                             noun_gender=t[4], default_population=t[5] * SCALE, tax_rate=t[6],
                                             sort_order=i))
        db.flush()
        for t in mig.TEMPLATES:
            for group_code, prod, cmult in mig.template_goods(t[0]):
                db.add(models.EconTemplateGood(template_code=t[0], group_code=group_code, production_per_1000=prod,
                                               consumption_mult=cmult))
        db.add(models.EconSimSettings(id=1, tick_enabled=True, params=dict(mig.DEFAULT_PARAMS)))
        db.commit()
    finally:
        db.close()


@pytest.fixture
def sc(storm):
    f = storm
    _seed_econ(f)
    cols = {r[1] for r in rows(f, "PRAGMA table_info(Locations)")}
    for col, ddl in (("marker_type", "VARCHAR(20) NULL"), ("recommended_level", "INTEGER NULL")):
        if col not in cols:
            exec_(f, f"ALTER TABLE Locations ADD COLUMN {col} {ddl}")
    exec_(f, "INSERT INTO Locations (id, name, region_id) VALUES (210, 'Караван-сарай', 20)")
    for a, b in ((GATE_A, P_A), (P_B, GATE_B)):
        exec_(f, "INSERT INTO LocationNeighbors (location_id, neighbor_id) VALUES (:a, :b), (:b, :a)", a=a, b=b)
    for rid, country, gate in ((R_SELL, 1, GATE_A), (R_BUY, 2, GATE_B)):
        _add_region(f, rid, country_id=country, world_row=False)
        exec_(f, "UPDATE econ_region_goods SET stock = norm_stock, price_mult = 1 WHERE region_id = :r", r=rid)
        exec_(f, "UPDATE econ_regions SET trade_gate_location_id = :g WHERE region_id = :r", g=gate, r=rid)
    _good(f, R_SELL, "food", 1000, 200)
    _good(f, R_BUY, "food", 100, 300)
    _pair(f, 1, 2, duty=10)
    _set_params(f, caravan_physical_enabled=1, caravan_physical_min_value=1, caravan_departure_minutes=0)
    econ_ledger.invalidate_settings_cache()
    f.T = f.t0                                   # ship 1 created at t0, departs at t0 + 30 min
    return f


# ===================================================================================================================
# helpers
# ===================================================================================================================

def _check(f):
    """escrow == Σ (paid − raid_paid − freight_paid − duty_paid) of caravans in transit (FEAT-216: a duty paid at a
    customs post left the escrow); nothing non-negative went negative."""
    expected = int(q(f, "SELECT COALESCE(SUM(paid_purse + paid_treasury - raid_paid - freight_paid - duty_paid), 0) "
                        "FROM econ_caravans WHERE status = 'in_transit'"))
    db = f()
    try:
        assert crud.escrow_expected(db) == expected == crud.escrow_balance(db)
    finally:
        db.close()
    assert rows(f, "SELECT kind, ref_id FROM econ_accounts WHERE allow_negative = 0 AND balance < 0 "
                   "AND kind <> 'character'") == []


def _dispatch(f, run_id=1):
    summary = econ_tick.RunSummary(run_id=run_id, trigger="manual", slot=None, status="running")
    econ_tick._caravan_pass(f, run_id, summary, _params(f), f.T - timedelta(hours=2), _groups(f), {})
    _check(f)
    return summary


def _cpass(f, when):
    stats = caravan_pass.run_pass(f, now=when, force=True, rng=lambda: 0.5)
    assert stats is not None and stats["failed"] == 0, stats
    _check(f)
    return stats


def _row(f, caravan_id=None):
    db = f()
    try:
        row = (db.get(models.EconCaravan, caravan_id) if caravan_id
               else db.query(models.EconCaravan).order_by(models.EconCaravan.id).first())
        if row is not None:
            db.expunge(row)
        return row
    finally:
        db.close()


def _set_row(f, caravan_id, **cols):
    db = f()
    try:
        row = db.get(models.EconCaravan, caravan_id)
        for k, v in cols.items():
            setattr(row, k, v)
        db.commit()
    finally:
        db.close()


def _waiting(f):
    """Dispatch the sea caravan and step it to its boarding port (stage ``waiting``); returns its id."""
    _dispatch(f)
    c = _row(f)
    stats = _cpass(f, f.T - timedelta(hours=1))
    assert stats["at_port"] == 1
    return int(c.id)


def _sea_row(f, *, stage, location, run_id, ship_id=None, alight=P_B, board=P_A, units=100, since=None):
    """A money-less sea caravan inserted directly (paid 0 → the escrow invariant is untouched)."""
    db = f()
    try:
        row = models.EconCaravan(
            dispatch_run_id=run_id, from_region_id=R_SELL, to_region_id=R_BUY, from_country_id=1, to_country_id=2,
            group_code="food", units=Decimal(units), unit_price=Decimal(2), value=2 * units, travel_runs=1,
            runs_left=1, last_run_id=run_id, status="in_transit", created_at=now(), is_physical=True, route=ROUTE,
            route_index=1, current_location_id=location, sea_stage=stage, sea_split_index=1, sea_board_port_id=board,
            sea_alight_port_id=alight, sea_ship_id=ship_id, sea_waiting_since=since)
        db.add(row)
        db.commit()
        return int(row.id)
    finally:
        db.close()


def _escort(f, caravan_id, character_id=GAMMA, location=None):
    exec_(f, "INSERT INTO econ_caravan_escorts (caravan_id, character_id, status, joined_at) "
             "VALUES (:c, :ch, 'active', :t)", c=caravan_id, ch=character_id, t=now())
    exec_(f, "UPDATE characters SET escort_caravan_id = :c WHERE id = :ch", c=caravan_id, ch=character_id)
    if location is not None:
        place(f, character_id, location)


def _purse_treasury(f, region_id):
    return int(q(f, "SELECT COALESCE(SUM(balance), 0) FROM econ_accounts WHERE ref_id = :r "
                    "AND kind IN ('population_purse', 'region_treasury')", r=region_id))


def _db_call(f, fn, *args, **kwargs):
    db = f()
    try:
        result = fn(db, *args, **kwargs)
        db.commit()
        return result
    finally:
        db.close()


# ===================================================================================================================
# dispatch / planning
# ===================================================================================================================

def test_dispatch_creates_a_sea_row_with_route_split_ports_and_freight(sc):
    before = money_total(sc)
    summary = _dispatch(sc)
    c = _row(sc)
    assert summary.caravans_dispatched == 1
    assert (c.is_physical, c.sea_stage, c.route, c.sea_split_index) == (True, "to_port", ROUTE, 1)
    assert (c.sea_board_port_id, c.sea_alight_port_id, c.sea_ship_id, c.current_location_id) == (P_A, P_B, None,
                                                                                                    GATE_A)
    assert c.freight == int(c.value * 5 // 100) and c.freight > 0 and c.freight_paid == 0
    assert c.paid_purse + c.paid_treasury == c.value + c.duty + c.freight
    assert crud.escrow_balance(sc()) == c.paid_purse + c.paid_treasury
    assert money_total(sc) == before


@pytest.mark.parametrize("change", ["no_hold", "ship_off", "physical_off"])
def test_no_land_and_no_sea_path_means_no_deal(sc, change):
    _set_params(sc, caravan_no_path_abstract=0)
    if change == "no_hold":
        set_ship(sc, cargo_capacity=0)
    elif change == "ship_off":
        set_ship(sc, is_active=False)
    else:
        _set_params(sc, caravan_physical_enabled=0)          # sea caravans are always physical
    _dispatch(sc)
    assert int(q(sc, "SELECT COUNT(*) FROM econ_caravans")) == 0
    assert _stock(sc, R_SELL, "food") == Decimal("1000.000")


@pytest.mark.parametrize("change", ["no_hold", "ship_off", "physical_off"])
def test_no_land_and_no_sea_path_falls_back_to_abstract_trade(sc, change):
    """Default ``caravan_no_path_abstract`` = 1: no road and no ship -> the old abstract caravan, no freight."""
    if change == "no_hold":
        set_ship(sc, cargo_capacity=0)
    elif change == "ship_off":
        set_ship(sc, is_active=False)
    else:
        _set_params(sc, caravan_physical_enabled=0)
    _dispatch(sc)
    found = rows(sc, "SELECT is_physical, sea_stage, freight FROM econ_caravans")
    assert len(found) == 1 and not found[0][0] and found[0][1] is None and int(found[0][2]) == 0


# ===================================================================================================================
# the voyage: waiting → aboard (+ escorts, deck view) → landed (+ freight) → delivered
# ===================================================================================================================

def test_full_voyage_with_an_escort_freight_and_delivery(sc):
    before = money_total(sc)
    cid = _waiting(sc)
    _escort(sc, cid, GAMMA, location=P_A)                     # the escort rides with the wagon (at the port now)
    c = _row(sc, cid)
    assert (c.sea_stage, c.current_location_id, c.next_move_at) == ("waiting", P_A, None)
    assert c.sea_waiting_since is not None
    _cpass(sc, sc.T)                                          # a waiting caravan is not stepped by the caravan pass
    assert _row(sc, cid).current_location_id == P_A

    _out, t = depart(sc)
    c = _row(sc, cid)
    assert (c.sea_stage, c.sea_ship_id, c.current_location_id) == ("aboard", sc.ship_id, DECK)
    assert loc(sc, GAMMA) == DECK and passes(sc, character_id=GAMMA) == []   # no ticket, not put ashore

    place(sc, BETA, DECK)                                     # a plain passenger
    db = sc()
    try:
        view = sea_crud.deck_view(db, DECK, BETA, int(q(sc, "SELECT user_id FROM characters WHERE id = 2")), now=t)
    finally:
        db.close()
    assert view["passengers_count"] == 1                      # the hidden escort is not counted
    food = q(sc, "SELECT name FROM econ_goods_groups WHERE code = 'food'")
    assert view["cargo"] == [{"caravan_id": cid, "group_name": food, "alight_port_name": "Оазис"}]
    place(sc, BETA, P_A)

    region_before = int(q(sc, "SELECT balance FROM econ_accounts WHERE kind = 'region_treasury' AND ref_id = 10")
                        or 0)
    out = run_ship(sc, t + timedelta(minutes=30))             # arrival at 200 → unload
    assert sea_pass.EV_ARRIVED in out.events
    c = _row(sc, cid)
    assert (c.sea_stage, c.current_location_id, c.route_index) == ("landed", P_B, 2)
    assert c.sea_unloaded_at is not None and c.next_move_at is not None
    assert c.freight_paid == c.freight and c.freight_op_id is not None
    assert loc(sc, GAMMA) == P_B
    assert op(sc, c.freight_op_id)[0] == core.OP_CARAVAN_FREIGHT
    legs = postings(sc, c.freight_op_id)
    rate = econ_ledger.get_economy_settings(sc()).country_tax_rate
    tax = core.tax_amount(c.freight, rate)
    assert tax > 0
    assert sorted((r[0], r[2], r[3], r[4]) for r in legs) == sorted(
        [("caravan_escrow", "region_treasury", R_A, c.freight - tax), ("caravan_escrow", "country_treasury", 1, tax)])
    assert int(q(sc, "SELECT balance FROM econ_accounts WHERE kind = 'region_treasury' AND ref_id = 10")) \
        == region_before + c.freight - tax
    _check(sc)
    assert money_total(sc) == before

    # land leg 2: 200 → 210, arrival, delivery (escrow drains to zero); sunk units never reach the buyer
    _set_row(sc, cid, sunk_units=Decimal(5))
    buyer_stock = _stock(sc, R_BUY, "food")
    when = t + timedelta(hours=1)
    for i in range(3):
        _cpass(sc, when + timedelta(minutes=30 * i))
    c = _row(sc, cid)
    assert c.status == "delivered" and crud.escrow_balance(sc()) == 0
    assert _stock(sc, R_BUY, "food") == buyer_stock + Decimal(str(c.units)) - 5
    assert q(sc, "SELECT escort_caravan_id FROM characters WHERE id = :c", c=GAMMA) is None
    assert q(sc, "SELECT status FROM econ_caravan_escorts WHERE caravan_id = :c", c=cid) == "delivered"
    assert money_total(sc) == before


def test_boarding_respects_the_hold_and_the_serving_ship(sc):
    set_ship(sc, cargo_capacity=1)
    # lowest id first: the ship never goes to 100 — skipped without taking the only hold slot
    wrong = _sea_row(sc, stage="waiting", location=P_A, run_id=11, alight=GATE_A, since=now())
    first = _sea_row(sc, stage="waiting", location=P_A, run_id=12, since=now())
    second = _sea_row(sc, stage="waiting", location=P_A, run_id=13, since=now())
    elsewhere = _sea_row(sc, stage="waiting", location=P_B, board=P_B, alight=P_C, run_id=14, since=now())
    depart(sc)
    assert [_row(sc, i).sea_stage for i in (wrong, first, second, elsewhere)] == [
        "waiting", "aboard", "waiting", "waiting"]
    assert (_row(sc, first).current_location_id, _row(sc, first).sea_ship_id) == (DECK, sc.ship_id)
    assert _row(sc, second).current_location_id == P_A and _row(sc, second).sea_ship_id is None
    db = sc()
    try:
        assert sea_admin.ship_admin_out(db, db.get(models.SeaShip, sc.ship_id))["cargo_aboard"] == 1
    finally:
        db.close()


def test_wait_limit_cancels_with_goods_and_money_back(sc):
    before = money_total(sc)
    cid = _waiting(sc)
    c = _row(sc, cid)
    _set_row(sc, cid, sea_waiting_since=sc.T - timedelta(hours=23), stolen_units=Decimal(1), sunk_units=Decimal(2))
    _cpass(sc, sc.T)
    assert _row(sc, cid).status == "in_transit"               # 23 h < 24 h
    stock = _stock(sc, R_SELL, "food")
    buyer = _purse_treasury(sc, R_BUY)
    _set_row(sc, cid, sea_waiting_since=sc.T - timedelta(hours=25))
    stats = _cpass(sc, sc.T)
    assert stats["sea_cancelled"] == 1
    c2 = _row(sc, cid)
    assert (c2.status, c2.cancel_reason) == ("cancelled", "sea_wait_expired")
    assert _stock(sc, R_SELL, "food") == stock + Decimal(str(c.units)) - 3       # minus stolen + sunk
    assert _purse_treasury(sc, R_BUY) == buyer + c.paid_purse + c.paid_treasury  # freight included (never charged)
    assert crud.escrow_balance(sc()) == 0 and money_total(sc) == before


# ===================================================================================================================
# strand: safe landing / ship delete / route change → cancel with refund
# ===================================================================================================================

def test_safe_landing_strands_the_cargo_and_the_caravan_pass_refunds(sc):
    before = money_total(sc)
    cid = _waiting(sc)
    _escort(sc, cid, GAMMA, location=P_A)
    _out, t = depart(sc)
    c = _row(sc, cid)
    assert c.sea_stage == "aboard"
    buyer = _purse_treasury(sc, R_BUY)
    db = sc()
    try:
        s = sea_crud.get_ship(db, sc.ship_id, lock=True)
        out = sea_pass.ShipOutcome(int(s.id), deck_location_id=DECK, now=t)
        sea_pass._land_broken(db, s, "no_path", t + timedelta(minutes=5), out)
        db.commit()
    finally:
        db.close()
    c = _row(sc, cid)
    assert (c.sea_stage, c.current_location_id) == ("stranded", P_A)     # landing target = the last port
    assert loc(sc, GAMMA) == P_A
    stats = _cpass(sc, t + timedelta(minutes=10))
    assert stats["sea_cancelled"] == 1
    c = _row(sc, cid)
    assert (c.status, c.cancel_reason, c.freight_paid) == ("cancelled", "sea_route_lost", 0)
    assert _purse_treasury(sc, R_BUY) == buyer + c.paid_purse + c.paid_treasury
    assert money_total(sc) == before
    assert q(sc, "SELECT escort_caravan_id FROM characters WHERE id = :c", c=GAMMA) is None   # escort released
    assert q(sc, "SELECT status FROM econ_caravan_escorts WHERE caravan_id = :c", c=cid) == "cancelled"


def test_delete_ship_strands_the_hold_and_is_refused_under_a_caravan_raid(sc):
    raided = _sea_row(sc, stage="aboard", location=DECK, run_id=21, ship_id=sc.ship_id)
    exec_(sc, "INSERT INTO econ_caravan_raids (caravan_id, leader_character_id, location_id, region_id, status, "
              "created_at) VALUES (:c, :l, :loc, 10, 'fighting', :t)", c=raided, l=ALPHA, loc=DECK, t=now())
    with pytest.raises(sea_admin.SeaError) as err:
        _db_call(sc, sea_admin.delete_ship, sc.ship_id)
    assert err.value.status_code == 409
    assert ship(sc) is not None and _row(sc, raided).sea_stage == "aboard"

    exec_(sc, "UPDATE econ_caravan_raids SET status = 'won' WHERE caravan_id = :c", c=raided)
    _db_call(sc, sea_admin.delete_ship, sc.ship_id)
    assert ship(sc) is None
    c = _row(sc, raided)
    assert (c.sea_stage, c.current_location_id) == ("stranded", P_A)
    _cpass(sc, now())
    assert (_row(sc, raided).status, _row(sc, raided).cancel_reason) == ("cancelled", "sea_route_lost")


def test_route_change_strands_the_cargo_at_the_next_pass(sc):
    cid = _sea_row(sc, stage="aboard", location=DECK, run_id=31, ship_id=sc.ship_id)
    _db_call(sc, sea_admin.update_ship, sc.ship_id,
             sea_admin.ShipUpdate(stops=[{"port_location_id": P_A}, {"port_location_id": P_C}]))
    run_ship(sc, sc.T + timedelta(minutes=1))                 # before the departure: only the hold check
    c = _row(sc, cid)
    assert (c.sea_stage, c.current_location_id) == ("stranded", P_A)
    _cpass(sc, sc.T + timedelta(minutes=2))
    assert (_row(sc, cid).status, _row(sc, cid).cancel_reason) == ("cancelled", "sea_route_lost")


def test_served_cargo_stays_aboard_and_unloading_waits_for_a_caravan_raid(sc):
    cid = _sea_row(sc, stage="aboard", location=DECK, run_id=32, ship_id=sc.ship_id)
    run_ship(sc, sc.T + timedelta(minutes=1))
    assert _row(sc, cid).sea_stage == "aboard"                # the route still serves 103 → 200
    _out, t = depart(sc)
    exec_(sc, "INSERT INTO econ_caravan_raids (caravan_id, leader_character_id, location_id, region_id, status, "
              "created_at) VALUES (:c, :l, :loc, 10, 'fighting', :t)", c=cid, l=ALPHA, loc=DECK, t=now())
    run_ship(sc, t + timedelta(minutes=30))                   # docked at the landing port, raid still on
    assert ship(sc).docked_port_id == P_B and _row(sc, cid).sea_stage == "aboard"
    exec_(sc, "UPDATE econ_caravan_raids SET status = 'repelled' WHERE caravan_id = :c", c=cid)
    run_ship(sc, t + timedelta(minutes=31))
    c = _row(sc, cid)
    assert (c.sea_stage, c.current_location_id) == ("landed", P_B)


# ===================================================================================================================
# raid on a deck
# ===================================================================================================================

def test_raid_on_deck_is_judged_by_the_departure_port_and_loot_skips_freight_and_sunk(sc, monkeypatch):
    before = money_total(sc)
    cid = _waiting(sc)
    _out, t = depart(sc)
    add_monster(sc, Z2, max_active=1, chance=0.0)             # a mob template for the guard pool only
    exec_(sc, "INSERT INTO econ_caravan_guard_templates (mob_template_id, created_at) VALUES (:t, :n)",
          t=MONSTER_TPL, n=now())
    place(sc, ALPHA, DECK)
    start = _db_call(sc, raids.begin_raid, cid, ALPHA, False, now=t + timedelta(minutes=2))
    region = int(q(sc, "SELECT region_id FROM econ_caravan_raids WHERE id = :r", r=start.raid_id))
    assert region == R_A                                      # «Тракт» (port of departure), not the hidden sea region

    _set_row(sc, cid, sunk_units=Decimal(10))
    _set_params(sc, caravan_raid_marks_share=1.0, caravan_raid_goods_share=0.5)
    monkeypatch.setattr(raids, "bale_item", lambda db, code: None)
    db = sc()
    try:
        raid = db.get(models.EconCaravanRaid, start.raid_id)
        car = db.get(models.EconCaravan, cid)
        raids._pay_out(db, raid, car, [ALPHA], [ALPHA], None, econ_tick.load_params(db), t + timedelta(minutes=5))
        db.commit()
    finally:
        db.close()
    c = _row(sc, cid)
    paid = c.paid_purse + c.paid_treasury
    assert c.raid_paid == paid - c.freight                    # the reserved freight is never loot
    assert Decimal(str(c.stolen_units)) == ((Decimal(str(c.units)) - 10) * Decimal("0.5")).quantize(Decimal("0.001"))
    _check(sc)
    assert money_total(sc) == before


# ===================================================================================================================
# sea monsters: cargo loss, empty deck, escorts in the fight
# ===================================================================================================================

def test_customs_landing_port_inspects_after_the_freight(sc):
    """FEAT-216 task 4: a legal caravan whose post is its landing port (``customs_index == sea_split_index + 1``)
    is unloaded, pays freight then duty in the same transaction, and stops there until ``customs_until``."""
    cid = _waiting(sc)
    _set_row(sc, cid, customs_index=2, customs_location_id=P_B, customs_state="pending")
    c = _row(sc, cid)
    _seller, duty = ec.remaining_payout(c.value, c.duty, c.paid_purse + c.paid_treasury, 0, freight=c.freight)
    assert duty > 0
    country = int(q(sc, "SELECT COALESCE(SUM(balance), 0) FROM econ_accounts WHERE kind = 'country_treasury' "
                        "AND ref_id = 2") or 0)
    _out, t = depart(sc)
    run_ship(sc, t + timedelta(minutes=30))                   # arrival at 200 → unload + freight + duty
    c = _row(sc, cid)
    assert (c.sea_stage, c.route_index, c.customs_state, c.duty_paid) == ("landed", 2, "inspecting", duty)
    assert c.freight_paid == c.freight and c.arrived_at is None
    assert c.customs_until is not None and c.next_move_at == c.customs_until
    assert op(sc, c.duty_op_id)[0] == core.OP_CARAVAN_DUTY
    assert int(q(sc, "SELECT balance FROM econ_accounts WHERE kind = 'country_treasury' AND ref_id = 2"))         == country + duty
    _check(sc)
    _cpass(sc, c.customs_until + timedelta(minutes=1))       # cleared → 210 → delivered
    c = _row(sc, cid)
    assert (c.status, c.customs_state) == ("delivered", "cleared")
    assert crud.escrow_balance(sc()) == 0


def _attack_rows(f, caravan_id, key="1:1:1:502:1"):
    add_monster(f, Z2)
    ids = []
    db = f()
    try:
        for n, battle in enumerate((901, 902)):
            r = models.SeaRaid(ship_id=f.ship_id, attack_key=key, group_no=n, deck_location_id=DECK, zone_id=Z2,
                               mob_template_id=MONSTER_TPL, monster_name="Кракен", player_ids=[ALPHA + n],
                               battle_id=battle, status="fighting", mobs_despawned=True, created_at=now(),
                               started_at=now(), caravan_ids=[caravan_id])
            db.add(r)
            db.flush()
            ids.append(int(r.id))
        db.commit()
    finally:
        db.close()
    return ids


def test_monster_loss_two_groups_one_lost_takes_half_the_share_once(sc, client):
    cid = _sea_row(sc, stage="aboard", location=DECK, run_id=41, ship_id=sc.ship_id, units=100)
    won, lost = _attack_rows(sc, cid)
    r = client.post(RESULT, json={"battle_id": 901, "sea_raid_id": won, "winner_team": 0}, headers=INTERNAL)
    assert r.status_code == 200 and r.json() == {"status": "won"}
    assert Decimal(str(_row(sc, cid).sunk_units)) == 0       # one group still fights: pending
    r = client.post(RESULT, json={"battle_id": 902, "sea_raid_id": lost, "winner_team": 1}, headers=INTERNAL)
    assert r.json() == {"status": "lost"}
    assert Decimal(str(_row(sc, cid).sunk_units)) == Decimal("12.5")    # 100 × 25 % × 1/2
    ((units, lost_groups, decided),) = rows(sc, "SELECT units_lost, lost_groups, decided_groups "
                                                 "FROM econ_caravan_sea_losses WHERE caravan_id = :c", c=cid)
    assert (Decimal(str(units)), lost_groups, decided) == (Decimal("12.5"), 1, 2)
    assert int(q(sc, "SELECT COUNT(*) FROM sea_raids WHERE cargo_settled_at IS NULL")) == 0
    db = sc()
    try:
        assert sea_raid_crud.apply_cargo_loss(db, "1:1:1:502:1").status == sea_raid_crud.CARGO_ALREADY
    finally:
        db.close()
    assert sea_raid_crud.cargo_followups(sc, now()) == 0
    assert Decimal(str(_row(sc, cid).sunk_units)) == Decimal("12.5")
    assert int(q(sc, "SELECT COUNT(*) FROM econ_caravan_sea_losses")) == 1


def test_empty_deck_means_no_attack_and_no_loss(sc):
    cid = _sea_row(sc, stage="aboard", location=DECK, run_id=51, ship_id=sc.ship_id)
    add_monster(sc, Z2)
    _out, t = depart(sc)
    out = run_ship(sc, t + timedelta(minutes=10))
    assert sea_pass.EV_RAID_REPELLED in out.events and sea_raids(sc) == []
    assert Decimal(str(_row(sc, cid).sunk_units)) == 0 and _row(sc, cid).sea_stage == "aboard"


def test_escort_fights_sea_monsters_other_locks_still_skip(sc):
    cid = _sea_row(sc, stage="aboard", location=DECK, run_id=61, ship_id=sc.ship_id)
    _escort(sc, cid, GAMMA, location=DECK)
    add_monster(sc, Z2)
    _out, t = depart(sc)
    assert loc(sc, GAMMA) == DECK                             # already aboard: not put ashore at departure
    place(sc, BETA, DECK)
    exec_(sc, "UPDATE characters SET unconscious_until = :u WHERE id = :c", u=now() + timedelta(hours=1), c=BETA)
    run_ship(sc, t + timedelta(minutes=10))
    (r,) = sea_raids(sc)
    assert r.player_ids == [GAMMA] and r.caravan_ids == [cid]
    assert sc.bs.calls[0]["players"] == [GAMMA]


# ===================================================================================================================
# admin: ship cargo_capacity, caravans kind=sea
# ===================================================================================================================

def test_ship_admin_cargo_capacity_default_range_and_update(sc, client):
    as_user(1, "admin", SHIP_PERMS)
    body = dict(name="Чайка", deck_location_id=601, captain_npc_id=71, capacity=4, crew_slots=1,
                boarding_minutes=20, zone_minutes=5, fare_base=3, fare_per_zone=2,
                stops=[{"port_location_id": P_B}, {"port_location_id": P_A}])
    for bad in (-1, 21):
        assert client.post(SHIPS, json={**body, "cargo_capacity": bad}).status_code == 422
    r = client.post(SHIPS, json=body)
    assert r.status_code in (200, 201), r.text
    new = r.json()
    assert new["cargo_capacity"] == 2 and new["cargo_aboard"] == 0
    assert client.patch(f"{SHIPS}/{new['id']}", json={"cargo_capacity": 21}).status_code == 422
    r = client.patch(f"{SHIPS}/{new['id']}", json={"cargo_capacity": 0})
    assert r.status_code == 200, r.text
    assert int(q(sc, "SELECT cargo_capacity FROM sea_ships WHERE id = :s", s=new["id"])) == 0
    _sea_row(sc, stage="aboard", location=DECK, run_id=71, ship_id=sc.ship_id)
    listed = {s["id"]: s for s in client.get(SHIPS).json()}
    assert listed[sc.ship_id]["cargo_aboard"] == 1


def test_admin_caravans_kind_sea_and_sea_fields(sc, client):
    as_user(1, "admin", ECON_READ)
    cid = _waiting(sc)
    _sea_row(sc, stage=None, location=GATE_A, run_id=81)               # a land-like row (no sea ports)
    exec_(sc, "UPDATE econ_caravans SET sea_board_port_id = NULL, sea_alight_port_id = NULL, sea_split_index = NULL "
              "WHERE dispatch_run_id = 81")
    body = client.get(CARAVANS, params={"kind": "sea"}).json()
    assert body["total"] == 1
    (item,) = body["items"]
    c = _row(sc, cid)
    assert item["id"] == cid and item["sea_stage"] == "waiting" and item["sea_split_index"] == 1
    assert (item["sea_board_port_name"], item["sea_alight_port_name"]) == ("Тракт", "Оазис")
    assert item["freight"] == c.freight and item["freight_paid"] == 0 and item["sunk_units"] == 0
    assert item["sea_wait_deadline"] is not None
    detail = client.get(f"{CARAVANS}/{cid}").json()
    assert detail["sea_losses"] == [] and detail["sea_stage"] == "waiting"
