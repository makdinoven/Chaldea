"""
Tests for user-facing endpoint authentication in locations-service.

Covers:
- L1: POST /locations/posts/           — ownership (character_id in body)
- L2: POST /locations/{dest_id}/move_and_post — ownership (character_id in body)
- L3: GET  /locations/admin/data        — admin-only (locations:read)

Uses dependency overrides and patches to avoid real MySQL connections.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient
from auth_http import get_current_user_via_http, UserRead

# ---------------------------------------------------------------------------
# Patch database engine before importing main (already done in conftest.py,
# but we repeat for standalone execution safety)
# ---------------------------------------------------------------------------
import database  # noqa: E402

_mock_engine = MagicMock()
_mock_conn = AsyncMock()
_mock_conn.run_sync = AsyncMock()
_mock_cm = AsyncMock()
_mock_cm.__aenter__ = AsyncMock(return_value=_mock_conn)
_mock_cm.__aexit__ = AsyncMock(return_value=False)
_mock_engine.begin = MagicMock(return_value=_mock_cm)
database.engine = _mock_engine

from main import app  # noqa: E402
from database import get_db  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


def _make_mock_db(owner_user_id: int = None):
    """Return an async mock DB session for ownership queries."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    if owner_user_id is not None:
        mock_result.fetchone.return_value = (owner_user_id,)
    else:
        mock_result.fetchone.return_value = None
    mock_db.execute.return_value = mock_result
    return mock_db


POST_PAYLOAD = {
    "character_id": 10,
    "location_id": 1,
    "content": "Hello world",
}

MOVE_AND_POST_PAYLOAD = {
    "character_id": 10,
    "content": "Travelling...",
}


# ═══════════════════════════════════════════════════════════════════════════
# L1: POST /locations/posts/ — ownership via verify_character_ownership
# ═══════════════════════════════════════════════════════════════════════════


class TestCreatePostAuth:
    """Auth + ownership tests for POST /locations/posts/."""

    def test_missing_token_returns_401(self):
        with TestClient(app) as client:
            response = client.post("/locations/posts/", json=POST_PAYLOAD)
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get):
        mock_get.return_value = _mock_response(401)
        with TestClient(app) as client:
            response = client.post(
                "/locations/posts/",
                json=POST_PAYLOAD,
                headers={"Authorization": "Bearer bad-token"},
            )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_wrong_owner_returns_403(self, mock_auth_get):
        """User does not own the character -> 403."""
        mock_auth_get.return_value = _mock_response(
            200, {"id": 99, "username": "hacker", "role": "user", "permissions": []}
        )
        mock_db = _make_mock_db(owner_user_id=1)  # character belongs to user 1

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/locations/posts/",
                    json=POST_PAYLOAD,
                    headers={"Authorization": "Bearer fake-token"},
                )
            assert response.status_code == 403
        finally:
            app.dependency_overrides.pop(get_db, None)

    @patch("auth_http.requests.get")
    @patch("crud.create_post", new_callable=AsyncMock)
    def test_correct_owner_passes_auth(self, mock_create_post, mock_auth_get):
        """User owns the character -> passes auth, calls create_post."""
        user_id = 5
        mock_auth_get.return_value = _mock_response(
            200, {"id": user_id, "username": "owner", "role": "user", "permissions": []}
        )
        mock_create_post.return_value = {
            "id": 1,
            "character_id": 10,
            "location_id": 1,
            "content": "Hello world",
            "created_at": "2026-01-01T00:00:00",
            "character_name": "Hero",
            "character_photo": None,
        }

        mock_db = _make_mock_db(owner_user_id=user_id)

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/locations/posts/",
                    json=POST_PAYLOAD,
                    headers={"Authorization": "Bearer fake-token"},
                )
            assert response.status_code not in (401, 403)
        finally:
            app.dependency_overrides.pop(get_db, None)


# ═══════════════════════════════════════════════════════════════════════════
# L2: POST /locations/{dest_id}/move_and_post — ownership
# ═══════════════════════════════════════════════════════════════════════════


class TestMoveAndPostAuth:
    """Auth + ownership tests for POST /locations/{dest_id}/move_and_post."""

    def test_missing_token_returns_401(self):
        with TestClient(app) as client:
            response = client.post(
                "/locations/5/move_and_post", json=MOVE_AND_POST_PAYLOAD
            )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get):
        mock_get.return_value = _mock_response(401)
        with TestClient(app) as client:
            response = client.post(
                "/locations/5/move_and_post",
                json=MOVE_AND_POST_PAYLOAD,
                headers={"Authorization": "Bearer bad-token"},
            )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_wrong_owner_returns_403(self, mock_auth_get):
        """User does not own the character -> 403."""
        mock_auth_get.return_value = _mock_response(
            200, {"id": 99, "username": "hacker", "role": "user", "permissions": []}
        )
        mock_db = _make_mock_db(owner_user_id=1)

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/locations/5/move_and_post",
                    json=MOVE_AND_POST_PAYLOAD,
                    headers={"Authorization": "Bearer fake-token"},
                )
            assert response.status_code == 403
        finally:
            app.dependency_overrides.pop(get_db, None)

    @patch("httpx.AsyncClient")
    @patch("auth_http.requests.get")
    def test_correct_owner_passes_auth(self, mock_auth_get, mock_httpx_cls):
        """User owns the character -> passes auth check.

        We mock httpx.AsyncClient to avoid real HTTP calls to character-service
        and attributes-service that happen after ownership check passes.
        """
        user_id = 5
        mock_auth_get.return_value = _mock_response(
            200, {"id": user_id, "username": "owner", "role": "user", "permissions": []}
        )

        # Mock httpx async client to return profile data
        mock_httpx_instance = AsyncMock()
        mock_profile_resp = MagicMock()
        mock_profile_resp.status_code = 200
        mock_profile_resp.json.return_value = {"current_location_id": None}
        mock_httpx_instance.__aenter__.return_value = mock_httpx_instance
        mock_httpx_instance.__aexit__.return_value = False
        mock_httpx_instance.get.return_value = mock_profile_resp
        mock_httpx_cls.return_value = mock_httpx_instance

        mock_db = _make_mock_db(owner_user_id=user_id)

        # Also mock crud.create_post for when movement_cost=0
        with patch("crud.create_post", new_callable=AsyncMock) as mock_create_post:
            mock_create_post.return_value = {
                "id": 1,
                "character_id": 10,
                "location_id": 5,
                "content": "Travelling...",
                "created_at": "2026-01-01T00:00:00",
                "character_name": "Hero",
                "character_photo": None,
            }
            # Mock the location update call
            mock_update_resp = MagicMock()
            mock_update_resp.status_code = 200
            mock_httpx_instance.put.return_value = mock_update_resp

            async def _fake_get_db():
                yield mock_db

            app.dependency_overrides[get_db] = _fake_get_db
            try:
                with TestClient(app) as client:
                    response = client.post(
                        "/locations/5/move_and_post",
                        json=MOVE_AND_POST_PAYLOAD,
                        headers={"Authorization": "Bearer fake-token"},
                    )
                # Auth and ownership passed — should not be 401/403
                assert response.status_code not in (401, 403)
            finally:
                app.dependency_overrides.pop(get_db, None)


# ═══════════════════════════════════════════════════════════════════════════
# L3: GET /locations/admin/data — admin-only (locations:read permission)
# ═══════════════════════════════════════════════════════════════════════════


class TestAdminDataAuth:
    """Auth + permission tests for GET /locations/admin/data."""

    def test_missing_token_returns_401(self):
        with TestClient(app) as client:
            response = client.get("/locations/admin/data")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get):
        mock_get.return_value = _mock_response(401)
        with TestClient(app) as client:
            response = client.get(
                "/locations/admin/data",
                headers={"Authorization": "Bearer bad-token"},
            )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_no_permission_returns_403(self, mock_auth_get):
        """User has no locations:read permission -> 403."""
        mock_auth_get.return_value = _mock_response(
            200, {"id": 2, "username": "user", "role": "user", "permissions": []}
        )
        with TestClient(app) as client:
            response = client.get(
                "/locations/admin/data",
                headers={"Authorization": "Bearer fake-token"},
            )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    @patch("crud.get_admin_panel_data", new_callable=AsyncMock)
    def test_with_permission_passes_auth(self, mock_admin_data, mock_auth_get):
        """User has locations:read permission -> passes auth."""
        mock_auth_get.return_value = _mock_response(
            200,
            {
                "id": 1,
                "username": "admin",
                "role": "admin",
                "permissions": ["locations:read"],
            },
        )
        mock_admin_data.return_value = {"countries": [], "regions": []}

        mock_db = AsyncMock()

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/locations/admin/data",
                    headers={"Authorization": "Bearer fake-token"},
                )
            assert response.status_code not in (401, 403)
        finally:
            app.dependency_overrides.pop(get_db, None)
