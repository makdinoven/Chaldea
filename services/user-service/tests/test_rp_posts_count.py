"""
FEAT-095 Task #14 — Tests for user-service rp_posts_count population.

Covers:
A) _fetch_character_post_stats with successful response — returns correct stats dict
B) _fetch_character_post_stats with locations-service unavailable (timeout/connection error)
   — returns empty dict, no exception raised
C) _fetch_character_post_stats with locations-service returning error (500)
   — returns empty dict gracefully
"""

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helper to run async functions in sync tests
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# A) Successful response — returns correct stats dict
# ---------------------------------------------------------------------------

class TestFetchCharacterPostStatsSuccess:

    def test_returns_stats_for_multiple_characters(self):
        """When locations-service returns valid stats, function returns them keyed by character_id."""
        from main import _fetch_character_post_stats

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "stats": {
                "1": {"count": 5, "last_date": "2026-03-20T12:00:00"},
                "2": {"count": 12, "last_date": "2026-03-25T15:30:00"},
            }
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("main.httpx.AsyncClient", return_value=mock_client):
            result = _run(_fetch_character_post_stats([1, 2]))

        assert result == {
            "1": {"count": 5, "last_date": "2026-03-20T12:00:00"},
            "2": {"count": 12, "last_date": "2026-03-25T15:30:00"},
        }

    def test_returns_empty_dict_for_empty_character_ids(self):
        """When character_ids list is empty, returns empty dict without making HTTP call."""
        from main import _fetch_character_post_stats

        with patch("main.httpx.AsyncClient") as mock_client_cls:
            result = _run(_fetch_character_post_stats([]))

        # Should not have created an HTTP client at all
        mock_client_cls.assert_not_called()
        assert result == {}

    def test_returns_stats_for_single_character(self):
        """Single character ID works correctly."""
        from main import _fetch_character_post_stats

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "stats": {
                "42": {"count": 3, "last_date": "2026-03-27T10:00:00"},
            }
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("main.httpx.AsyncClient", return_value=mock_client):
            result = _run(_fetch_character_post_stats([42]))

        assert result == {"42": {"count": 3, "last_date": "2026-03-27T10:00:00"}}

    def test_constructs_correct_url_with_character_ids(self):
        """Verify the URL includes comma-separated character IDs."""
        from main import _fetch_character_post_stats

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"stats": {}}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("main.httpx.AsyncClient", return_value=mock_client):
            _run(_fetch_character_post_stats([10, 20, 30]))

        # Check the URL passed to client.get
        call_args = mock_client.get.call_args
        url = call_args[0][0]
        assert "character_ids=10,20,30" in url
        assert "/locations/posts/character-stats" in url


# ---------------------------------------------------------------------------
# B) locations-service unavailable (timeout / connection error)
# ---------------------------------------------------------------------------

class TestFetchCharacterPostStatsConnectionError:

    def test_returns_empty_dict_on_connect_error(self):
        """When locations-service is unreachable, returns empty dict gracefully."""
        from main import _fetch_character_post_stats

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("main.httpx.AsyncClient", return_value=mock_client):
            result = _run(_fetch_character_post_stats([1, 2]))

        assert result == {}

    def test_returns_empty_dict_on_timeout(self):
        """When locations-service times out, returns empty dict gracefully."""
        from main import _fetch_character_post_stats

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.TimeoutException("Request timed out")
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("main.httpx.AsyncClient", return_value=mock_client):
            result = _run(_fetch_character_post_stats([1]))

        assert result == {}

    def test_no_exception_raised_on_network_error(self):
        """Network errors must not propagate — function handles them internally."""
        from main import _fetch_character_post_stats

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.ConnectTimeout("DNS resolution failed")
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("main.httpx.AsyncClient", return_value=mock_client):
            # Should NOT raise any exception
            result = _run(_fetch_character_post_stats([5, 10]))
            assert result == {}


# ---------------------------------------------------------------------------
# C) locations-service returns error (500)
# ---------------------------------------------------------------------------

class TestFetchCharacterPostStatsServerError:

    def test_returns_empty_dict_on_500(self):
        """When locations-service returns HTTP 500, returns empty dict gracefully."""
        from main import _fetch_character_post_stats

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Server Error",
                request=MagicMock(),
                response=mock_response,
            )
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("main.httpx.AsyncClient", return_value=mock_client):
            result = _run(_fetch_character_post_stats([1, 2, 3]))

        assert result == {}

    def test_returns_empty_dict_on_404(self):
        """When locations-service returns HTTP 404, returns empty dict gracefully."""
        from main import _fetch_character_post_stats

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Not Found",
                request=MagicMock(),
                response=mock_response,
            )
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("main.httpx.AsyncClient", return_value=mock_client):
            result = _run(_fetch_character_post_stats([1]))

        assert result == {}

    def test_no_exception_raised_on_http_error(self):
        """HTTP errors must not propagate — function handles them internally."""
        from main import _fetch_character_post_stats

        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Service Unavailable",
                request=MagicMock(),
                response=mock_response,
            )
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("main.httpx.AsyncClient", return_value=mock_client):
            # Should NOT raise any exception
            result = _run(_fetch_character_post_stats([7]))
            assert result == {}
