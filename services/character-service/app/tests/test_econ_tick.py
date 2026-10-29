"""FEAT-182 Q2: living-regions tick runner (``econ_tick``) and scheduler (``econ_scheduler``) on SQLite.

Every test gets its own in-memory database built from the character-service metadata (the conftest
``after_create`` hook adds the Countries / Regions hierarchy) and seeded with the migration-028 defaults.

SQLite note: DATETIME columns are compared as strings there, so the clocks used below are minutes apart
(never seconds) to keep ``heartbeat_at < :stale`` unambiguous.
"""

import importlib.util
import json
import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import econ_core as core
import econ_ledger
import econ_scheduler
import econ_sim
import econ_tick
import models

# FEAT-186: stored populations are lore numbers; the 028 seed numbers are simulated ones (x scale = lore).
SCALE = econ_sim.DEFAULT_PARAMS.population_scale

MIGRATION_PATH = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "028_econ_living_regions.py")
_spec = importlib.util.spec_from_file_location("migration_028_for_tick", MIGRATION_PATH)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)

T0 = datetime(2026, 10, 28, 0, 5)          # slot start + 5 min
COUNTRY_FUNDS = 100_000
SOURCE = "character-service"


# --------------------------------------------------------------------------------------------- fixtures

@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_factory()
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
    db.execute(text("INSERT INTO Countries (id, name) VALUES (1, 'Мидденгерд'), (2, 'Пустошь')"))
    db.commit()
    db.close()
    core.invalidate_settings_cache()
    yield session_factory
    core.invalidate_settings_cache()
    engine.dispose()


def _add_region(factory, region_id, *, template="rural", population=None, country_id=1, purse="start",
                world_row=True):
    """Regions row (unless ``world_row=False``) + econ_regions/goods from a template + funded purse."""
    db = factory()
    try:
        if world_row:
            db.execute(text("INSERT INTO Regions (id, name, country_id) VALUES (:i, :n, :c)"),
                       {"i": region_id, "n": f"Регион {region_id}", "c": country_id})
        groups = econ_tick.load_groups(db)
        tpl = db.get(models.EconRegionTemplate, template)
        pop = tpl.default_population // SCALE if population is None else population   # simulated population
        tgoods = {g: (p, c) for g, p, c in mig.template_goods(template)}
        goods = econ_sim.starting_goods(groups, tgoods, pop)
        db.add(models.EconRegion(region_id=region_id, template_code=template, population=pop * SCALE,
                                 tax_rate=tpl.tax_rate))
        db.flush()
        for code, g in goods.items():
            db.add(models.EconRegionGood(region_id=region_id, group_code=code,
                                         production_per_1000=g.production_per_1000,
                                         consumption_mult=g.consumption_mult,
                                         stock=round(g.stock, 3), norm_stock=round(g.norm_stock, 3)))
        amount = econ_sim.starting_purse(groups, goods, pop) if purse == "start" else int(purse)
        if amount > 0:
            econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION, source_service=SOURCE, comment="тест",
                                       legs=[core.Leg(core.AccountRef.emission(), core.AccountRef.purse(region_id),
                                                      amount)])
        db.commit()
    finally:
        db.close()


def _fund_country(factory, country_id, amount):
    db = factory()
    try:
        econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION, source_service=SOURCE, comment="тест",
                                   legs=[core.Leg(core.AccountRef.emission(), core.AccountRef.country(country_id),
                                                  amount)])
        db.commit()
    finally:
        db.close()


def _world(factory, regions=(1, 2, 3)):
    for rid in regions:
        _add_region(factory, rid)
    _fund_country(factory, 1, COUNTRY_FUNDS)


def _rows(factory, sql, **params):
    db = factory()
    try:
        return [tuple(r) for r in db.execute(text(sql), params).fetchall()]
    finally:
        db.close()


def _scalar(factory, sql, **params):
    db = factory()
    try:
        return db.execute(text(sql), params).scalar()
    finally:
        db.close()


def _balance(factory, kind, ref_id):
    return int(_scalar(factory, "SELECT balance FROM econ_accounts WHERE kind = :k AND ref_id = :r",
                       k=kind, r=ref_id) or 0)


def _tick_ops(factory, run_id=None):
    """{region_id: count} of region_tick operations (of one run)."""
    sql = "SELECT region_id, COUNT(*) FROM econ_operations WHERE op_type = 'region_tick'"
    params = {}
    if run_id is not None:
        sql += " AND idempotency_key LIKE :k"
        params["k"] = f"region_tick:{run_id}:r:%"
    return dict(_rows(factory, sql + " GROUP BY region_id", **params))


def _assert_ledger_closes(factory):
    assert int(_scalar(factory, "SELECT COALESCE(SUM(balance), 0) FROM econ_accounts")) == 0
    negatives = _rows(factory, "SELECT kind, ref_id, balance FROM econ_accounts "
                               "WHERE allow_negative = 0 AND balance < 0")
    assert negatives == []


def _run_row(factory, run_id):
    return _rows(factory, "SELECT status, regions_total, regions_done, regions_failed, error, slot, trigger_kind "
                          "FROM econ_tick_runs WHERE id = :i", i=run_id)[0]


# --------------------------------------------------------------------------------------------- one op per region

def test_manual_run_posts_one_operation_per_region(factory):
    _world(factory)
    summary = econ_tick.run_tick(factory, trigger="manual", actor_user_id=5, now=T0)

    assert summary.status == "done" and summary.trigger == "manual" and summary.slot is None
    assert (summary.regions_total, summary.regions_done, summary.regions_failed) == (3, 3, 0)
    assert summary.operations_posted == 3
    assert _tick_ops(factory, summary.run_id) == {1: 1, 2: 1, 3: 1}
    keys = sorted(r[0] for r in _rows(factory, "SELECT idempotency_key FROM econ_operations "
                                               "WHERE op_type = 'region_tick'"))
    assert keys == [f"region_tick:{summary.run_id}:r:{rid}" for rid in (1, 2, 3)]

    status, total, done, failed, error, slot, trigger = _run_row(factory, summary.run_id)
    assert (status, total, done, failed, error, slot, trigger) == ("done", 3, 3, 0, None, None, "manual")
    assert _scalar(factory, "SELECT actor_user_id FROM econ_tick_runs WHERE id = :i", i=summary.run_id) == 5

    regions = _rows(factory, "SELECT region_id, last_run_id, last_tax, last_wages, last_income "
                             "FROM econ_regions ORDER BY region_id")
    assert [r[:2] for r in regions] == [(1, summary.run_id), (2, summary.run_id), (3, summary.run_id)]
    assert all(r[4] > 0 and r[2] > 0 for r in regions)                 # income and tax happened
    assert _rows(factory, "SELECT region_id, COUNT(*) FROM econ_region_history WHERE run_id = :r "
                          "GROUP BY region_id", r=summary.run_id) == [(1, 1), (2, 1), (3, 1)]
    _assert_ledger_closes(factory)


def test_region_tick_legs_and_metadata(factory):
    _world(factory, regions=(1,))
    purse_before = _balance(factory, "population_purse", 1)
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    tax, wages, grant = _rows(factory, "SELECT last_tax, last_wages, last_grant FROM econ_regions "
                                       "WHERE region_id = 1")[0]
    op_id, meta = _rows(factory, "SELECT id, metadata FROM econ_operations WHERE op_type = 'region_tick'")[0]
    meta = json.loads(meta) if isinstance(meta, str) else meta
    assert meta["run_id"] == summary.run_id
    assert (meta["tax"], meta["wages"], meta["grant"]) == (tax, wages, grant)
    assert _balance(factory, "population_purse", 1) == purse_before - tax + wages
    history = _rows(factory, "SELECT purse, treasury, tax, wages, grant_amount FROM econ_region_history")[0]
    assert history[0] == _balance(factory, "population_purse", 1)
    assert history[1] == _balance(factory, "region_treasury", 1)
    assert history[2:] == (tax, wages, grant)
    kinds = {(f, t) for f, t in _rows(factory, (
        "SELECT fa.kind, ta.kind FROM econ_postings p JOIN econ_accounts fa ON fa.id = p.from_account_id "
        "JOIN econ_accounts ta ON ta.id = p.to_account_id WHERE p.operation_id = :o"), o=op_id)}
    assert ("population_purse", "region_treasury") in kinds
    assert ("region_treasury", "population_purse") in kinds
    assert ("country_treasury", "region_treasury") in kinds            # the grant
    assert ("region_treasury", "country_treasury") in kinds            # country tax added by the ledger
    _assert_ledger_closes(factory)


def test_regions_outside_the_simulation_are_not_ticked(factory):
    _world(factory, regions=(1, 2, 3))
    db = factory()
    db.execute(text("UPDATE econ_regions SET template_code = NULL WHERE region_id = 2"))
    db.execute(text("UPDATE econ_regions SET population = 0 WHERE region_id = 3"))
    db.commit()
    db.close()
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert summary.regions_total == 1
    assert _tick_ops(factory) == {1: 1}
    assert _scalar(factory, "SELECT last_run_id FROM econ_regions WHERE region_id = 2") is None


def test_run_with_no_regions_is_done_and_empty(factory):
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert summary.status == "done" and summary.regions_total == 0
    assert _tick_ops(factory) == {}


# --------------------------------------------------------------------------------------------- auto / idempotency

def test_auto_rerun_in_the_same_slot_is_a_noop(factory):
    _world(factory)
    first = econ_tick.run_tick(factory, now=T0)
    assert first is not None and first.trigger == "auto" and first.slot == econ_tick.slot_of(T0)
    assert first.status == "done" and not first.resumed
    assert econ_tick.run_tick(factory, now=T0 + timedelta(minutes=20)) is None
    assert econ_tick.run_tick(factory, now=T0 + timedelta(hours=5, minutes=50)) is None   # same slot still
    assert _tick_ops(factory) == {1: 1, 2: 1, 3: 1}
    assert _scalar(factory, "SELECT COUNT(*) FROM econ_tick_runs") == 1

    second = econ_tick.run_tick(factory, now=T0 + timedelta(hours=6))
    assert second is not None and second.slot == first.slot + 1
    assert _tick_ops(factory) == {1: 2, 2: 2, 3: 2}
    _assert_ledger_closes(factory)


def test_slot_of_boundaries():
    assert econ_tick.slot_of(datetime(1970, 1, 1, 5, 59)) == 0
    assert econ_tick.slot_of(datetime(1970, 1, 1, 6, 0)) == 1
    assert econ_tick.slot_start(econ_tick.slot_of(T0)) == datetime(2026, 10, 28, 0, 0)


def _crash_on_call(monkeypatch, n):
    """Make the n-th region call die like a killed process (BaseException escapes the runner)."""
    original = econ_tick._process_region
    calls = {"n": 0}

    def crashing(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == n:
            raise KeyboardInterrupt("simulated process death")
        return original(*args, **kwargs)

    monkeypatch.setattr(econ_tick, "_process_region", crashing)
    return original


def test_resume_after_stale_heartbeat_processes_only_unfinished_regions(factory, monkeypatch):
    _world(factory, regions=(1, 2, 3, 4))
    original = _crash_on_call(monkeypatch, 3)
    with pytest.raises(KeyboardInterrupt):
        econ_tick.run_tick(factory, now=T0)
    run_id = _scalar(factory, "SELECT id FROM econ_tick_runs WHERE slot = :s", s=econ_tick.slot_of(T0))
    status, total, done, *_ = _run_row(factory, run_id)
    assert (status, total, done) == ("running", 4, 2)
    assert _tick_ops(factory, run_id) == {1: 1, 2: 1}
    monkeypatch.setattr(econ_tick, "_process_region", original)

    # heartbeat still fresh (5 min) -> the run belongs to a live process
    assert econ_tick.run_tick(factory, now=T0 + timedelta(minutes=5)) is None

    seen = []

    def spy(*args, **kwargs):
        outcome = original(*args, **kwargs)
        seen.append((kwargs["region_id"], outcome.status))
        return outcome

    monkeypatch.setattr(econ_tick, "_process_region", spy)
    resumed = econ_tick.run_tick(factory, now=T0 + timedelta(minutes=15))
    assert resumed is not None and resumed.resumed and resumed.run_id == run_id
    assert seen == [(1, "already"), (2, "already"), (3, "done"), (4, "done")]
    assert resumed.status == "done" and resumed.regions_done == 4 and resumed.operations_posted == 2
    assert _tick_ops(factory, run_id) == {1: 1, 2: 1, 3: 1, 4: 1}
    assert _rows(factory, "SELECT region_id, COUNT(*) FROM econ_region_history GROUP BY region_id") == \
        [(1, 1), (2, 1), (3, 1), (4, 1)]
    assert _run_row(factory, run_id)[0] == "done"
    # the finished slot is not run a third time
    assert econ_tick.run_tick(factory, now=T0 + timedelta(minutes=40)) is None
    _assert_ledger_closes(factory)


def test_resume_keeps_the_original_grant_plan(factory, monkeypatch):
    _world(factory, regions=(1, 2))
    original = _crash_on_call(monkeypatch, 2)
    with pytest.raises(KeyboardInterrupt):
        econ_tick.run_tick(factory, now=T0)
    plan_before = _scalar(factory, "SELECT grant_plan FROM econ_tick_runs")
    _fund_country(factory, 1, 900_000)                 # more money arrives in between
    monkeypatch.setattr(econ_tick, "_process_region", original)
    econ_tick.run_tick(factory, now=T0 + timedelta(minutes=15))
    assert _scalar(factory, "SELECT grant_plan FROM econ_tick_runs") == plan_before
    plan = plan_before if isinstance(plan_before, dict) else json.loads(plan_before)
    assert _scalar(factory, "SELECT last_grant FROM econ_regions WHERE region_id = 2") == plan["2"]


def test_dead_manual_run_is_closed_by_the_next_claim(factory):
    _world(factory, regions=(1,))
    db = factory()
    dead = models.EconTickRun(slot=None, trigger_kind="manual", status="running", regions_done=0,
                              started_at=T0 - timedelta(hours=2), heartbeat_at=T0 - timedelta(hours=2))
    db.add(dead)
    db.commit()
    dead_id = dead.id
    db.close()
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert summary.status == "done"
    status, *_rest = _run_row(factory, dead_id)
    assert status == "failed"
    assert _scalar(factory, "SELECT error FROM econ_tick_runs WHERE id = :i", i=dead_id) == econ_tick.INTERRUPTED_ERROR


# --------------------------------------------------------------------------------------------- duplicate / failures

def test_duplicate_operation_counts_the_region_as_done(factory):
    _world(factory)
    # An overlapping runner already posted region 2 of run 1 (the first run id of a fresh database).
    db = factory()
    db.execute(text("INSERT INTO econ_operations (op_type, idempotency_key, region_id, source_service, created_at) "
                    "VALUES ('region_tick', 'region_tick:1:r:2', 2, 'character-service', :t)"), {"t": T0})
    db.commit()
    db.close()
    stock_before = _rows(factory, "SELECT group_code, stock FROM econ_region_goods WHERE region_id = 2 "
                                  "ORDER BY group_code")
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert summary.run_id == 1
    assert summary.status == "done" and summary.regions_done == 3 and summary.regions_failed == 0
    assert summary.operations_posted == 2
    # region 2 was rolled back: no second posting, state untouched
    assert _tick_ops(factory, 1) == {1: 1, 2: 1, 3: 1}
    assert _scalar(factory, "SELECT last_run_id FROM econ_regions WHERE region_id = 2") is None
    assert _rows(factory, "SELECT group_code, stock FROM econ_region_goods WHERE region_id = 2 "
                          "ORDER BY group_code") == stock_before
    assert _scalar(factory, "SELECT COUNT(*) FROM econ_region_history WHERE region_id = 2") == 0


def _fail_region(monkeypatch, failing):
    original = econ_sim.simulate_region

    def maybe_fail(region, goods, groups, **kwargs):
        if region.population in failing:
            raise RuntimeError("broken region data")
        return original(region, goods, groups, **kwargs)

    monkeypatch.setattr(econ_sim, "simulate_region", maybe_fail)


def test_failing_region_is_isolated_and_run_is_partial(factory, monkeypatch):
    _add_region(factory, 1, population=2500)
    _add_region(factory, 2, population=2501)
    _add_region(factory, 3, population=2502)
    _fund_country(factory, 1, COUNTRY_FUNDS)
    purse_before = _balance(factory, "population_purse", 2)
    stock_before = _rows(factory, "SELECT group_code, stock FROM econ_region_goods WHERE region_id = 2 "
                                  "ORDER BY group_code")
    _fail_region(monkeypatch, {2501 * SCALE})

    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert summary.status == "partial"
    assert (summary.regions_done, summary.regions_failed, summary.failed_region_ids) == (2, 1, [2])
    status, _total, done, failed, error, *_ = _run_row(factory, summary.run_id)
    assert (status, done, failed) == ("partial", 2, 1)
    assert "2" in error
    assert _tick_ops(factory) == {1: 1, 3: 1}
    assert _balance(factory, "population_purse", 2) == purse_before
    assert _scalar(factory, "SELECT last_run_id FROM econ_regions WHERE region_id = 2") is None
    assert _rows(factory, "SELECT group_code, stock FROM econ_region_goods WHERE region_id = 2 "
                          "ORDER BY group_code") == stock_before
    _assert_ledger_closes(factory)

    # fixed next time: the region ticks normally
    monkeypatch.undo()
    assert econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=30)).status == "done"
    assert _tick_ops(factory) == {1: 2, 2: 1, 3: 2}


def test_all_regions_failing_marks_the_run_failed(factory, monkeypatch):
    _add_region(factory, 1, population=2500)
    _add_region(factory, 2, population=2501)
    _fail_region(monkeypatch, {2500 * SCALE, 2501 * SCALE})
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert summary.status == "failed" and summary.regions_failed == 2 and summary.regions_done == 0
    assert _run_row(factory, summary.run_id)[0] == "failed"
    _assert_ledger_closes(factory)


def test_insufficient_purse_rolls_the_region_back(factory, monkeypatch, caplog):
    """A purse drained between reading and posting (admin adjust race) -> InsufficientFunds -> region failed."""
    _add_region(factory, 1, country_id=2)        # no grant -> wages cannot cover the tax on an empty purse
    _add_region(factory, 2)
    _fund_country(factory, 1, COUNTRY_FUNDS)
    original = econ_tick.account_balance

    def stale_balance(session, ref):
        value = original(session, ref)
        if ref.kind == core.AccountRef.purse(1).kind and ref.ref_id == 1:
            return value + 10**9                  # the sim believes the purse is huge
        return value

    db = factory()
    db.execute(text("UPDATE econ_regions SET tax_rate = 0.5 WHERE region_id = 1"))
    db.commit()
    db.close()
    purse_before = _balance(factory, "population_purse", 1)
    monkeypatch.setattr(econ_tick, "account_balance", stale_balance)
    # make the tax exceed the real purse: empty it right before the run
    db = factory()
    econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION, source_service=SOURCE, comment="тест",
                               legs=[core.Leg(core.AccountRef.purse(1), core.AccountRef.emission(), purse_before)])
    db.commit()
    db.close()

    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert summary.failed_region_ids == [1] and summary.status == "partial"
    assert "InsufficientFunds" in caplog.text
    assert _balance(factory, "population_purse", 1) == 0
    assert _tick_ops(factory) == {2: 1}
    _assert_ledger_closes(factory)


def test_purses_and_treasuries_never_go_negative_over_many_runs(factory):
    _add_region(factory, 1, template="fortress")
    _add_region(factory, 2, template="rural", purse=0, country_id=2)   # broke, and its country has no money
    _add_region(factory, 3, template="port", country_id=2)
    _fund_country(factory, 1, COUNTRY_FUNDS)
    for i in range(12):
        summary = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=30 * i))
        assert summary.status == "done"
        for rid in (1, 2, 3):
            assert _balance(factory, "population_purse", rid) >= 0
            assert _balance(factory, "region_treasury", rid) >= 0
        assert _balance(factory, "country_treasury", 1) >= 0
        _assert_ledger_closes(factory)
    hunger = dict(_rows(factory, "SELECT region_id, hunger FROM econ_regions"))
    assert float(hunger[2]) > 0.5                                       # an empty purse cannot buy food


# --------------------------------------------------------------------------------------------- grants

def test_grant_plan_splits_country_money_by_population(factory):
    _add_region(factory, 1, population=1000)
    _add_region(factory, 2, population=3000)
    _add_region(factory, 3, population=2000, country_id=2)
    _fund_country(factory, 1, COUNTRY_FUNDS)

    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    plan = _scalar(factory, "SELECT grant_plan FROM econ_tick_runs WHERE id = :i", i=summary.run_id)
    plan = plan if isinstance(plan, dict) else json.loads(plan)
    assert plan == {"1": 6250, "2": 18750, "3": 0}
    assert sum(plan.values()) <= COUNTRY_FUNDS * econ_sim.DEFAULT_PARAMS.country_grant_share
    grants = dict(_rows(factory, "SELECT region_id, last_grant FROM econ_regions"))
    assert grants == {1: 6250, 2: 18750, 3: 0}
    country_tax_in = int(_scalar(factory, (
        "SELECT COALESCE(SUM(p.amount), 0) FROM econ_postings p JOIN econ_accounts ta ON ta.id = p.to_account_id "
        "JOIN econ_operations o ON o.id = p.operation_id "
        "WHERE o.op_type = 'region_tick' AND ta.kind = 'country_treasury' AND ta.ref_id = 1")))
    assert country_tax_in > 0
    assert _balance(factory, "country_treasury", 1) == COUNTRY_FUNDS - 25_000 + country_tax_in
    _assert_ledger_closes(factory)


# --------------------------------------------------------------------------------------------- housekeeping

def test_orphan_economy_rows_are_purged(factory):
    _world(factory, regions=(1,))
    _add_region(factory, 99, world_row=False, purse=0)                 # its Regions row is gone
    assert _scalar(factory, "SELECT COUNT(*) FROM econ_region_goods WHERE region_id = 99") == 12
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert summary.regions_total == 1 and summary.status == "done"
    assert _scalar(factory, "SELECT COUNT(*) FROM econ_regions WHERE region_id = 99") == 0
    assert _scalar(factory, "SELECT COUNT(*) FROM econ_region_goods WHERE region_id = 99") == 0
    assert _scalar(factory, "SELECT COUNT(*) FROM econ_regions WHERE region_id = 1") == 1


def test_history_older_than_retention_is_purged(factory):
    _world(factory, regions=(1,))
    db = factory()
    old_run = models.EconTickRun(slot=None, trigger_kind="manual", status="done", started_at=T0 - timedelta(days=70),
                                 heartbeat_at=T0 - timedelta(days=70))
    db.add(old_run)
    db.flush()
    for days in (61, 59):
        db.add(models.EconRegionHistory(run_id=old_run.id, region_id=1, created_at=T0 - timedelta(days=days),
                                        population=1, stability=70, prosperity=50, hunger=0, purse=0, treasury=0,
                                        income=0, tax=0, wages=0, grant_amount=0, goods={}))
    db.commit()
    db.close()
    econ_tick.run_tick(factory, trigger="manual", now=T0)
    created = [str(r[0])[:10] for r in _rows(factory, "SELECT created_at FROM econ_region_history "
                                                      "ORDER BY created_at")]
    assert created == [str((T0 - timedelta(days=59)).date()), str(T0.date())]   # the 61-day row is gone


def test_custom_retention_param_is_respected(factory):
    _world(factory, regions=(1,))
    db = factory()
    db.query(models.EconSimSettings).filter_by(id=1).update(
        {"params": dict(mig.DEFAULT_PARAMS, history_retention_days=5)})
    old_run = models.EconTickRun(slot=None, trigger_kind="manual", status="done", started_at=T0 - timedelta(days=9),
                                 heartbeat_at=T0 - timedelta(days=9))
    db.add(old_run)
    db.flush()
    db.add(models.EconRegionHistory(run_id=old_run.id, region_id=1, created_at=T0 - timedelta(days=6),
                                    population=1, stability=70, prosperity=50, hunger=0, purse=0, treasury=0,
                                    income=0, tax=0, wages=0, grant_amount=0, goods={}))
    db.commit()
    db.close()
    econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert _scalar(factory, "SELECT COUNT(*) FROM econ_region_history") == 1     # only the new row


# --------------------------------------------------------------------------------------------- manual / scheduler

def test_run_manual_refuses_while_a_fresh_run_is_alive(factory):
    _world(factory, regions=(1,))
    db = factory()
    alive = models.EconTickRun(slot=None, trigger_kind="manual", status="running",
                               started_at=econ_tick._utcnow(), heartbeat_at=econ_tick._utcnow())
    db.add(alive)
    db.commit()
    alive_id = alive.id
    db.close()
    with pytest.raises(econ_tick.RunInProgress) as exc:
        econ_tick.run_manual(actor_user_id=1, session_factory=factory)
    assert exc.value.run_id == alive_id
    assert _tick_ops(factory) == {}
    assert _scalar(factory, "SELECT COUNT(*) FROM econ_tick_runs") == 1


def test_run_manual_runs_when_nothing_is_alive(factory):
    _world(factory, regions=(1, 2))
    summary = econ_tick.run_manual(actor_user_id=3, session_factory=factory)
    assert summary.trigger == "manual" and summary.status == "done" and summary.regions_done == 2
    assert summary.to_dict()["started_at"]


def test_unknown_trigger_is_rejected(factory):
    with pytest.raises(ValueError):
        econ_tick.run_tick(factory, trigger="cron")


def test_scheduler_not_started_without_env(monkeypatch):
    monkeypatch.delenv(econ_scheduler.ENV_ENABLED, raising=False)
    assert econ_scheduler.start_scheduler() is False
    assert not econ_scheduler.is_running()
    monkeypatch.setenv(econ_scheduler.ENV_ENABLED, "0")
    assert econ_scheduler.start_scheduler() is False


def test_scheduler_not_started_under_pytest_even_with_env(monkeypatch):
    monkeypatch.setenv(econ_scheduler.ENV_ENABLED, "true")
    assert econ_scheduler.start_scheduler() is False
    assert not econ_scheduler.is_running()


def test_scheduler_starts_one_thread_when_explicitly_allowed(monkeypatch, factory):
    monkeypatch.setenv(econ_scheduler.ENV_ENABLED, "1")
    try:
        assert econ_scheduler.start_scheduler(factory, first_delay=3600, allow_under_pytest=True) is True
        assert econ_scheduler.is_running()
        assert econ_scheduler.start_scheduler(factory, first_delay=3600, allow_under_pytest=True) is False
    finally:
        econ_scheduler.stop_scheduler(timeout=5)
    assert not econ_scheduler.is_running()


def test_poll_seconds_env(monkeypatch):
    monkeypatch.delenv(econ_scheduler.ENV_POLL_SECONDS, raising=False)
    assert econ_scheduler.poll_seconds() == econ_scheduler.DEFAULT_POLL_SECONDS
    monkeypatch.setenv(econ_scheduler.ENV_POLL_SECONDS, "1")
    assert econ_scheduler.poll_seconds() == econ_scheduler.MIN_POLL_SECONDS
    monkeypatch.setenv(econ_scheduler.ENV_POLL_SECONDS, "abc")
    assert econ_scheduler.poll_seconds() == econ_scheduler.DEFAULT_POLL_SECONDS


def test_scheduled_iteration_respects_db_switch(factory):
    _world(factory, regions=(1,))
    db = factory()
    db.query(models.EconSimSettings).filter_by(id=1).update({"tick_enabled": False})
    db.commit()
    db.close()
    assert econ_scheduler.run_scheduled_once(factory) is None
    assert _scalar(factory, "SELECT COUNT(*) FROM econ_tick_runs") == 0

    db = factory()
    db.query(models.EconSimSettings).filter_by(id=1).update({"tick_enabled": True})
    db.commit()
    db.close()
    summary = econ_scheduler.run_scheduled_once(factory)
    assert summary is not None and summary.trigger == "auto" and summary.status == "done"
    assert econ_scheduler.run_scheduled_once(factory) is None          # same wall-clock slot
    assert _tick_ops(factory) == {1: 1}
