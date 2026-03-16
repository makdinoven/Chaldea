"""
Task 21 — QA for Bug #16: Non-blocking RabbitMQ producer in character-service.

Tests:
1. Publishing does not raise when RabbitMQ is unavailable (graceful degradation).
2. Connection timeout is configured.
3. The producer is truly async (uses aio_pika, not pika.BlockingConnection).
"""

import inspect
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Test 1: Graceful degradation when RabbitMQ is unavailable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_notification_handles_connection_error():
    """
    send_character_approved_notification must NOT raise when RabbitMQ is
    unreachable. It should catch the exception and log a warning.
    """
    from unittest.mock import patch, AsyncMock

    with patch(
        "producer.aio_pika.connect_robust",
        new_callable=AsyncMock,
        side_effect=ConnectionError("RabbitMQ refused connection"),
    ):
        from producer import send_character_approved_notification

        # Must not raise
        await send_character_approved_notification(user_id=1, character_name="TestHero")


@pytest.mark.asyncio
async def test_send_notification_handles_timeout():
    """
    send_character_approved_notification must handle timeout errors gracefully.
    """
    import asyncio
    from unittest.mock import patch, AsyncMock

    with patch(
        "producer.aio_pika.connect_robust",
        new_callable=AsyncMock,
        side_effect=asyncio.TimeoutError("Connection timed out"),
    ):
        from producer import send_character_approved_notification

        # Must not raise
        await send_character_approved_notification(user_id=2, character_name="TimeoutHero")


@pytest.mark.asyncio
async def test_send_notification_handles_generic_exception():
    """
    Any unexpected exception in the producer must be caught and not propagated.
    """
    from unittest.mock import patch, AsyncMock

    with patch(
        "producer.aio_pika.connect_robust",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Unexpected"),
    ):
        from producer import send_character_approved_notification

        # Must not raise
        await send_character_approved_notification(user_id=3, character_name="ErrorHero")


# ---------------------------------------------------------------------------
# Test 2: Connection timeout is configured
# ---------------------------------------------------------------------------

def test_producer_has_timeout_configured():
    """
    The aio_pika.connect_robust call must include a timeout parameter.
    """
    from producer import send_character_approved_notification

    source = inspect.getsource(send_character_approved_notification)

    assert "timeout" in source, (
        "send_character_approved_notification must pass a timeout to "
        "aio_pika.connect_robust()"
    )


def test_timeout_value_is_reasonable():
    """
    The timeout for RabbitMQ connection should be a finite, reasonable value.
    """
    from producer import send_character_approved_notification

    source = inspect.getsource(send_character_approved_notification)

    assert "timeout=5" in source or "timeout = 5" in source, (
        "Connection timeout should be set to 5 seconds"
    )


# ---------------------------------------------------------------------------
# Test 3: Producer is truly async (aio_pika, not pika.BlockingConnection)
# ---------------------------------------------------------------------------

def test_producer_uses_aio_pika():
    """
    character-service producer must use aio_pika (async), not pika.BlockingConnection.
    """
    import producer as producer_mod

    source = inspect.getsource(producer_mod)

    assert "aio_pika" in source, (
        "character-service producer must use aio_pika for async publishing"
    )
    assert "BlockingConnection" not in source, (
        "character-service producer must NOT use pika.BlockingConnection "
        "(it blocks the async event loop)"
    )


def test_send_function_is_async():
    """
    send_character_approved_notification must be an async function (coroutine).
    """
    from producer import send_character_approved_notification

    assert inspect.iscoroutinefunction(send_character_approved_notification), (
        "send_character_approved_notification must be an async function"
    )


def test_producer_uses_connect_robust():
    """
    The producer should use aio_pika.connect_robust (auto-reconnect)
    rather than plain aio_pika.connect.
    """
    from producer import send_character_approved_notification

    source = inspect.getsource(send_character_approved_notification)

    assert "connect_robust" in source, (
        "Producer should use aio_pika.connect_robust for automatic reconnection"
    )


# ---------------------------------------------------------------------------
# Test 4: Successful publish path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_successful_publish():
    """
    When RabbitMQ is available, the producer should publish a message
    to the general_notifications queue with correct payload.
    """
    from unittest.mock import patch, AsyncMock, MagicMock

    mock_exchange = AsyncMock()
    mock_channel = AsyncMock()
    mock_channel.default_exchange = mock_exchange

    mock_connection = AsyncMock()
    mock_connection.channel = AsyncMock(return_value=mock_channel)
    mock_connection.__aenter__ = AsyncMock(return_value=mock_connection)
    mock_connection.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "producer.aio_pika.connect_robust",
        new_callable=AsyncMock,
        return_value=mock_connection,
    ):
        from producer import send_character_approved_notification

        await send_character_approved_notification(user_id=10, character_name="Hero")

    mock_channel.declare_queue.assert_called_once_with(
        "general_notifications", durable=True
    )
    mock_exchange.publish.assert_called_once()
