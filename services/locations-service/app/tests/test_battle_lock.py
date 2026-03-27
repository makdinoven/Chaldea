"""
Tests for battle lock in locations-service (FEAT-066).

Covers:
1. Create post while in battle -> 400
2. Move location while in battle -> 400
3. Create post while NOT in battle -> passes (normal flow)
"""

from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

import pytest

from auth_http import get_current_user_via_http, UserRead


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


MOCK_USER = UserRead(id=10, username="testuser", role="user", permissions=[])


def _make_db_with_battle(in_battle: bool):
    """Create a mock async DB session that simulates ownership + battle state."""
    async def mock_get_db():
        mock_db = AsyncMock()

        async def execute_side_effect(query, params=None):
            query_str = str(query)

            # verify_character_ownership: SELECT user_id FROM characters
            if "user_id" in query_str and "characters" in query_str:
                return _result_with_row(_row(10))  # user_id=10 matches MOCK_USER

            # check_not_in_battle: SELECT b.id FROM battles b JOIN battle_participants
            if "battles" in query_str and "battle_participants" in query_str:
                if in_battle:
                    return _result_with_row(_row(1))  # battle_id=1 — IN battle
                else:
                    return _result_empty()  # NOT in battle

            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        yield mock_db

    return mock_get_db


# ===========================================================================
# Test 1: Create post while in battle -> 400
# ===========================================================================
class TestCreatePostInBattle:
    """Creating a post while character is in active battle should be blocked."""

    def test_create_post_blocked_in_battle(self, client):
        """POST /locations/posts/ returns 400 when character is in battle."""
        from database import get_db
        from main import app

        app.dependency_overrides[get_current_user_via_http] = lambda: MOCK_USER
        app.dependency_overrides[get_db] = _make_db_with_battle(in_battle=True)
        try:
            response = client.post(
                "/locations/posts/",
                json={
                    "character_id": 1,
                    "location_id": 100,
                    "content": "Привет",
                },
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 400
        assert "бо" in response.json()["detail"].lower()


# ===========================================================================
# Test 2: Move location while in battle -> 400
# ===========================================================================
class TestMoveInBattle:
    """Moving to another location while in battle should be blocked."""

    def test_move_blocked_in_battle(self, client):
        """POST /locations/{id}/move_and_post returns 400 when in battle."""
        from database import get_db
        from main import app

        app.dependency_overrides[get_current_user_via_http] = lambda: MOCK_USER
        app.dependency_overrides[get_db] = _make_db_with_battle(in_battle=True)
        try:
            response = client.post(
                "/locations/200/move_and_post",
                json={
                    "character_id": 1,
                    "content": "Перехожу",
                },
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 400
        assert "бо" in response.json()["detail"].lower()


# ===========================================================================
# Test 3: Create post while NOT in battle -> passes
# ===========================================================================
class TestCreatePostNoBattle:
    """Creating a post when NOT in battle should work normally."""

    @patch("crud.create_post", new_callable=AsyncMock)
    def test_create_post_allowed_not_in_battle(self, mock_create_post, client):
        """POST /locations/posts/ succeeds when character is NOT in battle."""
        from database import get_db
        from main import app

        # Mock create_post to return a valid post-like object
        mock_post = MagicMock()
        mock_post.id = 1
        mock_post.character_id = 1
        mock_post.location_id = 100
        mock_post.content = "А" * 350
        mock_post.created_at = datetime(2026, 3, 23, 12, 0, 0)
        mock_post.updated_at = datetime(2026, 3, 23, 12, 0, 0)
        mock_post.character_name = "Воин"
        mock_post.character_avatar = None
        mock_post.likes_count = 0
        mock_post.liked_by_me = False
        mock_create_post.return_value = mock_post

        app.dependency_overrides[get_current_user_via_http] = lambda: MOCK_USER
        app.dependency_overrides[get_db] = _make_db_with_battle(in_battle=False)
        try:
            response = client.post(
                "/locations/posts/",
                json={
                    "character_id": 1,
                    "location_id": 100,
                    "content": "А" * 350,
                },
            )
        finally:
            app.dependency_overrides.clear()

        # Should succeed (not 400) — create_post is mocked so actual DB doesn't matter
        assert response.status_code != 400
