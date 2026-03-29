"""
Tests for chat_background cosmetic field in chat messages (notification-service).

Covers: send message stores chat_background from user profile,
message response includes chat_background, old messages without
chat_background return null.
"""

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _send_message(client, content="Hello!", channel="general", reply_to_id=None):
    payload = {"channel": channel, "content": content}
    if reply_to_id is not None:
        payload["reply_to_id"] = reply_to_id
    return client.post("/notifications/chat/messages", json=payload)


def _clear_rate_limiter():
    """Reset the in-memory rate limiter between test calls."""
    import chat_routes
    chat_routes._last_message_time.clear()


# ---------------------------------------------------------------------------
# 1. Send message stores chat_background from user profile
# ---------------------------------------------------------------------------

class TestSendMessageStoresChatBackground:

    @patch("chat_routes._fetch_user_profile_data", return_value={
        "avatar": None,
        "avatar_frame": None,
        "chat_background": "night-sky",
    })
    @patch("chat_routes.broadcast_to_channel")
    def test_send_message_stores_chat_background(self, mock_broadcast, mock_profile, client, db_session):
        """When _fetch_user_profile_data returns chat_background, it is persisted in the DB."""
        _clear_rate_limiter()

        resp = _send_message(client, content="Background test")
        assert resp.status_code == 201

        # Verify directly in DB
        from chat_models import ChatMessage
        msg = db_session.query(ChatMessage).order_by(ChatMessage.id.desc()).first()
        assert msg is not None
        assert msg.chat_background == "night-sky"

    @patch("chat_routes._fetch_user_profile_data", return_value={
        "avatar": "https://s3.example.com/av.webp",
        "avatar_frame": "gold",
        "chat_background": "fire-gradient",
    })
    @patch("chat_routes.broadcast_to_channel")
    def test_send_message_stores_all_profile_cosmetics(self, mock_broadcast, mock_profile, client, db_session):
        """All three cosmetic fields (avatar, avatar_frame, chat_background) are stored."""
        _clear_rate_limiter()

        resp = _send_message(client, content="Full cosmetics")
        assert resp.status_code == 201

        from chat_models import ChatMessage
        msg = db_session.query(ChatMessage).order_by(ChatMessage.id.desc()).first()
        assert msg.avatar == "https://s3.example.com/av.webp"
        assert msg.avatar_frame == "gold"
        assert msg.chat_background == "fire-gradient"

    @patch("chat_routes._fetch_user_profile_data", return_value={
        "avatar": None,
        "avatar_frame": None,
        "chat_background": None,
    })
    @patch("chat_routes.broadcast_to_channel")
    def test_send_message_stores_null_chat_background(self, mock_broadcast, mock_profile, client, db_session):
        """When user has no chat_background, null is stored in DB."""
        _clear_rate_limiter()

        resp = _send_message(client, content="No background")
        assert resp.status_code == 201

        from chat_models import ChatMessage
        msg = db_session.query(ChatMessage).order_by(ChatMessage.id.desc()).first()
        assert msg.chat_background is None


# ---------------------------------------------------------------------------
# 2. Message response includes chat_background field
# ---------------------------------------------------------------------------

class TestMessageResponseIncludesChatBackground:

    @patch("chat_routes._fetch_user_profile_data", return_value={
        "avatar": None,
        "avatar_frame": None,
        "chat_background": "ocean-deep",
    })
    @patch("chat_routes.broadcast_to_channel")
    def test_send_response_contains_chat_background(self, mock_broadcast, mock_profile, client):
        """POST response JSON includes chat_background value."""
        _clear_rate_limiter()

        resp = _send_message(client, content="Response check")
        assert resp.status_code == 201
        data = resp.json()
        assert "chat_background" in data
        assert data["chat_background"] == "ocean-deep"

    @patch("chat_routes._fetch_user_profile_data", return_value={
        "avatar": None,
        "avatar_frame": None,
        "chat_background": "aurora",
    })
    @patch("chat_routes.broadcast_to_channel")
    def test_get_messages_response_contains_chat_background(self, mock_broadcast, mock_profile, client):
        """GET messages list includes chat_background in each item."""
        _clear_rate_limiter()

        resp = _send_message(client, content="Listed message")
        assert resp.status_code == 201

        get_resp = client.get("/notifications/chat/messages?channel=general")
        assert get_resp.status_code == 200
        items = get_resp.json()["items"]
        assert len(items) >= 1
        assert items[0]["chat_background"] == "aurora"

    @patch("chat_routes._fetch_user_profile_data", return_value={
        "avatar": None,
        "avatar_frame": None,
        "chat_background": "cosmic",
    })
    @patch("chat_routes.broadcast_to_channel")
    def test_broadcast_payload_contains_chat_background(self, mock_broadcast, mock_profile, client):
        """SSE broadcast payload includes chat_background."""
        _clear_rate_limiter()

        resp = _send_message(client, content="Broadcast bg")
        assert resp.status_code == 201

        mock_broadcast.assert_called_once()
        call_args = mock_broadcast.call_args
        broadcast_data = call_args[0][1]["data"]
        assert broadcast_data["chat_background"] == "cosmic"


# ---------------------------------------------------------------------------
# 3. Old messages without chat_background return null
# ---------------------------------------------------------------------------

class TestOldMessagesWithoutChatBackground:

    def test_old_message_without_chat_background_returns_null(self, client, db_session):
        """Messages inserted without chat_background column value return null in API."""
        from chat_models import ChatMessage

        # Simulate an old message (no chat_background set)
        msg = ChatMessage(
            channel="general",
            user_id=1,
            username="testuser",
            content="Old message before cosmetics",
            avatar=None,
            avatar_frame=None,
            # chat_background intentionally not set — defaults to None
        )
        db_session.add(msg)
        db_session.commit()

        get_resp = client.get("/notifications/chat/messages?channel=general")
        assert get_resp.status_code == 200
        items = get_resp.json()["items"]
        assert len(items) >= 1

        old_msg = next(m for m in items if m["content"] == "Old message before cosmetics")
        assert old_msg["chat_background"] is None

    def test_mixed_old_and_new_messages(self, client, db_session):
        """Mix of old (no background) and new (with background) messages returns correct values."""
        from chat_models import ChatMessage

        # Old message without chat_background
        old_msg = ChatMessage(
            channel="trade",
            user_id=1,
            username="testuser",
            content="Old trade message",
        )
        db_session.add(old_msg)

        # New message with chat_background
        new_msg = ChatMessage(
            channel="trade",
            user_id=1,
            username="testuser",
            content="New trade message",
            chat_background="golden-gleam",
        )
        db_session.add(new_msg)
        db_session.commit()

        get_resp = client.get("/notifications/chat/messages?channel=trade")
        assert get_resp.status_code == 200
        items = get_resp.json()["items"]
        assert len(items) == 2

        old = next(m for m in items if m["content"] == "Old trade message")
        new = next(m for m in items if m["content"] == "New trade message")

        assert old["chat_background"] is None
        assert new["chat_background"] == "golden-gleam"


# ---------------------------------------------------------------------------
# 4. Mock _fetch_user_profile_data returns test data with chat_background
# ---------------------------------------------------------------------------

class TestFetchUserProfileDataMocking:

    @patch("chat_routes._fetch_user_profile_data")
    @patch("chat_routes.broadcast_to_channel")
    def test_profile_data_called_with_user_id(self, mock_broadcast, mock_profile, client):
        """_fetch_user_profile_data is called with the current user's ID."""
        _clear_rate_limiter()
        mock_profile.return_value = {
            "avatar": None,
            "avatar_frame": None,
            "chat_background": "steel-gray",
        }

        resp = _send_message(client, content="Profile call check")
        assert resp.status_code == 201

        mock_profile.assert_called_once_with(1)  # test_user has id=1

    @patch("chat_routes._fetch_user_profile_data")
    @patch("chat_routes.broadcast_to_channel")
    def test_profile_data_failure_defaults_chat_background_to_none(self, mock_broadcast, mock_profile, client):
        """If _fetch_user_profile_data returns default (None), chat_background is null."""
        _clear_rate_limiter()
        mock_profile.return_value = {
            "avatar": None,
            "avatar_frame": None,
            "chat_background": None,
        }

        resp = _send_message(client, content="Profile failure")
        assert resp.status_code == 201
        data = resp.json()
        assert data["chat_background"] is None


# ---------------------------------------------------------------------------
# 5. CRUD unit tests for chat_background
# ---------------------------------------------------------------------------

class TestChatCrudBackground:

    def test_create_message_with_chat_background(self, db_session):
        """chat_crud.create_message stores chat_background correctly."""
        import chat_crud
        from chat_schemas import ChatMessageCreate, ChatChannel

        msg_data = ChatMessageCreate(
            channel=ChatChannel.general,
            content="CRUD test",
        )
        msg = chat_crud.create_message(
            db=db_session,
            user_id=1,
            username="testuser",
            avatar=None,
            avatar_frame=None,
            chat_background="purple-mist",
            message_data=msg_data,
        )
        assert msg.chat_background == "purple-mist"
        assert msg.id is not None

    def test_create_message_without_chat_background(self, db_session):
        """chat_crud.create_message works with chat_background=None."""
        import chat_crud
        from chat_schemas import ChatMessageCreate, ChatChannel

        msg_data = ChatMessageCreate(
            channel=ChatChannel.help,
            content="No bg CRUD test",
        )
        msg = chat_crud.create_message(
            db=db_session,
            user_id=1,
            username="testuser",
            avatar=None,
            avatar_frame=None,
            chat_background=None,
            message_data=msg_data,
        )
        assert msg.chat_background is None
        assert msg.id is not None

    def test_get_messages_returns_chat_background(self, db_session):
        """chat_crud.get_messages includes chat_background in returned items."""
        import chat_crud
        from chat_models import ChatMessage

        msg = ChatMessage(
            channel="general",
            user_id=1,
            username="testuser",
            content="Get test",
            chat_background="dark-blue",
        )
        db_session.add(msg)
        db_session.commit()

        result = chat_crud.get_messages(db_session, "general", page=1, page_size=10)
        items = result["items"]
        assert len(items) == 1
        assert items[0].chat_background == "dark-blue"
