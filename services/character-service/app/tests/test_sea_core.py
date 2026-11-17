"""FEAT-213 QA (T7): pure rules of ``sea_core`` (features/FEAT-213 §3.4, §3.5) — no DB, no clock, no RNG.

Stop sequence (there-and-back / loop), skipping invalid stops, trip numbering, leg overrides (forward / reversed /
loop closing leg), override validation, the leg path (override vs BFS, same zone, no zone / no path), fares (base +
per zone), seats, entitlement, ETAs and the post length used by the sailor check.
"""

from datetime import datetime, timedelta

import pytest

import sea_core as sc

# zone graph of the sea world: 501-502-503 and 501-505-503, 503-504
ADJ = {501: [502, 505], 502: [501, 503], 503: [502, 504, 505], 504: [503], 505: [501, 503]}
ZONES = {501, 502, 503, 504, 505}


def _sequence(n, is_loop, steps, start=0, direction=1):
    out, i, d = [start], start, direction
    for _ in range(steps):
        i, d = sc.next_stop(i, d, n, is_loop)
        out.append(i)
    return out


# =============================================================================================== stop sequence

def test_there_and_back_flips_at_both_ends():
    assert _sequence(3, False, 8) == [0, 1, 2, 1, 0, 1, 2, 1, 0]
    assert _sequence(2, False, 4) == [0, 1, 0, 1, 0]


def test_there_and_back_direction_is_reported():
    assert sc.next_stop(2, 1, 3, False) == (1, -1)
    assert sc.next_stop(0, -1, 3, False) == (1, 1)
    assert sc.next_stop(1, -1, 3, False) == (0, -1)


def test_loop_wraps_and_is_always_forward():
    assert _sequence(3, True, 6) == [0, 1, 2, 0, 1, 2, 0]
    assert sc.next_stop(2, -1, 3, True) == (0, sc.DIRECTION_FORWARD)


def test_a_single_stop_never_moves():
    assert sc.next_stop(0, 1, 1, False) == (0, 1)
    assert sc.next_valid_stop(0, 1, 1, False, [0]) is None


def test_next_valid_stop_skips_invalid_ones_and_counts_them():
    assert sc.next_valid_stop(0, 1, 4, False, [0, 1, 2, 3]) == (1, 1, 0)
    assert sc.next_valid_stop(0, 1, 4, False, [0, 3]) == (3, 1, 2)
    # there-and-back from the end: 3 -> 2 (invalid) -> 1
    assert sc.next_valid_stop(3, 1, 4, False, [1, 3]) == (1, -1, 1)
    # loop: 2 -> 0 (invalid) -> 1
    assert sc.next_valid_stop(2, 1, 3, True, [1, 2]) == (1, 1, 1)


def test_next_valid_stop_none_when_only_the_current_stop_is_valid():
    assert sc.next_valid_stop(1, 1, 3, False, [1]) is None
    assert sc.next_valid_stop(0, 1, 3, True, []) is None


# =============================================================================================== trips

def test_future_trips_number_departures_from_the_first_trip():
    trips = sc.future_trips(0, 1, 3, False, first_trip=5, count=4)
    assert [(t.trip, t.from_idx, t.to_idx, t.direction, t.adjacent) for t in trips] == [
        (5, 0, 1, 1, True), (6, 1, 2, 1, True), (7, 2, 1, -1, True), (8, 1, 0, -1, True)]


def test_future_trips_mark_a_skipping_trip_as_not_adjacent():
    trips = sc.future_trips(0, 1, 3, False, 1, 2, valid=[0, 2])
    assert [(t.from_idx, t.to_idx, t.adjacent) for t in trips] == [(0, 2, False), (2, 0, False)]


def test_future_trips_stop_when_no_valid_stop_is_left():
    assert sc.future_trips(0, 1, 3, False, 1, 3, valid=[0]) == []
    assert sc.future_trips(0, 1, 3, False, 1, 0) == []


def test_future_trips_start_from_the_sailing_target_backwards():
    trips = sc.future_trips(1, -1, 3, False, 3, 2)
    assert [(t.from_idx, t.to_idx) for t in trips] == [(1, 0), (0, 1)]


# =============================================================================================== overrides

def test_override_forward_leg_uses_its_own_stop():
    assert sc.override_for(0, 1, 3, False, {0: [501, 505, 503]}) == [501, 505, 503]


def test_override_reverse_leg_uses_the_previous_stop_reversed():
    assert sc.override_for(1, 0, 3, False, {0: [501, 505, 503]}) == [503, 505, 501]


def test_override_loop_closing_leg_uses_the_last_stop():
    assert sc.override_for(2, 0, 3, True, {2: [504, 503, 501]}) == [504, 503, 501]
    assert sc.override_for(1, 0, 3, True, {0: [1, 2]}) is None    # no reverse legs on a loop


def test_override_none_for_non_adjacent_or_missing():
    assert sc.override_for(0, 2, 3, False, {0: [1, 2]}) is None
    assert sc.override_for(0, 1, 3, False, {}) is None
    assert sc.override_for(0, 1, 3, False, {0: None}) is None


@pytest.mark.parametrize("path, problem", [
    ([501, 505, 503], None),
    ([501, 502, 503], None),
    ([502, 503], sc.LEG_BAD_OVERRIDE),           # wrong start
    ([501, 502], sc.LEG_BAD_OVERRIDE),           # wrong goal
    ([501, 999, 503], sc.LEG_BAD_OVERRIDE),      # not a zone
    ([501, 503], sc.LEG_BAD_OVERRIDE),           # not adjacent
    ([501, 501, 502, 503], sc.LEG_BAD_OVERRIDE),  # repeated
    ([], sc.LEG_BAD_OVERRIDE),
    (None, sc.LEG_BAD_OVERRIDE),
])
def test_override_problem(path, problem):
    assert sc.override_problem(path, 501, 503, ADJ, ZONES, 200) == problem


def test_override_problem_respects_the_zone_limit():
    assert sc.override_problem([501, 502, 503], 501, 503, ADJ, ZONES, 2) == sc.LEG_BAD_OVERRIDE
    assert sc.override_problem([501, 502, 503], 501, 503, ADJ, ZONES, 3) is None


# =============================================================================================== leg path

def test_leg_path_bfs_is_deterministic_by_ascending_ids():
    assert sc.leg_path(ADJ, ZONES, 501, 503, None, 200) == ([501, 502, 503], None, False)
    assert sc.leg_path(ADJ, ZONES, 501, 504, None, 200) == ([501, 502, 503, 504], None, False)


def test_leg_path_valid_override_wins():
    assert sc.leg_path(ADJ, ZONES, 501, 503, [501, 505, 503], 200) == ([501, 505, 503], None, True)


def test_leg_path_bad_override_falls_back_to_bfs_with_a_problem():
    assert sc.leg_path(ADJ, ZONES, 501, 503, [501, 503], 200) == ([501, 502, 503], sc.LEG_BAD_OVERRIDE, False)


def test_leg_path_same_zone_is_one_zone():
    assert sc.leg_path(ADJ, ZONES, 503, 503, None, 200) == ([503], None, False)


def test_leg_path_without_a_zone():
    assert sc.leg_path(ADJ, ZONES, None, 503, None, 200) == (None, sc.LEG_NO_ZONE, False)
    assert sc.leg_path(ADJ, ZONES, 501, 999, None, 200) == (None, sc.LEG_NO_ZONE, False)


def test_leg_path_without_a_connection():
    adj = {501: [502], 502: [501], 503: []}
    assert sc.leg_path(adj, {501, 502, 503}, 501, 503, None, 200) == (None, sc.LEG_NO_PATH, False)


def test_leg_path_respects_the_bfs_limit():
    assert sc.leg_path(ADJ, ZONES, 501, 504, None, 3)[0] is None
    assert sc.leg_path(ADJ, ZONES, 501, 504, None, 4)[0] == [501, 502, 503, 504]


# =============================================================================================== money, seats, rights

@pytest.mark.parametrize("base, per_zone, zones, expected", [
    (10, 5, 3, 25), (10, 5, 5, 35), (0, 0, 7, 0), (10, 5, 0, 10), (-50, 5, 2, 0), (None, None, None, 0),
])
def test_fare_is_base_plus_per_zone_and_never_negative(base, per_zone, zones, expected):
    assert sc.fare(base, per_zone, zones) == expected


def test_covers_and_entitled():
    assert sc.covers(2, 4, 2) and sc.covers(2, 4, 4) and not sc.covers(2, 4, 5) and not sc.covers(2, 4, 1)
    for kind in sc.PASS_KINDS:
        assert sc.entitled(kind, sc.PASS_ACTIVE, 1, 1, 1)
    assert not sc.entitled("cargo", sc.PASS_ACTIVE, 1, 1, 1)
    for status in sc.PASS_STATUSES:
        if status != sc.PASS_ACTIVE:
            assert not sc.entitled(sc.KIND_TICKET, status, 1, 3, 2)


def test_seats_left_is_the_minimum_over_the_range():
    assert sc.seats_left(3, {1: 1, 2: 3}, [1]) == 2
    assert sc.seats_left(3, {1: 1, 2: 3}, [1, 2]) == 0
    assert sc.seats_left(3, {1: 5}, [1]) == 0              # never negative
    assert sc.seats_left(3, {}, []) == 0                   # an empty range sells nothing


# =============================================================================================== times

def test_leg_minutes_has_a_floor_of_one_zone():
    assert sc.leg_minutes(3, 10) == 30
    assert sc.leg_minutes(0, 10) == 10
    assert sc.leg_minutes(2, 0) == 2


def test_current_leg_arrival():
    t = datetime(2026, 1, 1, 12, 0)
    assert sc.current_leg_arrival(t, 3, 0, 10) == t + timedelta(minutes=20)
    assert sc.current_leg_arrival(t, 3, 2, 10) == t
    assert sc.current_leg_arrival(None, 3, 0, 10) is None


def test_arrivals_add_the_boarding_time_between_legs():
    t = datetime(2026, 1, 1, 12, 0)
    assert sc.arrivals(t, [3, 2], 10, 30) == [t + timedelta(minutes=30), t + timedelta(minutes=80)]
    assert sc.arrivals(None, [3, 2], 10, 30) == [None, None]
    assert sc.arrivals(t, [], 10, 30) == []


# =============================================================================================== misc

def test_plain_length_strips_tags_and_outer_whitespace():
    assert sc.plain_length("<p>abc</p>") == 3
    assert sc.plain_length("  <b>a</b> <i>b</i>  ") == 3
    assert sc.plain_length("<img src='x'>") == 0
    assert sc.plain_length(None) == 0
    assert sc.plain_length("x" * 800) == 800


def test_clamp():
    assert sc.clamp(5, (1, 3)) == 3 and sc.clamp(-5, (1, 3)) == 1 and sc.clamp(2, (1, 3)) == 2


def test_captain_role_constant():
    assert sc.CAPTAIN_ROLE == "captain"
