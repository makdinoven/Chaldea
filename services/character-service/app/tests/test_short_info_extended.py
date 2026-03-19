"""
Tests for extended GET /characters/{id}/short_info endpoint (FEAT-044, Task #12).

Covers:
(a) New fields present: id_race, id_class, id_subrace, race_name, class_name, subrace_name
(b) Backward compatibility: existing fields (id, name, avatar, level, current_location_id) still present
(c) Edge cases: character with null race/class/subrace, character with race but no subrace
(d) Character not found returns 404
(e) Security: SQL-injection-style character ID does not crash
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import database
from database import Base
from main import app, get_db
from auth_http import get_admin_user, get_current_user_via_http, OAUTH2_SCHEME, UserRead
from fastapi.testclient import TestClient
import models


# Admin user for auth override
_ADMIN_USER = UserRead(
    id=1, username="admin", role="admin",
    permissions=[
        "characters:create", "characters:read", "characters:update",
        "characters:delete", "characters:approve",
    ],
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """Create fresh tables for every test, yield a session, then tear down."""
    Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=database.engine)


@pytest.fixture
def client(db_session):
    """FastAPI TestClient wired to the real SQLite test session with admin auth."""

    def override_get_db():
        yield db_session

    def override_admin():
        return _ADMIN_USER

    def override_token():
        return "fake-admin-token"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = override_admin
    app.dependency_overrides[get_current_user_via_http] = override_admin
    app.dependency_overrides[OAUTH2_SCHEME] = override_token
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_race_class_subrace(session, *, race_name="Эльф", class_name="Воин",
                              subrace_name="Высший эльф"):
    """Insert a race, class, and subrace. Return (race, cls, subrace) ORM objects."""
    race = models.Race(name=race_name)
    session.add(race)
    session.flush()

    cls = models.Class(name=class_name)
    session.add(cls)
    session.flush()

    subrace = models.Subrace(id_race=race.id_race, name=subrace_name)
    session.add(subrace)
    session.flush()

    return race, cls, subrace


def _create_character(session, *, name="TestChar", race=None, cls=None,
                      subrace=None, level=5, avatar="avatar.webp",
                      current_location_id=None):
    """Insert a character with a required character_request. Return Character ORM object."""
    id_race = race.id_race if race else 0
    id_class = cls.id_class if cls else 0
    id_subrace = subrace.id_subrace if subrace else 0

    # CharacterRequest is required by FK constraint on Character.request_id
    char_req = models.CharacterRequest(
        name=name,
        id_subrace=id_subrace,
        id_race=id_race if id_race else 1,
        id_class=id_class if id_class else 1,
        biography="Bio",
        personality="Personality",
        appearance="Appearance",
        sex="male",
        user_id=1,
        avatar=avatar,
    )
    session.add(char_req)
    session.flush()

    char = models.Character(
        name=name,
        id_subrace=id_subrace,
        id_class=id_class,
        id_race=id_race,
        appearance="Appearance",
        avatar=avatar,
        request_id=char_req.id,
        level=level,
        current_location_id=current_location_id,
    )
    session.add(char)
    session.commit()
    return char


# ===========================================================================
# (a) New fields present in short_info response
# ===========================================================================

class TestShortInfoNewFields:
    """Verify new race/class/subrace fields are returned."""

    def test_short_info_returns_race_fields(self, client, db_session):
        """Response includes id_race and race_name."""
        race, cls, subrace = _seed_race_class_subrace(db_session)
        char = _create_character(db_session, race=race, cls=cls, subrace=subrace)

        resp = client.get(f"/characters/{char.id}/short_info")
        assert resp.status_code == 200
        data = resp.json()

        assert data["id_race"] == race.id_race
        assert data["race_name"] == "Эльф"

    def test_short_info_returns_class_fields(self, client, db_session):
        """Response includes id_class and class_name."""
        race, cls, subrace = _seed_race_class_subrace(db_session)
        char = _create_character(db_session, race=race, cls=cls, subrace=subrace)

        resp = client.get(f"/characters/{char.id}/short_info")
        assert resp.status_code == 200
        data = resp.json()

        assert data["id_class"] == cls.id_class
        assert data["class_name"] == "Воин"

    def test_short_info_returns_subrace_fields(self, client, db_session):
        """Response includes id_subrace and subrace_name."""
        race, cls, subrace = _seed_race_class_subrace(db_session)
        char = _create_character(db_session, race=race, cls=cls, subrace=subrace)

        resp = client.get(f"/characters/{char.id}/short_info")
        assert resp.status_code == 200
        data = resp.json()

        assert data["id_subrace"] == subrace.id_subrace
        assert data["subrace_name"] == "Высший эльф"

    def test_short_info_all_new_fields_present(self, client, db_session):
        """All six new fields are present in a single response."""
        race, cls, subrace = _seed_race_class_subrace(db_session)
        char = _create_character(db_session, race=race, cls=cls, subrace=subrace)

        resp = client.get(f"/characters/{char.id}/short_info")
        assert resp.status_code == 200
        data = resp.json()

        new_fields = ["id_race", "id_class", "id_subrace",
                      "race_name", "class_name", "subrace_name"]
        for field in new_fields:
            assert field in data, f"Missing field: {field}"


# ===========================================================================
# (b) Backward compatibility — existing fields still present
# ===========================================================================

class TestShortInfoBackwardCompatibility:
    """Existing fields must still be present and correct."""

    def test_existing_fields_present(self, client, db_session):
        """Fields id, name, avatar, level, current_location_id are still returned."""
        race, cls, subrace = _seed_race_class_subrace(db_session)
        char = _create_character(
            db_session, name="Артория", race=race, cls=cls, subrace=subrace,
            level=10, avatar="artoria.webp", current_location_id=42,
        )

        resp = client.get(f"/characters/{char.id}/short_info")
        assert resp.status_code == 200
        data = resp.json()

        assert data["id"] == char.id
        assert data["name"] == "Артория"
        assert data["avatar"] == "artoria.webp"
        assert data["level"] == 10
        assert data["current_location_id"] == 42

    def test_existing_fields_with_null_location(self, client, db_session):
        """current_location_id can be null."""
        race, cls, subrace = _seed_race_class_subrace(db_session)
        char = _create_character(
            db_session, race=race, cls=cls, subrace=subrace,
            current_location_id=None,
        )

        resp = client.get(f"/characters/{char.id}/short_info")
        assert resp.status_code == 200
        data = resp.json()

        assert data["current_location_id"] is None


# ===========================================================================
# (c) Edge cases: null race/class/subrace
# ===========================================================================

class TestShortInfoEdgeCases:
    """Edge cases for characters with missing race/class/subrace references."""

    def test_character_with_nonexistent_race(self, client, db_session):
        """Character whose id_race has no matching row — race_name should be null."""
        # Create a class but no race in the DB
        cls = models.Class(name="Маг")
        db_session.add(cls)
        db_session.flush()

        # Create character_request with dummy FK values
        char_req = models.CharacterRequest(
            name="OrphanChar", id_subrace=0, id_race=9999,
            id_class=cls.id_class, biography="Bio", personality="P",
            appearance="App", sex="male", user_id=1, avatar="a.webp",
        )
        db_session.add(char_req)
        db_session.flush()

        char = models.Character(
            name="OrphanChar", id_subrace=0, id_class=cls.id_class,
            id_race=9999, appearance="App", avatar="a.webp",
            request_id=char_req.id, level=1,
        )
        db_session.add(char)
        db_session.commit()

        resp = client.get(f"/characters/{char.id}/short_info")
        assert resp.status_code == 200
        data = resp.json()

        # race_name should be null since race 9999 doesn't exist
        assert data["id_race"] == 9999
        assert data["race_name"] is None

    def test_character_with_nonexistent_class(self, client, db_session):
        """Character whose id_class has no matching row — class_name should be null."""
        race = models.Race(name="Человек")
        db_session.add(race)
        db_session.flush()

        char_req = models.CharacterRequest(
            name="NoClassChar", id_subrace=0, id_race=race.id_race,
            id_class=8888, biography="Bio", personality="P",
            appearance="App", sex="male", user_id=1, avatar="a.webp",
        )
        db_session.add(char_req)
        db_session.flush()

        char = models.Character(
            name="NoClassChar", id_subrace=0, id_class=8888,
            id_race=race.id_race, appearance="App", avatar="a.webp",
            request_id=char_req.id, level=1,
        )
        db_session.add(char)
        db_session.commit()

        resp = client.get(f"/characters/{char.id}/short_info")
        assert resp.status_code == 200
        data = resp.json()

        assert data["id_class"] == 8888
        assert data["class_name"] is None

    def test_character_with_race_but_no_subrace(self, client, db_session):
        """Character with valid race but id_subrace=0 (no subrace) — subrace_name null."""
        race = models.Race(name="Драконид")
        db_session.add(race)
        db_session.flush()

        cls = models.Class(name="Плут")
        db_session.add(cls)
        db_session.flush()

        char_req = models.CharacterRequest(
            name="NoSubraceChar", id_subrace=0, id_race=race.id_race,
            id_class=cls.id_class, biography="Bio", personality="P",
            appearance="App", sex="male", user_id=1, avatar="a.webp",
        )
        db_session.add(char_req)
        db_session.flush()

        char = models.Character(
            name="NoSubraceChar", id_subrace=0, id_class=cls.id_class,
            id_race=race.id_race, appearance="App", avatar="a.webp",
            request_id=char_req.id, level=3,
        )
        db_session.add(char)
        db_session.commit()

        resp = client.get(f"/characters/{char.id}/short_info")
        assert resp.status_code == 200
        data = resp.json()

        assert data["race_name"] == "Драконид"
        assert data["class_name"] == "Плут"
        assert data["id_subrace"] == 0
        assert data["subrace_name"] is None

    def test_character_with_all_null_references(self, client, db_session):
        """Character with id_race=0, id_class=0, id_subrace=0 — all names should be null."""
        char_req = models.CharacterRequest(
            name="NullRefChar", id_subrace=0, id_race=1,
            id_class=1, biography="Bio", personality="P",
            appearance="App", sex="male", user_id=1, avatar="a.webp",
        )
        db_session.add(char_req)
        db_session.flush()

        char = models.Character(
            name="NullRefChar", id_subrace=0, id_class=0,
            id_race=0, appearance="App", avatar="a.webp",
            request_id=char_req.id, level=1,
        )
        db_session.add(char)
        db_session.commit()

        resp = client.get(f"/characters/{char.id}/short_info")
        assert resp.status_code == 200
        data = resp.json()

        assert data["race_name"] is None
        assert data["class_name"] is None
        assert data["subrace_name"] is None


# ===========================================================================
# (d) Character not found
# ===========================================================================

class TestShortInfoNotFound:
    """GET /characters/{id}/short_info for non-existent character."""

    def test_nonexistent_character_returns_404(self, client, db_session):
        """Requesting short_info for a non-existent ID returns 404."""
        resp = client.get("/characters/99999/short_info")
        assert resp.status_code == 404


# ===========================================================================
# (e) Security: non-integer ID does not crash
# ===========================================================================

class TestShortInfoSecurity:
    """Security edge cases for the short_info endpoint."""

    def test_sql_injection_in_character_id(self, client, db_session):
        """SQL injection attempt in character_id returns 422 (validation error), not 500."""
        resp = client.get("/characters/1;DROP TABLE characters/short_info")
        # FastAPI path param validation should reject non-integer
        assert resp.status_code == 422 or resp.status_code == 404

    def test_negative_character_id(self, client, db_session):
        """Negative character ID returns 404 (not found), not 500."""
        resp = client.get("/characters/-1/short_info")
        assert resp.status_code in (404, 422)

    def test_zero_character_id(self, client, db_session):
        """Character ID 0 returns 404."""
        resp = client.get("/characters/0/short_info")
        assert resp.status_code == 404
