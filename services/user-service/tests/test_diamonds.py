"""
FEAT-102 Task #12 — QA Tests for diamond endpoints in user-service.

Covers:
1. GET /users/internal/{user_id}/diamonds — returns correct diamond balance
2. POST /users/internal/{user_id}/diamonds/add — adds diamonds correctly
3. POST /users/internal/{user_id}/diamonds/add — invalid amount (0, negative) returns 400
4. POST /users/internal/{user_id}/diamonds/spend — spends diamonds correctly
5. POST /users/internal/{user_id}/diamonds/spend — insufficient balance returns 400
6. POST /users/internal/{user_id}/diamonds/spend — invalid amount returns 400
7. Nonexistent user returns 404 for all endpoints
8. Sequential add + spend operations maintain correct balance
"""

import pytest

from crud import create_user
from schemas import UserCreate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db, username="player1", email="player1@test.com", password="Pass1234"):
    """Create a user via CRUD and return the ORM object."""
    return create_user(db, UserCreate(email=email, username=username, password=password))


NONEXISTENT_USER_ID = 999999


# ===========================================================================
# 1. GET /users/internal/{user_id}/diamonds
# ===========================================================================

class TestGetDiamonds:

    def test_get_diamonds_default_zero(self, client, db_session):
        """New user should have 0 diamonds."""
        user = _make_user(db_session)
        resp = client.get(f"/users/internal/{user.id}/diamonds")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == user.id
        assert data["diamonds"] == 0

    def test_get_diamonds_nonexistent_user(self, client, db_session):
        """Requesting diamonds for a nonexistent user returns 404."""
        resp = client.get(f"/users/internal/{NONEXISTENT_USER_ID}/diamonds")
        assert resp.status_code == 404


# ===========================================================================
# 2. POST /users/internal/{user_id}/diamonds/add
# ===========================================================================

class TestAddDiamonds:

    def test_add_diamonds_success(self, client, db_session):
        """Adding diamonds increases balance correctly."""
        user = _make_user(db_session)
        resp = client.post(
            f"/users/internal/{user.id}/diamonds/add",
            json={"amount": 100, "reason": "test reward"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == user.id
        assert data["diamonds"] == 100

    def test_add_diamonds_cumulative(self, client, db_session):
        """Multiple add operations accumulate correctly."""
        user = _make_user(db_session)
        client.post(
            f"/users/internal/{user.id}/diamonds/add",
            json={"amount": 50, "reason": "first"},
        )
        resp = client.post(
            f"/users/internal/{user.id}/diamonds/add",
            json={"amount": 30, "reason": "second"},
        )
        assert resp.status_code == 200
        assert resp.json()["diamonds"] == 80

    def test_add_diamonds_zero_amount(self, client, db_session):
        """Adding 0 diamonds returns 400."""
        user = _make_user(db_session)
        resp = client.post(
            f"/users/internal/{user.id}/diamonds/add",
            json={"amount": 0, "reason": "invalid"},
        )
        assert resp.status_code == 400

    def test_add_diamonds_negative_amount(self, client, db_session):
        """Adding negative diamonds returns 400."""
        user = _make_user(db_session)
        resp = client.post(
            f"/users/internal/{user.id}/diamonds/add",
            json={"amount": -10, "reason": "invalid"},
        )
        assert resp.status_code == 400

    def test_add_diamonds_nonexistent_user(self, client, db_session):
        """Adding diamonds to nonexistent user returns 404."""
        resp = client.post(
            f"/users/internal/{NONEXISTENT_USER_ID}/diamonds/add",
            json={"amount": 100, "reason": "test"},
        )
        assert resp.status_code == 404


# ===========================================================================
# 3. POST /users/internal/{user_id}/diamonds/spend
# ===========================================================================

class TestSpendDiamonds:

    def test_spend_diamonds_success(self, client, db_session):
        """Spending diamonds reduces balance correctly."""
        user = _make_user(db_session)
        # First add diamonds
        client.post(
            f"/users/internal/{user.id}/diamonds/add",
            json={"amount": 200, "reason": "seed"},
        )
        # Then spend
        resp = client.post(
            f"/users/internal/{user.id}/diamonds/spend",
            json={"amount": 50, "reason": "purchase"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == user.id
        assert data["diamonds"] == 150

    def test_spend_diamonds_exact_balance(self, client, db_session):
        """Spending exactly the full balance succeeds and leaves 0."""
        user = _make_user(db_session)
        client.post(
            f"/users/internal/{user.id}/diamonds/add",
            json={"amount": 75, "reason": "seed"},
        )
        resp = client.post(
            f"/users/internal/{user.id}/diamonds/spend",
            json={"amount": 75, "reason": "all-in"},
        )
        assert resp.status_code == 200
        assert resp.json()["diamonds"] == 0

    def test_spend_diamonds_insufficient_balance(self, client, db_session):
        """Spending more than balance returns 400."""
        user = _make_user(db_session)
        # User has 0 diamonds
        resp = client.post(
            f"/users/internal/{user.id}/diamonds/spend",
            json={"amount": 10, "reason": "overdraft"},
        )
        assert resp.status_code == 400

    def test_spend_diamonds_insufficient_after_partial(self, client, db_session):
        """Spending more than remaining balance after prior spend returns 400."""
        user = _make_user(db_session)
        client.post(
            f"/users/internal/{user.id}/diamonds/add",
            json={"amount": 100, "reason": "seed"},
        )
        client.post(
            f"/users/internal/{user.id}/diamonds/spend",
            json={"amount": 80, "reason": "first spend"},
        )
        resp = client.post(
            f"/users/internal/{user.id}/diamonds/spend",
            json={"amount": 30, "reason": "too much"},
        )
        assert resp.status_code == 400

    def test_spend_diamonds_zero_amount(self, client, db_session):
        """Spending 0 diamonds returns 400."""
        user = _make_user(db_session)
        resp = client.post(
            f"/users/internal/{user.id}/diamonds/spend",
            json={"amount": 0, "reason": "invalid"},
        )
        assert resp.status_code == 400

    def test_spend_diamonds_negative_amount(self, client, db_session):
        """Spending negative diamonds returns 400."""
        user = _make_user(db_session)
        resp = client.post(
            f"/users/internal/{user.id}/diamonds/spend",
            json={"amount": -5, "reason": "invalid"},
        )
        assert resp.status_code == 400

    def test_spend_diamonds_nonexistent_user(self, client, db_session):
        """Spending diamonds for nonexistent user returns 404."""
        resp = client.post(
            f"/users/internal/{NONEXISTENT_USER_ID}/diamonds/spend",
            json={"amount": 10, "reason": "test"},
        )
        assert resp.status_code == 404


# ===========================================================================
# 4. Sequential add + spend — balance integrity
# ===========================================================================

class TestDiamondSequentialOperations:

    def test_add_spend_add_sequence(self, client, db_session):
        """Multiple add and spend operations maintain correct running balance."""
        user = _make_user(db_session)

        # +100
        resp = client.post(
            f"/users/internal/{user.id}/diamonds/add",
            json={"amount": 100, "reason": "step1"},
        )
        assert resp.json()["diamonds"] == 100

        # -30
        resp = client.post(
            f"/users/internal/{user.id}/diamonds/spend",
            json={"amount": 30, "reason": "step2"},
        )
        assert resp.json()["diamonds"] == 70

        # +50
        resp = client.post(
            f"/users/internal/{user.id}/diamonds/add",
            json={"amount": 50, "reason": "step3"},
        )
        assert resp.json()["diamonds"] == 120

        # -120 (exact balance)
        resp = client.post(
            f"/users/internal/{user.id}/diamonds/spend",
            json={"amount": 120, "reason": "step4"},
        )
        assert resp.json()["diamonds"] == 0

        # Verify via GET
        resp = client.get(f"/users/internal/{user.id}/diamonds")
        assert resp.json()["diamonds"] == 0

    def test_multiple_adds_then_single_spend(self, client, db_session):
        """Many small adds followed by one large spend works correctly."""
        user = _make_user(db_session)

        for i in range(10):
            client.post(
                f"/users/internal/{user.id}/diamonds/add",
                json={"amount": 10, "reason": f"add-{i}"},
            )

        # Balance should be 100
        resp = client.get(f"/users/internal/{user.id}/diamonds")
        assert resp.json()["diamonds"] == 100

        # Spend 100
        resp = client.post(
            f"/users/internal/{user.id}/diamonds/spend",
            json={"amount": 100, "reason": "bulk spend"},
        )
        assert resp.status_code == 200
        assert resp.json()["diamonds"] == 0
