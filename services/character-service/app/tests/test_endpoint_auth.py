"""
Tests for user-facing endpoint authentication in character-service.

Covers:
- C1: POST /characters/requests/ — ownership (user_id in body must match token user)
- C2: POST /characters/{cid}/titles/{tid} — admin-only (characters:update)
- C3: POST /characters/{cid}/current-title/{tid} — ownership via verify_character_ownership
- C6: GET /characters/moderation-requests — admin-only (characters:approve)
"""

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import models
from auth_http import get_current_user_via_http, require_permission, OAUTH2_SCHEME, UserRead
from main import app, get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


def _make_user(user_id: int = 1, role: str = "user", permissions: list = None):
    return UserRead(
        id=user_id,
        username=f"user{user_id}",
        role=role,
        permissions=permissions or [],
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def real_db_client(test_engine, test_session_factory, seed_fk_data):
    """
    TestClient with a real SQLite DB (tables created).
    Auth is NOT overridden — tests must either provide headers or override auth themselves.
    """
    from database import Base
    Base.metadata.create_all(bind=test_engine)
    session = test_session_factory()
    seed_fk_data(session)

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False), session
    app.dependency_overrides.clear()
    session.close()
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def _insert_character(real_db_client):
    """Insert a character owned by user_id=1 into the test DB and return its id."""
    client, session = real_db_client

    # Need a character_request first (FK constraint)
    req = models.CharacterRequest(
        id=1,
        name="TestChar",
        id_subrace=1,
        biography="bio",
        personality="pers",
        id_class=1,
        status="approved",
        user_id=1,
        appearance="appearance",
        id_race=1,
        avatar="avatar.png",
    )
    session.add(req)
    session.flush()

    char = models.Character(
        id=1,
        name="TestChar",
        id_subrace=1,
        biography="bio",
        personality="pers",
        id_class=1,
        user_id=1,
        appearance="appearance",
        id_race=1,
        avatar="avatar.png",
        request_id=1,
    )
    session.add(char)
    session.commit()
    return 1  # character id


# ===========================================================================
# C1: POST /characters/requests/ — ownership check
# ===========================================================================

class TestCreateCharacterRequest:
    """Auth tests for POST /characters/requests/."""

    def test_missing_token_returns_401(self, client: TestClient):
        """No Authorization header -> 401."""
        payload = {
            "name": "Hero",
            "id_subrace": 1,
            "biography": "bio",
            "personality": "pers",
            "appearance": "app",
            "id_class": 1,
            "id_race": 1,
            "user_id": 1,
            "avatar": "a.png",
        }
        response = client.post("/characters/requests/", json=payload)
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_user_id_mismatch_returns_403(self, mock_get, client: TestClient):
        """Token user (id=1) but body has user_id=999 -> 403."""
        mock_get.return_value = _mock_response(
            200, {"id": 1, "username": "user1", "role": "user", "permissions": []}
        )
        payload = {
            "name": "Hero",
            "id_subrace": 1,
            "biography": "bio",
            "personality": "pers",
            "appearance": "app",
            "id_class": 1,
            "id_race": 1,
            "user_id": 999,
            "avatar": "a.png",
        }
        response = client.post(
            "/characters/requests/",
            json=payload,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_matching_user_id_accepted(self, mock_get, real_db_client):
        """Token user matches body user_id -> request is accepted (not 401/403)."""
        mock_get.return_value = _mock_response(
            200, {"id": 1, "username": "user1", "role": "user", "permissions": []}
        )
        test_client, session = real_db_client

        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        payload = {
            "name": "Hero",
            "id_subrace": 1,
            "biography": "bio",
            "personality": "pers",
            "appearance": "app",
            "id_class": 1,
            "id_race": 1,
            "user_id": 1,
            "avatar": "a.png",
        }
        response = test_client.post(
            "/characters/requests/",
            json=payload,
            headers={"Authorization": "Bearer fake-token"},
        )
        # Should succeed (200) or at worst a DB issue — but NOT 401/403
        assert response.status_code not in (401, 403)


# ===========================================================================
# C2: POST /characters/{cid}/titles/{tid} — admin-only (characters:update)
# ===========================================================================

class TestAssignTitle:
    """Auth tests for POST /characters/{cid}/titles/{tid}."""

    def test_missing_token_returns_401(self, client: TestClient):
        """No Authorization header -> 401."""
        response = client.post("/characters/1/titles/1")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_user_without_permission_returns_403(self, mock_get, client: TestClient):
        """Valid token, role=user, no characters:update permission -> 403."""
        mock_get.return_value = _mock_response(
            200, {"id": 2, "username": "player", "role": "user", "permissions": []}
        )
        response = client.post(
            "/characters/1/titles/1",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_admin_with_permission_accepted(self, mock_get, real_db_client, _insert_character):
        """Admin with characters:update -> request passes auth (not 401/403)."""
        mock_get.return_value = _mock_response(
            200, {"id": 1, "username": "admin", "role": "admin", "permissions": ["characters:update"]}
        )
        test_client, session = real_db_client

        # Insert a title for the assignment
        title = models.Title(id_title=1, name="Hero Title")
        session.add(title)
        session.commit()

        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-admin-token"

        response = test_client.post(
            "/characters/1/titles/1",
            headers={"Authorization": "Bearer fake-admin-token"},
        )
        assert response.status_code not in (401, 403)


# ===========================================================================
# C3: POST /characters/{cid}/current-title/{tid} — ownership check
# ===========================================================================

class TestSetCurrentTitle:
    """Auth tests for POST /characters/{cid}/current-title/{tid}."""

    def test_missing_token_returns_401(self, client: TestClient):
        """No Authorization header -> 401."""
        response = client.post("/characters/1/current-title/1")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_wrong_owner_returns_403(self, mock_get, real_db_client, _insert_character):
        """Token user (id=999) tries to set title on character owned by user_id=1 -> 403."""
        mock_get.return_value = _mock_response(
            200, {"id": 999, "username": "hacker", "role": "user", "permissions": []}
        )
        test_client, _ = real_db_client

        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = test_client.post(
            "/characters/1/current-title/1",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_correct_owner_accepted(self, mock_get, real_db_client, _insert_character):
        """Token user (id=1) owns the character -> passes auth."""
        mock_get.return_value = _mock_response(
            200, {"id": 1, "username": "owner", "role": "user", "permissions": []}
        )
        test_client, session = real_db_client

        # Insert a title and assign it to the character
        title = models.Title(id_title=1, name="Hero Title")
        session.add(title)
        ct = models.CharacterTitle(character_id=1, title_id=1)
        session.add(ct)
        session.commit()

        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"

        response = test_client.post(
            "/characters/1/current-title/1",
            headers={"Authorization": "Bearer fake-token"},
        )
        # Should pass auth (not 401/403); may still fail on business logic
        assert response.status_code not in (401, 403)


# ===========================================================================
# C6: GET /characters/moderation-requests — admin-only (characters:approve)
# ===========================================================================

class TestModerationRequests:
    """Auth tests for GET /characters/moderation-requests."""

    def test_missing_token_returns_401(self, client: TestClient):
        """No Authorization header -> 401."""
        response = client.get("/characters/moderation-requests")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_user_without_permission_returns_403(self, mock_get, client: TestClient):
        """Valid token, no characters:approve permission -> 403."""
        mock_get.return_value = _mock_response(
            200, {"id": 2, "username": "player", "role": "user", "permissions": []}
        )
        response = client.get(
            "/characters/moderation-requests",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_admin_with_permission_accepted(self, mock_get, real_db_client):
        """Admin with characters:approve -> passes auth."""
        mock_get.return_value = _mock_response(
            200, {"id": 1, "username": "admin", "role": "admin", "permissions": ["characters:approve"]}
        )
        test_client, _ = real_db_client

        app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-admin-token"

        response = test_client.get(
            "/characters/moderation-requests",
            headers={"Authorization": "Bearer fake-admin-token"},
        )
        assert response.status_code not in (401, 403)
