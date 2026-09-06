"""
FEAT-154 (task #26) — rejecting a character request with a reason.

Covers rules 28, 30a and 30b:
- the reason is stored on the request and reaches the player's notification
- only a 'pending' request may be rejected (409 otherwise, rule 30a)
- an over-long reason is a 400 with a Russian message, never a bare 422 (rule 30b)
- the AMQP publish carries ws_type / ws_data for the SSE delivery
- RBAC and injection negatives
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import database
from database import Base
import models
import schemas
from auth_http import get_admin_user, get_current_user_via_http, OAUTH2_SCHEME, UserRead
from main import app, get_db


_ADMIN_USER = UserRead(id=1, username="admin", role="admin", permissions=[
    "characters:create", "characters:read", "characters:update",
    "characters:delete", "characters:approve",
])
_PLAIN_USER = UserRead(id=42, username="player", role="user", permissions=[])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session(seed_fk_data):
    Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    seed_fk_data(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=database.engine)


@pytest.fixture
def make_client(db_session):
    def _factory(user=_ADMIN_USER):
        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        if user is not None:
            app.dependency_overrides[get_admin_user] = lambda: user
            app.dependency_overrides[get_current_user_via_http] = lambda: user
            app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"
        else:
            app.dependency_overrides.pop(get_admin_user, None)
            app.dependency_overrides.pop(get_current_user_via_http, None)
            app.dependency_overrides.pop(OAUTH2_SCHEME, None)
        return TestClient(app)

    yield _factory
    app.dependency_overrides.clear()


@pytest.fixture
def client(make_client):
    return make_client(_ADMIN_USER)


@pytest.fixture
def notifier():
    with patch("main.send_character_request_rejected_notification", new_callable=AsyncMock) as mock:
        yield mock


def _seed_request(db, status="pending", **overrides):
    fields = dict(
        user_id=42,
        name="Аэлис",
        id_race=2,
        id_subrace=4,
        id_class=1,
        biography="Био",
        personality="Характер",
        appearance="Высокая эльфийка",
        sex="female",
        age=120,
        avatar="https://example.com/a.webp",
        status=status,
        request_type="creation",
    )
    fields.update(overrides)
    req = models.CharacterRequest(**fields)
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


# ===========================================================================
# Rule 28 — rejection with and without a reason
# ===========================================================================

class TestRejectWithReason:
    def test_reason_is_stored_and_notified(self, db_session, client, notifier):
        req = _seed_request(db_session)
        reason = "Возраст не соответствует подрасе"

        response = client.post(f"/characters/requests/{req.id}/reject", json={"reason": reason})
        assert response.status_code == 200
        assert str(req.id) in response.json()["message"]

        db_session.refresh(req)
        assert req.status == "rejected"
        assert req.rejection_reason == reason

        notifier.assert_awaited_once_with(req.user_id, req.id, reason)

    def test_reject_without_a_body_still_works(self, db_session, client, notifier):
        """Backward compatibility (R3): the body stayed optional."""
        req = _seed_request(db_session)

        response = client.post(f"/characters/requests/{req.id}/reject")
        assert response.status_code == 200

        db_session.refresh(req)
        assert req.status == "rejected"
        assert req.rejection_reason is None
        notifier.assert_awaited_once_with(req.user_id, req.id, None)

    def test_null_reason_is_accepted(self, db_session, client, notifier):
        req = _seed_request(db_session)

        assert client.post(
            f"/characters/requests/{req.id}/reject", json={"reason": None}
        ).status_code == 200
        db_session.refresh(req)
        assert req.rejection_reason is None

    def test_blank_reason_is_normalised_to_none(self, db_session, client, notifier):
        req = _seed_request(db_session)

        assert client.post(
            f"/characters/requests/{req.id}/reject", json={"reason": "   "}
        ).status_code == 200
        db_session.refresh(req)
        assert req.rejection_reason is None

    def test_reason_is_trimmed(self, db_session, client, notifier):
        req = _seed_request(db_session)

        client.post(f"/characters/requests/{req.id}/reject", json={"reason": "  Мало деталей  "})
        db_session.refresh(req)
        assert req.rejection_reason == "Мало деталей"

    def test_notification_failure_does_not_break_the_rejection(self, db_session, client, notifier):
        """The player notification is best effort — RabbitMQ down is not a 500."""
        notifier.side_effect = Exception("RabbitMQ unreachable")
        req = _seed_request(db_session)

        response = client.post(f"/characters/requests/{req.id}/reject", json={"reason": "Нет"})
        assert response.status_code == 200
        db_session.refresh(req)
        assert req.status == "rejected"

    def test_sql_injection_in_reason_is_stored_literally(self, db_session, client, notifier):
        req = _seed_request(db_session)
        payload = "'; DROP TABLE character_requests; --"

        assert client.post(
            f"/characters/requests/{req.id}/reject", json={"reason": payload}
        ).status_code == 200

        db_session.refresh(req)
        assert req.rejection_reason == payload
        assert db_session.query(models.CharacterRequest).count() == 1


# ===========================================================================
# Rule 30a — only a pending request may be rejected
# ===========================================================================

class TestRejectStatusGuard:
    def test_approved_request_returns_409(self, db_session, client, notifier):
        """Without this guard an approved request could be flipped to rejected
        while its character stayed alive and attached to it."""
        req = _seed_request(db_session, status="approved")

        response = client.post(f"/characters/requests/{req.id}/reject", json={"reason": "Поздно"})
        assert response.status_code == 409
        assert "ожидающую" in response.json()["detail"]

        db_session.refresh(req)
        assert req.status == "approved"
        assert req.rejection_reason is None
        notifier.assert_not_awaited()

    def test_already_rejected_request_returns_409_and_keeps_its_reason(
        self, db_session, client, notifier
    ):
        req = _seed_request(db_session, status="rejected", rejection_reason="Первая причина")

        response = client.post(
            f"/characters/requests/{req.id}/reject", json={"reason": "Вторая причина"}
        )
        assert response.status_code == 409

        db_session.refresh(req)
        assert req.rejection_reason == "Первая причина"

    def test_unknown_request_returns_404(self, db_session, client, notifier):
        response = client.post("/characters/requests/99999/reject", json={"reason": "Нет"})
        assert response.status_code == 404


# ===========================================================================
# Rule 30b — an over-long reason is 400 (Russian), not 422
# ===========================================================================

class TestRejectReasonLength:
    def test_too_long_reason_returns_400_not_422(self, db_session, client, notifier):
        req = _seed_request(db_session)
        long_reason = "а" * (schemas.MAX_REJECTION_REASON_LENGTH + 1)

        response = client.post(f"/characters/requests/{req.id}/reject", json={"reason": long_reason})
        assert response.status_code == 400, "правило 30b: должен быть 400, а не 422"

        detail = response.json()["detail"]
        assert str(schemas.MAX_REJECTION_REASON_LENGTH) in detail
        assert "Причина отклонения" in detail

        db_session.refresh(req)
        assert req.status == "pending"
        notifier.assert_not_awaited()

    def test_reason_at_the_limit_is_accepted(self, db_session, client, notifier):
        req = _seed_request(db_session)
        reason = "б" * schemas.MAX_REJECTION_REASON_LENGTH

        assert client.post(
            f"/characters/requests/{req.id}/reject", json={"reason": reason}
        ).status_code == 200
        db_session.refresh(req)
        assert len(req.rejection_reason) == schemas.MAX_REJECTION_REASON_LENGTH

    def test_length_check_runs_before_the_status_check(self, db_session, client, notifier):
        """Ordering is deliberate: a malformed body is a 400 whatever the status."""
        req = _seed_request(db_session, status="approved")
        long_reason = "а" * (schemas.MAX_REJECTION_REASON_LENGTH + 1)

        response = client.post(f"/characters/requests/{req.id}/reject", json={"reason": long_reason})
        assert response.status_code == 400


# ===========================================================================
# RBAC
# ===========================================================================

class TestRejectAuthorization:
    def test_unauthenticated_returns_401(self, db_session, make_client, notifier):
        req = _seed_request(db_session)
        response = make_client(None).post(f"/characters/requests/{req.id}/reject")
        assert response.status_code == 401

    def test_user_without_characters_approve_returns_403(self, db_session, make_client, notifier):
        req = _seed_request(db_session)
        response = make_client(_PLAIN_USER).post(
            f"/characters/requests/{req.id}/reject", json={"reason": "Нет"}
        )
        assert response.status_code == 403

        db_session.refresh(req)
        assert req.status == "pending"

    def test_moderator_with_the_permission_may_reject(self, db_session, make_client, notifier):
        moderator = UserRead(
            id=5, username="mod", role="moderator", permissions=["characters:approve"]
        )
        req = _seed_request(db_session)

        response = make_client(moderator).post(
            f"/characters/requests/{req.id}/reject", json={"reason": "Не подходит"}
        )
        assert response.status_code == 200


# ===========================================================================
# The AMQP publish itself
# ===========================================================================

class TestRejectionNotificationPublish:
    @pytest.mark.asyncio
    @patch("producer.aio_pika")
    async def test_publish_carries_reason_and_ws_payload(self, mock_aio_pika):
        from producer import send_character_request_rejected_notification

        mock_channel = AsyncMock()
        mock_connection = AsyncMock()
        mock_connection.channel.return_value = mock_channel
        mock_connection.__aenter__ = AsyncMock(return_value=mock_connection)
        mock_connection.__aexit__ = AsyncMock(return_value=False)
        mock_aio_pika.connect_robust = AsyncMock(return_value=mock_connection)
        mock_aio_pika.DeliveryMode.PERSISTENT = 2
        mock_aio_pika.Message.return_value = MagicMock()
        mock_channel.default_exchange = AsyncMock()

        await send_character_request_rejected_notification(
            user_id=42, request_id=12, reason="Возраст не соответствует подрасе"
        )

        mock_channel.declare_queue.assert_called_once_with("general_notifications", durable=True)
        assert mock_channel.default_exchange.publish.call_args[1]["routing_key"] == "general_notifications"

        body = mock_aio_pika.Message.call_args[1]["body"]
        parsed = json.loads(body.decode())
        assert parsed["target_type"] == "user"
        assert parsed["target_value"] == 42
        assert parsed["ws_type"] == "character_request_rejected"
        assert parsed["ws_data"] == {"request_id": 12, "reason": "Возраст не соответствует подрасе"}
        assert "Возраст не соответствует подрасе" in parsed["message"]

    @pytest.mark.asyncio
    @patch("producer.aio_pika")
    async def test_publish_without_reason_uses_the_plain_message(self, mock_aio_pika):
        from producer import send_character_request_rejected_notification

        mock_channel = AsyncMock()
        mock_connection = AsyncMock()
        mock_connection.channel.return_value = mock_channel
        mock_connection.__aenter__ = AsyncMock(return_value=mock_connection)
        mock_connection.__aexit__ = AsyncMock(return_value=False)
        mock_aio_pika.connect_robust = AsyncMock(return_value=mock_connection)
        mock_aio_pika.DeliveryMode.PERSISTENT = 2
        mock_aio_pika.Message.return_value = MagicMock()
        mock_channel.default_exchange = AsyncMock()

        await send_character_request_rejected_notification(user_id=42, request_id=12, reason=None)

        parsed = json.loads(mock_aio_pika.Message.call_args[1]["body"].decode())
        assert parsed["message"] == "Ваша заявка на персонажа отклонена."
        assert parsed["ws_data"]["reason"] is None

    @pytest.mark.asyncio
    @patch("producer.aio_pika")
    async def test_publish_failure_is_swallowed(self, mock_aio_pika):
        from producer import send_character_request_rejected_notification

        mock_aio_pika.connect_robust = AsyncMock(side_effect=Exception("Connection refused"))
        # Must not raise.
        await send_character_request_rejected_notification(user_id=42, request_id=12, reason="x")
