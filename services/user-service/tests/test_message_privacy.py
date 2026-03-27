"""
FEAT-094 Task #8 — Tests for message privacy and friend-check endpoints.

Covers:
- PUT  /users/me/message-privacy         — update privacy setting
- GET  /users/{user_id}/message-privacy   — get privacy setting
- GET  /users/friends/check/{friend_id}   — quick friendship check
"""

import pytest

from auth import get_current_user
from database import get_db
from main import app
import models

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db, *, user_id, username, email):
    """Create and persist a User in the test DB."""
    user = models.User(
        id=user_id,
        email=email,
        username=username,
        hashed_password="fakehash",
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _authed_client(db_session, user):
    """Return a TestClient authenticated as *user*."""
    def override_get_db():
        yield db_session

    def override_auth():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_auth
    client = TestClient(app)
    return client


def _unauthed_client(db_session):
    """Return a TestClient with DB override but no auth (for public endpoints)."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides.pop(get_current_user, None)
    client = TestClient(app)
    return client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def alice(db_session):
    return _make_user(db_session, user_id=1, username="alice", email="alice@test.com")


@pytest.fixture()
def bob(db_session):
    return _make_user(db_session, user_id=2, username="bob", email="bob@test.com")


# ---------------------------------------------------------------------------
# PUT /users/me/message-privacy — update privacy
# ---------------------------------------------------------------------------

class TestUpdateMessagePrivacy:
    """Tests for updating message_privacy setting."""

    def test_set_privacy_all(self, db_session, alice):
        """Setting privacy to 'all' succeeds."""
        client = _authed_client(db_session, alice)
        resp = client.put("/users/me/message-privacy", json={"message_privacy": "all"})
        assert resp.status_code == 200
        assert resp.json()["message_privacy"] == "all"

    def test_set_privacy_friends(self, db_session, alice):
        """Setting privacy to 'friends' succeeds."""
        client = _authed_client(db_session, alice)
        resp = client.put("/users/me/message-privacy", json={"message_privacy": "friends"})
        assert resp.status_code == 200
        assert resp.json()["message_privacy"] == "friends"

    def test_set_privacy_nobody(self, db_session, alice):
        """Setting privacy to 'nobody' succeeds."""
        client = _authed_client(db_session, alice)
        resp = client.put("/users/me/message-privacy", json={"message_privacy": "nobody"})
        assert resp.status_code == 200
        assert resp.json()["message_privacy"] == "nobody"

    def test_invalid_privacy_value_returns_422(self, db_session, alice):
        """Setting privacy to an invalid value returns 422."""
        client = _authed_client(db_session, alice)
        resp = client.put("/users/me/message-privacy", json={"message_privacy": "invalid"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /users/{user_id}/message-privacy — get privacy
# ---------------------------------------------------------------------------

class TestGetMessagePrivacy:
    """Tests for getting a user's message_privacy setting."""

    def test_default_privacy_is_all(self, db_session, alice):
        """New user's privacy defaults to 'all'."""
        client = _unauthed_client(db_session)
        resp = client.get(f"/users/{alice.id}/message-privacy")
        assert resp.status_code == 200
        assert resp.json()["message_privacy"] == "all"

    def test_returns_updated_value(self, db_session, alice):
        """After updating privacy, GET returns the new value."""
        authed = _authed_client(db_session, alice)
        authed.put("/users/me/message-privacy", json={"message_privacy": "nobody"})

        # Public endpoint — no auth needed
        client = _unauthed_client(db_session)
        resp = client.get(f"/users/{alice.id}/message-privacy")
        assert resp.status_code == 200
        assert resp.json()["message_privacy"] == "nobody"

    def test_nonexistent_user_returns_404(self, db_session):
        """Querying privacy for a non-existent user returns 404."""
        client = _unauthed_client(db_session)
        resp = client.get("/users/99999/message-privacy")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /users/friends/check/{friend_id} — friendship check
# ---------------------------------------------------------------------------

class TestFriendCheck:
    """Tests for the quick friend-check endpoint."""

    def test_accepted_friends_returns_true(self, db_session, alice, bob):
        """When an accepted friendship exists, is_friend is true."""
        friendship = models.Friendship(
            user_id=alice.id,
            friend_id=bob.id,
            status="accepted",
        )
        db_session.add(friendship)
        db_session.commit()

        client = _authed_client(db_session, alice)
        resp = client.get(f"/users/friends/check/{bob.id}")
        assert resp.status_code == 200
        assert resp.json()["is_friend"] is True

    def test_non_friends_returns_false(self, db_session, alice, bob):
        """When no friendship exists, is_friend is false."""
        client = _authed_client(db_session, alice)
        resp = client.get(f"/users/friends/check/{bob.id}")
        assert resp.status_code == 200
        assert resp.json()["is_friend"] is False

    def test_pending_friendship_returns_false(self, db_session, alice, bob):
        """A pending friendship is not a friendship — is_friend is false."""
        friendship = models.Friendship(
            user_id=alice.id,
            friend_id=bob.id,
            status="pending",
        )
        db_session.add(friendship)
        db_session.commit()

        client = _authed_client(db_session, alice)
        resp = client.get(f"/users/friends/check/{bob.id}")
        assert resp.status_code == 200
        assert resp.json()["is_friend"] is False
