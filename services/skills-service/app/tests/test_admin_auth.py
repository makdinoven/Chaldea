"""
Tests for admin endpoint authentication in skills-service.

Verifies that admin endpoints (create skill, delete skill)
properly enforce JWT + admin role checks.

Uses dependency overrides for the async DB session to avoid
needing a real MySQL connection.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient
from auth_http import get_admin_user, get_current_user_via_http, UserRead
from fastapi import HTTPException, status


# ---------------------------------------------------------------------------
# Override the async DB dependency so we don't need a real MySQL connection.
# We also override startup to skip table creation.
# ---------------------------------------------------------------------------

# Patch database and create_tables BEFORE importing main
import database  # noqa: E402

# Replace the async engine/session with mocks so startup doesn't fail
database.engine = MagicMock()
database.create_tables = AsyncMock()

from main import app  # noqa: E402

# Clear startup event handlers to prevent RabbitMQ connection attempts during tests
app.router.on_startup.clear()
from database import get_db  # noqa: E402


async def _fake_get_db():
    yield MagicMock()


app.dependency_overrides[get_db] = _fake_get_db


# ---------------------------------------------------------------------------
# Helper: build a mock requests.get response
# ---------------------------------------------------------------------------
def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


SKILL_PAYLOAD = {
    "name": "Fireball",
    "skill_type": "Attack",
    "description": "A fire spell",
}


# ── POST /skills/admin/skills/ (admin_create_skill) ───────────────────────


class TestAdminCreateSkillAuth:
    """Auth tests for POST /skills/admin/skills/."""

    def test_missing_token_returns_401(self):
        """No Authorization header → 401."""
        with TestClient(app) as client:
            response = client.post("/skills/admin/skills/", json=SKILL_PAYLOAD)
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get):
        """Valid token but role != admin → 403."""
        mock_get.return_value = _mock_response(
            200, {"id": 2, "username": "user", "role": "user"}
        )
        with TestClient(app) as client:
            response = client.post(
                "/skills/admin/skills/",
                json=SKILL_PAYLOAD,
                headers={"Authorization": "Bearer fake-token"},
            )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get):
        """User-service returns 401 → 401."""
        mock_get.return_value = _mock_response(401)
        with TestClient(app) as client:
            response = client.post(
                "/skills/admin/skills/",
                json=SKILL_PAYLOAD,
                headers={"Authorization": "Bearer bad-token"},
            )
        assert response.status_code == 401


# ── DELETE /skills/admin/skills/{skill_id} (admin_delete_skill) ────────────


class TestAdminDeleteSkillAuth:
    """Auth tests for DELETE /skills/admin/skills/{skill_id}."""

    def test_missing_token_returns_401(self):
        with TestClient(app) as client:
            response = client.delete("/skills/admin/skills/1")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get):
        mock_get.return_value = _mock_response(
            200, {"id": 2, "username": "user", "role": "user"}
        )
        with TestClient(app) as client:
            response = client.delete(
                "/skills/admin/skills/1",
                headers={"Authorization": "Bearer fake-token"},
            )
        assert response.status_code == 403
