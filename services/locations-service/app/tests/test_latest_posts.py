"""
Tests for the homepage "latest roleplay posts" feed.

Covers:
A) GET /locations/posts/latest — clamps the `limit` query param to [1, 20]
   and passes the sanitized value through to the crud layer.
B) GET /locations/posts/latest — returns the enriched payload as-is.
C) crud.get_latest_posts_details — enriches each post with its location
   (id + name) and likes, preserving newest-first order.
D) crud.get_latest_posts_details — a non-positive limit short-circuits to []
   without touching the database.
"""

from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from crud import get_latest_posts_details


# ---------------------------------------------------------------------------
# A-B) GET /locations/posts/latest endpoint
# ---------------------------------------------------------------------------
class TestLatestPostsEndpoint:
    @patch("crud.get_latest_posts_details", new_callable=AsyncMock)
    def test_default_limit_is_five(self, mock_latest, client):
        mock_latest.return_value = []
        response = client.get("/locations/posts/latest")
        assert response.status_code == 200
        # crud called with (session, 5)
        assert mock_latest.call_args.args[1] == 5

    @patch("crud.get_latest_posts_details", new_callable=AsyncMock)
    def test_limit_clamped_up_to_one(self, mock_latest, client):
        mock_latest.return_value = []
        response = client.get("/locations/posts/latest?limit=0")
        assert response.status_code == 200
        assert mock_latest.call_args.args[1] == 1

    @patch("crud.get_latest_posts_details", new_callable=AsyncMock)
    def test_negative_limit_clamped_up_to_one(self, mock_latest, client):
        mock_latest.return_value = []
        response = client.get("/locations/posts/latest?limit=-10")
        assert response.status_code == 200
        assert mock_latest.call_args.args[1] == 1

    @patch("crud.get_latest_posts_details", new_callable=AsyncMock)
    def test_limit_clamped_down_to_twenty(self, mock_latest, client):
        mock_latest.return_value = []
        response = client.get("/locations/posts/latest?limit=999")
        assert response.status_code == 200
        assert mock_latest.call_args.args[1] == 20

    @patch("crud.get_latest_posts_details", new_callable=AsyncMock)
    def test_returns_enriched_payload(self, mock_latest, client):
        mock_latest.return_value = [
            {
                "post_id": 4,
                "character_id": 1,
                "character_photo": "https://cdn/x.webp",
                "character_title": "Герой",
                "character_title_rarity": "legendary",
                "character_level": 2,
                "character_name": "Убийца",
                "user_id": 1,
                "user_nickname": "admin",
                "content": "<em>*текст*</em>",
                "length": 6,
                "created_at": datetime(2026, 4, 25, 17, 9, 8),
                "likes_count": 3,
                "liked_by": [5, 6, 7],
                "location_id": 7,
                "location_name": "Таверна",
            }
        ]
        response = client.get("/locations/posts/latest?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        post = data[0]
        assert post["post_id"] == 4
        assert post["location_id"] == 7
        assert post["location_name"] == "Таверна"
        assert post["character_name"] == "Убийца"
        assert post["likes_count"] == 3
        assert post["liked_by"] == [5, 6, 7]


# ---------------------------------------------------------------------------
# C-D) crud.get_latest_posts_details enrichment
# ---------------------------------------------------------------------------
async def _fake_get_post_details(post):
    """Stand-in for the Character-service enrichment call."""
    return {
        "post_id": post.id,
        "character_id": post.character_id,
        "character_photo": "",
        "character_title": "",
        "character_title_rarity": None,
        "character_level": 1,
        "user_id": 1,
        "user_nickname": "admin",
        "character_name": f"Char{post.id}",
        "content": "text",
        "length": 4,
        "created_at": datetime(2026, 1, 1),
    }


class TestGetLatestPostsDetails:
    @pytest.mark.asyncio
    async def test_enriches_and_preserves_order(self):
        post_a = MagicMock(id=10, location_id=100, character_id=1)
        post_b = MagicMock(id=11, location_id=200, character_id=2)

        exec_result = MagicMock()
        # Newest-first rows: each is (Post, location_name)
        exec_result.all = MagicMock(return_value=[(post_a, "Loc A"), (post_b, "Loc B")])
        session = MagicMock()
        session.execute = AsyncMock(return_value=exec_result)

        likes = {
            10: {"likes_count": 2, "liked_by": [5]},
            11: {"likes_count": 0, "liked_by": []},
        }

        with patch("crud.get_post_details", new=_fake_get_post_details), \
             patch("crud.get_likes_for_posts", new=AsyncMock(return_value=likes)):
            result = await get_latest_posts_details(session, 5)

        assert len(result) == 2
        # Order preserved (newest-first from the query)
        assert result[0]["post_id"] == 10
        assert result[1]["post_id"] == 11
        # Location joined on
        assert result[0]["location_id"] == 100
        assert result[0]["location_name"] == "Loc A"
        assert result[1]["location_id"] == 200
        assert result[1]["location_name"] == "Loc B"
        # Likes attached from the batch fetch
        assert result[0]["likes_count"] == 2
        assert result[0]["liked_by"] == [5]
        assert result[1]["likes_count"] == 0

    @pytest.mark.asyncio
    async def test_non_positive_limit_short_circuits(self):
        session = MagicMock()
        session.execute = AsyncMock()

        assert await get_latest_posts_details(session, 0) == []
        assert await get_latest_posts_details(session, -5) == []
        # DB is never queried for an empty request
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_list(self):
        exec_result = MagicMock()
        exec_result.all = MagicMock(return_value=[])
        session = MagicMock()
        session.execute = AsyncMock(return_value=exec_result)

        with patch("crud.get_likes_for_posts", new=AsyncMock(return_value={})):
            result = await get_latest_posts_details(session, 5)

        assert result == []
