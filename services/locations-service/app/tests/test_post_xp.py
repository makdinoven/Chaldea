"""
Tests for locations-service post validation, XP calculation, and character-stats endpoint.

Covers (FEAT-095, Task #13):
A) strip_html_tags — strips HTML tags, returns plain text
B) calculate_post_xp — content <300 chars → returns (count, 0)
C) calculate_post_xp — 340 chars → returns (340, 3)
D) calculate_post_xp — 350 chars → returns (350, 4) (standard rounding)
E) calculate_post_xp — 351 chars → returns (351, 4)
F) calculate_post_xp — heavy HTML markup → char count ignores tags
G) character-stats endpoint — returns correct counts/dates
H) character-stats endpoint — empty character_ids returns empty stats
I) award_post_xp_and_log — calls correct URLs with correct payloads (mocked httpx)
"""

from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

import pytest

from crud import strip_html_tags, calculate_post_xp, MIN_POST_LENGTH, award_post_xp_and_log


# ---------------------------------------------------------------------------
# A) strip_html_tags
# ---------------------------------------------------------------------------
class TestStripHtmlTags:
    def test_strips_p_tags(self):
        assert strip_html_tags("<p>Hello world</p>") == "Hello world"

    def test_strips_b_tags(self):
        assert strip_html_tags("<b>bold text</b>") == "bold text"

    def test_strips_br_tags(self):
        assert strip_html_tags("line one<br>line two") == "line oneline two"

    def test_strips_br_self_closing(self):
        assert strip_html_tags("line one<br/>line two") == "line oneline two"

    def test_strips_nested_tags(self):
        html = "<p>This is <b>bold</b> and <i>italic</i></p>"
        assert strip_html_tags(html) == "This is bold and italic"

    def test_strips_complex_markup(self):
        html = '<p style="color:red"><b>Hello</b> <span class="x">world</span></p>'
        assert strip_html_tags(html) == "Hello world"

    def test_plain_text_unchanged(self):
        assert strip_html_tags("no tags here") == "no tags here"

    def test_empty_string(self):
        assert strip_html_tags("") == ""

    def test_strips_and_trims_whitespace(self):
        assert strip_html_tags("  <p> text </p>  ") == "text"


# ---------------------------------------------------------------------------
# B-F) calculate_post_xp
# ---------------------------------------------------------------------------
class TestCalculatePostXp:
    def test_below_min_length_returns_zero_xp(self):
        """B) Content <300 chars → (count, 0)."""
        content = "a" * 200
        char_count, xp = calculate_post_xp(content)
        assert char_count == 200
        assert xp == 0

    def test_exactly_min_length_returns_xp(self):
        """At exactly 300 chars → (300, 3)."""
        content = "a" * 300
        char_count, xp = calculate_post_xp(content)
        assert char_count == 300
        assert xp == 3

    def test_299_chars_returns_zero_xp(self):
        """299 chars is below minimum → (299, 0)."""
        content = "a" * 299
        char_count, xp = calculate_post_xp(content)
        assert char_count == 299
        assert xp == 0

    def test_340_chars_returns_3_xp(self):
        """C) 340 chars → 340/100=3.4 → rounds to 3."""
        content = "a" * 340
        char_count, xp = calculate_post_xp(content)
        assert char_count == 340
        assert xp == 3

    def test_350_chars_returns_4_xp(self):
        """D) 350 chars → 350/100=3.5 → standard rounding → 4."""
        content = "a" * 350
        char_count, xp = calculate_post_xp(content)
        assert char_count == 350
        assert xp == 4

    def test_351_chars_returns_4_xp(self):
        """E) 351 chars → 351/100=3.51 → rounds to 4."""
        content = "a" * 351
        char_count, xp = calculate_post_xp(content)
        assert char_count == 351
        assert xp == 4

    def test_heavy_html_markup_ignored_in_count(self):
        """F) Heavy HTML markup — char count is based on plain text only."""
        # 310 plain characters wrapped in heavy HTML
        plain = "x" * 310
        html = f"<p><b><i><span style='color:red'>{plain}</span></i></b></p>"
        char_count, xp = calculate_post_xp(html)
        assert char_count == 310
        assert xp == 3

    def test_html_below_min_after_strip(self):
        """HTML content that looks long but has <300 plain chars."""
        # 250 plain chars with lots of tags
        plain = "y" * 250
        html = f"<div><p><b><strong>{plain}</strong></b></p></div>"
        char_count, xp = calculate_post_xp(html)
        assert char_count == 250
        assert xp == 0

    def test_1000_chars_returns_10_xp(self):
        """1000 chars → 1000/100=10.0 → 10 XP."""
        content = "a" * 1000
        char_count, xp = calculate_post_xp(content)
        assert char_count == 1000
        assert xp == 10

    def test_min_post_length_constant(self):
        """Verify MIN_POST_LENGTH is 300."""
        assert MIN_POST_LENGTH == 300


# ---------------------------------------------------------------------------
# G-H) character-stats endpoint
# ---------------------------------------------------------------------------
class TestCharacterStatsEndpoint:
    def test_empty_character_ids_returns_empty(self, client):
        """H) Empty character_ids returns empty stats."""
        response = client.get("/locations/posts/character-stats?character_ids=")
        assert response.status_code == 200
        assert response.json() == {"stats": {}}

    def test_no_character_ids_param_returns_empty(self, client):
        """No parameter at all returns empty stats."""
        response = client.get("/locations/posts/character-stats")
        assert response.status_code == 200
        assert response.json() == {"stats": {}}

    def test_invalid_character_ids_returns_empty(self, client):
        """Non-numeric IDs are skipped, resulting in empty stats."""
        response = client.get("/locations/posts/character-stats?character_ids=abc,xyz")
        assert response.status_code == 200
        assert response.json() == {"stats": {}}

    @patch("crud.get_character_post_stats")
    def test_returns_correct_stats(self, mock_stats, client):
        """G) Returns correct counts/dates for given character IDs."""
        mock_date = datetime(2026, 3, 27, 12, 0, 0)
        mock_stats.return_value = {
            "1": {"count": 5, "last_date": mock_date},
            "2": {"count": 3, "last_date": mock_date},
        }
        response = client.get("/locations/posts/character-stats?character_ids=1,2")
        assert response.status_code == 200
        data = response.json()
        assert "1" in data["stats"]
        assert data["stats"]["1"]["count"] == 5
        assert "2" in data["stats"]
        assert data["stats"]["2"]["count"] == 3

    @patch("crud.get_character_post_stats")
    def test_single_character_id(self, mock_stats, client):
        """Single character ID works correctly."""
        mock_stats.return_value = {
            "42": {"count": 10, "last_date": None},
        }
        response = client.get("/locations/posts/character-stats?character_ids=42")
        assert response.status_code == 200
        data = response.json()
        assert data["stats"]["42"]["count"] == 10
        assert data["stats"]["42"]["last_date"] is None

    @patch("crud.get_character_post_stats")
    def test_character_with_no_posts_not_in_response(self, mock_stats, client):
        """Characters with no posts are not included in stats dict."""
        mock_stats.return_value = {}
        response = client.get("/locations/posts/character-stats?character_ids=999")
        assert response.status_code == 200
        assert response.json() == {"stats": {}}


# ---------------------------------------------------------------------------
# I) award_post_xp_and_log — background task calls correct URLs
# ---------------------------------------------------------------------------
class TestAwardPostXpAndLog:
    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_calls_correct_urls_with_xp(self, mock_settings):
        """When xp > 0, calls both attributes and character-service."""
        mock_settings.ATTRIBUTES_SERVICE_URL = "http://attrs:8002"
        mock_settings.CHARACTER_SERVICE_URL = "http://chars:8005"

        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("crud.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.put = AsyncMock(return_value=mock_response)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            await award_post_xp_and_log(
                character_id=1,
                post_id=10,
                location_id=100,
                location_name="Таверна",
                char_count=350,
                xp=4,
            )

            # Verify passive XP call
            mock_client.put.assert_called_once_with(
                "http://attrs:8002/attributes/1/passive_experience",
                json={"amount": 4},
            )

            # Verify log creation call
            mock_client.post.assert_called_once_with(
                "http://chars:8005/characters/1/logs",
                json={
                    "event_type": "rp_post",
                    "description": "Написал пост в Таверна, получил 4 XP",
                    "metadata": {
                        "post_id": 10,
                        "location_id": 100,
                        "xp_earned": 4,
                        "char_count": 350,
                    },
                },
            )

    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_skips_xp_call_when_zero(self, mock_settings):
        """When xp = 0, does NOT call attributes service, but still logs."""
        mock_settings.ATTRIBUTES_SERVICE_URL = "http://attrs:8002"
        mock_settings.CHARACTER_SERVICE_URL = "http://chars:8005"

        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("crud.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.put = AsyncMock(return_value=mock_response)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            await award_post_xp_and_log(
                character_id=1,
                post_id=10,
                location_id=100,
                location_name="Таверна",
                char_count=200,
                xp=0,
            )

            # Should NOT call attributes service
            mock_client.put.assert_not_called()

            # Should still create log
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[1]["json"]["description"] == "Написал пост в Таверна, получил 0 XP"

    @pytest.mark.asyncio
    @patch("crud.settings")
    async def test_handles_http_error_gracefully(self, mock_settings):
        """If httpx raises an exception, the function does not propagate it."""
        mock_settings.ATTRIBUTES_SERVICE_URL = "http://attrs:8002"
        mock_settings.CHARACTER_SERVICE_URL = "http://chars:8005"

        with patch("crud.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.put = AsyncMock(side_effect=Exception("connection refused"))
            mock_client_cls.return_value = mock_client

            # Should not raise — fire-and-forget
            await award_post_xp_and_log(
                character_id=1,
                post_id=10,
                location_id=100,
                location_name="Таверна",
                char_count=350,
                xp=4,
            )
