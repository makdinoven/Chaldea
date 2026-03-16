"""
Task 18 — QA for Bug #12: Pagination on /users/all endpoint.

Tests:
1. Default page/page_size returns correct paginated structure.
2. Custom page/page_size work correctly.
3. Boundary conditions (empty DB, page beyond data, page_size limits).
"""

import pytest
from unittest.mock import patch


def _seed_users(db_session, count=5):
    """Insert N users into the test DB."""
    import models

    users = []
    for i in range(1, count + 1):
        user = models.User(
            email=f"user{i}@test.com",
            username=f"user{i}",
            hashed_password="fakehash",
            role="user",
        )
        db_session.add(user)
        users.append(user)
    db_session.commit()
    for u in users:
        db_session.refresh(u)
    return users


# ---------------------------------------------------------------------------
# Test 1: Default pagination returns correct structure
# ---------------------------------------------------------------------------

def test_get_all_users_default_pagination(client, db_session):
    """GET /users/all with defaults should return {items, total, page, page_size}."""
    _seed_users(db_session, count=3)

    response = client.get("/users/all")
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data

    assert data["total"] == 3
    assert data["page"] == 1
    assert data["page_size"] == 50  # default
    assert len(data["items"]) == 3


# ---------------------------------------------------------------------------
# Test 2: Custom page and page_size
# ---------------------------------------------------------------------------

def test_custom_page_size(client, db_session):
    """GET /users/all?page_size=2 should return at most 2 items."""
    _seed_users(db_session, count=5)

    response = client.get("/users/all?page_size=2")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) == 2


def test_custom_page(client, db_session):
    """GET /users/all?page=2&page_size=2 should return the second page of results."""
    _seed_users(db_session, count=5)

    response = client.get("/users/all?page=2&page_size=2")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 5
    assert data["page"] == 2
    assert data["page_size"] == 2
    assert len(data["items"]) == 2


def test_last_page_partial_results(client, db_session):
    """Last page should return remaining items (less than page_size)."""
    _seed_users(db_session, count=5)

    response = client.get("/users/all?page=3&page_size=2")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 1  # 5 items, page 3 of size 2 => 1 item


# ---------------------------------------------------------------------------
# Test 3: Boundary conditions
# ---------------------------------------------------------------------------

def test_empty_database(client, db_session):
    """GET /users/all on empty DB should return empty items list with total=0."""
    response = client.get("/users/all")
    assert response.status_code == 200

    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_page_beyond_data(client, db_session):
    """Requesting a page beyond available data should return empty items."""
    _seed_users(db_session, count=3)

    response = client.get("/users/all?page=100&page_size=10")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 3
    assert data["items"] == []


def test_page_zero_rejected(client):
    """page=0 should be rejected (ge=1 validation)."""
    response = client.get("/users/all?page=0")
    assert response.status_code == 422


def test_page_size_over_max_rejected(client):
    """page_size > 100 should be rejected (le=100 validation)."""
    response = client.get("/users/all?page_size=200")
    assert response.status_code == 422


def test_negative_page_rejected(client):
    """Negative page value should be rejected."""
    response = client.get("/users/all?page=-1")
    assert response.status_code == 422
