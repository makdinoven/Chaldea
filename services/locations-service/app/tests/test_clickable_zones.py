"""
Tests for ClickableZone CRUD endpoints in locations-service.

Covers:
- GET /locations/clickable-zones/{parent_type}/{parent_id} — get zones by parent, invalid parent_type
- POST /locations/clickable-zones/create — create zone (success + validation of zone_data), auth
- PUT /locations/clickable-zones/{zone_id}/update — update zone, 404 for non-existent, auth
- DELETE /locations/clickable-zones/{zone_id}/delete — delete zone, 404, auth
- Test invalid parent_type/target_type values
- Security: SQL injection
"""

from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException

import pytest


# ---------------------------------------------------------------------------
# Helpers
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


def _make_zone(zone_id=1, parent_type="area", parent_id=1,
               target_type="country", target_id=10,
               zone_data=None, label=None):
    """Create a mock ClickableZone ORM object."""
    zone = MagicMock()
    zone.id = zone_id
    zone.parent_type = parent_type
    zone.parent_id = parent_id
    zone.target_type = target_type
    zone.target_id = target_id
    zone.zone_data = zone_data or [{"x": 0.1, "y": 0.2}, {"x": 0.3, "y": 0.4}]
    zone.label = label
    return zone


VALID_ZONE_PAYLOAD = {
    "parent_type": "area",
    "parent_id": 1,
    "target_type": "country",
    "target_id": 10,
    "zone_data": [{"x": 0.1, "y": 0.2}, {"x": 0.3, "y": 0.4}, {"x": 0.5, "y": 0.6}],
    "label": "Test Zone",
}


# ===========================================================================
# GET /locations/clickable-zones/{parent_type}/{parent_id}
# ===========================================================================

class TestGetClickableZones:
    """Tests for GET /locations/clickable-zones/{parent_type}/{parent_id} (public)."""

    @patch("crud.get_clickable_zones_by_parent", new_callable=AsyncMock, return_value=[])
    def test_get_zones_empty(self, mock_crud, client):
        """Returns empty list when no zones for given parent."""
        response = client.get("/locations/clickable-zones/area/1")
        assert response.status_code == 200
        assert response.json() == []

    @patch("crud.get_clickable_zones_by_parent", new_callable=AsyncMock)
    def test_get_zones_by_area(self, mock_crud, client):
        """Returns zones for area parent."""
        zones = [
            _make_zone(zone_id=1, parent_type="area", parent_id=1),
            _make_zone(zone_id=2, parent_type="area", parent_id=1, target_id=20),
        ]
        mock_crud.return_value = zones

        response = client.get("/locations/clickable-zones/area/1")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    @patch("crud.get_clickable_zones_by_parent", new_callable=AsyncMock)
    def test_get_zones_by_country(self, mock_crud, client):
        """Returns zones for country parent."""
        zones = [_make_zone(zone_id=3, parent_type="country", parent_id=5, target_type="region")]
        mock_crud.return_value = zones

        response = client.get("/locations/clickable-zones/country/5")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["parent_type"] == "country"

    def test_invalid_parent_type_returns_400(self, client):
        """parent_type must be 'area' or 'country', otherwise 400."""
        response = client.get("/locations/clickable-zones/invalid_type/1")
        assert response.status_code == 400

    def test_invalid_parent_type_region_returns_400(self, client):
        """parent_type='region' is not allowed."""
        response = client.get("/locations/clickable-zones/region/1")
        assert response.status_code == 400

    @patch("crud.get_clickable_zones_by_parent", new_callable=AsyncMock)
    def test_returns_all_fields(self, mock_crud, client):
        """Verifies all expected fields in response."""
        zones = [_make_zone(label="My Label")]
        mock_crud.return_value = zones

        response = client.get("/locations/clickable-zones/area/1")
        assert response.status_code == 200
        z = response.json()[0]
        assert "id" in z
        assert "parent_type" in z
        assert "parent_id" in z
        assert "target_type" in z
        assert "target_id" in z
        assert "zone_data" in z
        assert "label" in z

    def test_no_auth_required(self, client):
        """GET clickable-zones should be accessible without auth."""
        with patch("crud.get_clickable_zones_by_parent", new_callable=AsyncMock, return_value=[]):
            response = client.get("/locations/clickable-zones/area/1")
            assert response.status_code == 200


# ===========================================================================
# POST /locations/clickable-zones/create
# ===========================================================================

class TestCreateClickableZone:
    """Tests for POST /locations/clickable-zones/create (admin-only)."""

    def test_missing_token_returns_401(self, client):
        """No Authorization header -> 401."""
        response = client.post("/locations/clickable-zones/create", json=VALID_ZONE_PAYLOAD)
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client):
        """Valid token but no locations:create permission -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.post(
            "/locations/clickable-zones/create",
            json=VALID_ZONE_PAYLOAD,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403

    @patch("crud.create_clickable_zone", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_zone_success(self, mock_auth, mock_crud, client):
        """Admin can create a clickable zone."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_zone(
            zone_id=10,
            label="Created Zone",
            zone_data=[{"x": 0.1, "y": 0.2}, {"x": 0.3, "y": 0.4}, {"x": 0.5, "y": 0.6}],
        )

        response = client.post(
            "/locations/clickable-zones/create",
            json=VALID_ZONE_PAYLOAD,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["label"] == "Created Zone"
        assert len(data["zone_data"]) == 3

    @patch("crud.create_clickable_zone", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_zone_without_label(self, mock_auth, mock_crud, client):
        """Label is optional; zone should be created without it."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_zone(zone_id=11, label=None)

        payload = {**VALID_ZONE_PAYLOAD}
        del payload["label"]

        response = client.post(
            "/locations/clickable-zones/create",
            json=payload,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["label"] is None

    @patch("auth_http.requests.get")
    def test_create_zone_missing_zone_data_returns_422(self, mock_auth, client):
        """Missing required field 'zone_data' -> 422."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        payload = {
            "parent_type": "area",
            "parent_id": 1,
            "target_type": "country",
            "target_id": 10,
        }
        response = client.post(
            "/locations/clickable-zones/create",
            json=payload,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422

    @patch("auth_http.requests.get")
    def test_create_zone_invalid_zone_data_format_returns_422(self, mock_auth, client):
        """zone_data must be a list of {x, y} objects."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        payload = {
            **VALID_ZONE_PAYLOAD,
            "zone_data": [{"bad_key": 1}],
        }
        response = client.post(
            "/locations/clickable-zones/create",
            json=payload,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422

    @patch("auth_http.requests.get")
    def test_create_zone_invalid_parent_type_returns_422(self, mock_auth, client):
        """parent_type must be 'area' or 'country' (Literal validation)."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        payload = {
            **VALID_ZONE_PAYLOAD,
            "parent_type": "district",
        }
        response = client.post(
            "/locations/clickable-zones/create",
            json=payload,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422

    @patch("auth_http.requests.get")
    def test_create_zone_invalid_target_type_returns_422(self, mock_auth, client):
        """target_type must be 'country' or 'region' (Literal validation)."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        payload = {
            **VALID_ZONE_PAYLOAD,
            "target_type": "location",
        }
        response = client.post(
            "/locations/clickable-zones/create",
            json=payload,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422


# ===========================================================================
# PUT /locations/clickable-zones/{zone_id}/update
# ===========================================================================

class TestUpdateClickableZone:
    """Tests for PUT /locations/clickable-zones/{zone_id}/update (admin-only)."""

    def test_missing_token_returns_401(self, client):
        """No auth -> 401."""
        response = client.put(
            "/locations/clickable-zones/1/update",
            json={"label": "Updated"},
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client):
        """Non-admin -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.put(
            "/locations/clickable-zones/1/update",
            json={"label": "Updated"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403

    @patch("crud.update_clickable_zone", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_zone_success(self, mock_auth, mock_crud, client):
        """Admin can partially update a clickable zone."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_zone(zone_id=1, label="Updated Label")

        response = client.put(
            "/locations/clickable-zones/1/update",
            json={"label": "Updated Label"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["label"] == "Updated Label"

    @patch("crud.update_clickable_zone", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_zone_data(self, mock_auth, mock_crud, client):
        """Admin can update zone_data points."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        new_zone_data = [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 1.0}]
        mock_crud.return_value = _make_zone(zone_id=1, zone_data=new_zone_data)

        response = client.put(
            "/locations/clickable-zones/1/update",
            json={"zone_data": new_zone_data},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["zone_data"]) == 2

    @patch("crud.update_clickable_zone", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_nonexistent_zone_returns_404(self, mock_auth, mock_crud, client):
        """Updating non-existent zone -> 404."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.side_effect = HTTPException(status_code=404, detail="ClickableZone not found")

        response = client.put(
            "/locations/clickable-zones/99999/update",
            json={"label": "Ghost"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404

    @patch("auth_http.requests.get")
    def test_update_zone_invalid_parent_type_returns_422(self, mock_auth, client):
        """parent_type must be 'area' or 'country'."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        response = client.put(
            "/locations/clickable-zones/1/update",
            json={"parent_type": "invalid"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422

    @patch("auth_http.requests.get")
    def test_update_zone_invalid_target_type_returns_422(self, mock_auth, client):
        """target_type must be 'country' or 'region'."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        response = client.put(
            "/locations/clickable-zones/1/update",
            json={"target_type": "area"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422


# ===========================================================================
# DELETE /locations/clickable-zones/{zone_id}/delete
# ===========================================================================

class TestDeleteClickableZone:
    """Tests for DELETE /locations/clickable-zones/{zone_id}/delete (admin-only)."""

    def test_missing_token_returns_401(self, client):
        """No auth -> 401."""
        response = client.delete("/locations/clickable-zones/1/delete")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client):
        """Non-admin -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.delete(
            "/locations/clickable-zones/1/delete",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403

    @patch("crud.delete_clickable_zone", new_callable=AsyncMock, return_value=None)
    @patch("auth_http.requests.get")
    def test_delete_zone_success(self, mock_auth, mock_crud, client):
        """Admin can delete a clickable zone."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.delete(
            "/locations/clickable-zones/1/delete",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "1" in data["message"]

    @patch("crud.delete_clickable_zone", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_nonexistent_zone_returns_404(self, mock_auth, mock_crud, client):
        """Deleting non-existent zone -> 404."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.side_effect = HTTPException(status_code=404, detail="ClickableZone not found")

        response = client.delete(
            "/locations/clickable-zones/99999/delete",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404


# ===========================================================================
# Security Tests
# ===========================================================================

class TestClickableZonesSecurity:
    """Security tests for ClickableZone endpoints."""

    def test_sql_injection_in_zone_id_delete(self, client):
        """SQL injection in zone_id path param -> 401/404/422."""
        response = client.delete("/locations/clickable-zones/1;DROP TABLE ClickableZones;--/delete")
        assert response.status_code in (401, 404, 422)

    @patch("crud.get_clickable_zones_by_parent", new_callable=AsyncMock, return_value=[])
    def test_sql_injection_in_parent_id_get(self, mock_crud, client):
        """SQL injection in parent_id path param -> 400/422 (invalid int or invalid parent_type)."""
        response = client.get("/locations/clickable-zones/area/1 OR 1=1")
        assert response.status_code in (400, 422)
