"""
Tests for the standalone world map screen (/map) in locations-service.

Covers:
- (a) GET /locations/map/graph — admin-only, returns the graph payload
- (b) crud.get_world_graph — hidden countries excluded with everything under them
- (c) crud.get_world_graph — directed rows collapsed into one edge per pair
- (d) crud.get_world_graph — one-way links preserved, self-loops dropped
- (e) crud.get_world_graph — region resolved through the district when needed
- (f) PATCH /locations/neighbors/{from}/{to}/cost — success, 404, auth, validation
- (g) crud.update_neighbor_cost — updates both rows and preserves path_data
"""

from unittest.mock import patch, MagicMock, AsyncMock

import pytest

import crud


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
MODERATOR_USER_RESPONSE = {
    "id": 3,
    "username": "moderator",
    "role": "moderator",
    "permissions": ["locations:read", "locations:update", "locations:delete"],
}


def _obj(**fields):
    """Lightweight stand-in for an ORM row."""
    item = MagicMock()
    for key, value in fields.items():
        setattr(item, key, value)
    return item


def _session_returning(*batches):
    """
    AsyncSession mock whose execute() yields the given batches in order.

    get_world_graph queries areas, countries, regions, districts, locations and
    neighbours in that fixed order.
    """
    session = MagicMock()

    def _make_result(rows):
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = rows
        result.scalars.return_value = scalars
        return result

    session.execute = AsyncMock(side_effect=[_make_result(rows) for rows in batches])
    return session


def _area(area_id=1, name="Area", sort_order=0):
    return _obj(id=area_id, name=name, sort_order=sort_order)


def _country(country_id=1, name="Country", area_id=1, is_hidden=False):
    return _obj(id=country_id, name=name, area_id=area_id, is_hidden=is_hidden)


def _region(region_id=1, name="Region", country_id=1):
    return _obj(id=region_id, name=name, country_id=country_id)


def _district(district_id=1, name="District", region_id=1):
    return _obj(id=district_id, name=name, region_id=region_id)


def _location(loc_id=1, name="Loc", district_id=None, region_id=1,
              marker_type="safe", recommended_level=1,
              no_quick_move=False, quick_travel_marker=False):
    return _obj(
        id=loc_id, name=name, district_id=district_id, region_id=region_id,
        marker_type=marker_type, recommended_level=recommended_level,
        no_quick_move=no_quick_move, quick_travel_marker=quick_travel_marker,
    )


def _neighbor(location_id, neighbor_id, energy_cost=1, is_auto_arrow=False, path_data=None):
    return _obj(
        location_id=location_id, neighbor_id=neighbor_id,
        energy_cost=energy_cost, is_auto_arrow=is_auto_arrow, path_data=path_data,
    )


# ===========================================================================
# (a) GET /locations/map/graph
# ===========================================================================
class TestWorldGraphRoute:

    @patch("crud.get_world_graph", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_graph_returns_payload_for_admin(self, mock_auth, mock_graph, client):
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        payload = {
            "areas": [], "countries": [], "regions": [], "districts": [],
            "locations": [], "edges": [],
            "stats": {"locations": 0, "edges": 0, "isolated": 0,
                      "one_way_edges": 0, "duplicate_rows": 0},
        }
        mock_graph.return_value = payload

        response = client.get("/locations/map/graph", headers=ADMIN_HEADERS)

        assert response.status_code == 200
        assert response.json() == payload

    def test_graph_requires_auth(self, client):
        """The payload exposes the whole world, so anonymous access is refused."""
        assert client.get("/locations/map/graph").status_code == 401

    @patch("auth_http.requests.get")
    def test_graph_rejects_regular_user(self, mock_auth, client):
        mock_auth.return_value = _mock_response(200, REGULAR_USER_RESPONSE)

        response = client.get(
            "/locations/map/graph",
            headers={"Authorization": "Bearer user-token"},
        )

        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_graph_rejects_moderator(self, mock_auth, client):
        """Admin-only: moderators and editors are deliberately excluded."""
        mock_auth.return_value = _mock_response(200, MODERATOR_USER_RESPONSE)

        response = client.get(
            "/locations/map/graph",
            headers={"Authorization": "Bearer moderator-token"},
        )

        assert response.status_code == 403

    @patch("crud.get_world_graph", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_graph_returns_nodes_and_edges(self, mock_auth, mock_graph, client):
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_graph.return_value = {
            "areas": [{"id": 1, "name": "A", "sort_order": 0}],
            "countries": [{"id": 1, "name": "C", "area_id": 1}],
            "regions": [{"id": 1, "name": "R", "country_id": 1}],
            "districts": [],
            "locations": [{
                "id": 1, "name": "L", "region_id": 1, "country_id": 1,
                "district_id": None, "marker_type": "safe", "recommended_level": 1,
                "no_quick_move": False, "quick_travel_marker": False,
            }],
            "edges": [{"a": 1, "b": 2, "cost_ab": 3, "cost_ba": 3, "auto": False}],
            "stats": {"locations": 1, "edges": 1, "isolated": 0,
                      "one_way_edges": 0, "duplicate_rows": 0},
        }

        data = client.get("/locations/map/graph", headers=ADMIN_HEADERS).json()

        assert data["locations"][0]["name"] == "L"
        assert data["edges"][0]["cost_ab"] == 3


# ===========================================================================
# (b)-(e) crud.get_world_graph
# ===========================================================================
class TestGetWorldGraph:

    @pytest.mark.asyncio
    async def test_hidden_country_excluded_with_its_content(self):
        """A hidden country must not leak its regions, locations or edges."""
        session = _session_returning(
            [_area()],
            # get_world_graph itself filters is_hidden in SQL; the visible set
            # is what comes back, so the hidden country is simply absent.
            [_country(country_id=1, name="Visible", is_hidden=False)],
            [_region(region_id=1, country_id=1), _region(region_id=99, country_id=2)],
            [_district(district_id=1, region_id=1), _district(district_id=99, region_id=99)],
            [_location(loc_id=1, district_id=1, region_id=None),
             _location(loc_id=90, district_id=99, region_id=None)],
            [_neighbor(1, 90), _neighbor(90, 1)],
        )

        graph = await crud.get_world_graph(session)

        location_ids = {loc["id"] for loc in graph["locations"]}
        assert location_ids == {1}
        assert graph["regions"] == [{"id": 1, "name": "Region", "country_id": 1}]
        # The edge touched a hidden location, so it must be dropped entirely.
        assert graph["edges"] == []

    @pytest.mark.asyncio
    async def test_bidirectional_rows_collapse_to_one_edge(self):
        session = _session_returning(
            [_area()], [_country()], [_region()], [],
            [_location(loc_id=1, region_id=1), _location(loc_id=2, region_id=1)],
            [_neighbor(1, 2, energy_cost=5), _neighbor(2, 1, energy_cost=5)],
        )

        graph = await crud.get_world_graph(session)

        assert len(graph["edges"]) == 1
        edge = graph["edges"][0]
        assert (edge["a"], edge["b"]) == (1, 2)
        assert edge["cost_ab"] == 5
        assert edge["cost_ba"] == 5
        assert graph["stats"]["one_way_edges"] == 0

    @pytest.mark.asyncio
    async def test_one_way_link_is_preserved(self):
        """Only the forward row exists — the reverse cost stays None."""
        session = _session_returning(
            [_area()], [_country()], [_region()], [],
            [_location(loc_id=1, region_id=1), _location(loc_id=2, region_id=1)],
            [_neighbor(1, 2, energy_cost=7)],
        )

        graph = await crud.get_world_graph(session)

        edge = graph["edges"][0]
        assert edge["cost_ab"] == 7
        assert edge["cost_ba"] is None
        assert graph["stats"]["one_way_edges"] == 1

    @pytest.mark.asyncio
    async def test_self_loop_is_dropped(self):
        session = _session_returning(
            [_area()], [_country()], [_region()], [],
            [_location(loc_id=1, region_id=1)],
            [_neighbor(1, 1, energy_cost=2)],
        )

        graph = await crud.get_world_graph(session)

        assert graph["edges"] == []
        assert graph["stats"]["isolated"] == 1

    @pytest.mark.asyncio
    async def test_duplicate_rows_counted_and_cheapest_kept(self):
        """The table has no unique index, so duplicates are possible."""
        session = _session_returning(
            [_area()], [_country()], [_region()], [],
            [_location(loc_id=1, region_id=1), _location(loc_id=2, region_id=1)],
            [_neighbor(1, 2, energy_cost=9), _neighbor(1, 2, energy_cost=4)],
        )

        graph = await crud.get_world_graph(session)

        assert graph["edges"][0]["cost_ab"] == 4
        assert graph["stats"]["duplicate_rows"] == 1

    @pytest.mark.asyncio
    async def test_region_resolved_through_district(self):
        """A location hanging off a district inherits that district's region."""
        session = _session_returning(
            [_area()],
            [_country(country_id=3, area_id=1)],
            [_region(region_id=8, country_id=3)],
            [_district(district_id=4, region_id=8)],
            [_location(loc_id=1, district_id=4, region_id=None)],
            [],
        )

        graph = await crud.get_world_graph(session)

        location = graph["locations"][0]
        assert location["region_id"] == 8
        assert location["country_id"] == 3
        assert location["district_id"] == 4

    @pytest.mark.asyncio
    async def test_auto_arrow_flag_propagates(self):
        session = _session_returning(
            [_area()], [_country()], [_region()], [],
            [_location(loc_id=1, region_id=1), _location(loc_id=2, region_id=1)],
            [_neighbor(1, 2, is_auto_arrow=True), _neighbor(2, 1, is_auto_arrow=False)],
        )

        graph = await crud.get_world_graph(session)

        assert graph["edges"][0]["auto"] is True

    @pytest.mark.asyncio
    async def test_isolated_locations_counted(self):
        session = _session_returning(
            [_area()], [_country()], [_region()], [],
            [_location(loc_id=1, region_id=1), _location(loc_id=2, region_id=1),
             _location(loc_id=3, region_id=1)],
            [_neighbor(1, 2), _neighbor(2, 1)],
        )

        graph = await crud.get_world_graph(session)

        assert graph["stats"]["locations"] == 3
        assert graph["stats"]["isolated"] == 1


# ===========================================================================
# (f) PATCH /locations/neighbors/{from}/{to}/cost
# ===========================================================================
class TestUpdateNeighborCostRoute:

    @patch("crud.update_neighbor_cost", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_cost_update_success(self, mock_auth, mock_update, client):
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_update.return_value = {
            "from_id": 1, "to_id": 2, "energy_cost": 12,
            "path_data": [{"x": 10.0, "y": 20.0}],
        }

        response = client.patch(
            "/locations/neighbors/1/2/cost",
            json={"energy_cost": 12},
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["energy_cost"] == 12
        # The drawn path must survive a cost-only edit.
        assert data["path_data"] == [{"x": 10.0, "y": 20.0}]

    @patch("crud.update_neighbor_cost", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_cost_update_missing_link_returns_404(self, mock_auth, mock_update, client):
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_update.return_value = None

        response = client.patch(
            "/locations/neighbors/1/2/cost",
            json={"energy_cost": 3},
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 404

    @patch("auth_http.requests.get")
    def test_cost_update_requires_permission(self, mock_auth, client):
        mock_auth.return_value = _mock_response(200, REGULAR_USER_RESPONSE)

        response = client.patch(
            "/locations/neighbors/1/2/cost",
            json={"energy_cost": 3},
            headers={"Authorization": "Bearer user-token"},
        )

        assert response.status_code == 403

    def test_cost_update_requires_auth(self, client):
        response = client.patch("/locations/neighbors/1/2/cost", json={"energy_cost": 3})
        assert response.status_code == 401

    @pytest.mark.parametrize("bad_cost", [-1, -50, 1001])
    @patch("auth_http.requests.get")
    def test_cost_update_rejects_out_of_range(self, mock_auth, client, bad_cost):
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.patch(
            "/locations/neighbors/1/2/cost",
            json={"energy_cost": bad_cost},
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 422

    @patch("crud.update_neighbor_cost", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_cost_zero_is_allowed(self, mock_auth, mock_update, client):
        """Free transitions are legitimate content, not an error."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_update.return_value = {
            "from_id": 1, "to_id": 2, "energy_cost": 0, "path_data": None,
        }

        response = client.patch(
            "/locations/neighbors/1/2/cost",
            json={"energy_cost": 0},
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 200
        assert response.json()["energy_cost"] == 0


# ===========================================================================
# (g) crud.update_neighbor_cost
# ===========================================================================
class TestUpdateNeighborCostCrud:

    @pytest.mark.asyncio
    async def test_updates_both_directions_and_keeps_path(self):
        path = [{"x": 5.0, "y": 6.0}]
        forward = _neighbor(1, 2, energy_cost=1, path_data=path)
        reverse = _neighbor(2, 1, energy_cost=1, path_data=path)

        session = MagicMock()
        forward_result = MagicMock()
        forward_result.scalars.return_value.first.return_value = forward
        reverse_result = MagicMock()
        reverse_result.scalars.return_value.first.return_value = reverse
        session.execute = AsyncMock(side_effect=[forward_result, reverse_result])
        session.commit = AsyncMock()

        result = await crud.update_neighbor_cost(session, 1, 2, 15)

        assert forward.energy_cost == 15
        assert reverse.energy_cost == 15
        # path_data must be untouched — this is the whole reason the endpoint exists.
        assert forward.path_data == path
        assert reverse.path_data == path
        assert result["energy_cost"] == 15
        assert result["path_data"] == path
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_link_absent(self):
        session = MagicMock()
        empty = MagicMock()
        empty.scalars.return_value.first.return_value = None
        session.execute = AsyncMock(side_effect=[empty, empty])
        session.commit = AsyncMock()

        result = await crud.update_neighbor_cost(session, 1, 2, 5)

        assert result is None
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_updates_one_way_link(self):
        """Only the forward row exists — it still gets the new cost."""
        forward = _neighbor(1, 2, energy_cost=1, path_data=None)

        session = MagicMock()
        forward_result = MagicMock()
        forward_result.scalars.return_value.first.return_value = forward
        empty = MagicMock()
        empty.scalars.return_value.first.return_value = None
        session.execute = AsyncMock(side_effect=[forward_result, empty])
        session.commit = AsyncMock()

        result = await crud.update_neighbor_cost(session, 1, 2, 8)

        assert forward.energy_cost == 8
        assert result["energy_cost"] == 8
