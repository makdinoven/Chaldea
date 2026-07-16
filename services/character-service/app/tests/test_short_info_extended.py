"""
Tests for extended GET /characters/{id}/short_info endpoint (FEAT-044, Task #12).

Covers:
(a) New fields present: id_race, id_class, id_subrace, race_name, class_name, subrace_name
(b) Backward compatibility: existing fields (id, name, avatar, level, current_location_id) still present
(c) Edge cases: character with race but no subrace
(d) Character not found returns 404
(e) Security: non-integer character ID does not crash
(f) FEAT-148: currency_balance is exposed with the character's value
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

def _seed_reference_data(session):
    """Insert races, classes, subraces needed for FK constraints."""
    race = models.Race(name="Эльф")
    session.add(race)
    session.flush()

    cls = models.Class(name="Воин")
    session.add(cls)
    session.flush()

    subrace = models.Subrace(id_race=race.id_race, name="Высший эльф")
    session.add(subrace)
    session.flush()

    return race, cls, subrace


def _create_character(session, *, name="TestChar", race=None, cls=None,
                      subrace=None, level=5, avatar="avatar.webp",
                      current_location_id=None, currency_balance=None):
    """Insert a character with a required character_request. Return Character ORM object."""
    char_req = models.CharacterRequest(
        name=name,
        id_subrace=subrace.id_subrace if subrace else None,
        id_race=race.id_race,
        id_class=cls.id_class,
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
        id_subrace=subrace.id_subrace if subrace else 0,
        id_class=cls.id_class,
        id_race=race.id_race,
        appearance="Appearance",
        avatar=avatar,
        request_id=char_req.id,
        level=level,
        current_location_id=current_location_id,
    )
    if currency_balance is not None:
        char.currency_balance = currency_balance
    session.add(char)
    session.commit()
    return char


# ===========================================================================
# (a) New fields present in short_info response
# ===========================================================================

class TestShortInfoNewFields:
    """Verify new race/class/subrace fields are returned."""

    def test_short_info_returns_race_fields(self, client, db_session):
        race, cls, subrace = _seed_reference_data(db_session)
        char = _create_character(db_session, race=race, cls=cls, subrace=subrace)

        resp = client.get(f"/characters/{char.id}/short_info")
        assert resp.status_code == 200
        data = resp.json()

        assert data["id_race"] == race.id_race
        assert data["race_name"] == "Эльф"

    def test_short_info_returns_class_fields(self, client, db_session):
        race, cls, subrace = _seed_reference_data(db_session)
        char = _create_character(db_session, race=race, cls=cls, subrace=subrace)

        resp = client.get(f"/characters/{char.id}/short_info")
        assert resp.status_code == 200
        data = resp.json()

        assert data["id_class"] == cls.id_class
        assert data["class_name"] == "Воин"

    def test_short_info_returns_subrace_fields(self, client, db_session):
        race, cls, subrace = _seed_reference_data(db_session)
        char = _create_character(db_session, race=race, cls=cls, subrace=subrace)

        resp = client.get(f"/characters/{char.id}/short_info")
        assert resp.status_code == 200
        data = resp.json()

        assert data["id_subrace"] == subrace.id_subrace
        assert data["subrace_name"] == "Высший эльф"

    def test_short_info_all_new_fields_present(self, client, db_session):
        race, cls, subrace = _seed_reference_data(db_session)
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

    def test_existing_fields_present(self, client, db_session):
        race, cls, subrace = _seed_reference_data(db_session)
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
        race, cls, subrace = _seed_reference_data(db_session)
        char = _create_character(
            db_session, race=race, cls=cls, subrace=subrace,
            current_location_id=None,
        )

        resp = client.get(f"/characters/{char.id}/short_info")
        assert resp.status_code == 200
        assert resp.json()["current_location_id"] is None


# ===========================================================================
# (c) Edge cases
# ===========================================================================

class TestShortInfoEdgeCases:

    def test_character_with_race_but_no_subrace(self, client, db_session):
        """Character with valid race/class but id_subrace=0 — subrace_name should be null."""
        race, cls, _ = _seed_reference_data(db_session)
        # Create without subrace
        char = _create_character(db_session, race=race, cls=cls, subrace=None)

        resp = client.get(f"/characters/{char.id}/short_info")
        assert resp.status_code == 200
        data = resp.json()

        assert data["race_name"] == "Эльф"
        assert data["class_name"] == "Воин"
        assert data["subrace_name"] is None


# ===========================================================================
# (f) FEAT-148 — currency_balance exposed in short_info
# ===========================================================================

class TestShortInfoCurrencyBalance:
    """FEAT-148: short_info must include the character's currency_balance."""

    def test_currency_balance_returned_with_character_value(self, client, db_session):
        race, cls, subrace = _seed_reference_data(db_session)
        char = _create_character(
            db_session, race=race, cls=cls, subrace=subrace,
            currency_balance=1500,
        )

        resp = client.get(f"/characters/{char.id}/short_info")
        assert resp.status_code == 200
        data = resp.json()

        assert "currency_balance" in data
        assert data["currency_balance"] == 1500

    def test_currency_balance_defaults_to_zero(self, client, db_session):
        """Character created without explicit gold — model default is 0."""
        race, cls, subrace = _seed_reference_data(db_session)
        char = _create_character(db_session, race=race, cls=cls, subrace=subrace)

        resp = client.get(f"/characters/{char.id}/short_info")
        assert resp.status_code == 200
        assert resp.json()["currency_balance"] == 0

    def test_currency_balance_additive_existing_keys_untouched(self, client, db_session):
        """Adding currency_balance must not remove any previously exposed key."""
        race, cls, subrace = _seed_reference_data(db_session)
        char = _create_character(
            db_session, race=race, cls=cls, subrace=subrace,
            currency_balance=42,
        )

        resp = client.get(f"/characters/{char.id}/short_info")
        assert resp.status_code == 200
        data = resp.json()

        expected_keys = [
            "id", "name", "avatar", "level", "current_location_id",
            "id_race", "id_class", "id_subrace",
            "race_name", "class_name", "subrace_name",
            "currency_balance",
        ]
        for key in expected_keys:
            assert key in data, f"Missing field: {key}"


# ===========================================================================
# (d) Character not found
# ===========================================================================

class TestShortInfoNotFound:

    def test_nonexistent_character_returns_404(self, client, db_session):
        resp = client.get("/characters/99999/short_info")
        assert resp.status_code == 404


# ===========================================================================
# (e) Security: non-integer ID does not crash
# ===========================================================================

class TestShortInfoSecurity:

    def test_sql_injection_in_character_id(self, client, db_session):
        resp = client.get("/characters/1;DROP TABLE characters/short_info")
        assert resp.status_code == 422 or resp.status_code == 404

    def test_negative_character_id(self, client, db_session):
        resp = client.get("/characters/-1/short_info")
        assert resp.status_code in (404, 422)

    def test_zero_character_id(self, client, db_session):
        resp = client.get("/characters/0/short_info")
        assert resp.status_code == 404
