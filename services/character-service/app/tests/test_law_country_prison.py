"""FEAT-202 (developer smoke tests): the country prison next to the region guard station.

World (on top of tests.law_world): country 1 «Мидденгерд» = regions 10 Ост (station 102 «Темница»), 11 Пашни (no
station), 12 Холмы. Prison district 500 «Казематы» @12 with a nested sub-district 501 «Двор»; locations 510 (entrance,
sort 2), 511 (sort 1) @500, 512 @501, 513 hanging off 512 by ``parent_id`` (no district). Outside: 103 «Тракт».
The full QA matrix lives in the QA task's tests.
"""

import logging
from datetime import timedelta
from decimal import Decimal

import pytest

import law_core as lc
import law_crud
import law_facility
from tests.law_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, INTERNAL, L_JAIL, L_POST, L_ROAD, R_OST, R_PASHNI, USER_ALPHA, USER_BETA, BANKER_MARKET,
    FixedRng, api, as_user, char_row, exec_, jail_character, law_payloads, law_world, make_encounter, now, q,
    rep_world, rid, rows, set_gold, set_wanted,
)

D_PRISON, D_YARD = 500, 501
L_CELL, L_CELL2, L_YARD, L_CELLAR = 510, 511, 512, 513
R_HOLMY = 12
VILLAIN, OFFENDER = 650, 150


@pytest.fixture
def prison(law_world):
    exec_(law_world, "INSERT INTO Districts (id, name, region_id, parent_district_id, entrance_location_id) "
                     "VALUES (500, 'Казематы', 12, NULL, 510), (501, 'Двор', 12, 500, NULL)")
    exec_(law_world, "INSERT INTO Locations (id, name, district_id, sort_order) VALUES (510, 'Камеры', 500, 2), "
                     "(511, 'Карцер', 500, 1), (512, 'Двор', 501, 0)")
    exec_(law_world, "INSERT INTO Locations (id, name, parent_id) VALUES (513, 'Подвал', 512)")
    exec_(law_world, "UPDATE Countries SET prison_district_id = 500 WHERE id = 1")
    return law_world


def _db(f):
    return f()


def _choose(api, enc_id, choice="surrender"):
    as_user(USER_ALPHA)
    return api.post(f"/characters/{ALPHA}/law/encounter/{enc_id}/choice",
                    json={"choice": choice, "request_id": rid()})


def _jail_alpha(api, f, value=VILLAIN):
    set_wanted(f, ALPHA, R_OST, value)
    enc_id = make_encounter(f, location_id=L_POST)
    resp = _choose(api, enc_id)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _move(api, dest, cid=ALPHA):
    return api.put(f"/characters/internal/{cid}/update_location", json={"new_location_id": dest}, headers=INTERNAL)


# ============================================================================================ pure


def test_pick_facility_matrix():
    levels = lc.DEFAULT_LEVELS
    assert lc.pick_facility("villain", "villain", levels, True, True) == "country"
    assert lc.pick_facility("enemy", "villain", levels, True, False) == "station"
    assert lc.pick_facility("offender", "villain", levels, True, True) == "station"
    assert lc.pick_facility("offender", "villain", levels, False, True) == "country"
    assert lc.pick_facility("offender", "villain", levels, False, False) is None
    assert lc.pick_facility("bogus", "villain", levels, True, True) == "station"
    assert lc.country_escape_chance(Decimal("50"), Decimal("0.5")) == Decimal("25.00")
    assert lc.facility_title("country", None, "x") == "Тюрьма страны «—»"
    assert lc.validate(lc.LawSettings(country_prison_min_level="nope"), lc.DEFAULT_LEVELS)
    assert lc.validate(lc.LawSettings(country_escape_multiplier=Decimal("1.1")), lc.DEFAULT_LEVELS)
    assert lc.validate(lc.LawSettings(country_escape_cooldown_hours=0), lc.DEFAULT_LEVELS)


# ============================================================================================ resolver


def test_subtree_and_cell(prison):
    db = _db(prison)
    try:
        assert law_facility.prison_location_ids(db, D_PRISON) == [L_CELL2, L_CELL, L_YARD, L_CELLAR]
        target = law_facility.country_prison(db, 1)
        assert (target.facility, target.location_id, target.district_id, target.region_id) == \
            ("country", L_CELL, D_PRISON, R_HOLMY)
        assert target.name == "Тюрьма страны «Мидденгерд»"
        exec_(prison, "UPDATE Districts SET entrance_location_id = 103 WHERE id = 500")   # outside -> first
        assert law_facility.country_prison(db, 1).location_id == L_CELL2
        exec_(prison, "UPDATE Districts SET region_id = 20 WHERE id = 500")              # another country
        assert law_facility.country_prison(db, 1) is None
    finally:
        db.close()


def test_resolve_jail_fallbacks(prison):
    db = _db(prison)
    try:
        assert law_facility.resolve_jail(db, R_OST, "villain").facility == "country"
        assert law_facility.resolve_jail(db, R_OST, "offender").location_id == L_JAIL
        assert law_facility.resolve_jail(db, R_PASHNI, "offender").facility == "country"   # no station
        exec_(prison, "UPDATE Countries SET prison_district_id = NULL")
        assert law_facility.resolve_jail(db, R_OST, "enemy").facility == "station"
        assert law_facility.resolve_jail(db, R_PASHNI, "enemy") is None
    finally:
        db.close()


def test_missing_prison_column_warns(law_world, caplog):
    db = _db(law_world)
    try:
        db.execute(law_crud.text("ALTER TABLE Countries DROP COLUMN prison_district_id"))
        with caplog.at_level(logging.WARNING, logger="character-service.law_facility"):
            assert law_facility.country_prison(db, 1) is None
        assert "prison_district_id is missing" in caplog.text
    finally:
        db.close()


# ============================================================================================ flows


def test_heavy_surrender_goes_to_country_prison(api, prison, stub_law_notify_send):
    data = _jail_alpha(api, prison)
    jail = data["jail"]
    assert jail["facility"] == "country" and jail["facility_name"] == "Тюрьма страны «Мидденгерд»"
    assert jail["bail_available"] is False and jail["bail_price"] is None
    assert jail["district_id"] == D_PRISON and jail["district_name"] == "Казематы"
    assert jail["allowed_location_ids"] == [L_CELL2, L_CELL, L_YARD, L_CELLAR]
    row = char_row(prison, ALPHA)
    assert row.current_location_id == L_CELL and row.jail_district_id == D_PRISON
    term = rows(prison, "SELECT facility, country_id, district_id, region_id, bail_price FROM law_jail_terms")[0]
    assert tuple(term) == ("country", 1, D_PRISON, R_OST, 0)
    msgs = [p["message"] for p in law_payloads(stub_law_notify_send) if p["target_value"] == USER_ALPHA]
    assert any("тюрьму страны «Мидденгерд»" in m for m in msgs)

    # movement inside the subtree only
    assert _move(api, L_CELLAR).status_code == 200
    assert char_row(prison, ALPHA).current_location_id == L_CELLAR
    assert _move(api, L_ROAD).status_code == 409

    # no bail; hidden from the banker list
    as_user(USER_ALPHA)
    resp = api.post(f"/characters/{ALPHA}/law/jail/bail", json={"request_id": rid()})
    assert resp.status_code == 409 and resp.json()["detail"] == "Из тюрьмы страны нельзя выйти под залог"
    set_gold(prison, BETA, 10_000)
    as_user(USER_BETA)
    resp = api.post("/characters/law/bail", json={"payer_character_id": BETA, "banker_npc_id": BANKER_MARKET,
                                                  "prisoner_character_id": ALPHA, "request_id": rid()})
    assert resp.status_code == 409 and resp.json()["detail"] == "Из тюрьмы страны нельзя выйти под залог"
    assert q(prison, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'law_bail'") == 0
    assert api.get("/characters/law/prisoners").json()["total"] == 0


def test_country_escape_halved_with_long_cooldown(api, prison, monkeypatch):
    _jail_alpha(api, prison)
    monkeypatch.setattr(law_crud, "rng", lambda: FixedRng(0.99))
    as_user(USER_ALPHA)
    resp = api.post(f"/characters/{ALPHA}/law/jail/escape", json={"request_id": rid()})
    assert resp.status_code == 200 and resp.json()["success"] is False
    chance = q(prison, "SELECT chance_pct FROM law_log WHERE action = 'escape_fail'")
    assert Decimal(str(chance)) == Decimal("2.50")                       # 5 % station × 0.5
    next_at = q(prison, "SELECT next_escape_at FROM law_jail_terms")
    next_at = law_crud._dt(next_at)
    assert timedelta(hours=11, minutes=59) < next_at - now() <= timedelta(hours=12, minutes=1)


def test_staff_release_clears_snapshot(api, prison):
    _jail_alpha(api, prison)
    db = _db(prison)
    try:
        law_crud.staff_release(db, ALPHA, reason="x", request_id=rid(), actor_user_id=1)
        db.commit()
    finally:
        db.close()
    assert char_row(prison, ALPHA).jail_district_id is None


def test_light_offender_goes_to_station_and_cannot_move(api, prison):
    data = _jail_alpha(api, prison, OFFENDER)
    assert data["jail"]["facility"] == "station" and data["jail"]["bail_available"] is True
    assert data["jail"]["facility_name"] == "Отделение стражи края «Ост»"
    assert data["jail"]["allowed_location_ids"] == [L_JAIL]
    assert char_row(prison, ALPHA).jail_district_id is None
    assert _move(api, L_CELL).status_code == 409
