"""
Tests for notification-service endpoints.

Covers:
- GET  /notifications/{user_id}/unread
- GET  /notifications/{user_id}/full
- PUT  /notifications/{user_id}/mark-as-read
- PUT  /notifications/{user_id}/mark-all-as-read
- POST /notifications/create  (admin only)
- Security: SQL injection, unauthorized access

Note: SSE stream and sse_manager tests were removed in FEAT-050 (WebSocket migration).
See test_websocket.py for WebSocket endpoint and ws_manager tests.
"""

import pytest
from unittest.mock import patch, MagicMock

# ── GET /notifications/{user_id}/unread ──────────────────────────────────

class TestGetUnreadNotifications:

    def test_returns_unread_notifications(self, client, seed_notifications):
        resp = client.get("/notifications/1/unread")
        assert resp.status_code == 200
        data = resp.json()
        items = data["items"]
        assert len(items) == 2
        assert all(n["status"] == "unread" for n in items)
        assert all(n["user_id"] == 1 for n in items)

    def test_returns_empty_when_no_unread(self, client, db_session):
        # user 1 has no notifications — paginated endpoint returns empty list
        resp = client.get("/notifications/1/unread")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_does_not_include_read_notifications(self, client, seed_notifications):
        resp = client.get("/notifications/1/unread")
        messages = [n["message"] for n in resp.json()["items"]]
        assert "Already read" not in messages

    def test_does_not_include_other_users(self, client, seed_notifications):
        resp = client.get("/notifications/1/unread")
        messages = [n["message"] for n in resp.json()["items"]]
        assert "Other user" not in messages

    def test_ordered_by_created_at_asc(self, client, seed_notifications):
        resp = client.get("/notifications/1/unread")
        items = resp.json()["items"]
        assert items[0]["message"] == "First unread"
        assert items[1]["message"] == "Second unread"


# ── GET /notifications/{user_id}/full ────────────────────────────────────

class TestGetAllNotifications:

    def test_returns_all_notifications_for_user(self, client, seed_notifications):
        resp = client.get("/notifications/1/full")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 3  # 2 unread + 1 read for user 1

    def test_includes_both_read_and_unread(self, client, seed_notifications):
        resp = client.get("/notifications/1/full")
        statuses = {n["status"] for n in resp.json()["items"]}
        assert statuses == {"read", "unread"}

    def test_returns_empty_when_user_has_no_notifications(self, client, db_session):
        # user 1 has no notifications at all (no seeded data in this test)
        resp = client.get("/notifications/1/full")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ── PUT /notifications/{user_id}/mark-as-read ────────────────────────────

class TestMarkAsRead:

    def test_marks_specific_notifications_as_read(self, client, seed_notifications):
        # Get unread IDs first
        unread = client.get("/notifications/1/unread").json()["items"]
        first_id = unread[0]["id"]

        resp = client.put(
            "/notifications/1/mark-as-read",
            json=[first_id],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "read"
        assert data[0]["id"] == first_id

    def test_returns_404_when_ids_not_found(self, client, seed_notifications):
        resp = client.put(
            "/notifications/1/mark-as-read",
            json=[99999],
        )
        assert resp.status_code == 404

    def test_does_not_mark_already_read(self, client, seed_notifications):
        # Find the "Already read" notification
        all_notifs = client.get("/notifications/1/full").json()["items"]
        read_notif = [n for n in all_notifs if n["status"] == "read"][0]

        resp = client.put(
            "/notifications/1/mark-as-read",
            json=[read_notif["id"]],
        )
        # Already-read notification won't match the filter (status == "unread"), so 404
        assert resp.status_code == 404

    def test_does_not_mark_other_users_notifications(self, client, seed_notifications):
        # Notification for user_id=2
        resp = client.put(
            "/notifications/1/mark-as-read",
            json=[seed_notifications[3].id],  # user_id=2 notification
        )
        assert resp.status_code == 404


# ── PUT /notifications/{user_id}/mark-all-as-read ────────────────────────

class TestMarkAllAsRead:

    def test_marks_all_unread_as_read(self, client, seed_notifications):
        resp = client.put("/notifications/1/mark-all-as-read")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert all(n["status"] == "read" for n in data)

    def test_returns_404_when_no_unread_to_mark(self, client, seed_notifications):
        # Mark all first
        client.put("/notifications/1/mark-all-as-read")
        # Try again — no unread left
        resp = client.put("/notifications/1/mark-all-as-read")
        assert resp.status_code == 404

    def test_does_not_affect_other_users(self, client, db_session, seed_notifications):
        client.put("/notifications/1/mark-all-as-read")
        # user 2's notification should still be unread
        from models import Notification
        other = db_session.query(Notification).filter(
            Notification.user_id == 2
        ).first()
        assert other.status == "unread"


# ── POST /notifications/create ───────────────────────────────────────────

class TestCreateNotification:

    @patch("main.pika")
    def test_admin_can_create_notification(self, mock_pika, admin_client):
        mock_conn = MagicMock()
        mock_channel = MagicMock()
        mock_pika.BlockingConnection.return_value = mock_conn
        mock_conn.channel.return_value = mock_channel

        resp = admin_client.post(
            "/notifications/create",
            json={
                "target_type": "user",
                "target_value": 1,
                "message": "Test admin notification",
            },
        )
        assert resp.status_code == 200
        assert "sent to queue" in resp.json()["detail"].lower()
        mock_channel.basic_publish.assert_called_once()

    def test_non_admin_gets_403(self, client):
        resp = client.post(
            "/notifications/create",
            json={
                "target_type": "all",
                "message": "Should be forbidden",
            },
        )
        assert resp.status_code == 403
        assert "прав" in resp.json()["detail"].lower()

    @patch("main.pika")
    def test_create_with_target_type_all(self, mock_pika, admin_client):
        mock_conn = MagicMock()
        mock_channel = MagicMock()
        mock_pika.BlockingConnection.return_value = mock_conn
        mock_conn.channel.return_value = mock_channel

        resp = admin_client.post(
            "/notifications/create",
            json={"target_type": "all", "message": "Broadcast"},
        )
        assert resp.status_code == 200

    def test_create_missing_message_returns_422(self, admin_client):
        resp = admin_client.post(
            "/notifications/create",
            json={"target_type": "user", "target_value": 1},
        )
        assert resp.status_code == 422

    def test_create_invalid_target_type_returns_422(self, admin_client):
        resp = admin_client.post(
            "/notifications/create",
            json={"target_type": "invalid_type", "message": "test"},
        )
        assert resp.status_code == 422


# ── Security tests ───────────────────────────────────────────────────────

class TestSecurity:

    def test_sql_injection_in_user_id(self, client):
        """SQL injection attempt in user_id path parameter does not crash."""
        resp = client.get("/notifications/1 OR 1=1/unread")
        # FastAPI validates user_id as int → 422
        assert resp.status_code == 422

    def test_sql_injection_in_notification_ids(self, client, seed_notifications):
        """Malformed notification_ids body does not crash the service."""
        resp = client.put(
            "/notifications/1/mark-as-read",
            json=["'; DROP TABLE notifications; --"],
        )
        assert resp.status_code == 422

    def test_xss_in_message_stored_safely(self, db_session):
        """XSS payload in message is stored as-is (no server-side execution)."""
        from models import Notification
        xss = '<script>alert("xss")</script>'
        n = Notification(user_id=1, message=xss, status="unread")
        db_session.add(n)
        db_session.commit()
        db_session.refresh(n)
        assert n.message == xss  # stored verbatim — frontend must escape

    def test_negative_user_id(self, client):
        """Negative user_id does not crash."""
        resp = client.get("/notifications/-1/unread")
        # Ownership check returns 403 for mismatched user_id, or 422 for invalid
        assert resp.status_code in (200, 403, 404, 422)

    def test_very_large_user_id(self, client):
        """Very large user_id does not crash."""
        resp = client.get("/notifications/99999999999/unread")
        # Ownership check returns 403 for mismatched user_id
        assert resp.status_code in (200, 403, 404, 422)
