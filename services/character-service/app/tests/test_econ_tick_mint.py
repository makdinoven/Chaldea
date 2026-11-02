"""FEAT-191 QA (#9): the season quota pass and the court mint pass of the economy tick on SQLite.

Harness of ``test_econ_tick.py`` (``factory`` fixture: migration-028 seed, countries 1 «Мидденгерд» and 2 «Пустошь»)
plus the shared ``game_time_config`` row (locations-service table, created here with its real columns
``id, epoch, offset_days, updated_at``). The ``econ_mint*`` tables come from the character-service metadata.

Calendar: epoch = T0 - 10 days -> T0 is in period 0 («spring», year 1); T0 + 40 days is period 1.
"""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

import econ_core as core
import econ_mint
import econ_tick
import economy_mint_crud as mint_crud
import models
from tests.test_econ_tick import (  # noqa: F401  (factory is a fixture)
    T0, _add_region, _assert_ledger_closes, _balance, _rows, _scalar, factory,
)

EPOCH = T0 - timedelta(days=10)
NEXT_SEASON = T0 + timedelta(days=40)

GAME_TIME_DDL = """CREATE TABLE IF NOT EXISTS game_time_config (
    id INTEGER PRIMARY KEY,
    epoch DATETIME NOT NULL,
    offset_days INTEGER NOT NULL DEFAULT 0,
    updated_at DATETIME NULL
)"""


def _exec(factory, sql, **params):
    db = factory()
    try:
        db.execute(text(sql), params)
        db.commit()
    finally:
        db.close()


@pytest.fixture
def world(factory):
    """The calendar row; tests add regions / params themselves."""
    _exec(factory, GAME_TIME_DDL)
    _exec(factory, "INSERT INTO game_time_config (id, epoch, offset_days) VALUES (1, :e, 0)", e=EPOCH)
    return factory


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


def _params(factory):
    db = factory()
    try:
        return econ_tick.load_params(db)
    finally:
        db.close()


def _ore(factory, region_id, stock=None, norm=None):
    if stock is not None:
        _exec(factory, "UPDATE econ_region_goods SET stock = :s, norm_stock = :n "
                       "WHERE region_id = :r AND group_code = 'ore_metal'", s=stock, n=norm, r=region_id)
    row = _rows(factory, "SELECT stock, norm_stock FROM econ_region_goods WHERE region_id = :r "
                         "AND group_code = 'ore_metal'", r=region_id)
    return (Decimal(str(row[0][0])).quantize(Decimal("0.001")), Decimal(str(row[0][1])).quantize(Decimal("0.001"))) \
        if row else None


def _mint_row(factory, country_id, *, capital=None, limit=None, enabled=True):
    db = factory()
    try:
        db.add(models.EconMint(country_id=country_id, capital_region_id=capital, season_limit=limit,
                               is_enabled=enabled))
        db.commit()
    finally:
        db.close()


def _season(factory, country_id, period_index=0):
    rows = _rows(factory, "SELECT minted_court, minted_players, ore_units_court, ore_units_players "
                          "FROM econ_mint_seasons WHERE country_id = :c AND period_index = :p",
                 c=country_id, p=period_index)
    return rows[0] if rows else None


def _ops(factory, op_type):
    return _rows(factory, "SELECT id, idempotency_key, region_id, metadata FROM econ_operations WHERE op_type = :t "
                          "ORDER BY id", t=op_type)


def _meta(raw):
    return json.loads(raw) if isinstance(raw, str) else raw


def _legs(factory, op_id):
    return _rows(factory, "SELECT a1.kind, a2.kind, a2.ref_id, l.amount FROM econ_postings l "
                          "JOIN econ_accounts a1 ON a1.id = l.from_account_id "
                          "JOIN econ_accounts a2 ON a2.id = l.to_account_id WHERE l.operation_id = :i "
                          "ORDER BY a2.ref_id", i=op_id)


def _summary(run_id=1):
    return econ_tick.RunSummary(run_id=run_id, trigger="manual", slot=None, status="running")


def _pops(factory):
    return dict(_rows(factory, "SELECT region_id, population FROM econ_regions"))


BIG_NORM = 10 ** 12


def _below_norm(factory, *region_ids):
    """FEAT-194: the quota goes only to regions below their money norm — put the regions far below it (the region
    step of a run rewrites wealth_norm, so call this again before every run that should issue)."""
    for rid in region_ids:
        _exec(factory, "UPDATE econ_regions SET wealth_norm = :n WHERE region_id = :r", n=BIG_NORM, r=rid)


def _deficits(factory):
    db = factory()
    try:
        return econ_tick.region_deficits(db)
    finally:
        db.close()


# --------------------------------------------------------------------------------------------- season quota

def test_quota_issued_once_per_season_split_by_deficit(world):
    _add_region(world, 1, template="capital")
    _add_region(world, 2, template="agrarian")
    _add_region(world, 3, template="rural", country_id=2)
    _set_params(world, quota_season_amount=10_001)
    _below_norm(world, 1, 2, 3)
    deficits = _deficits(world)

    first = econ_tick.run_tick(world, trigger="manual", now=T0)
    assert first.quota_amount == 10_001 and first.quota_failed is False
    ops = _ops(world, "season_quota")
    assert len(ops) == 1
    op_id, key, region_id, meta = ops[0]
    assert key == "season_quota:p0" and key == f"{mint_crud.KEY_QUOTA}:p0" and region_id is None
    meta = _meta(meta)
    assert (meta["period_index"], meta["year"], meta["season"], meta["amount"], meta["run_id"]) == \
        (0, 1, "spring", 10_001, first.run_id)
    expected = econ_mint.split_by_deficit(10_001, deficits)          # FEAT-194: by the deficit below the norm
    assert {int(k): v for k, v in meta["regions"].items()} == expected
    assert meta["requested"] == 10_001 and {int(k): v for k, v in meta["deficits"].items()} == deficits
    legs = _legs(world, op_id)
    assert [(a, b, r, n) for a, b, r, n in legs] == \
        [("emission", "region_treasury", rid, expected[rid]) for rid in sorted(expected)]
    assert sum(n for *_x, n in legs) == 10_001

    _below_norm(world, 1, 2, 3)
    second = econ_tick.run_tick(world, trigger="manual", now=T0 + timedelta(minutes=30))
    assert second.quota_amount == 0 and second.quota_failed is False
    assert len(_ops(world, "season_quota")) == 1
    # the treasuries got exactly their share once (the region steps move money too, so compare the posting sums)
    for rid in (1, 2, 3):
        got = int(_scalar(world, "SELECT COALESCE(SUM(l.amount), 0) FROM econ_postings l JOIN econ_operations o "
                                 "ON o.id = l.operation_id JOIN econ_accounts a ON a.id = l.to_account_id "
                                 "WHERE o.op_type = 'season_quota' AND a.kind = 'region_treasury' "
                                 "AND a.ref_id = :r", r=rid))
        assert got == expected[rid]
    _assert_ledger_closes(world)


def test_quota_only_for_participating_regions(world):
    _add_region(world, 1, template="capital")
    _add_region(world, 2, template="agrarian")
    _add_region(world, 3, template="rural")
    _add_region(world, 4, template="rural", world_row=False)      # econ row of a deleted world region
    _exec(world, "UPDATE econ_regions SET population = 0 WHERE region_id = 2")
    _exec(world, "UPDATE econ_regions SET template_code = NULL WHERE region_id = 3")
    _exec(world, "INSERT INTO Regions (id, name, country_id) VALUES (5, 'Без экономики', 1)")
    _set_params(world, quota_season_amount=900)
    _below_norm(world, 1, 2, 3, 4)

    summary = econ_tick.run_tick(world, trigger="manual", now=T0)
    assert summary.quota_amount == 900
    meta = _meta(_ops(world, "season_quota")[0][3])
    assert list(meta["regions"]) == ["1"] and meta["regions"]["1"] == 900


def test_auto_and_resumed_runs_do_not_issue_twice(world):
    _add_region(world, 1, template="capital")
    _set_params(world, quota_season_amount=500)
    _below_norm(world, 1)
    first = econ_tick.run_tick(world, now=T0)
    assert first is not None and first.quota_amount == 500
    assert econ_tick.run_tick(world, now=T0 + timedelta(minutes=10)) is None        # same slot is done
    _below_norm(world, 1)
    later = econ_tick.run_tick(world, now=T0 + timedelta(hours=6))                  # next slot, same season
    assert later is not None and later.quota_amount == 0
    manual = econ_tick.run_tick(world, trigger="manual", now=T0 + timedelta(hours=7))
    assert manual.quota_amount == 0
    assert len(_ops(world, "season_quota")) == 1


def test_quota_pass_twice_in_one_run_is_idempotent(world):
    """A resumed run re-enters the pass: the pre-check (and the UNIQUE key) stops a second issue."""
    _add_region(world, 1, template="capital")
    _set_params(world, quota_season_amount=300)
    _below_norm(world, 1)
    params = _params(world)
    s1, s2 = _summary(7), _summary(7)
    econ_tick._quota_pass(world, 7, s1, params, T0)
    econ_tick._quota_pass(world, 7, s2, params, T0)
    assert (s1.quota_amount, s2.quota_amount) == (300, 0)
    assert s2.quota_failed is False
    assert len(_ops(world, "season_quota")) == 1


def test_quota_duplicate_key_race_is_a_silent_skip(world, monkeypatch):
    """Another runner issued between the pre-check and the insert: DuplicateOperation -> rollback, no failure."""
    _add_region(world, 1, template="capital")
    _set_params(world, quota_season_amount=300)
    params = _params(world)
    import econ_ledger

    def raced(*_a, **_k):
        raise core.DuplicateOperation(1)

    monkeypatch.setattr(econ_ledger, "post_operation", raced)
    s = _summary(2)
    econ_tick._quota_pass(world, 2, s, params, T0)
    assert s.quota_amount == 0 and s.quota_failed is False
    assert _ops(world, "season_quota") == []


def test_quota_new_season_is_issued_again(world):
    _add_region(world, 1, template="capital")
    _add_region(world, 2, template="agrarian")
    _set_params(world, quota_season_amount=1000)
    _below_norm(world, 1, 2)
    econ_tick.run_tick(world, trigger="manual", now=T0)
    _below_norm(world, 1, 2)
    summary = econ_tick.run_tick(world, trigger="manual", now=NEXT_SEASON)
    assert summary.quota_amount == 1000
    keys = [k for _i, k, _r, _m in _ops(world, "season_quota")]
    assert keys == ["season_quota:p0", "season_quota:p1"]
    assert _meta(_ops(world, "season_quota")[1][3])["season"] == "summer"
    _assert_ledger_closes(world)


def test_missed_seasons_are_not_caught_up(world):
    _add_region(world, 1, template="capital")
    _set_params(world, quota_season_amount=100)
    _below_norm(world, 1)
    econ_tick.run_tick(world, trigger="manual", now=T0)
    _below_norm(world, 1)
    econ_tick.run_tick(world, trigger="manual", now=T0 + timedelta(days=49 * 3))     # period 3 (0 -> 3)
    keys = [k for _i, k, _r, _m in _ops(world, "season_quota")]
    assert keys == ["season_quota:p0", "season_quota:p3"]


def test_quota_waits_while_nobody_is_below_the_norm(world):
    """FEAT-194 (3.9): nobody below the money norm -> nothing posted, the next run of the season re-checks."""
    _add_region(world, 1, template="capital")
    _set_params(world, quota_season_amount=400)
    _exec(world, "UPDATE econ_regions SET wealth_norm = 0, treasury_target = 0")
    params = _params(world)
    waited = _summary(3)
    econ_tick._quota_pass(world, 3, waited, params, T0)
    assert waited.quota_amount == 0 and waited.quota_failed is False
    assert _ops(world, "season_quota") == []
    _below_norm(world, 1)
    retried = _summary(4)
    econ_tick._quota_pass(world, 4, retried, params, T0 + timedelta(hours=6))
    assert retried.quota_amount == 400 and len(_ops(world, "season_quota")) == 1


def test_quota_is_capped_at_the_total_deficit(world):
    """FEAT-194 (3.9): a small deficit takes only what it lacks; the rest of the season amount is not issued."""
    _add_region(world, 1, template="capital")
    _set_params(world, quota_season_amount=1_000_000)
    deficit = 123
    _exec(world, "UPDATE econ_regions SET treasury_target = 0")
    purse = _balance(world, "population_purse", 1)
    _exec(world, "UPDATE econ_regions SET wealth_norm = :n", n=purse + deficit)
    summary = _summary(5)
    econ_tick._quota_pass(world, 5, summary, _params(world), T0)
    assert summary.quota_amount == deficit
    meta = _meta(_ops(world, "season_quota")[0][3])
    assert meta["regions"] == {"1": deficit} and meta["requested"] == 1_000_000


def test_quota_amount_zero_is_skipped(world):
    _add_region(world, 1, template="capital")
    summary = econ_tick.run_tick(world, trigger="manual", now=T0)     # default quota_season_amount = 0
    assert summary.quota_amount == 0 and summary.quota_failed is False
    assert _ops(world, "season_quota") == []


def test_quota_without_calendar_row_is_skipped(world):
    _add_region(world, 1, template="capital")
    _set_params(world, quota_season_amount=100)
    _exec(world, "DELETE FROM game_time_config")
    summary = econ_tick.run_tick(world, trigger="manual", now=T0)
    assert summary.quota_amount == 0 and summary.quota_failed is False
    assert summary.status == "done"
    assert _ops(world, "season_quota") == []


def test_quota_without_calendar_table_is_skipped(factory):
    """game_time_config absent (no `world` fixture): skipped with a warning, the run is not failed."""
    _add_region(factory, 1, template="capital")
    _set_params(factory, quota_season_amount=100, mint_season_limit=1000)
    summary = econ_tick.run_tick(factory, trigger="manual", now=T0)
    assert summary.status == "done" and summary.quota_failed is False and summary.mint_failures == 0
    assert _ops(factory, "season_quota") == [] and _ops(factory, "mint_court") == []


def test_quota_without_participating_regions_is_skipped(world):
    _set_params(world, quota_season_amount=100)
    summary = econ_tick.run_tick(world, trigger="manual", now=T0)
    assert summary.quota_amount == 0 and summary.quota_failed is False
    assert _ops(world, "season_quota") == []


def test_quota_failure_marks_the_run_and_is_retried(world, monkeypatch):
    _add_region(world, 1, template="capital")
    _set_params(world, quota_season_amount=100)

    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(econ_mint, "split_quota", boom)
    _below_norm(world, 1)
    failed = econ_tick.run_tick(world, trigger="manual", now=T0)
    assert failed.quota_failed is True and failed.quota_amount == 0
    assert failed.regions_done == 1 and failed.status == "done"              # the regions still ticked
    error = _scalar(world, "SELECT error FROM econ_tick_runs WHERE id = :i", i=failed.run_id)
    assert econ_tick.QUOTA_ERROR_PREFIX in error
    assert _ops(world, "season_quota") == []

    monkeypatch.undo()
    _below_norm(world, 1)
    retried = econ_tick.run_tick(world, trigger="manual", now=T0 + timedelta(minutes=30))
    assert retried.quota_amount == 100 and retried.quota_failed is False
    assert _scalar(world, "SELECT error FROM econ_tick_runs WHERE id = :i", i=retried.run_id) is None


# --------------------------------------------------------------------------------------------- court mint (pass)

def _court(factory, run_id=1, now=T0):
    summary = _summary(run_id)
    econ_tick._mint_pass(factory, run_id, summary, _params(factory), now)
    return summary


def test_court_mint_auto_capital_takes_surplus_into_country_treasury(world):
    _add_region(world, 1, template="capital")
    _add_region(world, 2, template="agrarian")
    _set_params(world, mint_season_limit=100_000, mint_court_marks_per_unit=8.0, mint_court_threshold_pct=100.0)
    _ore(world, 1, stock=130, norm=100)
    country_before = _balance(world, "country_treasury", 1)

    summary = _court(world, run_id=42)
    assert (summary.mint_court_ops, summary.mint_court_marks, summary.mint_failures) == (1, 240, 0)
    assert _ore(world, 1) == (Decimal("100.000"), Decimal("100.000"))
    court, players, units_court, units_players = _season(world, 1)
    assert (court, players) == (240, 0)
    assert Decimal(str(units_court)) == Decimal("30") and Decimal(str(units_players)) == 0
    assert _balance(world, "country_treasury", 1) == country_before + 240

    (op_id, key, region_id, meta), = _ops(world, "mint_court")
    assert key == "mint_court:42:c1" and region_id == 1
    meta = _meta(meta)
    assert meta["run_id"] == 42 and meta["period_index"] == 0 and meta["units"] == "30.000"
    assert meta["rate"] == 8.0 and meta["stock_before"] == "130.000" and meta["norm"] == "100.000"
    assert _legs(world, op_id) == [("emission", "country_treasury", 1, 240)]
    _assert_ledger_closes(world)


def test_court_mint_threshold_is_respected(world):
    _add_region(world, 1, template="capital")
    _set_params(world, mint_season_limit=100_000, mint_court_threshold_pct=150.0)
    _ore(world, 1, stock=140, norm=100)                     # 140 < 150 % of 100
    summary = _court(world)
    assert summary.mint_court_ops == 0 and _ops(world, "mint_court") == []
    assert _ore(world, 1)[0] == Decimal("140.000")
    assert _season(world, 1)[:2] == (0, 0)                 # the counter row exists, untouched

    _set_params(world, mint_court_threshold_pct=50.0)       # threshold 50 -> excess 90
    summary = _court(world, run_id=2)
    assert summary.mint_court_marks == 720
    assert _ore(world, 1)[0] == Decimal("50.000")


def test_court_mint_below_norm_takes_nothing_with_default_threshold(world):
    _add_region(world, 1, template="capital")
    _set_params(world, mint_season_limit=100_000)
    _ore(world, 1, stock=80, norm=100)
    assert _court(world).mint_court_ops == 0
    assert _ore(world, 1)[0] == Decimal("80.000")


def test_court_mint_manual_override_capital(world):
    _add_region(world, 1, template="capital")
    _add_region(world, 2, template="mining")
    _mint_row(world, 1, capital=2)
    _set_params(world, mint_season_limit=100_000)
    _ore(world, 1, stock=500, norm=100)
    _ore(world, 2, stock=110, norm=100)
    summary = _court(world)
    assert summary.mint_court_marks == 80
    assert _ore(world, 1)[0] == Decimal("500.000")          # the template capital is not the mint
    assert _ore(world, 2)[0] == Decimal("100.000")
    assert _ops(world, "mint_court")[0][2] == 2


def test_court_mint_stale_override_falls_back_to_auto(world):
    _add_region(world, 1, template="capital")
    _add_region(world, 9, template="capital", country_id=2)
    _mint_row(world, 1, capital=9)                          # region of another country
    _set_params(world, mint_season_limit=100_000)
    _ore(world, 1, stock=110, norm=100)
    _ore(world, 9, stock=110, norm=100)
    db = world()
    try:
        cap = mint_crud.capital_of(db, 1)
    finally:
        db.close()
    assert (cap.region_id, cap.source, cap.override_id, cap.override_stale) == (1, "auto", 9, True)
    summary = _court(world)
    # country 1 mints from region 1, country 2 from its own auto capital 9
    assert summary.mint_court_ops == 2
    assert sorted((r, k) for _i, k, r, _m in _ops(world, "mint_court")) == \
        [(1, "mint_court:1:c1"), (9, "mint_court:1:c2")]


def test_court_mint_no_capital_or_two_candidates_does_nothing(world):
    _add_region(world, 1, template="agrarian")              # country 1: no capital template
    _add_region(world, 5, template="capital", country_id=2)
    _add_region(world, 6, template="capital", country_id=2)  # country 2: two candidates
    _set_params(world, mint_season_limit=100_000)
    for rid in (1, 5, 6):
        _ore(world, rid, stock=500, norm=100)
    db = world()
    try:
        s1 = mint_crud.mint_status(db, 1)
        s2 = mint_crud.mint_status(db, 2)
    finally:
        db.close()
    assert s1.capital.source == "none" and s1.closed_reason == mint_crud.REASON_NO_CAPITAL
    assert s2.capital.source == "none" and [c.region_id for c in s2.candidates][:2] == [5, 6]
    summary = _court(world)
    assert summary.mint_court_ops == 0 and _ops(world, "mint_court") == []
    assert _rows(world, "SELECT COUNT(*) FROM econ_mint_seasons") == [(0,)]


def test_court_mint_disabled_country_is_skipped(world):
    _add_region(world, 1, template="capital")
    _add_region(world, 5, template="capital", country_id=2)
    _mint_row(world, 1, enabled=False)
    _set_params(world, mint_season_limit=100_000)
    _ore(world, 1, stock=200, norm=100)
    _ore(world, 5, stock=200, norm=100)
    summary = _court(world)
    assert summary.mint_court_ops == 1
    assert [k for _i, k, _r, _m in _ops(world, "mint_court")] == ["mint_court:1:c2"]
    assert _ore(world, 1)[0] == Decimal("200.000")


def test_court_mint_limit_zero_or_capital_not_participating_closes_the_mint(world):
    _add_region(world, 1, template="capital")
    _ore(world, 1, stock=200, norm=100)
    assert _court(world).mint_court_ops == 0                # default mint_season_limit 0 = closed
    _set_params(world, mint_season_limit=100_000)
    _exec(world, "UPDATE econ_regions SET population = 0 WHERE region_id = 1")
    db = world()
    try:
        assert mint_crud.mint_status(db, 1).closed_reason == mint_crud.REASON_NOT_PARTICIPATING
    finally:
        db.close()
    assert _court(world, run_id=2).mint_court_ops == 0
    assert _ops(world, "mint_court") == []


def test_court_mint_country_limit_override(world):
    _add_region(world, 1, template="capital")
    _mint_row(world, 1, limit=100)                          # overrides the default limit
    _set_params(world, mint_season_limit=100_000)
    _ore(world, 1, stock=200, norm=100)                     # 100 units * 8 = 800 marks possible
    summary = _court(world)
    assert summary.mint_court_marks == 100
    assert _ore(world, 1)[0] == Decimal("187.500")          # 100 / 8 = 12.5 units
    assert _season(world, 1)[0] == 100


def test_court_mint_shares_the_limit_with_players(world):
    _add_region(world, 1, template="capital")
    _set_params(world, mint_season_limit=1000)
    _ore(world, 1, stock=300, norm=100)
    _exec(world, "INSERT INTO econ_mint_seasons (country_id, period_index, minted_court, minted_players, "
                 "ore_units_court, ore_units_players, created_at) VALUES (1, 0, 0, 960, 0, 5, :t)", t=T0)
    summary = _court(world)
    assert summary.mint_court_marks == 40
    assert _season(world, 1)[:2] == (40, 960)
    assert _ore(world, 1)[0] == Decimal("295.000")
    # the limit is exhausted now: the next run takes nothing
    assert _court(world, run_id=2).mint_court_ops == 0
    assert _ore(world, 1)[0] == Decimal("295.000")


def test_court_mint_limit_counts_per_season(world):
    _add_region(world, 1, template="capital")
    _set_params(world, mint_season_limit=80)
    _ore(world, 1, stock=300, norm=100)
    assert _court(world).mint_court_marks == 80
    assert _court(world, run_id=2).mint_court_marks == 0
    assert _court(world, run_id=3, now=NEXT_SEASON).mint_court_marks == 80        # new season row
    assert _season(world, 1, 0)[0] == 80 and _season(world, 1, 1)[0] == 80


def test_court_mint_rerun_of_the_same_run_is_a_duplicate(world):
    _add_region(world, 1, template="capital")
    _set_params(world, mint_season_limit=100_000)
    _ore(world, 1, stock=130, norm=100)
    assert _court(world, run_id=5).mint_court_marks == 240
    _ore(world, 1, stock=130, norm=100)                     # surplus again, same run id
    again = _court(world, run_id=5)
    assert again.mint_court_ops == 0 and again.mint_failures == 0
    assert _ore(world, 1)[0] == Decimal("130.000")          # rolled back with the duplicate posting
    assert _season(world, 1)[0] == 240
    assert len(_ops(world, "mint_court")) == 1
    _assert_ledger_closes(world)


def test_a_failing_country_does_not_stop_the_others(world, monkeypatch):
    _add_region(world, 1, template="capital")
    _add_region(world, 5, template="capital", country_id=2)
    _set_params(world, mint_season_limit=100_000)
    _ore(world, 1, stock=130, norm=100)
    _ore(world, 5, stock=130, norm=100)
    real = mint_crud.court_mint

    def flaky(db, status, **kw):
        if status.country_id == 1:
            real(db, status, **kw)                          # writes, then fails before the commit
            raise RuntimeError("boom")
        return real(db, status, **kw)

    monkeypatch.setattr(mint_crud, "court_mint", flaky)
    summary = _court(world)
    assert (summary.mint_failures, summary.mint_failed_country_ids) == (1, [1])
    assert (summary.mint_court_ops, summary.mint_court_marks) == (1, 240)
    assert _ore(world, 1)[0] == Decimal("130.000")          # country 1 rolled back entirely
    assert _season(world, 1)[0] == 0
    assert [k for _i, k, _r, _m in _ops(world, "mint_court")] == ["mint_court:1:c2"]
    _assert_ledger_closes(world)


def test_mint_failure_is_written_to_the_run_error(world, monkeypatch):
    _add_region(world, 1, template="capital", population=40_000)
    _set_params(world, mint_season_limit=100_000, mint_court_threshold_pct=0.0)

    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(mint_crud, "court_mint", boom)
    summary = econ_tick.run_tick(world, trigger="manual", now=T0)
    assert summary.mint_failures == 1 and summary.status == "done"
    error = _scalar(world, "SELECT error FROM econ_tick_runs WHERE id = :i", i=summary.run_id)
    assert error == econ_tick.MINT_ERROR_PREFIX + "1"


def test_court_mint_without_calendar_is_idle(world):
    _add_region(world, 1, template="capital")
    _set_params(world, mint_season_limit=100_000)
    _ore(world, 1, stock=500, norm=100)
    _exec(world, "DELETE FROM game_time_config")
    summary = _court(world)
    assert summary.mint_court_ops == 0 and summary.mint_failures == 0
    assert _ore(world, 1)[0] == Decimal("500.000")


# --------------------------------------------------------------------------------------------- full run

def test_full_run_quota_then_regions_then_court_mint(world):
    """In a real run the quota is posted before the region loop and the court mints after it from the fresh stock."""
    _add_region(world, 1, template="capital", population=40_000)
    _add_region(world, 2, template="mining")
    _set_params(world, quota_season_amount=5000, mint_season_limit=1_000_000, mint_court_threshold_pct=0.0)
    _below_norm(world, 1, 2)

    summary = econ_tick.run_tick(world, trigger="manual", now=T0)
    assert summary.status == "done" and summary.quota_amount == 5000
    assert summary.mint_court_ops == 1 and summary.mint_court_marks > 0
    quota_id = _ops(world, "season_quota")[0][0]
    (mint_id, key, _r, meta), = _ops(world, "mint_court")
    tick_ids = [r[0] for r in _rows(world, "SELECT id FROM econ_operations WHERE op_type = 'region_tick'")]
    assert quota_id < min(tick_ids) < max(tick_ids) < mint_id          # quota -> regions -> mint
    assert key == f"mint_court:{summary.run_id}:c1"
    meta = _meta(meta)
    stock_after, _norm = _ore(world, 1)
    assert stock_after == Decimal(meta["stock_before"]) - Decimal(meta["units"])
    expected = econ_mint.court_mint(Decimal(meta["stock_before"]), Decimal(meta["norm"]), 0.0, 8.0, 1_000_000)
    assert expected.marks == summary.mint_court_marks
    assert _season(world, 1)[0] == summary.mint_court_marks
    run_error = _scalar(world, "SELECT error FROM econ_tick_runs WHERE id = :i", i=summary.run_id)
    assert run_error is None
    _assert_ledger_closes(world)
