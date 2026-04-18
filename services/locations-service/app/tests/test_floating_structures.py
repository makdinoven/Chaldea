"""
Tests for floating_structures endpoints in locations-service (FEAT-123 / T14, FEAT-127 / T4).

Covers:
- GET /locations/map/floating-structures (empty + populated, server_now present, route round-trip)
- GET /locations/map/floating-structures?area_id=X (area_id filtering: FEAT-127)
- Admin CRUD: create (valid + invalid route_json + missing district), get, patch, delete
- Admin CRUD: create/update with area_id (FEAT-127)
- 401/403 without admin auth
- Structures with area_id=NULL excluded when filtering by specific area_id

CRUD layer is mocked: locations-service uses async SQLAlchemy + real MySQL,
which is unavailable in unit tests. We assert that the HTTP layer wires through
to crud + serialization correctly, and that auth gating + Pydantic validators work.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _admin_resp():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "id": 1,
        "username": "admin",
        "role": "admin",
        "permissions": [],
    }
    return resp


def _user_resp():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "id": 2,
        "username": "user",
        "role": "user",
        "permissions": [],
    }
    return resp


def _make_obj(**overrides):
    base = dict(
        id=1,
        name="Citadel",
        description="The flying fortress",
        icon_url="https://example.com/citadel.png",
        route_json=[{"x": 10.0, "y": 20.0}, {"x": 30.0, "y": 40.0}],
        speed=0.5,
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        internal_district_id=None,
        area_id=None,
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


VALID_PAYLOAD = {
    "name": "Citadel",
    "description": "Flying fortress",
    "icon_url": "https://example.com/c.png",
    "route_json": [{"x": 10.0, "y": 20.0}, {"x": 30.0, "y": 40.0}],
    "speed": 0.5,
    "started_at": "2026-01-01T12:00:00",
    "internal_district_id": None,
    "area_id": None,
}

ADMIN_HEADERS = {"Authorization": "Bearer admin-token"}


# ---------------------------------------------------------------------------
# Public GET /locations/map/floating-structures
# ---------------------------------------------------------------------------
class TestPublicListFloatingStructures:
    @patch("crud.list_floating_structures", new_callable=AsyncMock)
    def test_empty_list(self, mock_list, client):
        mock_list.return_value = []
        response = client.get("/locations/map/floating-structures")
        assert response.status_code == 200
        assert response.json() == []

    @patch("crud.list_floating_structures", new_callable=AsyncMock)
    def test_returns_record_with_server_now_and_route(self, mock_list, client):
        mock_list.return_value = [_make_obj()]
        response = client.get("/locations/map/floating-structures")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list) and len(body) == 1
        item = body[0]
        # server_now must be present (set by endpoint)
        assert "server_now" in item and item["server_now"]
        # route_json round-trips
        assert item["route_json"] == [
            {"x": 10.0, "y": 20.0},
            {"x": 30.0, "y": 40.0},
        ]
        # core fields
        assert item["id"] == 1
        assert item["name"] == "Citadel"
        assert item["speed"] == 0.5
        assert "started_at" in item


# ---------------------------------------------------------------------------
# Admin auth: 401/403
# ---------------------------------------------------------------------------
class TestAdminAuthGating:
    def test_list_no_token_401(self, client):
        response = client.get("/locations/admin/floating-structures")
        assert response.status_code == 401

    def test_create_no_token_401(self, client):
        response = client.post("/locations/admin/floating-structures", json=VALID_PAYLOAD)
        assert response.status_code == 401

    def test_get_no_token_401(self, client):
        response = client.get("/locations/admin/floating-structures/1")
        assert response.status_code == 401

    def test_patch_no_token_401(self, client):
        response = client.patch("/locations/admin/floating-structures/1", json={"name": "X"})
        assert response.status_code == 401

    def test_delete_no_token_401(self, client):
        response = client.delete("/locations/admin/floating-structures/1")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_create_non_admin_403(self, mock_get, client):
        mock_get.return_value = _user_resp()
        response = client.post(
            "/locations/admin/floating-structures",
            json=VALID_PAYLOAD,
            headers={"Authorization": "Bearer user-token"},
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_list_non_admin_403(self, mock_get, client):
        mock_get.return_value = _user_resp()
        response = client.get(
            "/locations/admin/floating-structures",
            headers={"Authorization": "Bearer user-token"},
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Admin CRUD: create
# ---------------------------------------------------------------------------
class TestAdminCreate:
    @patch("auth_http.requests.get")
    @patch("crud.create_floating_structure", new_callable=AsyncMock)
    def test_create_valid(self, mock_create, mock_auth, client):
        mock_auth.return_value = _admin_resp()
        mock_create.return_value = _make_obj()
        response = client.post(
            "/locations/admin/floating-structures",
            json=VALID_PAYLOAD,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["name"] == "Citadel"
        assert body["route_json"] == [
            {"x": 10.0, "y": 20.0},
            {"x": 30.0, "y": 40.0},
        ]
        assert mock_create.await_count == 1

    @patch("auth_http.requests.get")
    def test_create_invalid_route_json_shape_returns_422(self, mock_auth, client):
        mock_auth.return_value = _admin_resp()
        bad = dict(VALID_PAYLOAD)
        # missing 'y' field
        bad["route_json"] = [{"x": 10.0}]
        response = client.post(
            "/locations/admin/floating-structures",
            json=bad,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422

    @patch("auth_http.requests.get")
    def test_create_route_json_out_of_range_returns_422(self, mock_auth, client):
        mock_auth.return_value = _admin_resp()
        bad = dict(VALID_PAYLOAD)
        bad["route_json"] = [{"x": 999.0, "y": 5.0}]
        response = client.post(
            "/locations/admin/floating-structures",
            json=bad,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422

    @patch("auth_http.requests.get")
    @patch("crud.create_floating_structure", new_callable=AsyncMock)
    def test_create_invalid_internal_district_id_returns_404(
        self, mock_create, mock_auth, client
    ):
        mock_auth.return_value = _admin_resp()
        # crud raises 404 when district doesn't exist
        mock_create.side_effect = HTTPException(
            status_code=404, detail="Район с id=999 не найден"
        )
        payload = dict(VALID_PAYLOAD)
        payload["internal_district_id"] = 999
        response = client.post(
            "/locations/admin/floating-structures",
            json=payload,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Admin CRUD: get / patch / delete
# ---------------------------------------------------------------------------
class TestAdminGetPatchDelete:
    @patch("auth_http.requests.get")
    @patch("crud.get_floating_structure", new_callable=AsyncMock)
    def test_get_existing(self, mock_get, mock_auth, client):
        mock_auth.return_value = _admin_resp()
        mock_get.return_value = _make_obj()
        response = client.get(
            "/locations/admin/floating-structures/1", headers=ADMIN_HEADERS
        )
        assert response.status_code == 200
        assert response.json()["id"] == 1

    @patch("auth_http.requests.get")
    @patch("crud.get_floating_structure", new_callable=AsyncMock)
    def test_get_missing_returns_404(self, mock_get, mock_auth, client):
        mock_auth.return_value = _admin_resp()
        mock_get.return_value = None
        response = client.get(
            "/locations/admin/floating-structures/9999", headers=ADMIN_HEADERS
        )
        assert response.status_code == 404

    @patch("auth_http.requests.get")
    @patch("crud.update_floating_structure", new_callable=AsyncMock)
    def test_patch_updates_name(self, mock_update, mock_auth, client):
        mock_auth.return_value = _admin_resp()
        mock_update.return_value = _make_obj(name="Renamed")
        response = client.patch(
            "/locations/admin/floating-structures/1",
            json={"name": "Renamed"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Renamed"
        assert mock_update.await_count == 1

    @patch("auth_http.requests.get")
    def test_patch_invalid_route_json_returns_422(self, mock_auth, client):
        mock_auth.return_value = _admin_resp()
        response = client.patch(
            "/locations/admin/floating-structures/1",
            json={"route_json": [{"x": 1.0}]},  # missing y
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422

    @patch("auth_http.requests.get")
    @patch("crud.update_floating_structure", new_callable=AsyncMock)
    def test_patch_invalid_internal_district_id_returns_404(
        self, mock_update, mock_auth, client
    ):
        mock_auth.return_value = _admin_resp()
        mock_update.side_effect = HTTPException(
            status_code=404, detail="Район с id=999 не найден"
        )
        response = client.patch(
            "/locations/admin/floating-structures/1",
            json={"internal_district_id": 999},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404

    @patch("auth_http.requests.get")
    @patch("crud.delete_floating_structure", new_callable=AsyncMock)
    def test_delete_success(self, mock_delete, mock_auth, client):
        mock_auth.return_value = _admin_resp()
        mock_delete.return_value = None
        response = client.delete(
            "/locations/admin/floating-structures/1", headers=ADMIN_HEADERS
        )
        assert response.status_code == 204
        assert mock_delete.await_count == 1

    @patch("auth_http.requests.get")
    @patch("crud.delete_floating_structure", new_callable=AsyncMock)
    def test_delete_missing_returns_404(self, mock_delete, mock_auth, client):
        mock_auth.return_value = _admin_resp()
        mock_delete.side_effect = HTTPException(
            status_code=404, detail="Плавающая структура не найдена"
        )
        response = client.delete(
            "/locations/admin/floating-structures/9999", headers=ADMIN_HEADERS
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# FEAT-127: area_id filtering on public endpoint
# ---------------------------------------------------------------------------
class TestAreaIdFiltering:
    """Tests for GET /locations/map/floating-structures?area_id=X (FEAT-127)."""

    @patch("crud.list_floating_structures", new_callable=AsyncMock)
    def test_filter_by_area_id_returns_only_matching(self, mock_list, client):
        """area_id=1 should return only structures with area_id=1."""
        mock_list.return_value = [_make_obj(id=1, area_id=1, name="Citadel A1")]
        response = client.get("/locations/map/floating-structures?area_id=1")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["area_id"] == 1
        assert body[0]["name"] == "Citadel A1"
        # Verify crud was called with area_id=1
        mock_list.assert_awaited_once()
        call_kwargs = mock_list.call_args
        assert call_kwargs.kwargs.get("area_id") == 1

    @patch("crud.list_floating_structures", new_callable=AsyncMock)
    def test_no_area_id_returns_all_structures(self, mock_list, client):
        """No area_id param should return all structures (backward compat)."""
        mock_list.return_value = [
            _make_obj(id=1, area_id=1, name="Citadel A1"),
            _make_obj(id=2, area_id=2, name="Teleporter A2"),
            _make_obj(id=3, area_id=None, name="Unassigned"),
        ]
        response = client.get("/locations/map/floating-structures")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 3
        # Verify crud was called with area_id=None (no filter)
        mock_list.assert_awaited_once()
        call_kwargs = mock_list.call_args
        assert call_kwargs.kwargs.get("area_id") is None

    @patch("crud.list_floating_structures", new_callable=AsyncMock)
    def test_filter_by_area_id_excludes_null_area_id(self, mock_list, client):
        """When filtering by area_id=1, structures with area_id=NULL must NOT appear."""
        # The mock returns empty because crud filters at DB level —
        # structures with NULL area_id don't match WHERE area_id=1.
        mock_list.return_value = []
        response = client.get("/locations/map/floating-structures?area_id=1")
        assert response.status_code == 200
        assert response.json() == []
        mock_list.assert_awaited_once()
        call_kwargs = mock_list.call_args
        assert call_kwargs.kwargs.get("area_id") == 1

    @patch("crud.list_floating_structures", new_callable=AsyncMock)
    def test_filter_by_area_id_empty_result(self, mock_list, client):
        """area_id=999 (no structures in that area) returns empty list."""
        mock_list.return_value = []
        response = client.get("/locations/map/floating-structures?area_id=999")
        assert response.status_code == 200
        assert response.json() == []

    @patch("crud.list_floating_structures", new_callable=AsyncMock)
    def test_area_id_included_in_public_response(self, mock_list, client):
        """area_id field is present in the serialized public response."""
        mock_list.return_value = [_make_obj(id=5, area_id=42)]
        response = client.get("/locations/map/floating-structures?area_id=42")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["area_id"] == 42
        assert "server_now" in body[0]

    @patch("crud.list_floating_structures", new_callable=AsyncMock)
    def test_area_id_null_in_public_response_when_unassigned(self, mock_list, client):
        """Structures with no area_id have area_id=null in the response."""
        mock_list.return_value = [_make_obj(id=3, area_id=None)]
        response = client.get("/locations/map/floating-structures")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["area_id"] is None


# ---------------------------------------------------------------------------
# FEAT-127: area_id in admin create / update
# ---------------------------------------------------------------------------
class TestAdminAreaId:
    """Tests for area_id in admin create/update endpoints (FEAT-127)."""

    @patch("auth_http.requests.get")
    @patch("crud.create_floating_structure", new_callable=AsyncMock)
    def test_create_with_area_id(self, mock_create, mock_auth, client):
        """Creating a structure with area_id should persist it in response."""
        mock_auth.return_value = _admin_resp()
        mock_create.return_value = _make_obj(id=10, area_id=1, name="Area Citadel")
        payload = dict(VALID_PAYLOAD)
        payload["area_id"] = 1
        response = client.post(
            "/locations/admin/floating-structures",
            json=payload,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["area_id"] == 1
        assert body["name"] == "Area Citadel"
        assert mock_create.await_count == 1

    @patch("auth_http.requests.get")
    @patch("crud.create_floating_structure", new_callable=AsyncMock)
    def test_create_without_area_id_defaults_to_null(self, mock_create, mock_auth, client):
        """Creating a structure without area_id should default to null."""
        mock_auth.return_value = _admin_resp()
        mock_create.return_value = _make_obj(id=11, area_id=None)
        payload = dict(VALID_PAYLOAD)
        payload.pop("area_id", None)
        response = client.post(
            "/locations/admin/floating-structures",
            json=payload,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["area_id"] is None

    @patch("auth_http.requests.get")
    @patch("crud.update_floating_structure", new_callable=AsyncMock)
    def test_patch_area_id(self, mock_update, mock_auth, client):
        """Updating a structure's area_id should be reflected in response."""
        mock_auth.return_value = _admin_resp()
        mock_update.return_value = _make_obj(id=1, area_id=2, name="Citadel")
        response = client.patch(
            "/locations/admin/floating-structures/1",
            json={"area_id": 2},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["area_id"] == 2
        assert mock_update.await_count == 1

    @patch("auth_http.requests.get")
    @patch("crud.update_floating_structure", new_callable=AsyncMock)
    def test_patch_area_id_to_null(self, mock_update, mock_auth, client):
        """Setting area_id to null (unassign) should work."""
        mock_auth.return_value = _admin_resp()
        mock_update.return_value = _make_obj(id=1, area_id=None)
        response = client.patch(
            "/locations/admin/floating-structures/1",
            json={"area_id": None},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["area_id"] is None

    @patch("auth_http.requests.get")
    @patch("crud.get_floating_structure", new_callable=AsyncMock)
    def test_get_includes_area_id(self, mock_get, mock_auth, client):
        """Admin GET single structure includes area_id in response."""
        mock_auth.return_value = _admin_resp()
        mock_get.return_value = _make_obj(id=7, area_id=3)
        response = client.get(
            "/locations/admin/floating-structures/7", headers=ADMIN_HEADERS
        )
        assert response.status_code == 200
        assert response.json()["area_id"] == 3
