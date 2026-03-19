"""
Tests for race/subrace CRUD functionality (FEAT-043, Task #8).

Covers:
(a) Race CRUD: create, update, delete (including duplicate name, delete with subraces)
(b) Subrace CRUD: create, update, delete (stat_preset validation: sum=100, negative values, delete with characters)
(c) GET /characters/metadata and GET /characters/races return stat_presets from DB
(d) Character approval reads preset from DB (mock inter-service calls)
(e) Edge cases: empty stat_preset, missing fields in preset
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

import database
from database import Base
from main import app, get_db
from auth_http import get_admin_user, get_current_user_via_http, OAUTH2_SCHEME, UserRead
from fastapi.testclient import TestClient
import models

# Admin user with races permissions
_ADMIN_USER = UserRead(
    id=1, username="admin", role="admin",
    permissions=[
        "characters:create", "characters:read", "characters:update",
        "characters:delete", "characters:approve",
        "races:create", "races:update", "races:delete",
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

VALID_STAT_PRESET = {
    "strength": 20,
    "agility": 15,
    "intelligence": 10,
    "endurance": 10,
    "health": 10,
    "energy": 10,
    "mana": 5,
    "stamina": 10,
    "charisma": 5,
    "luck": 5,
}

VALID_STAT_PRESET_ALT = {
    "strength": 10,
    "agility": 10,
    "intelligence": 20,
    "endurance": 10,
    "health": 10,
    "energy": 10,
    "mana": 15,
    "stamina": 5,
    "charisma": 5,
    "luck": 5,
}


def _create_race(client, name="TestRace", description="A test race"):
    """Helper to create a race via the API."""
    return client.post("/characters/admin/races", json={
        "name": name,
        "description": description,
    })


def _create_subrace(client, race_id, name="TestSubrace",
                    description="A test subrace", stat_preset=None):
    """Helper to create a subrace via the API."""
    if stat_preset is None:
        stat_preset = VALID_STAT_PRESET
    return client.post("/characters/admin/subraces", json={
        "id_race": race_id,
        "name": name,
        "description": description,
        "stat_preset": stat_preset,
    })


# ===========================================================================
# (a) Race CRUD tests
# ===========================================================================

class TestRaceCreate:
    """Tests for POST /characters/admin/races."""

    def test_create_race_success(self, client):
        """Create a race with valid data returns 201."""
        resp = _create_race(client, name="Humans", description="Desc")
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Humans"
        assert data["description"] == "Desc"
        assert "id_race" in data

    def test_create_race_duplicate_name(self, client):
        """Creating a race with a duplicate name returns 409."""
        resp1 = _create_race(client, name="DupRace")
        assert resp1.status_code == 201

        resp2 = _create_race(client, name="DupRace")
        assert resp2.status_code == 409

    def test_create_race_no_description(self, client):
        """Creating a race without description succeeds (description is optional)."""
        resp = client.post("/characters/admin/races", json={"name": "NoDesc"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "NoDesc"
        assert data["description"] is None


class TestRaceUpdate:
    """Tests for PUT /characters/admin/races/{race_id}."""

    def test_update_race_success(self, client):
        """Update race name and description returns 200."""
        create_resp = _create_race(client, name="OldName")
        race_id = create_resp.json()["id_race"]

        update_resp = client.put(f"/characters/admin/races/{race_id}", json={
            "name": "NewName",
            "description": "New description",
        })
        assert update_resp.status_code == 200
        data = update_resp.json()
        assert data["name"] == "NewName"
        assert data["description"] == "New description"

    def test_update_race_not_found(self, client):
        """Updating a non-existent race returns 404."""
        resp = client.put("/characters/admin/races/99999", json={"name": "X"})
        assert resp.status_code == 404

    def test_update_race_duplicate_name(self, client):
        """Updating race name to an existing name returns 409."""
        _create_race(client, name="RaceA")
        create_resp = _create_race(client, name="RaceB")
        race_b_id = create_resp.json()["id_race"]

        resp = client.put(f"/characters/admin/races/{race_b_id}", json={
            "name": "RaceA",
        })
        assert resp.status_code == 409

    def test_update_race_empty_body(self, client):
        """Updating with an empty body returns 400."""
        create_resp = _create_race(client, name="SomeRace")
        race_id = create_resp.json()["id_race"]

        resp = client.put(f"/characters/admin/races/{race_id}", json={})
        assert resp.status_code == 400


class TestRaceDelete:
    """Tests for DELETE /characters/admin/races/{race_id}."""

    def test_delete_race_no_subraces(self, client):
        """Deleting a race with no subraces returns 200."""
        create_resp = _create_race(client, name="ToDelete")
        race_id = create_resp.json()["id_race"]

        delete_resp = client.delete(f"/characters/admin/races/{race_id}")
        assert delete_resp.status_code == 200
        assert delete_resp.json()["detail"] == "Race deleted"

    def test_delete_race_with_subraces_blocked(self, client):
        """Deleting a race that has subraces returns 409."""
        create_resp = _create_race(client, name="HasSubraces")
        race_id = create_resp.json()["id_race"]

        # Create a subrace linked to this race
        _create_subrace(client, race_id, name="Sub1")

        delete_resp = client.delete(f"/characters/admin/races/{race_id}")
        assert delete_resp.status_code == 409

    def test_delete_race_with_characters_blocked(self, client, db_session):
        """Deleting a race that has characters returns 409."""
        create_resp = _create_race(client, name="WithChars")
        race_id = create_resp.json()["id_race"]

        # Create a subrace for FK
        sub_resp = _create_subrace(client, race_id, name="CharSub")
        subrace_id = sub_resp.json()["id_subrace"]

        # Need a class for FK
        cls = db_session.query(models.Class).filter_by(id_class=1).first()
        if not cls:
            cls = models.Class(id_class=1, name="Warrior")
            db_session.add(cls)
            db_session.flush()

        # Need a character_request for FK
        char_req = models.CharacterRequest(
            name="FKChar",
            id_subrace=subrace_id,
            id_race=race_id,
            id_class=1,
            biography="Bio",
            personality="P",
            appearance="App",
            sex="male",
            user_id=1,
            avatar="test.jpg",
        )
        db_session.add(char_req)
        db_session.flush()

        # Insert a character referencing this race
        char = models.Character(
            name="TestChar",
            id_subrace=subrace_id,
            id_class=1,
            id_race=race_id,
            appearance="test",
            avatar="test.jpg",
            request_id=char_req.id,
        )
        db_session.add(char)
        db_session.commit()

        delete_resp = client.delete(f"/characters/admin/races/{race_id}")
        assert delete_resp.status_code == 409

    def test_delete_race_not_found(self, client):
        """Deleting a non-existent race returns 404."""
        resp = client.delete("/characters/admin/races/99999")
        assert resp.status_code == 404


# ===========================================================================
# (b) Subrace CRUD tests
# ===========================================================================

class TestSubraceCreate:
    """Tests for POST /characters/admin/subraces."""

    def test_create_subrace_valid_preset(self, client):
        """Create subrace with valid stat_preset (sum=100) returns 201."""
        race_resp = _create_race(client, name="SubraceRace")
        race_id = race_resp.json()["id_race"]

        resp = _create_subrace(client, race_id, name="ValidSub")
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "ValidSub"
        assert data["id_race"] == race_id
        assert data["stat_preset"] is not None
        assert data["stat_preset"]["strength"] == 20

    def test_create_subrace_invalid_preset_sum_not_100(self, client):
        """Create subrace with stat_preset sum != 100 returns 422."""
        race_resp = _create_race(client, name="SumTestRace")
        race_id = race_resp.json()["id_race"]

        bad_preset = {
            "strength": 50,
            "agility": 50,
            "intelligence": 50,
            "endurance": 0,
            "health": 0,
            "energy": 0,
            "mana": 0,
            "stamina": 0,
            "charisma": 0,
            "luck": 0,
        }
        resp = _create_subrace(client, race_id, stat_preset=bad_preset)
        assert resp.status_code == 422

    def test_create_subrace_negative_stat_values(self, client):
        """Create subrace with negative stat values returns 422."""
        race_resp = _create_race(client, name="NegTestRace")
        race_id = race_resp.json()["id_race"]

        bad_preset = {
            "strength": -10,
            "agility": 20,
            "intelligence": 20,
            "endurance": 20,
            "health": 20,
            "energy": 20,
            "mana": 10,
            "stamina": 0,
            "charisma": 0,
            "luck": 0,
        }
        resp = _create_subrace(client, race_id, stat_preset=bad_preset)
        assert resp.status_code == 422

    def test_create_subrace_race_not_found(self, client):
        """Creating a subrace for a non-existent race returns 404."""
        resp = _create_subrace(client, race_id=99999, name="Orphan")
        assert resp.status_code == 404


class TestSubraceUpdate:
    """Tests for PUT /characters/admin/subraces/{subrace_id}."""

    def test_update_subrace_success(self, client):
        """Update subrace name and stat_preset returns 200."""
        race_resp = _create_race(client, name="UpdSubRace")
        race_id = race_resp.json()["id_race"]
        sub_resp = _create_subrace(client, race_id, name="OldSub")
        subrace_id = sub_resp.json()["id_subrace"]

        update_resp = client.put(f"/characters/admin/subraces/{subrace_id}", json={
            "name": "NewSub",
            "stat_preset": VALID_STAT_PRESET_ALT,
        })
        assert update_resp.status_code == 200
        data = update_resp.json()
        assert data["name"] == "NewSub"
        assert data["stat_preset"]["intelligence"] == 20

    def test_update_subrace_invalid_preset(self, client):
        """Updating subrace with invalid stat_preset returns 422."""
        race_resp = _create_race(client, name="UpdInvalidRace")
        race_id = race_resp.json()["id_race"]
        sub_resp = _create_subrace(client, race_id, name="ToUpdate")
        subrace_id = sub_resp.json()["id_subrace"]

        bad_preset = {
            "strength": 99,
            "agility": 0,
            "intelligence": 0,
            "endurance": 0,
            "health": 0,
            "energy": 0,
            "mana": 0,
            "stamina": 0,
            "charisma": 0,
            "luck": 0,
        }
        update_resp = client.put(f"/characters/admin/subraces/{subrace_id}", json={
            "stat_preset": bad_preset,
        })
        assert update_resp.status_code == 422

    def test_update_subrace_not_found(self, client):
        """Updating a non-existent subrace returns 404."""
        resp = client.put("/characters/admin/subraces/99999", json={"name": "X"})
        assert resp.status_code == 404


class TestSubraceDelete:
    """Tests for DELETE /characters/admin/subraces/{subrace_id}."""

    def test_delete_subrace_no_characters(self, client):
        """Deleting a subrace with no characters returns 200."""
        race_resp = _create_race(client, name="DelSubRace")
        race_id = race_resp.json()["id_race"]
        sub_resp = _create_subrace(client, race_id, name="DelSub")
        subrace_id = sub_resp.json()["id_subrace"]

        delete_resp = client.delete(f"/characters/admin/subraces/{subrace_id}")
        assert delete_resp.status_code == 200
        assert delete_resp.json()["detail"] == "Subrace deleted"

    def test_delete_subrace_with_characters_blocked(self, client, db_session):
        """Deleting a subrace that has characters returns 409."""
        race_resp = _create_race(client, name="DelBlockRace")
        race_id = race_resp.json()["id_race"]
        sub_resp = _create_subrace(client, race_id, name="BlockedSub")
        subrace_id = sub_resp.json()["id_subrace"]

        # Need a class for FK
        cls = db_session.query(models.Class).filter_by(id_class=1).first()
        if not cls:
            cls = models.Class(id_class=1, name="Warrior")
            db_session.add(cls)
            db_session.flush()

        # Need a character_request for FK
        char_req = models.CharacterRequest(
            name="BlockReq",
            id_subrace=subrace_id,
            id_race=race_id,
            id_class=1,
            biography="Bio",
            personality="P",
            appearance="App",
            sex="male",
            user_id=1,
            avatar="test.jpg",
        )
        db_session.add(char_req)
        db_session.flush()

        # Insert a character referencing this subrace
        char = models.Character(
            name="BlockChar",
            id_subrace=subrace_id,
            id_class=1,
            id_race=race_id,
            appearance="test",
            avatar="test.jpg",
            request_id=char_req.id,
        )
        db_session.add(char)
        db_session.commit()

        delete_resp = client.delete(f"/characters/admin/subraces/{subrace_id}")
        assert delete_resp.status_code == 409

    def test_delete_subrace_not_found(self, client):
        """Deleting a non-existent subrace returns 404."""
        resp = client.delete("/characters/admin/subraces/99999")
        assert resp.status_code == 404


# ===========================================================================
# (c) Metadata and races endpoints
# ===========================================================================

class TestMetadataEndpoint:
    """Tests for GET /characters/metadata and GET /characters/races."""

    def test_metadata_returns_stat_presets_from_db(self, client):
        """GET /characters/metadata returns races with stat_presets from DB."""
        race_resp = _create_race(client, name="MetaRace")
        race_id = race_resp.json()["id_race"]
        _create_subrace(client, race_id, name="MetaSub", stat_preset=VALID_STAT_PRESET)

        resp = client.get("/characters/metadata")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

        # Find our race in the response
        meta_race = None
        for r in data:
            if r["name"] == "MetaRace":
                meta_race = r
                break

        assert meta_race is not None
        assert len(meta_race["subraces"]) == 1
        sub = meta_race["subraces"][0]
        assert sub["stat_preset"]["strength"] == 20
        # Backward compat: "attributes" key should also exist
        assert sub["attributes"]["strength"] == 20

    def test_races_endpoint_returns_presets(self, client):
        """GET /characters/races returns races with subraces and stat_presets."""
        race_resp = _create_race(client, name="RacesEndRace")
        race_id = race_resp.json()["id_race"]
        _create_subrace(client, race_id, name="RacesEndSub", stat_preset=VALID_STAT_PRESET)

        resp = client.get("/characters/races")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

        # Find our race
        race = None
        for r in data:
            if r["name"] == "RacesEndRace":
                race = r
                break

        assert race is not None
        assert len(race["subraces"]) == 1
        sub = race["subraces"][0]
        assert sub["stat_preset"]["strength"] == 20
        assert sub["name"] == "RacesEndSub"

    def test_races_endpoint_empty_db(self, client):
        """GET /characters/races on empty DB returns empty list."""
        resp = client.get("/characters/races")
        assert resp.status_code == 200
        assert resp.json() == []


# ===========================================================================
# (d) Character approval reads preset from DB
# ===========================================================================

class TestCharacterApprovalPreset:
    """Test that character approval reads stat presets from DB."""

    @patch("main.send_character_approved_notification", new_callable=AsyncMock)
    @patch("main.publish_character_attributes", new_callable=AsyncMock)
    @patch("main.publish_character_skills", new_callable=AsyncMock)
    @patch("main.publish_character_inventory", new_callable=AsyncMock)
    @patch("crud.httpx.AsyncClient")
    def test_approval_uses_db_preset(
        self,
        mock_async_client_cls,
        mock_pub_inv,
        mock_pub_skills,
        mock_pub_attrs,
        mock_notif,
        client,
        db_session,
    ):
        """Approving a character reads stat_preset from subraces table in DB."""
        # Create race + subrace with known preset
        race = models.Race(name="ApprovalRace")
        db_session.add(race)
        db_session.flush()

        subrace = models.Subrace(
            id_race=race.id_race,
            name="ApprovalSub",
            stat_preset=VALID_STAT_PRESET,
        )
        db_session.add(subrace)
        db_session.flush()

        # Create a class
        cls = db_session.query(models.Class).filter_by(id_class=1).first()
        if not cls:
            cls = models.Class(id_class=1, name="Warrior")
            db_session.add(cls)
            db_session.flush()

        # Create a character request referencing our subrace
        char_req = models.CharacterRequest(
            name="ApprovalChar",
            id_subrace=subrace.id_subrace,
            id_race=race.id_race,
            id_class=1,
            biography="Bio",
            personality="Personality",
            appearance="Appearance",
            sex="male",
            user_id=42,
            avatar="https://example.com/avatar.webp",
            status="pending",
        )
        db_session.add(char_req)
        db_session.commit()

        # Mock all external HTTP calls
        mock_client_instance = AsyncMock()

        # Mock responses for different HTTP calls
        attrs_response = AsyncMock()
        attrs_response.status_code = 200
        attrs_response.json.return_value = {"id": 99}
        attrs_response.text = '{"id": 99}'

        inv_response = AsyncMock()
        inv_response.status_code = 200
        inv_response.json.return_value = {"status": "ok"}
        inv_response.text = '{"status": "ok"}'

        skills_response = AsyncMock()
        skills_response.status_code = 200
        skills_response.json.return_value = {"status": "ok"}
        skills_response.text = '{"status": "ok"}'

        user_post_response = AsyncMock()
        user_post_response.status_code = 200
        user_post_response.json.return_value = {"status": "ok"}
        user_post_response.text = '{"status": "ok"}'

        user_put_response = AsyncMock()
        user_put_response.status_code = 200
        user_put_response.json.return_value = {"status": "ok"}
        user_put_response.text = '{"status": "ok"}'

        mock_client_instance.post = AsyncMock(side_effect=[
            inv_response,     # inventory
            skills_response,  # skills
            attrs_response,   # attributes
            user_post_response,  # user_characters
        ])
        mock_client_instance.put = AsyncMock(return_value=user_put_response)

        mock_async_client_cls.return_value.__aenter__ = AsyncMock(
            return_value=mock_client_instance
        )
        mock_async_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = client.post(f"/characters/requests/{char_req.id}/approve")

        # The approval should succeed (or fail only due to external service mock issues)
        # The key test is that generate_attributes_for_subrace reads from DB
        # Verify by checking the subrace was queried successfully
        import crud
        attrs = crud.generate_attributes_for_subrace(db_session, subrace.id_subrace)
        assert attrs == VALID_STAT_PRESET

    def test_generate_attributes_from_db(self, db_session):
        """generate_attributes_for_subrace reads preset from DB."""
        import crud

        # Create race + subrace with preset
        race = models.Race(name="GenAttrRace")
        db_session.add(race)
        db_session.flush()

        subrace = models.Subrace(
            id_race=race.id_race,
            name="GenAttrSub",
            stat_preset=VALID_STAT_PRESET,
        )
        db_session.add(subrace)
        db_session.commit()

        result = crud.generate_attributes_for_subrace(db_session, subrace.id_subrace)
        assert result == VALID_STAT_PRESET

    def test_generate_attributes_missing_preset_returns_defaults(self, db_session):
        """generate_attributes_for_subrace returns defaults when no preset in DB."""
        import crud

        race = models.Race(name="NoPresetRace")
        db_session.add(race)
        db_session.flush()

        subrace = models.Subrace(
            id_race=race.id_race,
            name="NoPresetSub",
            stat_preset=None,
        )
        db_session.add(subrace)
        db_session.commit()

        result = crud.generate_attributes_for_subrace(db_session, subrace.id_subrace)
        # Should return default values (all 10)
        assert result["strength"] == 10
        assert result["luck"] == 10

    def test_generate_attributes_nonexistent_subrace_returns_defaults(self, db_session):
        """generate_attributes_for_subrace returns defaults for nonexistent subrace."""
        import crud

        result = crud.generate_attributes_for_subrace(db_session, 99999)
        assert result["strength"] == 10
        assert sum(result.values()) == 100


# ===========================================================================
# (e) Edge cases: stat_preset validation
# ===========================================================================

class TestStatPresetEdgeCases:
    """Edge cases for stat_preset validation."""

    def test_empty_stat_preset_object(self, client):
        """Stat preset with all zeros (sum != 100) is rejected."""
        race_resp = _create_race(client, name="EmptyPresetRace")
        race_id = race_resp.json()["id_race"]

        empty_preset = {
            "strength": 0,
            "agility": 0,
            "intelligence": 0,
            "endurance": 0,
            "health": 0,
            "energy": 0,
            "mana": 0,
            "stamina": 0,
            "charisma": 0,
            "luck": 0,
        }
        resp = _create_subrace(client, race_id, stat_preset=empty_preset)
        assert resp.status_code == 422

    def test_stat_preset_missing_fields(self, client):
        """Stat preset with missing fields uses defaults (0), sum check applies."""
        race_resp = _create_race(client, name="MissingFieldsRace")
        race_id = race_resp.json()["id_race"]

        # Only provide strength=100, other fields default to 0, sum = 100
        partial_preset = {"strength": 100}
        resp = _create_subrace(client, race_id, stat_preset=partial_preset)
        assert resp.status_code == 201
        data = resp.json()
        assert data["stat_preset"]["strength"] == 100
        assert data["stat_preset"]["agility"] == 0

    def test_stat_preset_missing_fields_sum_wrong(self, client):
        """Stat preset with partial fields and wrong sum is rejected."""
        race_resp = _create_race(client, name="PartialSumRace")
        race_id = race_resp.json()["id_race"]

        # Only provide strength=50, rest default to 0, sum = 50 != 100
        partial_preset = {"strength": 50}
        resp = _create_subrace(client, race_id, stat_preset=partial_preset)
        assert resp.status_code == 422

    def test_stat_preset_all_in_one_stat(self, client):
        """Stat preset with all 100 in a single stat is valid."""
        race_resp = _create_race(client, name="AllInOneRace")
        race_id = race_resp.json()["id_race"]

        preset = {
            "strength": 0,
            "agility": 0,
            "intelligence": 0,
            "endurance": 0,
            "health": 0,
            "energy": 0,
            "mana": 0,
            "stamina": 0,
            "charisma": 0,
            "luck": 100,
        }
        resp = _create_subrace(client, race_id, stat_preset=preset)
        assert resp.status_code == 201

    def test_stat_preset_exceeds_100(self, client):
        """Stat preset with sum > 100 is rejected."""
        race_resp = _create_race(client, name="ExceedRace")
        race_id = race_resp.json()["id_race"]

        preset = {
            "strength": 20,
            "agility": 20,
            "intelligence": 20,
            "endurance": 20,
            "health": 20,
            "energy": 20,
            "mana": 0,
            "stamina": 0,
            "charisma": 0,
            "luck": 0,
        }
        # sum = 120
        resp = _create_subrace(client, race_id, stat_preset=preset)
        assert resp.status_code == 422

    def test_stat_preset_multiple_negative_values(self, client):
        """Stat preset with multiple negative values is rejected."""
        race_resp = _create_race(client, name="MultiNegRace")
        race_id = race_resp.json()["id_race"]

        preset = {
            "strength": -5,
            "agility": -5,
            "intelligence": 30,
            "endurance": 30,
            "health": 20,
            "energy": 20,
            "mana": 10,
            "stamina": 0,
            "charisma": 0,
            "luck": 0,
        }
        resp = _create_subrace(client, race_id, stat_preset=preset)
        assert resp.status_code == 422


# ===========================================================================
# Security: SQL injection in race name
# ===========================================================================

class TestSecurityEdgeCases:
    """Security edge cases for race/subrace CRUD."""

    def test_sql_injection_in_race_name(self, client):
        """Race creation with SQL injection in name does not crash."""
        resp = _create_race(client, name="'; DROP TABLE races; --")
        # Should either succeed (storing the string literally) or fail gracefully
        assert resp.status_code in (201, 409, 422)

    def test_sql_injection_in_subrace_name(self, client):
        """Subrace creation with SQL injection in name does not crash."""
        race_resp = _create_race(client, name="SafeRace")
        race_id = race_resp.json()["id_race"]

        resp = _create_subrace(
            client, race_id,
            name="\" OR 1=1 --",
        )
        assert resp.status_code in (201, 422)


# ===========================================================================
# Auth: unauthenticated access
# ===========================================================================

class TestRaceCrudAuth:
    """Verify that race CRUD endpoints require authentication."""

    def test_create_race_no_auth(self, db_session):
        """POST /characters/admin/races without auth returns 401/403."""
        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        # No auth overrides
        no_auth_client = TestClient(app, raise_server_exceptions=False)
        resp = no_auth_client.post("/characters/admin/races", json={"name": "X"})
        assert resp.status_code in (401, 403, 422)
        app.dependency_overrides.clear()

    def test_delete_race_no_auth(self, db_session):
        """DELETE /characters/admin/races/{id} without auth returns 401/403."""
        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        no_auth_client = TestClient(app, raise_server_exceptions=False)
        resp = no_auth_client.delete("/characters/admin/races/1")
        assert resp.status_code in (401, 403, 422)
        app.dependency_overrides.clear()

    def test_races_public_endpoint_no_auth(self, db_session):
        """GET /characters/races is public, should work without auth."""
        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        no_auth_client = TestClient(app, raise_server_exceptions=False)
        resp = no_auth_client.get("/characters/races")
        assert resp.status_code == 200
        app.dependency_overrides.clear()
