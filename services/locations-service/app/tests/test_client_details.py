"""
Tests for GET /locations/{location_id}/client/details endpoint (FEAT-091, FEAT-152).

Verifies:
- Neighbor objects use `id` field (not `neighbor_id`)
- Response includes `marker_type` field
- NeighborClient and LocationClientDetails schema validation
- 404 for non-existent location
- FEAT-152: breadcrumb fields (country_id / country_name / region_name /
  district_name) — schema, endpoint response, crud name-resolution logic,
  and backward compatibility with payloads lacking the new keys.
"""

from types import SimpleNamespace
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from schemas import NeighborClient, LocationClientDetails

BREADCRUMB_KEYS = {"country_id", "country_name", "region_name", "district_name"}


# ---------------------------------------------------------------------------
# Sample data builders
# ---------------------------------------------------------------------------

def _make_client_details(
    location_id=72,
    marker_type="safe",
    neighbors=None,
    district_id=1,
    region_id=1,
    breadcrumb=None,
):
    """Build a dict matching the shape returned by crud.get_client_location_details.

    By default the dict does NOT contain the FEAT-152 breadcrumb keys —
    this mirrors the pre-FEAT-152 payload and keeps backward-compat coverage.
    Pass ``breadcrumb`` (dict) to include them explicitly.
    """
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
    data = {
        "id": location_id,
        "name": "Деревня",
        "type": "location",
        "parent_id": None,
        "description": "Тихая деревня на окраине",
        "image_url": "https://example.com/loc.png",
        "recommended_level": 5,
        "quick_travel_marker": False,
        "marker_type": marker_type,
        "district_id": district_id,
        "region_id": region_id,
        "is_favorited": False,
        "neighbors": neighbors,
        "players": [],
        "npcs": [],
        "posts": [],
        "loot": [],
    }
    if breadcrumb is not None:
        data.update(breadcrumb)
    return data


def _full_breadcrumb():
    """Breadcrumb fields for a location with a full district→region→country chain."""
    return {
        "country_id": 1,
        "country_name": "Фолгард",
        "region_name": "Северные земли",
        "district_name": "Чащоба",
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


class TestBreadcrumbSchema:
    """FEAT-152: LocationClientDetails breadcrumb fields (schema level)."""

    def test_breadcrumb_fields_exist(self):
        """Schema defines all four breadcrumb fields."""
        for field in BREADCRUMB_KEYS:
            assert field in LocationClientDetails.__fields__, f"Missing field: {field}"

    def test_breadcrumb_fields_optional_default_none(self):
        """All breadcrumb fields are optional and default to None."""
        for field in BREADCRUMB_KEYS:
            assert LocationClientDetails.__fields__[field].default is None, (
                f"Field {field} must default to None"
            )

    def test_validates_payload_without_breadcrumb_keys(self):
        """Backward compat: payload without the new keys validates, fields = None."""
        data = _make_client_details()
        assert BREADCRUMB_KEYS.isdisjoint(data.keys())  # sanity: old-style payload
        details = LocationClientDetails(**data)
        assert details.country_id is None
        assert details.country_name is None
        assert details.region_name is None
        assert details.district_name is None

    def test_validates_with_full_breadcrumb(self):
        """Payload with full breadcrumb chain validates with correct types/values."""
        data = _make_client_details(district_id=5, region_id=2, breadcrumb=_full_breadcrumb())
        details = LocationClientDetails(**data)
        assert details.country_id == 1
        assert details.country_name == "Фолгард"
        assert details.region_name == "Северные земли"
        assert details.district_name == "Чащоба"

    def test_validates_with_null_breadcrumb_values(self):
        """Payload with explicit None breadcrumb values validates."""
        data = _make_client_details(
            district_id=None,
            region_id=None,
            breadcrumb={
                "country_id": None,
                "country_name": None,
                "region_name": None,
                "district_name": None,
            },
        )
        details = LocationClientDetails(**data)
        assert details.country_id is None
        assert details.country_name is None
        assert details.region_name is None
        assert details.district_name is None

    def test_breadcrumb_does_not_break_existing_fields(self):
        """Adding breadcrumb data leaves all pre-existing fields intact."""
        data = _make_client_details(breadcrumb=_full_breadcrumb())
        details = LocationClientDetails(**data)
        assert details.id == 72
        assert details.name == "Деревня"
        assert details.marker_type == "safe"
        assert details.district_id == 1
        assert details.region_id == 1
        assert len(details.neighbors) == 2


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
            "recommended_level", "quick_travel_marker", "no_quick_move", "marker_type",
            "district_id", "region_id", "is_favorited",
            # FEAT-152: breadcrumb fields
            "country_id", "country_name", "region_name", "district_name",
            "neighbors", "players", "npcs", "posts", "loot", "gathering_nodes",
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


class TestBreadcrumbEndpoint:
    """FEAT-152: breadcrumb fields in GET /locations/{id}/client/details response."""

    @patch("main.get_optional_user", return_value=None)
    @patch("crud.get_client_location_details", new_callable=AsyncMock)
    def test_full_hierarchy_chain(self, mock_crud, mock_user, client):
        """Location with district→region→country chain returns all four names."""
        mock_crud.return_value = _make_client_details(
            district_id=5, region_id=2, breadcrumb=_full_breadcrumb()
        )

        response = client.get("/locations/72/client/details")
        assert response.status_code == 200

        data = response.json()
        assert data["country_id"] == 1
        assert data["country_name"] == "Фолгард"
        assert data["region_name"] == "Северные земли"
        assert data["district_name"] == "Чащоба"

    @patch("main.get_optional_user", return_value=None)
    @patch("crud.get_client_location_details", new_callable=AsyncMock)
    def test_standalone_location(self, mock_crud, mock_user, client):
        """Standalone location (district_id NULL, region_id set): no district_name."""
        mock_crud.return_value = _make_client_details(
            district_id=None,
            region_id=2,
            breadcrumb={
                "country_id": 1,
                "country_name": "Фолгард",
                "region_name": "Северные земли",
                "district_name": None,
            },
        )

        response = client.get("/locations/72/client/details")
        assert response.status_code == 200

        data = response.json()
        assert data["district_id"] is None
        assert data["district_name"] is None
        assert data["region_name"] == "Северные земли"
        assert data["country_id"] == 1
        assert data["country_name"] == "Фолгард"

    @patch("main.get_optional_user", return_value=None)
    @patch("crud.get_client_location_details", new_callable=AsyncMock)
    def test_no_hierarchy(self, mock_crud, mock_user, client):
        """Location with neither district nor region: all four fields null."""
        mock_crud.return_value = _make_client_details(district_id=None, region_id=None)

        response = client.get("/locations/72/client/details")
        assert response.status_code == 200

        data = response.json()
        for key in BREADCRUMB_KEYS:
            assert key in data, f"Response must include '{key}' key"
            assert data[key] is None

    @patch("main.get_optional_user", return_value=None)
    @patch("crud.get_client_location_details", new_callable=AsyncMock)
    def test_backward_compat_existing_fields_unchanged(self, mock_crud, mock_user, client):
        """Breadcrumb extension is additive: existing fields keep their values."""
        mock_crud.return_value = _make_client_details(breadcrumb=_full_breadcrumb())

        response = client.get("/locations/72/client/details")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == 72
        assert data["name"] == "Деревня"
        assert data["type"] == "location"
        assert data["marker_type"] == "safe"
        assert data["district_id"] == 1
        assert data["region_id"] == 1
        assert data["is_favorited"] is False
        assert len(data["neighbors"]) == 2
        assert data["neighbors"][0]["id"] == 73


# ===========================================================================
# CRUD unit tests — breadcrumb name resolution (FEAT-152, section 3.1)
# ===========================================================================

def _make_loc(district_id=None, region_id=None):
    """Location ORM-row stand-in with the attributes read by the crud function."""
    return SimpleNamespace(
        id=72,
        name="Тёмный лес",
        type="location",
        parent_id=None,
        description="Мрачный лес",
        image_url=None,
        recommended_level=25,
        quick_travel_marker=False,
        no_quick_move=False,
        marker_type="dangerous",
        district_id=district_id,
        region_id=region_id,
    )


def _make_session(loc, hierarchy_rows):
    """AsyncSession mock whose execute() yields, in order:
    location query, then one result per hierarchy row, then empty neighbors.

    side_effect exhaustion guards against unexpected extra queries.
    """
    loc_result = MagicMock()
    loc_result.scalars.return_value.first.return_value = loc

    results = [loc_result]
    for row in hierarchy_rows:
        r = MagicMock()
        r.first.return_value = row
        results.append(r)

    neighbors_result = MagicMock()
    neighbors_result.scalars.return_value.all.return_value = []
    results.append(neighbors_result)

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=results)
    return session


@patch("crud.fetch_gathering_nodes_with_active_sessions", new_callable=AsyncMock, return_value=[])
@patch("crud.lazy_restore_depleted_nodes", new_callable=AsyncMock)
@patch("crud.get_location_loot", new_callable=AsyncMock, return_value=[])
@patch("crud.gates_for_posts", new_callable=AsyncMock, return_value={})
@patch("crud.get_likes_for_posts", new_callable=AsyncMock, return_value={})
@patch("crud.get_posts_by_location", new_callable=AsyncMock, return_value=[])
@patch("crud.get_npcs_in_location", new_callable=AsyncMock, return_value=[])
@patch("crud.get_players_in_location", new_callable=AsyncMock, return_value=[])
class TestBreadcrumbResolution:
    """Unit tests for the district→region→country resolution in
    crud.get_client_location_details (inter-service and post/loot/gathering
    helpers are mocked; only the hierarchy queries are exercised)."""

    @pytest.mark.asyncio
    async def test_full_chain_district_region_country(self, *mocks):
        """(a) district_id set: resolves district → region → country names."""
        import crud

        loc = _make_loc(district_id=5, region_id=2)
        session = _make_session(loc, [
            SimpleNamespace(name="Чащоба", region_id=2),      # District row
            SimpleNamespace(name="Северные земли", country_id=1),  # Region row
            SimpleNamespace(id=1, name="Фолгард"),            # Country row
        ])

        result = await crud.get_client_location_details(session, 72)

        assert result["district_name"] == "Чащоба"
        assert result["region_name"] == "Северные земли"
        assert result["country_id"] == 1
        assert result["country_name"] == "Фолгард"
        # existing fields unchanged
        assert result["district_id"] == 5
        assert result["region_id"] == 2

    @pytest.mark.asyncio
    async def test_standalone_location_region_country_only(self, *mocks):
        """(b) district_id NULL, region_id set: Region → Country, district_name None."""
        import crud

        loc = _make_loc(district_id=None, region_id=2)
        session = _make_session(loc, [
            SimpleNamespace(name="Северные земли", country_id=1),  # Region row
            SimpleNamespace(id=1, name="Фолгард"),                 # Country row
        ])

        result = await crud.get_client_location_details(session, 72)

        assert result["district_name"] is None
        assert result["region_name"] == "Северные земли"
        assert result["country_id"] == 1
        assert result["country_name"] == "Фолгард"

    @pytest.mark.asyncio
    async def test_no_hierarchy_all_none(self, *mocks):
        """(c) neither district_id nor region_id: all four fields None,
        no hierarchy queries issued."""
        import crud

        loc = _make_loc(district_id=None, region_id=None)
        session = _make_session(loc, [])

        result = await crud.get_client_location_details(session, 72)

        assert result["country_id"] is None
        assert result["country_name"] is None
        assert result["region_name"] is None
        assert result["district_name"] is None
        # only location + neighbors queries — no district/region/country selects
        assert session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_missing_district_row_does_not_break(self, *mocks):
        """district_id points at a missing District row: endpoint data still
        builds, all breadcrumb fields None (no crash, no extra queries)."""
        import crud

        loc = _make_loc(district_id=999, region_id=None)
        session = _make_session(loc, [None])  # District query returns no row

        result = await crud.get_client_location_details(session, 72)

        assert result["district_name"] is None
        assert result["region_name"] is None
        assert result["country_id"] is None
        assert result["country_name"] is None
        assert result["id"] == 72

    @pytest.mark.asyncio
    async def test_missing_country_row_keeps_region_name(self, *mocks):
        """Region resolves but its country row is missing: region_name kept,
        country fields None (missing hierarchy rows must not break the endpoint)."""
        import crud

        loc = _make_loc(district_id=None, region_id=2)
        session = _make_session(loc, [
            SimpleNamespace(name="Северные земли", country_id=42),  # Region row
            None,                                                   # Country row missing
        ])

        result = await crud.get_client_location_details(session, 72)

        assert result["region_name"] == "Северные земли"
        assert result["country_id"] is None
        assert result["country_name"] is None
