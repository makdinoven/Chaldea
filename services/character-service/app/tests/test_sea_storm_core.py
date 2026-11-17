"""FEAT-214 QA (T10): the pure storm / raid helpers of ``sea_core`` (features/FEAT-214 §3.4)."""

import math
import random
from decimal import Decimal
from types import SimpleNamespace

import pytest

import sea_core
import sea_crud

# the sea_world geography: sea 30 = 501, 502, 503, 505; sea 31 = 504
ADJ = {501: [502, 505], 502: [501, 503], 503: [502, 505, 504], 504: [503], 505: [501, 503]}
SEA = {501: 30, 502: 30, 503: 30, 505: 30, 504: 31}


# =============================================================================================== season_mult

@pytest.mark.parametrize("season, expected", [
    ("spring", Decimal("1.00")), ("summer", Decimal("0.50")), ("autumn", Decimal("1.50")),
    ("winter", Decimal("2.00")), (None, Decimal("1")), ("", Decimal("1")), ("festival", Decimal("1")),
    ("WINTER", Decimal("1")),
])
def test_season_mult_defaults(season, expected):
    assert sea_core.season_mult(season, sea_crud.SeaParams()) == expected


def test_season_mult_reads_the_params_and_never_goes_negative():
    params = SimpleNamespace(season_mult_winter=Decimal("3.25"), season_mult_summer=-1, season_mult_autumn=None)
    assert sea_core.season_mult("winter", params) == Decimal("3.25")
    assert sea_core.season_mult("summer", params) == Decimal("0")
    assert sea_core.season_mult("autumn", params) == Decimal("1")       # missing value → 1
    assert sea_core.season_mult("spring", params) == Decimal("1")       # attribute absent → 1


# =============================================================================================== pass_chance

@pytest.mark.parametrize("pct, mult, elapsed, expected", [
    (0, 1, 60, 0), (50, 0, 60, 0), (50, 1, 0, 0), (50, 1, -5, 0),
    (100, 1, 1, 1), (60, 2, 30, 1),                       # p capped at 1
    (50, 1, 60, 0.5), (10, 2, 60, 0.2), (50, Decimal("0.5"), 60, 0.25),
    (50, 1, 120, 0.5), (50, 1, 600, 0.5),                 # elapsed clamped to one hour: no burst after a downtime
])
def test_pass_chance(pct, mult, elapsed, expected):
    assert float(sea_core.pass_chance(pct, mult, elapsed)) == pytest.approx(expected, abs=1e-9)


def test_pass_chance_is_compounded_per_hour():
    assert float(sea_core.pass_chance(50, 1, 30)) == pytest.approx(1 - 0.5 ** 0.5, abs=1e-9)
    assert float(sea_core.pass_chance(20, 1, 1)) == pytest.approx(1 - 0.8 ** (1 / 60), abs=1e-9)
    assert isinstance(sea_core.pass_chance(20, 1, 1), Decimal)


def test_pass_chance_grows_with_elapsed_up_to_the_hour():
    values = [sea_core.pass_chance(30, 1, m) for m in (1, 10, 30, 60, 61)]
    assert values == sorted(values) and values[-1] == values[-2]


# =============================================================================================== split_groups

@pytest.mark.parametrize("n, sizes", [
    (0, []), (1, [1]), (5, [5]), (6, [3, 3]), (7, [4, 3]), (10, [5, 5]), (11, [4, 4, 3]), (12, [4, 4, 4]),
    (16, [4, 4, 4, 4]), (23, [5, 5, 5, 4, 4]),
])
def test_split_groups_sizes(n, sizes):
    groups = sea_core.split_groups(range(1, n + 1))
    assert [len(g) for g in groups] == sizes


def test_split_groups_six_is_three_plus_three_ascending():
    assert sea_core.split_groups([6, 2, 5, 1, 4, 3]) == [[1, 2, 3], [4, 5, 6]]


def test_split_groups_dedups_and_sorts():
    assert sea_core.split_groups([9, 3, 3, "7", 1]) == [[1, 3, 7, 9]]


@pytest.mark.parametrize("n", range(1, 41))
def test_split_groups_invariants(n):
    ids = random.Random(n).sample(range(100, 1000), n)
    groups = sea_core.split_groups(ids)
    sizes = [len(g) for g in groups]
    assert len(groups) == math.ceil(n / sea_core.SEA_RAID_TEAM_MAX)
    assert max(sizes) <= sea_core.SEA_RAID_TEAM_MAX and max(sizes) - min(sizes) <= 1
    assert [c for g in groups for c in g] == sorted(ids)


def test_split_groups_custom_cap():
    assert sea_core.split_groups(range(1, 5), cap=2) == [[1, 2], [3, 4]]
    assert [len(g) for g in sea_core.split_groups(range(1, 4), cap=0)] == [1, 1, 1]   # cap floored at 1


# =============================================================================================== pack_size

@pytest.mark.parametrize("max_active, group, expected", [
    (3, 5, 3), (10, 5, 5), (5, 2, 2), (0, 3, 1), (None, 2, 1), (-3, 4, 1), (1, 1, 1), (5, 0, 0), (7, 5, 5),
])
def test_pack_size(max_active, group, expected):
    assert sea_core.pack_size(max_active, group) == expected


# =============================================================================================== storm_zones

@pytest.mark.parametrize("center, radius, expected", [
    (501, 0, [501]), (501, 1, [501, 502, 505]), (501, 2, [501, 502, 503, 505]), (503, 5, [501, 502, 503, 505]),
    (504, 3, [504]), (502, None, [502]), (502, -2, [502]),
])
def test_storm_zones_stay_in_the_centres_sea(center, radius, expected):
    assert sea_core.storm_zones(ADJ, SEA, center, radius) == expected


def test_storm_zones_skip_neighbours_unknown_to_the_sea_map():
    assert sea_core.storm_zones({1: [2, 3]}, {1: 7, 3: 7}, 1, 1) == [1, 3]


def test_storm_zones_centre_without_a_sea_keeps_to_sea_less_zones():
    assert sea_core.storm_zones({1: [2, 3]}, {1: None, 2: None, 3: 5}, 1, 2) == [1, 2]


# =============================================================================================== storm_extra / relief

@pytest.mark.parametrize("zone_minutes, mult, expected", [
    (10, 2, 10), (10, 1, 0), (10, Decimal("1.5"), 5), (10, Decimal("1.25"), 3), (7, Decimal("2.5"), 11),
    (0, 2, 1), (10, Decimal("0.5"), 0), (10, 10, 90),
])
def test_storm_extra(zone_minutes, mult, expected):
    assert sea_core.storm_extra(zone_minutes, mult) == expected


@pytest.mark.parametrize("extra, pct, expected", [
    (10, 50, 5), (11, 50, 5), (10, 0, 0), (10, 100, 10), (10, 150, 10), (-5, 50, 0), (3, Decimal("33.33"), 0),
    (0, 50, 0), (None, 50, 0), (9, -10, 0),
])
def test_relief(extra, pct, expected):
    assert sea_core.relief(extra, pct) == expected


# =============================================================================================== pick_drift

class _Pick:
    def __init__(self, i):
        self.i = i

    def randrange(self, n):
        return min(self.i, n - 1)


def test_pick_drift_never_the_next_zone():
    assert sea_core.pick_drift(ADJ, 502, 503, _Pick(0)) == 501
    assert sea_core.pick_drift(ADJ, 503, 502, _Pick(0)) == 504
    assert sea_core.pick_drift(ADJ, 503, 502, _Pick(5)) == 505


def test_pick_drift_without_a_next_zone_takes_any_neighbour():
    assert sea_core.pick_drift(ADJ, 501, None, _Pick(1)) == 505


@pytest.mark.parametrize("adj, current, nxt", [
    ({504: [503]}, 504, 503), ({1: []}, 1, None), ({}, 1, 2), ({1: [1]}, 1, None),
])
def test_pick_drift_none_when_there_is_no_other_neighbour(adj, current, nxt):
    assert sea_core.pick_drift(adj, current, nxt, _Pick(0)) is None


def test_pick_drift_with_a_real_rng_stays_in_the_options():
    rng = random.Random(7)
    seen = {sea_core.pick_drift(ADJ, 503, 502, rng) for _ in range(50)}
    assert seen <= {504, 505} and seen


def test_weather_rng_is_a_fresh_random():
    a, b = sea_core.weather_rng(), sea_core.weather_rng()
    assert isinstance(a, random.Random) and a is not b


def test_raid_status_sets_are_disjoint():
    assert not set(sea_core.RAID_ACTIVE_STATUSES) & set(sea_core.RAID_FINAL_STATUSES)
    assert sea_core.SEA_RAID_TEAM_MAX == 5
