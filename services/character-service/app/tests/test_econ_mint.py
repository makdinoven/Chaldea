"""FEAT-191 QA (#8): pure math of the mint and the season quota (``econ_mint``) — no DB.

* ``period_of`` — season period boundaries (day 48/49), year rollover at 196, ``offset_days``, negative elapsed
  clamp, ``ends_at``; parity with locations-service ``compute_game_time`` (reference copy below).
* ``court_mint`` — threshold (0 / 50 / 100 %), rate rounding, units never above the excess, the remaining cap,
  zero cases.
* ``split_quota`` — exact sum, largest remainders, ties to the lower region id, zero population dropped.
"""

import math
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

import econ_core as core
import econ_mint

EPOCH = datetime(2026, 3, 19, 0, 0)


# --------------------------------------------------------------------------------------------- reference calendar
# Literal copy of locations-service/app/crud.py compute_game_time (the source of truth of the calendar).

_LOC_SEGMENTS = [
    {"name": "spring", "type": "season", "real_days": 39},
    {"name": "beltane", "type": "transition", "real_days": 10},
    {"name": "summer", "type": "season", "real_days": 39},
    {"name": "lughnasad", "type": "transition", "real_days": 10},
    {"name": "autumn", "type": "season", "real_days": 39},
    {"name": "samhain", "type": "transition", "real_days": 10},
    {"name": "winter", "type": "season", "real_days": 39},
    {"name": "imbolc", "type": "transition", "real_days": 10},
]
_LOC_DAYS_PER_YEAR = 196
_FESTIVAL_SEASON = {"beltane": "spring", "lughnasad": "summer", "samhain": "autumn", "imbolc": "winter"}


def _loc_compute_game_time(epoch, offset_days, now):
    elapsed_real_days = math.floor((now - epoch).total_seconds() / 86400) + offset_days
    if elapsed_real_days < 0:
        elapsed_real_days = 0
    year = elapsed_real_days // _LOC_DAYS_PER_YEAR + 1
    day_in_year = elapsed_real_days % _LOC_DAYS_PER_YEAR
    current = _LOC_SEGMENTS[0]
    cumulative = 0
    for segment in _LOC_SEGMENTS:
        if day_in_year < cumulative + segment["real_days"]:
            current = segment
            break
        cumulative += segment["real_days"]
    return {"year": year, "segment_name": current["name"], "segment_type": current["type"]}


def _day(n, hours=0):
    return EPOCH + timedelta(days=n, hours=hours)


# --------------------------------------------------------------------------------------------- calendar mirror

def test_calendar_mirror_matches_locations_layout():
    assert [(n, t, d) for n, t, d in econ_mint.YEAR_SEGMENTS] == \
        [(s["name"], s["type"], s["real_days"]) for s in _LOC_SEGMENTS]
    assert econ_mint.DAYS_PER_YEAR == 196
    assert econ_mint.PERIOD_DAYS == 49
    assert econ_mint.PERIODS_PER_YEAR == 4
    assert econ_mint.SEASONS == ("spring", "summer", "autumn", "winter")


# --------------------------------------------------------------------------------------------- period_of

def test_first_period_at_epoch():
    p = econ_mint.period_of(EPOCH, 0, EPOCH)
    assert (p.index, p.year, p.season) == (0, 1, "spring")
    assert p.starts_at == EPOCH and p.ends_at == EPOCH + timedelta(days=49)


def test_day_48_is_still_the_first_period_day_49_is_the_second():
    last = econ_mint.period_of(EPOCH, 0, _day(48, hours=23))
    assert (last.index, last.season) == (0, "spring")          # festival beltane belongs to spring
    nxt = econ_mint.period_of(EPOCH, 0, _day(49))
    assert (nxt.index, nxt.year, nxt.season) == (1, 1, "summer")
    assert nxt.starts_at == last.ends_at == _day(49)
    assert nxt.ends_at == _day(98)


def test_period_ends_at_is_exclusive():
    p = econ_mint.period_of(EPOCH, 0, _day(10))
    assert econ_mint.period_of(EPOCH, 0, p.ends_at - timedelta(seconds=1)).index == p.index
    assert econ_mint.period_of(EPOCH, 0, p.ends_at).index == p.index + 1


def test_year_rollover_at_196_days():
    winter = econ_mint.period_of(EPOCH, 0, _day(195))
    assert (winter.index, winter.year, winter.season) == (3, 1, "winter")
    spring2 = econ_mint.period_of(EPOCH, 0, _day(196))
    assert (spring2.index, spring2.year, spring2.season) == (4, 2, "spring")
    assert spring2.starts_at == _day(196)
    later = econ_mint.period_of(EPOCH, 0, _day(196 * 3 + 49 * 2 + 5))
    assert (later.index, later.year, later.season) == (14, 4, "autumn")


def test_offset_days_shifts_the_period_and_its_bounds():
    # offset 60 days: day 0 is elapsed 60 -> period 1 (summer), it started 11 real days before the epoch
    p = econ_mint.period_of(EPOCH, 60, EPOCH)
    assert (p.index, p.year, p.season) == (1, 1, "summer")
    assert p.starts_at == EPOCH - timedelta(days=11)
    assert p.ends_at == EPOCH + timedelta(days=38)
    # a lore-epoch offset of several years (the year is never hardcoded)
    big = econ_mint.period_of(EPOCH, 196 * 1000 + 100, _day(0))
    assert (big.index, big.year, big.season) == (4002, 1001, "autumn")


def test_negative_elapsed_is_clamped_to_the_first_period():
    p = econ_mint.period_of(EPOCH, 0, EPOCH - timedelta(days=30))
    assert (p.index, p.year, p.season) == (0, 1, "spring")
    assert econ_mint.elapsed_days(EPOCH, 0, EPOCH - timedelta(days=30)) == 0
    assert econ_mint.elapsed_days(EPOCH, -10, _day(5)) == 0
    assert econ_mint.elapsed_days(EPOCH, None, _day(5)) == 5


def test_aware_datetimes_are_treated_as_utc():
    aware_now = (_day(50)).replace(tzinfo=timezone.utc)
    assert econ_mint.period_of(EPOCH, 0, aware_now) == econ_mint.period_of(EPOCH, 0, _day(50))
    msk = timezone(timedelta(hours=3))
    assert econ_mint.period_of(EPOCH, 0, (_day(49)).replace(tzinfo=timezone.utc).astimezone(msk)).index == 1


def test_parity_with_locations_compute_game_time():
    rng = random.Random(191)
    samples = [(0, _day(d)) for d in range(0, 800)]
    samples += [(rng.randint(-50, 5000), EPOCH + timedelta(seconds=rng.randint(-10 ** 6, 10 ** 8)))
                for _ in range(1500)]
    for offset, now in samples:
        ref = _loc_compute_game_time(EPOCH, offset, now)
        p = econ_mint.period_of(EPOCH, offset, now)
        assert p.year == ref["year"], (offset, now)
        expected = ref["segment_name"] if ref["segment_type"] == "season" else _FESTIVAL_SEASON[ref["segment_name"]]
        assert p.season == expected, (offset, now)
        if math.floor((now - EPOCH).total_seconds() / 86400) + offset >= 0:     # not clamped
            assert p.starts_at <= now < p.ends_at, (offset, now)


def test_period_to_dict_shape():
    d = econ_mint.period_of(EPOCH, 0, _day(1)).to_dict()
    assert set(d) == {"index", "year", "season", "starts_at", "ends_at"}


def test_fmt_date():
    assert econ_mint.fmt_date(datetime(2026, 11, 12, 5, 0)) == "12.11.2026"
    assert econ_mint.fmt_date(None) == "—"


# --------------------------------------------------------------------------------------------- court_mint

def test_court_mint_below_or_at_threshold_takes_nothing():
    for stock in (0, 50, 100):
        r = econ_mint.court_mint(stock, 100, 100, 8, 10_000)
        assert r.marks == 0 and r.units == Decimal("0")


def test_court_mint_above_threshold_100():
    r = econ_mint.court_mint(Decimal("130.000"), Decimal("100.000"), 100, 8, 10_000)
    assert r.excess == Decimal("30.000")
    assert r.marks == 240 and r.units == Decimal("30.000")


@pytest.mark.parametrize("threshold,excess,marks", [(0, Decimal("130.000"), 1040), (50, Decimal("80.000"), 640),
                                                    (100, Decimal("30.000"), 240), (200, Decimal("0"), 0)])
def test_court_mint_thresholds(threshold, excess, marks):
    r = econ_mint.court_mint(130, 100, threshold, 8, 10 ** 9)
    assert r.excess == excess and r.marks == marks
    if marks:
        assert r.units == excess


def test_court_mint_rate_rounding_floor_marks_ceil_units_capped_by_excess():
    # excess 10.005 * 3 = 30.015 -> 30 marks; 30 / 3 = 10.000 units
    r = econ_mint.court_mint(Decimal("110.005"), 100, 100, 3, 10_000)
    assert r.marks == 30 and r.units == Decimal("10.000")
    # rate 7: excess 1.5 -> 10.5 -> 10 marks; 10/7 = 1.4285.. -> ceil_3 1.429 (<= excess)
    r = econ_mint.court_mint(Decimal("101.500"), 100, 100, 7, 10_000)
    assert r.marks == 10 and r.units == Decimal("1.429")
    # fractional rate: excess 0.333 * 3.3 = 1.0989 -> 1 mark; 1/3.3 = 0.30303 -> 0.304
    r = econ_mint.court_mint(Decimal("100.333"), 100, 100, 3.3, 10_000)
    assert r.marks == 1 and r.units == Decimal("0.304")


def test_court_mint_units_never_exceed_excess():
    rng = random.Random(7)
    for _ in range(3000):
        stock = Decimal(rng.randint(0, 10 ** 7)) / 1000
        norm = Decimal(rng.randint(0, 10 ** 7)) / 1000
        rate = round(rng.uniform(0.01, 50), 2)
        threshold = rng.choice([0, 25, 50, 100, 150])
        remaining = rng.choice([0, 1, 7, 100, 10 ** 9])
        r = econ_mint.court_mint(stock, norm, threshold, rate, remaining)
        assert 0 <= r.marks <= remaining
        assert Decimal(0) <= r.units <= r.excess
        assert r.units == r.units.quantize(Decimal("0.001"))
        if r.marks:
            # the marks are covered by the ore taken
            assert Decimal(r.marks) <= r.units * Decimal(str(rate)) + Decimal("0.0000001") or r.units == r.excess


def test_court_mint_remaining_caps_marks_and_units():
    r = econ_mint.court_mint(1000, 100, 100, 8, 50)
    assert r.marks == 50 and r.units == Decimal("6.250")
    assert r.excess == Decimal("900.000")


@pytest.mark.parametrize("kwargs", [
    {"remaining": 0}, {"remaining": -5}, {"marks_per_unit": 0}, {"marks_per_unit": -1}, {"stock": 0},
    {"stock": Decimal("100.0001")},                  # excess floors to 0.000
])
def test_court_mint_zero_cases(kwargs):
    args = {"stock": 200, "norm": 100, "threshold_pct": 100, "marks_per_unit": 8, "remaining": 1000}
    args.update(kwargs)
    r = econ_mint.court_mint(**args)
    assert r.marks == 0 and r.units == Decimal("0")


def test_court_mint_tiny_excess_below_one_mark():
    # 0.1 units * 8 = 0.8 marks -> floor 0 -> nothing taken
    r = econ_mint.court_mint(Decimal("100.100"), 100, 100, 8, 1000)
    assert r.marks == 0 and r.units == Decimal("0")
    assert r.excess == Decimal("0.100")


def test_remaining_limit():
    assert econ_mint.remaining_limit(1000, 300, 200) == 500
    assert econ_mint.remaining_limit(1000, 900, 200) == 0
    assert econ_mint.remaining_limit(0, 0, 0) == 0


# --------------------------------------------------------------------------------------------- split_quota

def test_split_quota_exact_sum_proportional():
    shares = econ_mint.split_quota(10_000, {1: 5000, 2: 3000, 3: 2000})
    assert shares == {1: 5000, 2: 3000, 3: 2000}


def test_split_quota_largest_remainder():
    # 100 by 1:1:1 -> 33 each, leftover 1 -> lowest id (all remainders tie)
    assert econ_mint.split_quota(100, {3: 10, 1: 10, 2: 10}) == {1: 34, 2: 33, 3: 33}
    # 10 by 6:3:1 of 7 marks: 4.2 / 2.1 / 0.7 -> floors 4,2,0, leftover 1 -> largest remainder (region 3: .7)
    assert econ_mint.split_quota(7, {1: 6, 2: 3, 3: 1}) == {1: 4, 2: 2, 3: 1}


def test_split_quota_ties_go_to_lower_region_id():
    assert econ_mint.split_quota(1, {9: 5, 4: 5}) == {4: 1}
    assert econ_mint.split_quota(2, {9: 1, 4: 1, 7: 1}) == {4: 1, 7: 1}


def test_split_quota_drops_zero_population_and_zero_shares():
    assert econ_mint.split_quota(100, {1: 0, 2: 50, 3: -10}) == {2: 100}
    # a tiny region whose share floors to 0 and gets no leftover is dropped
    shares = econ_mint.split_quota(10, {1: 1_000_000, 2: 1})
    assert shares == {1: 10}


def test_split_quota_nothing_to_split():
    assert econ_mint.split_quota(0, {1: 10}) == {}
    assert econ_mint.split_quota(-5, {1: 10}) == {}
    assert econ_mint.split_quota(100, {}) == {}
    assert econ_mint.split_quota(100, {1: 0}) == {}


def test_split_quota_sum_is_always_exact():
    rng = random.Random(42)
    for _ in range(500):
        pops = {rid: rng.randint(0, 10 ** 6) for rid in rng.sample(range(1, 200), rng.randint(1, 12))}
        amount = rng.randint(0, 10 ** 7)
        shares = econ_mint.split_quota(amount, pops)
        if amount > 0 and any(p > 0 for p in pops.values()):
            assert sum(shares.values()) == amount
        assert all(v > 0 for v in shares.values())
        assert all(pops[r] > 0 for r in shares)


# --------------------------------------------------------------------------------------------- op types (econ_core)

def test_mint_op_types_are_sources_without_comment():
    assert core.MINT_OP_TYPES == {core.OP_MINT_COURT, core.OP_MINT_PLAYER, core.OP_SEASON_QUOTA}
    assert (core.OP_MINT_COURT, core.OP_MINT_PLAYER, core.OP_SEASON_QUOTA) == \
        ("mint_court", "mint_player", "season_quota")
    assert core.MINT_OP_TYPES <= core.OP_TYPES
    assert core.MINT_OP_TYPES <= core.SOURCE_OP_TYPES
    assert not (core.MINT_OP_TYPES & core.COMMENT_REQUIRED_OP_TYPES)
