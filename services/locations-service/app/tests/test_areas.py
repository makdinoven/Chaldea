"""
Tests for Area CRUD endpoints in locations-service.

Covers:
- GET /locations/areas/list — empty list, list with areas ordered by sort_order
- GET /locations/areas/{area_id}/details — returns area with countries, 404 for non-existent
- POST /locations/areas/create — creates area (admin), validation, 401/403 without admin auth
- PUT /locations/areas/{area_id}/update — partial update (admin), 404 for non-existent
- DELETE /locations/areas/{area_id}/delete — deletes area (admin), 404, countries get area_id=NULL
- Security: SQL injection in path params
- Auth: verify endpoints require correct permissions
"""

from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException

import pytest


# ---------------------------------------------------------------------------
# Helper: mock auth response from user-service
# ---------------------------------------------------------------------------
def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


ADMIN_HEADERS = {"Authorization": "Bearer admin-token"}

ADMIN_USER_RESPONSE = {
    "id": 1,
    "username": "admin",
    "role": "admin",
    "permissions": [
        "locations:create", "locations:read", "locations:update", "locations:delete",
    ],
}
REGULAR_USER_RESPONSE = {"id": 2, "username": "user", "role": "user", "permissions": []}
MODERATOR_USER_RESPONSE = {
    "id": 3,
    "username": "moderator",
    "role": "moderator",
    "permissions": ["locations:read"],
}


def _make_area(area_id=1, name="Test Area", description="Test description",
               map_image_url=None, sort_order=0):
    """Create a mock Area ORM object."""
    area = MagicMock()
    area.id = area_id
    area.name = name
    area.description = description
    area.map_image_url = map_image_url
    area.sort_order = sort_order
    return area


# ===========================================================================
# GET /locations/areas/list
# ===========================================================================

class TestGetAreasList:
    """Tests for GET /locations/areas/list (public endpoint)."""

    @patch("crud.get_areas_list", new_callable=AsyncMock, return_value=[])
    def test_empty_list(self, mock_crud, client):
        """Returns empty list when no areas exist."""
        response = client.get("/locations/areas/list")
        assert response.status_code == 200
        assert response.json() == []

    @patch("crud.get_areas_list", new_callable=AsyncMock)
    def test_list_with_areas_ordered(self, mock_crud, client):
        """Returns areas ordered by sort_order."""
        areas = [
            _make_area(area_id=1, name="Area A", sort_order=0),
            _make_area(area_id=2, name="Area B", sort_order=1),
            _make_area(area_id=3, name="Area C", sort_order=2),
        ]
        mock_crud.return_value = areas

        response = client.get("/locations/areas/list")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert data[0]["name"] == "Area A"
        assert data[1]["name"] == "Area B"
        assert data[2]["name"] == "Area C"
        assert data[0]["sort_order"] < data[1]["sort_order"] < data[2]["sort_order"]

    @patch("crud.get_areas_list", new_callable=AsyncMock)
    def test_list_returns_all_fields(self, mock_crud, client):
        """Verifies all expected fields are in the response."""
        areas = [_make_area(map_image_url="https://example.com/map.png")]
        mock_crud.return_value = areas

        response = client.get("/locations/areas/list")
        assert response.status_code == 200
        data = response.json()
        area = data[0]
        assert "id" in area
        assert "name" in area
        assert "description" in area
        assert "map_image_url" in area
        assert "sort_order" in area

    def test_list_no_auth_required(self, client):
        """GET /locations/areas/list should be accessible without auth (public)."""
        with patch("crud.get_areas_list", new_callable=AsyncMock, return_value=[]):
            response = client.get("/locations/areas/list")
            assert response.status_code == 200


# ===========================================================================
# GET /locations/areas/{area_id}/details
# ===========================================================================

class TestGetAreaDetails:
    """Tests for GET /locations/areas/{area_id}/details (public endpoint)."""

    @patch("crud.get_area_details", new_callable=AsyncMock)
    def test_get_existing_area(self, mock_crud, client):
        """Returns area details with countries when it exists."""
        mock_crud.return_value = {
            "id": 1,
            "name": "Test Area",
            "description": "A test area",
            "map_image_url": None,
            "sort_order": 0,
            "countries": [
                {
                    "id": 10,
                    "name": "Country A",
                    "description": "A country",
                    "leader_id": None,
                    "map_image_url": None,
                    "area_id": 1,
                    "x": 0.5,
                    "y": 0.5,
                }
            ],
        }

        response = client.get("/locations/areas/1/details")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "Test Area"
        assert len(data["countries"]) == 1
        assert data["countries"][0]["name"] == "Country A"
        assert data["countries"][0]["area_id"] == 1

    @patch("crud.get_area_details", new_callable=AsyncMock)
    def test_area_details_with_no_countries(self, mock_crud, client):
        """Returns area with empty countries list."""
        mock_crud.return_value = {
            "id": 2,
            "name": "Empty Area",
            "description": "No countries here",
            "map_image_url": None,
            "sort_order": 1,
            "countries": [],
        }

        response = client.get("/locations/areas/2/details")
        assert response.status_code == 200
        data = response.json()
        assert data["countries"] == []

    @patch("crud.get_area_details", new_callable=AsyncMock, return_value=None)
    def test_get_nonexistent_area_returns_404(self, mock_crud, client):
        """Returns 404 when area does not exist."""
        response = client.get("/locations/areas/99999/details")
        assert response.status_code == 404

    def test_details_no_auth_required(self, client):
        """GET /locations/areas/{id}/details should be accessible without auth."""
        with patch("crud.get_area_details", new_callable=AsyncMock, return_value={
            "id": 1, "name": "A", "description": "D",
            "map_image_url": None, "sort_order": 0, "countries": [],
        }):
            response = client.get("/locations/areas/1/details")
            assert response.status_code == 200


# ===========================================================================
# POST /locations/areas/create
# ===========================================================================

class TestCreateArea:
    """Tests for POST /locations/areas/create (admin-only)."""

    def test_missing_token_returns_401(self, client):
        """No Authorization header -> 401."""
        response = client.post(
            "/locations/areas/create",
            json={"name": "New Area", "description": "Desc"},
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client):
        """Valid token but no locations:create permission -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.post(
            "/locations/areas/create",
            json={"name": "New Area", "description": "Desc"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get, client):
        """User-service returns 401 for invalid token -> 401."""
        mock_get.return_value = _mock_response(401)
        response = client.post(
            "/locations/areas/create",
            json={"name": "New Area", "description": "Desc"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 401

    @patch("crud.create_area", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_area_success(self, mock_auth, mock_crud, client):
        """Admin can create an area."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_area(area_id=10, name="New Area", sort_order=5)

        response = client.post(
            "/locations/areas/create",
            json={"name": "New Area", "description": "Description", "sort_order": 5},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Area"
        assert data["sort_order"] == 5

    @patch("crud.create_area", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_area_default_sort_order(self, mock_auth, mock_crud, client):
        """sort_order defaults to 0 if not provided."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_area(area_id=11, name="Area Default", sort_order=0)

        response = client.post(
            "/locations/areas/create",
            json={"name": "Area Default", "description": "Desc"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["sort_order"] == 0

    @patch("auth_http.requests.get")
    def test_create_area_missing_name_returns_422(self, mock_auth, client):
        """Missing required field 'name' -> 422."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        response = client.post(
            "/locations/areas/create",
            json={"description": "No name"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422

    @patch("auth_http.requests.get")
    def test_create_area_missing_description_returns_422(self, mock_auth, client):
        """Missing required field 'description' -> 422."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        response = client.post(
            "/locations/areas/create",
            json={"name": "Only Name"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422

    @patch("auth_http.requests.get")
    def test_moderator_without_permission_returns_403(self, mock_get, client):
        """Moderator without locations:create permission -> 403."""
        mock_get.return_value = _mock_response(200, MODERATOR_USER_RESPONSE)
        response = client.post(
            "/locations/areas/create",
            json={"name": "Area", "description": "Desc"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403


# ===========================================================================
# PUT /locations/areas/{area_id}/update
# ===========================================================================

class TestUpdateArea:
    """Tests for PUT /locations/areas/{area_id}/update (admin-only)."""

    def test_missing_token_returns_401(self, client):
        """No auth -> 401."""
        response = client.put(
            "/locations/areas/1/update",
            json={"name": "Updated"},
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client):
        """Non-admin -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.put(
            "/locations/areas/1/update",
            json={"name": "Updated"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403

    @patch("crud.update_area", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_area_success(self, mock_auth, mock_crud, client):
        """Admin can partially update an area."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_area(area_id=1, name="Updated Name")

        response = client.put(
            "/locations/areas/1/update",
            json={"name": "Updated Name"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    @patch("crud.update_area", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_area_sort_order(self, mock_auth, mock_crud, client):
        """Admin can update sort_order."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_area(area_id=1, sort_order=99)

        response = client.put(
            "/locations/areas/1/update",
            json={"sort_order": 99},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["sort_order"] == 99

    @patch("crud.update_area", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_nonexistent_area_returns_404(self, mock_auth, mock_crud, client):
        """Updating non-existent area -> 404."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.side_effect = HTTPException(status_code=404, detail="Area not found")

        response = client.put(
            "/locations/areas/99999/update",
            json={"name": "Ghost"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404


# ===========================================================================
# DELETE /locations/areas/{area_id}/delete
# ===========================================================================

class TestDeleteArea:
    """Tests for DELETE /locations/areas/{area_id}/delete (admin-only)."""

    def test_missing_token_returns_401(self, client):
        """No auth -> 401."""
        response = client.delete("/locations/areas/1/delete")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client):
        """Non-admin -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.delete(
            "/locations/areas/1/delete",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403

    @patch("crud.delete_area", new_callable=AsyncMock, return_value=None)
    @patch("auth_http.requests.get")
    def test_delete_area_success(self, mock_auth, mock_crud, client):
        """Admin can delete an area."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.delete("/locations/areas/1/delete", headers=ADMIN_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "1" in data["message"]

    @patch("crud.delete_area", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_nonexistent_area_returns_404(self, mock_auth, mock_crud, client):
        """Deleting non-existent area -> 404."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.side_effect = HTTPException(status_code=404, detail="Area not found")

        response = client.delete("/locations/areas/99999/delete", headers=ADMIN_HEADERS)
        assert response.status_code == 404

    @patch("crud.delete_area", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_area_countries_get_null_area_id(self, mock_auth, mock_crud, client):
        """After deleting an area, the crud layer should handle setting area_id=NULL
        on related countries (via ON DELETE SET NULL in the DB schema).
        This test verifies the endpoint returns success and the crud function is called."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = None  # successful deletion

        response = client.delete("/locations/areas/5/delete", headers=ADMIN_HEADERS)
        assert response.status_code == 200
        # Verify crud.delete_area was called with the correct area_id
        mock_crud.assert_called_once()
        call_args = mock_crud.call_args
        # The area_id is the second positional argument (first is session)
        assert call_args[0][1] == 5


# ===========================================================================
# Security Tests
# ===========================================================================

class TestAreasSecurity:
    """Security tests for Area endpoints."""

    @patch("crud.get_area_details", new_callable=AsyncMock, return_value=None)
    def test_sql_injection_in_area_id_get(self, mock_crud, client):
        """SQL injection in area_id path param should return 422 (not a valid int)."""
        response = client.get("/locations/areas/1;DROP TABLE Areas;--/details")
        assert response.status_code == 422

    def test_sql_injection_in_area_id_delete(self, client):
        """SQL injection in delete endpoint path param -> 401/404/422."""
        response = client.delete("/locations/areas/1 OR 1=1/delete")
        assert response.status_code in (401, 404, 422)

    @patch("crud.get_areas_list", new_callable=AsyncMock, return_value=[])
    def test_xss_in_area_name_list(self, mock_crud, client):
        """XSS in area data should be returned as-is (Pydantic serialization, no HTML rendering)."""
        xss_area = _make_area(name="<script>alert('xss')</script>", description="<img onerror=alert(1)>")
        mock_crud.return_value = [xss_area]

        response = client.get("/locations/areas/list")
        assert response.status_code == 200
        # Data should be returned as strings, not executed
        data = response.json()
        assert "<script>" in data[0]["name"]
