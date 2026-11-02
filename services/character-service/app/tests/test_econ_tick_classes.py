"""FEAT-194 QA (#9): social classes and the wealth norm in the economy tick (SQLite harness of ``test_econ_tick``).

``_seed_classes`` applies the migration-037 data (template default mixes, class demand weights of the goods groups)
to the 028 seed of the ``factory`` fixture; ``_classes`` gives a region the shares of its template (what 037's
backfill does on prod). Regions added without it keep NULL shares (no classes).

Covered: default mix stays put (dead zone) and the norm / history are written; NULL shares and ``classes_enabled = 0``
tick exactly like a region without classes; the wealth tax rides in the ``region_tick`` tax leg with the country 10 %,
stays out of same-tick wages, ``treasury_target`` from the income tax only; mobility with a boom / a famine; the
one-shot ``class_shift`` (incl. «Разорение» of 037) applied once with outcome before/after; quota by deficit at tick
level (rollout wait, only below-norm regions, cap, once per season); grant plan tilt; a 30-run property from 2x the
norm (world sum 0, shares bounded, the excess melts).
"""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

import econ_classes as C
import econ_core as core
import econ_ledger
import econ_mint
import econ_sim
import econ_tick
import models
from tests.test_econ_classes import mig037
from tests.test_econ_tick import (  # noqa: F401  (factory is a fixture)
    SOURCE, T0, _add_region, _assert_ledger_closes, _balance, _fund_country, _rows, _scalar, factory,
)
from tests.test_econ_tick_events import _add_template, _set_params, _start, calendar  # noqa: F401
from tests.test_econ_tick_mint import GAME_TIME_DDL, EPOCH, _exec, _ops, _meta

SIX_HOURS = timedelta(hours=6)


# --------------------------------------------------------------------------------------------- helpers

def _seed_classes(factory):
    db = factory()
    try:
        for code, (p, m, r) in mig037.TEMPLATE_CLASSES.items():
            row = db.get(models.EconRegionTemplate, code)
            row.class_poor, row.class_middling, row.class_rich = Decimal(str(p)), Decimal(str(m)), Decimal(str(r))
        for code, (p, m, r) in mig037.GROUP_CLASS_DEMAND.items():
            row = db.get(models.EconGoodsGroup, code)
            row.class_demand_poor, row.class_demand_middling, row.class_demand_rich = p, m, r
        db.commit()
    finally:
        db.close()


def _classes(factory, region_id, mix=None):
    """Shares of the region's template (037 backfill) or ``mix``."""
    db = factory()
    try:
        row = db.get(models.EconRegion, region_id)
        if mix is None:
            mix = C.ClassMix(*mig037.TEMPLATE_CLASSES[row.template_code])
        econ_tick.store_classes(row, mix)
        db.commit()
    finally:
        db.close()


def _region(factory, region_id):
    db = factory()
    try:
        row = db.get(models.EconRegion, region_id)
        db.expunge(row)
        return row
    finally:
        db.close()


def _mix(row):
    return (row.class_poor, row.class_middling, row.class_rich)


def _norm_now(factory, region_id, **params):
    """The wealth norm the next recount will compute (from the stored goods / shares)."""
    db = factory()
    try:
        p = econ_tick.load_params(db)
        if params:
            p = econ_sim.SimParams.from_mapping({**p.to_dict(), **params})
        row = db.get(models.EconRegion, region_id)
        groups = econ_tick.load_groups(db)
        goods = {g.group_code: econ_tick.good_state(g) for g in
                 db.query(models.EconRegionGood).filter_by(region_id=region_id).all()}
        state = econ_tick.region_state(row, econ_tick.class_base_of(db, row.template_code))
        return econ_sim.region_wealth_norm(groups, goods, state, p)
    finally:
        db.close()


def _emit(factory, ref, amount):
    db = factory()
    try:
        econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION, source_service=SOURCE, comment="тест",
                                   legs=[core.Leg(core.AccountRef.emission(), ref, amount)])
        db.commit()
    finally:
        db.close()


def _set_balance(factory, ref, kind, amount):
    have = _balance(factory, kind, ref.ref_id)
    if amount != have:
        legs = ([core.Leg(core.AccountRef.emission(), ref, amount - have)] if amount > have
                else [core.Leg(ref, core.AccountRef.emission(), have - amount)])
        db = factory()
        try:
            econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION, source_service=SOURCE, comment="тест",
                                       legs=legs)
            db.commit()
        finally:
            db.close()
    assert _balance(factory, kind, ref.ref_id) == amount


def _set_purse(factory, region_id, amount):
    _set_balance(factory, core.AccountRef.purse(region_id), "population_purse", amount)


def _set_treasury(factory, region_id, amount):
    _set_balance(factory, core.AccountRef.region(region_id), "region_treasury", amount)


def _tick_op(factory, run_id, region_id):
    op_id, meta = _rows(factory, "SELECT id, metadata FROM econ_operations WHERE idempotency_key = :k",
                        k=f"region_tick:{run_id}:r:{region_id}")[0]
    legs = _rows(factory, "SELECT a1.kind, a2.kind, l.amount FROM econ_postings l "
                          "JOIN econ_accounts a1 ON a1.id = l.from_account_id "
                          "JOIN econ_accounts a2 ON a2.id = l.to_account_id WHERE l.operation_id = :i "
                          "ORDER BY l.id", i=op_id)
    return _meta(meta), legs


def _history(factory, region_id, run_id):
    return _rows(factory, "SELECT class_poor, class_middling, class_rich, wealth_norm, wealth_tax, tax, wages "
                          "FROM econ_region_history WHERE region_id = :r AND run_id = :n", r=region_id, n=run_id)[0]


def _goods(factory, region_id):
    return _rows(factory, "SELECT group_code, stock, norm_stock, price_mult, last_consumed FROM econ_region_goods "
                          "WHERE region_id = :r ORDER BY group_code", r=region_id)


def _run(factory, k=0):
    return econ_tick.run_tick(factory, trigger="manual", now=T0 + SIX_HOURS * k)


# --------------------------------------------------------------------------------------------- default mix

def test_default_mix_stays_put_and_the_norm_and_history_are_written(factory):
    _seed_classes(factory)
    _add_region(factory, 1, template="fortress")
    _classes(factory, 1)
    before = _mix(_region(factory, 1))
    norm = _norm_now(factory, 1)
    assert _balance(factory, "population_purse", 1) <= norm            # 7 days vs the fortress norm 7.2 days
    summary = _run(factory)
    row = _region(factory, 1)
    assert _mix(row) == before                                           # dead zone: no drift at rollout
    assert row.class_dpoor == 0 and row.class_drich == 0
    assert int(row.wealth_norm) == norm > 0
    assert int(row.last_wealth_tax) == 0
    hist = _history(factory, 1, summary.run_id)
    assert tuple(Decimal(str(v)) for v in hist[:3]) == tuple(Decimal(str(v)) for v in before)
    assert hist[3] == norm and hist[4] == 0
    meta, _legs = _tick_op(factory, summary.run_id, 1)
    assert meta["wealth_tax"] == 0
    _assert_ledger_closes(factory)


def test_null_shares_tick_as_before_and_get_the_old_norm(factory):
    _seed_classes(factory)
    _add_region(factory, 1, template="fortress")                         # NULL shares
    summary = _run(factory)
    row = _region(factory, 1)
    assert _mix(row) == (None, None, None)
    assert row.class_dpoor == 0 and row.class_drich == 0
    assert int(row.wealth_norm) == _norm_now(factory, 1) > 0             # starting_purse of today
    assert _history(factory, 1, summary.run_id)[:3] == (None, None, None)
    meta, _legs = _tick_op(factory, summary.run_id, 1)
    assert "wealth_tax" not in meta
    _assert_ledger_closes(factory)


@pytest.mark.parametrize("switch_off", [False, True])
def test_classes_off_or_default_mix_tick_like_a_region_without_classes(factory, switch_off):
    """Twin fortresses in a country without funds: #1 NULL shares, #2 shares at the template mix. With the layer
    switched off they are identical to the last digit; with it on (purse below the norm, every class affords its
    basket) money and goods still match — the factors are exactly 1.0."""
    _seed_classes(factory)
    _add_region(factory, 1, template="fortress")
    _add_region(factory, 2, template="fortress")
    _classes(factory, 2)
    if switch_off:
        _set_params(factory, classes_enabled=0)
    for k in range(3):
        _run(factory, k)
    a, b = _region(factory, 1), _region(factory, 2)
    for col in ("last_income", "last_tax", "last_wages", "treasury_target", "last_wealth_tax"):
        assert getattr(a, col) == getattr(b, col), col
    assert float(a.hunger) == float(b.hunger) and float(a.stability) == pytest.approx(float(b.stability), abs=0.011)
    assert _balance(factory, "population_purse", 1) == _balance(factory, "population_purse", 2)
    assert _balance(factory, "region_treasury", 1) == _balance(factory, "region_treasury", 2)
    ga, gb = _goods(factory, 1), _goods(factory, 2)
    if switch_off:
        assert ga == gb
        assert b.class_dpoor == 0 and _mix(b) == tuple(Decimal(str(v)).quantize(Decimal("0.000001"))
                                                         for v in mig037.TEMPLATE_CLASSES["fortress"])
        assert int(b.wealth_norm) == int(a.wealth_norm)                  # no classes -> the old norm
        assert _rows(factory, "SELECT COUNT(*) FROM econ_region_history WHERE region_id = 2 "
                              "AND class_poor IS NOT NULL") == [(0,)]
    else:
        for x, y in zip(ga, gb):
            assert x[0] == y[0] and float(x[1]) == pytest.approx(float(y[1]), rel=1e-6, abs=1e-3)
            assert float(x[3]) == pytest.approx(float(y[3]), abs=1e-3)
    _assert_ledger_closes(factory)


# --------------------------------------------------------------------------------------------- wealth tax

def test_wealth_tax_rides_the_tax_leg_with_the_country_cut_and_not_same_tick_wages(factory):
    _seed_classes(factory)
    _add_region(factory, 1, template="fortress")
    _classes(factory, 1)
    norm = _norm_now(factory, 1)
    _set_purse(factory, 1, 2 * norm)
    _emit(factory, core.AccountRef.region(1), 5_000)
    treasury_before = _balance(factory, "region_treasury", 1)
    country_before = _balance(factory, "country_treasury", 1)
    rate = econ_ledger.get_economy_settings(_session := factory()).country_tax_rate
    _session.close()

    summary = _run(factory)
    row = _region(factory, 1)
    tax, wt, wages = int(row.last_tax), int(row.last_wealth_tax), int(row.last_wages)
    assert wt == int(0.02 * (2 * norm - tax - norm)) > 0                 # 2 % of the excess after the income tax
    meta, legs = _tick_op(factory, summary.run_id, 1)
    assert meta["wealth_tax"] == wt and meta["tax"] == tax and meta["wages"] == wages
    assert ("population_purse", "region_treasury", tax + wt) in legs              # one leg: income tax + wealth tax
    country_cut = core.tax_amount(tax + wt, rate)
    assert ("region_treasury", "country_treasury", country_cut) in legs                    # the ledger's 10 % on the sum
    assert ("region_treasury", "population_purse", wages) in legs
    assert len([leg for leg in legs if leg[1] == "region_treasury" and leg[0] == "population_purse"]) == 1
    # treasury_target from the income tax only; wages = net income tax + release (no wealth tax inside)
    params = econ_sim.DEFAULT_PARAMS
    assert int(row.treasury_target) == int(tax * (1 / params.dt) * params.treasury_reserve_days)
    net_income_tax = tax - core.tax_amount(tax, rate)
    assert wages == econ_sim.wage_amount(net_income_tax, int(row.last_grant), treasury_before, int(row.treasury_target), params)
    assert int(row.last_grant) == 0                                      # the country is empty
    assert _balance(factory, "region_treasury", 1) == treasury_before + tax + wt - country_cut - wages
    assert _balance(factory, "country_treasury", 1) == country_before + country_cut
    assert _balance(factory, "population_purse", 1) == 2 * norm - tax - wt + wages
    assert _history(factory, 1, summary.run_id)[4] == wt
    _assert_ledger_closes(factory)


def test_wealth_tax_surplus_comes_back_through_the_slow_release(factory):
    _seed_classes(factory)
    _add_region(factory, 1, template="fortress")
    _classes(factory, 1)
    _run(factory)                                                        # learn the wage reserve target
    _set_treasury(factory, 1, int(_region(factory, 1).treasury_target))
    _set_purse(factory, 1, 3 * _norm_now(factory, 1))
    first = _run(factory, 1)
    one = _region(factory, 1)
    treasury_mid = _balance(factory, "region_treasury", 1)
    assert treasury_mid > int(one.treasury_target)                       # the wealth tax parked above the target
    second = _run(factory, 2)
    two = _region(factory, 1)
    rate = econ_ledger.get_economy_settings(_session := factory()).country_tax_rate
    _session.close()
    net = int(two.last_tax) - core.tax_amount(int(two.last_tax), rate)
    expected = econ_sim.wage_amount(net, int(two.last_grant), treasury_mid, int(two.treasury_target), econ_sim.DEFAULT_PARAMS)
    assert int(two.last_wages) == expected > net + int(two.last_grant)                        # paid back later, slowly
    assert first.run_id != second.run_id
    _assert_ledger_closes(factory)


def test_no_wealth_tax_below_the_norm_and_with_rate_zero(factory):
    _seed_classes(factory)
    _add_region(factory, 1, template="capital")                         # 7 days vs the capital norm ~10 days
    _add_region(factory, 2, template="fortress")
    _classes(factory, 1)
    _classes(factory, 2)
    _set_purse(factory, 2, 3 * _norm_now(factory, 2))
    _set_params(factory, wealth_tax_rate=0.0)
    _run(factory)
    assert int(_region(factory, 1).last_wealth_tax) == 0
    assert int(_region(factory, 2).last_wealth_tax) == 0
    _set_params(factory, wealth_tax_rate=0.02)
    _run(factory, 1)
    assert int(_region(factory, 1).last_wealth_tax) == 0
    assert int(_region(factory, 2).last_wealth_tax) > 0
    _assert_ledger_closes(factory)


# --------------------------------------------------------------------------------------------- mobility

def test_boom_moves_classes_up_and_the_shift_is_stored(factory):
    _seed_classes(factory)
    _add_region(factory, 1, template="mining")
    _classes(factory, 1)
    _set_purse(factory, 1, 3 * _norm_now(factory, 1))
    db = factory()
    db.get(models.EconRegion, 1).prosperity = 100
    db.get(models.EconRegion, 1).stability = 100
    db.commit()
    db.close()
    before = _region(factory, 1)
    summary = _run(factory)
    after = _region(factory, 1)
    assert after.class_poor < before.class_poor and after.class_rich > before.class_rich
    assert after.class_dpoor == after.class_poor - before.class_poor < 0
    assert after.class_drich == after.class_rich - before.class_rich > 0
    assert after.class_poor + after.class_middling + after.class_rich == 1
    hist = _history(factory, 1, summary.run_id)
    assert Decimal(str(hist[0])) == after.class_poor
    _assert_ledger_closes(factory)


def test_famine_moves_classes_down(factory):
    _seed_classes(factory)
    _add_region(factory, 1, template="port")
    _classes(factory, 1)
    _set_purse(factory, 1, 0)
    _exec(factory, "UPDATE econ_region_goods SET stock = 0, production_per_1000 = 0 WHERE region_id = 1 "
                   "AND group_code = 'food'")
    _exec(factory, "UPDATE econ_regions SET stability = 10, prosperity = 5 WHERE region_id = 1")
    before = _region(factory, 1)
    _run(factory)
    after = _region(factory, 1)
    assert after.class_poor > before.class_poor and after.class_rich < before.class_rich
    assert after.class_dpoor > 0 > after.class_drich
    assert float(after.hunger) > 0.5
    _assert_ledger_closes(factory)


# --------------------------------------------------------------------------------------------- event class_shift

def test_class_shift_event_applied_once_with_outcome(factory):
    _seed_classes(factory)
    _add_region(factory, 1, template="fortress")
    _classes(factory, 1)
    _add_template(factory, "ruin_x", [{"type": "class_shift", "delta": -0.06}], trigger_kind="manual",
                  duration_min_days=5, duration_max_days=5)
    _start(factory, "ruin_x", 1, days=5)
    before = _region(factory, 1)
    first = _run(factory)
    assert first.events_applied == 1
    after = _region(factory, 1)
    expected, _dp, _dr = C.event_shift(econ_tick.region_classes(before), -0.06, econ_sim.DEFAULT_PARAMS)
    assert after.class_poor > before.class_poor and after.class_rich < before.class_rich
    # the stored shift = the event shift (+ mobility, which is inside the dead zone here)
    assert float(after.class_poor) == pytest.approx(expected.poor, abs=2e-4)
    assert after.class_dpoor == after.class_poor - before.class_poor
    outcome = _rows(factory, "SELECT outcome FROM econ_region_events WHERE region_id = 1")[0][0]
    outcome = json.loads(outcome) if isinstance(outcome, str) else outcome
    assert outcome["class_shift"]["before"] == [round(float(v), 6) for v in _mix(before)]
    assert outcome["class_shift"]["after"] == [round(v, 6) for v in expected.as_tuple()]
    # the next recount does not apply it again
    second = _run(factory, 1)
    assert second.events_applied == 0
    again = _region(factory, 1)
    assert abs(float(again.class_poor) - float(after.class_poor)) < 0.001
    _assert_ledger_closes(factory)


def test_class_shift_ignored_without_shares_or_with_classes_off(factory):
    _seed_classes(factory)
    _add_region(factory, 1, template="fortress")                         # NULL shares
    _add_region(factory, 2, template="fortress")
    _classes(factory, 2)
    _set_params(factory, classes_enabled=0)
    _add_template(factory, "boom_x", [{"type": "class_shift", "delta": 0.2}], kind="good", trigger_kind="manual")
    _start(factory, "boom_x", 1, days=2)
    _start(factory, "boom_x", 2, days=2)
    before = _mix(_region(factory, 2))
    summary = _run(factory)
    assert summary.events_applied == 2
    assert _mix(_region(factory, 1)) == (None, None, None)
    assert _mix(_region(factory, 2)) == before
    for (outcome,) in _rows(factory, "SELECT outcome FROM econ_region_events"):
        outcome = json.loads(outcome) if isinstance(outcome, str) else (outcome or {})
        assert "class_shift" not in outcome
    _assert_ledger_closes(factory)


def test_ruin_template_of_037_shifts_down_and_cuts_tax(factory):
    _seed_classes(factory)
    _add_region(factory, 1, template="port")
    _classes(factory, 1)
    db = factory()
    db.add(models.EconEventTemplate(**{**mig037.RUIN, "trigger_kind": "manual"}))
    db.commit()
    db.close()
    _start(factory, "ruin", 1, days=6)
    before = _region(factory, 1)
    _run(factory)
    after = _region(factory, 1)
    assert float(after.class_poor - before.class_poor) == pytest.approx(0.06 * float(before.class_middling), abs=5e-4)
    assert after.class_rich < before.class_rich
    _assert_ledger_closes(factory)


# --------------------------------------------------------------------------------------------- quota by deficit

@pytest.fixture
def season(factory):
    _exec(factory, GAME_TIME_DDL)
    _exec(factory, "INSERT INTO game_time_config (id, epoch, offset_days) VALUES (1, :e, 0)", e=EPOCH)
    return factory


def test_quota_goes_only_to_regions_below_their_norm_once_per_season(season):
    _seed_classes(season)
    _add_region(season, 1, template="fortress")
    _add_region(season, 2, template="fortress")
    _add_region(season, 3, template="capital")
    for rid in (1, 2, 3):
        _classes(season, rid)
    _set_purse(season, 1, _norm_now(season, 1) // 3)                     # far below
    _set_purse(season, 2, 4 * _norm_now(season, 2))                      # far above (incl. its treasury target)
    _set_params(season, quota_season_amount=10 ** 9)

    first = _run(season)                                                 # rollout: wealth_norm still 0 -> waits
    assert first.quota_amount == 0 and _ops(season, "season_quota") == []
    db = season()
    deficits = econ_tick.region_deficits(db)
    db.close()
    assert deficits[1] > 0 and deficits[2] == 0 and deficits[3] > 0     # capital: 7 days vs ~10 days norm

    second = _run(season, 1)
    assert second.quota_amount == deficits[1] + deficits[3]              # capped at the total deficit
    (_op_id, key, _r, meta), = _ops(season, "season_quota")
    meta = _meta(meta)
    assert key == "season_quota:p0"
    assert meta["regions"] == {"1": deficits[1], "3": deficits[3]}
    assert meta["deficits"] == {"1": deficits[1], "3": deficits[3]} and meta["requested"] == 10 ** 9
    legs = _rows(season, "SELECT a2.ref_id, l.amount FROM econ_postings l "
                         "JOIN econ_accounts a2 ON a2.id = l.to_account_id "
                         "WHERE l.operation_id = :i AND a2.kind = 'region_treasury' ORDER BY a2.ref_id", i=_op_id)
    assert legs == [(1, deficits[1]), (3, deficits[3])]

    third = _run(season, 2)                                             # same season: never twice
    assert third.quota_amount == 0 and len(_ops(season, "season_quota")) == 1
    _assert_ledger_closes(season)


def test_small_quota_is_split_by_deficit(season):
    _seed_classes(season)
    _add_region(season, 1, template="fortress")
    _add_region(season, 2, template="rural")
    for rid in (1, 2):
        _classes(season, rid)
    _set_purse(season, 1, 0)
    _set_purse(season, 2, 0)
    _run(season)                                                         # writes the norms (quota 0 = off)
    _set_params(season, quota_season_amount=1000)
    db = season()
    deficits = econ_tick.region_deficits(db)
    db.close()
    summary = _run(season, 1)
    assert summary.quota_amount == 1000
    meta = _meta(_ops(season, "season_quota")[0][3])
    expected = {str(k): v for k, v in sorted(econ_mint.split_by_deficit(1000, deficits).items())}
    assert meta["regions"] == expected and sum(expected.values()) == 1000
    big = max(deficits, key=deficits.get)
    assert meta["regions"][str(big)] >= meta["regions"][str(min(deficits, key=deficits.get))]
    _assert_ledger_closes(season)


# --------------------------------------------------------------------------------------------- grant plan

def test_grant_plan_tilts_toward_regions_below_the_norm(factory):
    _seed_classes(factory)
    _add_region(factory, 1, template="fortress")
    _add_region(factory, 2, template="fortress")
    for rid in (1, 2):
        _classes(factory, rid)
    _run(factory)                                                        # writes wealth_norm / treasury_target
    _set_purse(factory, 1, 0)                                            # #1 far below its norm
    _set_purse(factory, 2, 5 * int(_region(factory, 2).wealth_norm))
    _fund_country(factory, 1, 1_000_000)
    db = factory()
    try:
        params = econ_tick.load_params(db)
        plan = econ_tick.build_grant_plan(db, params)
        deficits = econ_tick.region_deficits(db)
        balance = econ_tick.account_balance(db, core.AccountRef.country(1))
        flat = econ_sim.country_grants(balance, {1: 1, 2: 1}, params)
        no_tilt = econ_tick.build_grant_plan(db, econ_sim.SimParams.from_mapping(
            {**params.to_dict(), "grant_deficit_share": 0.0}))
    finally:
        db.close()
    assert deficits[1] > 0 and deficits[2] == 0
    assert plan["1"] > plan["2"]
    assert plan["1"] + plan["2"] <= flat[1] + flat[2]
    assert no_tilt == {"1": flat[1], "2": flat[2]}                       # tilt 0 -> by population as before
    assert plan == {str(k): v for k, v in econ_sim.country_grants(balance, {1: 1, 2: 1}, params,
                                                                     deficits=deficits).items()}


# --------------------------------------------------------------------------------------------- long run

def test_thirty_recounts_from_twice_the_norm_stay_bounded_and_the_world_sum_stays_zero(factory):
    _seed_classes(factory)
    for rid, template in ((1, "capital"), (2, "rural"), (3, "port")):
        _add_region(factory, rid, template=template)
        _classes(factory, rid)
    _set_purse(factory, 1, 2 * _norm_now(factory, 1))
    _fund_country(factory, 1, 50_000)
    excess = []
    for k in range(30):
        _run(factory, k)
        _assert_ledger_closes(factory)
        for rid in (1, 2, 3):
            row = _region(factory, rid)
            mix = (row.class_poor, row.class_middling, row.class_rich)
            assert sum(mix) == 1 and all(Decimal("0.02") <= s <= Decimal("0.9") for s in mix)
        row = _region(factory, 1)
        excess.append(_balance(factory, "population_purse", 1) - int(row.wealth_norm))
    assert excess[-1] < excess[0]                                         # the excess melts ...
    assert all(b <= a + 1 for a, b in zip(excess, excess[1:]))            # ... monotonically
    assert int(_scalar(factory, "SELECT SUM(wealth_tax) FROM econ_region_history WHERE region_id = 1")) > 0
    assert int(_scalar(factory, "SELECT COALESCE(SUM(balance), 0) FROM econ_accounts")) == 0
