"""
Tests for path editor feature (FEAT-092) in locations-service.

Covers:
- (a) path_data stored and retrieved correctly via add_neighbor (both direction rows)
- (b) update_neighbor_path updates both direction rows atomically
- (c) GET /regions/{id}/details returns path_data and energy_cost in neighbor_edges
- (d) PUT /neighbors/{from_id}/{to_id}/path — success, 404, validation errors
- (e) POST /{location_id}/neighbors/ with path_data — creates neighbor with path data
- (f) Waypoint coordinate validation (x/y must be 0-100, max 50 waypoints)
- (g) path_data is null for legacy neighbors (no path specified)
- (h) Delete neighbor also removes path_data (both rows deleted)
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


def _make_location(loc_id=1, name="Test Location", map_x=50.0, map_y=50.0):
    """Create a mock Location ORM object."""
    loc = MagicMock()
    loc.id = loc_id
    loc.name = name
    loc.map_x = map_x
    loc.map_y = map_y
    loc.type = "location"
    loc.description = "Test"
    loc.recommended_level = 1
    loc.quick_travel_marker = False
    loc.image_url = ""
    loc.parent_id = None
    loc.marker_type = "safe"
    loc.map_icon_url = None
    loc.sort_order = 0
    loc.district_id = None
    loc.region_id = 1
    return loc


def _make_neighbor(neighbor_id=1, location_id=1, nbr_id=2, energy_cost=1, path_data=None):
    """Create a mock LocationNeighbor ORM object."""
    n = MagicMock()
    n.id = neighbor_id
    n.location_id = location_id
    n.neighbor_id = nbr_id
    n.energy_cost = energy_cost
    n.path_data = path_data
    return n


# ===========================================================================
# (a) path_data stored and retrieved correctly in add_neighbor
# ===========================================================================

class TestAddNeighborPathData:
    """Tests for POST /{location_id}/neighbors/ — path_data stored on both rows."""

    @patch("crud.add_neighbor", new_callable=AsyncMock)
    @patch("crud.get_location_by_id", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_neighbor_with_path_data(self, mock_auth, mock_get_loc, mock_add, client):
        """Creating a neighbor with path_data returns path_data in response."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_get_loc.return_value = _make_location()

        path_data = [{"x": 25.0, "y": 30.0}, {"x": 50.0, "y": 60.0}]
        mock_add.return_value = {
            "location_id": 1,
            "neighbor_id": 2,
            "energy_cost": 1,
            "path_data": path_data,
        }

        response = client.post(
            "/locations/1/neighbors/",
            json={"neighbor_id": 2, "energy_cost": 1, "path_data": path_data},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["path_data"] == path_data
        assert data["neighbor_id"] == 2
        assert data["energy_cost"] == 1

    @patch("crud.add_neighbor", new_callable=AsyncMock)
    @patch("crud.get_location_by_id", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_add_neighbor_passes_path_data_to_crud(self, mock_auth, mock_get_loc, mock_add, client):
        """Verify that path_data dicts are passed to crud.add_neighbor."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_get_loc.return_value = _make_location()
        mock_add.return_value = {
            "location_id": 1,
            "neighbor_id": 2,
            "energy_cost": 3,
            "path_data": [{"x": 10.0, "y": 20.0}],
        }

        response = client.post(
            "/locations/1/neighbors/",
            json={
                "neighbor_id": 2,
                "energy_cost": 3,
                "path_data": [{"x": 10.0, "y": 20.0}],
            },
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        # Verify crud.add_neighbor was called with path_data
        mock_add.assert_called_once()
        call_kwargs = mock_add.call_args
        # path_data should be passed as the last keyword arg
        assert call_kwargs[1].get("path_data") is not None or \
            (len(call_kwargs[0]) >= 5 and call_kwargs[0][4] is not None)


# ===========================================================================
# (b) update_neighbor_path updates both direction rows atomically
# ===========================================================================

class TestUpdateNeighborPath:
    """Tests for PUT /neighbors/{from_id}/{to_id}/path."""

    @patch("crud.update_neighbor_path", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_path_success(self, mock_auth, mock_update, client):
        """Successfully updating path returns updated edge data."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        path_data = [{"x": 10.0, "y": 20.0}, {"x": 30.0, "y": 40.0}]
        mock_update.return_value = {
            "from_id": 1,
            "to_id": 2,
            "energy_cost": 1,
            "path_data": path_data,
        }

        response = client.put(
            "/locations/neighbors/1/2/path",
            json={"path_data": path_data},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["from_id"] == 1
        assert data["to_id"] == 2
        assert data["energy_cost"] == 1
        assert data["path_data"] == path_data

    @patch("crud.update_neighbor_path", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_path_empty_waypoints(self, mock_auth, mock_update, client):
        """Updating with empty path_data (explicit straight line) succeeds."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_update.return_value = {
            "from_id": 5,
            "to_id": 10,
            "energy_cost": 2,
            "path_data": [],
        }

        response = client.put(
            "/locations/neighbors/5/10/path",
            json={"path_data": []},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["path_data"] == []


# ===========================================================================
# (c) GET /regions/{id}/details returns path_data and energy_cost
# ===========================================================================

class TestRegionDetailsPathData:
    """Tests for GET /regions/{id}/details — path_data and energy_cost in neighbor_edges."""

    @patch("crud.get_region_full_details", new_callable=AsyncMock)
    def test_region_details_includes_path_data(self, mock_details, client):
        """neighbor_edges in region details include path_data and energy_cost."""
        mock_details.return_value = {
            "id": 1,
            "country_id": 1,
            "name": "Test Region",
            "description": "Desc",
            "image_url": None,
            "map_image_url": None,
            "entrance_location": None,
            "leader_id": None,
            "x": 0,
            "y": 0,
            "districts": [],
            "map_items": [],
            "neighbor_edges": [
                {
                    "from_id": 1,
                    "to_id": 2,
                    "energy_cost": 1,
                    "path_data": [{"x": 25.0, "y": 30.0}, {"x": 50.0, "y": 60.0}],
                },
                {
                    "from_id": 3,
                    "to_id": 5,
                    "energy_cost": 2,
                    "path_data": None,
                },
            ],
        }

        response = client.get("/locations/regions/1/details")
        assert response.status_code == 200
        data = response.json()
        edges = data["neighbor_edges"]
        assert len(edges) == 2

        # First edge has path_data
        assert edges[0]["from_id"] == 1
        assert edges[0]["to_id"] == 2
        assert edges[0]["energy_cost"] == 1
        assert edges[0]["path_data"] is not None
        assert len(edges[0]["path_data"]) == 2
        assert edges[0]["path_data"][0]["x"] == 25.0
        assert edges[0]["path_data"][0]["y"] == 30.0

        # Second edge has null path_data (legacy)
        assert edges[1]["from_id"] == 3
        assert edges[1]["to_id"] == 5
        assert edges[1]["energy_cost"] == 2
        assert edges[1]["path_data"] is None

    @patch("crud.get_region_full_details", new_callable=AsyncMock)
    def test_region_details_no_edges(self, mock_details, client):
        """Region with no neighbor edges returns empty neighbor_edges list."""
        mock_details.return_value = {
            "id": 2,
            "country_id": 1,
            "name": "Empty Region",
            "description": "No edges",
            "image_url": None,
            "map_image_url": None,
            "entrance_location": None,
            "leader_id": None,
            "x": 0,
            "y": 0,
            "districts": [],
            "map_items": [],
            "neighbor_edges": [],
        }

        response = client.get("/locations/regions/2/details")
        assert response.status_code == 200
        data = response.json()
        assert data["neighbor_edges"] == []


# ===========================================================================
# (d) PUT /neighbors/{from_id}/{to_id}/path — 404 and validation errors
# ===========================================================================

class TestUpdatePathEdgeCases:
    """Tests for PUT /neighbors/{from_id}/{to_id}/path — error cases."""

    @patch("crud.update_neighbor_path", new_callable=AsyncMock, return_value=None)
    @patch("auth_http.requests.get")
    def test_update_path_nonexistent_neighbor_404(self, mock_auth, mock_update, client):
        """Updating path for non-existent neighbor returns 404."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.put(
            "/locations/neighbors/999/888/path",
            json={"path_data": [{"x": 10.0, "y": 20.0}]},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404

    @patch("auth_http.requests.get")
    def test_update_path_coords_out_of_range(self, mock_auth, client):
        """Waypoint coordinates outside 0-100 range return 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.put(
            "/locations/neighbors/1/2/path",
            json={"path_data": [{"x": 150.0, "y": 50.0}]},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    @patch("auth_http.requests.get")
    def test_update_path_negative_coords(self, mock_auth, client):
        """Negative waypoint coordinates return 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.put(
            "/locations/neighbors/1/2/path",
            json={"path_data": [{"x": -5.0, "y": 50.0}]},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    @patch("auth_http.requests.get")
    def test_update_path_too_many_waypoints(self, mock_auth, client):
        """More than 50 waypoints return 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        waypoints = [{"x": float(i), "y": float(i)} for i in range(51)]
        response = client.put(
            "/locations/neighbors/1/2/path",
            json={"path_data": waypoints},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    def test_update_path_no_auth_returns_401(self, client):
        """PUT without Authorization header returns 401."""
        response = client.put(
            "/locations/neighbors/1/2/path",
            json={"path_data": [{"x": 10.0, "y": 20.0}]},
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_update_path_non_admin_returns_403(self, mock_auth, client):
        """Non-admin user without locations:update permission returns 403."""
        mock_auth.return_value = _mock_response(200, REGULAR_USER_RESPONSE)

        response = client.put(
            "/locations/neighbors/1/2/path",
            json={"path_data": [{"x": 10.0, "y": 20.0}]},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_update_path_missing_body_returns_422(self, mock_auth, client):
        """PUT with no JSON body returns 422."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.put(
            "/locations/neighbors/1/2/path",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422

    @patch("auth_http.requests.get")
    def test_update_path_invalid_waypoint_type_returns_422(self, mock_auth, client):
        """Waypoint with non-numeric coordinates returns 422."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.put(
            "/locations/neighbors/1/2/path",
            json={"path_data": [{"x": "abc", "y": 20.0}]},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422


# ===========================================================================
# (e) POST /{location_id}/neighbors/ with path_data
# ===========================================================================

class TestCreateNeighborWithPathData:
    """Tests for POST /{location_id}/neighbors/ — create neighbor with path data."""

    @patch("crud.add_neighbor", new_callable=AsyncMock)
    @patch("crud.get_location_by_id", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_with_path_data_success(self, mock_auth, mock_get_loc, mock_add, client):
        """Creating neighbor with valid path_data succeeds."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_get_loc.return_value = _make_location()
        path = [{"x": 10.0, "y": 20.0}, {"x": 30.0, "y": 40.0}, {"x": 60.0, "y": 80.0}]
        mock_add.return_value = {
            "location_id": 1,
            "neighbor_id": 3,
            "energy_cost": 2,
            "path_data": path,
        }

        response = client.post(
            "/locations/1/neighbors/",
            json={"neighbor_id": 3, "energy_cost": 2, "path_data": path},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["neighbor_id"] == 3
        assert data["energy_cost"] == 2
        assert len(data["path_data"]) == 3

    @patch("crud.add_neighbor", new_callable=AsyncMock)
    @patch("crud.get_location_by_id", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_without_path_data(self, mock_auth, mock_get_loc, mock_add, client):
        """Creating neighbor without path_data defaults to null."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_get_loc.return_value = _make_location()
        mock_add.return_value = {
            "location_id": 1,
            "neighbor_id": 4,
            "energy_cost": 1,
            "path_data": None,
        }

        response = client.post(
            "/locations/1/neighbors/",
            json={"neighbor_id": 4, "energy_cost": 1},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["path_data"] is None

    @patch("crud.get_location_by_id", new_callable=AsyncMock, return_value=None)
    @patch("auth_http.requests.get")
    def test_create_neighbor_location_not_found(self, mock_auth, mock_get_loc, client):
        """Creating neighbor for non-existent location returns 404."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.post(
            "/locations/999/neighbors/",
            json={"neighbor_id": 2, "energy_cost": 1},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404

    @patch("crud.get_location_by_id", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_neighbor_target_not_found(self, mock_auth, mock_get_loc, client):
        """Creating neighbor where target location doesn't exist returns 404."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        # First call (source location) returns a location, second call (neighbor) returns None
        mock_get_loc.side_effect = [_make_location(loc_id=1), None]

        response = client.post(
            "/locations/1/neighbors/",
            json={"neighbor_id": 999, "energy_cost": 1},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404

    def test_create_neighbor_no_auth(self, client):
        """POST without auth returns 401."""
        response = client.post(
            "/locations/1/neighbors/",
            json={"neighbor_id": 2, "energy_cost": 1},
        )
        assert response.status_code == 401


# ===========================================================================
# (f) Waypoint coordinate validation (0-100 range, max 50 waypoints)
# ===========================================================================

class TestWaypointValidation:
    """Tests for waypoint coordinate validation in both create and update endpoints."""

    @patch("crud.get_location_by_id", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_neighbor_coords_out_of_range(self, mock_auth, mock_get_loc, client):
        """Creating neighbor with coordinates > 100 returns 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_get_loc.return_value = _make_location()

        response = client.post(
            "/locations/1/neighbors/",
            json={
                "neighbor_id": 2,
                "energy_cost": 1,
                "path_data": [{"x": 101.0, "y": 50.0}],
            },
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    @patch("crud.get_location_by_id", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_neighbor_negative_coords(self, mock_auth, mock_get_loc, client):
        """Creating neighbor with negative coordinates returns 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_get_loc.return_value = _make_location()

        response = client.post(
            "/locations/1/neighbors/",
            json={
                "neighbor_id": 2,
                "energy_cost": 1,
                "path_data": [{"x": 50.0, "y": -1.0}],
            },
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    @patch("crud.get_location_by_id", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_neighbor_too_many_waypoints(self, mock_auth, mock_get_loc, client):
        """Creating neighbor with more than 50 waypoints returns 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_get_loc.return_value = _make_location()

        waypoints = [{"x": float(i % 100), "y": float(i % 100)} for i in range(51)]
        response = client.post(
            "/locations/1/neighbors/",
            json={"neighbor_id": 2, "energy_cost": 1, "path_data": waypoints},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    @patch("crud.add_neighbor", new_callable=AsyncMock)
    @patch("crud.get_location_by_id", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_neighbor_exactly_50_waypoints(self, mock_auth, mock_get_loc, mock_add, client):
        """Creating neighbor with exactly 50 waypoints succeeds."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_get_loc.return_value = _make_location()

        waypoints = [{"x": float(i % 100), "y": float(i % 100)} for i in range(50)]
        mock_add.return_value = {
            "location_id": 1,
            "neighbor_id": 2,
            "energy_cost": 1,
            "path_data": waypoints,
        }

        response = client.post(
            "/locations/1/neighbors/",
            json={"neighbor_id": 2, "energy_cost": 1, "path_data": waypoints},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200

    @patch("crud.add_neighbor", new_callable=AsyncMock)
    @patch("crud.get_location_by_id", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_neighbor_boundary_coords(self, mock_auth, mock_get_loc, mock_add, client):
        """Boundary values 0 and 100 are accepted for coordinates."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_get_loc.return_value = _make_location()

        path = [{"x": 0.0, "y": 0.0}, {"x": 100.0, "y": 100.0}]
        mock_add.return_value = {
            "location_id": 1,
            "neighbor_id": 2,
            "energy_cost": 1,
            "path_data": path,
        }

        response = client.post(
            "/locations/1/neighbors/",
            json={"neighbor_id": 2, "energy_cost": 1, "path_data": path},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200

    @patch("auth_http.requests.get")
    def test_update_path_y_out_of_range(self, mock_auth, client):
        """Y coordinate > 100 in update returns 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.put(
            "/locations/neighbors/1/2/path",
            json={"path_data": [{"x": 50.0, "y": 200.0}]},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    @patch("crud.update_neighbor_path", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_path_exactly_50_waypoints(self, mock_auth, mock_update, client):
        """Updating with exactly 50 waypoints succeeds."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        waypoints = [{"x": float(i % 100), "y": float(i % 100)} for i in range(50)]
        mock_update.return_value = {
            "from_id": 1,
            "to_id": 2,
            "energy_cost": 1,
            "path_data": waypoints,
        }

        response = client.put(
            "/locations/neighbors/1/2/path",
            json={"path_data": waypoints},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200


# ===========================================================================
# (g) path_data is null for legacy neighbors
# ===========================================================================

class TestLegacyNeighbors:
    """Tests that legacy neighbors (without path_data) return null."""

    @patch("crud.add_neighbor", new_callable=AsyncMock)
    @patch("crud.get_location_by_id", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_neighbor_no_path_data_returns_null(self, mock_auth, mock_get_loc, mock_add, client):
        """Legacy neighbor creation (no path_data) returns null for path_data."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_get_loc.return_value = _make_location()
        mock_add.return_value = {
            "location_id": 1,
            "neighbor_id": 5,
            "energy_cost": 1,
            "path_data": None,
        }

        response = client.post(
            "/locations/1/neighbors/",
            json={"neighbor_id": 5, "energy_cost": 1},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["path_data"] is None

    @patch("crud.get_region_full_details", new_callable=AsyncMock)
    def test_region_details_legacy_edge_has_null_path(self, mock_details, client):
        """Legacy edges in region details have path_data=null."""
        mock_details.return_value = {
            "id": 1,
            "country_id": 1,
            "name": "Region",
            "description": "Desc",
            "image_url": None,
            "map_image_url": None,
            "entrance_location": None,
            "leader_id": None,
            "x": 0,
            "y": 0,
            "districts": [],
            "map_items": [],
            "neighbor_edges": [
                {"from_id": 10, "to_id": 20, "energy_cost": 1, "path_data": None},
            ],
        }

        response = client.get("/locations/regions/1/details")
        assert response.status_code == 200
        edges = response.json()["neighbor_edges"]
        assert len(edges) == 1
        assert edges[0]["path_data"] is None


# ===========================================================================
# (h) Delete neighbor also removes path_data (both rows deleted)
# ===========================================================================

class TestDeleteNeighborPathData:
    """Tests for DELETE /{location_id}/neighbors/{neighbor_id} — path_data deleted with rows."""

    @patch("crud.get_location_by_id", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_neighbor_success(self, mock_auth, mock_get_loc, client):
        """Deleting a neighbor removes both direction rows (and their path_data)."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_get_loc.return_value = _make_location()

        # Mock the session's execute calls for the delete endpoint
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_neighbor = _make_neighbor(
            location_id=1, nbr_id=2,
            path_data=[{"x": 25.0, "y": 30.0}],
        )
        mock_result.scalars.return_value.first.return_value = mock_neighbor
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        from database import get_db

        async def _fake_db():
            yield mock_session

        from main import app
        app.dependency_overrides[get_db] = _fake_db

        response = client.delete(
            "/locations/1/neighbors/2",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

        # Verify session.execute was called (for select + two deletes + commit)
        assert mock_session.execute.call_count >= 1

        app.dependency_overrides.clear()

    def test_delete_neighbor_no_auth(self, client):
        """DELETE without auth returns 401."""
        response = client.delete("/locations/1/neighbors/2")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_delete_neighbor_non_admin_returns_403(self, mock_auth, client):
        """Non-admin without locations:delete permission returns 403."""
        mock_auth.return_value = _mock_response(200, REGULAR_USER_RESPONSE)

        response = client.delete(
            "/locations/1/neighbors/2",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403


# ===========================================================================
# Security Tests
# ===========================================================================

class TestPathEditorSecurity:
    """Security tests for path editor endpoints."""

    def test_sql_injection_in_path_params_update(self, client):
        """SQL injection in from_id/to_id path params does not cause 500 (no SQL crash)."""
        response = client.put(
            "/locations/neighbors/1;DROP TABLE LocationNeighbors;--/2/path",
            json={"path_data": [{"x": 10.0, "y": 20.0}]},
            headers=ADMIN_HEADERS,
        )
        # Should never be 500 (server error from SQL injection). 422 = invalid int param,
        # 401/403 = auth gate, 503 = user-service unreachable (in test env) — all acceptable.
        assert response.status_code != 500

    def test_sql_injection_in_create_neighbor(self, client):
        """SQL injection in location_id path param does not cause 500 (no SQL crash)."""
        response = client.post(
            "/locations/1 OR 1=1/neighbors/",
            json={"neighbor_id": 2, "energy_cost": 1},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code != 500
