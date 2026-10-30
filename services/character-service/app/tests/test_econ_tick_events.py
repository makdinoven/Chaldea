"""FEAT-187 B3: region events in the economy tick (``econ_tick._events_pass`` / ``_process_region`` /
``economy_events_crud.start_event``) on SQLite. QA extends these in ``test_econ_events_tick.py``."""

import importlib.util
import json
import os
from datetime import timedelta

import pytest
from sqlalchemy import text

import econ_events
import econ_sim
import econ_tick
import economy_events_crud as ev_crud
import locations_client
import models
from tests.test_econ_tick import (  # noqa: F401  (factory is a fixture)
    T0, _add_region, _assert_ledger_closes, _balance, _rows, _scalar, factory,
)

_spec = importlib.util.spec_from_file_location(
    "migration_033_for_tick_events",
    os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "033_econ_region_events.py"))
mig033 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig033)

SLOT0 = econ_tick.slot_of(T0)


@pytest.fixture(autouse=True)
def calendar(monkeypatch):
    """No HTTP in tests: the calendar answers 'summer' unless a test changes ``calendar['segment']``."""
    state = {"segment": "summer", "calls": 0}

    def fake():
        state["calls"] += 1
        return state["segment"]

    monkeypatch.setattr(locations_client, "get_game_segment_sync", fake)
    return state


def _seed_templates(factory, only=None, **overrides):
    db = factory()
    try:
        for t in mig033.EVENT_TEMPLATES:
            if only is not None and t["code"] not in only:
                continue
            data = dict(t)
            data.update(overrides.get(t["code"], {}))
            db.add(models.EconEventTemplate(**data))
        db.commit()
    finally:
        db.close()


def _add_template(factory, code, effects, **kw):
    db = factory()
    try:
        data = {"code": code, "name": code.title(), "icon": "alert", "kind": "bad", "player_text": "текст",
                "trigger_kind": "random", "weight": 1, "duration_min_days": 2, "duration_max_days": 2,
                "scope": "region", "spread_chance": 0, "effects": effects}
        data.update(kw)
        db.add(models.EconEventTemplate(**data))
        db.commit()
    finally:
        db.close()


def _set_params(factory, **values):
    db = factory()
    try:
        row = db.get(models.EconSimSettings, 1)
        params = dict(row.params)
        params.update(values)
        row.params = params
        db.commit()
    finally:
        db.close()


def _start(factory, code, region_id, *, now=T0, days=None, origin="manual", key=None, scope=None):
    db = factory()
    try:
        tpl = db.query(models.EconEventTemplate).filter_by(code=code).one()
        res = ev_crud.start_event(db, tpl, region_id, origin=origin, origin_key=key, now=now, scope=scope,
                                  duration_seconds=None if days is None else int(days * 86400))
        db.commit()
        return [int(r.id) for r in res.started], res.skipped
    finally:
        db.close()


def _events(factory):
    return _rows(factory, "SELECT id, region_id, template_code, origin, status, origin_key, parent_event_id, "
                          "generation FROM econ_region_events ORDER BY id")


def _stock(factory, region_id, group):
    return float(_scalar(factory, "SELECT stock FROM econ_region_goods WHERE region_id = :r AND group_code = :g",
                         r=region_id, g=group))


# --------------------------------------------------------------------------------------------- one-shots


def test_manual_start_applies_one_shots_once_and_posts_region_event(factory):
    _add_region(factory, 1, template="agrarian")
    _seed_templates(factory, only={"flood", "plague"})
    _start(factory, "flood", 1, days=5)
    _start(factory, "plague", 1, days=5)
    food_before = _stock(factory, 1, "food")
    pop_before = int(_scalar(factory, "SELECT population FROM econ_regions WHERE region_id = 1"))

    first = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=10))
    assert first.events_applied == 2 and first.event_expense_ops == 2       # both carry a treasury expense
    assert first.events_started == first.events_spread == first.events_chained == first.riots_started == 0

    flood = _rows(factory, "SELECT applied_at, applied_run_id, outcome FROM econ_region_events "
                           "WHERE template_code = 'flood'")[0]
    assert flood[1] == first.run_id
    outcome = json.loads(flood[2]) if isinstance(flood[2], str) else flood[2]
    assert outcome["stock_lost"]["food"] == pytest.approx(food_before * 0.25, abs=0.01)
    assert outcome["treasury_expense"] > 0 and outcome["operation_id"]
    op = _rows(factory, "SELECT op_type, idempotency_key, region_id FROM econ_operations WHERE id = :i",
               i=outcome["operation_id"])[0]
    assert op[0] == "region_event" and op[2] == 1
    legs = _rows(factory, "SELECT a1.kind, a2.kind, l.amount, l.leg_type FROM econ_postings l "
                          "JOIN econ_accounts a1 ON a1.id = l.from_account_id "
                          "JOIN econ_accounts a2 ON a2.id = l.to_account_id WHERE l.operation_id = :i",
                 i=outcome["operation_id"])
    assert [(a, b, n) for a, b, n, _t in legs] == [("region_treasury", "population_purse", outcome["treasury_expense"])]

    pop = _rows(factory, "SELECT population_before, population_after FROM econ_region_events "
                         "WHERE template_code = 'plague'")[0]
    assert pop[0] == pop_before and pop[1] < pop_before
    assert int(_scalar(factory, "SELECT population FROM econ_regions WHERE region_id = 1")) == pop[1]

    second = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=30))
    assert second.events_applied == 0 and second.event_expense_ops == 0
    assert _scalar(factory, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'region_event'") == 2
    assert int(_scalar(factory, "SELECT population FROM econ_regions WHERE region_id = 1")) == pop[1]
    _assert_ledger_closes(factory)


def test_empty_treasury_spends_nothing(factory):
    _add_region(factory, 1, template="agrarian", purse=0)
    _add_template(factory, "fix", [{"type": "treasury_expense", "share": 0.5}])
    _start(factory, "fix", 1, days=3)
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=10))
    assert summary.events_applied == 1 and summary.event_expense_ops == 0
    assert _scalar(factory, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'region_event'") == 0
    _assert_ledger_closes(factory)


def test_per_step_mods_change_the_region_and_without_events_nothing_changes(factory):
    _add_region(factory, 1, template="agrarian")
    _add_region(factory, 2, template="agrarian")
    _add_template(factory, "dear", [{"type": "price", "groups": ["*"], "mult": 3.0},
                                    {"type": "stability", "delta": -5}])
    _start(factory, "dear", 1, days=3)
    econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=10))
    rows = dict(_rows(factory, "SELECT region_id, stability FROM econ_regions"))
    assert float(rows[1]) < float(rows[2])
    price = dict(_rows(factory, "SELECT region_id, price_mult FROM econ_region_goods WHERE group_code = 'food'"))
    assert float(price[1]) > float(price[2])


# --------------------------------------------------------------------------------------------- time & rolls


def test_manual_runs_never_roll_and_expiry_is_by_clock(factory):
    _add_region(factory, 1)
    _add_template(factory, "often", [{"type": "stability", "delta": -1}])
    _set_params(factory, event_rate_per_season=10, event_season_days=1)
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert summary.events_started == 0 and _events(factory) == []

    _start(factory, "often", 1, days=1)
    still = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(hours=12))
    assert still.events_ended == 0
    later = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(days=2))
    assert later.events_ended == 1
    status, ended_at, ends_at, key = _rows(factory, "SELECT status, ended_at, ends_at, active_key "
                                                    "FROM econ_region_events")[0]
    assert status == "ended" and ended_at == ends_at and key is None


def test_scheduled_run_rolls_at_most_one_random_per_region_and_resume_inserts_nothing(factory, calendar):
    for rid in (1, 2, 3):
        _add_region(factory, rid, template="agrarian")
    _seed_templates(factory)
    _set_params(factory, event_rate_per_season=10, event_season_days=1)

    summary = econ_tick.run_tick(factory, now=T0)
    events = _events(factory)
    randoms = [e for e in events if e[3] == "random"]
    assert summary.events_started == len(randoms) >= 1
    assert sorted(e[5] for e in randoms if e[5].count(":") == 2) == \
        sorted(f"auto:{SLOT0}:r{rid}" for rid in {e[1] for e in randoms if e[5].count(":") == 2})
    roots = [e for e in randoms if e[5].count(":") == 2]
    assert len(roots) == len({e[1] for e in roots}) <= 3
    assert calendar["calls"] == 1                                   # one calendar call per scheduled run
    segments = {r[0] for r in _rows(factory, "SELECT game_segment FROM econ_region_events")}
    assert segments == {"summer"}

    # a resumed run of the same slot repeats the same rolls and inserts nothing twice
    again = econ_tick.RunSummary(run_id=summary.run_id, trigger="auto", slot=SLOT0, status="running")
    params = econ_tick.load_params(factory())
    econ_tick._events_pass(factory, summary.run_id, SLOT0, again, params, T0, {})
    assert _events(factory) == events
    assert again.events_started == 0
    _assert_ledger_closes(factory)


def test_unknown_season_rolls_only_season_free_templates(factory, calendar):
    _add_region(factory, 1, template="agrarian")
    _add_template(factory, "summer_only", [{"type": "stability", "delta": -1}], seasons=["summer"], weight=100)
    _add_template(factory, "any_time", [{"type": "stability", "delta": -1}], weight=1)
    _set_params(factory, event_rate_per_season=10, event_season_days=1)
    calendar["segment"] = None
    econ_tick.run_tick(factory, now=T0)
    assert [e[2] for e in _events(factory)] == ["any_time"]
    assert _scalar(factory, "SELECT game_segment FROM econ_region_events") is None


def test_events_disabled_stops_automatic_starts(factory):
    _add_region(factory, 1)
    _add_template(factory, "often", [{"type": "stability", "delta": -1}])
    _set_params(factory, event_rate_per_season=10, event_season_days=1, events_enabled=0)
    econ_tick.run_tick(factory, now=T0)
    assert _events(factory) == []


# --------------------------------------------------------------------------------------------- spread / chain / riot


def _arrows(factory, pairs):
    db = factory()
    try:
        db.execute(text("CREATE TABLE IF NOT EXISTS region_transition_arrows (id INTEGER PRIMARY KEY, "
                        "region_id BIGINT NOT NULL, target_region_id BIGINT NOT NULL)"))
        for a, b in pairs:
            db.execute(text("INSERT INTO region_transition_arrows (region_id, target_region_id) VALUES (:a, :b)"),
                       {"a": a, "b": b})
        db.commit()
    finally:
        db.close()


def test_spread_goes_to_an_arrow_neighbour_and_chain_starts_in_place(factory):
    for rid in (1, 2, 3):
        _add_region(factory, rid)
    _arrows(factory, [(2, 1)])                       # 1 <-> 2 by arrow (reverse direction); 3 is only same-country
    _add_template(factory, "plague2", [{"type": "stability", "delta": -1}], trigger_kind="manual")
    _add_template(factory, "flood2", [{"type": "stability", "delta": -1}], trigger_kind="manual",
                  spread_chance=1, chains=[{"code": "plague2", "chance": 1}])
    _set_params(factory, event_rate_per_season=0)
    (source,), _ = _start(factory, "flood2", 1, days=4, now=T0 - timedelta(hours=1))

    summary = econ_tick.run_tick(factory, now=T0)
    assert (summary.events_spread, summary.events_chained) == (1, 1)
    rows = {(e[1], e[2]): e for e in _events(factory)}
    spread = rows[(2, "flood2")]
    assert spread[3] == "spread" and spread[6] == source and spread[7] == 1
    assert spread[5] == f"spread:{SLOT0}:e{source}"
    chain = rows[(1, "plague2")]
    assert chain[3] == "chain" and chain[6] == source and chain[5] == f"chain:{SLOT0}:e{source}:plague2"
    assert (3, "flood2") not in rows


def test_neighbours_fall_back_to_same_country_without_arrows(factory):
    _add_region(factory, 1)
    _add_region(factory, 2)
    _add_region(factory, 3, country_id=2)
    db = factory()
    try:
        regions = ev_crud.load_event_regions(db)
        assert ev_crud.neighbour_map(db, regions) == {1: [2], 2: [1], 3: []}
    finally:
        db.close()


def test_riot_after_long_low_stability(factory):
    _add_region(factory, 1)
    _seed_templates(factory, only={"riot"})
    _set_params(factory, event_rate_per_season=0)
    db = factory()
    try:
        db.execute(text("UPDATE econ_regions SET low_stability_since = :t, stability = 5"),
                   {"t": T0 - timedelta(days=4)})
        db.commit()
    finally:
        db.close()
    summary = econ_tick.run_tick(factory, now=T0)
    assert summary.riots_started == 1
    assert [(e[2], e[3], e[5]) for e in _events(factory)] == [("riot", "riot", f"riot:{SLOT0}:r1")]


def test_riot_clock_is_set_and_cleared_by_the_tick(factory):
    _add_region(factory, 1)
    _set_params(factory, event_riot_stability=101)        # everything counts as low
    econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert _scalar(factory, "SELECT low_stability_since FROM econ_regions") is not None
    _set_params(factory, event_riot_stability=0)
    econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=30))
    assert _scalar(factory, "SELECT low_stability_since FROM econ_regions") is None


# --------------------------------------------------------------------------------------------- start_event


def test_start_event_scope_country_skips_active_and_refuses_duplicates(factory):
    for rid in (1, 2, 3):
        _add_region(factory, rid)
    _add_template(factory, "fair", [{"type": "prosperity", "delta": 1}], kind="good", scope="country")
    _start(factory, "fair", 2, days=1, scope="region")
    ids, skipped = _start(factory, "fair", 1, days=2, key="manual:abc")
    assert len(ids) == 2 and [s[2] for s in skipped] == [ev_crud.SKIP_ALREADY_ACTIVE]
    rows = _rows(factory, "SELECT id, region_id, root_event_id, origin_key, ends_at FROM econ_region_events "
                          "WHERE origin_key LIKE 'manual:abc%' ORDER BY id")
    assert [r[1] for r in rows] == [1, 3] and rows[0][2] is None and rows[1][2] == rows[0][0]
    assert rows[1][3] == "manual:abc:r3" and rows[0][4] == rows[1][4]
    assert _start(factory, "fair", 1, key="manual:abc")[1][0][2] == ev_crud.SKIP_DUPLICATE


def test_missing_event_tables_do_not_stop_the_tick(factory):
    _add_region(factory, 1)
    db = factory()
    try:
        db.execute(text("DROP TABLE econ_region_events"))
        db.commit()
    finally:
        db.close()
    summary = econ_tick.run_tick(factory, now=T0)
    assert summary.status == "done" and summary.regions_done == 1 and summary.events_failed == 0
    _assert_ledger_closes(factory)


def test_pure_helpers_used_by_the_tick():
    assert econ_events.tick_chance(econ_sim.SimParams(event_rate_per_season=10, event_season_days=1)) == 1.0
    assert ev_crud.active_key(7, "flood") == "r7:flood"
