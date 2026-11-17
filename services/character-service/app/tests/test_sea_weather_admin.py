"""FEAT-214 QA (T10): the storm / raid admin API (features/FEAT-214 §3.11).

* A7 settings: the 18 new numbers (defaults, save, omitted = kept, ranges → 422, max < min → 400 in Russian);
* ``GET /admin/sea/weather``: season + multiplier, seas (regions with sea zones, config or defaults), active storms
  with their zones, raids (active first, then the last 20 finished);
* ``PUT /admin/sea/seas/{region_id}``, ``POST /admin/sea/storms`` (radius of the sea, one-per-sea bypass, not a sea
  zone → 400), ``DELETE /admin/sea/storms/{id}`` (204, unknown / ended → 404);
* 503 without the 053 tables; RBAC (401 / 403 / the exact permission); security cases.
"""

from datetime import timedelta

import pytest

import sea_admin
import sea_weather
from tests.sea_storm_world import (  # noqa: F401  (fixtures)
    MONSTER_TPL, add_monster, add_storm, set_params, set_sea, storm, storm_row, storm_zone_ids,
)
from tests.sea_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, DECK, LAND, P_A, USER_ALPHA, Z1, Z2, Z3, Z4, Z5, api, as_user, client, exec_, law_world, now, q,
    rep_world, rows, sea,
)

SETTINGS = "/characters/admin/sea/settings"
WEATHER = "/characters/admin/sea/weather"
SEAS = "/characters/admin/sea/seas/{}"
STORMS = "/characters/admin/sea/storms"
BASE = {"sailor_post_min_chars": 800, "stowaway_base_pct": 60, "stowaway_wanted_points": 50, "path_max_zones": 200}
DEFAULTS = {
    "storm_min_minutes": 60, "storm_max_minutes": 180, "storm_move_pct": 30.0, "storm_max_moves": 2,
    "storm_slow_mult": 2.0, "storm_drift_pct": 15.0, "storm_hp_pct": 10.0, "storm_stamina_pct": 20.0,
    "storm_postpone_minutes": 15, "storm_postpone_max_minutes": 240, "storm_sailor_relief_pct": 50.0,
    "season_mult_spring": 1.0, "season_mult_summer": 0.5, "season_mult_autumn": 1.5, "season_mult_winter": 2.0,
    "raid_chance_mult": 1.0, "raid_hold_max_minutes": 120, "raid_repelled_delay_minutes": 5,
}
ALL = ["locations:read", "locations:update"]


@pytest.fixture
def admin(client, storm):
    set_params(storm, storm_drift_pct=15.0)          # the storm fixture zeroes it; back to the migration default
    as_user(1, "admin", ALL)
    return client


# =============================================================================================== RBAC

ENDPOINTS = [
    ("get", WEATHER, None, "locations:read"),
    ("put", SEAS.format(30), {"is_enabled": True, "chance_per_hour_pct": 5, "radius": 1}, "locations:update"),
    ("post", STORMS, {"zone_id": Z2, "minutes": 30}, "locations:update"),
    ("put", SETTINGS, {**BASE, "storm_min_minutes": 30}, "locations:update"),
]


def _call(c, method, path, body):
    return getattr(c, method)(path, json=body) if body is not None else getattr(c, method)(path)


@pytest.mark.parametrize("method, path, body, perm", ENDPOINTS)
def test_needs_a_token(client, storm, method, path, body, perm):
    assert _call(client, method, path, body).status_code == 401


@pytest.mark.parametrize("method, path, body, perm", ENDPOINTS)
def test_needs_the_exact_permission(client, storm, method, path, body, perm):
    as_user(2, "moderator", [p for p in ALL + ["locations:create", "locations:delete"] if p != perm])
    assert _call(client, method, path, body).status_code == 403
    assert q(storm, "SELECT COUNT(*) FROM sea_storms") == 0
    assert q(storm, "SELECT COUNT(*) FROM sea_storm_seas") == 0
    assert q(storm, "SELECT storm_min_minutes FROM sea_settings WHERE id = 1") == 60


@pytest.mark.parametrize("method, path, body, perm", ENDPOINTS)
def test_the_permission_is_enough(client, storm, method, path, body, perm):
    as_user(3, "editor", [perm])
    r = _call(client, method, path, body)
    assert r.status_code in (200, 201), r.text


def test_delete_storm_rbac(client, storm):
    sid = add_storm(storm, [Z2], minutes=60)
    assert client.delete(f"{STORMS}/{sid}").status_code == 401
    as_user(2, "moderator", ["locations:read"])
    assert client.delete(f"{STORMS}/{sid}").status_code == 403
    as_user(USER_ALPHA)
    assert client.delete(f"{STORMS}/{sid}").status_code == 403
    assert storm_row(storm, sid).status == "active"


def test_plain_user_cannot_read_the_weather(client, storm):
    as_user(USER_ALPHA)
    assert client.get(WEATHER).status_code == 403


# =============================================================================================== settings

def test_settings_have_the_storm_defaults(admin):
    body = admin.get(SETTINGS).json()
    assert {k: body[k] for k in DEFAULTS} == DEFAULTS


def test_settings_save_every_storm_number(admin, storm):
    new = {"storm_min_minutes": 30, "storm_max_minutes": 600, "storm_move_pct": 12.5, "storm_max_moves": 4,
           "storm_slow_mult": 3.25, "storm_drift_pct": 40.0, "storm_hp_pct": 7.5, "storm_stamina_pct": 0.0,
           "storm_postpone_minutes": 30, "storm_postpone_max_minutes": 0, "storm_sailor_relief_pct": 100.0,
           "season_mult_spring": 0.0, "season_mult_summer": 10.0, "season_mult_autumn": 1.25,
           "season_mult_winter": 3.0, "raid_chance_mult": 0.0, "raid_hold_max_minutes": 1440,
           "raid_repelled_delay_minutes": 120}
    r = admin.put(SETTINGS, json={**BASE, **new})
    assert r.status_code == 200, r.text
    assert {k: r.json()[k] for k in new} == new
    assert {k: admin.get(SETTINGS).json()[k] for k in new} == new
    import sea_crud
    db = storm()
    try:
        p = sea_crud.load_params(db)
    finally:
        db.close()
    assert float(p.storm_slow_mult) == 3.25 and p.raid_hold_max_minutes == 1440


def test_omitted_storm_numbers_are_kept(admin):
    admin.put(SETTINGS, json={**BASE, "storm_hp_pct": 33, "raid_chance_mult": 2.5})
    r = admin.put(SETTINGS, json={**BASE, "storm_hp_pct": None})
    assert r.status_code == 200
    assert (r.json()["storm_hp_pct"], r.json()["raid_chance_mult"]) == (33.0, 2.5)


@pytest.mark.parametrize("body", [
    {"storm_min_minutes": 200, "storm_max_minutes": 100},
    {"storm_min_minutes": 200},                                   # vs the saved max 180
    {"storm_max_minutes": 59},                                    # vs the saved min 60
])
def test_storm_max_below_min_is_400(admin, body):
    r = admin.put(SETTINGS, json={**BASE, **body})
    assert (r.status_code, r.json()["detail"]) == (400, "Максимальная длительность шторма меньше минимальной")
    assert admin.get(SETTINGS).json()["storm_min_minutes"] == 60


def test_storm_min_equal_max_is_fine(admin):
    assert admin.put(SETTINGS, json={**BASE, "storm_min_minutes": 90, "storm_max_minutes": 90}).status_code == 200


@pytest.mark.parametrize("field, value", [
    ("storm_min_minutes", 9), ("storm_max_minutes", 1441), ("storm_move_pct", -1), ("storm_move_pct", 100.5),
    ("storm_max_moves", 11), ("storm_slow_mult", 0.99), ("storm_slow_mult", 10.5), ("storm_drift_pct", 101),
    ("storm_hp_pct", -0.1), ("storm_stamina_pct", 101), ("storm_postpone_minutes", 0),
    ("storm_postpone_minutes", 241), ("storm_postpone_max_minutes", 1441), ("storm_sailor_relief_pct", 100.01),
    ("season_mult_spring", -1), ("season_mult_winter", 11), ("raid_chance_mult", 10.01),
    ("raid_hold_max_minutes", -1), ("raid_repelled_delay_minutes", 121), ("storm_max_moves", "много"),
])
def test_storm_settings_ranges(admin, field, value):
    r = admin.put(SETTINGS, json={**BASE, field: value})
    assert r.status_code == 422, r.text
    assert {k: admin.get(SETTINGS).json()[k] for k in DEFAULTS} == DEFAULTS


# =============================================================================================== weather view

def test_weather_view_seas_season_and_storms(admin, storm):
    storm.season = "winter"
    set_sea(storm, 30, enabled=True, pct=12.5, radius=2)
    t = now()
    sid = add_storm(storm, [Z1, Z2, Z5], center=Z1, start=t, minutes=60, source="auto")
    add_storm(storm, [Z3], start=t, minutes=60, status="ended")
    r = admin.get(WEATHER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["season"], body["season_mult"]) == ("winter", 2.0)
    assert body["seas"] == [
        {"region_id": 30, "name": "Море Эйдонэи", "zones_count": 4, "is_enabled": True, "chance_per_hour_pct": 12.5,
         "radius": 2},
        {"region_id": 31, "name": "Внутреннее море", "zones_count": 1, "is_enabled": False,
         "chance_per_hour_pct": 0.0, "radius": sea_weather.DEFAULT_RADIUS},
    ]
    (s,) = body["storms"]
    assert (s["id"], s["region_id"], s["sea_name"], s["source"], s["moves"]) == (sid, 30, "Море Эйдонэи", "auto", 0)
    assert s["center_zone"] == {"id": Z1, "name": "Пролив Ветров"}
    assert [z["id"] for z in s["zones"]] == [Z1, Z2, Z5]
    assert body["raids"] == []


def test_weather_view_without_a_calendar(admin, storm):
    body = admin.get(WEATHER).json()
    assert (body["season"], body["season_mult"]) == (None, 1.0)


def _raid_row(f, status, n, battle_id=None, players=(ALPHA,), placed=None):
    import models
    db = f()
    try:
        extra = {"placed_ids": list(placed)} if placed is not None else {}
        r = models.SeaRaid(ship_id=f.ship_id, attack_key=f"k{n}", group_no=0, deck_location_id=DECK, zone_id=Z2,
                           mob_template_id=MONSTER_TPL, monster_name="Кракен", player_ids=list(players),
                           battle_id=battle_id, status=status, mobs_despawned=True,
                           created_at=now() + timedelta(seconds=n), **extra)
        db.add(r)
        db.commit()
        return int(r.id)
    finally:
        db.close()


def test_weather_view_raids_active_first_then_the_last_twenty_final(admin, storm):
    final_ids = [_raid_row(storm, "won", n) for n in range(25)]
    active = _raid_row(storm, "fighting", 100, battle_id=901, players=(ALPHA, BETA), placed=(BETA,))
    starting = _raid_row(storm, "starting", 101, players=(ALPHA, BETA))
    raids_out = admin.get(WEATHER).json()["raids"]
    assert [r["id"] for r in raids_out] == [starting, active] + final_ids[::-1][:20]
    by_id = {r["id"]: r for r in raids_out}
    assert by_id[active]["players"] == [{"id": BETA, "name": "Бета"}]            # placed players when known
    assert [p["id"] for p in by_id[starting]["players"]] == [ALPHA, BETA]
    assert by_id[active]["ship_name"] == "Морская дева" and by_id[active]["battle_id"] == 901
    assert by_id[active]["zone"] == {"id": Z2, "name": "Северный залив"}
    assert by_id[starting]["battle_id"] is None


def test_weather_view_of_a_deleted_ship_has_no_ship_name(admin, storm):
    _raid_row(storm, "lost", 1)
    exec_(storm, "DELETE FROM sea_ships")
    (r,) = admin.get(WEATHER).json()["raids"]
    assert r["ship_name"] is None


# =============================================================================================== seas

def test_put_sea_creates_then_updates_the_row(admin, storm):
    r = admin.put(SEAS.format(30), json={"is_enabled": True, "chance_per_hour_pct": 7.25, "radius": 3})
    assert r.status_code == 200, r.text
    assert r.json() == {"region_id": 30, "name": "Море Эйдонэи", "zones_count": 4, "is_enabled": True,
                        "chance_per_hour_pct": 7.25, "radius": 3}
    r = admin.put(SEAS.format(30), json={"is_enabled": False, "chance_per_hour_pct": 0, "radius": 0})
    assert (r.json()["is_enabled"], r.json()["radius"]) == (False, 0)
    assert q(storm, "SELECT COUNT(*) FROM sea_storm_seas") == 1


@pytest.mark.parametrize("region_id", [10, 20, 99999])
def test_put_sea_without_sea_zones_is_404(admin, storm, region_id):
    r = admin.put(SEAS.format(region_id), json={"is_enabled": True, "chance_per_hour_pct": 5, "radius": 1})
    assert (r.status_code, r.json()["detail"]) == (404, "Море не найдено")
    assert q(storm, "SELECT COUNT(*) FROM sea_storm_seas") == 0


@pytest.mark.parametrize("path, body", [
    (SEAS.format(30), {"is_enabled": True, "chance_per_hour_pct": 100.5, "radius": 1}),
    (SEAS.format(30), {"is_enabled": True, "chance_per_hour_pct": -1, "radius": 1}),
    (SEAS.format(30), {"is_enabled": True, "chance_per_hour_pct": 5, "radius": 6}),
    (SEAS.format(30), {"is_enabled": True, "chance_per_hour_pct": 5, "radius": -1}),
    (SEAS.format(30), {"chance_per_hour_pct": 5, "radius": 1}),
    (SEAS.format(0), {"is_enabled": True, "chance_per_hour_pct": 5, "radius": 1}),
    (SEAS.format("30;DROP TABLE sea_storm_seas"), {"is_enabled": True, "chance_per_hour_pct": 5, "radius": 1}),
])
def test_put_sea_validation(admin, storm, path, body):
    assert admin.put(path, json=body).status_code == 422
    assert q(storm, "SELECT COUNT(*) FROM sea_storm_seas") == 0


# =============================================================================================== storms

def test_post_storm_covers_the_seas_radius(admin, storm):
    set_sea(storm, 30, enabled=False, radius=1)
    t0 = now()
    r = admin.post(STORMS, json={"zone_id": Z2, "minutes": 45})
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["source"], body["region_id"], body["sea_name"], body["moves"]) == ("admin", 30, "Море Эйдонэи", 0)
    assert body["center_zone"] == {"id": Z2, "name": "Северный залив"}
    assert [z["id"] for z in body["zones"]] == [Z1, Z2, Z3]
    s = storm_row(storm, body["id"])
    assert s.status == "active" and timedelta(minutes=44) <= s.ends_at - t0 <= timedelta(minutes=46)


def test_post_storm_without_a_sea_config_uses_the_default_radius(admin, storm):
    body = admin.post(STORMS, json={"zone_id": Z4, "minutes": 10}).json()
    assert [z["id"] for z in body["zones"]] == [Z4] and body["region_id"] == 31


def test_post_storm_bypasses_one_storm_per_sea(admin, storm):
    add_storm(storm, [Z1], region=30, source="auto", minutes=60)
    assert admin.post(STORMS, json={"zone_id": Z3, "minutes": 30}).status_code == 201
    assert q(storm, "SELECT COUNT(*) FROM sea_storms WHERE status = 'active' AND region_id = 30") == 2


def test_admin_storm_is_seen_by_the_lookups(admin, storm):
    body = admin.post(STORMS, json={"zone_id": Z2, "minutes": 30}).json()
    db = storm()
    try:
        assert sea_weather.storm_at(db, Z3, now()).storm_id == body["id"]
    finally:
        db.close()


@pytest.mark.parametrize("zone_id", [P_A, DECK, LAND, 99999])
def test_post_storm_outside_the_sea_is_400(admin, storm, zone_id):
    r = admin.post(STORMS, json={"zone_id": zone_id, "minutes": 30})
    assert (r.status_code, r.json()["detail"]) == (400, "Это не морская зона")
    assert q(storm, "SELECT COUNT(*) FROM sea_storms") == 0


@pytest.mark.parametrize("body", [
    {"zone_id": Z2, "minutes": 9}, {"zone_id": Z2, "minutes": 1441}, {"zone_id": 0, "minutes": 30},
    {"zone_id": Z2}, {"minutes": 30}, {"zone_id": "502 OR 1=1", "minutes": 30},
    {"zone_id": "<script>", "minutes": 30},
])
def test_post_storm_validation(admin, storm, body):
    assert admin.post(STORMS, json=body).status_code == 422
    assert q(storm, "SELECT COUNT(*) FROM sea_storms") == 0


def test_delete_storm_ends_it_once(admin, storm):
    sid = add_storm(storm, [Z2], minutes=60)
    r = admin.delete(f"{STORMS}/{sid}")
    assert r.status_code == 204 and r.content == b""
    s = storm_row(storm, sid)
    assert s.status == "ended" and s.ended_at is not None
    again = admin.delete(f"{STORMS}/{sid}")
    assert (again.status_code, again.json()["detail"]) == (404, "Шторм не найден или уже закончился")
    assert admin.get(WEATHER).json()["storms"] == []


def test_delete_unknown_storm_is_404(admin, storm):
    assert admin.delete(f"{STORMS}/424242").status_code == 404
    assert admin.delete(f"{STORMS}/0").status_code == 422
    assert admin.delete(f"{STORMS}/1%20OR%201=1").status_code == 422


# =============================================================================================== missing tables

@pytest.mark.parametrize("method, path, body", [
    ("get", WEATHER, None),
    ("put", SEAS.format(30), {"is_enabled": True, "chance_per_hour_pct": 5, "radius": 1}),
    ("post", STORMS, {"zone_id": Z2, "minutes": 30}),
    ("delete", f"{STORMS}/1", None),
])
def test_without_the_053_tables_it_is_503(admin, storm, method, path, body):
    exec_(storm, "DROP TABLE sea_storms")
    r = _call(admin, method, path, body)
    assert (r.status_code, r.json()["detail"]) == (503, sea_admin.MSG_WEATHER_UNAVAILABLE)


def test_weather_db_error_is_a_generic_500(admin, storm, monkeypatch):
    from sqlalchemy.exc import OperationalError

    def boom(*a, **k):
        raise OperationalError("SELECT secret", {}, Exception("password=hunter2"))

    monkeypatch.setattr(sea_admin, "weather_out", boom)
    r = admin.get(WEATHER)
    assert r.status_code == 500 and "hunter2" not in r.text and r.json()["detail"] == sea_admin.MSG_LOAD_FAILED
