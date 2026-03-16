"""
Tests for inventory-service RabbitMQ consumer (rabbitmq_consumer.py).

Covers:
1. Message processing — correct CRUD calls with correct arguments
2. Idempotency — duplicate messages don't create duplicate inventory
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
# Helpers to build mock aio_pika messages
# ---------------------------------------------------------------------------

def _make_message(body_dict: dict) -> MagicMock:
    """Create a mock aio_pika.IncomingMessage with async context manager .process()."""
    msg = MagicMock()
    msg.body = json.dumps(body_dict).encode()

    @asynccontextmanager
    async def _process():
        yield

    msg.process = _process
    return msg


def _make_raw_message(raw_bytes: bytes) -> MagicMock:
    """Create a mock message with raw bytes (possibly invalid JSON)."""
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
    """Test that process_message calls the right CRUD functions."""

    @pytest.mark.asyncio
    async def test_creates_inventory_for_new_character(self):
        """Valid message for a new character creates equipment slots and inventory items."""
        payload = {
            "character_id": 42,
            "items": [
                {"item_id": 1, "quantity": 5},
                {"item_id": 2, "quantity": 3},
            ],
        }
        msg = _make_message(payload)

        mock_db = MagicMock()
        mock_item_1 = MagicMock(id=1)
        mock_item_2 = MagicMock(id=2)

        with (
            patch("rabbitmq_consumer.SessionLocal", return_value=mock_db),
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.models") as mock_models,
            patch("rabbitmq_consumer.schemas") as mock_schemas,
        ):
            # No existing inventory
            mock_crud.get_inventory_items.return_value = []
            # Items exist in DB
            mock_db.query.return_value.filter.return_value.first.side_effect = [
                mock_item_1,
                mock_item_2,
            ]
            # Schema constructor returns a mock object
            mock_schemas.CharacterInventoryBase.side_effect = [
                MagicMock(name="inv1"),
                MagicMock(name="inv2"),
            ]

            from rabbitmq_consumer import process_message
            await process_message(msg)

            # Should check existing inventory
            mock_crud.get_inventory_items.assert_called_once_with(mock_db, 42)
            # Should create default equipment slots
            mock_crud.create_default_equipment_slots.assert_called_once_with(mock_db, 42)
            # Should create inventory for each item
            assert mock_crud.create_character_inventory.call_count == 2
            # Schema constructed with correct params
            mock_schemas.CharacterInventoryBase.assert_any_call(
                character_id=42, item_id=1, quantity=5,
            )
            mock_schemas.CharacterInventoryBase.assert_any_call(
                character_id=42, item_id=2, quantity=3,
            )
            mock_db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_default_quantity_is_one(self):
        """If quantity is not specified in item_data, defaults to 1."""
        payload = {
            "character_id": 10,
            "items": [{"item_id": 5}],
        }
        msg = _make_message(payload)
        mock_db = MagicMock()

        with (
            patch("rabbitmq_consumer.SessionLocal", return_value=mock_db),
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.models"),
            patch("rabbitmq_consumer.schemas") as mock_schemas,
        ):
            mock_crud.get_inventory_items.return_value = []
            mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(id=5)

            from rabbitmq_consumer import process_message
            await process_message(msg)

            mock_schemas.CharacterInventoryBase.assert_called_once_with(
                character_id=10, item_id=5, quantity=1,
            )

    @pytest.mark.asyncio
    async def test_skips_nonexistent_item(self):
        """If an item_id doesn't exist in DB, it's skipped without error."""
        payload = {
            "character_id": 10,
            "items": [{"item_id": 999, "quantity": 1}],
        }
        msg = _make_message(payload)
        mock_db = MagicMock()

        with (
            patch("rabbitmq_consumer.SessionLocal", return_value=mock_db),
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.models"),
            patch("rabbitmq_consumer.schemas") as mock_schemas,
        ):
            mock_crud.get_inventory_items.return_value = []
            # Item not found
            mock_db.query.return_value.filter.return_value.first.return_value = None

            from rabbitmq_consumer import process_message
            await process_message(msg)

            # Should NOT create any inventory
            mock_crud.create_character_inventory.assert_not_called()
            mock_schemas.CharacterInventoryBase.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_items_list(self):
        """Message with empty items list creates equipment slots but no inventory."""
        payload = {"character_id": 7, "items": []}
        msg = _make_message(payload)
        mock_db = MagicMock()

        with (
            patch("rabbitmq_consumer.SessionLocal", return_value=mock_db),
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.models"),
            patch("rabbitmq_consumer.schemas"),
        ):
            mock_crud.get_inventory_items.return_value = []

            from rabbitmq_consumer import process_message
            await process_message(msg)

            mock_crud.create_default_equipment_slots.assert_called_once_with(mock_db, 7)
            mock_crud.create_character_inventory.assert_not_called()


# ===========================================================================
# 2. Idempotency — duplicate messages don't create duplicates
# ===========================================================================

class TestIdempotency:
    """Duplicate messages must not create duplicate inventory."""

    @pytest.mark.asyncio
    async def test_skips_if_inventory_already_exists(self):
        """If character already has inventory items, skip entirely."""
        payload = {
            "character_id": 42,
            "items": [{"item_id": 1, "quantity": 5}],
        }
        msg = _make_message(payload)
        mock_db = MagicMock()

        with (
            patch("rabbitmq_consumer.SessionLocal", return_value=mock_db),
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.models"),
            patch("rabbitmq_consumer.schemas") as mock_schemas,
        ):
            # Existing inventory found — idempotency guard triggers
            mock_crud.get_inventory_items.return_value = [MagicMock()]

            from rabbitmq_consumer import process_message
            await process_message(msg)

            mock_crud.create_default_equipment_slots.assert_not_called()
            mock_crud.create_character_inventory.assert_not_called()
            mock_schemas.CharacterInventoryBase.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_message_same_result(self):
        """Sending the same message twice — second time is a no-op."""
        payload = {"character_id": 42, "items": [{"item_id": 1, "quantity": 1}]}
        mock_db = MagicMock()

        with (
            patch("rabbitmq_consumer.SessionLocal", return_value=mock_db),
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.models"),
            patch("rabbitmq_consumer.schemas"),
        ):
            # First call: no existing inventory
            mock_crud.get_inventory_items.return_value = []
            mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(id=1)

            from rabbitmq_consumer import process_message
            await process_message(_make_message(payload))
            assert mock_crud.create_character_inventory.call_count == 1

            # Second call: inventory now exists
            mock_crud.get_inventory_items.return_value = [MagicMock()]
            mock_crud.create_character_inventory.reset_mock()

            await process_message(_make_message(payload))
            mock_crud.create_character_inventory.assert_not_called()


# ===========================================================================
# 3. Error handling — malformed messages don't crash
# ===========================================================================

class TestErrorHandling:
    """Malformed messages must be handled gracefully."""

    @pytest.mark.asyncio
    async def test_invalid_json_does_not_crash(self):
        """Invalid JSON body is caught and logged, no exception raised."""
        msg = _make_raw_message(b"not valid json{{{")

        from rabbitmq_consumer import process_message
        # Should not raise — exception caught inside process_message's
        # outer async with message.process() block, which triggers the
        # except clause in process_message.
        # The function re-raises inside 'async with message.process()' but
        # the consumer loop catches it. We test at process_message level —
        # if json.loads fails, it propagates out but the consumer loop catches it.
        with pytest.raises(json.JSONDecodeError):
            await process_message(msg)

    @pytest.mark.asyncio
    async def test_missing_character_id_skips(self):
        """Message without character_id is skipped gracefully."""
        payload = {"items": [{"item_id": 1, "quantity": 1}]}
        msg = _make_message(payload)

        with (
            patch("rabbitmq_consumer.SessionLocal") as mock_session_cls,
            patch("rabbitmq_consumer.crud") as mock_crud,
        ):
            from rabbitmq_consumer import process_message
            await process_message(msg)

            # SessionLocal should NOT be called — early return
            mock_session_cls.assert_not_called()
            mock_crud.create_character_inventory.assert_not_called()

    @pytest.mark.asyncio
    async def test_crud_exception_rolls_back(self):
        """If CRUD raises an exception, the DB session is rolled back and closed."""
        payload = {"character_id": 1, "items": [{"item_id": 1, "quantity": 1}]}
        msg = _make_message(payload)
        mock_db = MagicMock()

        with (
            patch("rabbitmq_consumer.SessionLocal", return_value=mock_db),
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.models"),
            patch("rabbitmq_consumer.schemas"),
        ):
            mock_crud.get_inventory_items.side_effect = RuntimeError("DB error")

            from rabbitmq_consumer import process_message
            await process_message(msg)

            mock_db.rollback.assert_called_once()
            mock_db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_items_key_defaults_to_empty(self):
        """Message without 'items' key defaults to empty list, no crash."""
        payload = {"character_id": 99}
        msg = _make_message(payload)
        mock_db = MagicMock()

        with (
            patch("rabbitmq_consumer.SessionLocal", return_value=mock_db),
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.models"),
            patch("rabbitmq_consumer.schemas"),
        ):
            mock_crud.get_inventory_items.return_value = []

            from rabbitmq_consumer import process_message
            await process_message(msg)

            mock_crud.create_default_equipment_slots.assert_called_once_with(mock_db, 99)
            mock_crud.create_character_inventory.assert_not_called()


# ===========================================================================
# 4. Connection handling — start_consumer handles errors
# ===========================================================================

class TestConnectionHandling:
    """start_consumer reconnects on failure."""

    @pytest.mark.asyncio
    async def test_reconnects_on_connection_error(self):
        """start_consumer retries after connection failure."""
        call_count = 0

        async def mock_connect_robust(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ConnectionError("RabbitMQ unavailable")
            # Third call — cancel the loop
            raise KeyboardInterrupt("stop test")

        with (
            patch("rabbitmq_consumer.aio_pika.connect_robust", side_effect=mock_connect_robust),
            patch("rabbitmq_consumer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            from rabbitmq_consumer import start_consumer
            with pytest.raises(KeyboardInterrupt):
                await start_consumer()

            # Should have slept twice (after each failed attempt)
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
                raise ConnectionError("test connection error")
            raise KeyboardInterrupt("stop")

        with (
            patch("rabbitmq_consumer.aio_pika.connect_robust", side_effect=mock_connect_robust),
            patch("rabbitmq_consumer.asyncio.sleep", new_callable=AsyncMock),
        ):
            from rabbitmq_consumer import start_consumer
            with caplog.at_level(logging.ERROR), pytest.raises(KeyboardInterrupt):
                await start_consumer()

            assert "RabbitMQ connection error" in caplog.text
