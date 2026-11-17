"""FEAT-214 (T11): ``sea_unrest`` in GET /locations/{id}/client/details, on a real SQLite DB.

``sea_unrest`` is True only on a PORT whose ``port_sea_zone_id`` is covered by an active storm
(``sea_storm_zones`` JOIN ``sea_storms`` with ``status='active'`` and ``ends_at > utcnow``). Storms are
character-service tables (migration ``053_sea_storms_raids``); here they are stand-ins with the read columns.
Missing tables (deploy order) → False plus one WARNING from ``sea_read._rows``.
"""
import logging
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import main  # noqa: E402
import sea_read  # noqa: E402
from auth_http import UserRead  # noqa: E402
from database import get_db  # noqa: E402
from sea_sqlite import CHAR, LAND, LAND2, OTHER_CHAR, PORT_A, PORT_B, PORT_C, Z1, Z2, Z3, build_world  # noqa: E402

USER, OTHER_USER = 5, 6
PLAYER = UserRead(id=USER, username="p", role="user", permissions=[])
STORM_WARNING = "storms over zone"

STORM_DDL = [
    "CREATE TABLE sea_storms (id INTEGER PRIMARY KEY AUTOINCREMENT, region_id INTEGER NULL, "
    "center_zone_id INTEGER NOT NULL, status VARCHAR(10) NOT NULL, source VARCHAR(10) NOT NULL, "
    "moves INTEGER NOT NULL DEFAULT 0, started_at DATETIME NOT NULL, ends_at DATETIME NOT NULL, "
    "ended_at DATETIME NULL)",
    "CREATE TABLE sea_storm_zones (storm_id INTEGER NOT NULL, zone_id INTEGER NOT NULL, "
    "PRIMARY KEY (storm_id, zone_id))",
]

_EXTERNALS = {
    "crud.finalize_due_sessions": None,
    "crud.get_players_in_location": [],
    "crud.get_npcs_in_location": [],
    "crud.get_posts_by_location": [],
    "crud.get_likes_for_posts": {},
    "crud.gates_for_posts": {},
    "crud.pending_gates_for_posts": {},
    "crud.get_location_loot": [],
    "crud.is_favorited": False,
    "crud.lazy_restore_depleted_nodes": None,
    "crud.fetch_gathering_nodes_with_active_sessions": [],
}


def _prepare(w):
    w.sql("CREATE TABLE characters (id INTEGER PRIMARY KEY, user_id INTEGER)")
    w.sql(f"INSERT INTO characters (id, user_id) VALUES ({CHAR}, {USER}), ({OTHER_CHAR}, {OTHER_USER})")
    return w


@pytest.fixture()
def world(tmp_path):
    w = _prepare(build_world(tmp_path / "sea.db"))
    for q in STORM_DDL:
        w.sql(q)
    return w


@pytest.fixture(autouse=True)
def _clean_overrides():
    main.app.dependency_overrides.clear()
    yield
    main.app.dependency_overrides.clear()


def _storm(world, zones, status="active", ends_in=timedelta(hours=1)):
    now = datetime.utcnow()
    world.sql("INSERT INTO sea_storms (center_zone_id, status, source, started_at, ends_at) "
              "VALUES (:c, :st, 'auto', :s, :e)",
              c=zones[0], st=status, s=(now - timedelta(minutes=5)).isoformat(" "),
              e=(now + ends_in).isoformat(" "))
    sid = world.sql("SELECT MAX(id) FROM sea_storms")[0][0]
    for z in zones:
        world.sql("INSERT INTO sea_storm_zones (storm_id, zone_id) VALUES (:s, :z)", s=sid, z=z)
    return sid


def _details(world, location_id, character_id=CHAR, user=PLAYER):
    main.app.dependency_overrides[get_db] = world.db_override()
    main.app.dependency_overrides[main.get_optional_user] = lambda: user
    patches = [patch(name, new_callable=AsyncMock, return_value=value) for name, value in _EXTERNALS.items()]
    for p in patches:
        p.start()
    try:
        url = f"/locations/{location_id}/client/details"
        if character_id is not None:
            url += f"?character_id={character_id}"
        r = TestClient(main.app).get(url)
    finally:
        for p in patches:
            p.stop()
    assert r.status_code == 200, r.text
    return r.json()


class TestSeaUnrestDetails:
    def test_port_with_active_storm(self, world):
        _storm(world, [Z1])
        data = _details(world, PORT_A)
        assert data["sea_unrest"] is True

    def test_storm_covering_several_zones(self, world):
        _storm(world, [Z2, Z1])
        assert _details(world, PORT_A)["sea_unrest"] is True
        assert _details(world, PORT_B)["sea_unrest"] is True

    def test_visible_to_anonymous_viewer(self, world):
        _storm(world, [Z1])
        assert _details(world, PORT_A, character_id=None, user=None)["sea_unrest"] is True

    def test_no_storms_at_all(self, world):
        assert _details(world, PORT_A)["sea_unrest"] is False

    def test_expired_but_still_active_status(self, world):
        _storm(world, [Z1], ends_in=timedelta(minutes=-1))
        assert _details(world, PORT_A)["sea_unrest"] is False

    @pytest.mark.parametrize("status", ["ended", "cancelled"])
    def test_ended_storm(self, world, status):
        _storm(world, [Z1], status=status)
        assert _details(world, PORT_A)["sea_unrest"] is False

    def test_one_live_storm_among_dead_ones(self, world):
        _storm(world, [Z1], status="ended")
        _storm(world, [Z1], ends_in=timedelta(minutes=-10))
        _storm(world, [Z1])
        assert _details(world, PORT_A)["sea_unrest"] is True

    def test_storm_in_another_zone(self, world):
        _storm(world, [Z2, Z3])
        assert _details(world, PORT_A)["sea_unrest"] is False
        assert _details(world, PORT_B)["sea_unrest"] is True

    def test_non_port_with_zone_column_is_not_affected(self, world):
        # A stale port_sea_zone_id on a non-port: crud passes the zone only for ports.
        world.sql("UPDATE Locations SET port_sea_zone_id = :z WHERE id = :i", z=Z1, i=LAND2)
        _storm(world, [Z1])
        assert _details(world, LAND2)["sea_unrest"] is False
        assert _details(world, LAND)["sea_unrest"] is False

    def test_stormy_sea_zone_itself_is_not_flagged(self, world):
        _storm(world, [Z1])
        assert _details(world, Z1)["sea_unrest"] is False

    def test_port_without_zone(self, world):
        _storm(world, [Z1, Z2, Z3])
        assert _details(world, PORT_C)["sea_unrest"] is False

    def test_missing_storm_tables_false_and_one_warning(self, tmp_path, caplog):
        # Ship tables present (052 deployed), storm tables absent (053 not yet).
        w = _prepare(build_world(tmp_path / "no_storms.db"))
        with caplog.at_level(logging.WARNING, logger=sea_read.logger.name):
            data = _details(w, PORT_A)
        assert data["sea_unrest"] is False
        storm_warnings = [r for r in caplog.records
                          if r.levelno == logging.WARNING and STORM_WARNING in r.getMessage()]
        assert len(storm_warnings) == 1

    def test_missing_all_cs_tables(self, tmp_path):
        w = _prepare(build_world(tmp_path / "bare.db", with_cs_tables=False))
        data = _details(w, PORT_A)
        assert data["sea_unrest"] is False and data["docked_ships"] == []


class TestZoneInStorm:
    def test_none_and_zero_zone_skip_the_query(self, world):
        assert world.run(lambda s: sea_read.zone_in_storm(s, None)) is False
        assert world.run(lambda s: sea_read.zone_in_storm(s, 0)) is False

    def test_explicit_now_boundary(self, world):
        _storm(world, [Z1], ends_in=timedelta(hours=1))
        ends_at = sea_read._as_dt(world.sql("SELECT ends_at FROM sea_storms")[0][0])
        assert world.run(lambda s: sea_read.zone_in_storm(s, Z1, now=ends_at - timedelta(seconds=1))) is True
        assert world.run(lambda s: sea_read.zone_in_storm(s, Z1, now=ends_at)) is False
