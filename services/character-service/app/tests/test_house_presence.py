"""FEAT-180 stage 7 — where a character stands inside a house (`characters.house_room_id`).

locations-service writes the column when a character enters a house or walks
between its rooms; character-service clears it whenever the character's
location changes (an ordinary move, the admin move, a dungeon knock-out back
to town) and fills it on a home teleport (the character arrives standing in the
return circle). The location's players list tells who is inside a house of
that location — the house, never the room.

Fixtures (the shared-DB stand-ins, the locations-service mocks) come from the
admin move tests.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sa_text

import auth_http
from main import app, get_db
from tests.test_admin_move_character import (  # noqa: F401  (fixtures)
    ADMIN_USER, LOC_FROM, LOC_TO, _override, _reload, character, cleanup_mocks, db_session,
)

TOKEN = "presence-token"
HEADERS = {"X-Internal-Token": TOKEN}
ROOM = 70

_HOUSE_DDL = (
    "CREATE TABLE IF NOT EXISTS house_plots (id INTEGER PRIMARY KEY, location_id INTEGER)",
    "CREATE TABLE IF NOT EXISTS houses (id INTEGER PRIMARY KEY, plot_id INTEGER, name VARCHAR(120))",
    "CREATE TABLE IF NOT EXISTS house_rooms (id INTEGER PRIMARY KEY, house_id INTEGER, name VARCHAR(120))",
)


@pytest.fixture
def client(db_session, monkeypatch):
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
    _override(db_session, ADMIN_USER)
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def houses(db_session):
    """A house «Мельница» (room ROOM) standing in LOC_FROM, and one in LOC_TO (room ROOM + 1)."""
    for ddl in _HOUSE_DDL:
        db_session.execute(sa_text(ddl))
    db_session.execute(sa_text("INSERT INTO house_plots VALUES (1, :a), (2, :b)"), {"a": LOC_FROM, "b": LOC_TO})
    db_session.execute(sa_text("INSERT INTO houses VALUES (1, 1, 'Мельница'), (2, 2, 'Башня')"))
    db_session.execute(sa_text("INSERT INTO house_rooms (id, house_id, name) VALUES (:r, 1, 'Спальня'), (:s, 2, 'Зал')"),
                       {"r": ROOM, "s": ROOM + 1})
    db_session.commit()
    yield
    for table in ("house_rooms", "houses", "house_plots"):
        db_session.execute(sa_text(f"DROP TABLE IF EXISTS {table}"))
    db_session.commit()


def _inside(db_session, character, room=ROOM):
    character.house_room_id = room
    db_session.commit()


def test_an_ordinary_move_leaves_the_house(client, db_session, character):
    _inside(db_session, character)
    # Moving "to" the same location keeps the character where it stands.
    r = client.put(f"/characters/internal/{character.id}/update_location",
                   json={"new_location_id": LOC_FROM}, headers=HEADERS)
    assert r.status_code == 200 and _reload(db_session, character.id).house_room_id == ROOM
    r = client.put(f"/characters/internal/{character.id}/update_location",
                   json={"new_location_id": LOC_TO}, headers=HEADERS)
    assert r.status_code == 200 and _reload(db_session, character.id).house_room_id is None


def test_the_admin_move_leaves_the_house(client, db_session, character, cleanup_mocks):
    _inside(db_session, character)
    r = client.post(f"/characters/admin/{character.id}/move", json={"new_location_id": LOC_TO})
    assert r.status_code == 200, r.text
    fresh = _reload(db_session, character.id)
    assert fresh.current_location_id == LOC_TO and fresh.house_room_id is None


def test_a_home_teleport_lands_inside_the_house(client, db_session, character, cleanup_mocks):
    _inside(db_session, character)
    r = client.post(f"/characters/internal/{character.id}/home-teleport",
                    json={"location_id": LOC_TO, "house_room_id": ROOM + 1}, headers=HEADERS)
    assert r.status_code == 200, r.text
    fresh = _reload(db_session, character.id)
    assert (fresh.current_location_id, fresh.house_room_id) == (LOC_TO, ROOM + 1)
    # Without a room (an older caller) the character simply stands in the location.
    r = client.post(f"/characters/internal/{character.id}/home-teleport", json={"location_id": LOC_FROM},
                    headers=HEADERS)
    assert r.status_code == 200 and _reload(db_session, character.id).house_room_id is None


def test_a_knockout_back_to_town_leaves_the_house(client, db_session, character):
    _inside(db_session, character)
    r = client.post("/characters/internal/activity-lock/knockout",
                    json={"character_ids": [character.id], "seconds": 60, "return_location_id": LOC_FROM},
                    headers=HEADERS)
    assert r.status_code == 200 and _reload(db_session, character.id).house_room_id == ROOM  # not moved
    r = client.post("/characters/internal/activity-lock/knockout",
                    json={"character_ids": [character.id], "seconds": 60, "return_location_id": LOC_TO},
                    headers=HEADERS)
    assert r.status_code == 200 and _reload(db_session, character.id).house_room_id is None


def test_the_players_list_marks_who_is_inside_a_house(client, db_session, character, houses):
    def me():
        players = client.get(f"/characters/by_location?location_id={LOC_FROM}").json()
        return next(p for p in players if p["id"] == character.id)

    assert me()["in_house"] is None
    _inside(db_session, character)
    assert me()["in_house"] == {"house_id": 1, "house_name": "Мельница"}
    # A room of a house standing elsewhere does not count (a clear missed somewhere).
    _inside(db_session, character, ROOM + 1)
    assert me()["in_house"] is None


def test_the_players_list_works_without_house_tables(client, db_session, character):
    _inside(db_session, character)
    players = client.get(f"/characters/by_location?location_id={LOC_FROM}").json()
    assert [p["in_house"] for p in players if p["id"] == character.id] == [None]


def test_internal_short_info_tells_the_house_room(client, db_session, character, houses):
    """The header's «back to the house» link: house and room while inside, null otherwise;
    the public card never tells the room."""
    url = f"/characters/internal/{character.id}/short_info"
    assert client.get(url, headers=HEADERS).json()["current_house"] is None
    _inside(db_session, character)
    assert client.get(url, headers=HEADERS).json()["current_house"] == {
        "house_id": 1, "house_name": "Мельница", "room_id": ROOM, "room_name": "Спальня"}
    assert "current_house" not in client.get(f"/characters/{character.id}/short_info").json()
    # A room of a house in another location does not count.
    _inside(db_session, character, ROOM + 1)
    assert client.get(url, headers=HEADERS).json()["current_house"] is None
