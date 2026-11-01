"""FEAT-193 QA (#9): the guild step of the economy tick (``economy_guild_crud.guild_step`` inside
``econ_tick._process_region``) and the guild sweep, on SQLite.

Harness of ``test_econ_tick.py`` (``factory``: migration-028 seed, countries 1 «Мидденгерд» and 2 «Пустошь»).
Precise volume / budget / refresh rules drive the step directly (``_step``: the same loader the region step uses, no
simulation in between); integration tests run ``run_tick`` / ``_process_region`` and compare the stored order with the
final stock of the run (the simulation moves stocks a little).

Groups used: wood (base 5, not food), ore_metal (base 10), food (base 2, food). Every goods row starts at its norm.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

import econ_core as core
import econ_guild
import econ_ledger
import econ_tick
import economy_guild_crud as guild_crud
import models
from tests.test_econ_tick import (  # noqa: F401  (factory is a fixture)
    SOURCE, T0, _add_region, _assert_ledger_closes, _balance, _rows, _scalar, factory,
)
from tests.test_econ_tick_events import calendar  # noqa: F401  (calendar: autouse, no HTTP)

PURSE = 10_000          # 25 % -> 2 500 marks of guild budget per recount


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
    core.invalidate_settings_cache()


def _region(f, rid, *, country=1, purse=PURSE, template="rural"):
    _add_region(f, rid, template=template, country_id=country, purse=purse)
    _exec(f, "UPDATE econ_region_goods SET stock = norm_stock, price_mult = 1 WHERE region_id = :r", r=rid)


def _good(f, rid, group, stock, norm, mult=1.0):
    _exec(f, "UPDATE econ_region_goods SET stock = :s, norm_stock = :n, price_mult = :m "
             "WHERE region_id = :r AND group_code = :g", s=stock, n=norm, m=mult, r=rid, g=group)


def _fund(f, ref, amount):
    db = f()
    try:
        econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION, source_service=SOURCE, comment="тест",
                                   legs=[core.Leg(core.AccountRef.emission(), ref, amount)])
        db.commit()
    finally:
        db.close()


def _step(f, rid, run_id=1, now=None):
    """The guild part of the region step on the stored goods rows; commits."""
    db = f()
    try:
        region = db.get(models.EconRegion, rid)
        goods = (db.query(models.EconRegionGood).filter(models.EconRegionGood.region_id == rid)
                 .order_by(models.EconRegionGood.group_code).all())
        orders = guild_crud.lock_open_orders(db, rid, False)
        out = guild_crud.guild_step(db, run_id=run_id, region_id=rid, region=region, goods_rows=goods,
                                    groups=econ_tick.load_groups(db), params=econ_tick.load_params(db),
                                    orders=orders, now=now or T0 + timedelta(hours=6 * run_id))
        db.commit()
        return out
    finally:
        db.close()


ORDER_COLS = ("id", "region_id", "group", "open_key", "status", "close_reason", "units_total", "units_left",
              "units_filled", "price_mult", "markup_pct", "pieces", "paid_total", "hand_ins", "opened_run_id",
              "last_run_id", "closed_run_id")


def _orders(f, rid=None):
    sql = ("SELECT id, region_id, group_code, open_key, status, close_reason, units_total, units_left, units_filled, "
           "price_mult, markup_pct, pieces, paid_total, hand_ins, opened_run_id, last_run_id, closed_run_id "
           "FROM econ_guild_orders")
    if rid is not None:
        sql += f" WHERE region_id = {int(rid)}"
    return [dict(zip(ORDER_COLS, r)) for r in _rows(f, sql + " ORDER BY id")]


def _open(f, rid=None):
    return [o for o in _orders(f, rid) if o["status"] == "open"]


def _budget(f, rid):
    return tuple(_rows(f, "SELECT guild_budget, guild_food_budget FROM econ_regions WHERE region_id = :r",
                       r=rid)[0])


def _d(value):
    return Decimal(str(value)).quantize(Decimal("0.001"))


_CARAVAN_SEQ = [100]


def _caravan(f, to_rid, group, units, status="in_transit"):
    _CARAVAN_SEQ[0] += 1
    db = f()
    try:
        db.add(models.EconCaravan(dispatch_run_id=1, from_region_id=_CARAVAN_SEQ[0], to_region_id=to_rid, from_country_id=1,
                                  to_country_id=1, group_code=group, units=Decimal(str(units)),
                                  unit_price=Decimal("5"), value=0, travel_runs=1, runs_left=1, last_run_id=1,
                                  status=status, created_at=T0))
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------------------------- open / volume

def test_order_opens_below_threshold_not_above(factory):
    _region(factory, 1)
    _good(factory, 1, "wood", 10, 100)              # 10 % of norm -> order
    _good(factory, 1, "ore_metal", 85, 100)         # 85 % >= 80 % -> no order
    out = _step(factory, 1)
    assert (out.opened, out.refreshed, out.closed, out.failed) == (1, 0, 0, False)
    [o] = _orders(factory)
    assert (o["region_id"], o["group"], o["open_key"], o["status"], o["close_reason"]) == \
        (1, "wood", "r1:wood", "open", None)
    assert _d(o["units_total"]) == _d(o["units_left"]) == Decimal("90.000")     # fill to the full norm
    assert _d(o["units_filled"]) == 0 and (o["pieces"], o["paid_total"], o["hand_ins"]) == (0, 0, 0)
    assert Decimal(str(o["price_mult"])) == Decimal("1") and Decimal(str(o["markup_pct"])) == Decimal("20")
    assert (o["opened_run_id"], o["last_run_id"], o["closed_run_id"]) == (1, 1, None)


def test_threshold_boundary_on_the_stored_rows(factory):
    _region(factory, 1)
    _good(factory, 1, "wood", 80, 100)              # exactly 80 % -> no order
    _good(factory, 1, "ore_metal", 79.5, 100)       # value 20.5 x 10 = 205 -> order
    _step(factory, 1)
    [o] = _orders(factory)
    assert o["group"] == "ore_metal" and _d(o["units_total"]) == Decimal("20.500")


def test_volume_subtracts_caravans_on_the_road(factory):
    _region(factory, 1)
    _good(factory, 1, "wood", 20, 100)
    _caravan(factory, 1, "wood", 30)
    _caravan(factory, 1, "wood", 5.5)
    _caravan(factory, 1, "wood", 1000, status="delivered")     # finished caravans do not count
    _caravan(factory, 2, "wood", 1000)                         # going elsewhere
    _step(factory, 1)
    [o] = _orders(factory)
    assert _d(o["units_total"]) == Decimal("44.500")           # 100 - 20 - 35.5


def test_caravans_on_the_road_can_cancel_the_order(factory):
    _region(factory, 1)
    _good(factory, 1, "wood", 50, 100)
    _caravan(factory, 1, "wood", 31)                           # 81 % covered
    assert _step(factory, 1).opened == 0
    assert _orders(factory) == []


def test_min_order_value_and_local_mult(factory):
    _region(factory, 1)
    _good(factory, 1, "wood", 70, 100, mult=0.3)               # value floor(30 x 5 x 0.3) = 45 < 50
    _step(factory, 1)
    assert _orders(factory) == []
    _set_params(factory, guild_min_order_value=45)
    _step(factory, 1, run_id=2)
    [o] = _orders(factory)
    assert Decimal(str(o["price_mult"])) == Decimal("0.3")     # snapshot of the local price


def test_markup_snapshot_follows_the_param(factory):
    _region(factory, 1)
    _set_params(factory, guild_markup_pct=35.5)
    _good(factory, 1, "wood", 10, 100, mult=1.234)
    _step(factory, 1)
    [o] = _orders(factory)
    assert Decimal(str(o["markup_pct"])) == Decimal("35.5") and Decimal(str(o["price_mult"])) == Decimal("1.234")


# --------------------------------------------------------------------------------------------- refresh / close

def test_refresh_keeps_one_open_row_and_its_counters(factory):
    _region(factory, 1)
    _good(factory, 1, "wood", 10, 100)
    _step(factory, 1)
    [first] = _orders(factory)
    # a hand-in happened between the recounts
    _exec(factory, "UPDATE econ_guild_orders SET units_left = 60, units_filled = 30, pieces = 30, paid_total = 180, "
                   "hand_ins = 2 WHERE id = :i", i=first["id"])
    _good(factory, 1, "wood", 40, 100, mult=1.4)
    out = _step(factory, 1, run_id=2)
    assert (out.opened, out.refreshed, out.closed) == (0, 1, 0)
    [o] = _orders(factory)
    assert o["id"] == first["id"] and o["status"] == "open"
    assert _d(o["units_total"]) == _d(o["units_left"]) == Decimal("60.000")     # re-measured shortage
    assert (_d(o["units_filled"]), o["pieces"], o["paid_total"], o["hand_ins"]) == (Decimal("30.000"), 30, 180, 2)
    assert Decimal(str(o["price_mult"])) == Decimal("1.4")
    assert (o["opened_run_id"], o["last_run_id"]) == (1, 2)


def test_closes_no_shortage(factory):
    _region(factory, 1)
    _good(factory, 1, "wood", 10, 100)
    _step(factory, 1)
    _good(factory, 1, "wood", 95, 100)
    out = _step(factory, 1, run_id=2)
    assert (out.closed, out.refreshed) == (1, 0)
    [o] = _orders(factory)
    assert (o["status"], o["close_reason"], o["open_key"], o["closed_run_id"]) == ("closed", "no_shortage", None, 2)


def test_closes_no_money_when_the_purse_is_empty(factory):
    _region(factory, 1, purse=3)                    # floor(3 x 0.25) = 0
    _good(factory, 1, "wood", 10, 100)
    _step(factory, 1)
    assert _orders(factory) == [] and _budget(factory, 1) == (0, 0)
    # with money an order opens; the money goes away -> the next recount closes it
    _fund(factory, core.AccountRef.purse(1), 997)
    _step(factory, 1, run_id=2)
    assert len(_open(factory)) == 1
    _set_params(factory, guild_purse_share=0.0)
    _step(factory, 1, run_id=3)
    [o] = _orders(factory)
    assert (o["status"], o["close_reason"]) == ("closed", "no_money")


def test_food_order_paid_by_the_treasury_share_only(factory):
    _region(factory, 1, purse=3)
    _fund(factory, core.AccountRef.region(1), 4000)
    _good(factory, 1, "food", 10, 1000)
    _good(factory, 1, "wood", 10, 100)
    _step(factory, 1)
    assert _budget(factory, 1) == (0, 1000)
    assert [o["group"] for o in _open(factory)] == ["food"]    # wood has no purse money


def test_closes_disabled_when_switched_off(factory):
    _region(factory, 1)
    _fund(factory, core.AccountRef.region(1), 4000)
    _good(factory, 1, "wood", 10, 100)
    _good(factory, 1, "food", 10, 1000)
    _step(factory, 1)
    assert len(_open(factory)) == 2
    _set_params(factory, guild_enabled=0)
    out = _step(factory, 1, run_id=2)
    assert out.closed == 2
    assert {(o["group"], o["status"], o["close_reason"]) for o in _orders(factory)} == {
        ("wood", "closed", "disabled"), ("food", "closed", "disabled")}
    assert _budget(factory, 1) == (0, 0)


def test_norm_zero_closes_disabled(factory):
    _region(factory, 1)
    _good(factory, 1, "wood", 10, 100)
    _step(factory, 1)
    _good(factory, 1, "wood", 0, 0)
    _step(factory, 1, run_id=2)
    assert _orders(factory)[0]["close_reason"] == "disabled"


def test_open_order_of_a_group_without_goods_row_is_closed(factory):
    _region(factory, 1)
    _good(factory, 1, "wood", 10, 100)
    _step(factory, 1)
    _exec(factory, "DELETE FROM econ_region_goods WHERE region_id = 1 AND group_code = 'wood'")
    assert _step(factory, 1, run_id=2).closed == 1
    assert _orders(factory)[0]["close_reason"] == "disabled"


def test_filled_row_stays_and_a_new_row_opens_next_run(factory):
    _region(factory, 1)
    _good(factory, 1, "wood", 10, 100)
    _step(factory, 1)
    [first] = _orders(factory)
    _exec(factory, "UPDATE econ_guild_orders SET status = 'filled', open_key = NULL, close_reason = 'filled', "
                   "units_left = 0 WHERE id = :i", i=first["id"])
    out = _step(factory, 1, run_id=2)
    assert (out.opened, out.refreshed) == (1, 0)
    old, new = _orders(factory)
    assert (old["id"], old["status"], old["close_reason"]) == (first["id"], "filled", "filled")
    assert (new["status"], new["open_key"], new["opened_run_id"]) == ("open", "r1:wood", 2)
    assert new["id"] != first["id"]


def test_regions_are_independent(factory):
    _region(factory, 1)
    _region(factory, 2)
    _good(factory, 1, "wood", 10, 100)
    _good(factory, 2, "wood", 10, 100)
    _step(factory, 1)
    _step(factory, 2)
    assert sorted(o["open_key"] for o in _orders(factory)) == ["r1:wood", "r2:wood"]


# --------------------------------------------------------------------------------------------- budgets

def test_budgets_are_shares_of_purse_and_positive_treasury(factory):
    _region(factory, 1, purse=10_001)
    _fund(factory, core.AccountRef.region(1), 803)
    _step(factory, 1)
    assert _budget(factory, 1) == (2500, 200)       # floor(10 001 / 4), floor(803 / 4)
    _set_params(factory, guild_purse_share=0.1, guild_treasury_food_share=1.0)
    _step(factory, 1, run_id=2)
    assert _budget(factory, 1) == (1000, 803)       # a fresh allowance per run, not accumulated


def test_negative_treasury_gives_no_food_budget(factory):
    _region(factory, 1)
    _fund(factory, core.AccountRef.region(1), 100)
    _exec(factory, "UPDATE econ_accounts SET balance = -500 WHERE kind = 'region_treasury' AND ref_id = 1")
    _step(factory, 1)
    assert _budget(factory, 1) == (2500, 0)


# --------------------------------------------------------------------------------------------- inside the tick

def _final(f, rid, group):
    norm, stock = _rows(f, "SELECT norm_stock, stock FROM econ_region_goods WHERE region_id = :r AND group_code = :g",
                        r=rid, g=group)[0]
    return Decimal(str(norm)), Decimal(str(stock))


def test_run_tick_opens_order_from_the_final_stock_and_budget(factory):
    _region(factory, 1)
    _good(factory, 1, "wood", 5, 1000)
    _good(factory, 1, "ore_metal", 3000, 100)       # far above the norm
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert summary.regions_done == 1 and summary.guild_opened >= 1 and summary.guild_failures == 0
    orders = {o["group"]: o for o in _open(factory)}
    assert "wood" in orders and "ore_metal" not in orders
    norm, stock = _final(factory, 1, "wood")
    assert _d(orders["wood"]["units_total"]) == _d(econ_guild.floor3(norm - stock))
    assert orders["wood"]["last_run_id"] == summary.run_id
    purse = _balance(factory, "population_purse", 1)
    assert _budget(factory, 1)[0] == purse // 4     # share of the purse AFTER the region's postings
    _assert_ledger_closes(factory)


def test_second_run_refreshes_without_duplicates(factory):
    _region(factory, 1)
    _good(factory, 1, "wood", 5, 1000)
    s1 = econ_tick.run_tick(factory, trigger="manual", now=T0)
    first = {o["group"]: o["id"] for o in _open(factory)}
    s2 = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=30))
    assert s2.guild_refreshed >= 1 and s2.guild_opened == 0
    second = {o["group"]: o for o in _open(factory)}
    assert {g: o["id"] for g, o in second.items()} == first
    assert second["wood"]["last_run_id"] == s2.run_id and second["wood"]["opened_run_id"] == s1.run_id
    assert _scalar(factory, "SELECT COUNT(*) FROM econ_guild_orders") == len(first)


def test_resumed_region_does_nothing_twice(factory):
    _region(factory, 1)
    _good(factory, 1, "wood", 5, 1000)
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    before = (_orders(factory), _budget(factory, 1))
    db = factory()
    groups, params = econ_tick.load_groups(db), econ_tick.load_params(db)
    db.close()
    outcome = econ_tick._process_region(factory, run_id=summary.run_id, region_id=1, grant=0, groups=groups,
                                        params=params, country_tax_rate=0.1, now=T0, with_guild=True)
    assert outcome.status == "already" and outcome.guild is None
    assert (_orders(factory), _budget(factory, 1)) == before


def test_failing_guild_step_rolls_back_only_itself(factory, monkeypatch):
    _region(factory, 1)
    _region(factory, 2)
    _good(factory, 1, "wood", 5, 1000)
    _good(factory, 2, "wood", 5, 1000)
    real = guild_crud.guild_step

    def broken(session, **kw):
        real(session, **kw)                         # writes orders and the budget ...
        if kw["region_id"] == 1:
            raise RuntimeError("boom")              # ... then fails: the SAVEPOINT must undo them
        return guild_crud.StepOutcome(opened=1)

    monkeypatch.setattr(guild_crud, "guild_step", broken)
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert summary.regions_done == 2 and summary.regions_failed == 0
    assert summary.guild_failures == 1 and summary.guild_failed_region_ids == [1]
    assert [o["region_id"] for o in _orders(factory)] == [2]     # region 1 has none, region 2 is fine
    assert _budget(factory, 1) == (0, 0)
    # the region itself ticked
    assert _scalar(factory, "SELECT last_run_id FROM econ_regions WHERE region_id = 1") == summary.run_id
    assert _scalar(factory, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'region_tick' AND region_id = 1") \
        == 1
    error = _scalar(factory, "SELECT error FROM econ_tick_runs WHERE id = :i", i=summary.run_id)
    assert econ_tick.GUILD_ERROR_PREFIX + "1" in error
    _assert_ledger_closes(factory)


def test_tick_without_guild_tables_skips_the_guild(factory):
    _region(factory, 1)
    _good(factory, 1, "wood", 5, 1000)
    _exec(factory, "DROP TABLE econ_guild_xp_days")
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert summary.regions_done == 1 and summary.guild_failures == 0 and not summary.guild_sweep_failed
    assert _orders(factory) == []


# --------------------------------------------------------------------------------------------- sweep

def _xp_day(f, cid, day, xp):
    _exec(f, "INSERT INTO econ_guild_xp_days (character_id, day, xp) VALUES (:c, :d, :x)", c=cid, d=day, x=xp)


def test_sweep_closes_orders_of_regions_that_left(factory):
    for rid in (1, 2, 3, 4):
        _region(factory, rid)
        _good(factory, rid, "wood", 10, 100)
        _step(factory, rid)
    _exec(factory, "UPDATE econ_regions SET template_code = NULL WHERE region_id = 1")
    _exec(factory, "UPDATE econ_regions SET population = 0 WHERE region_id = 2")
    _exec(factory, "DELETE FROM econ_region_goods WHERE region_id = 3")
    _exec(factory, "DELETE FROM econ_regions WHERE region_id = 3")
    db = factory()
    closed = guild_crud.sweep(db, 7, T0)
    db.commit()
    db.close()
    assert closed == 3
    by_region = {o["region_id"]: o for o in _orders(factory)}
    for rid in (1, 2, 3):
        assert (by_region[rid]["status"], by_region[rid]["close_reason"], by_region[rid]["open_key"],
                by_region[rid]["closed_run_id"]) == ("closed", "region_left", None, 7)
    assert by_region[4]["status"] == "open"
    assert _budget(factory, 1) == (0, 0) and _budget(factory, 2) == (0, 0)
    assert _budget(factory, 4) == (2500, 0)


def test_sweep_drops_old_xp_day_rows(factory):
    today = T0.date()
    _xp_day(factory, 1, today, 10)
    _xp_day(factory, 1, today - timedelta(days=7), 20)     # kept (exactly 7 days)
    _xp_day(factory, 1, today - timedelta(days=8), 30)     # dropped
    _xp_day(factory, 2, date(2020, 1, 1), 40)
    db = factory()
    guild_crud.sweep(db, 1, T0)
    db.commit()
    db.close()
    assert sorted(r[0] for r in _rows(factory, "SELECT xp FROM econ_guild_xp_days")) == [10, 20]


def test_run_tick_sweeps_a_region_that_left(factory):
    _region(factory, 1)
    _region(factory, 2)
    _good(factory, 1, "wood", 5, 1000)
    econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert any(o["region_id"] == 1 for o in _open(factory))
    _exec(factory, "UPDATE econ_regions SET template_code = NULL WHERE region_id = 1")
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=30))
    assert not summary.guild_sweep_failed and summary.guild_closed >= 1
    assert [o for o in _open(factory) if o["region_id"] == 1] == []
    assert {o["close_reason"] for o in _orders(factory, 1)} == {"region_left"}
