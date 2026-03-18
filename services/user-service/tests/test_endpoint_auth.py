"""
Tests for JWT authentication and ownership checks on user-service endpoints.

Covers:
- PUT /users/{user_id}/update_character

Each endpoint is tested for:
1. 401 without token
2. 403 with wrong user_id (ownership violation)
3. Success with correct auth

Note: user-service uses `get_current_user` from auth.py (local JWT decode),
NOT `get_current_user_via_http`.
"""

import pytest
from fastapi.testclient import TestClient

from auth import get_current_user
from database import get_db
from main import app
import models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user_model(db_session, user_id: int = 1, email: str = "test@example.com",
                     username: str = "testuser", role: str = "user"):
    """Create and persist a User model instance in the test DB."""
    user = models.User(
        id=user_id,
        email=email,
        username=username,
        hashed_password="fakehash",
        role=role,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _client_no_auth(db_session):
    """TestClient WITHOUT auth override — endpoints should reject with 401."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides.pop(get_current_user, None)
    return TestClient(app)


def _client_with_user(db_session, user):
    """TestClient with auth override returning the given user model."""
    def override_get_db():
        yield db_session

    def override_auth():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_auth
    return TestClient(app)


# ---------------------------------------------------------------------------
# PUT /users/{user_id}/update_character
# ---------------------------------------------------------------------------

class TestUpdateUserCharacter:
    """Auth tests for PUT /users/{user_id}/update_character."""

    def test_missing_token_returns_401(self, db_session):
        """No Authorization header -> 401."""
        client = _client_no_auth(db_session)
        response = client.put(
            "/users/1/update_character",
            json={"current_character": 1},
        )
        assert response.status_code == 401
        app.dependency_overrides.clear()

    def test_wrong_user_returns_403(self, db_session):
        """Authenticated as user 1, trying to update user 999 -> 403."""
        user = _make_user_model(db_session, user_id=1)
        client = _client_with_user(db_session, user)
        response = client.put(
            "/users/999/update_character",
            json={"current_character": 1},
        )
        assert response.status_code == 403
        app.dependency_overrides.clear()

    def test_correct_user_with_valid_character(self, db_session):
        """Authenticated as user 1, updating own character -> 200."""
        user = _make_user_model(db_session, user_id=1)
        # Create a character relation so the endpoint finds a valid link
        relation = models.UserCharacter(user_id=1, character_id=10)
        db_session.add(relation)
        db_session.commit()

        client = _client_with_user(db_session, user)
        response = client.put(
            "/users/1/update_character",
            json={"current_character": 10},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["current_character"] == 10
        app.dependency_overrides.clear()

    def test_correct_user_missing_character_field_returns_400(self, db_session):
        """Authenticated as user 1, but no current_character in body -> 400."""
        user = _make_user_model(db_session, user_id=1)
        client = _client_with_user(db_session, user)
        response = client.put(
            "/users/1/update_character",
            json={},
        )
        assert response.status_code == 400
        app.dependency_overrides.clear()

    def test_correct_user_no_relation_returns_400(self, db_session):
        """Authenticated as user 1, but character not linked -> 400."""
        user = _make_user_model(db_session, user_id=1)
        client = _client_with_user(db_session, user)
        response = client.put(
            "/users/1/update_character",
            json={"current_character": 999},
        )
        assert response.status_code == 400
        app.dependency_overrides.clear()
