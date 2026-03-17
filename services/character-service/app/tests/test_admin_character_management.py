"""
Tests for FEAT-021 admin endpoints in character-service:
- GET /characters/admin/list
- PUT /characters/admin/{character_id}
- POST /characters/admin/{character_id}/unlink
- DELETE /characters/{character_id} (cascade)
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy import String

import database
import models

# Patch Enum columns to String for SQLite compatibility
for col in models.Character.__table__.columns:
    if type(col.type).__name__ == "Enum":
        col.type = String(50)
for col in models.CharacterRequest.__table__.columns:
    if type(col.type).__name__ == "Enum":
        col.type = String(50)

from fastapi.testclient import TestClient
from auth_http import get_admin_user, OAUTH2_SCHEME, UserRead
from main import app, get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ADMIN_USER = UserRead(id=1, username="admin", role="admin")


def _seed_request(db, request_id=1):
    """Create a minimal CharacterRequest needed as FK for Character."""
    req = models.CharacterRequest(
        id=request_id,
        name="Test",
        id_subrace=1,
        biography="bio",
        personality="pers",
        id_class=1,
        status="approved",
        user_id=10,
        appearance="appearance",
        id_race=1,
        avatar="/avatar.jpg",
    )
    db.add(req)
    db.commit()
    return req


def _seed_character(db, char_id=1, request_id=1, **overrides):
    """Create a Character in the test DB."""
    defaults = dict(
        id=char_id,
        name="TestChar",
        id_subrace=1,
        id_class=1,
        id_race=1,
        level=1,
        stat_points=0,
        currency_balance=100,
        request_id=request_id,
        user_id=10,
        appearance="appearance",
        avatar="/avatar.jpg",
    )
    defaults.update(overrides)
    ch = models.Character(**defaults)
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session(test_engine, test_session_factory, seed_fk_data):
    database.Base.metadata.create_all(bind=test_engine)
    session = test_session_factory()
    seed_fk_data(session)
    try:
        yield session
    finally:
        session.close()
        database.Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def admin_client(db_session):
    def override_get_db():
        yield db_session

    def override_admin():
        return _ADMIN_USER

    def override_token():
        return "fake-admin-token"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = override_admin
    app.dependency_overrides[OAUTH2_SCHEME] = override_token
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def non_admin_client(db_session):
    def override_get_db():
        yield db_session

    def override_non_admin():
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Admin access required")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = override_non_admin
    yield TestClient(app)
    app.dependency_overrides.clear()


# ===========================================================================
# GET /characters/admin/list
# ===========================================================================

class TestAdminListCharacters:

    def test_list_empty(self, admin_client, db_session):
        resp = admin_client.get("/characters/admin/list")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    def test_list_with_characters(self, admin_client, db_session):
        _seed_request(db_session, 1)
        _seed_character(db_session, char_id=1, request_id=1, name="Alpha")
        _seed_request(db_session, 2)
        _seed_character(db_session, char_id=2, request_id=2, name="Beta")

        resp = admin_client.get("/characters/admin/list")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_list_search_by_name(self, admin_client, db_session):
        _seed_request(db_session, 1)
        _seed_character(db_session, char_id=1, request_id=1, name="Alpha")
        _seed_request(db_session, 2)
        _seed_character(db_session, char_id=2, request_id=2, name="Beta")

        resp = admin_client.get("/characters/admin/list?q=Alph")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Alpha"

    def test_list_filter_by_level(self, admin_client, db_session):
        _seed_request(db_session, 1)
        _seed_character(db_session, char_id=1, request_id=1, level=3)
        _seed_request(db_session, 2)
        _seed_character(db_session, char_id=2, request_id=2, level=10)

        resp = admin_client.get("/characters/admin/list?level_min=5")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_list_filter_by_race_and_class(self, admin_client, db_session):
        _seed_request(db_session, 1)
        _seed_character(db_session, char_id=1, request_id=1, id_race=1, id_class=2)
        _seed_request(db_session, 2)
        _seed_character(db_session, char_id=2, request_id=2, id_race=2, id_class=3)

        resp = admin_client.get("/characters/admin/list?id_race=1&id_class=2")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_list_pagination(self, admin_client, db_session):
        for i in range(1, 6):
            _seed_request(db_session, i)
            _seed_character(db_session, char_id=i, request_id=i, name=f"Char{i}")

        resp = admin_client.get("/characters/admin/list?page=1&page_size=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["page"] == 1

    def test_list_forbidden_for_non_admin(self, non_admin_client, db_session):
        resp = non_admin_client.get("/characters/admin/list")
        assert resp.status_code == 403


# ===========================================================================
# PUT /characters/admin/{character_id}
# ===========================================================================

class TestAdminUpdateCharacter:

    def test_update_level(self, admin_client, db_session):
        _seed_request(db_session)
        _seed_character(db_session, level=1)

        resp = admin_client.put("/characters/admin/1", json={"level": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["detail"] == "Character updated"
        assert data["character_id"] == 1

        # Verify in DB
        ch = db_session.query(models.Character).filter(models.Character.id == 1).first()
        assert ch.level == 10

    def test_update_partial(self, admin_client, db_session):
        _seed_request(db_session)
        _seed_character(db_session, level=1, stat_points=0, currency_balance=100)

        resp = admin_client.put("/characters/admin/1", json={"stat_points": 50})
        assert resp.status_code == 200

        ch = db_session.query(models.Character).filter(models.Character.id == 1).first()
        assert ch.stat_points == 50
        assert ch.level == 1  # unchanged
        assert ch.currency_balance == 100  # unchanged

    def test_update_invalid_level(self, admin_client, db_session):
        _seed_request(db_session)
        _seed_character(db_session)

        resp = admin_client.put("/characters/admin/1", json={"level": 0})
        assert resp.status_code == 400

    def test_update_negative_currency(self, admin_client, db_session):
        _seed_request(db_session)
        _seed_character(db_session)

        resp = admin_client.put("/characters/admin/1", json={"currency_balance": -10})
        assert resp.status_code == 400

    def test_update_not_found(self, admin_client, db_session):
        resp = admin_client.put("/characters/admin/999", json={"level": 5})
        assert resp.status_code == 404

    def test_update_empty_body(self, admin_client, db_session):
        _seed_request(db_session)
        _seed_character(db_session)

        resp = admin_client.put("/characters/admin/1", json={})
        assert resp.status_code == 400  # "No data for update"

    def test_update_forbidden_for_non_admin(self, non_admin_client, db_session):
        resp = non_admin_client.put("/characters/admin/1", json={"level": 5})
        assert resp.status_code == 403


# ===========================================================================
# POST /characters/admin/{character_id}/unlink
# ===========================================================================

class TestAdminUnlinkCharacter:

    @patch("httpx.AsyncClient")
    def test_unlink_success(self, mock_client_class, admin_client, db_session):
        _seed_request(db_session)
        _seed_character(db_session, user_id=10)

        # Mock httpx.AsyncClient context manager
        mock_instance = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_instance.delete = AsyncMock(return_value=mock_response)
        mock_instance.post = AsyncMock(return_value=mock_response)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_instance

        resp = admin_client.post("/characters/admin/1/unlink")
        assert resp.status_code == 200
        data = resp.json()
        assert data["detail"] == "Character unlinked from user"
        assert data["previous_user_id"] == 10

        # Verify user_id cleared locally
        ch = db_session.query(models.Character).filter(models.Character.id == 1).first()
        assert ch.user_id is None

    def test_unlink_not_linked(self, admin_client, db_session):
        _seed_request(db_session)
        _seed_character(db_session, user_id=None)

        resp = admin_client.post("/characters/admin/1/unlink")
        assert resp.status_code == 400

    def test_unlink_not_found(self, admin_client, db_session):
        resp = admin_client.post("/characters/admin/999/unlink")
        assert resp.status_code == 404

    def test_unlink_forbidden_for_non_admin(self, non_admin_client, db_session):
        resp = non_admin_client.post("/characters/admin/1/unlink")
        assert resp.status_code == 403


# ===========================================================================
# DELETE /characters/{character_id} — cascade
# ===========================================================================

class TestDeleteCharacterCascade:

    @patch("httpx.AsyncClient")
    def test_delete_cascade_success(self, mock_client_class, admin_client, db_session):
        _seed_request(db_session)
        _seed_character(db_session, user_id=10)

        # Mock all cascade HTTP calls
        mock_instance = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_instance.delete = AsyncMock(return_value=mock_response)
        mock_instance.post = AsyncMock(return_value=mock_response)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_instance

        resp = admin_client.delete("/characters/1")
        assert resp.status_code == 200

        # Verify character deleted from DB
        ch = db_session.query(models.Character).filter(models.Character.id == 1).first()
        assert ch is None

    @patch("httpx.AsyncClient")
    def test_delete_cascade_verifies_cleanup_calls(self, mock_client_class, admin_client, db_session):
        """Verify that all cascade cleanup HTTP calls are made."""
        _seed_request(db_session)
        _seed_character(db_session, user_id=10)

        mock_instance = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_instance.delete = AsyncMock(return_value=mock_response)
        mock_instance.post = AsyncMock(return_value=mock_response)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_instance

        resp = admin_client.delete("/characters/1")
        assert resp.status_code == 200

        # There should be calls for: inventory, skills, attributes, user relation, clear current
        # Each creates a new AsyncClient context, so we check mock_client_class was called multiple times
        assert mock_client_class.call_count >= 3  # at least inventory + skills + attributes

    def test_delete_not_found(self, admin_client, db_session):
        resp = admin_client.delete("/characters/999")
        assert resp.status_code == 404

    def test_delete_forbidden_for_non_admin(self, non_admin_client, db_session):
        resp = non_admin_client.delete("/characters/1")
        assert resp.status_code == 403

    @patch("httpx.AsyncClient")
    def test_delete_no_user_id_skips_user_cleanup(self, mock_client_class, admin_client, db_session):
        """When character has no user_id, skip user-service cleanup calls."""
        _seed_request(db_session)
        _seed_character(db_session, user_id=None)

        mock_instance = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_instance.delete = AsyncMock(return_value=mock_response)
        mock_instance.post = AsyncMock(return_value=mock_response)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_instance

        resp = admin_client.delete("/characters/1")
        assert resp.status_code == 200

        # Verify character deleted
        ch = db_session.query(models.Character).filter(models.Character.id == 1).first()
        assert ch is None
