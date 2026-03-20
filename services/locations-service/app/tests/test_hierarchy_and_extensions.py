"""
Tests for hierarchy tree endpoint and extended country/location endpoints.

Covers:
- GET /locations/hierarchy/tree — correct nested structure, orphan countries at root
- POST /locations/countries/create — country with area_id, x, y
- PUT /locations/countries/{id}/update — country with area_id, x, y
- PUT /locations/{id}/update — location with marker_type
- GET /locations/admin/data — admin data includes areas
- Countries without area appear at root of tree
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


def _make_country(country_id=1, name="Test Country", description="Desc",
                  leader_id=None, map_image_url=None, emblem_url=None,
                  area_id=None, x=None, y=None):
    """Create a mock Country ORM object."""
    country = MagicMock()
    country.id = country_id
    country.name = name
    country.description = description
    country.leader_id = leader_id
    country.map_image_url = map_image_url
    country.emblem_url = emblem_url
    country.area_id = area_id
    country.x = x
    country.y = y
    return country


def _make_location(location_id=1, name="Test Location", district_id=1,
                   type_="location", image_url="", recommended_level=1,
                   quick_travel_marker=False, parent_id=None,
                   description="Loc desc", marker_type="safe"):
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
    return loc


# ===========================================================================
# GET /locations/hierarchy/tree
# ===========================================================================

class TestHierarchyTree:
    """Tests for GET /locations/hierarchy/tree (public endpoint)."""

    @patch("crud.get_hierarchy_tree", new_callable=AsyncMock, return_value=[])
    def test_empty_tree(self, mock_crud, client):
        """Returns empty list when no data exists."""
        response = client.get("/locations/hierarchy/tree")
        assert response.status_code == 200
        assert response.json() == []

    @patch("crud.get_hierarchy_tree", new_callable=AsyncMock)
    def test_tree_correct_nested_structure(self, mock_crud, client):
        """Returns correct Area -> Country -> Region -> District -> Location hierarchy."""
        tree = [
            {
                "id": 1,
                "name": "Area 1",
                "type": "area",
                "children": [
                    {
                        "id": 10,
                        "name": "Country A",
                        "type": "country",
                        "children": [
                            {
                                "id": 100,
                                "name": "Region X",
                                "type": "region",
                                "children": [
                                    {
                                        "id": 1000,
                                        "name": "District Z",
                                        "type": "district",
                                        "children": [
                                            {
                                                "id": 10000,
                                                "name": "Location Q",
                                                "type": "location",
                                                "marker_type": "safe",
                                                "children": [],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
        mock_crud.return_value = tree

        response = client.get("/locations/hierarchy/tree")
        assert response.status_code == 200
        data = response.json()

        assert len(data) == 1
        area = data[0]
        assert area["type"] == "area"
        assert area["name"] == "Area 1"

        country = area["children"][0]
        assert country["type"] == "country"
        assert country["name"] == "Country A"

        region = country["children"][0]
        assert region["type"] == "region"

        district = region["children"][0]
        assert district["type"] == "district"

        location = district["children"][0]
        assert location["type"] == "location"
        assert location["marker_type"] == "safe"

    @patch("crud.get_hierarchy_tree", new_callable=AsyncMock)
    def test_orphan_countries_at_root(self, mock_crud, client):
        """Countries without area_id appear at root level of the tree."""
        tree = [
            {
                "id": 1,
                "name": "Area 1",
                "type": "area",
                "children": [],
            },
            {
                "id": 99,
                "name": "Orphan Country",
                "type": "country",
                "children": [],
            },
        ]
        mock_crud.return_value = tree

        response = client.get("/locations/hierarchy/tree")
        assert response.status_code == 200
        data = response.json()

        # Should have 2 root nodes: area + orphan country
        assert len(data) == 2
        types = [node["type"] for node in data]
        assert "area" in types
        assert "country" in types

        orphan = next(n for n in data if n["type"] == "country")
        assert orphan["name"] == "Orphan Country"

    @patch("crud.get_hierarchy_tree", new_callable=AsyncMock)
    def test_tree_multiple_areas(self, mock_crud, client):
        """Multiple areas are returned in order."""
        tree = [
            {"id": 1, "name": "Area A", "type": "area", "children": []},
            {"id": 2, "name": "Area B", "type": "area", "children": []},
            {"id": 3, "name": "Area C", "type": "area", "children": []},
        ]
        mock_crud.return_value = tree

        response = client.get("/locations/hierarchy/tree")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert data[0]["name"] == "Area A"

    @patch("crud.get_hierarchy_tree", new_callable=AsyncMock)
    def test_tree_location_marker_types(self, mock_crud, client):
        """Locations in the tree include marker_type field."""
        tree = [
            {
                "id": 1,
                "name": "Area",
                "type": "area",
                "children": [
                    {
                        "id": 10,
                        "name": "Country",
                        "type": "country",
                        "children": [
                            {
                                "id": 100,
                                "name": "Region",
                                "type": "region",
                                "children": [
                                    {
                                        "id": 1000,
                                        "name": "District",
                                        "type": "district",
                                        "children": [
                                            {"id": 1, "name": "Safe Loc", "type": "location", "marker_type": "safe", "children": []},
                                            {"id": 2, "name": "Danger Loc", "type": "location", "marker_type": "dangerous", "children": []},
                                            {"id": 3, "name": "Dungeon", "type": "location", "marker_type": "dungeon", "children": []},
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
        mock_crud.return_value = tree

        response = client.get("/locations/hierarchy/tree")
        assert response.status_code == 200
        data = response.json()
        locations = data[0]["children"][0]["children"][0]["children"][0]["children"]
        marker_types = [loc["marker_type"] for loc in locations]
        assert "safe" in marker_types
        assert "dangerous" in marker_types
        assert "dungeon" in marker_types

    def test_tree_no_auth_required(self, client):
        """GET /locations/hierarchy/tree should be accessible without auth."""
        with patch("crud.get_hierarchy_tree", new_callable=AsyncMock, return_value=[]):
            response = client.get("/locations/hierarchy/tree")
            assert response.status_code == 200


# ===========================================================================
# POST /locations/countries/create — with area_id, x, y
# ===========================================================================

class TestCreateCountryExtended:
    """Tests for country create with new area_id, x, y fields."""

    @patch("crud.create_new_country", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_country_with_area_id(self, mock_auth, mock_crud, client):
        """Admin can create a country with area_id, x, y."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_country(
            country_id=1, name="New Country", area_id=5, x=0.3, y=0.7,
        )

        response = client.post(
            "/locations/countries/create",
            json={
                "name": "New Country",
                "description": "A country in an area",
                "area_id": 5,
                "x": 0.3,
                "y": 0.7,
            },
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["area_id"] == 5
        assert data["x"] == 0.3
        assert data["y"] == 0.7

    @patch("crud.create_new_country", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_country_without_area_id(self, mock_auth, mock_crud, client):
        """Country can be created without area_id (orphan country)."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_country(
            country_id=2, name="Orphan Country", area_id=None, x=None, y=None,
        )

        response = client.post(
            "/locations/countries/create",
            json={"name": "Orphan Country", "description": "No area"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["area_id"] is None

    def test_create_country_no_auth_returns_401(self, client):
        """No auth -> 401."""
        response = client.post(
            "/locations/countries/create",
            json={"name": "C", "description": "D"},
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_create_country_non_admin_returns_403(self, mock_get, client):
        """Non-admin -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.post(
            "/locations/countries/create",
            json={"name": "C", "description": "D"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403


# ===========================================================================
# PUT /locations/countries/{id}/update — with area_id, x, y
# ===========================================================================

class TestUpdateCountryExtended:
    """Tests for country update with new area_id, x, y fields."""

    @patch("crud.update_country", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_country_area_id(self, mock_auth, mock_crud, client):
        """Admin can update country area_id."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_country(country_id=1, area_id=3, x=0.5, y=0.5)

        response = client.put(
            "/locations/countries/1/update",
            json={"area_id": 3, "x": 0.5, "y": 0.5},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["area_id"] == 3
        assert data["x"] == 0.5
        assert data["y"] == 0.5

    @patch("crud.update_country", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_country_remove_area(self, mock_auth, mock_crud, client):
        """Admin can set area_id to null (orphan the country)."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_country(country_id=1, area_id=None)

        response = client.put(
            "/locations/countries/1/update",
            json={"area_id": None},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["area_id"] is None

    @patch("crud.update_country", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_nonexistent_country_returns_404(self, mock_auth, mock_crud, client):
        """Updating non-existent country -> 404."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.side_effect = HTTPException(status_code=404, detail="Country not found")

        response = client.put(
            "/locations/countries/99999/update",
            json={"name": "Ghost"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404

    def test_update_country_no_auth_returns_401(self, client):
        """No auth -> 401."""
        response = client.put(
            "/locations/countries/1/update",
            json={"name": "New Name"},
        )
        assert response.status_code == 401


# ===========================================================================
# PUT /locations/{location_id}/update — with marker_type
# ===========================================================================

class TestUpdateLocationMarkerType:
    """Tests for location update with marker_type field."""

    @patch("crud.update_location", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_location_marker_type_safe(self, mock_auth, mock_crud, client):
        """Admin can set marker_type to 'safe'."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_location(
            location_id=1, marker_type="safe",
        )

        response = client.put(
            "/locations/1/update",
            json={"marker_type": "safe"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200

    @patch("crud.update_location", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_location_marker_type_dangerous(self, mock_auth, mock_crud, client):
        """Admin can set marker_type to 'dangerous'."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_location(
            location_id=1, marker_type="dangerous",
        )

        response = client.put(
            "/locations/1/update",
            json={"marker_type": "dangerous"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200

    @patch("crud.update_location", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_location_marker_type_dungeon(self, mock_auth, mock_crud, client):
        """Admin can set marker_type to 'dungeon'."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_location(
            location_id=1, marker_type="dungeon",
        )

        response = client.put(
            "/locations/1/update",
            json={"marker_type": "dungeon"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200

    @patch("auth_http.requests.get")
    def test_update_location_invalid_marker_type_returns_422(self, mock_auth, client):
        """marker_type must be 'safe', 'dangerous', or 'dungeon'."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        response = client.put(
            "/locations/1/update",
            json={"marker_type": "invalid_type"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422

    def test_update_location_no_auth_returns_401(self, client):
        """No auth -> 401."""
        response = client.put(
            "/locations/1/update",
            json={"marker_type": "safe"},
        )
        assert response.status_code == 401


# ===========================================================================
# GET /locations/admin/data — includes areas
# ===========================================================================

class TestAdminDataIncludesAreas:
    """Tests for GET /locations/admin/data — verify areas are included."""

    @patch("crud.get_admin_panel_data", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_admin_data_includes_areas(self, mock_auth, mock_crud, client):
        """Admin panel data should include 'areas' key."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = {
            "areas": [
                {"id": 1, "name": "Area 1", "description": "D1", "map_image_url": None, "sort_order": 0},
                {"id": 2, "name": "Area 2", "description": "D2", "map_image_url": None, "sort_order": 1},
            ],
            "countries": [],
            "regions": [],
        }

        response = client.get("/locations/admin/data", headers=ADMIN_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert "areas" in data
        assert len(data["areas"]) == 2
        assert data["areas"][0]["name"] == "Area 1"

    @patch("crud.get_admin_panel_data", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_admin_data_empty_areas(self, mock_auth, mock_crud, client):
        """Admin panel data with no areas returns empty list."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = {
            "areas": [],
            "countries": [],
            "regions": [],
        }

        response = client.get("/locations/admin/data", headers=ADMIN_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["areas"] == []

    def test_admin_data_no_auth_returns_401(self, client):
        """No auth -> 401."""
        response = client.get("/locations/admin/data")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_admin_data_non_admin_returns_403(self, mock_get, client):
        """Non-admin without locations:read permission -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.get(
            "/locations/admin/data",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403

    @patch("crud.get_admin_panel_data", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_admin_data_areas_fields(self, mock_auth, mock_crud, client):
        """Verify area objects in admin data contain correct fields."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = {
            "areas": [
                {
                    "id": 1,
                    "name": "Area",
                    "description": "Desc",
                    "map_image_url": "https://example.com/map.png",
                    "sort_order": 5,
                }
            ],
            "countries": [],
            "regions": [],
        }

        response = client.get("/locations/admin/data", headers=ADMIN_HEADERS)
        assert response.status_code == 200
        area = response.json()["areas"][0]
        assert "id" in area
        assert "name" in area
        assert "description" in area
        assert "map_image_url" in area
        assert "sort_order" in area


# ===========================================================================
# Security Tests
# ===========================================================================

class TestHierarchyAndExtensionsSecurity:
    """Security tests for hierarchy and extended endpoints."""

    @patch("crud.get_hierarchy_tree", new_callable=AsyncMock, return_value=[])
    def test_hierarchy_no_crash_on_empty(self, mock_crud, client):
        """Hierarchy endpoint does not crash on empty data."""
        response = client.get("/locations/hierarchy/tree")
        assert response.status_code == 200

    def test_sql_injection_in_country_id_update(self, client):
        """SQL injection in country_id path param -> 401/404/422."""
        response = client.put(
            "/locations/countries/1;DROP TABLE Countries;--/update",
            json={"name": "Hack"},
        )
        assert response.status_code in (401, 404, 422)

    def test_sql_injection_in_location_id_update(self, client):
        """SQL injection in location_id path param -> 401/404/422."""
        response = client.put(
            "/locations/1 OR 1=1/update",
            json={"marker_type": "safe"},
        )
        assert response.status_code in (401, 404, 422)
