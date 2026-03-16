"""
Task 21 — QA for Bug #16: Non-blocking RabbitMQ producer in user-service.

Tests:
1. Publishing does not raise exceptions when RabbitMQ is unavailable.
2. Connection timeout is configured (socket_timeout, connection_attempts).
3. send_notification_event is called via BackgroundTasks (non-blocking).
"""

import sys
import os
import inspect
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Test 1: Graceful degradation when RabbitMQ is unavailable
# ---------------------------------------------------------------------------

def test_send_notification_event_handles_connection_error():
    """
    send_notification_event must NOT raise when RabbitMQ is unreachable.
    It should catch the exception and log a warning.
    """
    from producer import send_notification_event

    # Patch the internal _publish_notification to simulate connection failure
    with patch(
        "producer._publish_notification",
        side_effect=ConnectionError("RabbitMQ refused connection"),
    ):
        # Must not raise
        send_notification_event(user_id=42)


def test_send_notification_event_handles_timeout():
    """
    send_notification_event must handle socket timeout errors gracefully.
    """
    import socket
    from producer import send_notification_event

    with patch(
        "producer._publish_notification",
        side_effect=socket.timeout("Connection timed out"),
    ):
        # Must not raise
        send_notification_event(user_id=99)


def test_send_notification_event_handles_generic_exception():
    """
    Any unexpected exception in the producer must be caught.
    """
    from producer import send_notification_event

    with patch(
        "producer._publish_notification",
        side_effect=RuntimeError("Unexpected error"),
    ):
        # Must not raise
        send_notification_event(user_id=1)


# ---------------------------------------------------------------------------
# Test 2: Connection timeout is configured
# ---------------------------------------------------------------------------

def test_connection_parameters_have_timeout():
    """
    _publish_notification must configure socket_timeout, connection_attempts,
    and retry_delay for the BlockingConnection.
    """
    from producer import _publish_notification

    source = inspect.getsource(_publish_notification)

    assert "socket_timeout" in source, (
        "_publish_notification must set socket_timeout on ConnectionParameters"
    )
    assert "connection_attempts" in source, (
        "_publish_notification must set connection_attempts on ConnectionParameters"
    )
    assert "retry_delay" in source, (
        "_publish_notification must set retry_delay on ConnectionParameters"
    )


def test_socket_timeout_is_reasonable():
    """
    The socket_timeout value should be finite and reasonable (not too long).
    """
    from producer import _publish_notification

    source = inspect.getsource(_publish_notification)

    # Verify socket_timeout is set to a small value (5 seconds in the implementation)
    assert "socket_timeout=5" in source or "socket_timeout = 5" in source, (
        "socket_timeout should be set to 5 seconds"
    )


def test_connection_attempts_is_one():
    """
    connection_attempts should be 1 to fail fast instead of retrying.
    """
    from producer import _publish_notification

    source = inspect.getsource(_publish_notification)

    assert "connection_attempts=1" in source or "connection_attempts = 1" in source, (
        "connection_attempts should be 1 for fail-fast behavior"
    )


# ---------------------------------------------------------------------------
# Test 3: send_notification_event is used via BackgroundTasks in register_user
# ---------------------------------------------------------------------------

def test_register_user_uses_background_tasks():
    """
    The register_user endpoint must call send_notification_event via
    BackgroundTasks.add_task() so it does not block the response.
    """
    import main

    source = inspect.getsource(main.register_user)

    assert "background_tasks" in source, (
        "register_user must accept BackgroundTasks parameter"
    )
    assert "add_task" in source, (
        "register_user must use background_tasks.add_task() for non-blocking publish"
    )
    assert "send_notification_event" in source, (
        "register_user must schedule send_notification_event as a background task"
    )


# ---------------------------------------------------------------------------
# Test 4: Successful publish path works
# ---------------------------------------------------------------------------

def test_successful_publish():
    """
    When RabbitMQ is available, _publish_notification should call basic_publish.
    """
    from producer import _publish_notification

    mock_channel = MagicMock()
    mock_connection = MagicMock()
    mock_connection.channel.return_value = mock_channel

    with patch("producer.BlockingConnection", return_value=mock_connection):
        _publish_notification(user_id=7)

    mock_channel.queue_declare.assert_called_once_with(
        queue="user_registration", durable=True
    )
    mock_channel.basic_publish.assert_called_once()
    mock_connection.close.assert_called_once()
