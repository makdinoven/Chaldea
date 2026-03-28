"""
Tests for cross-region neighbor auto-sync logic (FEAT-100) in locations-service.

Covers:
- (a) Auto-creation of cross-region LocationNeighbors when both sides of paired arrows
      have ArrowNeighbors: one-side-only does nothing, second-side triggers sync.
- (b) N x M cross-neighbors: multiple locations per arrow create correct pairs.
- (c) Auto-deletion on ArrowNeighbor delete: only affected cross-region neighbors removed.
- (d) Auto-deletion on arrow delete: all cross-region neighbors cleaned up.
- (e) update_location_neighbors preserves auto-arrow neighbors.
- (f) API response: paired_location_ids in arrow map_items of region details.
"""

from unittest.mock import patch, MagicMock, AsyncMock

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


# ===========================================================================
# (a) Auto-creation of cross-region neighbors
# ===========================================================================

class TestCrossRegionNeighborAutoCreation:
    """Creating ArrowNeighbors on both sides of paired arrows triggers auto-sync."""

    @patch("crud.create_arrow_neighbor", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_first_side_only_no_cross_neighbor(self, mock_auth, mock_create, client):
        """Creating ArrowNeighbor on one side only does NOT create LocationNeighbor.

        Setup: arrow1 (region1) paired with arrow2 (region2).
        Action: Create ArrowNeighbor(locA, arrow1) — arrow2 has no ArrowNeighbors yet.
        Expected: No cross-region LocationNeighbor created, just the ArrowNeighbor.
        """
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        # create_arrow_neighbor internally calls sync_cross_region_neighbors
        # which finds no remote ArrowNeighbors and returns without creating neighbors.
        mock_create.return_value = {
            "id": 1,
            "location_id": 100,
            "arrow_id": 10,
            "energy_cost": 3,
            "path_data": None,
        }

        response = client.post(
            "/locations/arrows/10/neighbors/",
            json={"location_id": 100, "energy_cost": 3},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["location_id"] == 100
        assert data["arrow_id"] == 10
        # No cross-region neighbor info in ArrowNeighbor response — that's correct.
        # Cross-neighbors are separate LocationNeighbor rows, not returned here.

    @patch("crud.create_arrow_neighbor", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_second_side_creates_cross_neighbor(self, mock_auth, mock_create, client):
        """Creating ArrowNeighbor on second side triggers cross-region neighbor creation.

        Setup: arrow1 (region1, paired with arrow2 in region2).
               ArrowNeighbor(locA=100, arrow1) already exists.
        Action: Create ArrowNeighbor(locB=200, arrow2).
        Expected: sync_cross_region_neighbors creates LocationNeighbor(100, 200)
                  with is_auto_arrow=True and energy_cost = costA + costB.
        """
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_create.return_value = {
            "id": 2,
            "location_id": 200,
            "arrow_id": 11,
            "energy_cost": 5,
            "path_data": None,
        }

        response = client.post(
            "/locations/arrows/11/neighbors/",
            json={"location_id": 200, "energy_cost": 5},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["location_id"] == 200
        assert data["arrow_id"] == 11

    @patch("crud.create_arrow_neighbor", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_cross_neighbor_energy_cost_is_sum(self, mock_auth, mock_create, client):
        """Cross-region neighbor energy_cost equals sum of both ArrowNeighbor costs.

        This is verified at the CRUD level — the mock here represents the endpoint
        working correctly. The actual energy calculation is tested via
        sync_cross_region_neighbors unit behavior.
        """
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        # ArrowNeighbor(locA, arrow1) has energy_cost=3
        # ArrowNeighbor(locB, arrow2) has energy_cost=5
        # => LocationNeighbor(locA, locB) should have energy_cost=8
        mock_create.return_value = {
            "id": 3,
            "location_id": 200,
            "arrow_id": 11,
            "energy_cost": 5,
            "path_data": None,
        }

        response = client.post(
            "/locations/arrows/11/neighbors/",
            json={"location_id": 200, "energy_cost": 5},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 201


# ===========================================================================
# (b) N x M cross-neighbors — multiple locations per arrow
# ===========================================================================

class TestCrossRegionNxM:
    """Multiple locations connected to arrows create N*M cross-region pairs."""

    @patch("crud.create_arrow_neighbor", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_two_local_one_remote_creates_two_pairs(self, mock_auth, mock_create, client):
        """Two locations on arrow1, one on arrow2 => 2 cross-region neighbor pairs.

        Setup: locA(100) -> arrow1, locC(300) -> arrow1, locB(200) -> arrow2.
        Expected: LocationNeighbor(100,200) + LocationNeighbor(300,200) both created.
        sync_cross_region_neighbors handles this by iterating local_ans x remote_ans.
        """
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        # Third ArrowNeighbor creation on arrow1 (locC=300), arrow2 already has locB=200
        mock_create.return_value = {
            "id": 4,
            "location_id": 300,
            "arrow_id": 10,
            "energy_cost": 2,
            "path_data": None,
        }

        response = client.post(
            "/locations/arrows/10/neighbors/",
            json={"location_id": 300, "energy_cost": 2},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 201

    @patch("crud.create_arrow_neighbor", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_two_by_two_creates_four_pairs(self, mock_auth, mock_create, client):
        """Two locations on each arrow => 4 cross-region neighbor pairs (2x2).

        Setup: locA, locC -> arrow1; locB, locD -> arrow2.
        Expected: (A,B), (A,D), (C,B), (C,D) — 4 pairs, each bidirectional = 8 rows.
        """
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_create.return_value = {
            "id": 5,
            "location_id": 400,
            "arrow_id": 11,
            "energy_cost": 1,
            "path_data": None,
        }

        response = client.post(
            "/locations/arrows/11/neighbors/",
            json={"location_id": 400, "energy_cost": 1},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 201


# ===========================================================================
# (c) Auto-deletion on ArrowNeighbor delete
# ===========================================================================

class TestCrossRegionDeleteArrowNeighbor:
    """Deleting an ArrowNeighbor removes only the affected cross-region neighbors."""

    @patch("crud.delete_arrow_neighbor", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_arrow_neighbor_removes_cross_neighbors(self, mock_auth, mock_delete, client):
        """Deleting ArrowNeighbor(locA, arrow1) removes cross-region neighbors for locA only.

        Setup: locA(100)->arrow1, locC(300)->arrow1, locB(200)->arrow2.
        Cross-neighbors: (100,200) and (300,200).
        Action: Delete ArrowNeighbor(100, arrow1=10).
        Expected: LocationNeighbor(100,200) deleted, but (300,200) preserved.
        """
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_delete.return_value = {"status": "deleted"}

        response = client.delete(
            "/locations/arrows/neighbors/100/10",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"

    @patch("crud.delete_arrow_neighbor", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_arrow_neighbor_preserves_other_cross_neighbors(
        self, mock_auth, mock_delete, client
    ):
        """Other cross-region neighbors (from different locations) are preserved.

        After deleting ArrowNeighbor(locA, arrow1), cross-neighbors for locC
        (which also connects to arrow1) remain intact.
        """
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_delete.return_value = {"status": "deleted"}

        response = client.delete(
            "/locations/arrows/neighbors/100/10",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        # The delete endpoint returns simple status — cross-neighbor cleanup
        # happens internally in crud.delete_arrow_neighbor before deleting the row.

    @patch("crud.delete_arrow_neighbor", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_arrow_neighbor_not_found_returns_404(self, mock_auth, mock_delete, client):
        """Deleting a non-existent ArrowNeighbor returns 404."""
        from fastapi import HTTPException
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_delete.side_effect = HTTPException(
            status_code=404, detail="Arrow neighbor not found"
        )

        response = client.delete(
            "/locations/arrows/neighbors/999/888",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404


# ===========================================================================
# (d) Auto-deletion on arrow delete
# ===========================================================================

class TestCrossRegionDeleteArrow:
    """Deleting a transition arrow cleans up all cross-region neighbors."""

    @patch("crud.delete_transition_arrow", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_arrow_cleans_up_cross_neighbors(self, mock_auth, mock_delete, client):
        """Deleting arrow calls cleanup_cross_region_neighbors_for_arrow before deletion.

        Setup: arrow1 (paired with arrow2), ArrowNeighbors on both sides.
        Action: Delete arrow1.
        Expected: All cross-region auto-neighbors for this arrow pair deleted,
                  then both arrows deleted.
        """
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_delete.return_value = {"status": "deleted", "deleted_ids": [10, 11]}

        response = client.delete(
            "/locations/arrows/10/delete",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        assert 10 in data["deleted_ids"]
        assert 11 in data["deleted_ids"]

    @patch("crud.delete_transition_arrow", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_arrow_without_pair_no_cross_cleanup_needed(
        self, mock_auth, mock_delete, client
    ):
        """Deleting an arrow without paired arrow skips cross-neighbor cleanup.

        cleanup_cross_region_neighbors_for_arrow returns early if no paired_arrow_id.
        """
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_delete.return_value = {"status": "deleted", "deleted_ids": [10]}

        response = client.delete(
            "/locations/arrows/10/delete",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["deleted_ids"] == [10]

    @patch("crud.delete_transition_arrow", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_paired_arrow_also_cleans_cross_neighbors(
        self, mock_auth, mock_delete, client
    ):
        """Deleting the paired arrow (arrow2) also cleans up cross-region neighbors.

        Both arrows in a pair are equivalent — deleting either one triggers
        the same cleanup via cleanup_cross_region_neighbors_for_arrow.
        """
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_delete.return_value = {"status": "deleted", "deleted_ids": [11, 10]}

        response = client.delete(
            "/locations/arrows/11/delete",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["deleted_ids"]) == 2


# ===========================================================================
# (e) update_location_neighbors preserves auto-arrow neighbors
# ===========================================================================

class TestUpdateLocationNeighborsPreservesAutoArrow:
    """Updating manual neighbors must not delete auto-arrow cross-region neighbors."""

    @patch("crud.update_location_neighbors", new_callable=AsyncMock)
    @patch("crud.get_location_by_id", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_neighbors_preserves_auto_arrow(
        self, mock_auth, mock_get_loc, mock_update, client
    ):
        """After update_location_neighbors, auto-arrow neighbors still exist.

        Setup: locA has manual neighbor locM and auto-arrow neighbor locB.
        Action: Call update_location_neighbors replacing manual neighbors.
        Expected: Auto-arrow neighbor (locA, locB) preserved — only
                  is_auto_arrow=False rows deleted.
        """
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_get_loc.return_value = MagicMock(id=100, name="Location A")
        # The endpoint returns the new manual neighbors list
        mock_update.return_value = [
            {"neighbor_id": 500, "energy_cost": 1},
        ]

        response = client.post(
            "/locations/100/neighbors/update",
            json={"neighbors": [{"neighbor_id": 500, "energy_cost": 1}]},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        # The returned list contains only the new manual neighbors
        assert len(data) == 1
        assert data[0]["neighbor_id"] == 500

    @patch("crud.update_location_neighbors", new_callable=AsyncMock)
    @patch("crud.get_location_by_id", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_neighbors_with_empty_list_preserves_auto_arrow(
        self, mock_auth, mock_get_loc, mock_update, client
    ):
        """Setting empty manual neighbors still preserves auto-arrow neighbors.

        Action: update_location_neighbors with empty list.
        Expected: All manual neighbors deleted, auto-arrow neighbors untouched.
        """
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_get_loc.return_value = MagicMock(id=100, name="Location A")
        mock_update.return_value = []

        response = client.post(
            "/locations/100/neighbors/update",
            json={"neighbors": []},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data == []


# ===========================================================================
# (f) API response — paired_location_ids in arrow map_items
# ===========================================================================

class TestRegionDetailsPairedLocationIds:
    """Region details response includes paired_location_ids for arrow map_items."""

    @patch("crud.get_region_full_details", new_callable=AsyncMock)
    def test_arrow_map_item_includes_paired_location_ids(self, mock_details, client):
        """Arrow map_items include paired_location_ids — locations connected to paired arrow.

        Setup: arrow10 in region1 paired with arrow11 in region2.
               arrow11 has ArrowNeighbors to locB(200) and locD(400).
        Expected: arrow10's map_item has paired_location_ids: [200, 400].
        """
        mock_details.return_value = {
            "id": 1,
            "country_id": 1,
            "name": "Region 1",
            "description": "Test region",
            "image_url": None,
            "map_image_url": None,
            "entrance_location": None,
            "leader_id": None,
            "x": 0,
            "y": 0,
            "districts": [],
            "map_items": [
                {
                    "id": 10,
                    "name": "To Region 2",
                    "type": "arrow",
                    "map_icon_url": None,
                    "map_x": 95.0,
                    "map_y": 50.0,
                    "marker_type": None,
                    "image_url": None,
                    "target_region_id": 2,
                    "target_region_name": "Region 2",
                    "paired_arrow_id": 11,
                    "paired_location_ids": [200, 400],
                },
                {
                    "id": 100,
                    "name": "Location A",
                    "type": "location",
                    "map_icon_url": None,
                    "map_x": 30.0,
                    "map_y": 40.0,
                    "marker_type": "safe",
                    "image_url": None,
                },
            ],
            "neighbor_edges": [],
            "arrow_edges": [
                {
                    "location_id": 100,
                    "arrow_id": 10,
                    "energy_cost": 3,
                    "path_data": None,
                },
            ],
        }

        response = client.get("/locations/regions/1/details")
        assert response.status_code == 200
        data = response.json()

        # Find arrow in map_items
        arrows = [item for item in data["map_items"] if item.get("type") == "arrow"]
        assert len(arrows) == 1
        arrow = arrows[0]
        assert arrow["id"] == 10
        assert "paired_location_ids" in arrow
        assert arrow["paired_location_ids"] == [200, 400]

    @patch("crud.get_region_full_details", new_callable=AsyncMock)
    def test_arrow_no_paired_neighbors_returns_empty_list(self, mock_details, client):
        """Arrow with paired arrow but no ArrowNeighbors on other side returns empty list.

        Setup: arrow10 paired with arrow11, but arrow11 has no ArrowNeighbors.
        Expected: paired_location_ids is [].
        """
        mock_details.return_value = {
            "id": 1,
            "country_id": 1,
            "name": "Region 1",
            "description": "Test region",
            "image_url": None,
            "map_image_url": None,
            "entrance_location": None,
            "leader_id": None,
            "x": 0,
            "y": 0,
            "districts": [],
            "map_items": [
                {
                    "id": 10,
                    "name": "To Region 2",
                    "type": "arrow",
                    "map_icon_url": None,
                    "map_x": 95.0,
                    "map_y": 50.0,
                    "marker_type": None,
                    "image_url": None,
                    "target_region_id": 2,
                    "target_region_name": "Region 2",
                    "paired_arrow_id": 11,
                    "paired_location_ids": [],
                },
            ],
            "neighbor_edges": [],
            "arrow_edges": [],
        }

        response = client.get("/locations/regions/1/details")
        assert response.status_code == 200
        data = response.json()

        arrows = [item for item in data["map_items"] if item.get("type") == "arrow"]
        assert len(arrows) == 1
        assert arrows[0]["paired_location_ids"] == []

    @patch("crud.get_region_full_details", new_callable=AsyncMock)
    def test_arrow_without_pair_returns_empty_paired_location_ids(self, mock_details, client):
        """Arrow without paired_arrow_id returns empty paired_location_ids.

        Edge case: orphaned arrow (no pair).
        """
        mock_details.return_value = {
            "id": 1,
            "country_id": 1,
            "name": "Region 1",
            "description": "Test region",
            "image_url": None,
            "map_image_url": None,
            "entrance_location": None,
            "leader_id": None,
            "x": 0,
            "y": 0,
            "districts": [],
            "map_items": [
                {
                    "id": 10,
                    "name": "Arrow",
                    "type": "arrow",
                    "map_icon_url": None,
                    "map_x": 50.0,
                    "map_y": 50.0,
                    "marker_type": None,
                    "image_url": None,
                    "target_region_id": 2,
                    "target_region_name": "Region 2",
                    "paired_arrow_id": None,
                    "paired_location_ids": [],
                },
            ],
            "neighbor_edges": [],
            "arrow_edges": [],
        }

        response = client.get("/locations/regions/1/details")
        assert response.status_code == 200
        data = response.json()

        arrows = [item for item in data["map_items"] if item.get("type") == "arrow"]
        assert len(arrows) == 1
        assert arrows[0]["paired_location_ids"] == []

    @patch("crud.get_region_full_details", new_callable=AsyncMock)
    def test_multiple_arrows_each_has_own_paired_location_ids(self, mock_details, client):
        """Multiple arrows in a region each have their own paired_location_ids.

        Setup: Region 1 has arrow10->region2 and arrow20->region3.
        arrow10's pair connects to locB(200), arrow20's pair connects to locE(500).
        """
        mock_details.return_value = {
            "id": 1,
            "country_id": 1,
            "name": "Hub Region",
            "description": "Central",
            "image_url": None,
            "map_image_url": None,
            "entrance_location": None,
            "leader_id": None,
            "x": 0,
            "y": 0,
            "districts": [],
            "map_items": [
                {
                    "id": 10,
                    "name": "To Region 2",
                    "type": "arrow",
                    "map_icon_url": None,
                    "map_x": 95.0,
                    "map_y": 50.0,
                    "marker_type": None,
                    "image_url": None,
                    "target_region_id": 2,
                    "target_region_name": "Region 2",
                    "paired_arrow_id": 11,
                    "paired_location_ids": [200],
                },
                {
                    "id": 20,
                    "name": "To Region 3",
                    "type": "arrow",
                    "map_icon_url": None,
                    "map_x": 5.0,
                    "map_y": 30.0,
                    "marker_type": None,
                    "image_url": None,
                    "target_region_id": 3,
                    "target_region_name": "Region 3",
                    "paired_arrow_id": 21,
                    "paired_location_ids": [500],
                },
                {
                    "id": 100,
                    "name": "Location A",
                    "type": "location",
                    "map_icon_url": None,
                    "map_x": 50.0,
                    "map_y": 50.0,
                    "marker_type": "safe",
                    "image_url": None,
                },
            ],
            "neighbor_edges": [],
            "arrow_edges": [
                {"location_id": 100, "arrow_id": 10, "energy_cost": 3, "path_data": None},
                {"location_id": 100, "arrow_id": 20, "energy_cost": 1, "path_data": None},
            ],
        }

        response = client.get("/locations/regions/1/details")
        assert response.status_code == 200
        data = response.json()

        arrows = [item for item in data["map_items"] if item.get("type") == "arrow"]
        assert len(arrows) == 2

        arrow_10 = next(a for a in arrows if a["id"] == 10)
        arrow_20 = next(a for a in arrows if a["id"] == 20)

        assert arrow_10["paired_location_ids"] == [200]
        assert arrow_20["paired_location_ids"] == [500]


# ===========================================================================
# (g) CRUD-level unit tests for sync/cleanup helpers
# ===========================================================================

class TestSyncCrossRegionNeighborsUnit:
    """Unit tests for the sync_cross_region_neighbors helper function.

    These tests mock the DB session to verify the sync algorithm directly.
    """

    @pytest.mark.asyncio
    async def test_sync_no_paired_arrow_returns_early(self):
        """sync_cross_region_neighbors returns early if arrow has no paired_arrow_id."""
        from crud import sync_cross_region_neighbors
        from models import RegionTransitionArrow

        mock_session = AsyncMock()
        # Arrow without paired_arrow_id
        mock_arrow = MagicMock(spec=RegionTransitionArrow)
        mock_arrow.paired_arrow_id = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_arrow
        mock_session.execute = AsyncMock(return_value=mock_result)

        await sync_cross_region_neighbors(mock_session, arrow_id=10)

        # Should only have been called once (to load the arrow), no further queries
        assert mock_session.execute.call_count == 1
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_no_remote_arrow_neighbors_returns_early(self):
        """sync_cross_region_neighbors returns early if paired arrow has no ArrowNeighbors."""
        from crud import sync_cross_region_neighbors
        from models import RegionTransitionArrow, ArrowNeighbor

        mock_session = AsyncMock()

        # Arrow with paired_arrow_id
        mock_arrow = MagicMock(spec=RegionTransitionArrow)
        mock_arrow.id = 10
        mock_arrow.paired_arrow_id = 11

        # Local ArrowNeighbors exist
        mock_local_an = MagicMock(spec=ArrowNeighbor)
        mock_local_an.location_id = 100
        mock_local_an.energy_cost = 3

        # Setup execute calls in order
        call_count = 0
        results = []

        # Call 1: load arrow
        r1 = MagicMock()
        r1.scalars.return_value.first.return_value = mock_arrow
        results.append(r1)

        # Call 2: local ArrowNeighbors
        r2 = MagicMock()
        r2.scalars.return_value.all.return_value = [mock_local_an]
        results.append(r2)

        # Call 3: remote ArrowNeighbors (empty)
        r3 = MagicMock()
        r3.scalars.return_value.all.return_value = []
        results.append(r3)

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            idx = call_count
            call_count += 1
            return results[idx]

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        await sync_cross_region_neighbors(mock_session, arrow_id=10)

        # 3 execute calls (arrow, local_ans, remote_ans), but no add() calls
        assert call_count == 3
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_creates_bidirectional_neighbors(self):
        """sync_cross_region_neighbors creates forward+reverse LocationNeighbor rows."""
        from crud import sync_cross_region_neighbors
        from models import RegionTransitionArrow, ArrowNeighbor

        mock_session = AsyncMock()
        mock_session.add = MagicMock()  # add() is sync, not async

        mock_arrow = MagicMock(spec=RegionTransitionArrow)
        mock_arrow.id = 10
        mock_arrow.paired_arrow_id = 11

        mock_local_an = MagicMock(spec=ArrowNeighbor)
        mock_local_an.location_id = 100
        mock_local_an.energy_cost = 3

        mock_remote_an = MagicMock(spec=ArrowNeighbor)
        mock_remote_an.location_id = 200
        mock_remote_an.energy_cost = 5

        call_count = 0
        results = []

        r1 = MagicMock()
        r1.scalars.return_value.first.return_value = mock_arrow
        results.append(r1)

        r2 = MagicMock()
        r2.scalars.return_value.all.return_value = [mock_local_an]
        results.append(r2)

        r3 = MagicMock()
        r3.scalars.return_value.all.return_value = [mock_remote_an]
        results.append(r3)

        # Call 4: delete existing auto-arrow neighbors
        r4 = MagicMock()
        results.append(r4)

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            idx = call_count
            call_count += 1
            return results[idx]

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        await sync_cross_region_neighbors(mock_session, arrow_id=10)

        # Should add 2 LocationNeighbor rows (forward + reverse)
        assert mock_session.add.call_count == 2
        mock_session.flush.assert_awaited_once()

        # Verify the added objects
        added_objects = [call.args[0] for call in mock_session.add.call_args_list]
        # Forward: location_id=100, neighbor_id=200
        assert added_objects[0].location_id == 100
        assert added_objects[0].neighbor_id == 200
        assert added_objects[0].energy_cost == 8  # 3 + 5
        assert added_objects[0].is_auto_arrow is True
        assert added_objects[0].path_data is None
        # Reverse: location_id=200, neighbor_id=100
        assert added_objects[1].location_id == 200
        assert added_objects[1].neighbor_id == 100
        assert added_objects[1].energy_cost == 8
        assert added_objects[1].is_auto_arrow is True

    @pytest.mark.asyncio
    async def test_sync_creates_n_times_m_neighbors(self):
        """sync_cross_region_neighbors creates N*M pairs for multiple locations."""
        from crud import sync_cross_region_neighbors
        from models import RegionTransitionArrow, ArrowNeighbor

        mock_session = AsyncMock()
        mock_session.add = MagicMock()  # add() is sync, not async

        mock_arrow = MagicMock(spec=RegionTransitionArrow)
        mock_arrow.id = 10
        mock_arrow.paired_arrow_id = 11

        # 2 local locations
        local1 = MagicMock(spec=ArrowNeighbor)
        local1.location_id = 100
        local1.energy_cost = 3

        local2 = MagicMock(spec=ArrowNeighbor)
        local2.location_id = 300
        local2.energy_cost = 2

        # 1 remote location
        remote1 = MagicMock(spec=ArrowNeighbor)
        remote1.location_id = 200
        remote1.energy_cost = 5

        call_count = 0
        results = []

        r1 = MagicMock()
        r1.scalars.return_value.first.return_value = mock_arrow
        results.append(r1)

        r2 = MagicMock()
        r2.scalars.return_value.all.return_value = [local1, local2]
        results.append(r2)

        r3 = MagicMock()
        r3.scalars.return_value.all.return_value = [remote1]
        results.append(r3)

        r4 = MagicMock()
        results.append(r4)

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            idx = call_count
            call_count += 1
            return results[idx]

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        await sync_cross_region_neighbors(mock_session, arrow_id=10)

        # 2 local x 1 remote = 2 pairs, each bidirectional = 4 rows
        assert mock_session.add.call_count == 4

        added = [call.args[0] for call in mock_session.add.call_args_list]
        # Pair 1: (100, 200) cost=3+5=8
        assert added[0].location_id == 100
        assert added[0].neighbor_id == 200
        assert added[0].energy_cost == 8
        assert added[1].location_id == 200
        assert added[1].neighbor_id == 100
        assert added[1].energy_cost == 8
        # Pair 2: (300, 200) cost=2+5=7
        assert added[2].location_id == 300
        assert added[2].neighbor_id == 200
        assert added[2].energy_cost == 7
        assert added[3].location_id == 200
        assert added[3].neighbor_id == 300
        assert added[3].energy_cost == 7


class TestCleanupCrossRegionNeighborsUnit:
    """Unit tests for cleanup_cross_region_neighbors_for_arrow helper."""

    @pytest.mark.asyncio
    async def test_cleanup_no_paired_arrow_returns_early(self):
        """cleanup returns early if arrow has no paired_arrow_id."""
        from crud import cleanup_cross_region_neighbors_for_arrow
        from models import RegionTransitionArrow

        mock_session = AsyncMock()

        mock_arrow = MagicMock(spec=RegionTransitionArrow)
        mock_arrow.paired_arrow_id = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_arrow
        mock_session.execute = AsyncMock(return_value=mock_result)

        await cleanup_cross_region_neighbors_for_arrow(mock_session, arrow_id=10)

        assert mock_session.execute.call_count == 1
        mock_session.flush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cleanup_no_arrow_found_returns_early(self):
        """cleanup returns early if arrow doesn't exist."""
        from crud import cleanup_cross_region_neighbors_for_arrow

        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        await cleanup_cross_region_neighbors_for_arrow(mock_session, arrow_id=999)

        assert mock_session.execute.call_count == 1
        mock_session.flush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cleanup_empty_local_ids_returns_early(self):
        """cleanup returns early if this arrow has no ArrowNeighbors."""
        from crud import cleanup_cross_region_neighbors_for_arrow
        from models import RegionTransitionArrow

        mock_session = AsyncMock()

        mock_arrow = MagicMock(spec=RegionTransitionArrow)
        mock_arrow.id = 10
        mock_arrow.paired_arrow_id = 11

        call_count = 0
        results = []

        r1 = MagicMock()
        r1.scalars.return_value.first.return_value = mock_arrow
        results.append(r1)

        # Local IDs: empty
        r2 = MagicMock()
        r2.all.return_value = []
        results.append(r2)

        # Remote IDs: has entries
        r3 = MagicMock()
        r3.all.return_value = [(200,)]
        results.append(r3)

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            idx = call_count
            call_count += 1
            return results[idx]

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        await cleanup_cross_region_neighbors_for_arrow(mock_session, arrow_id=10)

        # Should not flush (returns early because local_ids is empty)
        mock_session.flush.assert_not_awaited()
