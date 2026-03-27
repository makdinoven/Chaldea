"""
Tests for messenger endpoints (notification-service).

Covers: conversation creation, list conversations, messages (send/get/delete),
read/unread tracking, group operations (add participants, leave),
rate limiting, and security.
"""

import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers: mock payloads for cross-service calls
# ---------------------------------------------------------------------------

_NO_BLOCK = {"is_blocked": False, "blocked_by_me": False, "blocked_by_them": False}
_BLOCKED_BY_ME = {"is_blocked": True, "blocked_by_me": True, "blocked_by_them": False}
_BLOCKED_BY_THEM = {"is_blocked": True, "blocked_by_me": False, "blocked_by_them": True}
_PROFILE = {"username": "player2", "avatar": None, "avatar_frame": None}


def _mock_cross_service_defaults():
    """Return a dict of patch targets -> return values for typical happy-path mocks."""
    return {
        "messenger_routes._check_block_status": _NO_BLOCK,
        "messenger_routes._get_message_privacy": "all",
        "messenger_routes._check_friendship": True,
        "messenger_routes._fetch_user_profile": _PROFILE,
        "messenger_routes._get_blocked_user_ids": set(),
        "messenger_routes._enrich_participants": None,  # side_effect handled separately
        "messenger_routes.send_to_user": None,
    }


class _Patches:
    """Context manager that applies all standard messenger cross-service mocks."""

    def __init__(self, **overrides):
        self._targets = _mock_cross_service_defaults()
        self._targets.update(overrides)
        self._patchers = []
        self.mocks = {}

    def __enter__(self):
        for target, rv in self._targets.items():
            if target == "messenger_routes._enrich_participants":
                # enrich_participants modifies the list in-place and returns it
                p = patch(target, side_effect=lambda parts: parts)
            elif rv is None:
                p = patch(target)
            else:
                p = patch(target, return_value=rv)
            mock = p.start()
            self._patchers.append(p)
            short = target.rsplit(".", 1)[-1]
            self.mocks[short] = mock
        return self

    def __exit__(self, *args):
        for p in self._patchers:
            p.stop()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def messenger_client(db_session):
    """TestClient for messenger that also overrides OAUTH2_SCHEME to return a fake token."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from auth_http import get_current_user_via_http, UserRead, OAUTH2_SCHEME
    from database import get_db
    from main import app
    from fastapi.testclient import TestClient

    # Monkey-patch Conversation.type column to String for SQLite compatibility
    from messenger_models import Conversation
    from sqlalchemy import String as SAString
    Conversation.__table__.c.type.type = SAString(10)

    from database import engine, Base
    Base.metadata.create_all(bind=engine)

    test_user = UserRead(id=1, username="testuser", role="user", permissions=[])

    def override_get_db():
        yield db_session

    def override_auth():
        return test_user

    def override_token():
        return "fake-test-token"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_via_http] = override_auth
    app.dependency_overrides[OAUTH2_SCHEME] = override_token

    yield TestClient(app)
    app.dependency_overrides.clear()



# ---------------------------------------------------------------------------
# Helper: create a conversation via API
# ---------------------------------------------------------------------------

def _create_direct(client, participant_id=2):
    """Helper to create a direct conversation."""
    return client.post("/notifications/messenger/conversations", json={
        "type": "direct",
        "participant_ids": [participant_id],
    })


def _create_group(client, participant_ids=None, title="Test Group"):
    """Helper to create a group conversation."""
    if participant_ids is None:
        participant_ids = [2, 3]
    return client.post("/notifications/messenger/conversations", json={
        "type": "group",
        "participant_ids": participant_ids,
        "title": title,
    })


def _send_msg(client, conversation_id, content="Hello!"):
    """Helper to send a message."""
    return client.post(
        f"/notifications/messenger/conversations/{conversation_id}/messages",
        json={"content": content},
    )


# ===========================================================================
# 1. Conversation creation
# ===========================================================================

class TestCreateConversation:

    def test_create_direct_201(self, messenger_client):
        """Create a direct conversation returns 201."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            resp = _create_direct(messenger_client)
        assert resp.status_code == 201
        data = resp.json()
        assert data["type"] == "direct"
        assert data["created_by"] == 1

    def test_create_direct_returns_existing(self, messenger_client):
        """Creating duplicate direct conversation returns the existing one (200-level)."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            resp1 = _create_direct(messenger_client)
            assert resp1.status_code == 201
            conv_id_1 = resp1.json()["id"]

        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            resp2 = _create_direct(messenger_client)
            # Returns existing conversation — still 201 from the endpoint
            # but the ID should be the same
            conv_id_2 = resp2.json()["id"]

        assert conv_id_1 == conv_id_2

    def test_create_group_201(self, messenger_client):
        """Create a group conversation returns 201."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            resp = _create_group(messenger_client)
        assert resp.status_code == 201
        data = resp.json()
        assert data["type"] == "group"
        assert data["title"] == "Test Group"

    def test_create_group_with_one_participant_becomes_direct(self, messenger_client):
        """Group conversation with 1 participant becomes direct."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            resp = messenger_client.post("/notifications/messenger/conversations", json={
                "type": "group",
                "participant_ids": [2],
            })
        assert resp.status_code == 201
        data = resp.json()
        assert data["type"] == "direct"

    def test_create_conversation_self_only_rejected(self, messenger_client):
        """Cannot create conversation only with self."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            resp = messenger_client.post("/notifications/messenger/conversations", json={
                "type": "direct",
                "participant_ids": [1],  # self
            })
        assert resp.status_code == 400

    def test_create_conversation_blocked_user(self, messenger_client):
        """Creating conversation with a blocked user returns 403."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        with _Patches(**{"messenger_routes._check_block_status": _BLOCKED_BY_ME}) as p:
            resp = _create_direct(messenger_client)
        assert resp.status_code == 403

    def test_create_group_without_title_rejected(self, messenger_client):
        """Group conversation without title is rejected."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            resp = messenger_client.post("/notifications/messenger/conversations", json={
                "type": "group",
                "participant_ids": [2, 3],
            })
        assert resp.status_code == 400
        assert "название" in resp.json()["detail"].lower()


# ===========================================================================
# 2. List conversations
# ===========================================================================

class TestListConversations:

    def test_list_returns_conversations(self, messenger_client, db_session):
        """List returns user's conversations."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            _create_direct(messenger_client)

        with _Patches() as p:
            resp = messenger_client.get("/notifications/messenger/conversations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_list_empty_for_user_with_no_conversations(self, messenger_client, db_session):
        """Empty list for user with no conversations."""
        with _Patches() as p:
            resp = messenger_client.get("/notifications/messenger/conversations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_includes_unread_count(self, messenger_client, db_session):
        """List includes correct unread_count."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()
        messenger_routes._last_message_time.clear()

        # Create conversation
        with _Patches() as p:
            resp = _create_direct(messenger_client)
            conv_id = resp.json()["id"]

        # Insert a message from user 2 directly in DB (simulating a received message)
        from messenger_models import PrivateMessage
        msg = PrivateMessage(
            conversation_id=conv_id,
            sender_id=2,
            content="Hello from user 2",
        )
        db_session.add(msg)
        db_session.commit()

        with _Patches() as p:
            resp = messenger_client.get("/notifications/messenger/conversations")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1
        # Find our conversation
        conv_item = next(i for i in items if i["id"] == conv_id)
        assert conv_item["unread_count"] >= 1


# ===========================================================================
# 3. Messages
# ===========================================================================

class TestGetMessages:

    def test_get_messages_paginated(self, messenger_client, db_session):
        """Get messages returns paginated results."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            resp = _create_direct(messenger_client)
            conv_id = resp.json()["id"]

        # Insert messages directly to avoid rate limiting
        from messenger_models import PrivateMessage
        for i in range(5):
            msg = PrivateMessage(
                conversation_id=conv_id,
                sender_id=1,
                content=f"Message {i}",
            )
            db_session.add(msg)
        db_session.commit()

        with _Patches() as p:
            resp = messenger_client.get(
                f"/notifications/messenger/conversations/{conv_id}/messages?page=1&page_size=2"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["page_size"] == 2

    def test_get_messages_excludes_blocked(self, messenger_client, db_session):
        """Messages from blocked users are excluded."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            resp = _create_direct(messenger_client)
            conv_id = resp.json()["id"]

        # Insert messages from user 2 (who we'll block)
        from messenger_models import PrivateMessage
        msg = PrivateMessage(
            conversation_id=conv_id,
            sender_id=2,
            content="From blocked user",
        )
        db_session.add(msg)
        db_session.commit()

        # Get messages with user 2 blocked
        with _Patches(**{"messenger_routes._get_blocked_user_ids": {2}}) as p:
            resp = messenger_client.get(
                f"/notifications/messenger/conversations/{conv_id}/messages"
            )
        assert resp.status_code == 200
        data = resp.json()
        # The message from user 2 should be excluded
        assert data["total"] == 0

    def test_soft_deleted_messages_shown_with_empty_content(self, messenger_client, db_session):
        """Soft-deleted messages are shown but with empty content."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            resp = _create_direct(messenger_client)
            conv_id = resp.json()["id"]

        # Insert a soft-deleted message
        from messenger_models import PrivateMessage
        msg = PrivateMessage(
            conversation_id=conv_id,
            sender_id=1,
            content="This was deleted",
            deleted_at=datetime.utcnow(),
        )
        db_session.add(msg)
        db_session.commit()

        with _Patches() as p:
            resp = messenger_client.get(
                f"/notifications/messenger/conversations/{conv_id}/messages"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["content"] == ""
        assert data["items"][0]["is_deleted"] is True


class TestSendMessage:

    def test_send_message_201(self, messenger_client, db_session):
        """Send a message returns 201."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()
        messenger_routes._last_message_time.clear()

        with _Patches() as p:
            resp = _create_direct(messenger_client)
            conv_id = resp.json()["id"]

        with _Patches() as p:
            resp = _send_msg(messenger_client, conv_id, "Hello!")
        assert resp.status_code == 201
        data = resp.json()
        assert data["content"] == "Hello!"
        assert data["sender_id"] == 1
        assert data["conversation_id"] == conv_id

    def test_send_message_ws_notification(self, messenger_client, db_session):
        """Sending a message triggers send_to_user for other participants."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()
        messenger_routes._last_message_time.clear()

        with _Patches() as p:
            resp = _create_direct(messenger_client)
            conv_id = resp.json()["id"]

        with _Patches() as p:
            resp = _send_msg(messenger_client, conv_id, "WS test")
            assert resp.status_code == 201
            # send_to_user should be called for user 2 (the other participant)
            ws_mock = p.mocks["send_to_user"]
            assert ws_mock.called
            # Find the call for user 2
            calls = ws_mock.call_args_list
            recipient_ids = [c[0][0] for c in calls]
            assert 2 in recipient_ids

    def test_send_message_rate_limit(self, messenger_client, db_session):
        """Second message within rate limit returns 429."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()
        messenger_routes._last_message_time.clear()

        with _Patches() as p:
            resp = _create_direct(messenger_client)
            conv_id = resp.json()["id"]

        with _Patches() as p:
            resp1 = _send_msg(messenger_client, conv_id, "First")
            assert resp1.status_code == 201

            # Immediately send second message
            resp2 = _send_msg(messenger_client, conv_id, "Second")
            assert resp2.status_code == 429
            assert "Подождите" in resp2.json()["detail"]

    def test_send_message_not_participant(self, messenger_client, db_session):
        """Sending message as non-participant returns 403."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()
        messenger_routes._last_message_time.clear()

        # Create conversation between user 1 and user 3 directly in DB
        import messenger_crud
        conv = messenger_crud.create_conversation(
            db=db_session,
            conversation_type="direct",
            created_by=10,
            participant_ids=[10, 30],
        )
        conv_id = conv.id

        # User 1 (the test user) is NOT a participant of this conversation
        with _Patches() as p:
            resp = messenger_client.post(
                f"/notifications/messenger/conversations/{conv_id}/messages",
                json={"content": "I shouldn't be here"},
            )
        assert resp.status_code == 403

    def test_send_message_strips_html(self, messenger_client, db_session):
        """HTML tags are stripped from message content (XSS prevention)."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()
        messenger_routes._last_message_time.clear()

        with _Patches() as p:
            resp = _create_direct(messenger_client)
            conv_id = resp.json()["id"]

        with _Patches() as p:
            resp = _send_msg(messenger_client, conv_id, "<script>alert('xss')</script>Hello")
        assert resp.status_code == 201
        data = resp.json()
        assert "<script>" not in data["content"]
        assert "Hello" in data["content"]


class TestDeleteMessage:

    def test_delete_own_message(self, messenger_client, db_session):
        """Delete own message returns 200."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()
        messenger_routes._last_message_time.clear()

        with _Patches() as p:
            resp = _create_direct(messenger_client)
            conv_id = resp.json()["id"]

        with _Patches() as p:
            resp = _send_msg(messenger_client, conv_id, "To delete")
            msg_id = resp.json()["id"]

        with _Patches() as p:
            resp = messenger_client.delete(f"/notifications/messenger/messages/{msg_id}")
        assert resp.status_code == 200
        assert "удалено" in resp.json()["detail"].lower()

    def test_delete_others_message_403(self, messenger_client, db_session):
        """Cannot delete another user's message."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            resp = _create_direct(messenger_client)
            conv_id = resp.json()["id"]

        # Insert a message from user 2
        from messenger_models import PrivateMessage
        msg = PrivateMessage(
            conversation_id=conv_id,
            sender_id=2,
            content="Not yours",
        )
        db_session.add(msg)
        db_session.commit()
        db_session.refresh(msg)

        with _Patches() as p:
            resp = messenger_client.delete(f"/notifications/messenger/messages/{msg.id}")
        assert resp.status_code == 403

    def test_delete_nonexistent_message_404(self, messenger_client):
        """Deleting non-existent message returns 404."""
        with _Patches() as p:
            resp = messenger_client.delete("/notifications/messenger/messages/99999")
        assert resp.status_code == 404

    def test_delete_message_ws_notification(self, messenger_client, db_session):
        """Deleting a message triggers WebSocket notification."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()
        messenger_routes._last_message_time.clear()

        with _Patches() as p:
            resp = _create_direct(messenger_client)
            conv_id = resp.json()["id"]

        with _Patches() as p:
            resp = _send_msg(messenger_client, conv_id, "To delete with WS")
            msg_id = resp.json()["id"]

        with _Patches() as p:
            messenger_client.delete(f"/notifications/messenger/messages/{msg_id}")
            ws_mock = p.mocks["send_to_user"]
            assert ws_mock.called
            # Check that the WS event has the correct type
            last_call_data = ws_mock.call_args_list[-1][0][1]
            assert last_call_data["type"] == "private_message_deleted"
            assert last_call_data["data"]["message_id"] == msg_id


# ===========================================================================
# 4. Read / Unread
# ===========================================================================

class TestReadUnread:

    def test_mark_read_updates_last_read_at(self, messenger_client, db_session):
        """Mark conversation read updates last_read_at."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            resp = _create_direct(messenger_client)
            conv_id = resp.json()["id"]

        with _Patches() as p:
            resp = messenger_client.put(f"/notifications/messenger/conversations/{conv_id}/read")
        assert resp.status_code == 200

        # Verify last_read_at is set
        from messenger_models import ConversationParticipant
        participant = db_session.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == conv_id,
            ConversationParticipant.user_id == 1,
        ).first()
        assert participant.last_read_at is not None

    def test_unread_count_correct(self, messenger_client, db_session):
        """Unread count correct across conversations."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        # Create two conversations
        with _Patches() as p:
            resp1 = _create_direct(messenger_client, participant_id=2)
            conv_id_1 = resp1.json()["id"]

        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            resp2 = _create_direct(messenger_client, participant_id=3)
            conv_id_2 = resp2.json()["id"]

        # Insert unread messages from other users
        from messenger_models import PrivateMessage
        for i in range(3):
            db_session.add(PrivateMessage(
                conversation_id=conv_id_1, sender_id=2, content=f"Msg {i}"
            ))
        for i in range(2):
            db_session.add(PrivateMessage(
                conversation_id=conv_id_2, sender_id=3, content=f"Msg {i}"
            ))
        db_session.commit()

        with _Patches() as p:
            resp = messenger_client.get("/notifications/messenger/unread-count")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_unread"] == 5

    def test_mark_read_then_unread_count_decreases(self, messenger_client, db_session):
        """After marking conversation read, unread count for that conversation becomes 0."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            resp = _create_direct(messenger_client)
            conv_id = resp.json()["id"]

        # Insert unread message from user 2
        from messenger_models import PrivateMessage
        db_session.add(PrivateMessage(
            conversation_id=conv_id, sender_id=2, content="Unread msg"
        ))
        db_session.commit()

        # Mark read
        with _Patches() as p:
            messenger_client.put(f"/notifications/messenger/conversations/{conv_id}/read")

        with _Patches() as p:
            resp = messenger_client.get("/notifications/messenger/unread-count")
        assert resp.status_code == 200
        assert resp.json()["total_unread"] == 0

    def test_mark_read_nonparticipant_403(self, messenger_client, db_session):
        """Non-participant cannot mark conversation as read."""
        # Create conversation between user 10 and user 30 directly in DB
        # User 1 (the test user) is NOT a participant
        import messenger_crud
        conv = messenger_crud.create_conversation(
            db=db_session,
            conversation_type="direct",
            created_by=10,
            participant_ids=[10, 30],
        )
        conv_id = conv.id

        with _Patches() as p:
            resp = messenger_client.put(
                f"/notifications/messenger/conversations/{conv_id}/read"
            )
        assert resp.status_code == 403


# ===========================================================================
# 5. Group operations
# ===========================================================================

class TestGroupOperations:

    def test_add_participants_to_group(self, messenger_client, db_session):
        """Add participants to a group conversation returns 200."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            resp = _create_group(messenger_client)
            conv_id = resp.json()["id"]

        with _Patches() as p:
            resp = messenger_client.post(
                f"/notifications/messenger/conversations/{conv_id}/participants",
                json={"user_ids": [4, 5]},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert 4 in data["added"]
        assert 5 in data["added"]

    def test_add_participants_to_direct_rejected(self, messenger_client, db_session):
        """Cannot add participants to a direct conversation."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            resp = _create_direct(messenger_client)
            conv_id = resp.json()["id"]

        with _Patches() as p:
            resp = messenger_client.post(
                f"/notifications/messenger/conversations/{conv_id}/participants",
                json={"user_ids": [3]},
            )
        assert resp.status_code == 400

    def test_leave_group_conversation(self, messenger_client, db_session):
        """Leave a group conversation returns 200."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            resp = _create_group(messenger_client)
            conv_id = resp.json()["id"]

        with _Patches() as p:
            resp = messenger_client.delete(
                f"/notifications/messenger/conversations/{conv_id}/leave"
            )
        assert resp.status_code == 200
        assert "покинули" in resp.json()["detail"].lower()

    def test_leave_direct_conversation_rejected(self, messenger_client, db_session):
        """Cannot leave a direct conversation."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            resp = _create_direct(messenger_client)
            conv_id = resp.json()["id"]

        with _Patches() as p:
            resp = messenger_client.delete(
                f"/notifications/messenger/conversations/{conv_id}/leave"
            )
        assert resp.status_code == 400

    def test_add_existing_participant_skipped(self, messenger_client, db_session):
        """Adding an already-existing participant is skipped, not an error."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()

        with _Patches() as p:
            resp = _create_group(messenger_client)
            conv_id = resp.json()["id"]

        # User 2 is already a participant
        with _Patches() as p:
            resp = messenger_client.post(
                f"/notifications/messenger/conversations/{conv_id}/participants",
                json={"user_ids": [2]},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert 2 in data["skipped"]


# ===========================================================================
# 6. Security
# ===========================================================================

class TestSecurity:

    def test_sql_injection_in_message_content(self, messenger_client, db_session):
        """SQL injection in message content doesn't crash the app."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()
        messenger_routes._last_message_time.clear()

        with _Patches() as p:
            resp = _create_direct(messenger_client)
            conv_id = resp.json()["id"]

        with _Patches() as p:
            resp = _send_msg(messenger_client, conv_id, "'; DROP TABLE private_messages; --")
        assert resp.status_code == 201

    def test_xss_stripped_from_content(self, messenger_client, db_session):
        """HTML/script tags are stripped from message content."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()
        messenger_routes._last_message_time.clear()

        with _Patches() as p:
            resp = _create_direct(messenger_client)
            conv_id = resp.json()["id"]

        with _Patches() as p:
            resp = _send_msg(
                messenger_client, conv_id,
                '<img src=x onerror="alert(1)">safe text'
            )
        assert resp.status_code == 201
        data = resp.json()
        assert "<img" not in data["content"]
        assert "safe text" in data["content"]

    def test_get_messages_nonexistent_conversation(self, messenger_client):
        """Getting messages for non-existent conversation returns 404."""
        with _Patches() as p:
            resp = messenger_client.get(
                "/notifications/messenger/conversations/99999/messages"
            )
        assert resp.status_code == 404

    def test_empty_message_rejected(self, messenger_client, db_session):
        """Empty message content is rejected."""
        import messenger_routes
        messenger_routes._last_conversation_time.clear()
        messenger_routes._last_message_time.clear()

        with _Patches() as p:
            resp = _create_direct(messenger_client)
            conv_id = resp.json()["id"]

        with _Patches() as p:
            resp = _send_msg(messenger_client, conv_id, "   ")
        assert resp.status_code == 422
