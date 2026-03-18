"""
Tests for user-facing endpoint authentication in skills-service.

Verifies that POST /skills/character_skills/upgrade enforces:
- 401 when no token is provided
- 403 when the character does not belong to the authenticated user
- Success when the character belongs to the user (mocked DB + crud)

Uses dependency overrides and patches to avoid real MySQL / RabbitMQ.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient
from auth_http import get_current_user_via_http, UserRead

# ---------------------------------------------------------------------------
# Patch database engine before importing main to avoid MySQL connection
# ---------------------------------------------------------------------------
import database  # noqa: E402

database.engine = MagicMock()
database.create_tables = AsyncMock()

from main import app  # noqa: E402

# Clear startup event handlers to prevent RabbitMQ connection attempts
app.router.on_startup.clear()
from database import get_db  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


UPGRADE_PAYLOAD = {
    "character_id": 10,
    "next_rank_id": 2,
}


# ---------------------------------------------------------------------------
# Mock async DB session that supports execute() for ownership check
# ---------------------------------------------------------------------------
def _make_mock_db(owner_user_id: int = None):
    """Return an async mock DB session.

    If *owner_user_id* is given, the ``characters`` ownership query will
    return a row with that user_id.  Otherwise the query returns no rows
    (character not found).
    """
    mock_db = AsyncMock()
    mock_result = MagicMock()
    if owner_user_id is not None:
        mock_result.fetchone.return_value = (owner_user_id,)
    else:
        mock_result.fetchone.return_value = None
    mock_db.execute.return_value = mock_result
    return mock_db


# ---------------------------------------------------------------------------
# POST /skills/character_skills/upgrade — ownership via verify_character_ownership
# ---------------------------------------------------------------------------


class TestUpgradeSkillAuth:
    """Auth + ownership tests for POST /skills/character_skills/upgrade."""

    def test_missing_token_returns_401(self):
        """No Authorization header -> 401."""
        with TestClient(app) as client:
            response = client.post(
                "/skills/character_skills/upgrade", json=UPGRADE_PAYLOAD
            )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get):
        """user-service rejects token -> 401."""
        mock_get.return_value = _mock_response(401)
        with TestClient(app) as client:
            response = client.post(
                "/skills/character_skills/upgrade",
                json=UPGRADE_PAYLOAD,
                headers={"Authorization": "Bearer bad-token"},
            )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_wrong_owner_returns_403(self, mock_auth_get):
        """Authenticated user does not own the character -> 403."""
        # Auth succeeds: user id=99
        mock_auth_get.return_value = _mock_response(
            200, {"id": 99, "username": "hacker", "role": "user", "permissions": []}
        )

        # DB says character belongs to user_id=1 (not 99)
        mock_db = _make_mock_db(owner_user_id=1)

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/skills/character_skills/upgrade",
                    json=UPGRADE_PAYLOAD,
                    headers={"Authorization": "Bearer fake-token"},
                )
            assert response.status_code == 403
        finally:
            app.dependency_overrides.pop(get_db, None)

    @patch("auth_http.requests.get")
    def test_correct_owner_passes_auth(self, mock_auth_get):
        """Authenticated user owns the character -> passes ownership check.

        The request may still fail downstream (e.g. SkillRank not found),
        but the important thing is that it does NOT return 401 or 403.
        """
        user_id = 5
        mock_auth_get.return_value = _mock_response(
            200, {"id": user_id, "username": "owner", "role": "user", "permissions": []}
        )

        # DB returns character owned by user_id=5
        mock_db = _make_mock_db(owner_user_id=user_id)

        # Mock crud.get_skill_rank to return None -> 404 "SkillRank not found"
        # This proves auth + ownership passed successfully.
        mock_db.refresh = AsyncMock()

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/skills/character_skills/upgrade",
                    json=UPGRADE_PAYLOAD,
                    headers={"Authorization": "Bearer fake-token"},
                )
            # Should NOT be 401 or 403 — auth and ownership passed
            assert response.status_code not in (401, 403)
        finally:
            app.dependency_overrides.pop(get_db, None)
