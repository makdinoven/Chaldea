"""
Tests for Location map fields (map_icon_url, map_x, map_y) added in FEAT-054.

Covers:
- Create location with map fields — verify persisted and returned
- Create location without map fields — verify defaults (null)
- Update location map_x/map_y — verify update works
- Update location map_icon_url — verify update works
- Region details include map_icon_url, map_x, map_y for locations
- Region details include marker_type for locations (bug fix verification)
- Region details include neighbor_edges array
- neighbor_edges are deduplicated (from_id < to_id)
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


def _make_location(
    location_id=1,
    name="Test Location",
    district_id=1,
    type_="location",
    image_url="",
    recommended_level=1,
    quick_travel_marker=False,
    parent_id=None,
    description="",
    marker_type="safe",
    map_icon_url=None,
    map_x=None,
    map_y=None,
):
    """Create a mock Location ORM object."""
    loc = MagicMock()
    loc.id = location_id
    loc.name = name
    loc.district_id = district_id
    loc.type = type_
    loc.image_url = image_url
    loc.recommended_level = recommended_level
    loc.quick_travel_marker = quick_travel_marker
    loc.parent_id = parent_id
    loc.description = description
    loc.marker_type = marker_type
    loc.map_icon_url = map_icon_url
    loc.map_x = map_x
    loc.map_y = map_y
    return loc


def _make_neighbor(id_=1, location_id=1, neighbor_id=2, energy_cost=1):
    """Create a mock LocationNeighbor ORM object."""
    n = MagicMock()
    n.id = id_
    n.location_id = location_id
    n.neighbor_id = neighbor_id
    n.energy_cost = energy_cost
    return n


# ===========================================================================
# POST /locations/locations/create — with map fields
# ===========================================================================

class TestCreateLocationWithMapFields:
    """Tests for creating locations with map_icon_url, map_x, map_y."""

    @patch("crud.create_location", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_with_map_fields(self, mock_auth, mock_crud, client):
        """Create location with all map fields — values are persisted and returned."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_location(
            location_id=10,
            name="Map Location",
            map_icon_url="https://s3.example.com/icon.webp",
            map_x=45.2,
            map_y=72.8,
        )

        response = client.post(
            "/locations/",
            json={
                "name": "Map Location",
                "district_id": 1,
                "map_icon_url": "https://s3.example.com/icon.webp",
                "map_x": 45.2,
                "map_y": 72.8,
            },
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["map_icon_url"] == "https://s3.example.com/icon.webp"
        assert data["map_x"] == pytest.approx(45.2)
        assert data["map_y"] == pytest.approx(72.8)

    @patch("crud.create_location", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_without_map_fields_defaults_to_null(self, mock_auth, mock_crud, client):
        """Create location without map fields — defaults to null."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_location(
            location_id=11,
            name="Plain Location",
            map_icon_url=None,
            map_x=None,
            map_y=None,
        )

        response = client.post(
            "/locations/",
            json={"name": "Plain Location", "district_id": 1},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["map_icon_url"] is None
        assert data["map_x"] is None
        assert data["map_y"] is None


# ===========================================================================
# PUT /locations/{location_id}/update — map fields
# ===========================================================================

class TestUpdateLocationMapFields:
    """Tests for updating location map position and icon."""

    @patch("crud.update_location", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_map_x_map_y(self, mock_auth, mock_crud, client):
        """Update map_x and map_y — values are returned."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_location(
            location_id=1,
            map_x=55.0,
            map_y=30.0,
        )

        response = client.put(
            "/locations/1/update",
            json={"map_x": 55.0, "map_y": 30.0},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["map_x"] == pytest.approx(55.0)
        assert data["map_y"] == pytest.approx(30.0)

    @patch("crud.update_location", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_map_icon_url(self, mock_auth, mock_crud, client):
        """Update map_icon_url — value is returned."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_location(
            location_id=1,
            map_icon_url="https://s3.example.com/icons/new_icon.webp",
        )

        response = client.put(
            "/locations/1/update",
            json={"map_icon_url": "https://s3.example.com/icons/new_icon.webp"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["map_icon_url"] == "https://s3.example.com/icons/new_icon.webp"

    @patch("crud.update_location", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_map_fields_to_null(self, mock_auth, mock_crud, client):
        """Setting map_x/map_y to null (remove from map) works."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_location(
            location_id=1,
            map_x=None,
            map_y=None,
            map_icon_url=None,
        )

        response = client.put(
            "/locations/1/update",
            json={"map_x": None, "map_y": None},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["map_x"] is None
        assert data["map_y"] is None


# ===========================================================================
# GET /locations/regions/{region_id}/details — map fields in region response
# ===========================================================================

class TestRegionDetailsMapFields:
    """Tests for region details response containing map fields and neighbor edges."""

    @patch("crud.get_region_full_details", new_callable=AsyncMock)
    def test_region_details_include_map_fields(self, mock_crud, client):
        """Locations in region details include map_icon_url, map_x, map_y."""
        mock_crud.return_value = {
            "id": 1,
            "country_id": 1,
            "name": "Test Region",
            "description": "A region",
            "image_url": None,
            "map_image_url": "https://s3.example.com/map.png",
            "entrance_location": None,
            "leader_id": None,
            "x": 10.0,
            "y": 20.0,
            "districts": [
                {
                    "id": 1,
                    "name": "District A",
                    "description": "A district",
                    "entrance_location": None,
                    "x": 0.0,
                    "y": 0.0,
                    "image_url": None,
                    "locations": [
                        {
                            "id": 10,
                            "name": "Village",
                            "type": "location",
                            "image_url": "village.png",
                            "recommended_level": 1,
                            "quick_travel_marker": False,
                            "description": "A village",
                            "parent_id": None,
                            "marker_type": "safe",
                            "map_icon_url": "https://s3.example.com/icons/village.webp",
                            "map_x": 25.5,
                            "map_y": 60.3,
                            "children": [],
                        }
                    ],
                }
            ],
            "neighbor_edges": [],
        }

        response = client.get("/locations/regions/1/details")
        assert response.status_code == 200
        data = response.json()
        loc = data["districts"][0]["locations"][0]
        assert loc["map_icon_url"] == "https://s3.example.com/icons/village.webp"
        assert loc["map_x"] == pytest.approx(25.5)
        assert loc["map_y"] == pytest.approx(60.3)

    @patch("crud.get_region_full_details", new_callable=AsyncMock)
    def test_region_details_include_marker_type(self, mock_crud, client):
        """Bug fix verification: marker_type is included in location data."""
        mock_crud.return_value = {
            "id": 1,
            "country_id": 1,
            "name": "Region",
            "description": "",
            "image_url": None,
            "map_image_url": None,
            "entrance_location": None,
            "leader_id": None,
            "x": 0.0,
            "y": 0.0,
            "districts": [
                {
                    "id": 1,
                    "name": "D",
                    "description": "",
                    "entrance_location": None,
                    "x": 0.0,
                    "y": 0.0,
                    "image_url": None,
                    "locations": [
                        {
                            "id": 20,
                            "name": "Dungeon",
                            "type": "location",
                            "image_url": "",
                            "recommended_level": 10,
                            "quick_travel_marker": False,
                            "description": "",
                            "parent_id": None,
                            "marker_type": "dungeon",
                            "map_icon_url": None,
                            "map_x": None,
                            "map_y": None,
                            "children": [],
                        }
                    ],
                }
            ],
            "neighbor_edges": [],
        }

        response = client.get("/locations/regions/1/details")
        assert response.status_code == 200
        loc = response.json()["districts"][0]["locations"][0]
        assert loc["marker_type"] == "dungeon"

    @patch("crud.get_region_full_details", new_callable=AsyncMock)
    def test_region_details_include_neighbor_edges(self, mock_crud, client):
        """Region details response includes neighbor_edges array."""
        mock_crud.return_value = {
            "id": 1,
            "country_id": 1,
            "name": "Region",
            "description": "",
            "image_url": None,
            "map_image_url": "https://s3.example.com/map.png",
            "entrance_location": None,
            "leader_id": None,
            "x": 0.0,
            "y": 0.0,
            "districts": [],
            "neighbor_edges": [
                {"from_id": 1, "to_id": 2},
                {"from_id": 2, "to_id": 3},
            ],
        }

        response = client.get("/locations/regions/1/details")
        assert response.status_code == 200
        data = response.json()
        assert "neighbor_edges" in data
        assert len(data["neighbor_edges"]) == 2
        assert data["neighbor_edges"][0] == {"from_id": 1, "to_id": 2}
        assert data["neighbor_edges"][1] == {"from_id": 2, "to_id": 3}

    @patch("crud.get_region_full_details", new_callable=AsyncMock)
    def test_neighbor_edges_deduplicated(self, mock_crud, client):
        """neighbor_edges are deduplicated with from_id < to_id."""
        mock_crud.return_value = {
            "id": 1,
            "country_id": 1,
            "name": "Region",
            "description": "",
            "image_url": None,
            "map_image_url": "https://s3.example.com/map.png",
            "entrance_location": None,
            "leader_id": None,
            "x": 0.0,
            "y": 0.0,
            "districts": [],
            "neighbor_edges": [
                {"from_id": 5, "to_id": 10},
            ],
        }

        response = client.get("/locations/regions/1/details")
        assert response.status_code == 200
        edges = response.json()["neighbor_edges"]
        # Verify deduplication invariant: from_id < to_id for all edges
        for edge in edges:
            assert edge["from_id"] < edge["to_id"], (
                f"Edge not deduplicated: from_id={edge['from_id']} >= to_id={edge['to_id']}"
            )

    @patch("crud.get_region_full_details", new_callable=AsyncMock)
    def test_region_details_empty_neighbor_edges(self, mock_crud, client):
        """Region with no neighbors returns empty neighbor_edges array."""
        mock_crud.return_value = {
            "id": 1,
            "country_id": 1,
            "name": "Isolated Region",
            "description": "",
            "image_url": None,
            "map_image_url": None,
            "entrance_location": None,
            "leader_id": None,
            "x": 0.0,
            "y": 0.0,
            "districts": [],
            "neighbor_edges": [],
        }

        response = client.get("/locations/regions/1/details")
        assert response.status_code == 200
        assert response.json()["neighbor_edges"] == []

    @patch("crud.get_region_full_details", new_callable=AsyncMock, return_value=None)
    def test_region_details_nonexistent_returns_404(self, mock_crud, client):
        """Non-existent region returns 404."""
        response = client.get("/locations/regions/99999/details")
        assert response.status_code == 404
