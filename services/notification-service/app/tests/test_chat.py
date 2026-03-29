"""
Tests for chat endpoints (notification-service).

Covers: send message, get messages, delete message, ban/unban, ban status,
rate limiting, and message retention cleanup.
"""

import time
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helper: send a chat message via the API
# ---------------------------------------------------------------------------

def _send_message(client, content="Hello!", channel="general", reply_to_id=None):
    payload = {"channel": channel, "content": content}
    if reply_to_id is not None:
        payload["reply_to_id"] = reply_to_id
    return client.post("/notifications/chat/messages", json=payload)


# ---------------------------------------------------------------------------
# 1. Send message
# ---------------------------------------------------------------------------

class TestSendMessage:

    @patch("chat_routes._fetch_user_profile_data", return_value={"avatar": None, "avatar_frame": None, "chat_background": None})
    @patch("chat_routes.broadcast_to_channel")
    def test_send_message_success(self, mock_broadcast, mock_profile, client):
        """Valid message returns 201 with correct data."""
        # Reset rate limiter for clean state
        import chat_routes
        chat_routes._last_message_time.clear()

        resp = _send_message(client, content="Test message", channel="general")
        assert resp.status_code == 201
        data = resp.json()
        assert data["content"] == "Test message"
        assert data["channel"] == "general"
        assert data["user_id"] == 1
        assert data["username"] == "testuser"
        assert "id" in data
        assert "created_at" in data

    @patch("chat_routes._fetch_user_profile_data", return_value={"avatar": None, "avatar_frame": None, "chat_background": None})
    @patch("chat_routes.broadcast_to_channel")
    def test_send_message_empty_content(self, mock_broadcast, mock_profile, client):
        """Empty content should fail validation."""
        import chat_routes
        chat_routes._last_message_time.clear()

        resp = _send_message(client, content="   ")
        assert resp.status_code == 422

    @patch("chat_routes._fetch_user_profile_data", return_value={"avatar": None, "avatar_frame": None, "chat_background": None})
    @patch("chat_routes.broadcast_to_channel")
    def test_send_message_too_long(self, mock_broadcast, mock_profile, client):
        """Content over 500 chars should fail validation."""
        import chat_routes
        chat_routes._last_message_time.clear()

        long_content = "A" * 501
        resp = _send_message(client, content=long_content)
        assert resp.status_code == 422

    def test_send_message_invalid_channel(self, client):
        """Invalid channel value should fail validation."""
        import chat_routes
        chat_routes._last_message_time.clear()

        resp = client.post("/notifications/chat/messages", json={
            "channel": "invalid_channel",
            "content": "Hello",
        })
        assert resp.status_code == 422

    def test_send_message_no_auth(self, db_session):
        """Request without auth token returns 401."""
        from main import app
        from database import get_db
        from fastapi.testclient import TestClient

        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        # Do NOT override auth — let it call the real dependency (which will fail)
        app.dependency_overrides.pop(
            __import__("auth_http").get_current_user_via_http, None
        )

        unauthenticated_client = TestClient(app)
        resp = unauthenticated_client.post("/notifications/chat/messages", json={
            "channel": "general",
            "content": "Hello",
        })
        # Without a valid token, FastAPI's OAuth2 scheme returns 401
        assert resp.status_code == 401
        app.dependency_overrides.clear()

    @patch("chat_routes._fetch_user_profile_data", return_value={"avatar": None, "avatar_frame": None, "chat_background": None})
    @patch("chat_routes.broadcast_to_channel")
    def test_send_message_banned_user(self, mock_broadcast, mock_profile, client, db_session):
        """Banned user gets 403 when sending a message."""
        import chat_routes
        chat_routes._last_message_time.clear()

        from chat_models import ChatBan
        ban = ChatBan(user_id=1, banned_by=99, reason="Spam")
        db_session.add(ban)
        db_session.commit()

        resp = _send_message(client, content="I am banned")
        assert resp.status_code == 403
        assert "заблокированы" in resp.json()["detail"]

    @patch("chat_routes._fetch_user_profile_data", return_value={"avatar": "https://s3.example.com/avatar.webp", "avatar_frame": "gold", "chat_background": None})
    @patch("chat_routes.broadcast_to_channel")
    def test_send_message_with_avatar(self, mock_broadcast, mock_profile, client):
        """Message includes avatar and avatar_frame from user profile."""
        import chat_routes
        chat_routes._last_message_time.clear()

        resp = _send_message(client, content="With avatar")
        assert resp.status_code == 201
        data = resp.json()
        assert data["avatar"] == "https://s3.example.com/avatar.webp"
        assert data["avatar_frame"] == "gold"

    @patch("chat_routes._fetch_user_profile_data", return_value={"avatar": None, "avatar_frame": None, "chat_background": None})
    @patch("chat_routes.broadcast_to_channel")
    def test_send_message_broadcasts(self, mock_broadcast, mock_profile, client):
        """Sending a message triggers broadcast_to_channel."""
        import chat_routes
        chat_routes._last_message_time.clear()

        resp = _send_message(client, content="Broadcast test", channel="trade")
        assert resp.status_code == 201
        mock_broadcast.assert_called_once()
        call_args = mock_broadcast.call_args
        assert call_args[0][0] == "trade"
        assert call_args[0][1]["type"] == "chat_message"


# ---------------------------------------------------------------------------
# 2. Get messages
# ---------------------------------------------------------------------------

class TestGetMessages:

    @patch("chat_routes._fetch_user_profile_data", return_value={"avatar": None, "avatar_frame": None, "chat_background": None})
    @patch("chat_routes.broadcast_to_channel")
    def test_get_messages_pagination(self, mock_broadcast, mock_profile, client):
        """Pagination returns correct page and page_size."""
        import chat_routes
        chat_routes._last_message_time.clear()

        # Insert 5 messages
        for i in range(5):
            _send_message(client, content=f"Msg {i}", channel="general")
            chat_routes._last_message_time.clear()

        # Get page 1 with page_size=2
        resp = client.get("/notifications/chat/messages?channel=general&page=1&page_size=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["items"]) == 2
        assert data["total"] == 5

        # Get page 3 with page_size=2 (should have 1 item)
        resp = client.get("/notifications/chat/messages?channel=general&page=3&page_size=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1

    def test_get_messages_channel_filter(self, client):
        """Empty channel returns empty list."""
        resp = client.get("/notifications/chat/messages?channel=trade")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @patch("chat_routes._fetch_user_profile_data", return_value={"avatar": None, "avatar_frame": None, "chat_background": None})
    @patch("chat_routes.broadcast_to_channel")
    def test_get_messages_reply_to_included(self, mock_broadcast, mock_profile, client):
        """reply_to nested object included when reply_to_id is set."""
        import chat_routes
        chat_routes._last_message_time.clear()

        # Send original message
        resp1 = _send_message(client, content="Original message", channel="general")
        assert resp1.status_code == 201
        original_id = resp1.json()["id"]

        chat_routes._last_message_time.clear()

        # Send reply
        resp2 = _send_message(client, content="Reply message", channel="general", reply_to_id=original_id)
        assert resp2.status_code == 201

        # Get messages and find the reply
        resp = client.get("/notifications/chat/messages?channel=general")
        assert resp.status_code == 200
        items = resp.json()["items"]
        # Find the reply (newest first, so it should be first)
        reply = next(m for m in items if m["reply_to_id"] is not None)
        assert reply["reply_to"] is not None
        assert reply["reply_to"]["id"] == original_id
        assert reply["reply_to"]["content"] == "Original message"
        assert reply["reply_to"]["username"] == "testuser"

    def test_get_messages_invalid_channel(self, client):
        """Invalid channel parameter returns 422."""
        resp = client.get("/notifications/chat/messages?channel=invalid")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 3. Delete message
# ---------------------------------------------------------------------------

class TestDeleteMessage:

    @patch("chat_routes.broadcast_to_all")
    def test_delete_message_success(self, mock_broadcast_all, admin_client, db_session):
        """Admin can delete a message, returns 200."""
        from chat_models import ChatMessage

        # Insert message directly into DB
        msg = ChatMessage(
            channel="general", user_id=1, username="testuser", content="To be deleted",
        )
        db_session.add(msg)
        db_session.commit()
        db_session.refresh(msg)
        msg_id = msg.id

        # Delete as admin
        resp = admin_client.delete(f"/notifications/chat/messages/{msg_id}")
        assert resp.status_code == 200
        assert "удалено" in resp.json()["detail"]

    @patch("chat_routes.broadcast_to_all")
    def test_delete_message_not_found(self, mock_broadcast_all, admin_client):
        """Deleting non-existent message returns 404."""
        resp = admin_client.delete("/notifications/chat/messages/99999")
        assert resp.status_code == 404

    def test_delete_message_no_permission(self, client, db_session):
        """User without chat:delete gets 403."""
        from chat_models import ChatMessage

        msg = ChatMessage(
            channel="general", user_id=1, username="testuser", content="Protected",
        )
        db_session.add(msg)
        db_session.commit()
        db_session.refresh(msg)
        msg_id = msg.id

        # Try to delete as regular user (no chat:delete permission)
        resp = client.delete(f"/notifications/chat/messages/{msg_id}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 4. Ban / Unban
# ---------------------------------------------------------------------------

class TestBanUnban:

    def test_ban_user_success(self, admin_client):
        """Admin can ban a user, returns 201."""
        resp = admin_client.post("/notifications/chat/bans", json={
            "user_id": 42,
            "reason": "Spam",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["user_id"] == 42
        assert data["banned_by"] == 99
        assert data["reason"] == "Spam"

    def test_ban_user_already_banned(self, admin_client):
        """Banning an already-banned user returns 409."""
        admin_client.post("/notifications/chat/bans", json={
            "user_id": 42,
            "reason": "First ban",
        })
        resp = admin_client.post("/notifications/chat/bans", json={
            "user_id": 42,
            "reason": "Second ban",
        })
        assert resp.status_code == 409

    def test_unban_user_success(self, admin_client):
        """Admin can unban a user."""
        admin_client.post("/notifications/chat/bans", json={"user_id": 42})
        resp = admin_client.delete("/notifications/chat/bans/42")
        assert resp.status_code == 200
        assert "разбанен" in resp.json()["detail"]

    def test_unban_user_not_found(self, admin_client):
        """Unbanning a user who is not banned returns 404."""
        resp = admin_client.delete("/notifications/chat/bans/99999")
        assert resp.status_code == 404

    def test_ban_no_permission(self, client):
        """User without chat:ban permission gets 403."""
        resp = client.post("/notifications/chat/bans", json={
            "user_id": 42,
            "reason": "Spam",
        })
        assert resp.status_code == 403

    def test_unban_no_permission(self, client):
        """User without chat:ban permission gets 403 on unban."""
        resp = client.delete("/notifications/chat/bans/42")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 5. Check ban status
# ---------------------------------------------------------------------------

class TestCheckBanStatus:

    def test_check_ban_banned_user(self, admin_client):
        """Banned user shows is_banned: true."""
        # Ban user 42
        admin_client.post("/notifications/chat/bans", json={
            "user_id": 42,
            "reason": "Bad behavior",
        })

        # Check ban status
        resp = admin_client.get("/notifications/chat/bans/42")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_banned"] is True
        assert data["reason"] == "Bad behavior"

    def test_check_ban_not_banned(self, admin_client):
        """Non-banned user shows is_banned: false."""
        resp = admin_client.get("/notifications/chat/bans/42")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_banned"] is False
        assert data["reason"] is None

    def test_check_own_ban_status(self, client):
        """Regular user can check their own ban status (user_id matches current_user.id=1)."""
        resp = client.get("/notifications/chat/bans/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_banned"] is False

    def test_check_other_ban_status_no_permission(self, client):
        """Regular user cannot check another user's ban status without chat:ban."""
        resp = client.get("/notifications/chat/bans/42")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 6. Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiting:

    @patch("chat_routes._fetch_user_profile_data", return_value={"avatar": None, "avatar_frame": None, "chat_background": None})
    @patch("chat_routes.broadcast_to_channel")
    def test_rate_limit_second_message_within_2_seconds(self, mock_broadcast, mock_profile, client):
        """Second message within 2 seconds returns 429."""
        import chat_routes
        chat_routes._last_message_time.clear()

        resp1 = _send_message(client, content="First message")
        assert resp1.status_code == 201

        # Immediately send second message (within 2s window)
        resp2 = _send_message(client, content="Second message")
        assert resp2.status_code == 429
        assert "Подождите" in resp2.json()["detail"]

    @patch("chat_routes._fetch_user_profile_data", return_value={"avatar": None, "avatar_frame": None, "chat_background": None})
    @patch("chat_routes.broadcast_to_channel")
    def test_rate_limit_after_cooldown(self, mock_broadcast, mock_profile, client):
        """Message after rate limit cooldown succeeds."""
        import chat_routes
        chat_routes._last_message_time.clear()

        resp1 = _send_message(client, content="First")
        assert resp1.status_code == 201

        # Simulate that enough time has passed by manipulating the timestamp
        chat_routes._last_message_time[1] = time.time() - 3.0

        resp2 = _send_message(client, content="Second after cooldown")
        assert resp2.status_code == 201


# ---------------------------------------------------------------------------
# 7. Message retention (cleanup)
# ---------------------------------------------------------------------------

class TestMessageRetention:

    @patch("chat_routes._fetch_user_profile_data", return_value={"avatar": None, "avatar_frame": None, "chat_background": None})
    @patch("chat_routes.broadcast_to_channel")
    def test_cleanup_old_messages(self, mock_broadcast, mock_profile, client, db_session):
        """Oldest messages are deleted when exceeding limit per channel."""
        import chat_routes
        from chat_models import ChatMessage

        # Patch the cleanup limit to a small number for testing
        with patch("chat_routes.chat_crud.cleanup_old_messages") as mock_cleanup:
            # We test the crud function directly instead
            pass

        # Insert messages directly into DB to avoid rate limiting
        for i in range(7):
            msg = ChatMessage(
                channel="general",
                user_id=1,
                username="testuser",
                content=f"Message {i}",
            )
            db_session.add(msg)
        db_session.commit()

        # Verify 7 messages exist
        count_before = db_session.query(ChatMessage).filter(
            ChatMessage.channel == "general"
        ).count()
        assert count_before == 7

        # Run cleanup with limit=5
        import chat_crud
        deleted = chat_crud.cleanup_old_messages(db_session, "general", limit=5)
        assert deleted == 2

        # Verify only 5 remain
        count_after = db_session.query(ChatMessage).filter(
            ChatMessage.channel == "general"
        ).count()
        assert count_after == 5

    def test_cleanup_no_deletion_under_limit(self, db_session):
        """No deletion when message count is under the limit."""
        from chat_models import ChatMessage
        import chat_crud

        # Insert 3 messages
        for i in range(3):
            msg = ChatMessage(
                channel="help",
                user_id=1,
                username="testuser",
                content=f"Help msg {i}",
            )
            db_session.add(msg)
        db_session.commit()

        deleted = chat_crud.cleanup_old_messages(db_session, "help", limit=10)
        assert deleted == 0

        count = db_session.query(ChatMessage).filter(
            ChatMessage.channel == "help"
        ).count()
        assert count == 3


# ---------------------------------------------------------------------------
# 8. Security: SQL injection
# ---------------------------------------------------------------------------

class TestSecurity:

    @patch("chat_routes._fetch_user_profile_data", return_value={"avatar": None, "avatar_frame": None, "chat_background": None})
    @patch("chat_routes.broadcast_to_channel")
    def test_sql_injection_in_message_content(self, mock_broadcast, mock_profile, client):
        """SQL injection attempt in message content should not crash."""
        import chat_routes
        chat_routes._last_message_time.clear()

        resp = _send_message(client, content="'; DROP TABLE chat_messages; --")
        # Should succeed (content is stored safely via ORM)
        assert resp.status_code == 201
        data = resp.json()
        assert "DROP TABLE" in data["content"]
