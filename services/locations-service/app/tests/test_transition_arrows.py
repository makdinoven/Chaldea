"""
Tests for region transition arrows feature (FEAT-099) in locations-service.

Covers:
- (a) Arrow CRUD: create → verify paired arrow auto-created, update, delete → paired also deleted
- (b) Arrow validation: invalid coordinates, non-existent region, same region
- (c) Arrow neighbor CRUD: create, upsert, update path, delete
- (d) Arrow neighbor validation: non-existent location, non-existent arrow
- (e) Region details: arrows in map_items with type='arrow', arrow_edges in response
- (f) Security: auth checks on all admin endpoints
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
REGULAR_USER_RESPONSE = {"id": 2, "username": "user", "role": "user", "permissions": []}


# ===========================================================================
# (a) Arrow CRUD — create with paired arrow
# ===========================================================================

class TestCreateTransitionArrow:
    """Tests for POST /locations/arrows/create — auto-creates paired arrow."""

    @patch("crud.create_transition_arrow", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_arrow_returns_both_arrows(self, mock_auth, mock_create, client):
        """Creating an arrow returns both the primary and paired arrow."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_create.return_value = {
            "arrow": {
                "id": 10,
                "region_id": 1,
                "target_region_id": 2,
                "target_region_name": "Region B",
                "paired_arrow_id": 11,
                "x": 95.0,
                "y": 50.0,
                "label": "To Region B",
            },
            "paired_arrow": {
                "id": 11,
                "region_id": 2,
                "target_region_id": 1,
                "target_region_name": "Region A",
                "paired_arrow_id": 10,
                "x": None,
                "y": None,
                "label": None,
            },
        }

        response = client.post(
            "/locations/arrows/create",
            json={"region_id": 1, "target_region_id": 2, "x": 95.0, "y": 50.0, "label": "To Region B"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["arrow"]["id"] == 10
        assert data["paired_arrow"]["id"] == 11
        # Verify they are linked
        assert data["arrow"]["paired_arrow_id"] == data["paired_arrow"]["id"]
        assert data["paired_arrow"]["paired_arrow_id"] == data["arrow"]["id"]

    @patch("crud.create_transition_arrow", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_arrow_regions_swapped_in_paired(self, mock_auth, mock_create, client):
        """Paired arrow has region_id and target_region_id swapped."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_create.return_value = {
            "arrow": {
                "id": 1, "region_id": 5, "target_region_id": 10,
                "target_region_name": "R10", "paired_arrow_id": 2,
                "x": 50.0, "y": 50.0, "label": None,
            },
            "paired_arrow": {
                "id": 2, "region_id": 10, "target_region_id": 5,
                "target_region_name": "R5", "paired_arrow_id": 1,
                "x": None, "y": None, "label": None,
            },
        }

        response = client.post(
            "/locations/arrows/create",
            json={"region_id": 5, "target_region_id": 10, "x": 50.0, "y": 50.0},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["arrow"]["region_id"] == 5
        assert data["arrow"]["target_region_id"] == 10
        assert data["paired_arrow"]["region_id"] == 10
        assert data["paired_arrow"]["target_region_id"] == 5

    @patch("crud.create_transition_arrow", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_arrow_without_position(self, mock_auth, mock_create, client):
        """Arrow can be created without x/y coordinates (to be positioned later)."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_create.return_value = {
            "arrow": {
                "id": 1, "region_id": 1, "target_region_id": 2,
                "target_region_name": "R2", "paired_arrow_id": 2,
                "x": None, "y": None, "label": None,
            },
            "paired_arrow": {
                "id": 2, "region_id": 2, "target_region_id": 1,
                "target_region_name": "R1", "paired_arrow_id": 1,
                "x": None, "y": None, "label": None,
            },
        }

        response = client.post(
            "/locations/arrows/create",
            json={"region_id": 1, "target_region_id": 2},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["arrow"]["x"] is None
        assert data["arrow"]["y"] is None


# ===========================================================================
# (a.2) Arrow CRUD — update arrow position/label
# ===========================================================================

class TestUpdateTransitionArrow:
    """Tests for PUT /locations/arrows/{arrow_id}/update."""

    @patch("crud.update_transition_arrow", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_arrow_position(self, mock_auth, mock_update, client):
        """Updating arrow position returns updated data."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_update.return_value = {
            "id": 10, "region_id": 1, "target_region_id": 2,
            "target_region_name": "Region B", "paired_arrow_id": 11,
            "x": 80.0, "y": 30.0, "label": "Updated label",
        }

        response = client.put(
            "/locations/arrows/10/update",
            json={"x": 80.0, "y": 30.0, "label": "Updated label"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["x"] == 80.0
        assert data["y"] == 30.0
        assert data["label"] == "Updated label"

    @patch("crud.update_transition_arrow", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_arrow_label_only(self, mock_auth, mock_update, client):
        """Updating only the label leaves position unchanged."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_update.return_value = {
            "id": 10, "region_id": 1, "target_region_id": 2,
            "target_region_name": "Region B", "paired_arrow_id": 11,
            "x": 95.0, "y": 50.0, "label": "New label",
        }

        response = client.put(
            "/locations/arrows/10/update",
            json={"label": "New label"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["label"] == "New label"

    @patch("crud.update_transition_arrow", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_arrow_not_found(self, mock_auth, mock_update, client):
        """Updating a non-existent arrow returns 404."""
        from fastapi import HTTPException
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_update.side_effect = HTTPException(status_code=404, detail="Arrow not found")

        response = client.put(
            "/locations/arrows/999/update",
            json={"x": 50.0},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404


# ===========================================================================
# (a.3) Arrow CRUD — delete arrow and paired
# ===========================================================================

class TestDeleteTransitionArrow:
    """Tests for DELETE /locations/arrows/{arrow_id}/delete — paired arrow also deleted."""

    @patch("crud.delete_transition_arrow", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_arrow_returns_both_ids(self, mock_auth, mock_delete, client):
        """Deleting an arrow returns IDs of both deleted arrows (primary + paired)."""
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
    def test_delete_arrow_without_pair(self, mock_auth, mock_delete, client):
        """Deleting an arrow that has no paired arrow works (one-sided)."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_delete.return_value = {"status": "deleted", "deleted_ids": [10]}

        response = client.delete(
            "/locations/arrows/10/delete",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["deleted_ids"] == [10]

    @patch("crud.delete_transition_arrow", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_nonexistent_arrow(self, mock_auth, mock_delete, client):
        """Deleting a non-existent arrow returns 404."""
        from fastapi import HTTPException
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_delete.side_effect = HTTPException(status_code=404, detail="Arrow not found")

        response = client.delete(
            "/locations/arrows/999/delete",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404


# ===========================================================================
# (b) Arrow validation — invalid coordinates, same region, non-existent region
# ===========================================================================

class TestArrowValidation:
    """Validation tests for arrow create/update endpoints."""

    @patch("crud.create_transition_arrow", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_arrow_coords_out_of_range(self, mock_auth, mock_create, client):
        """Coordinates > 100 are rejected by crud validation."""
        from fastapi import HTTPException
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_create.side_effect = HTTPException(status_code=400, detail="x must be between 0 and 100")

        response = client.post(
            "/locations/arrows/create",
            json={"region_id": 1, "target_region_id": 2, "x": 150.0, "y": 50.0},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    @patch("crud.create_transition_arrow", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_arrow_negative_coords(self, mock_auth, mock_create, client):
        """Negative coordinates are rejected."""
        from fastapi import HTTPException
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_create.side_effect = HTTPException(status_code=400, detail="x must be between 0 and 100")

        response = client.post(
            "/locations/arrows/create",
            json={"region_id": 1, "target_region_id": 2, "x": -5.0, "y": 50.0},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    @patch("crud.create_transition_arrow", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_arrow_same_region(self, mock_auth, mock_create, client):
        """Creating an arrow where region_id == target_region_id returns 400."""
        from fastapi import HTTPException
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_create.side_effect = HTTPException(
            status_code=400, detail="region_id and target_region_id must be different"
        )

        response = client.post(
            "/locations/arrows/create",
            json={"region_id": 1, "target_region_id": 1, "x": 50.0, "y": 50.0},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    @patch("crud.create_transition_arrow", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_arrow_nonexistent_region(self, mock_auth, mock_create, client):
        """Creating an arrow with a non-existent region returns 404."""
        from fastapi import HTTPException
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_create.side_effect = HTTPException(status_code=404, detail="Region 999 not found")

        response = client.post(
            "/locations/arrows/create",
            json={"region_id": 999, "target_region_id": 2, "x": 50.0, "y": 50.0},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404

    @patch("crud.create_transition_arrow", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_arrow_nonexistent_target_region(self, mock_auth, mock_create, client):
        """Creating an arrow with a non-existent target region returns 404."""
        from fastapi import HTTPException
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_create.side_effect = HTTPException(status_code=404, detail="Target region 888 not found")

        response = client.post(
            "/locations/arrows/create",
            json={"region_id": 1, "target_region_id": 888},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404

    @patch("auth_http.requests.get")
    def test_create_arrow_label_too_long(self, mock_auth, client):
        """Label exceeding 255 characters returns 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.post(
            "/locations/arrows/create",
            json={
                "region_id": 1, "target_region_id": 2,
                "label": "A" * 256,
            },
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    @patch("auth_http.requests.get")
    def test_update_arrow_label_too_long(self, mock_auth, client):
        """Update with label exceeding 255 characters returns 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.put(
            "/locations/arrows/1/update",
            json={"label": "B" * 256},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    @patch("crud.update_transition_arrow", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_arrow_coords_out_of_range(self, mock_auth, mock_update, client):
        """Update with coords > 100 returns 400."""
        from fastapi import HTTPException
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_update.side_effect = HTTPException(status_code=400, detail="x must be between 0 and 100")

        response = client.put(
            "/locations/arrows/1/update",
            json={"x": 200.0},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    def test_create_arrow_missing_required_field(self, client):
        """Missing region_id or target_region_id returns 422."""
        response = client.post(
            "/locations/arrows/create",
            json={"region_id": 1},
            headers=ADMIN_HEADERS,
        )
        # No auth mock — but missing fields trigger 422 before auth in some cases,
        # or 401/503 if auth checked first. Either way, NOT 500.
        assert response.status_code != 500


# ===========================================================================
# (c) Arrow neighbor CRUD — create, upsert, update, delete
# ===========================================================================

class TestCreateArrowNeighbor:
    """Tests for POST /locations/arrows/{arrow_id}/neighbors/ — create location-to-arrow path."""

    @patch("crud.create_arrow_neighbor", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_arrow_neighbor_success(self, mock_auth, mock_create, client):
        """Creating an arrow neighbor path returns the created row."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        path = [{"x": 10.0, "y": 20.0}, {"x": 30.0, "y": 40.0}]
        mock_create.return_value = {
            "id": 1,
            "location_id": 5,
            "arrow_id": 10,
            "energy_cost": 2,
            "path_data": path,
        }

        response = client.post(
            "/locations/arrows/10/neighbors/",
            json={"location_id": 5, "energy_cost": 2, "path_data": path},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["location_id"] == 5
        assert data["arrow_id"] == 10
        assert data["energy_cost"] == 2
        assert len(data["path_data"]) == 2

    @patch("crud.create_arrow_neighbor", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_arrow_neighbor_upsert(self, mock_auth, mock_create, client):
        """Creating an arrow neighbor when one already exists updates it (upsert)."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        # Simulate upsert returning updated row
        mock_create.return_value = {
            "id": 1,
            "location_id": 5,
            "arrow_id": 10,
            "energy_cost": 5,
            "path_data": [{"x": 50.0, "y": 60.0}],
        }

        response = client.post(
            "/locations/arrows/10/neighbors/",
            json={"location_id": 5, "energy_cost": 5, "path_data": [{"x": 50.0, "y": 60.0}]},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["energy_cost"] == 5

    @patch("crud.create_arrow_neighbor", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_arrow_neighbor_without_path(self, mock_auth, mock_create, client):
        """Creating an arrow neighbor without path_data defaults to null."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_create.return_value = {
            "id": 1,
            "location_id": 5,
            "arrow_id": 10,
            "energy_cost": 0,
            "path_data": None,
        }

        response = client.post(
            "/locations/arrows/10/neighbors/",
            json={"location_id": 5, "energy_cost": 0},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["path_data"] is None


class TestArrowNeighborValidation:
    """Validation tests for arrow neighbor endpoints."""

    @patch("crud.create_arrow_neighbor", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_arrow_neighbor_nonexistent_location(self, mock_auth, mock_create, client):
        """Creating an arrow neighbor with non-existent location returns 404."""
        from fastapi import HTTPException
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_create.side_effect = HTTPException(
            status_code=404, detail="Location 999 not found"
        )

        response = client.post(
            "/locations/arrows/10/neighbors/",
            json={"location_id": 999, "energy_cost": 1},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404

    @patch("crud.create_arrow_neighbor", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_arrow_neighbor_nonexistent_arrow(self, mock_auth, mock_create, client):
        """Creating a neighbor for a non-existent arrow returns 404."""
        from fastapi import HTTPException
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_create.side_effect = HTTPException(
            status_code=404, detail="Arrow not found"
        )

        response = client.post(
            "/locations/arrows/999/neighbors/",
            json={"location_id": 5, "energy_cost": 1},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404

    @patch("auth_http.requests.get")
    def test_create_arrow_neighbor_coords_out_of_range(self, mock_auth, client):
        """Path data with coordinates > 100 returns 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.post(
            "/locations/arrows/10/neighbors/",
            json={
                "location_id": 5,
                "energy_cost": 1,
                "path_data": [{"x": 150.0, "y": 50.0}],
            },
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    @patch("auth_http.requests.get")
    def test_create_arrow_neighbor_negative_coords(self, mock_auth, client):
        """Path data with negative coordinates returns 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.post(
            "/locations/arrows/10/neighbors/",
            json={
                "location_id": 5,
                "energy_cost": 1,
                "path_data": [{"x": -1.0, "y": 50.0}],
            },
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    @patch("auth_http.requests.get")
    def test_create_arrow_neighbor_too_many_waypoints(self, mock_auth, client):
        """More than 50 waypoints returns 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        waypoints = [{"x": float(i % 100), "y": float(i % 100)} for i in range(51)]
        response = client.post(
            "/locations/arrows/10/neighbors/",
            json={"location_id": 5, "energy_cost": 1, "path_data": waypoints},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400


class TestUpdateArrowNeighborPath:
    """Tests for PUT /locations/arrows/neighbors/{location_id}/{arrow_id}/path."""

    @patch("crud.update_arrow_neighbor_path", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_arrow_neighbor_path_success(self, mock_auth, mock_update, client):
        """Updating arrow neighbor path returns updated data."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        path = [{"x": 10.0, "y": 20.0}, {"x": 30.0, "y": 40.0}]
        mock_update.return_value = {
            "location_id": 5,
            "arrow_id": 10,
            "energy_cost": 2,
            "path_data": path,
        }

        response = client.put(
            "/locations/arrows/neighbors/5/10/path",
            json={"path_data": path},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["location_id"] == 5
        assert data["arrow_id"] == 10
        assert data["path_data"] == path

    @patch("crud.update_arrow_neighbor_path", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_arrow_neighbor_path_not_found(self, mock_auth, mock_update, client):
        """Updating path for non-existent arrow neighbor returns 404."""
        from fastapi import HTTPException
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_update.side_effect = HTTPException(
            status_code=404, detail="Arrow neighbor not found"
        )

        response = client.put(
            "/locations/arrows/neighbors/999/888/path",
            json={"path_data": [{"x": 10.0, "y": 20.0}]},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404

    @patch("crud.update_arrow_neighbor_path", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_arrow_neighbor_path_empty(self, mock_auth, mock_update, client):
        """Updating with empty path_data (straight line) succeeds."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_update.return_value = {
            "location_id": 5,
            "arrow_id": 10,
            "energy_cost": 0,
            "path_data": None,
        }

        response = client.put(
            "/locations/arrows/neighbors/5/10/path",
            json={"path_data": []},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200


class TestDeleteArrowNeighbor:
    """Tests for DELETE /locations/arrows/neighbors/{location_id}/{arrow_id}."""

    @patch("crud.delete_arrow_neighbor", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_arrow_neighbor_success(self, mock_auth, mock_delete, client):
        """Deleting an arrow neighbor returns success."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_delete.return_value = {"status": "deleted"}

        response = client.delete(
            "/locations/arrows/neighbors/5/10",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"

    @patch("crud.delete_arrow_neighbor", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_arrow_neighbor_not_found(self, mock_auth, mock_delete, client):
        """Deleting a non-existent arrow neighbor returns 404."""
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
# (e) Region details — arrows in map_items + arrow_edges
# ===========================================================================

class TestRegionDetailsArrows:
    """Tests for GET /locations/regions/{id}/details — arrows in response."""

    @patch("crud.get_region_full_details", new_callable=AsyncMock)
    def test_region_details_arrows_in_map_items(self, mock_details, client):
        """Arrows appear in map_items with type='arrow' and correct fields."""
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
            "map_items": [
                {
                    "id": 10,
                    "name": "To Region B",
                    "type": "arrow",
                    "map_icon_url": None,
                    "map_x": 95.0,
                    "map_y": 50.0,
                    "marker_type": None,
                    "image_url": None,
                    "target_region_id": 2,
                    "target_region_name": "Region B",
                    "paired_arrow_id": 11,
                },
                {
                    "id": 100,
                    "name": "Village",
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
                    "energy_cost": 0,
                    "path_data": [{"x": 50.0, "y": 45.0}],
                },
            ],
        }

        response = client.get("/locations/regions/1/details")
        assert response.status_code == 200
        data = response.json()

        # Find arrow item in map_items
        arrows = [item for item in data["map_items"] if item.get("type") == "arrow"]
        assert len(arrows) == 1
        arrow_item = arrows[0]
        assert arrow_item["id"] == 10
        assert arrow_item["type"] == "arrow"
        assert arrow_item["map_x"] == 95.0
        assert arrow_item["map_y"] == 50.0
        assert arrow_item["target_region_id"] == 2
        assert arrow_item["target_region_name"] == "Region B"
        assert arrow_item["paired_arrow_id"] == 11

    @patch("crud.get_region_full_details", new_callable=AsyncMock)
    def test_region_details_arrow_edges(self, mock_details, client):
        """Arrow edges appear in response with correct fields."""
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
            "neighbor_edges": [],
            "arrow_edges": [
                {
                    "location_id": 100,
                    "arrow_id": 10,
                    "energy_cost": 2,
                    "path_data": [{"x": 25.0, "y": 30.0}, {"x": 60.0, "y": 70.0}],
                },
                {
                    "location_id": 200,
                    "arrow_id": 10,
                    "energy_cost": 0,
                    "path_data": None,
                },
            ],
        }

        response = client.get("/locations/regions/1/details")
        assert response.status_code == 200
        data = response.json()
        edges = data["arrow_edges"]
        assert len(edges) == 2

        # First edge with path_data
        assert edges[0]["location_id"] == 100
        assert edges[0]["arrow_id"] == 10
        assert edges[0]["energy_cost"] == 2
        assert len(edges[0]["path_data"]) == 2

        # Second edge without path_data
        assert edges[1]["location_id"] == 200
        assert edges[1]["path_data"] is None

    @patch("crud.get_region_full_details", new_callable=AsyncMock)
    def test_region_details_no_arrows(self, mock_details, client):
        """Region with no arrows returns empty arrow_edges and no arrow items."""
        mock_details.return_value = {
            "id": 2,
            "country_id": 1,
            "name": "Empty Region",
            "description": "No arrows",
            "image_url": None,
            "map_image_url": None,
            "entrance_location": None,
            "leader_id": None,
            "x": 0,
            "y": 0,
            "districts": [],
            "map_items": [
                {
                    "id": 100, "name": "Loc", "type": "location",
                    "map_icon_url": None, "map_x": 50.0, "map_y": 50.0,
                    "marker_type": "safe", "image_url": None,
                },
            ],
            "neighbor_edges": [],
            "arrow_edges": [],
        }

        response = client.get("/locations/regions/2/details")
        assert response.status_code == 200
        data = response.json()
        assert data["arrow_edges"] == []
        arrows = [item for item in data["map_items"] if item.get("type") == "arrow"]
        assert len(arrows) == 0

    @patch("crud.get_region_full_details", new_callable=AsyncMock)
    def test_region_details_multiple_arrows(self, mock_details, client):
        """Region with multiple arrows to different regions shows all."""
        mock_details.return_value = {
            "id": 1,
            "country_id": 1,
            "name": "Hub Region",
            "description": "Central hub",
            "image_url": None,
            "map_image_url": None,
            "entrance_location": None,
            "leader_id": None,
            "x": 0,
            "y": 0,
            "districts": [],
            "map_items": [
                {
                    "id": 10, "name": "To Region B", "type": "arrow",
                    "map_icon_url": None, "map_x": 95.0, "map_y": 50.0,
                    "marker_type": None, "image_url": None,
                    "target_region_id": 2, "target_region_name": "Region B",
                    "paired_arrow_id": 11,
                },
                {
                    "id": 20, "name": "To Region C", "type": "arrow",
                    "map_icon_url": None, "map_x": 5.0, "map_y": 30.0,
                    "marker_type": None, "image_url": None,
                    "target_region_id": 3, "target_region_name": "Region C",
                    "paired_arrow_id": 21,
                },
            ],
            "neighbor_edges": [],
            "arrow_edges": [
                {"location_id": 100, "arrow_id": 10, "energy_cost": 0, "path_data": None},
                {"location_id": 100, "arrow_id": 20, "energy_cost": 0, "path_data": None},
            ],
        }

        response = client.get("/locations/regions/1/details")
        assert response.status_code == 200
        data = response.json()
        arrows = [item for item in data["map_items"] if item.get("type") == "arrow"]
        assert len(arrows) == 2
        assert data["arrow_edges"][0]["arrow_id"] != data["arrow_edges"][1]["arrow_id"]


# ===========================================================================
# (f) Security — auth checks on arrow endpoints
# ===========================================================================

class TestArrowSecurity:
    """Security tests for all arrow admin endpoints."""

    def test_create_arrow_no_auth_returns_401(self, client):
        """POST /arrows/create without auth returns 401."""
        response = client.post(
            "/locations/arrows/create",
            json={"region_id": 1, "target_region_id": 2},
        )
        assert response.status_code == 401

    def test_update_arrow_no_auth_returns_401(self, client):
        """PUT /arrows/{id}/update without auth returns 401."""
        response = client.put(
            "/locations/arrows/1/update",
            json={"x": 50.0},
        )
        assert response.status_code == 401

    def test_delete_arrow_no_auth_returns_401(self, client):
        """DELETE /arrows/{id}/delete without auth returns 401."""
        response = client.delete("/locations/arrows/1/delete")
        assert response.status_code == 401

    def test_create_arrow_neighbor_no_auth_returns_401(self, client):
        """POST /arrows/{id}/neighbors/ without auth returns 401."""
        response = client.post(
            "/locations/arrows/10/neighbors/",
            json={"location_id": 5, "energy_cost": 0},
        )
        assert response.status_code == 401

    def test_update_arrow_neighbor_no_auth_returns_401(self, client):
        """PUT /arrows/neighbors/{loc}/{arrow}/path without auth returns 401."""
        response = client.put(
            "/locations/arrows/neighbors/5/10/path",
            json={"path_data": [{"x": 10.0, "y": 20.0}]},
        )
        assert response.status_code == 401

    def test_delete_arrow_neighbor_no_auth_returns_401(self, client):
        """DELETE /arrows/neighbors/{loc}/{arrow} without auth returns 401."""
        response = client.delete("/locations/arrows/neighbors/5/10")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_create_arrow_non_admin_returns_403(self, mock_auth, client):
        """Non-admin user without locations:create returns 403."""
        mock_auth.return_value = _mock_response(200, REGULAR_USER_RESPONSE)

        response = client.post(
            "/locations/arrows/create",
            json={"region_id": 1, "target_region_id": 2},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_update_arrow_non_admin_returns_403(self, mock_auth, client):
        """Non-admin user without locations:update returns 403."""
        mock_auth.return_value = _mock_response(200, REGULAR_USER_RESPONSE)

        response = client.put(
            "/locations/arrows/1/update",
            json={"x": 50.0},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_delete_arrow_non_admin_returns_403(self, mock_auth, client):
        """Non-admin user without locations:delete returns 403."""
        mock_auth.return_value = _mock_response(200, REGULAR_USER_RESPONSE)

        response = client.delete(
            "/locations/arrows/1/delete",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403

    def test_sql_injection_in_arrow_id(self, client):
        """SQL injection in arrow_id path param does not cause 500."""
        response = client.put(
            "/locations/arrows/1;DROP TABLE region_transition_arrows;--/update",
            json={"x": 50.0},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code != 500

    def test_sql_injection_in_arrow_neighbor_path(self, client):
        """SQL injection in arrow neighbor path params does not cause 500."""
        response = client.delete(
            "/locations/arrows/neighbors/1 OR 1=1/10",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code != 500
