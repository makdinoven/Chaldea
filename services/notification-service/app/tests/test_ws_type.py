"""
Tests for notification-service ws_type extension in general_notification consumer.

Covers:
- Message with ws_type sends structured WS message with custom type
- Message without ws_type sends generic notification (backward compatible)

These tests verify the create_and_send function which handles the ws_type/ws_data
routing in the general_notification consumer.
"""

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

# Ensure app dir is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set env vars before importing any app modules
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")
os.environ.setdefault("DATABASE_URL", "sqlite://")

# Mock pika before importing consumers
sys.modules.setdefault("pika", MagicMock())

from sqlalchemy import create_engine, String
from sqlalchemy.orm import sessionmaker

from database import Base, engine  # noqa: E402

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Patch ENUM columns for SQLite compatibility
from models import Notification as NotificationModel  # noqa: E402

NotificationModel.__table__.c.status.type = String(10)

# Ensure tables exist
Base.metadata.create_all(bind=engine)


# ═══════════════════════════════════════════════════════════════════════════
# Tests for create_and_send with ws_type
# ═══════════════════════════════════════════════════════════════════════════


class TestWsTypeExtension:
    """Tests for ws_type routing in create_and_send."""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        """Create and drop tables for each test."""
        Base.metadata.create_all(bind=engine)
        self.session = TestingSessionLocal()
        yield
        self.session.close()
        Base.metadata.drop_all(bind=engine)

    @patch("consumers.general_notification.send_to_user")
    def test_ws_type_sends_structured_message(self, mock_send_to_user):
        """When ws_type is provided, send structured WS message with that type."""
        from consumers.general_notification import create_and_send

        create_and_send(
            db=self.session,
            user_id=1,
            message="Игрок вызывает вас на бой!",
            ws_type="pvp_invitation",
            ws_data={"invitation_id": 42, "initiator_name": "Воин", "battle_type": "pvp_training"},
        )

        # Verify send_to_user was called
        mock_send_to_user.assert_called_once()
        call_args = mock_send_to_user.call_args
        user_id_arg = call_args[0][0]
        payload_arg = call_args[0][1]

        assert user_id_arg == 1
        assert payload_arg["type"] == "pvp_invitation"
        assert payload_arg["data"]["invitation_id"] == 42
        assert payload_arg["data"]["initiator_name"] == "Воин"
        assert payload_arg["data"]["battle_type"] == "pvp_training"
        # Should also include notification_id and message
        assert "notification_id" in payload_arg["data"]
        assert payload_arg["data"]["message"] == "Игрок вызывает вас на бой!"

    @patch("consumers.general_notification.send_to_user")
    def test_ws_type_with_empty_ws_data(self, mock_send_to_user):
        """When ws_type is provided but ws_data is None, send with empty data dict."""
        from consumers.general_notification import create_and_send

        create_and_send(
            db=self.session,
            user_id=1,
            message="Тестовое сообщение",
            ws_type="custom_type",
            ws_data=None,
        )

        mock_send_to_user.assert_called_once()
        payload = mock_send_to_user.call_args[0][1]
        assert payload["type"] == "custom_type"
        assert "notification_id" in payload["data"]
        assert payload["data"]["message"] == "Тестовое сообщение"

    @patch("consumers.general_notification.send_to_user")
    def test_no_ws_type_sends_generic_notification(self, mock_send_to_user):
        """When ws_type is None, send generic notification format (backward compatible)."""
        from consumers.general_notification import create_and_send

        create_and_send(
            db=self.session,
            user_id=1,
            message="Обычное уведомление",
        )

        mock_send_to_user.assert_called_once()
        payload = mock_send_to_user.call_args[0][1]

        # Generic format: {"type": "notification", "data": {...}}
        assert payload["type"] == "notification"
        assert payload["data"]["user_id"] == 1
        assert payload["data"]["message"] == "Обычное уведомление"
        assert payload["data"]["status"] == "unread"
        assert "id" in payload["data"]
        assert "created_at" in payload["data"]

    @patch("consumers.general_notification.send_to_user")
    def test_notification_persisted_to_db_regardless_of_ws_type(self, mock_send_to_user):
        """Notification is always saved to DB, whether ws_type is provided or not."""
        from consumers.general_notification import create_and_send
        from models import Notification

        # With ws_type
        create_and_send(
            db=self.session,
            user_id=1,
            message="С типом WS",
            ws_type="pvp_invitation",
            ws_data={"invitation_id": 1},
        )

        # Without ws_type
        create_and_send(
            db=self.session,
            user_id=1,
            message="Без типа WS",
        )

        # Both should be in the DB
        notifications = self.session.query(Notification).filter(
            Notification.user_id == 1
        ).all()
        assert len(notifications) == 2
        messages = {n.message for n in notifications}
        assert "С типом WS" in messages
        assert "Без типа WS" in messages

    @patch("consumers.general_notification.send_to_user")
    def test_pvp_battle_start_ws_type(self, mock_send_to_user):
        """Test pvp_battle_start ws_type used for battle start notifications."""
        from consumers.general_notification import create_and_send

        create_and_send(
            db=self.session,
            user_id=5,
            message="Бой с Воин начинается!",
            ws_type="pvp_battle_start",
            ws_data={
                "battle_id": 42,
                "opponent_name": "Воин",
                "battle_type": "pvp_training",
            },
        )

        mock_send_to_user.assert_called_once()
        payload = mock_send_to_user.call_args[0][1]
        assert payload["type"] == "pvp_battle_start"
        assert payload["data"]["battle_id"] == 42
        assert payload["data"]["opponent_name"] == "Воин"
        assert payload["data"]["battle_type"] == "pvp_training"
