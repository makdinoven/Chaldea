"""
FEAT-029 Task #7 — Tests for user stats, online users, and last_active_at tracking.

Covers:
1. GET /users/stats — total_users and online_users counts
2. GET /users/stats — returns 0 online when no recent activity
3. GET /users/online — returns only users active in last 5 minutes
4. GET /users/online — pagination works correctly
5. GET /users/online — response excludes hashed_password and email
6. GET /users/all — response excludes hashed_password and email (security fix)
7. GET /users/all — pagination works
8. GET /users/me — updates last_active_at on call
9. Edge case — user with NULL last_active_at is NOT counted as online
"""

from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

import pytest

from crud import create_user
from schemas import UserCreate
import models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SENSITIVE_FIELDS = ("hashed_password", "email", "balance", "role", "current_character")


def _make_user(db, username="player1", email="player1@test.com", password="Pass1234"):
    """Create a user via CRUD and return the ORM object."""
    return create_user(db, UserCreate(email=email, username=username, password=password))


def _set_last_active(db, user, dt_value):
    """Set a specific last_active_at timestamp on a user."""
    db.query(models.User).filter(models.User.id == user.id).update(
        {models.User.last_active_at: dt_value}
    )
    db.commit()


def _auth_header(user):
    """Build an Authorization header with a valid JWT for the given user."""
    from auth import create_access_token
    token = create_access_token(data={"sub": user.email}, role=user.role)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. GET /users/stats — correct counts
# ---------------------------------------------------------------------------

class TestGetUserStats:

    def test_stats_returns_correct_counts(self, client, db_session):
        """Stats endpoint returns total_users and online_users correctly."""
        u1 = _make_user(db_session, "u1", "u1@t.com")
        u2 = _make_user(db_session, "u2", "u2@t.com")
        _make_user(db_session, "u3", "u3@t.com")  # no activity

        # Mark u1 and u2 as recently active
        now = datetime.utcnow()
        _set_last_active(db_session, u1, now - timedelta(minutes=1))
        _set_last_active(db_session, u2, now - timedelta(minutes=3))

        resp = client.get("/users/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_users"] == 3
        assert data["online_users"] == 2

    def test_stats_returns_zero_online_when_no_recent_activity(self, client, db_session):
        """When all users have old or NULL last_active_at, online_users == 0."""
        u1 = _make_user(db_session, "u1", "u1@t.com")
        _make_user(db_session, "u2", "u2@t.com")  # NULL last_active_at

        # u1 was active 10 minutes ago (beyond the 5-min threshold)
        _set_last_active(db_session, u1, datetime.utcnow() - timedelta(minutes=10))

        resp = client.get("/users/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_users"] == 2
        assert data["online_users"] == 0

    def test_stats_empty_db(self, client, db_session):
        """Stats on an empty DB returns zeros."""
        resp = client.get("/users/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_users"] == 0
        assert data["online_users"] == 0


# ---------------------------------------------------------------------------
# 2. GET /users/online
# ---------------------------------------------------------------------------

class TestGetOnlineUsers:

    def test_returns_only_recently_active_users(self, client, db_session):
        """Only users with last_active_at within 5 minutes appear."""
        u_online = _make_user(db_session, "online_guy", "online@t.com")
        u_offline = _make_user(db_session, "offline_guy", "offline@t.com")
        u_null = _make_user(db_session, "null_guy", "null@t.com")

        now = datetime.utcnow()
        _set_last_active(db_session, u_online, now - timedelta(minutes=2))
        _set_last_active(db_session, u_offline, now - timedelta(minutes=10))
        # u_null has NULL last_active_at

        resp = client.get("/users/online")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["username"] == "online_guy"

    def test_pagination_works(self, client, db_session):
        """Pagination returns correct slices and total count."""
        now = datetime.utcnow()
        for i in range(5):
            u = _make_user(db_session, f"p{i}", f"p{i}@t.com")
            _set_last_active(db_session, u, now - timedelta(seconds=i * 10))

        # Request page 1 with page_size=2
        resp = client.get("/users/online?page=1&page_size=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2

        # Request page 3 — should have 1 item
        resp2 = client.get("/users/online?page=3&page_size=2")
        data2 = resp2.json()
        assert data2["total"] == 5
        assert len(data2["items"]) == 1

    def test_response_excludes_sensitive_fields(self, client, db_session):
        """Online user items must NOT contain hashed_password, email, etc."""
        u = _make_user(db_session, "secret", "secret@t.com")
        _set_last_active(db_session, u, datetime.utcnow())

        resp = client.get("/users/online")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        for field in SENSITIVE_FIELDS:
            assert field not in item, f"Sensitive field '{field}' leaked in /users/online response"

        # Verify expected public fields are present
        assert "id" in item
        assert "username" in item
        assert "avatar" in item
        assert "registered_at" in item
        assert "last_active_at" in item

    def test_empty_when_nobody_online(self, client, db_session):
        """Returns empty list with total=0 when no users are online."""
        _make_user(db_session, "lonely", "lonely@t.com")  # NULL last_active_at

        resp = client.get("/users/online")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []


# ---------------------------------------------------------------------------
# 3. GET /users/all — security fix verification
# ---------------------------------------------------------------------------

class TestGetAllUsers:

    def test_response_excludes_sensitive_fields(self, client, db_session):
        """All-users list must NOT contain hashed_password, email, etc."""
        _make_user(db_session, "pub", "pub@t.com")

        resp = client.get("/users/all")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        for field in SENSITIVE_FIELDS:
            assert field not in item, f"Sensitive field '{field}' leaked in /users/all response"

    def test_pagination_works(self, client, db_session):
        """Pagination on /users/all returns correct slices."""
        for i in range(7):
            _make_user(db_session, f"u{i}", f"u{i}@t.com")

        resp = client.get("/users/all?page=1&page_size=3")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 7
        assert len(data["items"]) == 3
        assert data["page"] == 1
        assert data["page_size"] == 3

        # Last page
        resp2 = client.get("/users/all?page=3&page_size=3")
        data2 = resp2.json()
        assert len(data2["items"]) == 1

    def test_returns_all_public_fields(self, client, db_session):
        """Each item has id, username, avatar, registered_at, last_active_at."""
        _make_user(db_session, "full", "full@t.com")
        resp = client.get("/users/all")
        item = resp.json()["items"][0]
        assert "id" in item
        assert "username" in item
        assert "avatar" in item
        assert "registered_at" in item
        assert "last_active_at" in item


# ---------------------------------------------------------------------------
# 4. GET /users/me — updates last_active_at
# ---------------------------------------------------------------------------

class TestMeUpdatesLastActive:

    @patch("main._fetch_character_short", new_callable=AsyncMock, return_value=None)
    def test_me_updates_last_active_at(self, mock_fetch, client, db_session):
        """Calling /users/me should update last_active_at for the current user."""
        user = _make_user(db_session, "me_user", "me@t.com")
        assert user.last_active_at is None  # initially NULL

        headers = _auth_header(user)
        resp = client.get("/users/me", headers=headers)
        assert resp.status_code == 200

        # Refresh from DB to check the update
        db_session.expire_all()
        updated_user = db_session.query(models.User).filter(models.User.id == user.id).first()
        assert updated_user.last_active_at is not None
        # Should be very recent (within last 5 seconds)
        assert (datetime.utcnow() - updated_user.last_active_at).total_seconds() < 5

    @patch("main._fetch_character_short", new_callable=AsyncMock, return_value=None)
    def test_me_makes_user_appear_online_in_stats(self, mock_fetch, client, db_session):
        """After calling /me, the user should be counted as online in /stats."""
        user = _make_user(db_session, "tracker", "tracker@t.com")

        # Before /me call — 0 online
        resp = client.get("/users/stats")
        assert resp.json()["online_users"] == 0

        # Call /me to update last_active_at
        headers = _auth_header(user)
        client.get("/users/me", headers=headers)

        # After /me call — 1 online
        resp = client.get("/users/stats")
        assert resp.json()["online_users"] == 1


# ---------------------------------------------------------------------------
# 5. Edge case — NULL last_active_at
# ---------------------------------------------------------------------------

class TestNullLastActiveAt:

    def test_null_last_active_not_counted_as_online(self, client, db_session):
        """User with NULL last_active_at must NOT be counted as online."""
        _make_user(db_session, "new_user", "new@t.com")

        resp = client.get("/users/stats")
        data = resp.json()
        assert data["total_users"] == 1
        assert data["online_users"] == 0

    def test_null_last_active_not_in_online_list(self, client, db_session):
        """User with NULL last_active_at must NOT appear in /users/online."""
        _make_user(db_session, "ghost", "ghost@t.com")

        resp = client.get("/users/online")
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []
