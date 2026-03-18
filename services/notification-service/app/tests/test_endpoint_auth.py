"""
Tests for JWT authentication and ownership checks on notification-service endpoints.

Covers 4 endpoints:
- GET  /notifications/{user_id}/unread
- GET  /notifications/{user_id}/full
- PUT  /notifications/{user_id}/mark-as-read
- PUT  /notifications/{user_id}/mark-all-as-read

Each endpoint is tested for:
1. 401 without token
2. 403 with wrong user_id (ownership violation)
3. Success with correct auth
"""

import pytest
from fastapi.testclient import TestClient

from auth_http import get_current_user_via_http, UserRead
from database import get_db
from main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(user_id: int = 1, username: str = "testuser", role: str = "user") -> UserRead:
    return UserRead(id=user_id, username=username, role=role)


def _client_no_auth(db_session):
    """TestClient WITHOUT auth override — endpoints should reject with 401."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # Do NOT override get_current_user_via_http — let OAuth2 scheme fail
    app.dependency_overrides.pop(get_current_user_via_http, None)
    client = TestClient(app)
    return client


def _client_with_user(db_session, user: UserRead):
    """TestClient with auth override returning the given user."""
    def override_get_db():
        yield db_session

    def override_auth():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_via_http] = override_auth
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /notifications/{user_id}/unread
# ---------------------------------------------------------------------------

class TestGetUnreadNotifications:
    """Auth tests for GET /notifications/{user_id}/unread."""

    def test_missing_token_returns_401(self, db_session):
        client = _client_no_auth(db_session)
        response = client.get("/notifications/1/unread")
        assert response.status_code == 401
        app.dependency_overrides.clear()

    def test_wrong_user_returns_403(self, db_session):
        user = _make_user(user_id=1)
        client = _client_with_user(db_session, user)
        response = client.get("/notifications/999/unread")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    def test_correct_user_returns_200(self, db_session):
        user = _make_user(user_id=1)
        client = _client_with_user(db_session, user)
        response = client.get("/notifications/1/unread")
        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert "total" in body
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /notifications/{user_id}/full
# ---------------------------------------------------------------------------

class TestGetAllNotifications:
    """Auth tests for GET /notifications/{user_id}/full."""

    def test_missing_token_returns_401(self, db_session):
        client = _client_no_auth(db_session)
        response = client.get("/notifications/1/full")
        assert response.status_code == 401
        app.dependency_overrides.clear()

    def test_wrong_user_returns_403(self, db_session):
        user = _make_user(user_id=1)
        client = _client_with_user(db_session, user)
        response = client.get("/notifications/999/full")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    def test_correct_user_returns_200(self, db_session):
        user = _make_user(user_id=1)
        client = _client_with_user(db_session, user)
        response = client.get("/notifications/1/full")
        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert "total" in body
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# PUT /notifications/{user_id}/mark-as-read
# ---------------------------------------------------------------------------

class TestMarkAsRead:
    """Auth tests for PUT /notifications/{user_id}/mark-as-read."""

    def test_missing_token_returns_401(self, db_session):
        client = _client_no_auth(db_session)
        response = client.put("/notifications/1/mark-as-read", json=[1, 2])
        assert response.status_code == 401
        app.dependency_overrides.clear()

    def test_wrong_user_returns_403(self, db_session):
        user = _make_user(user_id=1)
        client = _client_with_user(db_session, user)
        response = client.put("/notifications/999/mark-as-read", json=[1, 2])
        assert response.status_code == 403
        app.dependency_overrides.clear()

    def test_correct_user_with_notifications(self, db_session, seed_notifications):
        user = _make_user(user_id=1)
        client = _client_with_user(db_session, user)
        # Get IDs of unread notifications for user 1
        unread_ids = [n.id for n in seed_notifications if n.user_id == 1 and n.status == "unread"]
        response = client.put("/notifications/1/mark-as-read", json=unread_ids)
        assert response.status_code == 200
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# PUT /notifications/{user_id}/mark-all-as-read
# ---------------------------------------------------------------------------

class TestMarkAllAsRead:
    """Auth tests for PUT /notifications/{user_id}/mark-all-as-read."""

    def test_missing_token_returns_401(self, db_session):
        client = _client_no_auth(db_session)
        response = client.put("/notifications/1/mark-all-as-read")
        assert response.status_code == 401
        app.dependency_overrides.clear()

    def test_wrong_user_returns_403(self, db_session):
        user = _make_user(user_id=1)
        client = _client_with_user(db_session, user)
        response = client.put("/notifications/999/mark-all-as-read")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    def test_correct_user_with_notifications(self, db_session, seed_notifications):
        user = _make_user(user_id=1)
        client = _client_with_user(db_session, user)
        response = client.put("/notifications/1/mark-all-as-read")
        assert response.status_code == 200
        app.dependency_overrides.clear()
