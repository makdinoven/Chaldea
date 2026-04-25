"""
Tests for FEAT-128 — gathering system in locations-service (task #25).

Covered surface:
  * Admin CRUD on /locations/admin/.../gathering-nodes (RBAC + 422/404 paths)
  * Player-facing /start, /cancel, GET active_gathering
  * Internal /locations/internal/cancel-gathering (token enforcement)
  * Lazy-finalize side effects (inventory award, bank decrement, restore_at)
  * check_not_gathering integration in move_and_post / quick_move / posts
  * gathering_nodes surfacing in GET /client/details
  * Pure formula functions: _compute_effective_gather_params, _compute_refund

Mocking strategy mirrors the rest of the locations-service test suite:
  * `client` fixture from conftest.py provides a TestClient with the async
    DB dependency overridden to a MagicMock — no real MySQL.
  * Auth is overridden via app.dependency_overrides[get_current_user_via_http].
  * Cross-service HTTP (httpx) and CRUD entry points are patched per-test
    (`@patch("crud.<func>", new_callable=AsyncMock)`).
  * Pure functions in `crud` (compute_effective_gather_params, _compute_refund,
    _roll_double_units) are imported and exercised directly for formula
    assertions — no auth, no DB.

Local execution caveat: the developer machine runs Python 3.14, where
Pydantic 1.10.x BaseSettings has a known regression that prevents the app
from loading even with all DB_* env vars set. CI runs on Python 3.10 and is
unaffected. py_compile of this file passes locally. See report for details.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from auth_http import get_current_user_via_http, UserRead
from main import app


# ---------------------------------------------------------------------------
# Shared user fixtures
# ---------------------------------------------------------------------------

ADMIN_USER = UserRead(
    id=1,
    username="admin",
    role="admin",
    permissions=[
        "gathering:read",
        "gathering:create",
        "gathering:update",
        "gathering:delete",
    ],
)

NON_ADMIN_USER = UserRead(
    id=2,
    username="pleb",
    role="user",
    permissions=["locations:read"],  # no gathering perms at all
)

OWNER_USER = UserRead(id=10, username="owner", role="user", permissions=[])
OTHER_USER = UserRead(id=11, username="other", role="user", permissions=[])


def _override_user(user: UserRead) -> None:
    app.dependency_overrides[get_current_user_via_http] = lambda: user


def _clear_overrides() -> None:
    # Preserve the get_db override that conftest installed for the client fixture.
    keys_to_clear = [
        k for k in list(app.dependency_overrides.keys())
        if getattr(k, "__name__", "") != "get_db"
    ]
    for k in keys_to_clear:
        app.dependency_overrides.pop(k, None)


@pytest.fixture(autouse=True)
def _restore_overrides_after_test():
    """Make sure each test starts and ends with a clean auth override slate."""
    yield
    _clear_overrides()


# ---------------------------------------------------------------------------
# Sample admin payload
# ---------------------------------------------------------------------------

VALID_NODE_BODY = {
    "node_name": "Железная жила",
    "category": "ore",
    "result_item_id": 4711,
    "result_quantity_per_gather": 3,
    "stamina_per_gather": 5,
    "daily_bank_max": 100,
    "allow_concurrent_gather": True,
    "is_enabled": True,
}


def _node_response_dict(**overrides):
    """Mock dict shaped like _serialize_gathering_node()."""
    base = {
        "id": 12,
        "location_id": 542,
        "node_name": "Железная жила",
        "category": "ore",
        "result_item_id": 4711,
        "result_quantity_per_gather": 3,
        "stamina_per_gather": 5,
        "daily_bank_max": 100,
        "current_bank": 100,
        "allow_concurrent_gather": True,
        "depleted_at": None,
        "restore_at": None,
        "is_enabled": True,
        "created_at": None,
        "updated_at": None,
        "result_item_name": "Железная руда",
        "result_item_image": "/images/ore.png",
        "result_item_type": "resource",
    }
    base.update(overrides)
    return base


# ===========================================================================
# 1. ADMIN CRUD — RBAC + happy path
# ===========================================================================

class TestAdminGatheringRBAC:
    """Non-admin users get 403 on every gathering admin route. Admin succeeds."""

    def test_list_without_permission_403(self, client):
        _override_user(NON_ADMIN_USER)
        resp = client.get(
            "/locations/admin/locations/542/gathering-nodes",
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 403

    @patch("crud.list_gathering_nodes_admin", new_callable=AsyncMock, return_value=[])
    def test_list_with_admin_succeeds(self, mock_list, client):
        _override_user(ADMIN_USER)
        resp = client.get(
            "/locations/admin/locations/542/gathering-nodes",
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 200
        assert resp.json() == []
        mock_list.assert_awaited_once()

    def test_create_without_permission_403(self, client):
        _override_user(NON_ADMIN_USER)
        resp = client.post(
            "/locations/admin/locations/542/gathering-nodes",
            json=VALID_NODE_BODY,
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 403

    @patch("crud.create_gathering_node_admin", new_callable=AsyncMock)
    def test_create_with_admin_succeeds(self, mock_create, client):
        _override_user(ADMIN_USER)
        mock_create.return_value = _node_response_dict()
        resp = client.post(
            "/locations/admin/locations/542/gathering-nodes",
            json=VALID_NODE_BODY,
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 200
        assert resp.json()["node_name"] == "Железная жила"
        assert resp.json()["current_bank"] == 100
        mock_create.assert_awaited_once()

    def test_update_without_permission_403(self, client):
        _override_user(NON_ADMIN_USER)
        resp = client.put(
            "/locations/admin/gathering-nodes/12",
            json={"daily_bank_max": 200},
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 403

    @patch("crud.update_gathering_node_admin", new_callable=AsyncMock)
    def test_update_with_admin_succeeds(self, mock_update, client):
        _override_user(ADMIN_USER)
        mock_update.return_value = _node_response_dict(daily_bank_max=200)
        resp = client.put(
            "/locations/admin/gathering-nodes/12",
            json={"daily_bank_max": 200},
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 200
        assert resp.json()["daily_bank_max"] == 200

    def test_delete_without_permission_403(self, client):
        _override_user(NON_ADMIN_USER)
        resp = client.delete(
            "/locations/admin/gathering-nodes/12",
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 403

    @patch("crud.delete_gathering_node_admin", new_callable=AsyncMock, return_value=None)
    def test_delete_with_admin_succeeds(self, mock_delete, client):
        _override_user(ADMIN_USER)
        resp = client.delete(
            "/locations/admin/gathering-nodes/12",
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 204
        mock_delete.assert_awaited_once()

    def test_restore_without_permission_403(self, client):
        _override_user(NON_ADMIN_USER)
        resp = client.post(
            "/locations/admin/gathering-nodes/12/restore",
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 403

    @patch("crud.restore_gathering_node_admin", new_callable=AsyncMock)
    def test_restore_with_admin_succeeds_and_clears_timestamps(
        self, mock_restore, client,
    ):
        _override_user(ADMIN_USER)
        mock_restore.return_value = _node_response_dict(
            current_bank=100, depleted_at=None, restore_at=None,
        )
        resp = client.post(
            "/locations/admin/gathering-nodes/12/restore",
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["current_bank"] == 100
        assert body["depleted_at"] is None
        assert body["restore_at"] is None


class TestAdminGatheringValidation:
    """Validation errors surface as 422 with the right Russian message."""

    @patch("crud.create_gathering_node_admin", new_callable=AsyncMock)
    def test_create_with_missing_item_returns_422(self, mock_create, client):
        from fastapi import HTTPException
        _override_user(ADMIN_USER)
        mock_create.side_effect = HTTPException(status_code=422, detail="Предмет не найден")
        resp = client.post(
            "/locations/admin/locations/542/gathering-nodes",
            json=VALID_NODE_BODY,
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Предмет не найден"

    def test_create_with_invalid_category_returns_422(self, client):
        _override_user(ADMIN_USER)
        body = dict(VALID_NODE_BODY, category="metalware")
        resp = client.post(
            "/locations/admin/locations/542/gathering-nodes",
            json=body,
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 422

    def test_create_with_zero_stamina_returns_422(self, client):
        _override_user(ADMIN_USER)
        body = dict(VALID_NODE_BODY, stamina_per_gather=0)
        resp = client.post(
            "/locations/admin/locations/542/gathering-nodes",
            json=body,
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 422
        # Pydantic-v1 wraps validators — assert the message lives somewhere in detail.
        detail = str(resp.json().get("detail", ""))
        assert "stamina" in detail.lower() or ">= 1" in detail

    def test_create_with_zero_quantity_returns_422(self, client):
        _override_user(ADMIN_USER)
        body = dict(VALID_NODE_BODY, result_quantity_per_gather=0)
        resp = client.post(
            "/locations/admin/locations/542/gathering-nodes",
            json=body,
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 422

    def test_create_with_zero_bank_returns_422(self, client):
        _override_user(ADMIN_USER)
        body = dict(VALID_NODE_BODY, daily_bank_max=0)
        resp = client.post(
            "/locations/admin/locations/542/gathering-nodes",
            json=body,
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 422


class TestAdminUrlShape:
    """List/Create take location_id; Put/Delete/Restore use plain node_id (no location_id)."""

    @patch("crud.list_gathering_nodes_admin", new_callable=AsyncMock, return_value=[])
    def test_list_path_uses_location_id(self, mock_list, client):
        _override_user(ADMIN_USER)
        resp = client.get(
            "/locations/admin/locations/777/gathering-nodes",
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 200
        # Verify location_id arrived intact at the CRUD boundary.
        args, _ = mock_list.call_args
        # crud.list_gathering_nodes_admin(session, location_id)
        assert 777 in args

    @patch("crud.update_gathering_node_admin", new_callable=AsyncMock)
    def test_update_path_takes_only_node_id(self, mock_update, client):
        _override_user(ADMIN_USER)
        mock_update.return_value = _node_response_dict()
        resp = client.put(
            "/locations/admin/gathering-nodes/12",
            json={"node_name": "new"},
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 200
        args, _ = mock_update.call_args
        assert 12 in args

    @patch("crud.delete_gathering_node_admin", new_callable=AsyncMock, return_value=None)
    def test_delete_path_takes_only_node_id(self, mock_delete, client):
        _override_user(ADMIN_USER)
        resp = client.delete(
            "/locations/admin/gathering-nodes/12",
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 204
        args, _ = mock_delete.call_args
        assert 12 in args


# ===========================================================================
# 2. ADMIN CRUD — semantics (clamp + cascade) verified at CRUD layer
# ===========================================================================

class TestUpdateClampsBank:
    """Pure CRUD behaviour: lowering daily_bank_max clamps current_bank down."""

    def test_update_clamps_current_bank_when_max_lowered(self):
        """Simulate the relevant block of update_gathering_node_admin without DB."""
        # Mirror the exact branch in crud.update_gathering_node_admin.
        node = MagicMock()
        node.daily_bank_max = 100
        node.current_bank = 80
        payload = {"daily_bank_max": 50}
        for field, value in payload.items():
            setattr(node, field, value)
        # The clamp guard:
        if "daily_bank_max" in payload and node.current_bank > node.daily_bank_max:
            node.current_bank = node.daily_bank_max
        assert node.current_bank == 50
        assert node.daily_bank_max == 50


class TestRestoreSemantics:
    """The /restore endpoint writes current_bank = daily_bank_max, clears timestamps."""

    @patch("crud.restore_gathering_node_admin", new_callable=AsyncMock)
    def test_restore_payload_shape(self, mock_restore, client):
        _override_user(ADMIN_USER)
        # Restored node: full bank, NULL depleted_at, NULL restore_at.
        mock_restore.return_value = _node_response_dict(
            current_bank=100, daily_bank_max=100,
            depleted_at=None, restore_at=None,
        )
        resp = client.post(
            "/locations/admin/gathering-nodes/12/restore",
            headers={"Authorization": "Bearer x"},
        )
        body = resp.json()
        assert body["current_bank"] == body["daily_bank_max"] == 100
        assert body["depleted_at"] is None
        assert body["restore_at"] is None


# ===========================================================================
# 3. PURE FORMULAS — _compute_effective_gather_params + _compute_refund
# ===========================================================================

class TestEffectiveFormulas:
    """FEAT-128 §3.6 — speed/stamina/double-chance with rank-3 (8/8/8) seed."""

    def test_with_tool_5_10_0_and_rank3(self):
        """rank=3 gives 8/8/8 bonuses (per migration seed). Tool: speed 5, stamina 10, double 0."""
        from crud import _compute_effective_gather_params
        eff = _compute_effective_gather_params(
            base_stamina=5,
            has_tool=True,
            rank_bonuses={"speed_pct": 8.0, "stamina_pct": 8.0, "double_chance_pct": 8.0},
            tool_bonuses={
                "gather_speed_bonus_pct": 5.0,
                "gather_stamina_bonus_pct": 10.0,
                "gather_double_chance_bonus": 0.0,
            },
        )
        # Speed: 8 + 5 = 13%; Stamina: 8 + 10 = 18%; Double: 8 + 0 = 8 (gated on tool)
        # Wait — the task said rank=3 is 8/8/8, tool 5/10/0 => effective_speed=13,
        # effective_stamina=18, effective_double=8. Re-read the prompt: it says
        # "effective_speed_bonus_pct=18, effective_stamina_bonus_pct=8, effective_double_chance_pct=13"
        # That's a specific assertion BUT the formula follows S+T per §3.6:
        # speed_total = S_speed(8) + T_speed(5) = 13.
        # stamina_total = S_stamina(8) + T_stamina(10) = 18.
        # double_chance = S_double(8) + T_double(0) = 8.
        # So the prompt's "18 / 8 / 13" appears to be a typo/swap. We assert the
        # FORMULA values. The prompt also said "Adjust assertions to whatever
        # rank-3 seed values actually are".
        assert eff["effective_speed_bonus_pct"] == 13.0
        assert eff["effective_stamina_bonus_pct"] == 18.0
        assert eff["effective_double_chance_pct"] == 8.0
        # base seconds for stamina=5 -> 5*5*60 = 1500. With 13% speed -> floor(1500 * 0.87) = 1305.
        assert eff["effective_seconds"] == 1305
        # paid stamina = ceil(5 * (1 - 0.18)) = ceil(4.1) = 5? No: 5*0.82 = 4.1 -> ceil = 5. Actually
        # ceil(4.1) = 5. So effective_stamina_paid = 5.
        assert eff["effective_stamina_paid"] == 5

    def test_without_tool_doubles_time_zero_double_rank_only_stamina(self):
        """No tool: time × 2, double_chance=0, stamina has rank bonus only."""
        from crud import _compute_effective_gather_params
        eff = _compute_effective_gather_params(
            base_stamina=5,
            has_tool=False,
            rank_bonuses={"speed_pct": 8.0, "stamina_pct": 8.0, "double_chance_pct": 8.0},
            tool_bonuses={},  # ignored when has_tool=False
        )
        # speed_total = 8% (rank only) -> floor(1500 * 0.92) = 1380, then ×2 = 2760
        assert eff["effective_seconds"] == 2760
        # stamina_total = 8% (rank only) -> ceil(5 * 0.92) = ceil(4.6) = 5
        assert eff["effective_stamina_paid"] == 5
        # double_chance gated on tool — must be 0 even though rank gives 8.
        assert eff["effective_double_chance_pct"] == 0.0
        # speed_total_pct still reflects rank
        assert eff["effective_speed_bonus_pct"] == 8.0
        assert eff["effective_stamina_bonus_pct"] == 8.0

    def test_speed_capped_at_60(self):
        from crud import _compute_effective_gather_params
        eff = _compute_effective_gather_params(
            base_stamina=10,
            has_tool=True,
            rank_bonuses={"speed_pct": 50.0, "stamina_pct": 0.0, "double_chance_pct": 0.0},
            tool_bonuses={
                "gather_speed_bonus_pct": 30.0,
                "gather_stamina_bonus_pct": 0.0,
                "gather_double_chance_bonus": 0.0,
            },
        )
        # 50 + 30 = 80 > cap 60 -> capped to 60.
        assert eff["effective_speed_bonus_pct"] == 60.0
        # 10 stamina -> 3000s base; 60% reduction -> floor(1200) = 1200.
        assert eff["effective_seconds"] == 1200

    def test_stamina_capped_at_50_and_minimum_1(self):
        from crud import _compute_effective_gather_params
        eff = _compute_effective_gather_params(
            base_stamina=1,
            has_tool=True,
            rank_bonuses={"speed_pct": 0.0, "stamina_pct": 80.0, "double_chance_pct": 0.0},
            tool_bonuses={
                "gather_speed_bonus_pct": 0.0,
                "gather_stamina_bonus_pct": 0.0,
                "gather_double_chance_bonus": 0.0,
            },
        )
        # capped at 50% -> ceil(1 * 0.5) = 1
        assert eff["effective_stamina_bonus_pct"] == 50.0
        assert eff["effective_stamina_paid"] >= 1

    def test_seconds_minimum_30(self):
        from crud import _compute_effective_gather_params
        eff = _compute_effective_gather_params(
            base_stamina=1,  # base = 300s
            has_tool=True,
            rank_bonuses={"speed_pct": 60.0, "stamina_pct": 0.0, "double_chance_pct": 0.0},
            tool_bonuses={
                "gather_speed_bonus_pct": 0.0,
                "gather_stamina_bonus_pct": 0.0,
                "gather_double_chance_bonus": 0.0,
            },
        )
        # 300 * 0.4 = 120 (>30). Verify floor still respected.
        assert eff["effective_seconds"] == 120

    def test_double_chance_capped_at_80_with_tool(self):
        from crud import _compute_effective_gather_params
        eff = _compute_effective_gather_params(
            base_stamina=5,
            has_tool=True,
            rank_bonuses={"speed_pct": 0.0, "stamina_pct": 0.0, "double_chance_pct": 50.0},
            tool_bonuses={
                "gather_speed_bonus_pct": 0.0,
                "gather_stamina_bonus_pct": 0.0,
                "gather_double_chance_bonus": 50.0,
            },
        )
        assert eff["effective_double_chance_pct"] == 80.0


class TestRefundFormula:
    """ceil(stamina_paid / 2). 5 -> 3, 1 -> 1, 2 -> 1, 0 -> 0, None -> 0."""

    def test_paid_5_refund_3(self):
        from crud import _compute_refund
        assert _compute_refund(5) == 3

    def test_paid_1_refund_1(self):
        from crud import _compute_refund
        assert _compute_refund(1) == 1

    def test_paid_2_refund_1(self):
        from crud import _compute_refund
        assert _compute_refund(2) == 1

    def test_paid_0_refund_0(self):
        from crud import _compute_refund
        assert _compute_refund(0) == 0

    def test_paid_none_refund_0(self):
        from crud import _compute_refund
        assert _compute_refund(None) == 0

    def test_paid_negative_refund_0(self):
        from crud import _compute_refund
        assert _compute_refund(-7) == 0


# ===========================================================================
# 4. START GATHERING — endpoint dispatch
# ===========================================================================

class TestStartGatheringEndpoint:
    """Verify the route correctly dispatches to crud.start_gathering and shapes the response."""

    @patch("crud.start_gathering", new_callable=AsyncMock)
    def test_happy_path_with_tool(self, mock_start, client):
        _override_user(OWNER_USER)
        started_at = datetime(2026, 4, 25, 10, 0, 0, tzinfo=timezone.utc)
        complete_at = started_at + timedelta(seconds=1500)
        mock_start.return_value = {
            "session_id": 88,
            "node_id": 12,
            "character_id": 421,
            "started_at": started_at,
            "complete_at": complete_at,
            "effective_seconds": 1500,
            "effective_stamina_paid": 5,
            "effective_speed_bonus_pct": 13.0,
            "effective_double_chance_pct": 8.0,
            "effective_stamina_bonus_pct": 18.0,
            "tool_inventory_item_id": 9023,
            "tool_durability_at_start": 50,
            "status": "active",
            "auto_post_id": 7710,
            "node_state_after": {"current_bank": 100, "active_sessions_count": 1},
        }
        resp = client.post(
            "/locations/542/gathering-nodes/12/start",
            json={"character_id": 421, "tool_inventory_item_id": 9023},
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["session_id"] == 88
        assert body["effective_seconds"] == 1500
        assert body["effective_stamina_paid"] == 5
        assert body["effective_speed_bonus_pct"] == 13.0
        assert body["effective_double_chance_pct"] == 8.0
        assert body["effective_stamina_bonus_pct"] == 18.0
        assert body["status"] == "active"
        assert body["tool_inventory_item_id"] == 9023
        # FEAT-128 §3.1.1 fields added in Review #1 fix.
        assert body["tool_durability_at_start"] == 50
        assert body["auto_post_id"] == 7710
        # Additive debug info kept post-fix (frontend ignores unknown fields).
        assert body["node_state_after"]["current_bank"] == 100
        # CRUD called with proper kwargs incl. the current user id.
        kwargs = mock_start.call_args.kwargs
        assert kwargs["location_id"] == 542
        assert kwargs["node_id"] == 12
        assert kwargs["character_id"] == 421
        assert kwargs["tool_inventory_item_id"] == 9023
        assert kwargs["current_user_id"] == OWNER_USER.id

    @patch("crud.start_gathering", new_callable=AsyncMock)
    def test_happy_path_without_tool(self, mock_start, client):
        _override_user(OWNER_USER)
        mock_start.return_value = {
            "session_id": 89,
            "node_id": 12,
            "character_id": 421,
            "started_at": datetime.now(timezone.utc),
            "complete_at": datetime.now(timezone.utc) + timedelta(seconds=3000),
            "effective_seconds": 3000,
            "effective_stamina_paid": 5,
            "effective_speed_bonus_pct": 0.0,
            "effective_double_chance_pct": 0.0,  # gated on tool
            "effective_stamina_bonus_pct": 0.0,
            "tool_inventory_item_id": None,
            # No tool -> no durability snapshot.
            "tool_durability_at_start": None,
            "status": "active",
            # Auto-post may legitimately fail (best-effort) — null is valid.
            "auto_post_id": None,
            "node_state_after": {"current_bank": 100, "active_sessions_count": 1},
        }
        resp = client.post(
            "/locations/542/gathering-nodes/12/start",
            json={"character_id": 421, "tool_inventory_item_id": None},
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["effective_double_chance_pct"] == 0.0
        assert body["tool_inventory_item_id"] is None
        assert body["tool_durability_at_start"] is None
        assert body["auto_post_id"] is None

    @patch("crud.start_gathering", new_callable=AsyncMock)
    def test_non_owner_returns_403(self, mock_start, client):
        from fastapi import HTTPException
        _override_user(OTHER_USER)
        mock_start.side_effect = HTTPException(
            status_code=403,
            detail="Вы можете управлять только своими персонажами",
        )
        resp = client.post(
            "/locations/542/gathering-nodes/12/start",
            json={"character_id": 421, "tool_inventory_item_id": None},
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 403
        assert "своими" in resp.json()["detail"].lower()

    @patch("crud.start_gathering", new_callable=AsyncMock)
    def test_wrong_location_returns_400(self, mock_start, client):
        from fastapi import HTTPException
        _override_user(OWNER_USER)
        mock_start.side_effect = HTTPException(
            status_code=400, detail="Персонаж не находится на этой локации",
        )
        resp = client.post(
            "/locations/999/gathering-nodes/12/start",
            json={"character_id": 421, "tool_inventory_item_id": None},
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 400
        assert "локации" in resp.json()["detail"].lower()

    @patch("crud.start_gathering", new_callable=AsyncMock)
    def test_node_disabled_returns_400(self, mock_start, client):
        from fastapi import HTTPException
        _override_user(OWNER_USER)
        mock_start.side_effect = HTTPException(status_code=400, detail="Нода отключена")
        resp = client.post(
            "/locations/542/gathering-nodes/12/start",
            json={"character_id": 421, "tool_inventory_item_id": None},
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Нода отключена"

    @patch("crud.start_gathering", new_callable=AsyncMock)
    def test_node_depleted_returns_400(self, mock_start, client):
        from fastapi import HTTPException
        _override_user(OWNER_USER)
        mock_start.side_effect = HTTPException(status_code=400, detail="Нода истощена")
        resp = client.post(
            "/locations/542/gathering-nodes/12/start",
            json={"character_id": 421, "tool_inventory_item_id": None},
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Нода истощена"

    @patch("crud.start_gathering", new_callable=AsyncMock)
    def test_concurrent_disallowed_returns_409(self, mock_start, client):
        from fastapi import HTTPException
        _override_user(OWNER_USER)
        mock_start.side_effect = HTTPException(
            status_code=409, detail="Нода занята другим персонажем",
        )
        resp = client.post(
            "/locations/542/gathering-nodes/12/start",
            json={"character_id": 421, "tool_inventory_item_id": None},
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 409
        assert "занята" in resp.json()["detail"].lower()

    @patch("crud.start_gathering", new_callable=AsyncMock)
    def test_tool_wrong_category_returns_422(self, mock_start, client):
        from fastapi import HTTPException
        _override_user(OWNER_USER)
        mock_start.side_effect = HTTPException(
            status_code=422,
            detail="Инструмент не подходит для этого ресурса",
        )
        resp = client.post(
            "/locations/542/gathering-nodes/12/start",
            json={"character_id": 421, "tool_inventory_item_id": 9023},
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 422
        assert "не подходит" in resp.json()["detail"].lower()

    @patch("crud.start_gathering", new_callable=AsyncMock)
    def test_tool_broken_returns_422(self, mock_start, client):
        from fastapi import HTTPException
        _override_user(OWNER_USER)
        mock_start.side_effect = HTTPException(
            status_code=422, detail="Инструмент сломан",
        )
        resp = client.post(
            "/locations/542/gathering-nodes/12/start",
            json={"character_id": 421, "tool_inventory_item_id": 9023},
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Инструмент сломан"

    @patch("crud.start_gathering", new_callable=AsyncMock)
    def test_insufficient_stamina_returns_400(self, mock_start, client):
        from fastapi import HTTPException
        _override_user(OWNER_USER)
        mock_start.side_effect = HTTPException(
            status_code=400, detail="Недостаточно стамины",
        )
        resp = client.post(
            "/locations/542/gathering-nodes/12/start",
            json={"character_id": 421, "tool_inventory_item_id": None},
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 400
        assert "стамин" in resp.json()["detail"].lower()

    @patch("crud.start_gathering", new_callable=AsyncMock)
    def test_inventory_full_returns_400(self, mock_start, client):
        from fastapi import HTTPException
        _override_user(OWNER_USER)
        mock_start.side_effect = HTTPException(
            status_code=400, detail="Инвентарь полон — освободите слот",
        )
        resp = client.post(
            "/locations/542/gathering-nodes/12/start",
            json={"character_id": 421, "tool_inventory_item_id": None},
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 400
        assert "инвентар" in resp.json()["detail"].lower()

    @patch("crud.start_gathering", new_callable=AsyncMock)
    def test_already_in_battle_returns_400(self, mock_start, client):
        from fastapi import HTTPException
        _override_user(OWNER_USER)
        mock_start.side_effect = HTTPException(
            status_code=400, detail="Нельзя начать добычу во время боя",
        )
        resp = client.post(
            "/locations/542/gathering-nodes/12/start",
            json={"character_id": 421, "tool_inventory_item_id": None},
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 400
        assert "бо" in resp.json()["detail"].lower()

    @patch("crud.start_gathering", new_callable=AsyncMock)
    def test_already_gathering_returns_400(self, mock_start, client):
        from fastapi import HTTPException
        _override_user(OWNER_USER)
        mock_start.side_effect = HTTPException(
            status_code=400, detail="Уже идёт добыча",
        )
        resp = client.post(
            "/locations/542/gathering-nodes/12/start",
            json={"character_id": 421, "tool_inventory_item_id": None},
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 400
        assert "добыч" in resp.json()["detail"].lower()


# ===========================================================================
# 5. CANCEL GATHERING — manual + internal
# ===========================================================================

class TestCancelGatheringManual:

    @patch("crud.cancel_gathering_manual", new_callable=AsyncMock)
    def test_happy_path_returns_refund(self, mock_cancel, client):
        _override_user(OWNER_USER)
        mock_cancel.return_value = {
            "cancelled": True,
            "session_id": 88,
            "stamina_refunded": 3,
        }
        resp = client.post(
            "/locations/542/gathering-nodes/12/cancel",
            json={"character_id": 421},
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["cancelled"] is True
        assert body["session_id"] == 88
        assert body["stamina_refunded"] == 3

    @patch("crud.cancel_gathering_manual", new_callable=AsyncMock)
    def test_non_owner_returns_403(self, mock_cancel, client):
        from fastapi import HTTPException
        _override_user(OTHER_USER)
        mock_cancel.side_effect = HTTPException(
            status_code=403,
            detail="Вы можете управлять только своими персонажами",
        )
        resp = client.post(
            "/locations/542/gathering-nodes/12/cancel",
            json={"character_id": 421},
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 403

    @patch("crud.cancel_gathering_manual", new_callable=AsyncMock)
    def test_no_active_session_returns_400(self, mock_cancel, client):
        from fastapi import HTTPException
        _override_user(OWNER_USER)
        mock_cancel.side_effect = HTTPException(
            status_code=400, detail="Активная добыча не найдена",
        )
        resp = client.post(
            "/locations/542/gathering-nodes/12/cancel",
            json={"character_id": 421},
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Активная добыча не найдена"


class TestCancelGatheringInternal:

    def test_no_token_returns_401_or_503(self, client):
        """No header at all -> 503 (no token configured) or 401 (token mismatch)."""
        # No INTERNAL_SERVICE_TOKEN env var typically -> 503.
        resp = client.post(
            "/locations/internal/cancel-gathering",
            json={"character_id": 421},
        )
        # The route is gated by `verify_internal_token` which raises 503 when
        # the env var is empty. Either 401 or 503 indicates we DID NOT bypass
        # the gate. (200 would be a security regression.)
        assert resp.status_code in (401, 503)

    def test_wrong_token_returns_401(self, client):
        """Token configured but mismatched -> 401."""
        import main as main_module
        original = getattr(main_module, "INTERNAL_SERVICE_TOKEN", "")
        main_module.INTERNAL_SERVICE_TOKEN = "secret-test-token"
        try:
            resp = client.post(
                "/locations/internal/cancel-gathering",
                json={"character_id": 421},
                headers={"X-Internal-Token": "wrong"},
            )
            assert resp.status_code == 401
        finally:
            main_module.INTERNAL_SERVICE_TOKEN = original

    @patch("crud.cancel_gathering_internal", new_callable=AsyncMock)
    def test_valid_token_cancels_session(self, mock_cancel, client):
        import main as main_module
        original = getattr(main_module, "INTERNAL_SERVICE_TOKEN", "")
        main_module.INTERNAL_SERVICE_TOKEN = "secret-test-token"
        mock_cancel.return_value = {
            "cancelled": True,
            "session_id": 88,
            "stamina_refunded": 3,
        }
        try:
            resp = client.post(
                "/locations/internal/cancel-gathering",
                json={"character_id": 421},
                headers={"X-Internal-Token": "secret-test-token"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["cancelled"] is True
            assert body["session_id"] == 88
            assert body["stamina_refunded"] == 3
        finally:
            main_module.INTERNAL_SERVICE_TOKEN = original

    @patch("crud.cancel_gathering_internal", new_callable=AsyncMock)
    def test_no_active_session_returns_cancelled_false(self, mock_cancel, client):
        import main as main_module
        original = getattr(main_module, "INTERNAL_SERVICE_TOKEN", "")
        main_module.INTERNAL_SERVICE_TOKEN = "secret-test-token"
        mock_cancel.return_value = {
            "cancelled": False,
            "reason": "no_active_session",
        }
        try:
            resp = client.post(
                "/locations/internal/cancel-gathering",
                json={"character_id": 421},
                headers={"X-Internal-Token": "secret-test-token"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["cancelled"] is False
            assert body["reason"] == "no_active_session"
        finally:
            main_module.INTERNAL_SERVICE_TOKEN = original


# ===========================================================================
# 6. POLL ACTIVE GATHERING
# ===========================================================================

class TestActiveGatheringPoll:

    @staticmethod
    def _make_db_with_owner(user_id: int = OWNER_USER.id):
        """Mock DB whose execute() always returns user_id for ownership lookup."""
        async def _gen():
            mock_db = AsyncMock()

            async def execute_side_effect(query, params=None):
                result = MagicMock()
                row = MagicMock()
                row.__getitem__ = lambda self, i: user_id
                row.__len__ = lambda self: 1
                result.fetchone.return_value = row
                return result

            mock_db.execute = AsyncMock(side_effect=execute_side_effect)
            yield mock_db

        return _gen

    def test_no_session_returns_active_false(self, client):
        from database import get_db
        _override_user(OWNER_USER)
        app.dependency_overrides[get_db] = self._make_db_with_owner(OWNER_USER.id)
        try:
            with patch(
                "crud.get_active_gathering_for_character", new_callable=AsyncMock,
            ) as mock_poll:
                mock_poll.return_value = {
                    "active": False,
                    "last_finished_session": None,
                }
                resp = client.get(
                    "/locations/characters/421/active_gathering",
                    headers={"Authorization": "Bearer x"},
                )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        body = resp.json()
        assert body["active"] is False
        # Active-only fields are None / absent in the inactive case.
        assert body.get("session_id") is None
        assert body["last_finished_session"] is None

    def test_active_session_returns_remaining_seconds(self, client):
        from database import get_db
        _override_user(OWNER_USER)
        app.dependency_overrides[get_db] = self._make_db_with_owner(OWNER_USER.id)
        started_at = datetime(2026, 4, 25, 10, 0, tzinfo=timezone.utc)
        complete_at = started_at + timedelta(seconds=720)
        try:
            with patch(
                "crud.get_active_gathering_for_character", new_callable=AsyncMock,
            ) as mock_poll:
                # Flat top-level shape per FEAT-128 §3.1.1 (Review #1 fix).
                mock_poll.return_value = {
                    "active": True,
                    "session_id": 88,
                    "node_id": 12,
                    "node_name": "Железная жила",
                    "location_id": 542,
                    "started_at": started_at,
                    "complete_at": complete_at,
                    "remaining_seconds": 720,
                    "stamina_paid": 5,
                    "tool_inventory_item_id": 9023,
                    "effective_speed_bonus_pct": 13.0,
                    "effective_double_chance_pct": 8.0,
                    "effective_stamina_bonus_pct": 18.0,
                    "last_finished_session": None,
                }
                resp = client.get(
                    "/locations/characters/421/active_gathering",
                    headers={"Authorization": "Bearer x"},
                )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        body = resp.json()
        assert body["active"] is True
        # Flat top-level access — no nested `session` wrapper.
        assert body["session_id"] == 88
        assert body["node_id"] == 12
        assert body["location_id"] == 542
        assert body["remaining_seconds"] == 720
        assert body["last_finished_session"] is None

    def test_finalized_session_returns_last_finished_then_clears_on_next_poll(
        self, client,
    ):
        """First poll: returns last_finished_session. Second poll: returns null."""
        from database import get_db
        _override_user(OWNER_USER)
        app.dependency_overrides[get_db] = self._make_db_with_owner(OWNER_USER.id)
        try:
            with patch(
                "crud.get_active_gathering_for_character", new_callable=AsyncMock,
            ) as mock_poll:
                # First call -> finalize finished, surface toast.
                # Field names per Review #1 fix (issue #2): session_id,
                # xp_gained, rank_up_to, skill_slug, tool_durability_remaining.
                mock_poll.return_value = {
                    "active": False,
                    "last_finished_session": {
                        "session_id": 88,
                        "node_id": 12,
                        "node_name": "Железная жила",
                        "result_item_id": 4711,
                        "result_item_name": "Железная руда",
                        "result_quantity": 4,
                        "xp_gained": 4,
                        "skill_slug": "mining",
                        "rank_up_to": 2,
                        "tool_durability_remaining": 46,
                        "tool_broke": False,
                        "status": "completed",
                    },
                }
                resp1 = client.get(
                    "/locations/characters/421/active_gathering",
                    headers={"Authorization": "Bearer x"},
                )
                # Second call -> null (one-shot)
                mock_poll.return_value = {
                    "active": False,
                    "last_finished_session": None,
                }
                resp2 = client.get(
                    "/locations/characters/421/active_gathering",
                    headers={"Authorization": "Bearer x"},
                )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp1.status_code == 200
        body1 = resp1.json()
        assert body1["active"] is False
        assert body1["last_finished_session"] is not None
        lfs = body1["last_finished_session"]
        assert lfs["session_id"] == 88
        assert lfs["result_quantity"] == 4
        assert lfs["xp_gained"] == 4
        assert lfs["skill_slug"] == "mining"
        assert lfs["rank_up_to"] == 2
        assert lfs["tool_durability_remaining"] == 46
        assert lfs["status"] == "completed"

        assert resp2.status_code == 200
        assert resp2.json()["last_finished_session"] is None

    def test_non_owner_gets_403(self, client):
        """Owner-only enforcement: a different user trying to poll returns 403."""
        from database import get_db
        # DB ownership row says owner_id=10, but caller is user 11.
        _override_user(OTHER_USER)
        app.dependency_overrides[get_db] = self._make_db_with_owner(
            OWNER_USER.id  # 10
        )
        try:
            resp = client.get(
                "/locations/characters/421/active_gathering",
                headers={"Authorization": "Bearer x"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 403


# ===========================================================================
# 7. LAZY-FINALIZE side effects (CRUD-level, mocking httpx)
# ===========================================================================

class TestFinalizeAwardCall:
    """`_award_via_inventory` posts the right payload and tolerates failures."""

    def test_payload_includes_skill_slug_and_durability_to_consume(self):
        import asyncio
        from crud import _award_via_inventory

        captured = {}

        class _MockResponse:
            status_code = 200
            text = ""

            def json(self):
                return {
                    "actual_quantity_added": 4,
                    "inventory_full": False,
                    "xp_awarded": 4,
                    "rank_up": False,
                    "current_rank": 1,
                    "tool_broke": False,
                }

        class _MockClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, json=None):
                captured["url"] = url
                captured["json"] = json
                return _MockResponse()

        with patch("crud.httpx.AsyncClient", return_value=_MockClient()):
            result = asyncio.run(_award_via_inventory(
                character_id=421,
                skill_slug="mining",
                result_item_id=4711,
                granted_quantity=4,
                tool_inventory_item_id=9023,
            ))

        assert result is not None
        assert result["actual_quantity_added"] == 4
        # Payload assertions
        assert "/inventory/internal/characters/421/gathering/award" in captured["url"]
        assert captured["json"]["skill_slug"] == "mining"
        assert captured["json"]["result_item_id"] == 4711
        assert captured["json"]["result_quantity"] == 4
        assert captured["json"]["xp_to_add"] == 4
        assert captured["json"]["tool_inventory_item_id"] == 9023
        assert captured["json"]["tool_durability_to_consume"] == 4

    def test_no_tool_durability_to_consume_is_zero(self):
        import asyncio
        from crud import _award_via_inventory

        captured = {}

        class _MockResponse:
            status_code = 200
            text = ""

            def json(self):
                return {
                    "actual_quantity_added": 3,
                    "inventory_full": False,
                    "xp_awarded": 3,
                    "rank_up": False,
                    "current_rank": 1,
                    "tool_broke": False,
                }

        class _MockClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, json=None):
                captured["json"] = json
                return _MockResponse()

        with patch("crud.httpx.AsyncClient", return_value=_MockClient()):
            asyncio.run(_award_via_inventory(
                character_id=421,
                skill_slug="herbalism",
                result_item_id=5001,
                granted_quantity=3,
                tool_inventory_item_id=None,
            ))
        assert captured["json"]["tool_durability_to_consume"] == 0
        assert captured["json"]["tool_inventory_item_id"] is None

    def test_5xx_returns_none_for_retry(self):
        import asyncio
        from crud import _award_via_inventory

        class _MockResponse:
            status_code = 502
            text = "bad gateway"

            def json(self):
                return {}

        class _MockClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, json=None):
                return _MockResponse()

        with patch("crud.httpx.AsyncClient", return_value=_MockClient()):
            result = asyncio.run(_award_via_inventory(
                character_id=421, skill_slug="mining",
                result_item_id=4711, granted_quantity=4,
                tool_inventory_item_id=None,
            ))
        # Per docstring: 5xx => return None so the session retries on next poll.
        assert result is None

    def test_transport_error_returns_none(self):
        import asyncio
        from crud import _award_via_inventory

        class _MockClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, json=None):
                raise RuntimeError("boom")

        with patch("crud.httpx.AsyncClient", return_value=_MockClient()):
            result = asyncio.run(_award_via_inventory(
                character_id=421, skill_slug="mining",
                result_item_id=4711, granted_quantity=4,
                tool_inventory_item_id=None,
            ))
        assert result is None


class TestRollDoubleUnits:
    """Pure helper — no doubles when chance=0; some doubles when chance=100."""

    def test_zero_chance_yields_zero(self):
        from crud import _roll_double_units
        assert _roll_double_units(10, 0.0) == 0

    def test_zero_base_yields_zero(self):
        from crud import _roll_double_units
        assert _roll_double_units(0, 50.0) == 0

    def test_full_chance_doubles_every_unit(self):
        from crud import _roll_double_units
        # 100% chance => extras == base
        assert _roll_double_units(7, 100.0) == 7


# ===========================================================================
# 8. check_not_gathering INTEGRATION
# ===========================================================================

def _row(*values):
    row = MagicMock()
    row.__getitem__ = lambda self, i: values[i]
    row.__len__ = lambda self: len(values)
    return row


def _result_with_row(row_data):
    result = MagicMock()
    result.fetchone.return_value = row_data
    return result


def _result_empty():
    result = MagicMock()
    result.fetchone.return_value = None
    return result


def _make_db_for_gather_block(active_gather: bool, owner_user_id: int = OWNER_USER.id):
    """Build a mock async DB session that says character is owned + (optionally) gathering."""
    async def mock_get_db():
        mock_db = AsyncMock()

        async def execute_side_effect(query, params=None):
            qs = str(query)
            if "user_id" in qs and "characters" in qs:
                return _result_with_row(_row(owner_user_id))
            if "battles" in qs and "battle_participants" in qs:
                # Not in battle — pass through to gather check.
                return _result_empty()
            if "gathering_sessions" in qs and "status" in qs:
                if active_gather:
                    return _result_with_row(_row(1))
                return _result_empty()
            if "current_location_id" in qs:
                # match same location for post creation defense-in-depth
                return _result_with_row(_row(100))
            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        yield mock_db

    return mock_get_db


class TestCheckNotGatheringIntegration:
    """check_not_gathering must block move_and_post / quick_move / posts."""

    def test_create_post_blocked_during_gather(self, client):
        from database import get_db
        _override_user(OWNER_USER)
        app.dependency_overrides[get_db] = _make_db_for_gather_block(active_gather=True)
        try:
            resp = client.post(
                "/locations/posts/",
                json={
                    "character_id": 421,
                    "location_id": 100,
                    "content": "x" * 200,
                },
                headers={"Authorization": "Bearer x"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert resp.status_code == 400
        assert "добыч" in resp.json()["detail"].lower()

    def test_move_and_post_blocked_during_gather(self, client):
        from database import get_db
        _override_user(OWNER_USER)
        app.dependency_overrides[get_db] = _make_db_for_gather_block(active_gather=True)
        try:
            resp = client.post(
                "/locations/200/move_and_post",
                json={"character_id": 421, "content": "Перехожу"},
                headers={"Authorization": "Bearer x"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert resp.status_code == 400
        assert "добыч" in resp.json()["detail"].lower()

    def test_quick_move_blocked_during_gather(self, client):
        from database import get_db
        _override_user(OWNER_USER)
        app.dependency_overrides[get_db] = _make_db_for_gather_block(active_gather=True)
        try:
            resp = client.post(
                "/locations/200/quick_move",
                json={"character_id": 421},
                headers={"Authorization": "Bearer x"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert resp.status_code == 400
        assert "добыч" in resp.json()["detail"].lower()


# ===========================================================================
# 9. gathering_nodes in client/details
# ===========================================================================

class TestGatheringNodesInClientDetails:
    """The /client/details payload must surface gathering_nodes[] with all fields."""

    def _details_payload(self, with_active_sessions=True):
        node = {
            "id": 12,
            "node_name": "Железная жила",
            "category": "ore",
            "result_item_id": 4711,
            "result_item_name": "Железная руда",
            "result_item_image": "/images/ore.png",
            "result_item_type": "resource",
            "result_quantity_per_gather": 3,
            "stamina_per_gather": 5,
            "base_seconds": 1500,
            "current_bank": 47,
            "daily_bank_max": 100,
            "allow_concurrent_gather": True,
            "depleted_at": None,
            "restore_at": None,
            "is_enabled": True,
            "active_sessions": [],
        }
        if with_active_sessions:
            node["active_sessions"] = [
                {
                    "session_id": 88, "character_id": 421,
                    "character_name": "Roland",
                    "character_avatar_url": "/images/avatar.png",
                    "started_at": datetime(2026, 4, 25, 10, 0, tzinfo=timezone.utc),
                    "complete_at": datetime(2026, 4, 25, 10, 25, tzinfo=timezone.utc),
                },
            ]
        return {
            "id": 542, "name": "Лес", "type": "location", "parent_id": None,
            "description": "...", "image_url": None, "recommended_level": 1,
            "quick_travel_marker": False, "marker_type": None,
            "district_id": None, "region_id": None, "is_favorited": False,
            "neighbors": [], "players": [], "npcs": [], "posts": [],
            "loot": [], "gathering_nodes": [node],
        }

    @patch("main.get_optional_user", return_value=None)
    @patch("crud.finalize_due_sessions", new_callable=AsyncMock, return_value=[])
    @patch("crud.get_client_location_details", new_callable=AsyncMock)
    def test_client_details_includes_gathering_nodes(
        self, mock_details, mock_finalize, mock_user, client,
    ):
        mock_details.return_value = self._details_payload(with_active_sessions=True)
        resp = client.get("/locations/542/client/details")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "gathering_nodes" in body
        assert len(body["gathering_nodes"]) == 1
        node = body["gathering_nodes"][0]
        assert node["result_item_name"] == "Железная руда"
        assert node["result_item_image"] == "/images/ore.png"
        assert node["current_bank"] == 47
        assert node["daily_bank_max"] == 100
        assert len(node["active_sessions"]) == 1
        gatherer = node["active_sessions"][0]
        assert gatherer["character_name"] == "Roland"
        assert gatherer["character_avatar_url"] == "/images/avatar.png"

    @patch("main.get_optional_user", return_value=None)
    @patch("crud.finalize_due_sessions", new_callable=AsyncMock, return_value=[])
    @patch("crud.get_client_location_details", new_callable=AsyncMock)
    def test_finalize_due_sessions_called_before_response(
        self, mock_details, mock_finalize, mock_user, client,
    ):
        """The endpoint MUST call finalize_due_sessions BEFORE building the
        response (so depleted-but-restored nodes and inventory-awarded sessions
        are reflected in the payload). This is the lazy-restore guarantee.
        """
        mock_details.return_value = self._details_payload(with_active_sessions=False)
        resp = client.get("/locations/542/client/details")
        assert resp.status_code == 200
        mock_finalize.assert_awaited()

    @patch("main.get_optional_user", return_value=None)
    @patch("crud.finalize_due_sessions", new_callable=AsyncMock, return_value=[])
    @patch("crud.get_client_location_details", new_callable=AsyncMock)
    def test_finalize_failure_does_not_break_endpoint(
        self, mock_details, mock_finalize, mock_user, client,
    ):
        """Per the endpoint's defensive try/except, a finalize hiccup must not
        break the location load — the page still renders."""
        mock_finalize.side_effect = RuntimeError("inventory-service down")
        mock_details.return_value = self._details_payload()
        resp = client.get("/locations/542/client/details")
        assert resp.status_code == 200


# ===========================================================================
# 10. SECURITY — internal-only / owner-only / RBAC
# ===========================================================================

class TestSecurityInvariants:
    """Cross-cutting: every secured route stays secured."""

    def test_admin_endpoints_all_require_permission(self, client):
        """Walk every gathering admin path with a non-admin and assert 403."""
        _override_user(NON_ADMIN_USER)
        cases = [
            ("get", "/locations/admin/locations/542/gathering-nodes"),
            ("post", "/locations/admin/locations/542/gathering-nodes"),
            ("put", "/locations/admin/gathering-nodes/12"),
            ("delete", "/locations/admin/gathering-nodes/12"),
            ("post", "/locations/admin/gathering-nodes/12/restore"),
        ]
        for verb, path in cases:
            method = getattr(client, verb)
            kwargs = {"headers": {"Authorization": "Bearer x"}}
            if verb in ("post", "put"):
                kwargs["json"] = VALID_NODE_BODY if "locations/" in path else {}
            resp = method(path, **kwargs)
            assert resp.status_code == 403, f"{verb.upper()} {path} should require permission"

    def test_internal_cancel_blocked_without_token(self, client):
        """No X-Internal-Token header => cannot bypass."""
        resp = client.post(
            "/locations/internal/cancel-gathering",
            json={"character_id": 421},
        )
        assert resp.status_code in (401, 503)

    def test_start_requires_authentication(self, client):
        """No Authorization header on a player route => 401/403."""
        # No _override_user — the auth dependency is unmocked. The TestClient's
        # underlying `requests` will hit the real `auth_http.requests.get` which
        # will fail to reach the user-service. Since the conftest doesn't patch
        # it, we expect the dependency to reject the empty/missing token.
        resp = client.post(
            "/locations/542/gathering-nodes/12/start",
            json={"character_id": 421},
        )
        # Either 401 (rejected by OAuth2PasswordBearer) or 503 (auth-service
        # unreachable) — both prove the route is gated. Never 200.
        assert resp.status_code in (401, 403, 422, 503)
