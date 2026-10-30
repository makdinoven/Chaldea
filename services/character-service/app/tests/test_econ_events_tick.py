"""FEAT-187 Q2: region events in the economy tick on SQLite — extends B3's ``test_econ_tick_events.py``.

Covered here (not repeated from B3's file): exact seeded rolls, resume after a crash through ``run_tick``, wall-clock
expiry in auto runs, spreading in both arrow directions / same-country fallback / depth / snapshot, chains (limits,
disabled targets), the riot clock by time + cooldown, one-shots exactly once (population +/- with the floor, stock loss
of every group, treasury expense formula), stacking caps, merchants halt / bank panic / loan boom per region,
calendar fail-soft (real ``get_game_segment_sync`` over a broken transport), non-participating regions, a failing
events pass, ``RunSummary`` counters. Every scenario ends with the world sum 0 and the admin summary invariant ``ok``.
"""

import dataclasses
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import text

import econ_core as core
import econ_events
import econ_ledger
import econ_tick
import economy_bank_crud as bank_crud
import economy_crud
import economy_events_crud as ev_crud
import locations_client
import models
from tests.test_econ_tick import (  # noqa: F401  (factory is a fixture)
    SCALE, T0, _add_region, _assert_ledger_closes, _balance, _rows, _scalar, factory,
)
from tests.test_econ_tick_events import (  # noqa: F401  (calendar is an autouse fixture)
    _add_template, _arrows, _events, _set_params, _start, _stock, calendar,
)

SLOT0 = econ_tick.slot_of(T0)
HOUR = timedelta(hours=6)              # one scheduled slot
REAL_GET_SEGMENT = locations_client.get_game_segment_sync    # captured before the autouse fixture patches it
AUCTION_DDL = [
    "CREATE TABLE IF NOT EXISTS auction_listings (id INTEGER PRIMARY KEY, current_bid INTEGER, "
    "current_bidder_id INTEGER NULL, status VARCHAR(20))",
    "CREATE TABLE IF NOT EXISTS auction_storage (id INTEGER PRIMARY KEY, gold_amount INTEGER)",
]
STAB = [{"type": "stability", "delta": -1}]


def _slot(k):
    """Clock of the k-th scheduled slot after T0's (same offset into the slot)."""
    return T0 + HOUR * k


def _check(factory):
    """World sum 0, no negative non-source account, admin summary invariant ``ok``."""
    _assert_ledger_closes(factory)
    db = factory()
    try:
        for ddl in AUCTION_DDL:
            db.execute(text(ddl))
        db.commit()
        invariant = economy_crud.get_summary(db)["invariant"]
    finally:
        db.close()
    assert invariant["ok"] and invariant["ledger_sum"] == 0, invariant


def _event(factory, **filters):
    db = factory()
    try:
        q = db.query(models.EconRegionEvent)
        for k, v in filters.items():
            q = q.filter(getattr(models.EconRegionEvent, k) == v)
        rows = q.order_by(models.EconRegionEvent.id).all()
        for r in rows:
            db.expunge(r)
        return rows
    finally:
        db.close()


def _population(factory, region_id):
    return int(_scalar(factory, "SELECT population FROM econ_regions WHERE region_id = :r", r=region_id))


def _set_region(factory, region_id, **values):
    db = factory()
    try:
        row = db.get(models.EconRegion, region_id)
        for k, v in values.items():
            setattr(row, k, v)
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------------------------- rolls


def test_scheduled_rolls_are_exactly_the_seeded_ones(factory):
    """Region r's random start = rng_for(slot, r, 'auto'): random() -> pick_weighted(eligible) -> duration."""
    for rid, tpl in ((1, "agrarian"), (2, "rural"), (3, "agrarian"), (4, "rural")):
        _add_region(factory, rid, template=tpl)
    specs = [("a_any", 1, 1, 5, None), ("b_heavy", 5, 2, 3, None), ("c_agr", 3, 1, 2, ["agrarian"]),
             ("d_winter", 50, 1, 1, None)]
    for code, weight, lo, hi, region_templates in specs:
        _add_template(factory, code, STAB, weight=weight, duration_min_days=lo, duration_max_days=hi,
                      region_templates=region_templates, seasons=["winter"] if code == "d_winter" else None)
    _set_params(factory, event_rate_per_season=10, event_season_days=1)

    summary = econ_tick.run_tick(factory, now=T0)

    tpls = [{"code": c, "is_enabled": True, "trigger_kind": "random", "weight": w, "region_templates": rt,
             "seasons": ["winter"] if c == "d_winter" else None, "lo": lo, "hi": hi}
            for c, w, lo, hi, rt in specs]
    expected = {}
    for rid, tpl in ((1, "agrarian"), (2, "rural"), (3, "agrarian"), (4, "rural")):
        rng = econ_events.rng_for(SLOT0, rid, "auto")
        assert rng.random() < 1.0
        pick = econ_events.pick_weighted(rng, econ_events.eligible(tpls, region_template=tpl, segment="summer",
                                                                    active_codes=[]))
        expected[rid] = (pick["code"], T0 + timedelta(seconds=econ_events.roll_duration_seconds(
            rng, pick["lo"], pick["hi"])))
    got = {e.region_id: (e.template_code, e.ends_at) for e in _event(factory)}
    assert got == expected
    assert all(code != "d_winter" for code, _ in got.values())          # summer: the winter template never rolls
    assert all(code != "c_agr" for rid, (code, _) in got.items() if rid in (2, 4))
    assert summary.events_started == 4
    assert {e.origin_key for e in _event(factory)} == {f"auto:{SLOT0}:r{r}" for r in (1, 2, 3, 4)}
    assert {e.run_id for e in _event(factory)} == {summary.run_id}
    _check(factory)


def test_crash_and_resume_through_run_tick_inserts_nothing_twice_and_applies_once(factory, monkeypatch):
    for rid in (1, 2, 3):
        _add_region(factory, rid, template="agrarian")
    _add_template(factory, "fix", [{"type": "treasury_expense", "share": 0.2},
                                   {"type": "stock_loss", "groups": ["food"], "share": 0.1}],
                  duration_min_days=1, duration_max_days=4)
    _set_params(factory, event_rate_per_season=10, event_season_days=1)
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
    first = [(e.id, e.region_id, e.origin_key, e.ends_at) for e in _event(factory)]
    assert len(first) == 3
    monkeypatch.setattr(econ_tick, "_process_region", original)

    resumed = econ_tick.run_tick(factory, now=T0 + timedelta(minutes=15))
    assert resumed.resumed and resumed.status == "done"
    assert [(e.id, e.region_id, e.origin_key, e.ends_at) for e in _event(factory)] == first
    assert resumed.events_started == 0 and resumed.events_failed == 0
    assert resumed.events_applied == 2 and resumed.event_expense_ops == 2        # regions 2, 3 (1 was done)
    rows = _event(factory)
    assert all(e.applied_at is not None and e.applied_run_id == resumed.run_id for e in rows)
    assert _scalar(factory, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'region_event'") == 3
    keys = {r[0] for r in _rows(factory, "SELECT idempotency_key FROM econ_operations WHERE op_type = 'region_event'")}
    assert keys == {f"region_event:e{e.id}" for e in rows}
    _check(factory)


def test_random_roll_respects_max_active_and_stacked_events(factory):
    _add_region(factory, 1)
    _add_region(factory, 2)
    _add_template(factory, "busy1", STAB, trigger_kind="manual", duration_min_days=5, duration_max_days=5)
    _add_template(factory, "busy2", STAB, trigger_kind="manual", duration_min_days=5, duration_max_days=5)
    _add_template(factory, "roll", STAB)
    _set_params(factory, event_rate_per_season=10, event_season_days=1, event_max_active=2)
    _start(factory, "busy1", 1, now=T0 - timedelta(hours=1))
    _start(factory, "busy2", 1, now=T0 - timedelta(hours=1))
    summary = econ_tick.run_tick(factory, now=T0)
    assert summary.events_started == 1
    assert [(e.region_id, e.template_code) for e in _event(factory, origin="random")] == [(2, "roll")]
    assert summary.events_applied == 3                       # 2 manual ones in region 1 + the new one in region 2
    _check(factory)


# --------------------------------------------------------------------------------------------- time


def test_expiry_is_by_wall_clock_in_auto_runs_and_manual_runs_do_not_accelerate(factory):
    _add_region(factory, 1)
    _add_template(factory, "short", [{"type": "stability", "delta": -1}], trigger_kind="manual")
    _set_params(factory, event_rate_per_season=0)
    _start(factory, "short", 1, now=T0, days=0.49)           # ends at T0 + 11 h 45.6 min
    for i in range(1, 8):                                       # 7 manual recounts inside the first hour
        s = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=5 * i))
        assert s.events_ended == 0
    assert _event(factory)[0].status == "active"
    assert econ_tick.run_tick(factory, now=_slot(1)).events_ended == 0       # T0 + 6 h: still running
    later = econ_tick.run_tick(factory, now=_slot(2))                         # T0 + 12 h: ends_at < now
    assert later.events_ended == 1
    row = _event(factory)[0]
    assert (row.status, row.ended_at, row.active_key) == ("ended", row.ends_at, None)
    # an ended event no longer acts: its one-shot state stays, no further application
    assert econ_tick.run_tick(factory, trigger="manual", now=_slot(2) + timedelta(minutes=5)).events_applied == 0
    _check(factory)


def test_expired_but_not_yet_ended_event_is_not_applied(factory, monkeypatch):
    """The region transaction itself filters ``ends_at > now`` (an event the expiry step missed never acts)."""
    _add_region(factory, 1, template="agrarian")
    _add_template(factory, "late", [{"type": "stock_loss", "groups": ["food"], "share": 0.5}], trigger_kind="manual")
    _start(factory, "late", 1, now=T0, days=0.01)            # ~14 minutes
    food = _stock(factory, 1, "food")
    monkeypatch.setattr(ev_crud, "expire_events", lambda session, now, region_ids=None: 0)
    s = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(hours=1))
    assert s.status == "done" and s.events_applied == 0 and s.events_ended == 0
    row = _event(factory)[0]
    assert row.applied_at is None and row.status == "active"
    assert _stock(factory, 1, "food") > food * 0.6
    _check(factory)


# --------------------------------------------------------------------------------------------- spreading


def test_spread_forward_arrow_and_same_country_fallback(factory):
    for rid in (1, 2, 3):
        _add_region(factory, rid)
    _add_region(factory, 4, country_id=2)
    _arrows(factory, [(1, 2)])                       # forward from 1; 3 and 4 have no arrows
    _add_template(factory, "fire", STAB, trigger_kind="manual", spread_chance=1, duration_min_days=2,
                  duration_max_days=2)
    _set_params(factory, event_rate_per_season=0, event_spread_max_depth=1)
    (src1,), _ = _start(factory, "fire", 1, days=4, now=T0 - timedelta(hours=1))

    s1 = econ_tick.run_tick(factory, now=T0)
    assert s1.events_spread == 1
    spread = _event(factory, origin="spread")[0]
    assert (spread.region_id, spread.parent_event_id, spread.generation) == (2, src1, 1)
    assert spread.ends_at == T0 + timedelta(days=2)              # fresh duration from the template range

    # region 3 has no arrows -> its neighbours are the same-country regions (1, 2), never region 4 (country 2)
    db = factory()
    try:
        assert ev_crud.neighbour_map(db, ev_crud.load_event_regions(db)) == {1: [2], 2: [1], 3: [1, 2], 4: []}
    finally:
        db.close()
    (src3,), _ = _start(factory, "fire", 3, days=4, now=_slot(1) - timedelta(hours=1))
    s2 = econ_tick.run_tick(factory, now=_slot(1))
    # 1 and 2 already burn -> the only spread candidates of region 3 are taken; gen-1 spread (depth 1) stays put
    assert s2.events_spread == 0
    assert {(e.region_id) for e in _event(factory, template_code="fire")} == {1, 2, 3}
    _check(factory)


def test_spread_fallback_picks_a_same_country_region_and_keeps_the_source_snapshot(factory):
    for rid in (1, 2):
        _add_region(factory, rid)
    _add_region(factory, 3, country_id=2)
    _add_template(factory, "mist", STAB, trigger_kind="manual", spread_chance=1, name="Туман")
    _set_params(factory, event_rate_per_season=0, event_spread_max_depth=0)
    (src,), _ = _start(factory, "mist", 1, days=4, now=T0 - timedelta(hours=1))
    assert econ_tick.run_tick(factory, now=T0).events_spread == 0          # depth 0 = no spreading

    _set_params(factory, event_spread_max_depth=2)
    db = factory()
    try:
        tpl = db.query(models.EconEventTemplate).filter_by(code="mist").one()
        tpl.name = "Новое имя"
        tpl.effects = [{"type": "stability", "delta": -9}]
        db.commit()
    finally:
        db.close()
    assert econ_tick.run_tick(factory, now=_slot(1)).events_spread == 1
    spread = _event(factory, origin="spread")[0]
    assert spread.region_id == 2 and spread.country_id == 1
    assert spread.name == "Туман" and spread.effects == STAB          # the source's snapshot, not the edited template
    assert spread.origin_key == f"spread:{SLOT0 + 1}:e{src}"
    _check(factory)


def test_spread_never_targets_non_participating_regions_and_arrows_disable_the_fallback(factory):
    for rid in (1, 2, 3):
        _add_region(factory, rid)
    _set_region(factory, 2, population=0)                     # out of the simulation
    _arrows(factory, [(2, 1)])                                # region 1's only arrow neighbour is region 2
    _add_template(factory, "fire", STAB, trigger_kind="manual", spread_chance=1)
    _set_params(factory, event_rate_per_season=0)
    _start(factory, "fire", 1, days=4, now=T0 - timedelta(hours=1))
    assert econ_tick.run_tick(factory, now=T0).events_spread == 0
    assert [e.region_id for e in _event(factory)] == [1]       # not 2 (not participating), not 3 (1 has arrows)
    _check(factory)


# --------------------------------------------------------------------------------------------- chains


def test_chains_respect_max_active_disabled_targets_and_ignore_seasons(factory, calendar):
    _add_region(factory, 1, template="agrarian")
    _add_region(factory, 2, template="agrarian")
    _add_template(factory, "pest", STAB, trigger_kind="manual", seasons=["winter"], region_templates=["mining"])
    _add_template(factory, "off", STAB, trigger_kind="manual", is_enabled=False)
    _add_template(factory, "flood", STAB, trigger_kind="manual",
                  chains=[{"code": "off", "chance": 1}, {"code": "pest", "chance": 1}])
    _add_template(factory, "other", STAB, trigger_kind="manual")
    _set_params(factory, event_rate_per_season=0, event_max_active=2)
    (f1,), _ = _start(factory, "flood", 1, days=4, now=T0 - timedelta(hours=1))
    _start(factory, "flood", 2, days=4, now=T0 - timedelta(hours=1))
    _start(factory, "other", 2, days=4, now=T0 - timedelta(hours=1))   # region 2 is full (2 of 2)

    summary = econ_tick.run_tick(factory, now=T0)
    assert summary.events_chained == 1
    chained = _event(factory, origin="chain")
    assert [(e.region_id, e.template_code, e.parent_event_id) for e in chained] == [(1, "pest", f1)]
    assert chained[0].origin_key == f"chain:{SLOT0}:e{f1}:pest"
    # the next slot does not chain again (pest already active in 1; region 2 still full)
    assert econ_tick.run_tick(factory, now=_slot(1)).events_chained == 0
    assert calendar["segment"] == "summer"
    _check(factory)


# --------------------------------------------------------------------------------------------- riot


def test_riot_clock_is_wall_time_with_cooldown_and_ignores_max_active(factory):
    _add_region(factory, 1)
    _add_template(factory, "unrest", [{"type": "stability", "delta": -1}], trigger_kind="low_stability",
                  duration_min_days=1, duration_max_days=1)
    _add_template(factory, "long", STAB, trigger_kind="manual")
    _set_params(factory, event_rate_per_season=0, event_riot_stability=101, event_riot_after_days=3,
                event_max_active=1)
    _start(factory, "long", 1, days=30, now=T0 - timedelta(hours=1))     # region already at max_active
    _set_region(factory, 1, low_stability_since=T0 - timedelta(days=1))

    assert econ_tick.run_tick(factory, now=T0).riots_started == 0           # 1 day low
    for i in range(1, 6):                                                    # manual recounts never start a riot
        assert econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=10 * i)).riots_started == 0
    assert econ_tick.run_tick(factory, now=_slot(1)).riots_started == 0     # 1 day 6 h
    assert _scalar(factory, "SELECT low_stability_since FROM econ_regions") is not None

    due = _slot(8)                                                           # 3 days after the clock started
    s = econ_tick.run_tick(factory, now=due)
    assert s.riots_started == 1
    riot = _event(factory, origin="riot")[0]
    assert riot.origin_key == f"riot:{SLOT0 + 8}:r1" and riot.ends_at == due + timedelta(days=1)

    assert econ_tick.run_tick(factory, now=_slot(9)).riots_started == 0      # riot active
    after_end = econ_tick.run_tick(factory, now=_slot(13))                   # riot ended at slot 12 (+1 day)
    assert after_end.events_ended == 1 and after_end.riots_started == 0      # cooldown from the riot's end
    assert econ_tick.run_tick(factory, now=_slot(23)).riots_started == 0     # 2.75 days after the end
    assert econ_tick.run_tick(factory, now=_slot(24)).riots_started == 1     # 3 days after the end
    assert len(_event(factory, origin="riot")) == 2
    _check(factory)


# --------------------------------------------------------------------------------------------- one-shots


def test_population_change_is_permanent_and_never_below_the_scale(factory):
    _add_region(factory, 1, population=2)                        # lore 2 * SCALE
    _add_region(factory, 2)
    _add_template(factory, "plague_x", [{"type": "population", "pct": -0.5}], trigger_kind="manual")
    _add_template(factory, "plague_y", [{"type": "population", "pct": -0.5}], trigger_kind="manual")
    _add_template(factory, "boom", [{"type": "population", "pct": 0.1}], kind="good", trigger_kind="manual")
    _start(factory, "plague_x", 1, days=0.5)
    _start(factory, "plague_y", 1, days=0.5)
    _start(factory, "boom", 2, days=0.5)
    pop2 = _population(factory, 2)

    econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=10))
    x, y = _event(factory, region_id=1)
    assert (x.population_before, x.population_after) == (2 * SCALE, SCALE)
    assert (y.population_before, y.population_after) == (SCALE, SCALE)      # floor = scale
    assert _population(factory, 1) == SCALE
    b = _event(factory, region_id=2)[0]
    assert (b.population_before, b.population_after) == (pop2, round(pop2 * 1.1))

    # after the events end the populations stay (permanent), history records the lore number
    s = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(days=1))
    assert s.events_ended == 3 and s.events_applied == 0
    assert (_population(factory, 1), _population(factory, 2)) == (SCALE, round(pop2 * 1.1))
    hist = _scalar(factory, "SELECT population FROM econ_region_history WHERE region_id = 2 AND run_id = :r",
                   r=s.run_id)
    assert hist == round(pop2 * 1.1)
    _check(factory)


def test_stock_loss_of_every_group_is_taken_once_before_the_sim(factory):
    _add_region(factory, 1, template="agrarian")
    _add_template(factory, "quake", [{"type": "stock_loss", "groups": ["*"], "share": 0.5}], trigger_kind="manual")
    before = dict(_rows(factory, "SELECT group_code, stock FROM econ_region_goods WHERE region_id = 1"))
    _start(factory, "quake", 1, days=2)
    first = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=10))
    assert first.events_applied == 1 and first.event_expense_ops == 0
    row = _event(factory)[0]
    lost = row.outcome["stock_lost"]
    for code, stock in before.items():
        assert lost.get(code, 0) == pytest.approx(float(stock) * 0.5, abs=0.01)
    econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=20))
    again = _event(factory)[0]
    assert again.outcome == row.outcome and again.applied_run_id == first.run_id
    _check(factory)


def test_treasury_expense_is_a_share_of_the_treasury_after_the_tick_untaxed(factory):
    _add_region(factory, 1, template="agrarian")
    _add_template(factory, "repair", [{"type": "treasury_expense", "share": 0.5},
                                      {"type": "treasury_expense", "share": 0.6}], trigger_kind="manual")
    # one regular run first so the treasury has money from taxes
    econ_tick.run_tick(factory, trigger="manual", now=T0)
    _start(factory, "repair", 1, days=2, now=T0 + timedelta(minutes=5))
    s = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=10))
    row = _event(factory)[0]
    spent = row.outcome["treasury_expense"]
    treasury = _balance(factory, "region_treasury", 1)
    assert spent > 0 and spent == int((treasury + spent) * 0.9)            # shares sum, capped at 0.9
    op_id = row.outcome["operation_id"]
    assert _rows(factory, "SELECT op_type, region_id, idempotency_key FROM econ_operations WHERE id = :i",
                 i=op_id) == [("region_event", 1, f"region_event:e{row.id}")]
    legs = _rows(factory, "SELECT amount FROM econ_postings WHERE operation_id = :i", i=op_id)
    assert legs == [(spent,)]                                               # one leg, no tax leg
    assert s.event_expense_ops == 1
    _check(factory)


def test_negative_treasury_spends_nothing(factory):
    _add_region(factory, 1, template="agrarian")
    _add_template(factory, "repair", [{"type": "treasury_expense", "share": 0.5}], trigger_kind="manual")
    db = factory()
    try:                                                    # region treasuries may be in debt
        econ_ledger.post_operation(db, op_type=core.OP_ADMIN_ADJUST, source_service="character-service",
                                   comment="тест", legs=[core.Leg(core.AccountRef.region(1),
                                                                  core.AccountRef.adjustment(), 10_000_000)])
        db.commit()
    finally:
        db.close()
    _start(factory, "repair", 1, days=2)
    s = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=10))
    assert s.events_applied == 1 and s.event_expense_ops == 0
    assert _event(factory)[0].outcome["treasury_expense"] == 0
    _check(factory)


# --------------------------------------------------------------------------------------------- per-step effects


def test_stacked_multipliers_and_deltas_are_clamped(factory):
    for rid in (1, 2, 3):
        _add_region(factory, rid, template="agrarian")
    for i in (1, 2, 3):
        _add_template(factory, f"dry{i}", [{"type": "production", "groups": ["food"], "mult": 0.2}],
                      trigger_kind="manual")
    _add_template(factory, "dry_one", [{"type": "production", "groups": ["food"], "mult": 0.1}],
                  trigger_kind="manual")
    _add_template(factory, "anger1", [{"type": "stability", "delta": -8}], trigger_kind="manual")
    _add_template(factory, "anger2", [{"type": "stability", "delta": -8}], trigger_kind="manual")
    _add_template(factory, "anger_one", [{"type": "stability", "delta": -10}], trigger_kind="manual")
    for code in ("dry1", "dry2", "dry3", "anger1", "anger2"):
        _start(factory, code, 1, days=2)
    for code in ("dry_one", "anger_one"):
        _start(factory, code, 2, days=2)
    econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=10))
    produced = dict(_rows(factory, "SELECT region_id, last_produced FROM econ_region_goods WHERE group_code = 'food'"))
    stability = dict(_rows(factory, "SELECT region_id, stability FROM econ_regions"))
    assert float(produced[1]) == pytest.approx(float(produced[2]))          # 0.2^3 -> clamped to 0.1
    assert float(produced[1]) < float(produced[3])
    assert float(stability[1]) == pytest.approx(float(stability[2]))        # -16 -> capped at -10
    assert float(stability[1]) < float(stability[3])
    # the stored inputs are never changed by events
    assert len({r[0] for r in _rows(factory, "SELECT production_per_1000 FROM econ_region_goods "
                                             "WHERE group_code = 'food'")}) == 1
    _check(factory)


def test_merchants_halt_changes_only_that_regions_merchant_params(factory, monkeypatch):
    for rid in (1, 2):
        _add_region(factory, rid)
    _add_template(factory, "closed", [{"type": "merchants_halt"}], trigger_kind="manual")
    _start(factory, "closed", 1, days=2)
    seen = {}
    monkeypatch.setattr(econ_tick, "_prepare_merchants", lambda sf, run_id: ({1: [31], 2: [32]}, 0))
    monkeypatch.setattr(econ_tick, "lock_merchants",
                        lambda session, region_id, npc_ids, for_update: econ_tick.MerchantContext(
                            merchants=[object()], rows={}, dropped=[]))

    def step(session, *, region_id, params, **kw):
        seen[region_id] = params.merchant_take_share
        return {}

    monkeypatch.setattr(econ_tick, "_merchant_step", step)
    s = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=10))
    assert s.status == "done"
    default = econ_tick.load_params(factory()).merchant_take_share
    assert default > 0 and seen == {1: 0.0, 2: default}
    _check(factory)


def test_bank_panic_and_loan_boom_change_only_their_banks(factory, monkeypatch):
    for rid in (1, 2, 3):
        _add_region(factory, rid)
    db = factory()
    try:
        for rid in (1, 2, 3):
            db.add(models.EconBank(region_id=rid, is_enabled=True))
        db.flush()
        for rid in (1, 2, 3):
            econ_ledger.post_operation(db, op_type=core.OP_ADMIN_EMISSION, source_service="character-service",
                                       comment="тест", legs=[core.Leg(core.AccountRef.emission(),
                                                                      core.AccountRef.region(rid), 500_000)])
            econ_ledger.post_operation(db, op_type=core.OP_BANK_CAPITAL, source_service="character-service",
                                       apply_tax=False, legs=[core.Leg(core.AccountRef.region(rid),
                                                                       core.AccountRef.bank(rid), 500_000)])
        db.commit()
    finally:
        db.close()
    _add_template(factory, "panic", [{"type": "bank_panic"}], trigger_kind="manual")
    _add_template(factory, "boom", [{"type": "loan_boom", "mult": 3}], kind="good", trigger_kind="manual")
    _start(factory, "panic", 1, days=2)
    _start(factory, "boom", 2, days=2)
    seen = {}
    original = bank_crud.tick_bank

    def spy(db, region_id, *, params, **kw):
        seen[region_id] = (params.bank_resident_deposit_share, params.bank_resident_loan_share)
        return original(db, region_id, params=params, **kw)

    monkeypatch.setattr(bank_crud, "tick_bank", spy)
    s = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=10))
    assert s.banks_processed == 3 and s.bank_failures == 0
    base = econ_tick.load_params(factory())
    assert seen[1] == (0.0, base.bank_resident_loan_share)
    assert seen[2] == (base.bank_resident_deposit_share,
                       pytest.approx(min(econ_events.BANK_LOAN_SHARE_MAX, base.bank_resident_loan_share * 3)))
    assert seen[3] == (base.bank_resident_deposit_share, base.bank_resident_loan_share)
    banks = {r[0]: (r[1], r[2]) for r in _rows(factory, "SELECT region_id, resident_deposits, resident_loans "
                                                        "FROM econ_banks")}
    assert banks[1][0] == 0 and banks[3][0] > 0                             # panic: residents keep nothing there
    assert banks[2][1] > banks[3][1]                                        # boom: more resident loans
    assert dataclasses.asdict(base) == dataclasses.asdict(econ_tick.load_params(factory()))   # no leak
    _check(factory)


# --------------------------------------------------------------------------------------------- calendar


class _Resp:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _client_returning(outcome):
    class _Client:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url):
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
    return _Client


@pytest.mark.parametrize("outcome, expected", [
    (_Resp(200, {"computed": {"segment_name": "winter"}}), "winter"),
    (httpx.ConnectError("down"), None),
    (httpx.ReadTimeout("slow"), None),
    (_Resp(503, {}), None),
    (_Resp(200, ValueError("not json")), None),
    (_Resp(200, {"computed": {}}), None),
    (_Resp(200, {"computed": {"segment_name": ""}}), None),
    (_Resp(200, None), None),
])
def test_game_segment_client_fails_soft(monkeypatch, outcome, expected):
    monkeypatch.setattr(locations_client.httpx, "Client", _client_returning(outcome))
    assert REAL_GET_SEGMENT() == expected


def test_unreachable_calendar_rolls_only_season_free_templates(factory, monkeypatch):
    monkeypatch.setattr(locations_client, "get_game_segment_sync", REAL_GET_SEGMENT)
    monkeypatch.setattr(locations_client.httpx, "Client", _client_returning(httpx.ConnectError("down")))
    for rid in (1, 2, 3):
        _add_region(factory, rid)
    _add_template(factory, "summer_only", STAB, seasons=["summer"], weight=1000)
    _add_template(factory, "always", STAB, weight=1)
    _set_params(factory, event_rate_per_season=10, event_season_days=1)
    s = econ_tick.run_tick(factory, now=T0)
    assert s.status == "done" and s.events_failed == 0 and s.events_started == 3
    assert {(e.template_code, e.game_segment) for e in _event(factory)} == {("always", None)}
    _check(factory)


def test_unknown_segment_name_counts_as_unknown_and_manual_runs_never_ask(factory, calendar):
    _add_region(factory, 1)
    _add_template(factory, "summer_only", STAB, seasons=["summer"], weight=1000)
    _add_template(factory, "always", STAB, weight=1)
    _set_params(factory, event_rate_per_season=10, event_season_days=1)
    econ_tick.run_tick(factory, trigger="manual", now=T0 - timedelta(minutes=4))
    assert calendar["calls"] == 0
    calendar["segment"] = "середина лета"
    econ_tick.run_tick(factory, now=T0)
    assert [(e.template_code, e.game_segment) for e in _event(factory)] == [("always", None)]
    _check(factory)


# --------------------------------------------------------------------------------------------- non-participating


def test_events_of_non_participating_regions_are_skipped(factory):
    for rid in (1, 2, 3):
        _add_region(factory, rid)
    _add_template(factory, "storm", [{"type": "stock_loss", "groups": ["*"], "share": 0.5}], trigger_kind="manual",
                  scope="world")
    _set_region(factory, 2, template_code=None)
    db = factory()
    try:                                             # an instance left over from before the region was taken out
        db.add(models.EconRegionEvent(
            region_id=2, template_code="storm", name="Буря", icon="alert", kind="bad", player_text="-",
            trigger_kind="manual", effects=[{"type": "stock_loss", "groups": ["*"], "share": 0.5}], origin="manual",
            active_key="r2:old", status="active", started_at=T0 - timedelta(hours=1), ends_at=T0 + timedelta(days=1)))
        db.commit()
    finally:
        db.close()
    ids, skipped = _start(factory, "storm", 2, days=1)
    assert ids == [] and [s[2] for s in skipped] == [ev_crud.SKIP_NOT_PARTICIPATING]
    ids, skipped = _start(factory, "storm", 1, days=1)
    assert [e.region_id for e in _event(factory) if e.id in ids] == [1, 3] and skipped == []

    s = econ_tick.run_tick(factory, trigger="manual", now=T0 + timedelta(minutes=10))
    assert s.regions_total == 2 and s.events_applied == 2
    assert _event(factory, region_id=2)[0].applied_at is None
    _check(factory)


# --------------------------------------------------------------------------------------------- failures / summary


def test_failing_events_pass_keeps_expiry_and_regions_and_reports_the_error(factory, monkeypatch):
    for rid in (1, 2):
        _add_region(factory, rid)
    _add_template(factory, "old", STAB, trigger_kind="manual")
    _add_template(factory, "dear", [{"type": "price", "groups": ["*"], "mult": 3.0}], trigger_kind="manual")
    _start(factory, "old", 1, days=0.01, now=T0 - timedelta(hours=1))
    _start(factory, "dear", 2, days=3, now=T0 - timedelta(hours=1))
    _set_params(factory, event_rate_per_season=10, event_season_days=1)

    def boom(session):
        raise RuntimeError("broken read")

    monkeypatch.setattr(ev_crud, "load_event_regions", boom)
    s = econ_tick.run_tick(factory, now=T0)
    assert s.status == "done" and s.regions_done == 2
    assert s.events_ended == 1 and s.events_failed == 1 and s.events_started == 0
    assert s.events_applied == 1                                       # the running event still acts
    error = _scalar(factory, "SELECT error FROM econ_tick_runs WHERE id = :i", i=s.run_id)
    assert error.startswith(econ_tick.EVENTS_ERROR_PREFIX)
    _check(factory)


def test_run_summary_counters_of_a_busy_slot(factory):
    for rid in (1, 2, 3):
        _add_region(factory, rid, template="agrarian")
    _add_region(factory, 4, template="agrarian")
    _arrows(factory, [(1, 2)])
    _add_template(factory, "plague", [{"type": "population", "pct": -0.1}], trigger_kind="manual")
    _add_template(factory, "flood", [{"type": "treasury_expense", "share": 0.1}], trigger_kind="manual",
                  spread_chance=1, chains=[{"code": "plague", "chance": 1}])
    _add_template(factory, "unrest", STAB, trigger_kind="low_stability")
    _add_template(factory, "gone", STAB, trigger_kind="manual")
    _add_template(factory, "luck", STAB, kind="good", region_templates=["agrarian"])
    _set_params(factory, event_rate_per_season=10, event_season_days=1, event_riot_after_days=1)
    econ_tick.run_tick(factory, trigger="manual", now=T0 - timedelta(minutes=5))   # treasuries get taxes
    _start(factory, "flood", 1, days=4, now=T0 - timedelta(hours=1))
    _start(factory, "gone", 3, days=0.01, now=T0 - timedelta(hours=1))
    _set_region(factory, 4, low_stability_since=T0 - timedelta(days=2))

    s = econ_tick.run_tick(factory, now=T0)
    by_origin = {}
    for e in _event(factory):
        by_origin.setdefault(e.origin, []).append((e.region_id, e.template_code))
    assert sorted(by_origin["random"]) == [(r, "luck") for r in (1, 2, 3, 4)]
    assert by_origin["spread"] == [(2, "flood")] and by_origin["chain"] == [(1, "plague")]
    assert by_origin["riot"] == [(4, "unrest")]
    assert (s.events_ended, s.events_started, s.events_spread, s.events_chained, s.riots_started) == (1, 4, 1, 1, 1)
    # applied: flood(1) + 4 luck + spread flood(2) + plague(1) + riot(4) = 8; expenses: flood in 1 and 2
    assert (s.events_applied, s.event_expense_ops, s.events_failed) == (8, 2, 0)
    data = s.to_dict()
    for key in ("events_ended", "events_started", "events_spread", "events_chained", "riots_started",
                "events_applied", "event_expense_ops", "events_failed"):
        assert data[key] == getattr(s, key)
    _check(factory)
