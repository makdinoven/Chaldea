"""FEAT-192 QA (#9): the caravan pass of the economy tick (``econ_tick._caravan_pass`` + ``economy_caravan_crud``)
on SQLite.

Harness of ``test_econ_tick.py`` (``factory``: migration-028 seed, countries 1 «Мидденгерд» and 2 «Пустошь»). The
``econ_caravans`` / ``econ_trade_pairs`` tables come from the character-service metadata (columns of migration 035).

Most tests drive ``_caravan_pass`` directly with explicit run ids (the pass only compares run ids, it needs no
``econ_tick_runs`` row), so stocks are not touched by region steps in between; a few run the whole ``run_tick``.
Every goods row starts at its norm (no caravans) and each test opens exactly the surplus / deficit it needs.
After every step: world sum 0, nothing negative, escrow balance == Σ paid of caravans in transit,
no tax / source legs on caravan operations (the summary invariant itself: test_econ_caravan_api.py).
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

import econ_core as core
import econ_ledger
import econ_tick
import economy_caravan_crud as crud
import models
from tests.test_econ_tick import (  # noqa: F401  (factory is a fixture)
    SOURCE, T0, _add_region, _assert_ledger_closes, _balance, _rows, _scalar, factory,
)
from tests.test_econ_tick_events import _seed_templates, _start, calendar  # noqa: F401  (calendar: autouse)

CARAVAN_OPS = ("caravan_dispatch", "caravan_delivery", "caravan_cancel")
PURSE = 10_000          # 25 % -> 2 500 marks per run for caravans


# --------------------------------------------------------------------------------------------- helpers

def _exec(f, sql, **params):
    db = f()
    try:
        db.execute(text(sql), params)
        db.commit()
    finally:
        db.close()


def _set_params(f, **values):
    db = f()
    try:
        row = db.get(models.EconSimSettings, 1)
        params = dict(row.params)
        params.update(values)
        row.params = params
        db.commit()
    finally:
        db.close()


def _params(f):
    db = f()
    try:
        return econ_tick.load_params(db)
    finally:
        db.close()


def _groups(f):
    db = f()
    try:
        return econ_tick.load_groups(db)
    finally:
        db.close()


def _region(f, rid, *, country=1, purse=PURSE, template="rural"):
    _add_region(f, rid, template=template, country_id=country, purse=purse)
    _exec(f, "UPDATE econ_region_goods SET stock = norm_stock, price_mult = 1 WHERE region_id = :r", r=rid)


def _good(f, rid, group, stock, norm, mult=1.0):
    _exec(f, "UPDATE econ_region_goods SET stock = :s, norm_stock = :n, price_mult = :m "
             "WHERE region_id = :r AND group_code = :g", s=stock, n=norm, m=mult, r=rid, g=group)


def _stock(f, rid, group):
    value = _scalar(f, "SELECT stock FROM econ_region_goods WHERE region_id = :r AND group_code = :g", r=rid, g=group)
    return None if value is None else Decimal(str(value)).quantize(Decimal("0.001"))


def _fund(f, ref, amount):
    db = f()
    try:
        econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION, source_service=SOURCE, comment="тест",
                                   legs=[core.Leg(core.AccountRef.emission(), ref, amount)])
        db.commit()
    finally:
        db.close()


def _pair(f, a, b, *, enabled=True, duty=10.0):
    a, b = min(a, b), max(a, b)
    db = f()
    try:
        row = db.get(models.EconTradePair, (a, b)) or models.EconTradePair(country_a=a, country_b=b)
        row.is_enabled = enabled
        row.duty_pct = Decimal(str(duty))
        db.merge(row)
        db.commit()
    finally:
        db.close()


def _summary(run_id):
    return econ_tick.RunSummary(run_id=run_id, trigger="manual", slot=None, status="running")


def _pass(f, run_id, *, active_map=None, now=None, check=True):
    summary = _summary(run_id)
    econ_tick._caravan_pass(f, run_id, summary, _params(f), now or T0 + timedelta(hours=6 * run_id), _groups(f),
                            active_map or {})
    if check:
        _check(f)
    return summary


def _caravans(f):
    return [dict(zip(("id", "status", "from", "to", "group", "units", "value", "duty", "duty_pct", "paid_purse",
                      "paid_treasury", "travel_runs", "runs_left", "last_run_id", "dispatch_run_id",
                      "finished_run_id", "cancel_reason", "goods_returned", "dispatch_op_id", "finish_op_id",
                      "from_country", "to_country"), r))
            for r in _rows(f, "SELECT id, status, from_region_id, to_region_id, group_code, units, value, duty, "
                              "duty_pct, paid_purse, paid_treasury, travel_runs, runs_left, last_run_id, "
                              "dispatch_run_id, finished_run_id, cancel_reason, goods_returned, dispatch_op_id, "
                              "finish_op_id, from_country_id, to_country_id FROM econ_caravans ORDER BY id")]


def _ops(f, op_type=None):
    sql = "SELECT id, op_type, idempotency_key, region_id FROM econ_operations WHERE op_type IN " \
          "('caravan_dispatch', 'caravan_delivery', 'caravan_cancel')"
    if op_type:
        sql += f" AND op_type = '{op_type}'"
    return _rows(f, sql + " ORDER BY id")


def _legs(f, op_id):
    """[(from kind, from ref, to kind, to ref, amount, leg_type)]"""
    return _rows(f, "SELECT a1.kind, a1.ref_id, a2.kind, a2.ref_id, l.amount, l.leg_type FROM econ_postings l "
                    "JOIN econ_accounts a1 ON a1.id = l.from_account_id "
                    "JOIN econ_accounts a2 ON a2.id = l.to_account_id WHERE l.operation_id = :i ORDER BY l.id",
                 i=op_id)


def _escrow(f):
    return _balance(f, "caravan_escrow", 0)


def _check(f):
    """World sum 0, nothing negative, escrow == Σ paid of in-transit caravans, no tax / source legs."""
    _assert_ledger_closes(f)
    expected = int(_scalar(f, "SELECT COALESCE(SUM(paid_purse + paid_treasury), 0) FROM econ_caravans "
                              "WHERE status = 'in_transit'"))
    assert _escrow(f) == expected
    assert _scalar(f, "SELECT COUNT(*) FROM econ_postings l JOIN econ_operations o ON o.id = l.operation_id "
                      "WHERE o.op_type IN ('caravan_dispatch', 'caravan_delivery', 'caravan_cancel') "
                      "AND l.leg_type <> 'main'") == 0
    assert _scalar(f, "SELECT COUNT(*) FROM econ_postings l JOIN econ_operations o ON o.id = l.operation_id "
                      "JOIN econ_accounts a ON a.id = l.from_account_id WHERE o.op_type IN "
                      "('caravan_dispatch', 'caravan_delivery', 'caravan_cancel') "
                      "AND a.kind IN ('emission', 'adjustment')") == 0
    db = f()
    try:
        assert crud.escrow_expected(db) == expected == crud.escrow_balance(db)
    finally:
        db.close()


def _two_regions(f, *, seller_country=1, buyer_country=1, buyer_purse=PURSE):
    """Seller 1 food 1000 / norm 200 (supply 200), buyer 2 food 100 / norm 300 (need 200), price 2 x 1."""
    _region(f, 1, country=seller_country)
    _region(f, 2, country=buyer_country, purse=buyer_purse)
    _good(f, 1, "food", 1000, 200)
    _good(f, 2, "food", 100, 300)


# --------------------------------------------------------------------------------------------- happy paths

def test_domestic_caravan_dispatched_then_delivered_next_run(factory):
    _two_regions(factory)
    seller_purse, buyer_purse = _balance(factory, "population_purse", 1), _balance(factory, "population_purse", 2)

    s1 = _pass(factory, 1)
    assert (s1.caravans_dispatched, s1.caravan_value, s1.caravans_delivered, s1.caravans_failed) == (1, 400, 0, 0)
    [c] = _caravans(factory)
    assert (c["status"], c["from"], c["to"], c["group"], Decimal(str(c["units"]))) == \
        ("in_transit", 1, 2, "food", Decimal("200"))
    assert (c["value"], c["duty"], c["paid_purse"], c["paid_treasury"]) == (400, 0, 400, 0)
    assert (c["travel_runs"], c["runs_left"], c["last_run_id"], c["dispatch_run_id"]) == (1, 1, 1, 1)
    assert (c["from_country"], c["to_country"]) == (1, 1)
    assert _stock(factory, 1, "food") == Decimal("800") and _stock(factory, 2, "food") == Decimal("100")
    assert _balance(factory, "population_purse", 2) == buyer_purse - 400
    assert _escrow(factory) == 400
    [(op_id, op_type, key, region)] = _ops(factory)
    assert (op_type, key, region, c["dispatch_op_id"]) == ("caravan_dispatch", f"caravan:c{c['id']}:pay", 2, op_id)
    assert _legs(factory, op_id) == [("population_purse", 2, "caravan_escrow", 0, 400, "main")]

    s2 = _pass(factory, 2)
    assert (s2.caravans_delivered, s2.caravans_dispatched, s2.caravans_cancelled) == (1, 0, 0)
    [c] = _caravans(factory)
    assert (c["status"], c["runs_left"], c["finished_run_id"], c["cancel_reason"]) == ("delivered", 0, 2, None)
    assert _stock(factory, 2, "food") == Decimal("300") and _stock(factory, 1, "food") == Decimal("800")
    assert _balance(factory, "population_purse", 1) == seller_purse + 400
    assert _escrow(factory) == 0
    done = _ops(factory, "caravan_delivery")
    assert [(k, r) for _i, _t, k, r in done] == [(f"caravan:c{c['id']}:done", 2)]
    assert c["finish_op_id"] == done[0][0]
    assert _legs(factory, done[0][0]) == [("caravan_escrow", 0, "population_purse", 1, 400, "main")]


def test_foreign_caravan_takes_two_runs_and_pays_duty_to_the_buyer_country(factory):
    _two_regions(factory, seller_country=2)
    _pair(factory, 2, 1, duty=10)
    country_before = _balance(factory, "country_treasury", 1)

    assert _pass(factory, 1).caravans_dispatched == 1
    [c] = _caravans(factory)
    assert (c["travel_runs"], c["runs_left"], c["value"], c["duty"], float(c["duty_pct"])) == (2, 2, 400, 40, 10.0)
    assert c["paid_purse"] == 440 and _escrow(factory) == 440

    s2 = _pass(factory, 2)
    assert (s2.caravans_delivered, s2.caravans_dispatched) == (0, 0)
    [c] = _caravans(factory)
    assert (c["status"], c["runs_left"], c["last_run_id"]) == ("in_transit", 1, 2)
    assert _stock(factory, 2, "food") == Decimal("100")

    s3 = _pass(factory, 3)
    assert s3.caravans_delivered == 1
    [c] = _caravans(factory)
    assert (c["status"], c["finished_run_id"]) == ("delivered", 3)
    assert _stock(factory, 2, "food") == Decimal("300")
    assert _balance(factory, "country_treasury", 1) == country_before + 40
    [(op_id, *_)] = _ops(factory, "caravan_delivery")
    assert sorted(_legs(factory, op_id)) == sorted([("caravan_escrow", 0, "population_purse", 1, 400, "main"),
                                                    ("caravan_escrow", 0, "country_treasury", 1, 40, "main")])


def test_travel_params_change_the_trip_length(factory):
    _two_regions(factory)
    _set_params(factory, caravan_travel_domestic=3)
    _pass(factory, 1)
    assert [(c["travel_runs"], c["runs_left"]) for c in _caravans(factory)] == [(3, 3)]
    _pass(factory, 2)
    _pass(factory, 3)
    assert _caravans(factory)[0]["status"] == "in_transit"
    _pass(factory, 4)
    assert _caravans(factory)[0]["status"] == "delivered"


def test_forbidden_or_disabled_pair_sends_nothing(factory):
    _two_regions(factory, seller_country=2)
    assert _pass(factory, 1).caravans_dispatched == 0                  # no row = forbidden
    _pair(factory, 1, 2, enabled=False)
    assert _pass(factory, 2).caravans_dispatched == 0                  # row switched off
    assert _caravans(factory) == [] and _ops(factory) == []
    assert _stock(factory, 1, "food") == Decimal("1000")


def test_food_is_topped_up_from_the_buyer_treasury_without_tax(factory):
    _two_regions(factory, buyer_purse=200)                             # 25 % -> 50 marks
    _fund(factory, core.AccountRef.region(2), 1000)                    # 50 % -> 500 marks for food
    treasury_before = _balance(factory, "region_treasury", 2)
    country_before = _balance(factory, "country_treasury", 1)

    _pass(factory, 1)
    [c] = _caravans(factory)
    assert (c["value"], c["paid_purse"], c["paid_treasury"]) == (400, 50, 350)
    [(op_id, *_)] = _ops(factory, "caravan_dispatch")
    assert sorted(_legs(factory, op_id)) == sorted([("population_purse", 2, "caravan_escrow", 0, 50, "main"),
                                                    ("region_treasury", 2, "caravan_escrow", 0, 350, "main")])
    assert _balance(factory, "region_treasury", 2) == treasury_before - 350
    assert _balance(factory, "country_treasury", 1) == country_before     # no tax leg anywhere


def test_non_food_is_never_paid_from_the_treasury(factory):
    _region(factory, 1)
    _region(factory, 2, purse=400)                                     # 100 marks
    _fund(factory, core.AccountRef.region(2), 1_000_000)
    _good(factory, 1, "ore_metal", 1000, 200)
    _good(factory, 2, "ore_metal", 0, 300)
    _pass(factory, 1)
    [c] = _caravans(factory)
    assert (c["group"], c["value"], c["paid_purse"], c["paid_treasury"]) == ("ore_metal", 100, 100, 0)
    assert Decimal(str(c["units"])) == Decimal("10")


def test_cannot_pay_ships_partial_units(factory):
    _two_regions(factory, buyer_purse=100)                             # 25 marks, price 2
    _pass(factory, 1)
    [c] = _caravans(factory)
    assert (Decimal(str(c["units"])), c["value"]) == (Decimal("12.5"), 25)
    assert _stock(factory, 1, "food") == Decimal("987.5")


def test_empty_purse_sends_nothing(factory):
    _two_regions(factory, buyer_purse=0)
    assert _pass(factory, 1).caravans_dispatched == 0


def test_seller_keeps_its_norm_and_buyer_not_above_norm_over_many_runs(factory):
    _region(factory, 1)
    _region(factory, 2)
    _region(factory, 3)
    _good(factory, 1, "food", 600, 200)
    _good(factory, 2, "food", 0, 500)
    _good(factory, 3, "food", 0, 500)
    for run in range(1, 9):
        _pass(factory, run)
        assert _stock(factory, 1, "food") >= Decimal("200")
        for rid in (2, 3):
            inbound = Decimal(str(_scalar(factory, "SELECT COALESCE(SUM(units), 0) FROM econ_caravans WHERE "
                                                   "status = 'in_transit' AND to_region_id = :r", r=rid)))
            assert _stock(factory, rid, "food") + inbound <= Decimal("500")
    total_moved = sum(Decimal(str(c["units"])) for c in _caravans(factory) if c["status"] == "delivered")
    assert _stock(factory, 1, "food") == Decimal("600") - total_moved - sum(
        Decimal(str(c["units"])) for c in _caravans(factory) if c["status"] == "in_transit")


def test_caravans_disabled_stops_dispatch_but_arrivals_continue(factory):
    _two_regions(factory)
    _pass(factory, 1)
    _set_params(factory, caravans_enabled=0)
    _good(factory, 2, "ore_metal", 0, 300)
    _good(factory, 1, "ore_metal", 1000, 200)
    s2 = _pass(factory, 2)
    assert (s2.caravans_delivered, s2.caravans_dispatched) == (1, 0)
    assert [c["status"] for c in _caravans(factory)] == ["delivered"]


# --------------------------------------------------------------------------------------------- idempotency

def test_rerun_of_the_same_run_moves_nothing_twice(factory):
    _two_regions(factory, seller_country=2)
    _pair(factory, 1, 2)
    _pass(factory, 1)
    again = _pass(factory, 1)                                          # resumed run 1: nothing new
    assert (again.caravans_dispatched, again.caravans_delivered, again.caravans_failed) == (0, 0, 0)
    assert len(_caravans(factory)) == 1 and len(_ops(factory)) == 1

    _pass(factory, 2)
    _pass(factory, 2)                                                  # no double decrement
    assert [(c["runs_left"], c["last_run_id"]) for c in _caravans(factory)] == [(1, 2)]

    assert _pass(factory, 3).caravans_delivered == 1
    assert _pass(factory, 3).caravans_delivered == 0                   # no double delivery
    assert _stock(factory, 2, "food") == Decimal("300")
    assert len(_ops(factory, "caravan_delivery")) == 1


def test_same_plan_dispatched_twice_in_one_run_is_already(factory):
    _two_regions(factory)
    db = factory()
    try:
        snap = crud.load_snapshot(db, 1, _params(factory), _groups(factory), {})
    finally:
        db.close()
    import econ_caravan
    [plan] = econ_caravan.plan_caravans(snap.markets, _groups(factory), snap.inbound, snap.pairs, _params(factory))
    first = crud.dispatch_tx(factory, plan, run_id=1, params=_params(factory), now=T0)
    second = crud.dispatch_tx(factory, plan, run_id=1, params=_params(factory), now=T0)
    assert (first.status, second.status) == ("sent", "already")
    assert len(_caravans(factory)) == 1 and _stock(factory, 1, "food") == Decimal("800")
    _check(factory)


def test_finish_twice_is_already(factory):
    _two_regions(factory)
    _pass(factory, 1)
    _pass(factory, 2)
    cid = _caravans(factory)[0]["id"]
    db = factory()
    try:
        assert crud.finish(db, cid, run_id=2, now=T0).status == "already"
        assert crud.finish(db, cid, run_id=3, now=T0).status == "already"
        assert crud.advance(db, cid, run_id=3).status == "already"
        db.rollback()
    finally:
        db.close()


def test_regions_already_ticked_in_this_run_do_not_dispatch(factory):
    _two_regions(factory)
    _exec(factory, "UPDATE econ_regions SET last_run_id = 1 WHERE region_id = 1")
    assert _pass(factory, 1).caravans_dispatched == 0
    _exec(factory, "UPDATE econ_regions SET last_run_id = 2 WHERE region_id = 2")
    assert _pass(factory, 2).caravans_dispatched == 0
    assert _pass(factory, 3).caravans_dispatched == 1


@pytest.mark.parametrize("ticked_region", [1, 2])
def test_arrival_postponed_when_a_region_already_ticked(factory, ticked_region):
    _two_regions(factory)
    _pass(factory, 1)
    _exec(factory, "UPDATE econ_regions SET last_run_id = 2 WHERE region_id = :r", r=ticked_region)
    s2 = _pass(factory, 2)
    assert (s2.caravans_delivered, s2.caravans_failed) == (0, 0)
    [c] = _caravans(factory)
    assert (c["status"], c["runs_left"], c["last_run_id"]) == ("in_transit", 0, 2)
    assert _stock(factory, 2, "food") == Decimal("100") and _escrow(factory) == 400
    _pass(factory, 2)                                                  # still postponed within run 2
    assert _caravans(factory)[0]["status"] == "in_transit"
    s3 = _pass(factory, 3)
    assert s3.caravans_delivered == 1
    [c] = _caravans(factory)
    assert (c["status"], c["finished_run_id"]) == ("delivered", 3)
    assert _stock(factory, 2, "food") == Decimal("300")


def test_resumed_run_tick_does_not_double_dispatch(factory, monkeypatch):
    _two_regions(factory)
    original = econ_tick._process_region
    calls = {"n": 0}

    def crashing(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt("simulated process death")
        return original(*args, **kwargs)

    monkeypatch.setattr(econ_tick, "_process_region", crashing)
    with pytest.raises(KeyboardInterrupt):
        econ_tick.run_tick(factory, now=T0)
    food = [c for c in _caravans(factory) if c["group"] == "food"]
    assert len(food) == 1 and food[0]["status"] == "in_transit"
    caravans_before, ops_before = len(_caravans(factory)), len(_ops(factory))
    _check(factory)

    monkeypatch.setattr(econ_tick, "_process_region", original)
    resumed = econ_tick.run_tick(factory, now=T0 + timedelta(minutes=15))
    assert resumed is not None and resumed.resumed
    assert resumed.caravans_delivered == 0 and resumed.caravans_failed == 0
    assert len(_caravans(factory)) == caravans_before and len(_ops(factory)) == ops_before
    assert _caravans(factory)[0]["runs_left"] == 1
    _check(factory)

    nxt = econ_tick.run_tick(factory, now=T0 + timedelta(hours=6))
    assert nxt.caravans_delivered >= 1
    assert _caravans(factory)[0]["status"] == "delivered"
    _check(factory)


# --------------------------------------------------------------------------------------------- full runs

def test_manual_runs_move_caravans(factory):
    _two_regions(factory)
    first = econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert first.caravans_dispatched >= 1 and first.status == "done" and first.caravans_failed == 0
    food = [c for c in _caravans(factory) if c["group"] == "food"]
    assert [(c["from"], c["to"], c["dispatch_run_id"]) for c in food] == [(1, 2, first.run_id)]
    _check(factory)
    second = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=30))
    assert second.caravans_delivered >= 1
    food = [c for c in _caravans(factory) if c["group"] == "food" and c["dispatch_run_id"] == first.run_id]
    assert food[0]["status"] == "delivered" and food[0]["finished_run_id"] == second.run_id
    run_error = _scalar(factory, "SELECT error FROM econ_tick_runs WHERE id = :i", i=second.run_id)
    assert run_error is None
    _check(factory)


def test_run_without_caravan_tables_still_ticks(factory):
    _two_regions(factory)
    _exec(factory, "DROP TABLE econ_caravans")
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert summary.status == "done" and summary.regions_done == 2
    assert (summary.caravans_dispatched, summary.caravans_failed) == (0, 0)


# --------------------------------------------------------------------------------------------- events

@pytest.mark.parametrize("effects", [[{"type": "merchants_halt"}],
                                     [{"type": "stock_loss", "group": "food", "share": 0.1},
                                      {"type": "merchants_halt"}]])
def test_halted_region_stops_exports_only(factory, effects):
    _two_regions(factory)
    assert _pass(factory, 1, active_map={1: [effects]}).caravans_dispatched == 0
    # the halted region still imports
    _good(factory, 1, "food", 0, 300)
    _good(factory, 2, "food", 1000, 200)
    s = _pass(factory, 2, active_map={1: [effects]})
    assert s.caravans_dispatched == 1
    assert [(c["from"], c["to"]) for c in _caravans(factory)] == [(2, 1)]


def test_caravan_on_the_road_arrives_although_its_origin_is_halted(factory):
    _two_regions(factory)
    _pass(factory, 1)
    s = _pass(factory, 2, active_map={1: [[{"type": "merchants_halt"}]], 2: [[{"type": "merchants_halt"}]]})
    assert s.caravans_delivered == 1


def test_other_event_effects_do_not_halt(factory):
    _two_regions(factory)
    assert _pass(factory, 1, active_map={1: [[{"type": "price", "group": "food", "mult": 0.9}]]}) \
        .caravans_dispatched == 1


@pytest.mark.parametrize("code", ["raid", "riot"])
def test_raid_and_riot_events_stop_exports_in_a_real_run(factory, code):
    _seed_templates(factory, only={code})
    _two_regions(factory)
    _start(factory, code, 1)
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=1))
    assert summary.status == "done"
    assert [c for c in _caravans(factory) if c["from"] == 1] == []
    _check(factory)


# --------------------------------------------------------------------------------------------- pair changes

def test_pair_disabled_mid_transit_still_delivers_with_stored_duty(factory):
    _two_regions(factory, seller_country=2)
    _pair(factory, 1, 2, duty=10)
    _pass(factory, 1)
    _pair(factory, 1, 2, enabled=False, duty=50)
    country_before = _balance(factory, "country_treasury", 1)
    _pass(factory, 2)
    s3 = _pass(factory, 3)
    assert s3.caravans_delivered == 1 and s3.caravans_dispatched == 0
    [c] = _caravans(factory)
    assert (c["status"], c["duty"]) == ("delivered", 40)
    assert _balance(factory, "country_treasury", 1) == country_before + 40


def test_new_duty_applies_to_new_dispatches_only(factory):
    _two_regions(factory, seller_country=2)
    _pair(factory, 1, 2, duty=10)
    _pass(factory, 1)
    _pair(factory, 1, 2, duty=20)
    _good(factory, 1, "ore_metal", 1000, 200)
    _good(factory, 2, "ore_metal", 0, 100)
    _pass(factory, 2)
    rows = _caravans(factory)
    assert [(r["group"], float(r["duty_pct"])) for r in rows] == [("food", 10.0), ("ore_metal", 20.0)]


# --------------------------------------------------------------------------------------------- cancels / fallbacks

def test_destination_left_the_simulation_cancels_with_goods_back_and_full_refund(factory):
    _two_regions(factory)
    _fund(factory, core.AccountRef.region(2), 1000)
    _pass(factory, 1)
    [c] = _caravans(factory)
    purse, treasury = _balance(factory, "population_purse", 2), _balance(factory, "region_treasury", 2)
    _exec(factory, "UPDATE econ_regions SET template_code = NULL WHERE region_id = 2")
    s = _pass(factory, 2)
    assert (s.caravans_cancelled, s.caravans_delivered) == (1, 0)
    [c] = _caravans(factory)
    assert (c["status"], c["cancel_reason"], bool(c["goods_returned"]), c["finished_run_id"]) == \
        ("cancelled", "destination_left", True, 2)
    assert _stock(factory, 1, "food") == Decimal("1000") and _stock(factory, 2, "food") == Decimal("100")
    assert _balance(factory, "population_purse", 2) == purse + c["paid_purse"]
    assert _balance(factory, "region_treasury", 2) == treasury + c["paid_treasury"]
    [(op_id, _t, key, _r)] = _ops(factory, "caravan_cancel")
    assert key == f"caravan:c{c['id']}:back" and c["finish_op_id"] == op_id
    assert all(leg[0] == "caravan_escrow" and leg[2] in ("population_purse", "region_treasury")
               for leg in _legs(factory, op_id))


def test_cancel_refunds_the_treasury_part_without_tax(factory):
    _two_regions(factory, buyer_purse=200)
    _fund(factory, core.AccountRef.region(2), 1000)
    _pass(factory, 1)
    [c] = _caravans(factory)
    assert c["paid_treasury"] > 0
    country_before = _balance(factory, "country_treasury", 1)
    _exec(factory, "UPDATE econ_regions SET population = 0 WHERE region_id = 2")
    _pass(factory, 2)
    [(op_id, *_)] = _ops(factory, "caravan_cancel")
    assert sorted(_legs(factory, op_id)) == sorted([
        ("caravan_escrow", 0, "population_purse", 2, c["paid_purse"], "main"),
        ("caravan_escrow", 0, "region_treasury", 2, c["paid_treasury"], "main")])
    assert _balance(factory, "country_treasury", 1) == country_before


def test_destination_deleted_refunds_its_country_and_returns_goods(factory):
    _two_regions(factory)
    _pass(factory, 1)
    [c] = _caravans(factory)
    country_before = _balance(factory, "country_treasury", 1)
    _exec(factory, "DELETE FROM Regions WHERE id = 2")
    s = _pass(factory, 2)
    assert s.caravans_cancelled == 1
    [c] = _caravans(factory)
    assert (c["status"], c["cancel_reason"], bool(c["goods_returned"])) == ("cancelled", "destination_deleted", True)
    assert _stock(factory, 1, "food") == Decimal("1000")
    assert _balance(factory, "country_treasury", 1) == country_before + 400


def test_destination_deleted_refunds_purse_and_treasury_parts_to_its_country(factory):
    """Both refund legs land on the same country treasury (purse part + food treasury part)."""
    _two_regions(factory, buyer_purse=200)
    _fund(factory, core.AccountRef.region(2), 1000)
    _pass(factory, 1)
    [c] = _caravans(factory)
    assert c["paid_purse"] > 0 and c["paid_treasury"] > 0
    country_before = _balance(factory, "country_treasury", 1)
    _exec(factory, "DELETE FROM Regions WHERE id = 2")
    assert _pass(factory, 2).caravans_cancelled == 1
    assert _balance(factory, "country_treasury", 1) == country_before + c["paid_purse"] + c["paid_treasury"]
    [(op_id, *_)] = _ops(factory, "caravan_cancel")
    assert sum(leg[4] for leg in _legs(factory, op_id) if leg[2] == "country_treasury" and leg[3] == 1) ==         c["paid_purse"] + c["paid_treasury"]


def test_destination_and_its_country_deleted_refund_the_world_treasury(factory):
    _two_regions(factory, buyer_country=2)
    _pair(factory, 1, 2, duty=0)
    _pass(factory, 1)
    world_before = _balance(factory, "world_treasury", 0)
    _exec(factory, "DELETE FROM Regions WHERE id = 2")
    _exec(factory, "DELETE FROM Countries WHERE id = 2")
    _pass(factory, 2)
    _pass(factory, 3)
    [c] = _caravans(factory)
    assert (c["status"], c["cancel_reason"]) == ("cancelled", "destination_deleted")
    assert _balance(factory, "world_treasury", 0) == world_before + 400


def test_destination_deleted_and_purged_by_a_real_run(factory):
    _two_regions(factory)
    first = econ_tick.run_tick(factory, trigger="manual", now=T0)
    food = [c for c in _caravans(factory) if c["group"] == "food"]
    assert len(food) == 1
    _exec(factory, "DELETE FROM Regions WHERE id = 2")
    second = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=30))
    assert second.caravans_cancelled >= 1 and second.run_id != first.run_id
    assert _scalar(factory, "SELECT COUNT(*) FROM econ_regions WHERE region_id = 2") == 0     # purged
    c = next(c for c in _caravans(factory) if c["id"] == food[0]["id"])
    assert (c["status"], c["cancel_reason"], bool(c["goods_returned"])) == ("cancelled", "destination_deleted", True)
    _check(factory)


def test_origin_deleted_still_delivers_and_pays_the_seller_country(factory):
    _two_regions(factory, seller_country=2)
    _pair(factory, 1, 2, duty=10)
    _pass(factory, 1)
    seller_country_before = _balance(factory, "country_treasury", 2)
    buyer_country_before = _balance(factory, "country_treasury", 1)
    _exec(factory, "DELETE FROM Regions WHERE id = 1")
    _pass(factory, 2)
    s = _pass(factory, 3)
    assert s.caravans_delivered == 1
    assert _stock(factory, 2, "food") == Decimal("300")
    assert _balance(factory, "country_treasury", 2) == seller_country_before + 400
    assert _balance(factory, "country_treasury", 1) == buyer_country_before + 40


def test_origin_deleted_and_purged_still_delivers(factory):
    _two_regions(factory)
    _pass(factory, 1)
    db = factory()
    try:
        _exec(factory, "DELETE FROM Regions WHERE id = 1")
        econ_tick.purge_orphans(db)
        db.commit()
    finally:
        db.close()
    country_before = _balance(factory, "country_treasury", 1)
    assert _pass(factory, 2).caravans_delivered == 1
    assert _balance(factory, "country_treasury", 1) == country_before + 400


def test_both_regions_gone_writes_the_goods_off_and_refunds(factory):
    _two_regions(factory)
    _pass(factory, 1)
    country_before = _balance(factory, "country_treasury", 1)
    _exec(factory, "DELETE FROM Regions WHERE id IN (1, 2)")
    s = _pass(factory, 2)
    assert s.caravans_cancelled == 1
    [c] = _caravans(factory)
    assert (c["status"], c["cancel_reason"], c["goods_returned"]) == ("cancelled", "destination_deleted", 0)
    assert _stock(factory, 1, "food") == Decimal("800")                 # econ row left over: not refilled
    assert _balance(factory, "country_treasury", 1) == country_before + 400


# --------------------------------------------------------------------------------------------- failures

def test_one_failing_dispatch_does_not_stop_the_others(factory, monkeypatch):
    _region(factory, 1)
    _region(factory, 2)
    _region(factory, 3)
    _good(factory, 1, "food", 5000, 200)
    _good(factory, 2, "food", 0, 300)
    _good(factory, 3, "food", 0, 300)
    original = crud.dispatch

    def flaky(db, plan, **kw):
        if plan.to_region_id == 2:
            raise RuntimeError("boom")
        return original(db, plan, **kw)

    monkeypatch.setattr(crud, "dispatch", flaky)
    s = _pass(factory, 1)
    assert (s.caravans_dispatched, s.caravans_failed) == (1, 1)
    assert [c["to"] for c in _caravans(factory)] == [3]
    assert _stock(factory, 1, "food") == Decimal("4700")


def test_failing_arrival_is_retried_next_run(factory, monkeypatch):
    _two_regions(factory)
    _pass(factory, 1)
    original = crud.finish
    monkeypatch.setattr(crud, "finish", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    s = _pass(factory, 2)
    assert (s.caravans_failed, s.caravans_delivered) == (1, 0)
    assert _caravans(factory)[0]["status"] == "in_transit"
    monkeypatch.setattr(crud, "finish", original)
    assert _pass(factory, 3).caravans_delivered == 1


def test_snapshot_failure_skips_dispatch_but_not_arrivals(factory, monkeypatch):
    _two_regions(factory)
    _pass(factory, 1)
    _good(factory, 1, "ore_metal", 1000, 200)
    _good(factory, 2, "ore_metal", 0, 300)
    monkeypatch.setattr(crud, "load_snapshot", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    s = _pass(factory, 2)
    assert (s.caravans_delivered, s.caravans_dispatched, s.caravans_failed) == (1, 0, 1)


def test_run_error_prefix_and_region_loop_survive_caravan_failures(factory, monkeypatch):
    _two_regions(factory)
    monkeypatch.setattr(crud, "dispatch", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert summary.caravans_failed >= 1 and summary.caravans_dispatched == 0
    assert summary.status == "done" and summary.regions_done == 2
    error = _scalar(factory, "SELECT error FROM econ_tick_runs WHERE id = :i", i=summary.run_id)
    assert error == econ_tick.CARAVAN_ERROR_PREFIX + str(summary.caravans_failed)
    _check(factory)


# --------------------------------------------------------------------------------------------- dispatch re-checks

def test_dispatch_rechecks_the_locked_rows(factory):
    _two_regions(factory)
    db = factory()
    try:
        snap = crud.load_snapshot(db, 1, _params(factory), _groups(factory), {})
    finally:
        db.close()
    import econ_caravan
    [plan] = econ_caravan.plan_caravans(snap.markets, _groups(factory), snap.inbound, snap.pairs, _params(factory))
    # between the snapshot and the lock the seller lost stock and the buyer's purse shrank
    _good(factory, 1, "food", 250, 200)
    db = factory()
    try:
        econ_ledger.post_operation(db, op_type=core.OP_ADMIN_ADJUST, source_service=SOURCE, comment="тест",
                                   legs=[core.Leg(core.AccountRef.purse(2), core.AccountRef.adjustment(),
                                                  PURSE - 60)])
        db.commit()
    finally:
        db.close()
    result = crud.dispatch_tx(factory, plan, run_id=1, params=_params(factory), now=T0)
    assert result.status == "sent"
    [c] = _caravans(factory)
    assert (Decimal(str(c["units"])), c["value"], c["paid_purse"]) == (Decimal("30"), 60, 60)
    assert _stock(factory, 1, "food") == Decimal("220")
    assert _balance(factory, "population_purse", 2) == 0
    _check(factory)


def test_dispatch_skips_when_the_pair_was_closed_after_the_snapshot(factory):
    _two_regions(factory, seller_country=2)
    _pair(factory, 1, 2)
    db = factory()
    try:
        snap = crud.load_snapshot(db, 1, _params(factory), _groups(factory), {})
    finally:
        db.close()
    import econ_caravan
    [plan] = econ_caravan.plan_caravans(snap.markets, _groups(factory), snap.inbound, snap.pairs, _params(factory))
    _pair(factory, 1, 2, enabled=False)
    assert crud.dispatch_tx(factory, plan, run_id=1, params=_params(factory), now=T0).status == "skipped"
    assert _caravans(factory) == []
    _check(factory)


def test_snapshot_shape(factory):
    _two_regions(factory, seller_country=2)
    _region(factory, 3, purse=0)
    _add_region(factory, 4, world_row=False)                              # econ row of a deleted region
    _pair(factory, 1, 2, duty=7.5)
    _exec(factory, "UPDATE econ_regions SET last_run_id = 9 WHERE region_id = 3")
    _fund(factory, core.AccountRef.region(2), 321)
    db = factory()
    try:
        snap = crud.load_snapshot(db, 9, _params(factory), _groups(factory), {1: [[{"type": "merchants_halt"}]]})
    finally:
        db.close()
    assert sorted(snap.markets) == [1, 2]                                  # 3 ticked in run 9, 4 has no Regions row
    assert snap.markets[1].halted is True and snap.markets[2].halted is False
    assert (snap.markets[1].country_id, snap.markets[2].country_id) == (2, 1)
    assert snap.markets[2].treasury == 321 and snap.markets[2].purse == PURSE
    assert snap.markets[1].goods["food"].stock == 1000.0
    assert list(snap.pairs) == [(1, 2)] and snap.pairs[(1, 2)].duty_pct == 7.5


def test_resumed_pass_does_not_ship_a_second_share_from_the_same_seller(factory):
    """Review #1 note: re-planning a resumed run must not let a seller send another X % of its leftover
    surplus of the same group to a different buyer within the same run."""
    _two_regions(factory)
    _region(factory, 3, country=1, purse=PURSE)
    _good(factory, 3, "food", 100, 300)
    _pass(factory, 1)
    first = [c for c in _caravans(factory) if c["from"] == 1 and c["group"] == "food"]
    assert len(first) >= 1
    _pass(factory, 1)                                   # the same run planned again (crash + resume)
    again = [c for c in _caravans(factory) if c["from"] == 1 and c["group"] == "food"]
    assert len(again) == len(first)
    _pass(factory, 2)                                   # next run: the seller may sell again
    later = [c for c in _caravans(factory) if c["from"] == 1 and c["group"] == "food" and c["dispatch_run_id"] == 2]
    assert len(later) >= 1
