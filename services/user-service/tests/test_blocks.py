"""
FEAT-094 Task #8 — Tests for user blocking endpoints.

Covers:
- POST   /users/blocks/{blocked_user_id}  — create block
- DELETE /users/blocks/{blocked_user_id}  — remove block
- GET    /users/blocks                    — list blocks
- GET    /users/blocks/check/{other_user_id} — bidirectional check
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def users(db_session):
    """Create two users for block tests."""
    alice = _make_user(db_session, user_id=1, username="alice", email="alice@test.com")
    bob = _make_user(db_session, user_id=2, username="bob", email="bob@test.com")
    return alice, bob


# ---------------------------------------------------------------------------
# POST /users/blocks/{blocked_user_id} — create block
# ---------------------------------------------------------------------------

class TestCreateBlock:
    """Tests for blocking a user."""

    def test_block_user_success(self, db_session, users):
        """Blocking another user returns 201 with block data."""
        alice, bob = users
        client = _authed_client(db_session, alice)

        resp = client.post(f"/users/blocks/{bob.id}")
        assert resp.status_code == 201
        data = resp.json()
        assert data["user_id"] == alice.id
        assert data["blocked_user_id"] == bob.id
        assert "created_at" in data

    def test_block_self_returns_400(self, db_session, users):
        """Blocking yourself returns 400."""
        alice, _ = users
        client = _authed_client(db_session, alice)

        resp = client.post(f"/users/blocks/{alice.id}")
        assert resp.status_code == 400

    def test_duplicate_block_returns_409(self, db_session, users):
        """Blocking the same user twice returns 409."""
        alice, bob = users
        client = _authed_client(db_session, alice)

        resp1 = client.post(f"/users/blocks/{bob.id}")
        assert resp1.status_code == 201

        resp2 = client.post(f"/users/blocks/{bob.id}")
        assert resp2.status_code == 409

    def test_block_nonexistent_user_returns_404(self, db_session, users):
        """Blocking a user that does not exist returns 404."""
        alice, _ = users
        client = _authed_client(db_session, alice)

        resp = client.post("/users/blocks/99999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /users/blocks/{blocked_user_id} — remove block
# ---------------------------------------------------------------------------

class TestDeleteBlock:
    """Tests for unblocking a user."""

    def test_unblock_success(self, db_session, users):
        """Unblocking an existing block returns 200."""
        alice, bob = users
        client = _authed_client(db_session, alice)

        client.post(f"/users/blocks/{bob.id}")
        resp = client.delete(f"/users/blocks/{bob.id}")
        assert resp.status_code == 200

    def test_unblock_nonexistent_returns_404(self, db_session, users):
        """Unblocking when no block exists returns 404."""
        alice, bob = users
        client = _authed_client(db_session, alice)

        resp = client.delete(f"/users/blocks/{bob.id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /users/blocks — list blocks
# ---------------------------------------------------------------------------

class TestListBlocks:
    """Tests for listing blocked users."""

    def test_empty_list(self, db_session, users):
        """When no blocks exist, returns empty list."""
        alice, _ = users
        client = _authed_client(db_session, alice)

        resp = client.get("/users/blocks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []

    def test_list_with_items(self, db_session, users):
        """After blocking a user, the list contains the block with username."""
        alice, bob = users
        client = _authed_client(db_session, alice)

        client.post(f"/users/blocks/{bob.id}")

        resp = client.get("/users/blocks")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["blocked_user_id"] == bob.id
        assert items[0]["blocked_username"] == "bob"


# ---------------------------------------------------------------------------
# GET /users/blocks/check/{other_user_id} — bidirectional check
# ---------------------------------------------------------------------------

class TestBlockCheck:
    """Tests for bidirectional block check."""

    def test_no_blocks_both_false(self, db_session, users):
        """When neither user has blocked the other, both flags are false."""
        alice, bob = users
        client = _authed_client(db_session, alice)

        resp = client.get(f"/users/blocks/check/{bob.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_blocked"] is False
        assert data["blocked_by_me"] is False
        assert data["blocked_by_them"] is False

    def test_blocked_by_me(self, db_session, users):
        """When I block the other user, blocked_by_me is true."""
        alice, bob = users
        client = _authed_client(db_session, alice)

        client.post(f"/users/blocks/{bob.id}")

        resp = client.get(f"/users/blocks/check/{bob.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_blocked"] is True
        assert data["blocked_by_me"] is True
        assert data["blocked_by_them"] is False

    def test_blocked_by_them(self, db_session, users):
        """When the other user blocks me, blocked_by_them is true from my perspective."""
        alice, bob = users

        # Bob blocks Alice
        bob_client = _authed_client(db_session, bob)
        bob_client.post(f"/users/blocks/{alice.id}")

        # Alice checks — blocked_by_them should be true
        alice_client = _authed_client(db_session, alice)
        resp = alice_client.get(f"/users/blocks/check/{bob.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_blocked"] is True
        assert data["blocked_by_me"] is False
        assert data["blocked_by_them"] is True
