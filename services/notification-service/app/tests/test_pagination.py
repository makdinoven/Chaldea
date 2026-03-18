"""
Task 18 — QA for Bug #12: Pagination on notification endpoints.

Endpoints tested:
- GET /notifications/{user_id}/unread
- GET /notifications/{user_id}/full

Tests:
1. Default page/page_size returns correct paginated structure.
2. Custom page/page_size work correctly.
3. Boundary conditions.
"""

import pytest
from datetime import datetime


def _seed_notifications(db_session, user_id=1, count=10, status="unread"):
    """Insert N notifications for a given user."""
    from models import Notification

    items = []
    for i in range(count):
        n = Notification(
            user_id=user_id,
            message=f"Notification {i + 1}",
            status=status,
            created_at=datetime(2026, 1, 1, i, 0),
        )
        db_session.add(n)
        items.append(n)
    db_session.commit()
    for n in items:
        db_session.refresh(n)
    return items


# ===========================================================================
# /notifications/{user_id}/unread
# ===========================================================================

class TestUnreadPagination:
    """Tests for GET /notifications/{user_id}/unread pagination."""

    def test_default_pagination_structure(self, client, db_session):
        """Default request returns {items, total, page, page_size}."""
        _seed_notifications(db_session, user_id=1, count=3, status="unread")

        response = client.get("/notifications/1/unread")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert data["total"] == 3
        assert data["page"] == 1
        assert data["page_size"] == 50
        assert len(data["items"]) == 3

    def test_custom_page_size(self, client, db_session):
        """page_size=2 returns at most 2 items."""
        _seed_notifications(db_session, user_id=1, count=5, status="unread")

        response = client.get("/notifications/1/unread?page_size=2")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2

    def test_second_page(self, client, db_session):
        """page=2&page_size=2 returns the second chunk."""
        _seed_notifications(db_session, user_id=1, count=5, status="unread")

        response = client.get("/notifications/1/unread?page=2&page_size=2")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 5
        assert data["page"] == 2
        assert len(data["items"]) == 2

    def test_only_unread_returned(self, client, db_session):
        """The unread endpoint must not include 'read' notifications."""
        _seed_notifications(db_session, user_id=1, count=3, status="unread")
        _seed_notifications(db_session, user_id=1, count=2, status="read")

        response = client.get("/notifications/1/unread")
        data = response.json()

        assert data["total"] == 3

    def test_empty_result(self, client, db_session):
        """No notifications returns empty items with total=0."""
        response = client.get("/notifications/1/unread")
        data = response.json()

        assert data["items"] == []
        assert data["total"] == 0

    def test_page_beyond_data(self, client, db_session):
        """Page beyond available data returns empty items."""
        _seed_notifications(db_session, user_id=1, count=3, status="unread")

        response = client.get("/notifications/1/unread?page=100")
        data = response.json()

        assert data["total"] == 3
        assert data["items"] == []

    def test_page_zero_rejected(self, client):
        """page=0 should be rejected by validation."""
        response = client.get("/notifications/1/unread?page=0")
        assert response.status_code == 422

    def test_page_size_over_max_rejected(self, client):
        """page_size > 100 should be rejected."""
        response = client.get("/notifications/1/unread?page_size=200")
        assert response.status_code == 422


# ===========================================================================
# /notifications/{user_id}/full
# ===========================================================================

class TestFullPagination:
    """Tests for GET /notifications/{user_id}/full pagination."""

    def test_default_pagination_structure(self, client, db_session):
        """Default request returns paginated structure."""
        _seed_notifications(db_session, user_id=1, count=3, status="unread")
        _seed_notifications(db_session, user_id=1, count=2, status="read")

        response = client.get("/notifications/1/full")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["page_size"] == 50
        assert len(data["items"]) == 5

    def test_custom_page_size(self, client, db_session):
        """page_size=2 limits the result."""
        _seed_notifications(db_session, user_id=1, count=5, status="unread")

        response = client.get("/notifications/1/full?page_size=2")
        data = response.json()

        assert data["total"] == 5
        assert len(data["items"]) == 2

    def test_includes_both_read_and_unread(self, client, db_session):
        """The full endpoint returns notifications of all statuses."""
        _seed_notifications(db_session, user_id=1, count=3, status="unread")
        _seed_notifications(db_session, user_id=1, count=2, status="read")

        response = client.get("/notifications/1/full")
        data = response.json()

        assert data["total"] == 5

    def test_filters_by_user_id(self, client, db_session):
        """Only notifications for the requested user_id are returned."""
        _seed_notifications(db_session, user_id=1, count=3, status="unread")
        _seed_notifications(db_session, user_id=2, count=4, status="unread")

        response = client.get("/notifications/1/full")
        data = response.json()

        assert data["total"] == 3

    def test_empty_result(self, client, db_session):
        """No notifications returns empty items."""
        response = client.get("/notifications/1/full")
        data = response.json()

        assert data["items"] == []
        assert data["total"] == 0
