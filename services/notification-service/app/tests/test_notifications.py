"""
Tests for notification-service endpoints.

Covers:
- GET  /notifications/{user_id}/unread
- GET  /notifications/{user_id}/full
- PUT  /notifications/{user_id}/mark-as-read
- PUT  /notifications/{user_id}/mark-all-as-read
- POST /notifications/create  (admin only)
- GET  /notifications/stream   (SSE, initial connection)
- send_to_sse helper
- Security: SQL injection, unauthorized access
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

    def test_returns_empty_when_no_unread(self, client, seed_notifications):
        # user 3 has no notifications at all — paginated endpoint returns empty list
        resp = client.get("/notifications/3/unread")
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

    def test_returns_empty_when_user_has_no_notifications(self, client, seed_notifications):
        resp = client.get("/notifications/999/full")
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
        assert "admin" in resp.json()["detail"].lower()

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


# ── GET /notifications/stream (SSE) ─────────────────────────────────────

class TestSSEStream:

    @pytest.mark.skip(reason="SSE infinite generator hangs TestClient; needs async test with timeout")
    def test_sse_stream_returns_200_with_auth(self, client):
        """SSE endpoint returns 200 and text/event-stream content type."""
        with client.stream("GET", "/notifications/stream") as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_sse_stream_returns_401_without_auth(self, db_session):
        """Without auth override, the endpoint should reject the request."""
        from main import app
        from database import get_db

        # Only override DB, NOT auth — so real auth dependency runs and fails
        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        # Clear auth override if any
        from auth_http import get_current_user_via_http
        app.dependency_overrides.pop(get_current_user_via_http, None)

        from fastapi.testclient import TestClient
        unauthenticated = TestClient(app)
        resp = unauthenticated.get("/notifications/stream")
        # FastAPI returns 401 when OAuth2PasswordBearer token is missing
        assert resp.status_code in (401, 403)
        app.dependency_overrides.clear()


# ── send_to_sse helper ───────────────────────────────────────────────────

class TestSSEManager:

    def test_send_to_sse_delivers_to_connected_user(self):
        """send_to_sse puts JSON data into the user's asyncio.Queue."""
        import asyncio
        import json
        from sse_manager import connections, send_to_sse

        loop = asyncio.new_event_loop()
        queue = asyncio.Queue()
        connections[42] = queue

        try:
            # send_to_sse uses run_coroutine_threadsafe which needs a running loop
            asyncio.set_event_loop(loop)

            # Run in loop context so run_coroutine_threadsafe works
            async def _test():
                send_to_sse(42, {"msg": "hello"})
                # Give the coroutine a chance to execute
                await asyncio.sleep(0.05)
                assert not queue.empty()
                item = await queue.get()
                assert json.loads(item) == {"msg": "hello"}

            loop.run_until_complete(_test())
        finally:
            connections.pop(42, None)
            loop.close()

    def test_send_to_sse_no_op_for_disconnected_user(self):
        """send_to_sse does nothing if user has no active connection."""
        from sse_manager import connections, send_to_sse

        connections.pop(999, None)
        # Should not raise
        send_to_sse(999, {"msg": "ignored"})


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
        assert resp.status_code in (200, 404, 422)

    def test_very_large_user_id(self, client):
        """Very large user_id does not crash."""
        resp = client.get("/notifications/99999999999/unread")
        assert resp.status_code in (200, 404, 422)
