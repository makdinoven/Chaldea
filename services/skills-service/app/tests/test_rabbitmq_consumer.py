"""
Tests for skills-service RabbitMQ consumer (rabbitmq_consumer.py).

Covers:
1. Message processing — correct CRUD calls with correct arguments
2. Idempotency — duplicate messages don't create duplicate skills
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


@asynccontextmanager
async def _mock_async_session():
    """Mock async_session() context manager yielding a MagicMock."""
    session = MagicMock()
    # Make CRUD coroutines return proper values
    yield session


# ===========================================================================
# 1. Message processing — calls correct CRUD functions
# ===========================================================================

class TestProcessMessage:
    """Test that process_message assigns skills correctly."""

    @pytest.mark.asyncio
    async def test_assigns_skills_to_new_character(self):
        """Valid message assigns skills using existing rank 1."""
        payload = {
            "character_id": 42,
            "skill_ids": [10, 20],
        }
        msg = _make_message(payload)

        mock_db = MagicMock()
        mock_skill_10 = MagicMock(id=10)
        mock_skill_20 = MagicMock(id=20)
        mock_rank_10 = MagicMock(id=100, rank_number=1)
        mock_rank_20 = MagicMock(id=200, rank_number=1)

        with (
            patch("rabbitmq_consumer.async_session") as mock_session_factory,
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.schemas") as mock_schemas,
        ):
            # Setup async session context manager
            @asynccontextmanager
            async def session_cm():
                yield mock_db
            mock_session_factory.return_value = session_cm()

            # No existing skills
            mock_crud.list_character_skills_for_character = AsyncMock(return_value=[])
            # Skills exist
            mock_crud.get_skill = AsyncMock(side_effect=[mock_skill_10, mock_skill_20])
            # Ranks exist (rank 1 present)
            mock_crud.list_skill_ranks_by_skill = AsyncMock(
                side_effect=[[mock_rank_10], [mock_rank_20]]
            )
            mock_crud.create_character_skill = AsyncMock()

            from rabbitmq_consumer import process_message
            await process_message(msg)

            # Should check existing skills
            mock_crud.list_character_skills_for_character.assert_called_once_with(mock_db, 42)
            # Should look up each skill
            assert mock_crud.get_skill.call_count == 2
            # Should create CharacterSkill for each
            assert mock_crud.create_character_skill.call_count == 2
            # Verify schema construction
            mock_schemas.CharacterSkillCreate.assert_any_call(
                character_id=42, skill_rank_id=100,
            )
            mock_schemas.CharacterSkillCreate.assert_any_call(
                character_id=42, skill_rank_id=200,
            )

    @pytest.mark.asyncio
    async def test_creates_rank_1_if_missing(self):
        """If rank 1 doesn't exist for a skill, it is created."""
        payload = {"character_id": 5, "skill_ids": [10]}
        msg = _make_message(payload)
        mock_db = MagicMock()
        mock_skill = MagicMock(id=10)
        mock_new_rank = MagicMock(id=999)

        with (
            patch("rabbitmq_consumer.async_session") as mock_session_factory,
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.schemas") as mock_schemas,
        ):
            @asynccontextmanager
            async def session_cm():
                yield mock_db
            mock_session_factory.return_value = session_cm()

            mock_crud.list_character_skills_for_character = AsyncMock(return_value=[])
            mock_crud.get_skill = AsyncMock(return_value=mock_skill)
            # No ranks for this skill
            mock_crud.list_skill_ranks_by_skill = AsyncMock(return_value=[])
            mock_crud.create_skill_rank = AsyncMock(return_value=mock_new_rank)
            mock_crud.create_character_skill = AsyncMock()

            from rabbitmq_consumer import process_message
            await process_message(msg)

            # Should create rank 1
            mock_schemas.SkillRankCreate.assert_called_once_with(
                skill_id=10, rank_number=1,
            )
            mock_crud.create_skill_rank.assert_called_once()
            # Should use the new rank's id
            mock_schemas.CharacterSkillCreate.assert_called_once_with(
                character_id=5, skill_rank_id=999,
            )

    @pytest.mark.asyncio
    async def test_skips_nonexistent_skill(self):
        """If skill_id doesn't exist in DB, it's skipped."""
        payload = {"character_id": 5, "skill_ids": [999]}
        msg = _make_message(payload)
        mock_db = MagicMock()

        with (
            patch("rabbitmq_consumer.async_session") as mock_session_factory,
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.schemas") as mock_schemas,
        ):
            @asynccontextmanager
            async def session_cm():
                yield mock_db
            mock_session_factory.return_value = session_cm()

            mock_crud.list_character_skills_for_character = AsyncMock(return_value=[])
            mock_crud.get_skill = AsyncMock(return_value=None)

            from rabbitmq_consumer import process_message
            await process_message(msg)

            mock_crud.create_character_skill.assert_not_called()
            mock_schemas.CharacterSkillCreate.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_skill_ids_list(self):
        """Message with empty skill_ids creates nothing."""
        payload = {"character_id": 7, "skill_ids": []}
        msg = _make_message(payload)
        mock_db = MagicMock()

        with (
            patch("rabbitmq_consumer.async_session") as mock_session_factory,
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.schemas"),
        ):
            @asynccontextmanager
            async def session_cm():
                yield mock_db
            mock_session_factory.return_value = session_cm()

            mock_crud.list_character_skills_for_character = AsyncMock(return_value=[])

            from rabbitmq_consumer import process_message
            await process_message(msg)

            mock_crud.create_character_skill.assert_not_called()


# ===========================================================================
# 2. Idempotency — duplicate messages don't create duplicates
# ===========================================================================

class TestIdempotency:

    @pytest.mark.asyncio
    async def test_skips_if_character_already_has_skills(self):
        """If character already has skills, skip entirely."""
        payload = {"character_id": 42, "skill_ids": [1, 2]}
        msg = _make_message(payload)
        mock_db = MagicMock()

        with (
            patch("rabbitmq_consumer.async_session") as mock_session_factory,
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.schemas") as mock_schemas,
        ):
            @asynccontextmanager
            async def session_cm():
                yield mock_db
            mock_session_factory.return_value = session_cm()

            # Existing skills found
            mock_crud.list_character_skills_for_character = AsyncMock(
                return_value=[MagicMock()]
            )

            from rabbitmq_consumer import process_message
            await process_message(msg)

            mock_crud.get_skill.assert_not_called()
            mock_crud.create_character_skill.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_message_is_noop(self):
        """Second identical message is a no-op."""
        payload = {"character_id": 42, "skill_ids": [10]}
        mock_db = MagicMock()
        mock_skill = MagicMock(id=10)
        mock_rank = MagicMock(id=100, rank_number=1)

        with (
            patch("rabbitmq_consumer.async_session") as mock_session_factory,
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.schemas"),
        ):
            # First call: no existing skills
            @asynccontextmanager
            async def session_cm_1():
                yield mock_db
            mock_session_factory.return_value = session_cm_1()
            mock_crud.list_character_skills_for_character = AsyncMock(return_value=[])
            mock_crud.get_skill = AsyncMock(return_value=mock_skill)
            mock_crud.list_skill_ranks_by_skill = AsyncMock(return_value=[mock_rank])
            mock_crud.create_character_skill = AsyncMock()

            from rabbitmq_consumer import process_message
            await process_message(_make_message(payload))
            assert mock_crud.create_character_skill.call_count == 1

            # Second call: skills now exist
            @asynccontextmanager
            async def session_cm_2():
                yield mock_db
            mock_session_factory.return_value = session_cm_2()
            mock_crud.list_character_skills_for_character = AsyncMock(
                return_value=[MagicMock()]
            )
            mock_crud.create_character_skill.reset_mock()

            await process_message(_make_message(payload))
            mock_crud.create_character_skill.assert_not_called()


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
        payload = {"skill_ids": [1, 2]}
        msg = _make_message(payload)

        with (
            patch("rabbitmq_consumer.async_session") as mock_session_factory,
            patch("rabbitmq_consumer.crud") as mock_crud,
        ):
            from rabbitmq_consumer import process_message
            await process_message(msg)

            # async_session should NOT be entered — early return
            mock_crud.list_character_skills_for_character.assert_not_called()

    @pytest.mark.asyncio
    async def test_crud_exception_is_caught(self):
        """If CRUD raises, exception is caught and logged (no crash)."""
        payload = {"character_id": 1, "skill_ids": [1]}
        msg = _make_message(payload)
        mock_db = MagicMock()

        with (
            patch("rabbitmq_consumer.async_session") as mock_session_factory,
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.schemas"),
        ):
            @asynccontextmanager
            async def session_cm():
                yield mock_db
            mock_session_factory.return_value = session_cm()

            mock_crud.list_character_skills_for_character = AsyncMock(
                side_effect=RuntimeError("DB error")
            )

            from rabbitmq_consumer import process_message
            # Should not raise — exception caught inside process_message
            await process_message(msg)

    @pytest.mark.asyncio
    async def test_missing_skill_ids_defaults_to_empty(self):
        """Message without 'skill_ids' key defaults to empty list."""
        payload = {"character_id": 99}
        msg = _make_message(payload)
        mock_db = MagicMock()

        with (
            patch("rabbitmq_consumer.async_session") as mock_session_factory,
            patch("rabbitmq_consumer.crud") as mock_crud,
            patch("rabbitmq_consumer.schemas"),
        ):
            @asynccontextmanager
            async def session_cm():
                yield mock_db
            mock_session_factory.return_value = session_cm()

            mock_crud.list_character_skills_for_character = AsyncMock(return_value=[])

            from rabbitmq_consumer import process_message
            await process_message(msg)

            mock_crud.create_character_skill.assert_not_called()


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
