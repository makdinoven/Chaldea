"""
Tests for battle-pass tracking in locations-service (FEAT-102, Task #14).

Covers:
1. Character movement triggers fire-and-forget POST to battle-pass track-event
   endpoint with correct payload (user_id, event_type, character_id, metadata).
2. Movement succeeds even if battle-pass-service returns an HTTP error.
3. Movement succeeds even if battle-pass-service is unreachable (connection error).
4. Tracking is skipped entirely when BATTLEPASS_SERVICE_URL is not configured.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

import pytest

from auth_http import get_current_user_via_http, UserRead


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MOCK_USER = UserRead(id=10, username="testuser", role="user", permissions=[])
DESTINATION_LOC_ID = 200
CHARACTER_ID = 42
LONG_CONTENT = "А" * 350  # Above MIN_POST_LENGTH


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _row(*values):
    """Create a mock row that supports index access."""
    row = MagicMock()
    row.__getitem__ = lambda self, i: values[i]
    row.__len__ = lambda self: len(values)
    return row


def _result_with_row(row_data):
    result = MagicMock()
    result.fetchone.return_value = row_data
    return result


def _result_empty():
    result = MagicMock()
    result.fetchone.return_value = None
    return result


def _make_db_for_move():
    """
    Create a mock async DB session that simulates:
    - verify_character_ownership: user_id matches MOCK_USER
    - check_not_in_battle: not in battle
    - neighbor check: destination is adjacent with energy_cost=0
    - destination location lookup for notification: returns a location
    - favorite user ids: empty list
    """
    async def mock_get_db():
        mock_db = AsyncMock()

        async def execute_side_effect(query, params=None):
            query_str = str(query)

            # verify_character_ownership: SELECT user_id FROM characters
            if "user_id" in query_str and "characters" in query_str:
                return _result_with_row(_row(MOCK_USER.id))

            # check_not_in_battle: SELECT b.id FROM battles
            if "battles" in query_str and "battle_participants" in query_str:
                return _result_empty()

            # LocationNeighbor lookup (select from location_neighbors)
            # Return a mock scalars result with a neighbor having energy_cost=0
            if "location_neighbor" in query_str.lower() or "LocationNeighbor" in query_str:
                neighbor = MagicMock()
                neighbor.energy_cost = 0
                scalars_result = MagicMock()
                scalars_result.first.return_value = neighbor
                result = MagicMock()
                result.scalars.return_value = scalars_result
                return result

            # Destination location lookup (for notification section)
            if "Location" in query_str or "location" in query_str.lower():
                loc = MagicMock()
                loc.id = DESTINATION_LOC_ID
                loc.name = "Test Location"
                scalars_result = MagicMock()
                scalars_result.first.return_value = loc
                result = MagicMock()
                result.scalars.return_value = scalars_result
                return result

            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        yield mock_db

    return mock_get_db


def _mock_post_result():
    """Return a mock post object as returned by crud.create_post."""
    mock_post = MagicMock()
    mock_post.id = 1
    mock_post.character_id = CHARACTER_ID
    mock_post.location_id = DESTINATION_LOC_ID
    mock_post.content = LONG_CONTENT
    mock_post.created_at = datetime(2026, 3, 29, 12, 0, 0)
    mock_post.updated_at = datetime(2026, 3, 29, 12, 0, 0)
    mock_post.character_name = "Воин"
    mock_post.character_avatar = None
    mock_post.likes_count = 0
    mock_post.liked_by_me = False
    return mock_post


def _make_httpx_client_mock(bp_response=None, bp_side_effect=None):
    """
    Build an httpx.AsyncClient mock that handles all inter-service calls
    (character-service, attributes-service) plus the battle-pass call.

    bp_response: what the BP POST should return (MagicMock with status_code)
    bp_side_effect: exception to raise on BP POST
    """
    mock_client = AsyncMock()

    async def _post(url, **kwargs):
        # Battle-pass tracking call
        if "battle-pass" in url or "track-event" in url:
            if bp_side_effect:
                raise bp_side_effect
            return bp_response or MagicMock(status_code=200)

        # consume_stamina
        if "consume_stamina" in url:
            return MagicMock(status_code=200)

        return MagicMock(status_code=200)

    async def _put(url, **kwargs):
        # update_location
        if "update_location" in url:
            return MagicMock(status_code=200)

        return MagicMock(status_code=200)

    async def _get(url, **kwargs):
        # character profile
        if "profile" in url:
            resp = MagicMock(status_code=200)
            resp.json.return_value = {
                "current_location_id": 100,
                "character_name": "Воин",
            }
            return resp

        # attributes (stamina)
        if "attributes" in url:
            resp = MagicMock(status_code=200)
            resp.json.return_value = {"current_stamina": 100}
            return resp

        return MagicMock(status_code=200)

    mock_client.post = AsyncMock(side_effect=_post)
    mock_client.put = AsyncMock(side_effect=_put)
    mock_client.get = AsyncMock(side_effect=_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ===========================================================================
# 1. Movement triggers BP tracking with correct payload
# ===========================================================================
class TestBPTrackingPayload:
    """Verify that move_and_post sends the correct payload to BP service."""

    @patch("main.httpx.AsyncClient")
    @patch("crud.get_favorite_user_ids", new_callable=AsyncMock, return_value=[])
    @patch("crud.create_post", new_callable=AsyncMock)
    def test_move_sends_bp_tracking_call(
        self, mock_create_post, mock_fav_ids, mock_client_cls, client
    ):
        """POST /{id}/move_and_post should fire POST to BP track-event."""
        from database import get_db
        from main import app
        import config

        mock_create_post.return_value = _mock_post_result()

        bp_response = MagicMock(status_code=200)
        bp_calls = []

        real_client = _make_httpx_client_mock(bp_response=bp_response)

        # Capture BP tracking call payload
        original_post = real_client.post

        async def tracking_post(url, **kwargs):
            if "track-event" in url:
                bp_calls.append({"url": url, "json": kwargs.get("json")})
            return await original_post(url, **kwargs)

        real_client.post = AsyncMock(side_effect=tracking_post)
        mock_client_cls.return_value = real_client

        original_bp_url = config.settings.BATTLEPASS_SERVICE_URL
        config.settings.BATTLEPASS_SERVICE_URL = "http://battle-pass-service:8012"

        app.dependency_overrides[get_current_user_via_http] = lambda: MOCK_USER
        app.dependency_overrides[get_db] = _make_db_for_move()
        try:
            response = client.post(
                f"/locations/{DESTINATION_LOC_ID}/move_and_post",
                json={"character_id": CHARACTER_ID, "content": LONG_CONTENT},
            )
        finally:
            app.dependency_overrides.clear()
            config.settings.BATTLEPASS_SERVICE_URL = original_bp_url

        assert response.status_code == 200, f"Move failed: {response.json()}"

        # Verify BP tracking call was made with correct payload
        assert len(bp_calls) == 1, f"Expected 1 BP call, got {len(bp_calls)}"
        payload = bp_calls[0]["json"]
        assert payload["user_id"] == MOCK_USER.id
        assert payload["event_type"] == "location_visit"
        assert payload["character_id"] == CHARACTER_ID
        assert payload["metadata"] == {"location_id": DESTINATION_LOC_ID}

        # Verify the URL is correct
        assert "track-event" in bp_calls[0]["url"]
        assert "battle-pass/internal/track-event" in bp_calls[0]["url"]


# ===========================================================================
# 2. Movement succeeds even if BP service returns HTTP error
# ===========================================================================
class TestBPServiceDown:
    """Movement must succeed even when battle-pass-service returns errors."""

    @patch("main.httpx.AsyncClient")
    @patch("crud.get_favorite_user_ids", new_callable=AsyncMock, return_value=[])
    @patch("crud.create_post", new_callable=AsyncMock)
    def test_move_succeeds_when_bp_returns_500(
        self, mock_create_post, mock_fav_ids, mock_client_cls, client
    ):
        """BP returning 500 should not break move_and_post."""
        from database import get_db
        from main import app
        import config

        mock_create_post.return_value = _mock_post_result()

        bp_error_resp = MagicMock(status_code=500, text="Internal Server Error")
        real_client = _make_httpx_client_mock(bp_response=bp_error_resp)
        mock_client_cls.return_value = real_client

        original_bp_url = config.settings.BATTLEPASS_SERVICE_URL
        config.settings.BATTLEPASS_SERVICE_URL = "http://battle-pass-service:8012"

        app.dependency_overrides[get_current_user_via_http] = lambda: MOCK_USER
        app.dependency_overrides[get_db] = _make_db_for_move()
        try:
            response = client.post(
                f"/locations/{DESTINATION_LOC_ID}/move_and_post",
                json={"character_id": CHARACTER_ID, "content": LONG_CONTENT},
            )
        finally:
            app.dependency_overrides.clear()
            config.settings.BATTLEPASS_SERVICE_URL = original_bp_url

        # Movement should succeed regardless of BP error
        assert response.status_code == 200, f"Move should succeed: {response.json()}"

    @patch("main.httpx.AsyncClient")
    @patch("crud.get_favorite_user_ids", new_callable=AsyncMock, return_value=[])
    @patch("crud.create_post", new_callable=AsyncMock)
    def test_move_succeeds_when_bp_connection_refused(
        self, mock_create_post, mock_fav_ids, mock_client_cls, client
    ):
        """BP connection error should not break move_and_post."""
        from database import get_db
        from main import app
        import config

        mock_create_post.return_value = _mock_post_result()

        real_client = _make_httpx_client_mock(
            bp_side_effect=ConnectionError("Connection refused")
        )
        mock_client_cls.return_value = real_client

        original_bp_url = config.settings.BATTLEPASS_SERVICE_URL
        config.settings.BATTLEPASS_SERVICE_URL = "http://battle-pass-service:8012"

        app.dependency_overrides[get_current_user_via_http] = lambda: MOCK_USER
        app.dependency_overrides[get_db] = _make_db_for_move()
        try:
            response = client.post(
                f"/locations/{DESTINATION_LOC_ID}/move_and_post",
                json={"character_id": CHARACTER_ID, "content": LONG_CONTENT},
            )
        finally:
            app.dependency_overrides.clear()
            config.settings.BATTLEPASS_SERVICE_URL = original_bp_url

        # Movement should succeed regardless of BP connection error
        assert response.status_code == 200, f"Move should succeed: {response.json()}"


# ===========================================================================
# 3. Tracking skipped when BATTLEPASS_SERVICE_URL is empty
# ===========================================================================
class TestBPTrackingSkipped:
    """No BP call should be made when BATTLEPASS_SERVICE_URL is empty."""

    @patch("main.httpx.AsyncClient")
    @patch("crud.get_favorite_user_ids", new_callable=AsyncMock, return_value=[])
    @patch("crud.create_post", new_callable=AsyncMock)
    def test_no_bp_call_when_url_empty(
        self, mock_create_post, mock_fav_ids, mock_client_cls, client
    ):
        """With BATTLEPASS_SERVICE_URL='', no track-event call is made."""
        from database import get_db
        from main import app
        import config

        mock_create_post.return_value = _mock_post_result()

        bp_calls = []
        real_client = _make_httpx_client_mock()

        original_post = real_client.post

        async def tracking_post(url, **kwargs):
            if "track-event" in url:
                bp_calls.append(url)
            return await original_post(url, **kwargs)

        real_client.post = AsyncMock(side_effect=tracking_post)
        mock_client_cls.return_value = real_client

        original_bp_url = config.settings.BATTLEPASS_SERVICE_URL
        config.settings.BATTLEPASS_SERVICE_URL = ""

        app.dependency_overrides[get_current_user_via_http] = lambda: MOCK_USER
        app.dependency_overrides[get_db] = _make_db_for_move()
        try:
            response = client.post(
                f"/locations/{DESTINATION_LOC_ID}/move_and_post",
                json={"character_id": CHARACTER_ID, "content": LONG_CONTENT},
            )
        finally:
            app.dependency_overrides.clear()
            config.settings.BATTLEPASS_SERVICE_URL = original_bp_url

        assert response.status_code == 200, f"Move should succeed: {response.json()}"

        # No BP tracking call should have been made
        assert len(bp_calls) == 0, f"Expected 0 BP calls, got {len(bp_calls)}"
