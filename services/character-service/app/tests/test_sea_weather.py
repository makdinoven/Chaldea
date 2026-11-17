"""FEAT-214 QA (T10): the sea weather step and the storm damage client (features/FEAT-214 §3.5, §3.7).

* spawn: enabled seas only, chance per hour × season multiplier with the elapsed time since the last step (clamped to
  one hour; first step = one minute), one storm per sea, centre = a zone of the sea, zones by the sea's radius
  (clamped), duration within [min, max]; ``weather_last_run_at`` advanced;
* due storms move (chance, max moves, a neighbour in the same sea, zones recomputed, new end) or end;
* lookups ``storm_at`` / ``storms_for`` (active and not expired only, the later end wins), tolerance of missing tables;
* ``apply_storm_damage``: payload, batches of 200, nothing to do, transport / non-200 failures;
* ``sea_pass.run_pass`` runs the weather once per pass and a failing step never stops the ships.
"""

import logging
from datetime import timedelta

import pytest

import sea_crud
import sea_pass
import sea_weather
from tests.sea_storm_world import (  # noqa: F401  (fixtures)
    ScriptedRng, add_storm, http_error, set_params, set_sea, storm, storm_row, storm_zone_ids,
)
from tests.sea_world import (  # noqa: F401  (fixtures)
    Z1, Z2, Z3, Z4, Z5, api, exec_, law_world, now, q, rep_world, rows, sea, ship,
)


def _weather(f, when):
    db = f()
    try:
        return sea_weather.run_weather(db, when)
    finally:
        db.close()


def _active(f, region=None):
    sql = "SELECT id FROM sea_storms WHERE status = 'active'"
    if region is not None:
        sql += " AND region_id = :r"
    return [int(r[0]) for r in rows(f, sql + " ORDER BY id", r=region)]


def _last_run(f, when):
    exec_(f, "UPDATE sea_settings SET weather_last_run_at = :t WHERE id = 1", t=when)


# =============================================================================================== spawn

def test_enabled_sea_spawns_a_storm_with_its_radius_and_duration(storm):
    set_sea(storm, 30, pct=100, radius=1)
    storm.rng.pick = 0
    t = now()
    stats = _weather(storm, t)
    assert stats == {"ended": 0, "moved": 0, "spawned": 1}
    (sid,) = _active(storm)
    s = storm_row(storm, sid)
    assert (s.region_id, s.center_zone_id, s.source, s.moves, s.status) == (30, Z1, "auto", 0, "active")
    assert s.started_at == t and s.ends_at == t + timedelta(minutes=60)        # randint → the minimum
    assert storm_zone_ids(storm, sid) == [Z1, Z2, Z5]
    assert q(storm, "SELECT weather_last_run_at FROM sea_settings WHERE id = 1") is not None


def test_duration_uses_the_maximum_end_of_the_range(storm):
    set_sea(storm, 30, pct=100)
    set_params(storm, storm_min_minutes=30, storm_max_minutes=90)
    storm.rng.high = True
    t = now()
    _weather(storm, t)
    assert storm_row(storm, _active(storm)[0]).ends_at == t + timedelta(minutes=90)


def test_duration_max_below_min_is_raised_to_min(storm):
    set_sea(storm, 30, pct=100)
    set_params(storm, storm_min_minutes=120, storm_max_minutes=60)
    storm.rng.high = True
    t = now()
    _weather(storm, t)
    assert storm_row(storm, _active(storm)[0]).ends_at == t + timedelta(minutes=120)


def test_centre_is_a_random_zone_of_that_sea(storm):
    set_sea(storm, 30, pct=100, radius=0)
    storm.rng.pick = 3                                   # zones of sea 30 ascending: 501, 502, 503, 505
    _weather(storm, now())
    (sid,) = _active(storm)
    assert storm_row(storm, sid).center_zone_id == Z5 and storm_zone_ids(storm, sid) == [Z5]


@pytest.mark.parametrize("radius, zones", [(-3, [Z3]), (9, [Z1, Z2, Z3, Z5])])
def test_radius_is_clamped(storm, radius, zones):
    set_sea(storm, 30, pct=100, radius=radius)          # out of range in the DB (validated by the admin API)
    storm.rng.pick = 2
    _weather(storm, now())
    assert storm_zone_ids(storm, _active(storm)[0]) == zones


def test_radius_never_crosses_into_another_sea(storm):
    set_sea(storm, 31, pct=100, radius=5)
    _weather(storm, now())
    (sid,) = _active(storm, 31)
    assert storm_zone_ids(storm, sid) == [Z4]


def test_disabled_or_unconfigured_sea_never_spawns(storm):
    set_sea(storm, 30, enabled=False, pct=100)
    assert _weather(storm, now())["spawned"] == 0 and _active(storm) == []


def test_zero_chance_never_spawns(storm):
    set_sea(storm, 30, pct=0)
    storm.rng.values = [0.0]
    assert _weather(storm, now())["spawned"] == 0


@pytest.mark.parametrize("season, roll, spawned", [
    (None, 0.49, 1), (None, 0.51, 0),
    ("winter", 0.99, 1),                                 # 50 % × 2 = 100 %
    ("summer", 0.24, 1), ("summer", 0.26, 0),            # 50 % × 0.5 = 25 %
    ("autumn", 0.74, 1), ("autumn", 0.76, 0),            # 75 %
])
def test_season_multiplies_the_chance(storm, season, roll, spawned):
    set_sea(storm, 30, pct=50)
    t = now()
    _last_run(storm, t - timedelta(minutes=60))
    storm.season = season
    storm.rng.values = [roll]
    assert _weather(storm, t)["spawned"] == spawned


def test_season_multiplier_follows_the_settings(storm):
    set_sea(storm, 30, pct=50)
    set_params(storm, season_mult_winter=0.0)
    storm.season = "winter"
    t = now()
    _last_run(storm, t - timedelta(minutes=60))
    storm.rng.values = [0.0]
    assert _weather(storm, t)["spawned"] == 0


def test_elapsed_time_is_clamped_to_one_hour(storm):
    set_sea(storm, 30, pct=50)
    t = now()
    _last_run(storm, t - timedelta(hours=10))            # unclamped: 1 − 0.5^10 ≈ 99.9 %
    storm.rng.values = [0.6]
    assert _weather(storm, t)["spawned"] == 0


def test_first_step_counts_one_minute(storm):
    set_sea(storm, 30, pct=60)                           # one minute of 60 %/h ≈ 1.5 %
    storm.rng.values = [0.02]
    assert _weather(storm, now())["spawned"] == 0
    storm.rng.values = [0.01]
    t = now() + timedelta(seconds=30)
    _last_run(storm, None)
    assert _weather(storm, t)["spawned"] == 1


def test_one_storm_per_sea(storm):
    set_sea(storm, 30, pct=100)
    set_sea(storm, 31, pct=100)
    add_storm(storm, [Z2], region=30, source="admin")
    stats = _weather(storm, now())
    assert stats["spawned"] == 1
    assert len(_active(storm, 30)) == 1 and len(_active(storm, 31)) == 1
    assert _weather(storm, now() + timedelta(minutes=1))["spawned"] == 0


def test_an_ended_storm_frees_the_sea(storm):
    set_sea(storm, 30, pct=100)
    add_storm(storm, [Z2], region=30, status="ended")
    assert _weather(storm, now())["spawned"] == 1


# =============================================================================================== move / end

def test_due_storm_moves_to_a_neighbour_and_recomputes_its_zones(storm):
    set_params(storm, storm_move_pct=100.0)
    t = now()
    sid = add_storm(storm, [Z1, Z2, Z5], center=Z1, start=t - timedelta(hours=2), minutes=60, source="auto")
    storm.rng.values, storm.rng.pick = [0.5], 0
    assert _weather(storm, t)["moved"] == 1
    s = storm_row(storm, sid)
    assert (s.status, s.center_zone_id, s.moves) == ("active", Z2, 1)
    assert s.ends_at == t + timedelta(minutes=60)
    assert storm_zone_ids(storm, sid) == [Z1, Z2, Z3]


def test_move_uses_the_seas_configured_radius(storm):
    set_params(storm, storm_move_pct=100.0)
    set_sea(storm, 30, enabled=False, radius=0)
    t = now()
    sid = add_storm(storm, [Z1], center=Z1, start=t - timedelta(hours=2), minutes=60)
    storm.rng.pick = 1
    _weather(storm, t)
    assert storm_row(storm, sid).center_zone_id == Z5 and storm_zone_ids(storm, sid) == [Z5]


@pytest.mark.parametrize("move_pct, moves, max_moves", [(0.0, 0, 2), (100.0, 2, 2), (100.0, 0, 0)])
def test_due_storm_ends_without_a_move(storm, move_pct, moves, max_moves):
    set_params(storm, storm_move_pct=move_pct, storm_max_moves=max_moves)
    t = now()
    sid = add_storm(storm, [Z1, Z2], center=Z1, start=t - timedelta(hours=2), minutes=60, moves=moves)
    assert _weather(storm, t)["ended"] == 1
    s = storm_row(storm, sid)
    assert (s.status, s.ended_at, s.moves) == ("ended", t, moves)
    assert storm_zone_ids(storm, sid) == [Z1, Z2]                       # history kept


def test_storm_without_a_neighbour_in_its_sea_ends(storm):
    set_params(storm, storm_move_pct=100.0)
    t = now()
    sid = add_storm(storm, [Z4], center=Z4, region=31, start=t - timedelta(hours=2), minutes=60)
    _weather(storm, t)
    assert storm_row(storm, sid).status == "ended"


def test_storm_not_due_is_untouched(storm):
    set_params(storm, storm_move_pct=100.0)
    t = now()
    sid = add_storm(storm, [Z1], start=t, minutes=30)
    assert _weather(storm, t + timedelta(minutes=29)) == {"ended": 0, "moved": 0, "spawned": 0}
    assert storm_row(storm, sid).status == "active"


def test_season_change_never_touches_a_running_storm(storm):
    t = now()
    sid = add_storm(storm, [Z1], start=t, minutes=30)
    storm.season = "summer"
    _weather(storm, t + timedelta(minutes=10))
    s = storm_row(storm, sid)
    assert s.ends_at == t + timedelta(minutes=30) and s.status == "active"


# =============================================================================================== lookups

def test_storm_at_sees_active_unexpired_storms_only(storm):
    t = now()
    add_storm(storm, [Z1], start=t - timedelta(hours=2), minutes=60)             # expired, not yet ended by a step
    add_storm(storm, [Z2], start=t, minutes=60, status="ended")
    sid = add_storm(storm, [Z3], start=t, minutes=60)
    db = storm()
    try:
        assert sea_weather.storm_at(db, Z1, t) is None
        assert sea_weather.storm_at(db, Z2, t) is None
        info = sea_weather.storm_at(db, Z3, t)
        assert (info.storm_id, info.zone_id, info.ends_at) == (sid, Z3, t + timedelta(minutes=60))
        assert sea_weather.storm_at(db, None, t) is None and sea_weather.storm_at(db, 0, t) is None
        assert sea_weather.storm_at(db, Z3, t + timedelta(minutes=60)) is None    # ends_at is exclusive
    finally:
        db.close()


def test_storms_for_the_later_end_wins(storm):
    t = now()
    add_storm(storm, [Z1, Z2], start=t, minutes=30)
    late = add_storm(storm, [Z2], start=t, minutes=90)
    db = storm()
    try:
        out = sea_weather.storms_for(db, [Z1, Z2, Z3, None], t)
    finally:
        db.close()
    assert set(out) == {Z1, Z2} and out[Z2].storm_id == late


def test_missing_tables_read_as_calm_and_skip_the_step(storm, monkeypatch, caplog):
    exec_(storm, "DROP TABLE sea_storm_zones")
    db = storm()
    try:
        assert sea_weather.storm_at(db, Z1, now()) is None
    finally:
        db.close()
    with caplog.at_level(logging.WARNING, logger="character-service.sea_weather"):
        assert _weather(storm, now()) is None
        assert _weather(storm, now()) is None
    assert len([r for r in caplog.records if "053" in r.getMessage()]) == 1


def test_failing_step_rolls_back_and_the_ships_still_sail(storm, monkeypatch):
    set_sea(storm, 30, pct=100)

    def boom(db):
        raise RuntimeError("graph down")

    monkeypatch.setattr(sea_crud, "zone_graph", boom)
    assert _weather(storm, now()) is None
    assert _active(storm) == []
    monkeypatch.undo()


def test_run_pass_runs_the_weather_once_and_reports_it(storm):
    set_sea(storm, 30, pct=100)
    stats = sea_pass.run_pass(storm, now=storm.t0 + timedelta(minutes=31), force=True)
    assert stats["storm_spawned"] == 1 and stats["departed"] in (0, 1)
    assert len(_active(storm)) == 1


def test_run_pass_survives_a_weather_crash(storm, monkeypatch):
    monkeypatch.setattr(sea_weather, "_run_weather", lambda db, when, params: 1 / 0)
    stats = sea_pass.run_pass(storm, now=storm.t0 + timedelta(minutes=31), force=True)
    assert stats["departed"] == 1 and "storm_spawned" not in stats


# =============================================================================================== damage client

def test_damage_payload_distinct_ids_floor_and_url(storm):
    applied = sea_weather.apply_storm_damage([3, 1, 3, 0, None, 2], 10, 20)
    ((url, payload),) = storm.cas.calls
    assert url.endswith("/internal/storm-damage")
    assert payload == {"items": [{"character_id": c, "health_pct": 10.0, "stamina_pct": 20.0} for c in (1, 2, 3)],
                       "min_health": 1}
    assert [a["character_id"] for a in applied] == [1, 2, 3]


def test_damage_percentages_are_clamped():
    assert sea_weather.damage_items([1], 150, -5) == [{"character_id": 1, "health_pct": 100.0, "stamina_pct": 0.0}]


def test_no_damage_means_no_call(storm):
    assert sea_weather.apply_storm_damage([1, 2], 0, 0) == []
    assert sea_weather.apply_storm_damage([], 10, 10) == []
    assert storm.cas.calls == []


def test_damage_is_sent_in_batches_of_200(storm):
    sea_weather.apply_storm_damage(range(1, 251), 10, 0)
    assert [len(p["items"]) for _u, p in storm.cas.calls] == [200, 50]


@pytest.mark.parametrize("kind", ["transport", "status"])
def test_damage_failure_is_none_without_retry(storm, kind):
    if kind == "transport":
        storm.cas.error = http_error()
    else:
        storm.cas.status = 500
    assert sea_weather.apply_storm_damage([1], 10, 10) is None
    assert len(storm.cas.calls) == 1


def test_http_post_sends_the_internal_token(monkeypatch):
    import crud
    import httpx
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, json=json, headers=headers, timeout=timeout)
        return "ok"

    monkeypatch.setattr(crud, "_internal_token_headers", lambda: {"X-Internal-Token": "t"})
    monkeypatch.setattr(httpx, "post", fake_post)
    assert sea_weather.http_post("http://cas/internal/storm-damage", {"items": []}) == "ok"
    assert sent["headers"] == {"X-Internal-Token": "t"} and sent["timeout"] == sea_weather.HTTP_TIMEOUT_SECONDS
