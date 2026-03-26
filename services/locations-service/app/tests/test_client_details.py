"""
Tests for GET /locations/{location_id}/client/details endpoint (FEAT-091).

Verifies:
- Neighbor objects use `id` field (not `neighbor_id`)
- Response includes `marker_type` field
- NeighborClient and LocationClientDetails schema validation
- 404 for non-existent location
"""

from unittest.mock import patch, AsyncMock

import pytest
from schemas import NeighborClient, LocationClientDetails


# ---------------------------------------------------------------------------
# Sample data builders
# ---------------------------------------------------------------------------

def _make_client_details(
    location_id=72,
    marker_type="safe",
    neighbors=None,
):
    """Build a dict matching the shape returned by crud.get_client_location_details."""
    if neighbors is None:
        neighbors = [
            {
                "id": 73,
                "name": "Лесная поляна",
                "recommended_level": 5,
                "image_url": "https://example.com/img.png",
                "energy_cost": 1,
            },
            {
                "id": 74,
                "name": "Горный перевал",
                "recommended_level": 10,
                "image_url": None,
                "energy_cost": 2,
            },
        ]
    return {
        "id": location_id,
        "name": "Деревня",
        "type": "location",
        "parent_id": None,
        "description": "Тихая деревня на окраине",
        "image_url": "https://example.com/loc.png",
        "recommended_level": 5,
        "quick_travel_marker": False,
        "marker_type": marker_type,
        "district_id": 1,
        "region_id": 1,
        "is_favorited": False,
        "neighbors": neighbors,
        "players": [],
        "npcs": [],
        "posts": [],
        "loot": [],
    }


# ===========================================================================
# Schema unit tests
# ===========================================================================

class TestNeighborClientSchema:
    """NeighborClient schema must use `id` field, not `neighbor_id`."""

    def test_has_id_field(self):
        """NeighborClient schema defines `id` field."""
        assert "id" in NeighborClient.__fields__

    def test_no_neighbor_id_field(self):
        """NeighborClient schema must NOT have `neighbor_id` field."""
        assert "neighbor_id" not in NeighborClient.__fields__

    def test_validates_with_id(self):
        """NeighborClient accepts data with `id` key."""
        neighbor = NeighborClient(
            id=73,
            name="Лесная поляна",
            recommended_level=5,
            image_url=None,
            energy_cost=1,
        )
        assert neighbor.id == 73
        assert neighbor.name == "Лесная поляна"

    def test_all_fields_present(self):
        """NeighborClient has all expected fields."""
        expected_fields = {"id", "name", "recommended_level", "image_url", "energy_cost"}
        assert set(NeighborClient.__fields__.keys()) == expected_fields


class TestLocationClientDetailsSchema:
    """LocationClientDetails schema must include marker_type."""

    def test_has_marker_type_field(self):
        """LocationClientDetails schema defines `marker_type` field."""
        assert "marker_type" in LocationClientDetails.__fields__

    def test_marker_type_optional_default_none(self):
        """marker_type is optional and defaults to None."""
        field = LocationClientDetails.__fields__["marker_type"]
        assert field.default is None

    def test_validates_full_response(self):
        """LocationClientDetails accepts a full response dict."""
        data = _make_client_details()
        details = LocationClientDetails(**data)
        assert details.id == 72
        assert details.marker_type == "safe"
        assert len(details.neighbors) == 2
        assert details.neighbors[0].id == 73

    def test_neighbors_use_id_not_neighbor_id(self):
        """Nested neighbors in LocationClientDetails use `id`."""
        data = _make_client_details()
        details = LocationClientDetails(**data)
        for neighbor in details.neighbors:
            assert hasattr(neighbor, "id")
            assert not hasattr(neighbor, "neighbor_id")


# ===========================================================================
# Endpoint integration tests
# ===========================================================================

class TestGetLocationClientDetails:
    """Tests for GET /locations/{location_id}/client/details."""

    @patch("main.get_optional_user", return_value=None)
    @patch("crud.get_client_location_details", new_callable=AsyncMock)
    def test_returns_neighbors_with_id_field(self, mock_crud, mock_user, client):
        """Neighbors in the response must have `id` field, not `neighbor_id`."""
        mock_crud.return_value = _make_client_details()

        response = client.get("/locations/72/client/details")
        assert response.status_code == 200

        data = response.json()
        neighbors = data["neighbors"]
        assert len(neighbors) == 2
        for neighbor in neighbors:
            assert "id" in neighbor, "Neighbor must have 'id' field"
            assert "neighbor_id" not in neighbor, "Neighbor must NOT have 'neighbor_id' field"

    @patch("main.get_optional_user", return_value=None)
    @patch("crud.get_client_location_details", new_callable=AsyncMock)
    def test_neighbor_id_values_are_correct(self, mock_crud, mock_user, client):
        """Neighbor `id` values match the expected location IDs."""
        mock_crud.return_value = _make_client_details()

        response = client.get("/locations/72/client/details")
        assert response.status_code == 200

        neighbors = response.json()["neighbors"]
        assert neighbors[0]["id"] == 73
        assert neighbors[1]["id"] == 74

    @patch("main.get_optional_user", return_value=None)
    @patch("crud.get_client_location_details", new_callable=AsyncMock)
    def test_returns_marker_type(self, mock_crud, mock_user, client):
        """Response must include `marker_type` field."""
        mock_crud.return_value = _make_client_details(marker_type="dangerous")

        response = client.get("/locations/72/client/details")
        assert response.status_code == 200

        data = response.json()
        assert "marker_type" in data, "Response must include 'marker_type' field"
        assert data["marker_type"] == "dangerous"

    @patch("main.get_optional_user", return_value=None)
    @patch("crud.get_client_location_details", new_callable=AsyncMock)
    def test_marker_type_null_when_not_set(self, mock_crud, mock_user, client):
        """marker_type can be null (None)."""
        mock_crud.return_value = _make_client_details(marker_type=None)

        response = client.get("/locations/72/client/details")
        assert response.status_code == 200

        data = response.json()
        assert "marker_type" in data
        assert data["marker_type"] is None

    @patch("main.get_optional_user", return_value=None)
    @patch("crud.get_client_location_details", new_callable=AsyncMock)
    def test_full_response_structure(self, mock_crud, mock_user, client):
        """Response includes all expected top-level fields."""
        mock_crud.return_value = _make_client_details()

        response = client.get("/locations/72/client/details")
        assert response.status_code == 200

        data = response.json()
        expected_keys = {
            "id", "name", "type", "parent_id", "description", "image_url",
            "recommended_level", "quick_travel_marker", "marker_type",
            "district_id", "region_id", "is_favorited",
            "neighbors", "players", "npcs", "posts", "loot",
        }
        assert set(data.keys()) == expected_keys

    @patch("main.get_optional_user", return_value=None)
    @patch("crud.get_client_location_details", new_callable=AsyncMock)
    def test_neighbor_fields_complete(self, mock_crud, mock_user, client):
        """Each neighbor has all expected fields."""
        mock_crud.return_value = _make_client_details()

        response = client.get("/locations/72/client/details")
        assert response.status_code == 200

        neighbor = response.json()["neighbors"][0]
        expected_neighbor_keys = {"id", "name", "recommended_level", "image_url", "energy_cost"}
        assert set(neighbor.keys()) == expected_neighbor_keys

    @patch("main.get_optional_user", return_value=None)
    @patch("crud.get_client_location_details", new_callable=AsyncMock)
    def test_empty_neighbors(self, mock_crud, mock_user, client):
        """Response works with empty neighbors list."""
        mock_crud.return_value = _make_client_details(neighbors=[])

        response = client.get("/locations/72/client/details")
        assert response.status_code == 200
        assert response.json()["neighbors"] == []

    @patch("main.get_optional_user", return_value=None)
    @patch("crud.get_client_location_details", new_callable=AsyncMock)
    def test_location_not_found(self, mock_crud, mock_user, client):
        """Returns 404 when location does not exist."""
        mock_crud.return_value = None

        response = client.get("/locations/99999/client/details")
        assert response.status_code == 404

    def test_invalid_location_id(self, client):
        """Returns 422 when location_id is not an integer (e.g. 'undefined')."""
        response = client.get("/locations/undefined/client/details")
        assert response.status_code == 422

    @patch("main.get_optional_user", return_value=None)
    @patch("crud.get_client_location_details", new_callable=AsyncMock)
    def test_marker_type_values(self, mock_crud, mock_user, client):
        """marker_type accepts known game values."""
        for marker in ("safe", "dangerous", "dungeon", "farm"):
            mock_crud.return_value = _make_client_details(marker_type=marker)
            response = client.get("/locations/72/client/details")
            assert response.status_code == 200
            assert response.json()["marker_type"] == marker
