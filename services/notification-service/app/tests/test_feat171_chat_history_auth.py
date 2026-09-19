"""
FEAT-171 task 18 (notification-service half) — `GET /notifications/chat/messages`
is closed to guests (§3.4 N1).

Until this feature the whole history of every channel was readable anonymously
through the gateway: usernames, avatars, frames, backgrounds and the full text
of every message, paginated. `POST` and `DELETE` on the same router were
already gated; only the read was open.

The gate is a dedicated dependency, `require_chat_reader`, rather than plain
`get_current_user_via_http`, purely so the refusal message is Russian
(«Войдите в аккаунт, чтобы читать чат») per CLAUDE.md. Both halves matter:
a guest must be refused, and the message must stay Russian — so the text is
pinned here, not just the status code.

What must NOT have changed: an authenticated reader's body, and the two
already-gated writes.
"""

import pytest
from fastapi.testclient import TestClient


HISTORY_URL = "/notifications/chat/messages?channel=general"


def _seed_messages(db_session, count=3):
    from chat_models import ChatMessage

    for i in range(count):
        db_session.add(ChatMessage(
            user_id=1, username="testuser", channel="general",
            content=f"Сообщение {i}",
        ))
    db_session.commit()


@pytest.fixture()
def guest_client(db_session):
    """A client with *no* auth override — the real dependency runs."""
    from database import get_db
    from main import app

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestChatHistoryRequiresLogin:

    def test_a_guest_gets_401(self, guest_client, db_session):
        _seed_messages(db_session)
        r = guest_client.get(HISTORY_URL)
        assert r.status_code == 401, r.text

    def test_the_refusal_is_in_russian(self, guest_client, db_session):
        """CLAUDE.md: user-facing messages are Russian. The bespoke dependency
        exists only for this; if it is ever replaced by the generic one the
        player sees English again."""
        _seed_messages(db_session)
        assert guest_client.get(HISTORY_URL).json()["detail"] == (
            "Войдите в аккаунт, чтобы читать чат"
        )

    def test_the_refusal_carries_the_www_authenticate_header(
        self, guest_client, db_session
    ):
        r = guest_client.get(HISTORY_URL)
        assert r.headers.get("www-authenticate") == "Bearer"

    def test_no_message_content_leaks_in_the_401_body(self, guest_client, db_session):
        _seed_messages(db_session)
        assert "Сообщение" not in guest_client.get(HISTORY_URL).text

    @pytest.mark.parametrize("channel", ["general", "trade", "roleplay"])
    def test_every_channel_is_closed_not_just_general(
        self, guest_client, db_session, channel
    ):
        r = guest_client.get(f"/notifications/chat/messages?channel={channel}")
        # An unknown channel would be 422; a known one must be 401, never 200.
        assert r.status_code in (401, 422), (channel, r.status_code)
        assert r.status_code != 200

    def test_pagination_parameters_do_not_bypass_the_gate(
        self, guest_client, db_session
    ):
        _seed_messages(db_session)
        r = guest_client.get(
            "/notifications/chat/messages?channel=general&page=1&page_size=100"
        )
        assert r.status_code == 401


class TestAuthenticatedReadersAreUnaffected:

    def test_a_logged_in_user_still_reads_the_history(self, client, db_session):
        _seed_messages(db_session, count=3)
        r = client.get(HISTORY_URL)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3

    def test_the_body_shape_is_unchanged(self, client, db_session):
        _seed_messages(db_session, count=1)
        body = client.get(HISTORY_URL).json()
        assert {"items", "total", "page", "page_size"} <= set(body)
        message = body["items"][0]
        assert message["username"] == "testuser"
        assert message["content"] == "Сообщение 0"

    def test_pagination_still_works(self, client, db_session):
        _seed_messages(db_session, count=5)
        body = client.get(
            "/notifications/chat/messages?channel=general&page=1&page_size=2"
        ).json()
        assert body["page"] == 1
        assert body["page_size"] == 2
        assert len(body["items"]) == 2


class TestTheWritesWereNotTouched:
    """§3.4 N1: 'Nothing else in chat_routes.py changes.'"""

    def test_posting_without_a_token_is_still_401(self, guest_client):
        r = guest_client.post(
            "/notifications/chat/messages",
            json={"channel": "general", "content": "Привет"},
        )
        assert r.status_code == 401

    def test_deleting_without_a_token_is_still_401(self, guest_client):
        assert guest_client.delete(
            "/notifications/chat/messages/1"
        ).status_code == 401

    def test_deleting_as_a_plain_user_is_still_403(self, client, db_session):
        _seed_messages(db_session, count=1)
        from chat_models import ChatMessage
        message_id = db_session.query(ChatMessage).first().id
        r = client.delete(f"/notifications/chat/messages/{message_id}")
        assert r.status_code == 403, r.text
