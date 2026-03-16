"""
Tests for character-attributes-service RabbitMQ consumer (rabbitmq_consumer.py).

Covers:
1. Message processing — correct CRUD calls with correct arguments
2. Idempotency — duplicate messages don't create duplicate attributes
3. Error handling — malformed messages don't crash the consumer
4. Connection handling — start_consumer handles connection errors gracefully
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_message(body_dict: dict) -> MagicMock:
    """Create a mock aio_pika.IncomingMessage."""
    msg = MagicMock()
    msg.body = json.dumps(body_dict).encode()

    @asynccontextmanager
    async def _process():
        yield

    msg.process = _process
    return msg


def _make_raw_message(raw_bytes: bytes) -> MagicMock:
    """Create a mock message with raw bytes."""
    msg = MagicMock()
    msg.body = raw_bytes

    @asynccontextmanager
    async def _process():
        yield

    msg.process = _process
    return msg


# ===========================================================================
# 1. Message processing — calls correct CRUD functions
# ===========================================================================

class TestProcessMessage:
    """Test that process_message creates character attributes correctly."""

    @pytest.mark.asyncio
    async def test_creates_attributes_for_new_character(self):
        """Valid message creates attributes via crud.create_character_attributes."""
        payload = {
            "character_id": 42,
            "attributes": {"strength": 15, "agility": 12, "intelligence": 8},
        }
        msg = _make_message(payload)

        mock_db = MagicMock()

        with (
            patch("rabbitmq_consumer.SessionLocal", return_value=mock_db),
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.models") as mock_models,
            patch("rabbitmq_consumer.schemas") as mock_schemas,
        ):
            # No existing attributes
            mock_db.query.return_value.filter.return_value.first.return_value = None

            from rabbitmq_consumer import process_message
            await process_message(msg)

            # Schema constructed with character_id + attributes
            mock_schemas.CharacterAttributesCreate.assert_called_once_with(
                character_id=42, strength=15, agility=12, intelligence=8,
            )
            # CRUD called with db and schema
            mock_crud.create_character_attributes.assert_called_once()
            args = mock_crud.create_character_attributes.call_args
            assert args[0][0] is mock_db
            mock_db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_default_empty_attributes(self):
        """Message without 'attributes' key defaults to empty dict."""
        payload = {"character_id": 10}
        msg = _make_message(payload)
        mock_db = MagicMock()

        with (
            patch("rabbitmq_consumer.SessionLocal", return_value=mock_db),
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.models"),
            patch("rabbitmq_consumer.schemas") as mock_schemas,
        ):
            mock_db.query.return_value.filter.return_value.first.return_value = None

            from rabbitmq_consumer import process_message
            await process_message(msg)

            # Called with character_id only (no extra kwargs from empty dict)
            mock_schemas.CharacterAttributesCreate.assert_called_once_with(
                character_id=10,
            )
            mock_crud.create_character_attributes.assert_called_once()

    @pytest.mark.asyncio
    async def test_partial_attributes(self):
        """Message with only some attributes passes them correctly."""
        payload = {
            "character_id": 7,
            "attributes": {"strength": 20},
        }
        msg = _make_message(payload)
        mock_db = MagicMock()

        with (
            patch("rabbitmq_consumer.SessionLocal", return_value=mock_db),
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.models"),
            patch("rabbitmq_consumer.schemas") as mock_schemas,
        ):
            mock_db.query.return_value.filter.return_value.first.return_value = None

            from rabbitmq_consumer import process_message
            await process_message(msg)

            mock_schemas.CharacterAttributesCreate.assert_called_once_with(
                character_id=7, strength=20,
            )


# ===========================================================================
# 2. Idempotency — duplicate messages don't create duplicates
# ===========================================================================

class TestIdempotency:

    @pytest.mark.asyncio
    async def test_skips_if_attributes_already_exist(self):
        """If character already has attributes, skip entirely."""
        payload = {
            "character_id": 42,
            "attributes": {"strength": 15},
        }
        msg = _make_message(payload)
        mock_db = MagicMock()

        with (
            patch("rabbitmq_consumer.SessionLocal", return_value=mock_db),
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.models"),
            patch("rabbitmq_consumer.schemas") as mock_schemas,
        ):
            # Existing attributes found
            mock_db.query.return_value.filter.return_value.first.return_value = MagicMock()

            from rabbitmq_consumer import process_message
            await process_message(msg)

            mock_crud.create_character_attributes.assert_not_called()
            mock_schemas.CharacterAttributesCreate.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_message_is_noop(self):
        """Second identical message is a no-op."""
        payload = {"character_id": 42, "attributes": {"strength": 15}}
        mock_db = MagicMock()

        with (
            patch("rabbitmq_consumer.SessionLocal", return_value=mock_db),
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.models"),
            patch("rabbitmq_consumer.schemas"),
        ):
            # First call: no existing attributes
            mock_db.query.return_value.filter.return_value.first.return_value = None

            from rabbitmq_consumer import process_message
            await process_message(_make_message(payload))
            assert mock_crud.create_character_attributes.call_count == 1

            # Second call: attributes now exist
            mock_db.query.return_value.filter.return_value.first.return_value = MagicMock()
            mock_crud.create_character_attributes.reset_mock()

            await process_message(_make_message(payload))
            mock_crud.create_character_attributes.assert_not_called()


# ===========================================================================
# 3. Error handling — malformed messages don't crash
# ===========================================================================

class TestErrorHandling:

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self):
        """Invalid JSON body raises JSONDecodeError (caught by consumer loop)."""
        msg = _make_raw_message(b"not valid json{{{")

        from rabbitmq_consumer import process_message
        with pytest.raises(json.JSONDecodeError):
            await process_message(msg)

    @pytest.mark.asyncio
    async def test_missing_character_id_skips(self):
        """Message without character_id is skipped gracefully."""
        payload = {"attributes": {"strength": 10}}
        msg = _make_message(payload)

        with (
            patch("rabbitmq_consumer.SessionLocal") as mock_session_cls,
            patch("rabbitmq_consumer.crud") as mock_crud,
        ):
            from rabbitmq_consumer import process_message
            await process_message(msg)

            # SessionLocal should NOT be called — early return
            mock_session_cls.assert_not_called()
            mock_crud.create_character_attributes.assert_not_called()

    @pytest.mark.asyncio
    async def test_crud_exception_rolls_back(self):
        """If CRUD raises, the DB session is rolled back and closed."""
        payload = {"character_id": 1, "attributes": {"strength": 10}}
        msg = _make_message(payload)
        mock_db = MagicMock()

        with (
            patch("rabbitmq_consumer.SessionLocal", return_value=mock_db),
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.models"),
            patch("rabbitmq_consumer.schemas"),
        ):
            # Make the query itself fail (before create)
            mock_db.query.side_effect = RuntimeError("DB error")

            from rabbitmq_consumer import process_message
            await process_message(msg)

            mock_db.rollback.assert_called_once()
            mock_db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_schema_validation_error_caught(self):
        """If schema validation fails (e.g. bad attribute value), it's caught."""
        payload = {"character_id": 1, "attributes": {"strength": "not_a_number"}}
        msg = _make_message(payload)
        mock_db = MagicMock()

        with (
            patch("rabbitmq_consumer.SessionLocal", return_value=mock_db),
            patch("rabbitmq_consumer.crud"),
            patch("rabbitmq_consumer.models"),
            patch("rabbitmq_consumer.schemas") as mock_schemas,
        ):
            mock_db.query.return_value.filter.return_value.first.return_value = None
            # Schema constructor raises validation error
            mock_schemas.CharacterAttributesCreate.side_effect = ValueError("validation failed")

            from rabbitmq_consumer import process_message
            # Should not raise — caught by except block
            await process_message(msg)

            mock_db.rollback.assert_called_once()
            mock_db.close.assert_called_once()


# ===========================================================================
# 4. Connection handling — start_consumer handles errors
# ===========================================================================

class TestConnectionHandling:

    @pytest.mark.asyncio
    async def test_reconnects_on_connection_error(self):
        """start_consumer retries after connection failure."""
        call_count = 0

        async def mock_connect_robust(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ConnectionError("RabbitMQ unavailable")
            raise KeyboardInterrupt("stop test")

        with (
            patch("rabbitmq_consumer.aio_pika.connect_robust", side_effect=mock_connect_robust),
            patch("rabbitmq_consumer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            from rabbitmq_consumer import start_consumer
            with pytest.raises(KeyboardInterrupt):
                await start_consumer()

            assert mock_sleep.call_count == 2
            mock_sleep.assert_called_with(5)

    @pytest.mark.asyncio
    async def test_logs_connection_error(self, caplog):
        """Connection errors are logged."""
        call_count = 0

        async def mock_connect_robust(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("test conn error")
            raise KeyboardInterrupt("stop")

        with (
            patch("rabbitmq_consumer.aio_pika.connect_robust", side_effect=mock_connect_robust),
            patch("rabbitmq_consumer.asyncio.sleep", new_callable=AsyncMock),
        ):
            from rabbitmq_consumer import start_consumer
            with caplog.at_level(logging.ERROR), pytest.raises(KeyboardInterrupt):
                await start_consumer()

            assert "RabbitMQ connection error" in caplog.text
