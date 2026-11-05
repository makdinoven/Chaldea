"""FEAT-202 QA (task 5): the country prison next to the region guard station — the full matrix.

The developer smoke tests (``test_law_country_prison.py``) cover one happy path per area; this module covers the rest:

* pure: ``pick_facility`` for every level × threshold × station present/absent × country prison present/absent,
  ``country_escape_chance`` (rounding, 0, never below 0), ``facility_title``, settings validation bounds;
* ``law_facility`` on the SQLite world: nested sub-districts (2 levels) + ``Locations.parent_id`` chains, a prison
  that IS a sub-district, the entrance inside a sub-district, the district deleted / its region moved to another
  country / empty / unknown country, a prison of another country, cyclic parents and the depth guard, the threshold
  setting, outlaws, the missing-column fallback (heavy -> station, the session stays usable) and other DB errors;
* flows: encounter DTO + options per facility (live resolve, closed encounter, snapshot ``has_jail``), surrender
  409 when both facilities vanish, lost guard fight and auto-resolution per facility, ``jail_writes`` overwrites a
  stale district snapshot, escape (clamp then × multiplier, multiplier 0, custom cooldown, the station term keeps its
  own cooldown, success = crime in the crime region + snapshot cleared), prisoners list mixed, the law pass clears a
  served snapshot but keeps a fresh re-jail, ``update_location`` (snapshot vs a reassigned prison, visitors, garbage
  ids, expired term), the admin character view;
* migration ``042_country_prison`` against a simulated information_schema (up / re-run no-op / down / partial) and
  the ORM column shapes; the settings API (save, older client omitting the fields, 400 texts).
"""

import logging
import re
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

import battle_client
import law_core as lc
import law_crud
import law_facility
import law_pass
import models
from tests.law_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, GAMMA, GUARD_FARM, INTERNAL, L_FARM, L_JAIL, L_MARKET, L_POST, L_ROAD, R_OST, R_PASHNI, USER_ALPHA,
    USER_BETA, USER_GAMMA, FixedRng, api, as_admin, as_user, char_row, encounter, exec_, jail_character, law_payloads,
    law_world, make_encounter, now, q, rep_world, rid, rows, set_value, set_wanted,
)
from tests.test_law_core import _load_042

R_HOLMY, R_DUNY = 12, 20
D_PRISON, D_YARD, D_PIT, D_EMPTY, D_FOREIGN = 500, 501, 502, 520, 530
L_CELL, L_CELL2, L_YARD, L_CELLAR, L_WELL, L_HOLE, L_FOREIGN = 510, 511, 512, 513, 514, 515, 531
# (depth, sort_order, id): 511 (0,1) 510 (0,2) 512 (1,0) 513 (1,0 via parent_id 512) 515 (1,0 via 513) 514 (2,0)
SUBTREE = [L_CELL2, L_CELL, L_YARD, L_CELLAR, L_HOLE, L_WELL]
YARD_SUBTREE = [L_YARD, L_CELLAR, L_HOLE, L_WELL]
COUNTRY_TITLE = "Тюрьма страны «Мидденгерд»"
STATION_TITLE = "Отделение стражи края «Ост»"
LEVEL_VALUE = {"suspect": 50, "offender": 150, "criminal": 350, "villain": 650, "enemy": 950}
BATTLE_ID = 777


@pytest.fixture
def world(law_world):
    """law_world + the prison district tree of country 1 (region 12 «Холмы») and a district of country 2."""
    exec_(law_world, "INSERT INTO Districts (id, name, region_id, parent_district_id, entrance_location_id) VALUES "
                     "(500, 'Казематы', 12, NULL, 510), (501, 'Двор', 12, 500, NULL), (502, 'Яма', 12, 501, NULL), "
                     "(520, 'Пустырь', 12, NULL, NULL), (530, 'Чужбина', 20, NULL, NULL)")
    exec_(law_world, "INSERT INTO Locations (id, name, district_id, sort_order) VALUES (510, 'Камеры', 500, 2), "
                     "(511, 'Карцер', 500, 1), (512, 'Двор', 501, 0), (514, 'Колодец', 502, 0), "
                     "(531, 'Чужой острог', 530, 0)")
    exec_(law_world, "INSERT INTO Locations (id, name, parent_id) VALUES (513, 'Подвал', 512), (515, 'Лаз', 513)")
    exec_(law_world, "UPDATE Countries SET prison_district_id = 500 WHERE id = 1")
    return law_world


def _session(f):
    return f()


def _set_threshold(f, code):
    exec_(f, "UPDATE law_settings SET country_prison_min_level = :c", c=code)


def _choose(api, enc_id, choice="surrender", user=USER_ALPHA, cid=ALPHA):
    as_user(user)
    return api.post(f"/characters/{cid}/law/encounter/{enc_id}/choice", json={"choice": choice, "request_id": rid()})


def _encounter_dto(api, cid=ALPHA, user=USER_ALPHA):
    as_user(user)
    resp = api.get(f"/characters/{cid}/law/encounter")
    assert resp.status_code == 200, resp.text
    return resp.json()["encounter"]


def _jail(api, f, level="villain", cid=ALPHA, user=USER_ALPHA, region=R_OST, location=L_POST):
    set_wanted(f, cid, region, LEVEL_VALUE[level])
    enc_id = make_encounter(f, character_id=cid, location_id=location)
    resp = _choose(api, enc_id, user=user, cid=cid)
    assert resp.status_code == 200, resp.text
    return resp.json()["jail"]


def _move(api, dest, cid=ALPHA):
    return api.put(f"/characters/internal/{cid}/update_location", json={"new_location_id": dest}, headers=INTERNAL)


def _term(f, cid=ALPHA):
    return rows(f, "SELECT id, facility, country_id, district_id, region_id, location_id, bail_price, status "
                   "FROM law_jail_terms WHERE character_id = :c ORDER BY id DESC", c=cid)[0]


# =====================================================================================================================
# pure (law_core)
# =====================================================================================================================

_LEVELS = [c for c in lc.LEVEL_CODES]


def _expected(level, threshold, has_station, has_country):
    heavy = level in _LEVELS and _LEVELS.index(level) >= _LEVELS.index(threshold)
    order = (("country", has_country), ("station", has_station)) if heavy else \
        (("station", has_station), ("country", has_country))
    return next((name for name, ok in order if ok), None)


@pytest.mark.parametrize("has_station,has_country", [(True, True), (True, False), (False, True), (False, False)],
                         ids=["both", "station-only", "country-only", "none"])
@pytest.mark.parametrize("threshold", _LEVELS)
@pytest.mark.parametrize("level", _LEVELS + ["bogus", None])
def test_pick_facility_full_matrix(level, threshold, has_station, has_country):
    got = lc.pick_facility(level, threshold, lc.DEFAULT_LEVELS, has_station, has_country)
    assert got == _expected(level, threshold, has_station, has_country)


@pytest.mark.parametrize("level", _LEVELS)
def test_unknown_threshold_means_nobody_is_heavy(level):
    assert lc.is_heavy(level, "bogus", lc.DEFAULT_LEVELS) is False
    assert lc.pick_facility(level, None, lc.DEFAULT_LEVELS, True, True) == "station"


def test_is_heavy_uses_the_level_sort_order_not_the_code_order():
    levels = [lc.Level(code=x.code, sort_order=6 - x.sort_order, name=x.name, min_value=x.min_value, fine=x.fine,
                       jail_hours=x.jail_hours) for x in lc.DEFAULT_LEVELS]          # reversed ranks
    assert lc.is_heavy("suspect", "enemy", levels) is True
    assert lc.is_heavy("enemy", "suspect", levels) is False


@pytest.mark.parametrize("station,multiplier,expected", [
    ("50", "0.5", "25.00"), ("2", "0.5", "1.00"), ("5", "0.5", "2.50"), ("33.33", "0.5", "16.67"),
    ("10", "0", "0.00"), ("10", "1", "10.00"), ("7.5", "0.33", "2.48"), ("-4", "0.5", "0.00"), ("0", "0.5", "0.00"),
])
def test_country_escape_chance(station, multiplier, expected):
    value = lc.country_escape_chance(Decimal(station), Decimal(multiplier))
    assert value == Decimal(expected) and str(value) == expected


def test_facility_titles():
    assert lc.facility_title("country", "Мидденгерд", "Ост") == COUNTRY_TITLE
    assert lc.facility_title("station", "Мидденгерд", "Ост") == STATION_TITLE
    assert lc.facility_title("station", None, None) == "Отделение стражи края «—»"
    assert lc.facility_title("anything", None, "Ост") == STATION_TITLE             # not country -> station wording
    assert lc.FACILITIES == ("station", "country")


@pytest.mark.parametrize("field,value,ok", [
    *[("country_prison_min_level", code, True) for code in lc.LEVEL_CODES],
    ("country_prison_min_level", "VILLAIN", False), ("country_prison_min_level", "", False),
    ("country_escape_multiplier", Decimal("0"), True), ("country_escape_multiplier", Decimal("1"), True),
    ("country_escape_multiplier", Decimal("0.05"), True), ("country_escape_multiplier", Decimal("-0.01"), False),
    ("country_escape_multiplier", Decimal("1.01"), False),
    ("country_escape_cooldown_hours", 1, True), ("country_escape_cooldown_hours", 168, True),
    ("country_escape_cooldown_hours", 0, False), ("country_escape_cooldown_hours", 169, False),
    ("country_escape_cooldown_hours", -5, False),
])
def test_validate_country_settings_bounds(field, value, ok):
    error = lc.validate(lc.LawSettings(**{field: value}), lc.DEFAULT_LEVELS)
    assert (error is None) is ok, error
    if not ok:
        fragment = {"country_prison_min_level": "Порог тюрьмы страны",
                    "country_escape_multiplier": "Множитель побега из тюрьмы страны: от 0 до 1",
                    "country_escape_cooldown_hours": "Перезарядка побега из тюрьмы страны: от 1 до 168 ч"}[field]
        assert fragment in error


def test_settings_defaults():
    s = lc.LawSettings()
    assert (s.country_prison_min_level, s.country_escape_multiplier, s.country_escape_cooldown_hours) == \
        ("villain", Decimal("0.5"), 12)
    assert {"country_prison_min_level", "country_escape_multiplier", "country_escape_cooldown_hours"} <= \
        set(lc.SETTINGS_FIELDS)


# =====================================================================================================================
# law_facility (SQLite world)
# =====================================================================================================================

def test_subtree_two_levels_deep_with_parent_id_chains(world):
    db = _session(world)
    try:
        assert law_facility.prison_location_ids(db, D_PRISON) == SUBTREE
        assert law_facility.prison_location_ids(db, D_YARD) == YARD_SUBTREE
        assert law_facility.prison_location_ids(db, D_EMPTY) == []
        assert law_facility.prison_location_ids(db, 99999) == []
        assert law_facility.prison_location_ids(db, None) == []
        assert law_facility.prison_location_ids(db, 0) == []
    finally:
        db.close()


def test_subtree_null_sort_order_sorts_like_zero(world):
    exec_(world, "INSERT INTO Locations (id, name, district_id, sort_order) VALUES (509, 'Сени', 500, 0)")
    db = _session(world)
    try:
        assert law_facility.prison_location_ids(db, D_PRISON)[:3] == [509, L_CELL2, L_CELL]
    finally:
        db.close()


def test_cyclic_district_and_location_parents_terminate(world):
    exec_(world, "INSERT INTO Districts (id, name, region_id, parent_district_id) VALUES (540, 'Круг', 12, 541), "
                 "(541, 'Петля', 12, 540)")
    exec_(world, "INSERT INTO Locations (id, name, district_id, parent_id) VALUES (542, 'А', 540, 545), "
                 "(543, 'Б', 541, NULL)")
    exec_(world, "INSERT INTO Locations (id, name, parent_id) VALUES (545, 'В', 542)")          # 542 <-> 545
    db = _session(world)
    try:
        ids = law_facility.prison_location_ids(db, 540)
        assert sorted(ids) == [542, 543, 545] and len(ids) == len(set(ids))
        assert ids[0] == 542                                                     # depth 0 first
    finally:
        db.close()


def test_depth_guard_caps_the_district_chain_at_ten_levels(world):
    for i in range(12):
        exec_(world, "INSERT INTO Districts (id, name, region_id, parent_district_id) VALUES (:id, :n, 12, :p)",
              id=600 + i, n=f"Ярус {i}", p=599 + i if i else None)
        exec_(world, "INSERT INTO Locations (id, name, district_id) VALUES (:id, :n, :d)", id=700 + i,
              n=f"Камера {i}", d=600 + i)
    db = _session(world)
    try:
        assert law_facility.prison_location_ids(db, 600) == [700 + i for i in range(11)]      # depth 0..10
    finally:
        db.close()


def test_prison_that_is_a_sub_district(world):
    exec_(world, "UPDATE Countries SET prison_district_id = 501 WHERE id = 1")
    db = _session(world)
    try:
        target = law_facility.country_prison(db, 1)
        assert (target.location_id, target.district_id, target.district_name) == (L_YARD, D_YARD, "Двор")
    finally:
        db.close()


def test_entrance_inside_a_sub_district_is_the_cell(world):
    exec_(world, "UPDATE Districts SET entrance_location_id = 515 WHERE id = 500")      # parent_id-hung location
    db = _session(world)
    try:
        assert law_facility.country_prison(db, 1).location_id == L_HOLE
    finally:
        db.close()


@pytest.mark.parametrize("breakage", [
    "DELETE FROM Districts WHERE id = 500",
    "UPDATE Regions SET country_id = 2 WHERE id = 12",
    "UPDATE Countries SET prison_district_id = 520 WHERE id = 1",
    "UPDATE Countries SET prison_district_id = 99999 WHERE id = 1",
    "UPDATE Countries SET prison_district_id = NULL WHERE id = 1",
    "UPDATE Countries SET prison_district_id = 530 WHERE id = 1",
    "DELETE FROM Locations WHERE id IN (510, 511, 512, 513, 514, 515)",
], ids=["district-deleted", "region-moved", "empty", "unknown", "null", "foreign-district", "locations-gone"])
def test_unusable_country_prison_is_none(world, breakage):
    exec_(world, breakage)
    db = _session(world)
    try:
        assert law_facility.country_prison(db, 1) is None
        # a heavy offender then falls back to the station of Ост
        target = law_facility.resolve_jail(db, R_OST, "villain")
        assert (target.facility, target.location_id) == ("station", L_JAIL)
    finally:
        db.close()


def test_country_prison_unknown_or_missing_country(world):
    db = _session(world)
    try:
        assert law_facility.country_prison(db, None) is None
        assert law_facility.country_prison(db, 99) is None
        assert law_facility.country_prison(db, 2) is None                    # country 2 has no prison
    finally:
        db.close()


def test_prison_of_another_country_is_ignored(world):
    """Country 2 «Пустошь» pointing at a district of country 1: no prison, and region 20 has no station -> None."""
    exec_(world, "UPDATE Countries SET prison_district_id = 500 WHERE id = 2")
    db = _session(world)
    try:
        assert law_facility.country_prison(db, 2) is None
        assert law_facility.resolve_jail(db, R_DUNY, "enemy") is None
        exec_(world, "UPDATE Countries SET prison_district_id = 530 WHERE id = 2")      # its own district: fine
        target = law_facility.resolve_jail(db, R_DUNY, "enemy")
        assert (target.facility, target.location_id, target.region_id, target.country_id) == \
            ("country", L_FOREIGN, R_DUNY, 2)
        assert target.name == "Тюрьма страны «Пустошь»"
    finally:
        db.close()


@pytest.mark.parametrize("level", _LEVELS)
@pytest.mark.parametrize("station", [True, False], ids=["station", "no-station"])
@pytest.mark.parametrize("prison", ["valid", "absent", "invalid"])
def test_resolve_jail_matrix(world, level, station, prison):
    if not station:
        exec_(world, "UPDATE Regions SET jail_location_id = NULL WHERE id = 10")
    if prison == "absent":
        exec_(world, "UPDATE Countries SET prison_district_id = NULL WHERE id = 1")
    elif prison == "invalid":
        exec_(world, "UPDATE Districts SET region_id = 20 WHERE id = 500")
    db = _session(world)
    try:
        target = law_facility.resolve_jail(db, R_OST, level)
    finally:
        db.close()
    expected = _expected(level, "villain", station, prison == "valid")
    if expected is None:
        assert target is None
        return
    assert target.facility == expected
    if expected == "country":
        assert (target.location_id, target.region_id, target.country_id, target.district_id, target.name,
                target.district_name) == (L_CELL, R_HOLMY, 1, D_PRISON, COUNTRY_TITLE, "Казематы")
    else:
        assert (target.location_id, target.region_id, target.country_id, target.district_id, target.name,
                target.district_name) == (L_JAIL, R_OST, 1, None, STATION_TITLE, None)


@pytest.mark.parametrize("threshold,country_levels", [
    ("suspect", set(_LEVELS)), ("criminal", {"criminal", "villain", "enemy"}), ("enemy", {"enemy"}),
])
def test_threshold_setting_is_read_from_the_db(world, threshold, country_levels):
    _set_threshold(world, threshold)
    db = _session(world)
    try:
        got = {lv for lv in _LEVELS if law_facility.resolve_jail(db, R_OST, lv).facility == "country"}
    finally:
        db.close()
    assert got == country_levels


def test_resolve_jail_without_region(world):
    db = _session(world)
    try:
        assert law_facility.resolve_jail(db, None, "enemy") is None
        assert law_facility.resolve_jail(db, 0, "enemy") is None
    finally:
        db.close()


def test_missing_column_falls_back_to_the_station_and_keeps_the_session(world, caplog):
    db = _session(world)
    try:
        db.execute(text("ALTER TABLE Countries DROP COLUMN prison_district_id"))
        with caplog.at_level(logging.WARNING, logger="character-service.law_facility"):
            target = law_facility.resolve_jail(db, R_OST, "enemy")
        assert (target.facility, target.location_id) == ("station", L_JAIL)
        assert any(r.levelno == logging.WARNING and "migration 057" in r.getMessage() for r in caplog.records)
        # the savepoint kept the outer transaction alive
        assert db.execute(text("SELECT name FROM Regions WHERE id = 10")).scalar() == "Ост"
        # nothing left at all: no surrender
        db.execute(text("UPDATE Regions SET jail_location_id = NULL WHERE id = 10"))
        assert law_facility.resolve_jail(db, R_OST, "enemy") is None
    finally:
        db.close()


def test_other_db_errors_are_not_swallowed(world):
    db = _session(world)
    try:
        db.execute(text("ALTER TABLE Countries RENAME TO Countries_gone"))
        with pytest.raises(DBAPIError):
            law_facility.prison_district_of(db, 1)
    finally:
        db.rollback()
        db.close()


def test_missing_column_predicate():
    class _E(Exception):
        pass

    assert law_facility._missing_prison_column(_E("(1054, \"Unknown column 'prison_district_id' in 'field list'\")"))
    assert law_facility._missing_prison_column(_E("no such column: prison_district_id"))
    assert not law_facility._missing_prison_column(_E("Unknown column 'jail_location_id'"))
    assert not law_facility._missing_prison_column(_E("prison_district_id: deadlock found"))


# =====================================================================================================================
# encounters: snapshot, DTO, options
# =====================================================================================================================

@pytest.mark.parametrize("level,facility,title", [
    ("offender", "station", STATION_TITLE), ("criminal", "station", STATION_TITLE),
    ("villain", "country", COUNTRY_TITLE), ("enemy", "country", COUNTRY_TITLE),
])
def test_encounter_dto_names_the_facility(api, world, level, facility, title):
    set_wanted(world, ALPHA, R_OST, LEVEL_VALUE[level])
    enc_id = make_encounter(world)
    assert encounter(world, enc_id).has_jail is True
    dto = _encounter_dto(api)
    assert (dto["jail_facility"], dto["jail_name"], dto["has_jail"]) == (facility, title, True)
    assert "surrender" in dto["options"]


def test_encounter_without_any_facility(api, world):
    """Region 11 «Пашни» has no station; with the country prison gone nobody can be jailed there."""
    exec_(world, "UPDATE Countries SET prison_district_id = NULL WHERE id = 1")
    set_wanted(world, ALPHA, R_PASHNI, LEVEL_VALUE["villain"])
    enc_id = make_encounter(world, location_id=L_FARM)
    assert encounter(world, enc_id).has_jail is False
    dto = _encounter_dto(api)
    assert dto["has_jail"] is False and dto["jail_facility"] is None and dto["jail_name"] is None
    assert dto["options"] == ["fine", "flee", "fight"]


def test_light_offender_without_station_goes_to_the_country(api, world):
    set_wanted(world, ALPHA, R_PASHNI, LEVEL_VALUE["suspect"])
    enc_id = make_encounter(world, location_id=L_FARM)
    assert encounter(world, enc_id).has_jail is True                          # the snapshot sees the country prison
    dto = _encounter_dto(api)
    assert (dto["jail_facility"], dto["jail_name"]) == ("country", COUNTRY_TITLE)
    jail = _choose(api, enc_id).json()["jail"]
    assert jail["facility"] == "country" and char_row(world, ALPHA).current_location_id == L_CELL
    assert _term(world)[4] == R_PASHNI                                          # crime region kept


def test_outlaw_options_and_facility(api, world):
    """An outlaw is stopped at the outlaw minimum level («criminal» < «villain») -> the station; no fine / flee."""
    set_value(world, ALPHA, R_OST, -700)
    enc_id = make_encounter(world)
    dto = _encounter_dto(api)
    assert dto["is_outlaw"] is True and dto["options"] == ["surrender", "fight"]
    assert dto["jail_facility"] == "station"
    _set_threshold(world, "criminal")
    dto = _encounter_dto(api)
    assert (dto["jail_facility"], dto["jail_name"]) == ("country", COUNTRY_TITLE)
    assert _choose(api, enc_id).json()["jail"]["facility"] == "country"


def test_encounter_dto_is_a_live_resolve(api, world):
    set_wanted(world, ALPHA, R_OST, LEVEL_VALUE["villain"])
    make_encounter(world)
    assert _encounter_dto(api)["jail_facility"] == "country"
    exec_(world, "UPDATE Countries SET prison_district_id = NULL WHERE id = 1")
    dto = _encounter_dto(api)
    assert (dto["jail_facility"], dto["jail_name"]) == ("station", STATION_TITLE)


def test_closed_encounter_has_no_facility_fields(api, world):
    set_wanted(world, ALPHA, R_OST, LEVEL_VALUE["villain"])
    enc_id = make_encounter(world)
    _choose(api, enc_id)
    db = _session(world)
    try:
        enc = db.query(models.LawEncounter).filter(models.LawEncounter.id == enc_id).first()
        out = law_crud.encounter_out(db, enc)
    finally:
        db.close()
    assert out["status"] == "jailed" and out["options"] == []
    assert out["jail_facility"] is None and out["jail_name"] is None and out["has_jail"] is True


def test_surrender_when_both_facilities_vanished_is_409(api, world):
    set_wanted(world, ALPHA, R_OST, LEVEL_VALUE["villain"])
    enc_id = make_encounter(world)
    exec_(world, "UPDATE Countries SET prison_district_id = NULL WHERE id = 1")
    exec_(world, "UPDATE Regions SET jail_location_id = NULL WHERE id = 10")
    assert "surrender" not in _encounter_dto(api)["options"]
    resp = _choose(api, enc_id)
    assert resp.status_code == 409 and resp.json()["detail"] == law_crud.MSG_NO_JAIL
    assert q(world, "SELECT COUNT(*) FROM law_jail_terms") == 0
    assert encounter(world, enc_id).status == "pending"


def test_station_jail_notification_and_journal(api, world, stub_law_notify_send):
    _jail(api, world, "offender")
    msgs = [p["message"] for p in law_payloads(stub_law_notify_send) if p["target_value"] == USER_ALPHA]
    assert any(m.startswith("Стража края «Ост» заключила вас в отделение стражи — срок") for m in msgs)
    assert not any("Залога нет" in m for m in msgs)
    desc = q(world, "SELECT description FROM character_logs WHERE character_id = :c ORDER BY id DESC LIMIT 1",
             c=ALPHA)
    assert desc.endswith(f"({STATION_TITLE})")


def test_country_jail_journal_names_the_prison(api, world, stub_law_notify_send):
    _jail(api, world, "villain")
    desc = q(world, "SELECT description FROM character_logs WHERE character_id = :c ORDER BY id DESC LIMIT 1",
             c=ALPHA)
    assert desc == f"Заключён под стражу: «Застава» → «Камеры» ({COUNTRY_TITLE})"
    msgs = [p["message"] for p in law_payloads(stub_law_notify_send) if p["target_value"] == USER_ALPHA]
    assert any("Залога нет, передвигаться можно только внутри тюрьмы" in m for m in msgs)


def test_jail_writes_overwrites_a_stale_district_snapshot(api, world):
    exec_(world, "UPDATE characters SET jail_district_id = 999 WHERE id = :c", c=ALPHA)
    jail = _jail(api, world, "offender")
    assert jail["facility"] == "station" and jail["district_id"] is None
    assert char_row(world, ALPHA).jail_district_id is None
    term = _term(world)
    assert term[1:7] == ("station", None, None, R_OST, L_JAIL, 300)            # bail = ceil(150 × 2)


def test_country_term_snapshot_and_jailed_in_place(api, world):
    """Already standing in the prison cell: no move, still a country term."""
    exec_(world, "UPDATE characters SET current_location_id = :l WHERE id = :g", l=L_CELL, g=60)   # guard -> cell
    set_wanted(world, ALPHA, R_HOLMY, LEVEL_VALUE["villain"])
    enc_id = make_encounter(world, location_id=L_CELL, from_location_id=L_CELL2)
    world.prepare_move.reset_mock()
    jail = _choose(api, enc_id).json()["jail"]
    world.prepare_move.assert_not_called()                                      # not moving
    assert jail["facility"] == "country" and jail["region_id"] == R_HOLMY
    assert _term(world)[1:7] == ("country", 1, D_PRISON, R_HOLMY, L_CELL, 0)


# =====================================================================================================================
# lost guard fight / auto-resolution per facility
# =====================================================================================================================

@pytest.fixture
def battle(monkeypatch):
    from unittest.mock import AsyncMock
    mock = AsyncMock(return_value=BATTLE_ID)
    monkeypatch.setattr(battle_client, "create_guard_battle", mock)
    return mock


def _lose_fight(api, f, level):
    set_wanted(f, ALPHA, R_OST, LEVEL_VALUE[level])
    enc_id = make_encounter(f)
    assert _choose(api, enc_id, "fight").json()["result"] == "fight"
    return api.post("/characters/internal/law/battle-result",
                    json={"battle_id": BATTLE_ID, "law_encounter_id": enc_id, "winner_team": 2, "aborted": False},
                    headers=INTERNAL)


@pytest.mark.parametrize("level,facility,cell", [("offender", "station", L_JAIL), ("enemy", "country", L_CELL)])
def test_lost_fight_jails_per_facility(api, world, battle, level, facility, cell):
    resp = _lose_fight(api, world, level)
    assert resp.status_code == 200 and resp.json()["status"] == "jailed", resp.text
    assert _term(world)[1] == facility and char_row(world, ALPHA).current_location_id == cell


def test_lost_fight_without_any_facility_is_a_forced_fine(api, world, battle):
    exec_(world, "UPDATE Countries SET prison_district_id = NULL WHERE id = 1")
    exec_(world, "UPDATE Regions SET jail_location_id = NULL WHERE id = 10")
    resp = _lose_fight(api, world, "villain")
    assert resp.json()["status"] == "auto_fined"
    assert q(world, "SELECT COUNT(*) FROM law_jail_terms") == 0


@pytest.mark.parametrize("region,location,level,facility,cell", [
    (R_OST, L_POST, "offender", "station", L_JAIL),
    (R_OST, L_POST, "villain", "country", L_CELL),
    (R_PASHNI, L_FARM, "offender", "country", L_CELL),                 # no station in Пашни -> the country prison
])
def test_auto_resolve_per_facility(world, stub_law_notify_send, region, location, level, facility, cell):
    set_wanted(world, ALPHA, region, LEVEL_VALUE[level])
    enc_id = make_encounter(world, location_id=location)
    exec_(world, "UPDATE law_encounters SET expires_at = :t WHERE id = :e", t=now() - timedelta(minutes=1), e=enc_id)
    assert law_pass.run_pass(world, None, claim=False)["auto_resolved"] == 1
    term = _term(world)
    assert (term[1], term[5], term[4]) == (facility, cell, region)
    row = char_row(world, ALPHA)
    assert row.current_location_id == cell
    assert row.jail_district_id == (D_PRISON if facility == "country" else None)
    assert q(world, "SELECT action FROM law_log WHERE event_key = :k", k=f"law:auto:{enc_id}") == "auto_surrender"


def test_auto_resolve_without_facility_is_a_forced_fine(world):
    exec_(world, "UPDATE Countries SET prison_district_id = NULL WHERE id = 1")
    set_wanted(world, ALPHA, R_PASHNI, LEVEL_VALUE["villain"])
    enc_id = make_encounter(world, location_id=L_FARM)
    exec_(world, "UPDATE law_encounters SET expires_at = :t WHERE id = :e", t=now() - timedelta(minutes=1), e=enc_id)
    law_pass.run_pass(world, None, claim=False)
    assert encounter(world, enc_id).status == "auto_fined"
    assert q(world, "SELECT COUNT(*) FROM law_jail_terms") == 0


# =====================================================================================================================
# escape
# =====================================================================================================================

def _escape(api, cid=ALPHA, user=USER_ALPHA):
    as_user(user)
    return api.post(f"/characters/{cid}/law/jail/escape", json={"request_id": rid()})


def _stealth(f, value, cid=ALPHA):
    exec_(f, "UPDATE character_attributes SET stealth = :v WHERE character_id = :c", v=value, c=cid)


def test_escape_multiplier_applies_after_the_station_clamp(api, world, monkeypatch):
    _stealth(world, 5000)                                    # station chance clamped at 50 %
    jail = _jail(api, world, "villain")
    assert jail["escape_chance_pct"] == 25.0
    monkeypatch.setattr(law_crud, "rng", lambda: FixedRng(0.99))
    _escape(api)
    assert Decimal(str(q(world, "SELECT chance_pct FROM law_log WHERE action = 'escape_fail'"))) == Decimal("25.00")


def test_station_term_escape_is_not_multiplied(api, world):
    _stealth(world, 5000)
    assert _jail(api, world, "offender")["escape_chance_pct"] == 50.0


def test_escape_multiplier_zero_refuses_the_attempt(api, world, monkeypatch):
    exec_(world, "UPDATE law_settings SET country_escape_multiplier = 0")
    jail = _jail(api, world, "villain")
    assert jail["escape_chance_pct"] == 0.0
    until_before = q(world, "SELECT until FROM law_jail_terms WHERE character_id = :c", c=ALPHA)
    monkeypatch.setattr(law_crud, "rng", lambda: FixedRng(0.0))               # the luckiest roll
    resp = _escape(api)
    assert resp.status_code == 409 and resp.json()["detail"] == "Отсюда не сбежать"
    # no attempt is spent: the term is not extended, no cooldown, no log row
    assert q(world, "SELECT until FROM law_jail_terms WHERE character_id = :c", c=ALPHA) == until_before
    assert q(world, "SELECT next_escape_at FROM law_jail_terms WHERE character_id = :c", c=ALPHA) is None
    assert int(q(world, "SELECT escape_attempts FROM law_jail_terms WHERE character_id = :c", c=ALPHA) or 0) == 0
    assert q(world, "SELECT COUNT(*) FROM law_log WHERE action IN ('escape_fail', 'escape_ok')") == 0


def test_custom_country_cooldown_and_the_station_keeps_its_own(api, world, monkeypatch):
    exec_(world, "UPDATE law_settings SET country_escape_cooldown_hours = 5, escape_cooldown_hours = 2")
    monkeypatch.setattr(law_crud, "rng", lambda: FixedRng(0.99))
    _jail(api, world, "villain")
    assert _escape(api).status_code == 200
    next_at = law_crud._dt(q(world, "SELECT next_escape_at FROM law_jail_terms WHERE character_id = :c", c=ALPHA))
    assert timedelta(hours=4, minutes=59) < next_at - now() <= timedelta(hours=5, minutes=1)
    resp = _escape(api)                                                        # inside the cooldown
    assert resp.status_code == 409 and resp.json()["detail"].startswith("Следующая попытка побега")
    # a station prisoner (Beta) uses escape_cooldown_hours
    _jail(api, world, "offender", cid=BETA, user=USER_BETA)
    assert _escape(api, BETA, USER_BETA).status_code == 200
    next_b = law_crud._dt(q(world, "SELECT next_escape_at FROM law_jail_terms WHERE character_id = :c", c=BETA))
    assert timedelta(hours=1, minutes=59) < next_b - now() <= timedelta(hours=2, minutes=1)


def test_successful_escape_from_the_country_prison(api, world, monkeypatch):
    _jail(api, world, "villain")
    monkeypatch.setattr(law_crud, "rng", lambda: FixedRng(0.0))
    resp = _escape(api)
    assert resp.status_code == 200 and resp.json()["success"] is True
    row = char_row(world, ALPHA)
    assert row.jail_district_id is None and row.jail_region_id is None
    assert _term(world)[7] == "escaped"
    crime = rows(world, "SELECT crime_type, region_id, location_id FROM law_crimes WHERE character_id = :c", c=ALPHA)
    assert crime == [("jail_escape", R_OST, L_CELL)]                           # crime region, not the prison's
    # free again: the prison exception no longer applies, and he may walk anywhere
    assert _move(api, L_ROAD).status_code == 200


# =====================================================================================================================
# bail / prisoners
# =====================================================================================================================

def test_self_bail_refused_before_any_money_moves(api, world):
    _jail(api, world, "villain")
    exec_(world, "UPDATE characters SET currency_balance = 5000 WHERE id = :c", c=ALPHA)
    as_user(USER_ALPHA)
    resp = api.post(f"/characters/{ALPHA}/law/jail/bail", json={"request_id": rid()})
    assert resp.status_code == 409 and resp.json()["detail"] == law_crud.MSG_NO_BAIL_COUNTRY
    assert q(world, "SELECT currency_balance FROM characters WHERE id = :c", c=ALPHA) == 5000
    assert _term(world)[7] == "serving"
    assert q(world, "SELECT COUNT(*) FROM law_log WHERE action = 'bail'") == 0


def test_prisoners_list_mixed_facilities(api, world):
    _jail(api, world, "villain")                                               # Alpha: country
    _jail(api, world, "offender", cid=BETA, user=USER_BETA)                    # Beta: station
    as_user(USER_GAMMA)
    data = api.get("/characters/law/prisoners").json()
    assert data["total"] == 1
    assert [p["character_id"] for p in data["items"]] == [BETA]
    as_user(USER_GAMMA)
    assert api.get("/characters/law/prisoners", params={"q": "Альфа"}).json()["total"] == 0


# =====================================================================================================================
# snapshot lifecycle (term end, law pass, staff)
# =====================================================================================================================

def test_law_pass_served_country_term_clears_the_snapshot(api, world):
    _jail(api, world, "villain")
    exec_(world, "UPDATE law_jail_terms SET until = :t WHERE character_id = :c", t=now() - timedelta(minutes=1),
          c=ALPHA)
    exec_(world, "UPDATE characters SET jailed_until = :t WHERE id = :c", t=now() - timedelta(minutes=1), c=ALPHA)
    assert law_pass.run_pass(world, None, claim=False)["served"] == 1
    row = char_row(world, ALPHA)
    assert row.jail_district_id is None and row.jail_region_id is None


def test_law_pass_keeps_a_fresh_re_jail_snapshot(api, world):
    """An old term reaches its end while the character already serves a new country term: the pass closes the old
    term but must not clear the new snapshot (``jailed_until`` is in the future)."""
    old = jail_character(world, hours=-1)                                       # a stale station term
    exec_(world, "UPDATE characters SET jailed_until = NULL, jail_region_id = NULL WHERE id = :c", c=ALPHA)
    _jail(api, world, "villain")                                                # the fresh country term
    assert char_row(world, ALPHA).jail_district_id == D_PRISON
    assert law_pass.run_pass(world, None, claim=False)["served"] == 1
    assert q(world, "SELECT status FROM law_jail_terms WHERE id = :t", t=old) == "served"
    row = char_row(world, ALPHA)
    assert row.jail_district_id == D_PRISON and row.jail_region_id == R_OST


def test_staff_release_endpoint_clears_the_snapshot_and_frees_movement(api, world):
    _jail(api, world, "villain")
    as_admin()
    resp = api.post(f"/characters/admin/law/characters/{ALPHA}/release",
                    json={"reason": "проверка", "request_id": rid()})
    assert resp.status_code == 200, resp.text
    assert char_row(world, ALPHA).jail_district_id is None
    assert _move(api, L_ROAD).status_code == 200


# =====================================================================================================================
# update_location (the authority)
# =====================================================================================================================

@pytest.mark.parametrize("dest", SUBTREE)
def test_country_prisoner_moves_anywhere_inside_the_subtree(api, world, dest):
    _jail(api, world, "villain")
    resp = _move(api, dest)
    assert resp.status_code == 200, resp.text
    assert resp.json()["law_encounter"] is None
    assert char_row(world, ALPHA).current_location_id == dest


@pytest.mark.parametrize("dest", [L_JAIL, L_FOREIGN, L_POST, 99999, "abc", None])
def test_country_prisoner_cannot_leave(api, world, dest):
    _jail(api, world, "villain")
    resp = _move(api, dest)
    if dest is None:
        assert resp.status_code == 400
    else:
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"].startswith("Персонаж в тюрьме")
    assert char_row(world, ALPHA).current_location_id == L_CELL


def test_movement_uses_the_snapshot_not_the_live_prison(api, world):
    _jail(api, world, "villain")
    exec_(world, "UPDATE Countries SET prison_district_id = 530 WHERE id = 1")         # reassigned mid-term
    assert _move(api, L_FOREIGN).status_code == 409
    assert _move(api, L_WELL).status_code == 200
    exec_(world, "UPDATE Countries SET prison_district_id = NULL WHERE id = 1")        # removed mid-term
    assert _move(api, L_CELL2).status_code == 200
    as_user(USER_ALPHA)
    jail = api.get(f"/characters/{ALPHA}/law/jail").json()["jail"]
    assert jail["allowed_location_ids"] == SUBTREE and jail["facility"] == "country"


def test_station_prisoner_cannot_move_into_the_prison(api, world):
    _jail(api, world, "offender")
    for dest in (L_CELL, L_JAIL + 1):
        assert _move(api, dest).status_code == 409


def test_visitor_walks_into_the_prison(api, world):
    resp = _move(api, L_CELL)
    assert resp.status_code == 200 and resp.json()["law_encounter"] is None
    assert char_row(world, ALPHA).current_location_id == L_CELL


def test_stale_snapshot_does_not_open_an_encounter_lock(api, world):
    """The term ran out lazily (``jailed_until`` past, the snapshot not yet cleared by the pass) and the guards stop
    the character again: the leftover ``jail_district_id`` must not let a pending encounter move into the prison."""
    _jail(api, world, "villain")
    exec_(world, "UPDATE characters SET jailed_until = :t WHERE id = :c", t=now() - timedelta(minutes=1), c=ALPHA)
    set_wanted(world, ALPHA, R_OST, LEVEL_VALUE["villain"])
    enc_id = make_encounter(world)
    assert enc_id is not None
    assert _move(api, L_CELL).status_code == 409


# =====================================================================================================================
# read models
# =====================================================================================================================

def test_jail_dto_for_a_vanished_prison_district(api, world):
    _jail(api, world, "villain")
    exec_(world, "DELETE FROM Districts WHERE id IN (500, 501, 502)")
    as_user(USER_ALPHA)
    jail = api.get(f"/characters/{ALPHA}/law/jail").json()["jail"]
    assert jail["allowed_location_ids"] == [] and jail["district_name"] is None
    assert jail["facility_name"] == COUNTRY_TITLE and jail["bail_available"] is False


def test_state_and_admin_views_carry_the_facility(api, world):
    _jail(api, world, "villain")
    as_user(USER_ALPHA)
    state = api.get(f"/characters/{ALPHA}/law").json()
    assert state["jail"]["facility"] == "country" and state["jail"]["bail_price"] is None
    as_admin()
    resp = api.get(f"/characters/admin/law/characters/{ALPHA}")
    assert resp.status_code == 200, resp.text
    jail = resp.json()["jail"]
    assert (jail["facility"], jail["facility_name"], jail["district_id"], jail["district_name"], jail["country_id"],
            jail["bail_available"], jail["bail_price"], jail["status"]) == \
        ("country", COUNTRY_TITLE, D_PRISON, "Казематы", 1, False, None, "serving")
    assert jail["allowed_location_ids"] == SUBTREE


def test_station_jail_dto_fields(api, world):
    jail = _jail(api, world, "offender")
    assert (jail["facility"], jail["facility_name"], jail["country_id"], jail["district_id"], jail["district_name"],
            jail["bail_available"], jail["bail_price"], jail["allowed_location_ids"]) == \
        ("station", STATION_TITLE, None, None, None, True, 300, [L_JAIL])


def test_legacy_term_without_facility_reads_as_station(api, world):
    """Rows written before migration 042 get the column default 'station'; a NULL / odd value reads as station."""
    term_id = jail_character(world, hours=3)
    assert q(world, "SELECT facility FROM law_jail_terms WHERE id = :t", t=term_id) == "station"
    exec_(world, "UPDATE law_jail_terms SET facility = 'odd' WHERE id = :t", t=term_id)
    as_user(USER_ALPHA)
    jail = api.get(f"/characters/{ALPHA}/law/jail").json()["jail"]
    assert jail["facility"] == "station" and jail["bail_available"] is True


# =====================================================================================================================
# settings API
# =====================================================================================================================

def _settings_body(api):
    as_admin()
    return api.get("/characters/admin/law/settings").json()


def test_settings_api_roundtrip(api, world):
    body = _settings_body(api)
    assert (body["settings"]["country_prison_min_level"], body["settings"]["country_escape_multiplier"],
            body["settings"]["country_escape_cooldown_hours"]) == ("villain", 0.5, 12)
    body["settings"].update(country_prison_min_level="criminal", country_escape_multiplier=0.25,
                            country_escape_cooldown_hours=24)
    resp = api.put("/characters/admin/law/settings", json=body)
    assert resp.status_code == 200, resp.text
    s = resp.json()["settings"]
    assert (s["country_prison_min_level"], s["country_escape_multiplier"], s["country_escape_cooldown_hours"]) == \
        ("criminal", 0.25, 24)
    assert rows(world, "SELECT country_prison_min_level, country_escape_cooldown_hours FROM law_settings") == \
        [("criminal", 24)]


def test_settings_api_older_client_keeps_the_new_fields(api, world):
    exec_(world, "UPDATE law_settings SET country_prison_min_level = 'enemy', country_escape_multiplier = 0.3, "
                 "country_escape_cooldown_hours = 6")
    body = _settings_body(api)
    for name in ("country_prison_min_level", "country_escape_multiplier", "country_escape_cooldown_hours"):
        body["settings"].pop(name)
    resp = api.put("/characters/admin/law/settings", json=body)
    assert resp.status_code == 200, resp.text
    s = resp.json()["settings"]
    assert (s["country_prison_min_level"], s["country_escape_multiplier"], s["country_escape_cooldown_hours"]) == \
        ("enemy", 0.3, 6)


@pytest.mark.parametrize("field,value,fragment", [
    ("country_prison_min_level", "boss", "Порог тюрьмы страны должен быть одним из уровней розыска"),
    ("country_prison_min_level", "' OR 1=1 --", "Порог тюрьмы страны"),
    ("country_escape_multiplier", 1.5, "Множитель побега из тюрьмы страны: от 0 до 1"),
    ("country_escape_multiplier", -0.1, "Множитель побега из тюрьмы страны: от 0 до 1"),
    ("country_escape_cooldown_hours", 0, "Перезарядка побега из тюрьмы страны: от 1 до 168 ч"),
    ("country_escape_cooldown_hours", 500, "Перезарядка побега из тюрьмы страны: от 1 до 168 ч"),
])
def test_settings_api_validation(api, world, field, value, fragment):
    body = _settings_body(api)
    body["settings"][field] = value
    resp = api.put("/characters/admin/law/settings", json=body)
    assert resp.status_code == 400 and fragment in resp.json()["detail"]
    assert q(world, "SELECT country_prison_min_level FROM law_settings") == "villain"
    assert q(world, "SELECT country_escape_cooldown_hours FROM law_settings") == 12


def test_settings_api_long_level_code_is_422(api, world):
    body = _settings_body(api)
    body["settings"]["country_prison_min_level"] = "x" * 21
    assert api.put("/characters/admin/law/settings", json=body).status_code == 422


# =====================================================================================================================
# migration 042 + ORM
# =====================================================================================================================

class _Scalar:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _FakeMySQL:
    """information_schema answers + the ALTER statements 042 issues."""

    def __init__(self, tables=("law_settings", "law_jail_terms", "characters"), columns=None):
        self.tables = set(tables)
        self.columns = {t: set() for t in self.tables}
        for t, c in (columns or ()):
            self.columns[t].add(c)
        self.statements = []

    def execute(self, clause, params=None):
        sql = str(clause)
        if "information_schema.tables" in sql:
            return _Scalar(int(params["t"] in self.tables))
        if "information_schema.columns" in sql:
            return _Scalar(int(params["c"] in self.columns.get(params["t"], set())))
        raise AssertionError(sql)

    def op_execute(self, sql):
        self.statements.append(sql)
        m = re.match(r"ALTER TABLE (\w+) (ADD|DROP) COLUMN (\w+)", sql)
        assert m, sql
        table, verb, column = m.groups()
        (self.columns[table].add if verb == "ADD" else self.columns[table].discard)(column)


class _Op:
    def __init__(self, db):
        self.db = db

    def get_bind(self):
        return self.db

    def execute(self, sql):
        self.db.op_execute(sql)


def _run_042(db, step):
    mod = _load_042()
    mod.op = _Op(db)
    getattr(mod, step)()
    return mod


def test_042_upgrade_rerun_downgrade():
    db = _FakeMySQL()
    mod = _run_042(db, "upgrade")
    assert len(db.statements) == 7
    assert db.columns == {"law_settings": {"country_prison_min_level", "country_escape_multiplier",
                                           "country_escape_cooldown_hours"},
                          "law_jail_terms": {"facility", "country_id", "district_id"},
                          "characters": {"jail_district_id"}}
    ddl = {c: d for _t, c, d in mod._COLUMNS}
    assert ddl["country_prison_min_level"] == "VARCHAR(20) NOT NULL DEFAULT 'villain'"
    assert ddl["country_escape_multiplier"] == "DECIMAL(5,2) NOT NULL DEFAULT 0.50"
    assert ddl["country_escape_cooldown_hours"] == "INT NOT NULL DEFAULT 12"
    assert ddl["facility"] == "VARCHAR(10) NOT NULL DEFAULT 'station'"
    assert all(ddl[c] == "INT NULL" for c in ("country_id", "district_id", "jail_district_id"))
    assert not any("FOREIGN KEY" in s or "ENUM" in s for s in db.statements)
    db.statements.clear()
    _run_042(db, "upgrade")
    assert db.statements == []                                                     # re-run: no-op
    _run_042(db, "downgrade")
    assert [s.split()[-1] for s in db.statements] == [c for _t, c, _d in reversed(mod._COLUMNS)]
    assert all(not cols for cols in db.columns.values())
    db.statements.clear()
    _run_042(db, "downgrade")
    assert db.statements == []


def test_042_partial_state_and_missing_table():
    db = _FakeMySQL(tables=("law_settings", "characters"), columns=[("characters", "jail_district_id")])
    _run_042(db, "upgrade")
    assert all("law_jail_terms" not in s and "jail_district_id" not in s for s in db.statements)
    assert len(db.statements) == 3


def test_042_defaults_match_the_dataclass():
    s = lc.LawSettings()
    ddl = {c: d for _t, c, d in _load_042()._COLUMNS}
    assert f"'{s.country_prison_min_level}'" in ddl["country_prison_min_level"]
    assert Decimal(ddl["country_escape_multiplier"].split()[-1]) == s.country_escape_multiplier
    assert int(ddl["country_escape_cooldown_hours"].split()[-1]) == s.country_escape_cooldown_hours


def test_orm_column_shapes():
    t = models.LawJailTerm.__table__.c
    assert t.facility.type.length == 10 and t.facility.nullable is False
    assert t.facility.server_default.arg == "station" and t.facility.default.arg == "station"
    assert t.country_id.nullable and t.district_id.nullable
    assert not t.country_id.foreign_keys and not t.district_id.foreign_keys
    s = models.LawSettings.__table__.c
    assert s.country_prison_min_level.nullable is False and s.country_escape_multiplier.nullable is False
    assert s.country_escape_cooldown_hours.nullable is False
    assert (s.country_escape_multiplier.type.precision, s.country_escape_multiplier.type.scale) == (5, 2)
    c = models.Character.__table__.c.jail_district_id
    assert c.nullable is True and not c.foreign_keys


def test_settings_row_reads_the_new_columns(world):
    exec_(world, "UPDATE law_settings SET country_prison_min_level = 'criminal', country_escape_multiplier = 0.75, "
                 "country_escape_cooldown_hours = 30")
    db = _session(world)
    try:
        s = law_crud.load_settings(db)
    finally:
        db.close()
    assert (s.country_prison_min_level, Decimal(str(s.country_escape_multiplier)), s.country_escape_cooldown_hours) \
        == ("criminal", Decimal("0.75"), 30)
