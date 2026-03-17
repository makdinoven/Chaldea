"""
Tests for rules CRUD endpoints in locations-service.

Covers:
- GET /rules/list — empty list, list with rules ordered by sort_order
- GET /rules/{id} — returns rule, 404 for non-existent
- POST /rules/create — creates rule (admin), 401/403 without admin auth
- PUT /rules/{id}/update — partial update (admin), 404 for non-existent
- DELETE /rules/{id}/delete — deletes (admin), 404 for non-existent
- PUT /rules/reorder — bulk update sort_order (admin)
- Security: SQL injection in path params
"""

from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

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

ADMIN_USER_RESPONSE = {"id": 1, "username": "admin", "role": "admin"}
REGULAR_USER_RESPONSE = {"id": 2, "username": "user", "role": "user"}


def _make_rule(rule_id=1, title="Test Rule", content="<p>Content</p>", sort_order=0, image_url=None):
    """Create a mock GameRule ORM object."""
    rule = MagicMock()
    rule.id = rule_id
    rule.title = title
    rule.content = content
    rule.sort_order = sort_order
    rule.image_url = image_url
    rule.created_at = datetime(2026, 1, 1, 12, 0, 0)
    rule.updated_at = datetime(2026, 1, 1, 12, 0, 0)
    return rule


# ===========================================================================
# GET /rules/list
# ===========================================================================

class TestGetRulesList:
    """Tests for GET /rules/list (public endpoint, no auth)."""

    @patch("crud.get_all_rules", new_callable=AsyncMock, return_value=[])
    def test_empty_list(self, mock_crud, client):
        """Returns empty list when no rules exist."""
        response = client.get("/rules/list")
        assert response.status_code == 200
        assert response.json() == []

    @patch("crud.get_all_rules", new_callable=AsyncMock)
    def test_list_with_rules_ordered(self, mock_crud, client):
        """Returns rules ordered by sort_order ASC, id ASC."""
        rules = [
            _make_rule(rule_id=1, title="First", sort_order=0),
            _make_rule(rule_id=2, title="Second", sort_order=1),
            _make_rule(rule_id=3, title="Third", sort_order=2),
        ]
        mock_crud.return_value = rules

        response = client.get("/rules/list")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert data[0]["title"] == "First"
        assert data[1]["title"] == "Second"
        assert data[2]["title"] == "Third"
        # Verify sort_order values are in order
        assert data[0]["sort_order"] < data[1]["sort_order"] < data[2]["sort_order"]

    @patch("crud.get_all_rules", new_callable=AsyncMock)
    def test_list_returns_all_fields(self, mock_crud, client):
        """Verifies all expected fields are in the response."""
        rules = [_make_rule(image_url="https://s3.example.com/rules/img.webp")]
        mock_crud.return_value = rules

        response = client.get("/rules/list")
        assert response.status_code == 200
        data = response.json()
        rule = data[0]
        assert "id" in rule
        assert "title" in rule
        assert "image_url" in rule
        assert "content" in rule
        assert "sort_order" in rule
        assert "created_at" in rule
        assert "updated_at" in rule

    def test_list_no_auth_required(self, client):
        """GET /rules/list should be accessible without auth token (public)."""
        with patch("crud.get_all_rules", new_callable=AsyncMock, return_value=[]):
            response = client.get("/rules/list")
            # Should NOT return 401/403 — it's a public endpoint
            assert response.status_code == 200


# ===========================================================================
# GET /rules/{rule_id}
# ===========================================================================

class TestGetRule:
    """Tests for GET /rules/{rule_id} (public endpoint)."""

    @patch("crud.get_rule_by_id", new_callable=AsyncMock)
    def test_get_existing_rule(self, mock_crud, client):
        """Returns a rule when it exists."""
        mock_crud.return_value = _make_rule(rule_id=42, title="Combat Rules")

        response = client.get("/rules/42")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 42
        assert data["title"] == "Combat Rules"

    @patch("crud.get_rule_by_id", new_callable=AsyncMock, return_value=None)
    def test_get_nonexistent_rule_returns_404(self, mock_crud, client):
        """Returns 404 when rule does not exist."""
        response = client.get("/rules/99999")
        assert response.status_code == 404

    def test_get_rule_no_auth_required(self, client):
        """GET /rules/{id} should be accessible without auth."""
        with patch("crud.get_rule_by_id", new_callable=AsyncMock, return_value=_make_rule()):
            response = client.get("/rules/1")
            assert response.status_code == 200


# ===========================================================================
# POST /rules/create
# ===========================================================================

class TestCreateRule:
    """Tests for POST /rules/create (admin-only)."""

    def test_missing_token_returns_401(self, client):
        """No Authorization header -> 401."""
        response = client.post("/rules/create", json={"title": "New Rule"})
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client):
        """Valid token but role != admin -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.post(
            "/rules/create",
            json={"title": "New Rule"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get, client):
        """User-service returns 401 for invalid token -> 401."""
        mock_get.return_value = _mock_response(401)
        response = client.post(
            "/rules/create",
            json={"title": "New Rule"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 401

    @patch("crud.create_rule", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_rule_success(self, mock_auth, mock_crud, client):
        """Admin can create a rule."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_rule(rule_id=10, title="New Rule", sort_order=5)

        response = client.post(
            "/rules/create",
            json={"title": "New Rule", "content": "<p>Text</p>", "sort_order": 5},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Rule"
        assert data["sort_order"] == 5

    @patch("crud.create_rule", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_create_rule_default_sort_order(self, mock_auth, mock_crud, client):
        """sort_order defaults to 0 if not provided."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_rule(rule_id=11, title="Rule Default", sort_order=0)

        response = client.post(
            "/rules/create",
            json={"title": "Rule Default"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200

    @patch("auth_http.requests.get")
    def test_create_rule_missing_title_returns_422(self, mock_auth, client):
        """Missing required field 'title' -> 422."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        response = client.post(
            "/rules/create",
            json={"content": "<p>No title</p>"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422


# ===========================================================================
# PUT /rules/{rule_id}/update
# ===========================================================================

class TestUpdateRule:
    """Tests for PUT /rules/{rule_id}/update (admin-only)."""

    def test_missing_token_returns_401(self, client):
        """No auth -> 401."""
        response = client.put("/rules/1/update", json={"title": "Updated"})
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client):
        """Non-admin -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.put(
            "/rules/1/update",
            json={"title": "Updated"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403

    @patch("crud.update_rule", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_rule_success(self, mock_auth, mock_crud, client):
        """Admin can partially update a rule."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.return_value = _make_rule(rule_id=1, title="Updated Title")

        response = client.put(
            "/rules/1/update",
            json={"title": "Updated Title"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Updated Title"

    @patch("crud.update_rule", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_update_nonexistent_rule_returns_404(self, mock_auth, mock_crud, client):
        """Updating non-existent rule -> 404 (raised by crud.update_rule)."""
        from fastapi import HTTPException
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.side_effect = HTTPException(status_code=404, detail="Правило не найдено")

        response = client.put(
            "/rules/99999/update",
            json={"title": "Ghost"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404


# ===========================================================================
# DELETE /rules/{rule_id}/delete
# ===========================================================================

class TestDeleteRule:
    """Tests for DELETE /rules/{rule_id}/delete (admin-only)."""

    def test_missing_token_returns_401(self, client):
        """No auth -> 401."""
        response = client.delete("/rules/1/delete")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client):
        """Non-admin -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.delete(
            "/rules/1/delete",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403

    @patch("crud.delete_rule", new_callable=AsyncMock, return_value=None)
    @patch("auth_http.requests.get")
    def test_delete_rule_success(self, mock_auth, mock_crud, client):
        """Admin can delete a rule."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.delete("/rules/1/delete", headers=ADMIN_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "1" in data["message"]

    @patch("crud.delete_rule", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_delete_nonexistent_rule_returns_404(self, mock_auth, mock_crud, client):
        """Deleting non-existent rule -> 404."""
        from fastapi import HTTPException
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        mock_crud.side_effect = HTTPException(status_code=404, detail="Правило не найдено")

        response = client.delete("/rules/99999/delete", headers=ADMIN_HEADERS)
        assert response.status_code == 404


# ===========================================================================
# PUT /rules/reorder
# ===========================================================================

class TestReorderRules:
    """Tests for PUT /rules/reorder (admin-only)."""

    def test_missing_token_returns_401(self, client):
        """No auth -> 401."""
        response = client.put(
            "/rules/reorder",
            json={"order": [{"id": 1, "sort_order": 0}]},
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client):
        """Non-admin -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.put(
            "/rules/reorder",
            json={"order": [{"id": 1, "sort_order": 0}]},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403

    @patch("crud.reorder_rules", new_callable=AsyncMock, return_value=None)
    @patch("auth_http.requests.get")
    def test_reorder_success(self, mock_auth, mock_crud, client):
        """Admin can bulk-update sort_order."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.put(
            "/rules/reorder",
            json={"order": [
                {"id": 3, "sort_order": 0},
                {"id": 1, "sort_order": 1},
                {"id": 2, "sort_order": 2},
            ]},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    @patch("auth_http.requests.get")
    def test_reorder_invalid_payload_returns_422(self, mock_auth, client):
        """Missing 'order' field -> 422."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        response = client.put(
            "/rules/reorder",
            json={"wrong_field": []},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422

    @patch("crud.reorder_rules", new_callable=AsyncMock, return_value=None)
    @patch("auth_http.requests.get")
    def test_reorder_empty_list(self, mock_auth, mock_crud, client):
        """Empty order list should still succeed."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.put(
            "/rules/reorder",
            json={"order": []},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200


# ===========================================================================
# Security Tests
# ===========================================================================

class TestRulesSecurity:
    """Security tests: SQL injection attempts in path parameters."""

    @patch("crud.get_rule_by_id", new_callable=AsyncMock, return_value=None)
    def test_sql_injection_in_rule_id_get(self, mock_crud, client):
        """SQL injection in rule_id path param should return 422 (not a valid int)."""
        response = client.get("/rules/1;DROP TABLE game_rules;--")
        # FastAPI validates path param as int -> 422
        assert response.status_code == 422

    def test_sql_injection_in_rule_id_delete(self, client):
        """SQL injection in delete endpoint path param -> 401/404/422.

        The delete route requires admin auth, so without a token the
        response may be 401 (auth fires before path-param validation).
        Any of 401/404/422 means the injection is safely rejected.
        """
        response = client.delete("/rules/1 OR 1=1/delete")
        assert response.status_code in (401, 404, 422)
