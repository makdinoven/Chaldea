"""
Tests for FEAT-052 Clickable Zone Enhancements (locations-service).

Covers:
- Create clickable zone with stroke_color — verify it's persisted and returned
- Create clickable zone without stroke_color — verify default (null) works
- Update clickable zone stroke_color — verify update works
- Create clickable zone with target_type='area' — verify it works
- Create clickable zone with invalid target_type — verify validation error
- Get clickable zones — verify stroke_color is in response
- Country CRUD returns emblem_url field
- Create country with emblem_url — verify it's returned
- Area details include countries with emblem_url
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


def _make_zone(zone_id=1, parent_type="area", parent_id=1,
               target_type="country", target_id=10,
               zone_data=None, label=None, stroke_color=None):
    """Create a mock ClickableZone ORM object."""
    zone = MagicMock()
    zone.id = zone_id
    zone.parent_type = parent_type
    zone.parent_id = parent_id
    zone.target_type = target_type
    zone.target_id = target_id
    zone.zone_data = zone_data or [{"x": 0.1, "y": 0.2}, {"x": 0.3, "y": 0.4}]
    zone.label = label
    zone.stroke_color = stroke_color
    return zone


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


VALID_ZONE_PAYLOAD = {
    "parent_type": "area",
    "parent_id": 1,
    "target_type": "country",
    "target_id": 10,
    "zone_data": [{"x": 0.1, "y": 0.2}, {"x": 0.3, "y": 0.4}, {"x": 0.5, "y": 0.6}],
    "label": "Test Zone",
}


# ===========================================================================
# Stroke Color Tests
# ===========================================================================

class TestClickableZoneStrokeColor:
    """Tests for stroke_color field on clickable zones."""

    @patch("crud.create_clickable_zone", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_zone_with_stroke_color(self, mock_auth, mock_crud, client):
        """Create zone with stroke_color — verify it's persisted and returned."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_zone(
            zone_id=10, label="Colored Zone", stroke_color="#ff5500",
            zone_data=[{"x": 0.1, "y": 0.2}, {"x": 0.3, "y": 0.4}, {"x": 0.5, "y": 0.6}],
        )

        payload = {**VALID_ZONE_PAYLOAD, "stroke_color": "#ff5500"}
        response = client.post(
            "/locations/clickable-zones/create",
            json=payload,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stroke_color"] == "#ff5500"

    @patch("crud.create_clickable_zone", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_zone_without_stroke_color(self, mock_auth, mock_crud, client):
        """Create zone without stroke_color — verify default (null) works."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_zone(
            zone_id=11, label="No Color Zone", stroke_color=None,
            zone_data=[{"x": 0.1, "y": 0.2}, {"x": 0.3, "y": 0.4}, {"x": 0.5, "y": 0.6}],
        )

        response = client.post(
            "/locations/clickable-zones/create",
            json=VALID_ZONE_PAYLOAD,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stroke_color"] is None

    @patch("crud.update_clickable_zone", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_zone_stroke_color(self, mock_auth, mock_crud, client):
        """Update zone stroke_color — verify update works."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_zone(zone_id=1, stroke_color="#00ff00")

        response = client.put(
            "/locations/clickable-zones/1/update",
            json={"stroke_color": "#00ff00"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["stroke_color"] == "#00ff00"

    @patch("crud.get_clickable_zones_by_parent", new_callable=AsyncMock)
    def test_get_zones_returns_stroke_color(self, mock_crud, client):
        """Get clickable zones — verify stroke_color is in response."""
        zones = [
            _make_zone(zone_id=1, stroke_color="#ff5500"),
            _make_zone(zone_id=2, stroke_color=None),
        ]
        mock_crud.return_value = zones

        response = client.get("/locations/clickable-zones/area/1")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert "stroke_color" in data[0]
        assert data[0]["stroke_color"] == "#ff5500"
        assert "stroke_color" in data[1]
        assert data[1]["stroke_color"] is None


# ===========================================================================
# Target Type 'area' Tests
# ===========================================================================

class TestClickableZoneTargetTypeArea:
    """Tests for target_type='area' on clickable zones."""

    @patch("crud.create_clickable_zone", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_zone_with_target_type_area(self, mock_auth, mock_crud, client):
        """Create zone with target_type='area' — verify it works."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_zone(
            zone_id=20, target_type="area", target_id=5,
            zone_data=[{"x": 0.1, "y": 0.2}, {"x": 0.3, "y": 0.4}, {"x": 0.5, "y": 0.6}],
        )

        payload = {**VALID_ZONE_PAYLOAD, "target_type": "area", "target_id": 5}
        response = client.post(
            "/locations/clickable-zones/create",
            json=payload,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["target_type"] == "area"

    @patch("auth_http.requests.get")
    def test_create_zone_invalid_target_type_returns_422(self, mock_auth, client):
        """Create zone with invalid target_type — verify validation error."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        payload = {**VALID_ZONE_PAYLOAD, "target_type": "city"}
        response = client.post(
            "/locations/clickable-zones/create",
            json=payload,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422

    @patch("auth_http.requests.get")
    def test_update_zone_invalid_target_type_returns_422(self, mock_auth, client):
        """Update zone with invalid target_type — verify validation error."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        response = client.put(
            "/locations/clickable-zones/1/update",
            json={"target_type": "planet"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422

    @patch("auth_http.requests.get")
    def test_update_zone_target_type_area_accepted(self, mock_auth, client):
        """Update zone target_type to 'area' — verify schema accepts it."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        with patch("crud.update_clickable_zone", new_callable=AsyncMock) as mock_crud:
            mock_crud.return_value = _make_zone(zone_id=1, target_type="area")
            response = client.put(
                "/locations/clickable-zones/1/update",
                json={"target_type": "area", "target_id": 3},
                headers=ADMIN_HEADERS,
            )
            assert response.status_code == 200
            assert response.json()["target_type"] == "area"


# ===========================================================================
# Country emblem_url Tests
# ===========================================================================

class TestCountryEmblemUrl:
    """Tests for emblem_url field on countries."""

    @patch("crud.create_new_country", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_country_with_emblem_url(self, mock_auth, mock_crud, client):
        """Create country with emblem_url — verify it's returned."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_country(
            country_id=5, name="Fire Nation", description="A fiery land",
            emblem_url="https://s3.example.com/emblems/fire.webp",
        )

        payload = {
            "name": "Fire Nation",
            "description": "A fiery land",
            "emblem_url": "https://s3.example.com/emblems/fire.webp",
        }
        response = client.post(
            "/locations/countries/create",
            json=payload,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["emblem_url"] == "https://s3.example.com/emblems/fire.webp"

    @patch("crud.create_new_country", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_country_without_emblem_url(self, mock_auth, mock_crud, client):
        """Create country without emblem_url — verify null returned."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_country(
            country_id=6, name="Water Tribe", description="A watery place",
            emblem_url=None,
        )

        payload = {
            "name": "Water Tribe",
            "description": "A watery place",
        }
        response = client.post(
            "/locations/countries/create",
            json=payload,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["emblem_url"] is None

    @patch("crud.get_country_details", new_callable=AsyncMock)
    def test_get_country_details_returns_emblem_url(self, mock_crud, client):
        """Country details include emblem_url field."""
        mock_crud.return_value = {
            "id": 5,
            "name": "Fire Nation",
            "description": "A fiery land",
            "leader_id": None,
            "map_image_url": None,
            "emblem_url": "https://s3.example.com/emblems/fire.webp",
            "regions": [],
        }

        response = client.get("/locations/countries/5/details")
        assert response.status_code == 200
        data = response.json()
        assert "emblem_url" in data
        assert data["emblem_url"] == "https://s3.example.com/emblems/fire.webp"

    @patch("crud.get_area_details", new_callable=AsyncMock)
    def test_area_details_includes_countries_with_emblem_url(self, mock_crud, client):
        """Area details include countries with emblem_url field."""
        mock_crud.return_value = {
            "id": 1,
            "name": "Test Area",
            "description": "An area",
            "map_image_url": None,
            "sort_order": 0,
            "countries": [
                {
                    "id": 5,
                    "name": "Fire Nation",
                    "description": "A fiery land",
                    "leader_id": None,
                    "map_image_url": None,
                    "emblem_url": "https://s3.example.com/emblems/fire.webp",
                    "area_id": 1,
                    "x": None,
                    "y": None,
                },
                {
                    "id": 6,
                    "name": "Water Tribe",
                    "description": "Watery",
                    "leader_id": None,
                    "map_image_url": None,
                    "emblem_url": None,
                    "area_id": 1,
                    "x": None,
                    "y": None,
                },
            ],
        }

        response = client.get("/locations/areas/1/details")
        assert response.status_code == 200
        data = response.json()
        assert len(data["countries"]) == 2
        assert data["countries"][0]["emblem_url"] == "https://s3.example.com/emblems/fire.webp"
        assert data["countries"][1]["emblem_url"] is None

    @patch("crud.get_countries_list", new_callable=AsyncMock)
    def test_countries_list_returns_emblem_url(self, mock_crud, client):
        """Countries list includes emblem_url for each country."""
        mock_crud.return_value = [
            {
                "id": 5,
                "name": "Fire Nation",
                "emblem_url": "https://s3.example.com/emblems/fire.webp",
            },
            {
                "id": 6,
                "name": "Water Tribe",
                "emblem_url": None,
            },
        ]

        response = client.get("/locations/countries/list")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert "emblem_url" in data[0]
        assert data[0]["emblem_url"] == "https://s3.example.com/emblems/fire.webp"
        assert data[1]["emblem_url"] is None
