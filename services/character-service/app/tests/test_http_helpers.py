"""
Tests for HTTP helper functions in character-service crud.py and main.py.

Verifies that after FEAT-005 refactor:
1. httpx.RequestError is caught and returns the expected fallback (None/False)
2. Non-network exceptions (TypeError, ValueError) propagate upward (NOT caught)
3. Logger is called on network errors

Functions tested (crud.py):
- send_equipment_slots_request
- send_inventory_request
- send_skills_request
- send_attributes_request
- assign_character_to_user
- get_character_experience
- send_skills_presets_request

Functions tested (main.py):
- update_user_with_character
- get_character_profile (inline httpx call to user-service)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request_error(message="Connection refused"):
    """Create an httpx.RequestError with a dummy request."""
    request = httpx.Request("GET", "http://test")
    return httpx.RequestError(message, request=request)


def _make_mock_response(status_code=200, json_data=None, text=""):
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# 1. send_equipment_slots_request
# ---------------------------------------------------------------------------

class TestSendEquipmentSlotsRequest:
    """Tests for crud.send_equipment_slots_request."""

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_network_error_returns_none(self, mock_client_cls):
        """httpx.RequestError should be caught, function returns None."""
        import crud

        mock_client = AsyncMock()
        mock_client.post.side_effect = _make_request_error()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await crud.send_equipment_slots_request(character_id=1)

        assert result is None

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_non_network_exception_propagates(self, mock_client_cls):
        """Non-httpx exceptions (e.g. TypeError) must propagate upward."""
        import crud

        mock_client = AsyncMock()
        mock_client.post.side_effect = TypeError("unexpected type")
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(TypeError, match="unexpected type"):
            await crud.send_equipment_slots_request(character_id=1)

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_network_error_logs_error(self, mock_client_cls):
        """Verify logger.error is called on network error."""
        import crud

        mock_client = AsyncMock()
        mock_client.post.side_effect = _make_request_error("timeout")
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with patch.object(crud.logger, "error") as mock_log:
            await crud.send_equipment_slots_request(character_id=1)
            mock_log.assert_called_once()

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_success_returns_json(self, mock_client_cls):
        """On 200 response, returns parsed JSON."""
        import crud

        mock_client = AsyncMock()
        mock_response = _make_mock_response(200, {"slots": "created"})
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await crud.send_equipment_slots_request(character_id=1)

        assert result == {"slots": "created"}

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_non_200_returns_none(self, mock_client_cls):
        """On non-200 response, returns None."""
        import crud

        mock_client = AsyncMock()
        mock_response = _make_mock_response(500, text="Internal Server Error")
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await crud.send_equipment_slots_request(character_id=1)

        assert result is None


# ---------------------------------------------------------------------------
# 2. send_inventory_request
# ---------------------------------------------------------------------------

class TestSendInventoryRequest:
    """Tests for crud.send_inventory_request."""

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_network_error_returns_none(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_client.post.side_effect = _make_request_error()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await crud.send_inventory_request(character_id=1, items=[])

        assert result is None

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_non_network_exception_propagates(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_client.post.side_effect = ValueError("bad value")
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(ValueError, match="bad value"):
            await crud.send_inventory_request(character_id=1, items=[])

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_network_error_logs_error(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_client.post.side_effect = _make_request_error()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with patch.object(crud.logger, "error") as mock_log:
            await crud.send_inventory_request(character_id=1, items=[])
            mock_log.assert_called_once()


# ---------------------------------------------------------------------------
# 3. send_skills_request
# ---------------------------------------------------------------------------

class TestSendSkillsRequest:
    """Tests for crud.send_skills_request."""

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_network_error_returns_none(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_client.post.side_effect = _make_request_error()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await crud.send_skills_request(character_id=1)

        assert result is None

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_non_network_exception_propagates(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_client.post.side_effect = TypeError("wrong type")
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(TypeError, match="wrong type"):
            await crud.send_skills_request(character_id=1)

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_network_error_logs_error(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_client.post.side_effect = _make_request_error()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with patch.object(crud.logger, "error") as mock_log:
            await crud.send_skills_request(character_id=1)
            mock_log.assert_called_once()


# ---------------------------------------------------------------------------
# 4. send_attributes_request
# ---------------------------------------------------------------------------

class TestSendAttributesRequest:
    """Tests for crud.send_attributes_request."""

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_network_error_returns_none(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_client.post.side_effect = _make_request_error()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await crud.send_attributes_request(
            character_id=1, attributes={"strength": 10}
        )

        assert result is None

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_non_network_exception_propagates(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_client.post.side_effect = ValueError("bad attrs")
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(ValueError, match="bad attrs"):
            await crud.send_attributes_request(
                character_id=1, attributes={"strength": 10}
            )

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_network_error_logs_error(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_client.post.side_effect = _make_request_error()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with patch.object(crud.logger, "error") as mock_log:
            await crud.send_attributes_request(
                character_id=1, attributes={"strength": 10}
            )
            mock_log.assert_called_once()


# ---------------------------------------------------------------------------
# 5. assign_character_to_user
# ---------------------------------------------------------------------------

class TestAssignCharacterToUser:
    """Tests for crud.assign_character_to_user."""

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_network_error_returns_false(self, mock_client_cls):
        """httpx.RequestError should be caught, function returns False."""
        import crud

        mock_client = AsyncMock()
        mock_client.post.side_effect = _make_request_error()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await crud.assign_character_to_user(user_id=1, character_id=1)

        assert result is False

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_non_network_exception_propagates(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_client.post.side_effect = TypeError("unexpected")
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(TypeError, match="unexpected"):
            await crud.assign_character_to_user(user_id=1, character_id=1)

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_network_error_logs_error(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_client.post.side_effect = _make_request_error()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with patch.object(crud.logger, "error") as mock_log:
            await crud.assign_character_to_user(user_id=1, character_id=1)
            mock_log.assert_called_once()

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_success_returns_true(self, mock_client_cls):
        """When both POST and PUT return 200, function returns True."""
        import crud

        mock_client = AsyncMock()
        post_response = _make_mock_response(200)
        put_response = _make_mock_response(200)
        mock_client.post.return_value = post_response
        mock_client.put.return_value = put_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await crud.assign_character_to_user(user_id=1, character_id=1)

        assert result is True

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_first_step_failure_returns_false(self, mock_client_cls):
        """When the first POST returns non-200/201, function returns False."""
        import crud

        mock_client = AsyncMock()
        post_response = _make_mock_response(500, text="error")
        mock_client.post.return_value = post_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await crud.assign_character_to_user(user_id=1, character_id=1)

        assert result is False


# ---------------------------------------------------------------------------
# 6. get_character_experience
# ---------------------------------------------------------------------------

class TestGetCharacterExperience:
    """Tests for crud.get_character_experience."""

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_network_error_returns_none(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_client.get.side_effect = _make_request_error()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await crud.get_character_experience(character_id=1)

        assert result is None

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_non_network_exception_propagates(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_client.get.side_effect = TypeError("bad type")
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(TypeError, match="bad type"):
            await crud.get_character_experience(character_id=1)

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_network_error_logs_error(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_client.get.side_effect = _make_request_error()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with patch.object(crud.logger, "error") as mock_log:
            await crud.get_character_experience(character_id=1)
            mock_log.assert_called_once()

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_success_returns_json(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_response = _make_mock_response(200, {"passive_experience": 500})
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await crud.get_character_experience(character_id=1)

        assert result == {"passive_experience": 500}

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_non_200_returns_none(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_response = _make_mock_response(404, text="Not found")
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await crud.get_character_experience(character_id=1)

        assert result is None


# ---------------------------------------------------------------------------
# 7. send_skills_presets_request
# ---------------------------------------------------------------------------

class TestSendSkillsPresetsRequest:
    """Tests for crud.send_skills_presets_request."""

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_network_error_returns_none(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_client.post.side_effect = _make_request_error()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await crud.send_skills_presets_request(
            character_id=1, skill_ids=[1, 2, 3]
        )

        assert result is None

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_non_network_exception_propagates(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_client.post.side_effect = ValueError("bad skill")
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(ValueError, match="bad skill"):
            await crud.send_skills_presets_request(
                character_id=1, skill_ids=[1, 2, 3]
            )

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_network_error_logs_error(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_client.post.side_effect = _make_request_error()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with patch.object(crud.logger, "error") as mock_log:
            await crud.send_skills_presets_request(
                character_id=1, skill_ids=[1, 2, 3]
            )
            mock_log.assert_called_once()

    @pytest.mark.asyncio
    @patch("crud.httpx.AsyncClient")
    async def test_success_returns_json(self, mock_client_cls):
        import crud

        mock_client = AsyncMock()
        mock_response = _make_mock_response(200, {"assigned": 3})
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await crud.send_skills_presets_request(
            character_id=1, skill_ids=[1, 2, 3]
        )

        assert result == {"assigned": 3}


# ---------------------------------------------------------------------------
# 8. update_user_with_character (main.py)
# ---------------------------------------------------------------------------

class TestUpdateUserWithCharacter:
    """Tests for main.update_user_with_character."""

    @pytest.mark.asyncio
    @patch("main.httpx.AsyncClient")
    async def test_network_error_returns_false(self, mock_client_cls):
        """httpx.RequestError should be caught, function returns False."""
        from main import update_user_with_character

        mock_client = AsyncMock()
        mock_client.post.side_effect = _make_request_error()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await update_user_with_character(user_id=1, character_id=1)

        assert result is False

    @pytest.mark.asyncio
    @patch("main.httpx.AsyncClient")
    async def test_non_network_exception_propagates(self, mock_client_cls):
        """Non-httpx exceptions must propagate upward."""
        from main import update_user_with_character

        mock_client = AsyncMock()
        mock_client.post.side_effect = TypeError("unexpected type")
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(TypeError, match="unexpected type"):
            await update_user_with_character(user_id=1, character_id=1)

    @pytest.mark.asyncio
    @patch("main.httpx.AsyncClient")
    async def test_network_error_logs_error(self, mock_client_cls):
        import main

        mock_client = AsyncMock()
        mock_client.post.side_effect = _make_request_error()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with patch.object(main.logger, "error") as mock_log:
            await main.update_user_with_character(user_id=1, character_id=1)
            mock_log.assert_called_once()

    @pytest.mark.asyncio
    @patch("main.httpx.AsyncClient")
    async def test_success_returns_true(self, mock_client_cls):
        """When both POST and PUT return 200, function returns True."""
        from main import update_user_with_character

        mock_client = AsyncMock()
        post_response = _make_mock_response(200)
        put_response = _make_mock_response(200)
        mock_client.post.return_value = post_response
        mock_client.put.return_value = put_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await update_user_with_character(user_id=1, character_id=1)

        assert result is True

    @pytest.mark.asyncio
    @patch("main.httpx.AsyncClient")
    async def test_first_step_failure_returns_false(self, mock_client_cls):
        """When the first POST returns non-200/201, function returns False."""
        from main import update_user_with_character

        mock_client = AsyncMock()
        post_response = _make_mock_response(500, text="error")
        mock_client.post.return_value = post_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await update_user_with_character(user_id=1, character_id=1)

        assert result is False


# ---------------------------------------------------------------------------
# 9. get_character_profile (main.py — inline httpx call to user-service)
# ---------------------------------------------------------------------------

class TestGetCharacterProfile:
    """Tests for GET /{character_id}/profile endpoint.

    The endpoint queries DB for a character, then makes an inline httpx GET
    to user-service to fetch the username. Tests cover:
    - Network error on httpx call → fallback to empty string for user_nickname
    - Success path → returns username from user-service response
    - Non-200 response from user-service → fallback to empty string
    - Character not found → 404
    """

    def _make_mock_character(self, user_id=42, avatar="avatar.webp", name="Артас"):
        """Create a mock Character ORM object."""
        char = MagicMock()
        char.id = 1
        char.user_id = user_id
        char.avatar = avatar
        char.name = name
        char.current_title = None
        return char

    @patch("main.httpx.AsyncClient")
    @patch("main.models")
    def test_network_error_returns_empty_nickname(self, mock_models, mock_client_cls, client, mock_db_session):
        """httpx.RequestError should be caught, user_nickname falls back to empty string."""
        mock_char = self._make_mock_character()
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_char

        mock_client = AsyncMock()
        mock_client.get.side_effect = _make_request_error("Connection refused")
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        response = client.get("/characters/1/profile")

        assert response.status_code == 200
        data = response.json()
        assert data["user_nickname"] == ""
        assert data["character_name"] == "Артас"
        assert data["user_id"] == 42

    @patch("main.httpx.AsyncClient")
    @patch("main.models")
    def test_success_returns_username(self, mock_models, mock_client_cls, client, mock_db_session):
        """On 200 response from user-service, returns username."""
        mock_char = self._make_mock_character()
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_char

        mock_client = AsyncMock()
        mock_response = _make_mock_response(200, {"username": "player1"})
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        response = client.get("/characters/1/profile")

        assert response.status_code == 200
        data = response.json()
        assert data["user_nickname"] == "player1"
        assert data["character_name"] == "Артас"

    @patch("main.httpx.AsyncClient")
    @patch("main.models")
    def test_non_200_response_returns_empty_nickname(self, mock_models, mock_client_cls, client, mock_db_session):
        """When user-service returns non-200, user_nickname falls back to empty string."""
        mock_char = self._make_mock_character()
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_char

        mock_client = AsyncMock()
        mock_response = _make_mock_response(500, text="Internal Server Error")
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        response = client.get("/characters/1/profile")

        assert response.status_code == 200
        data = response.json()
        assert data["user_nickname"] == ""

    @patch("main.models")
    def test_character_not_found_returns_404(self, mock_models, client, mock_db_session):
        """When character doesn't exist, endpoint returns 404."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        response = client.get("/characters/999/profile")

        assert response.status_code == 404

    @patch("main.httpx.AsyncClient")
    @patch("main.models")
    def test_network_error_logs_error(self, mock_models, mock_client_cls, client, mock_db_session):
        """Verify logger.error is called when httpx.RequestError occurs."""
        import main

        mock_char = self._make_mock_character()
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_char

        mock_client = AsyncMock()
        mock_client.get.side_effect = _make_request_error("timeout")
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with patch.object(main.logger, "error") as mock_log:
            response = client.get("/characters/1/profile")

        assert response.status_code == 200
        mock_log.assert_called_once()
