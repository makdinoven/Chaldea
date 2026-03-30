# test_room_positions.py - Tests for room position fields and bulk position update endpoint.
import pytest
from helpers import _dungeon_payload, _room_payload

pytestmark = pytest.mark.asyncio


# ===========================
#  Room create/update WITH positions
# ===========================

async def test_create_room_with_positions(admin_client, created_dungeon):
    """POST room with position_x and position_y — values are stored and returned."""
    dungeon_id = created_dungeon["id"]
    payload = _room_payload("battle", name="Positioned Room", position_x=100.5, position_y=200.0)
    resp = await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
        json=payload,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["position_x"] == 100.5
    assert data["position_y"] == 200.0


async def test_create_room_without_positions(admin_client, created_dungeon):
    """POST room without position_x/position_y — both are null."""
    dungeon_id = created_dungeon["id"]
    payload = _room_payload("battle", name="No Position Room")
    resp = await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
        json=payload,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["position_x"] is None
    assert data["position_y"] is None


async def test_update_room_positions(admin_client, dungeon_with_rooms):
    """PUT /dungeons/admin/rooms/{id} — update position_x and position_y."""
    room_id = dungeon_with_rooms["battle_room"]["id"]
    resp = await admin_client.put(
        "/dungeons/admin/rooms/%d" % room_id,
        json={"position_x": 300.0, "position_y": 450.5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["position_x"] == 300.0
    assert data["position_y"] == 450.5
    # Other fields unchanged
    assert data["name"] == "Battle Room"


async def test_update_room_clear_positions(admin_client, created_dungeon):
    """PUT room with positions then clear them back to null."""
    dungeon_id = created_dungeon["id"]
    # Create with positions
    payload = _room_payload("rest", name="Rest Room", position_x=10.0, position_y=20.0)
    create_resp = await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
        json=payload,
    )
    assert create_resp.status_code == 201
    room_id = create_resp.json()["id"]

    # Update to null
    resp = await admin_client.put(
        "/dungeons/admin/rooms/%d" % room_id,
        json={"position_x": None, "position_y": None},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["position_x"] is None
    assert data["position_y"] is None


async def test_positions_returned_in_dungeon_detail(admin_client, created_dungeon):
    """GET dungeon detail includes position_x/position_y in room objects."""
    dungeon_id = created_dungeon["id"]
    await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
        json=_room_payload("fork", name="Entry", is_entrance=True, position_x=0.0, position_y=0.0),
    )
    await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
        json=_room_payload("boss", name="Boss", is_boss_room=True, position_x=200.0, position_y=200.0),
    )

    resp = await admin_client.get("/dungeons/admin/dungeons/%d" % dungeon_id)
    assert resp.status_code == 200
    rooms = resp.json()["rooms"]
    assert len(rooms) == 2
    for room in rooms:
        assert "position_x" in room
        assert "position_y" in room
        assert room["position_x"] is not None
        assert room["position_y"] is not None


# ===========================
#  Bulk position update — happy path
# ===========================

async def test_bulk_update_positions_happy(admin_client, dungeon_with_rooms):
    """PUT bulk positions — all rooms updated, returns correct count."""
    dungeon_id = dungeon_with_rooms["dungeon"]["id"]
    entrance_id = dungeon_with_rooms["entrance"]["id"]
    battle_id = dungeon_with_rooms["battle_room"]["id"]
    boss_id = dungeon_with_rooms["boss_room"]["id"]

    payload = {
        "positions": [
            {"room_id": entrance_id, "position_x": 0.0, "position_y": 0.0},
            {"room_id": battle_id, "position_x": 200.0, "position_y": 0.0},
            {"room_id": boss_id, "position_x": 400.0, "position_y": 0.0},
        ]
    }
    resp = await admin_client.put(
        "/dungeons/admin/dungeons/%d/rooms/positions" % dungeon_id,
        json=payload,
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] == 3

    # Verify via dungeon detail
    detail = await admin_client.get("/dungeons/admin/dungeons/%d" % dungeon_id)
    rooms_by_id = {r["id"]: r for r in detail.json()["rooms"]}
    assert rooms_by_id[entrance_id]["position_x"] == 0.0
    assert rooms_by_id[entrance_id]["position_y"] == 0.0
    assert rooms_by_id[battle_id]["position_x"] == 200.0
    assert rooms_by_id[boss_id]["position_x"] == 400.0


async def test_bulk_update_positions_single_room(admin_client, dungeon_with_rooms):
    """PUT bulk positions — works with a single room."""
    dungeon_id = dungeon_with_rooms["dungeon"]["id"]
    entrance_id = dungeon_with_rooms["entrance"]["id"]

    payload = {
        "positions": [
            {"room_id": entrance_id, "position_x": 50.0, "position_y": 75.0},
        ]
    }
    resp = await admin_client.put(
        "/dungeons/admin/dungeons/%d/rooms/positions" % dungeon_id,
        json=payload,
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] == 1


# ===========================
#  Bulk position update — error cases
# ===========================

async def test_bulk_update_dungeon_not_found(admin_client):
    """PUT bulk positions for nonexistent dungeon — 404."""
    payload = {
        "positions": [
            {"room_id": 1, "position_x": 0.0, "position_y": 0.0},
        ]
    }
    resp = await admin_client.put(
        "/dungeons/admin/dungeons/99999/rooms/positions",
        json=payload,
    )
    assert resp.status_code == 404


async def test_bulk_update_room_not_in_dungeon(admin_client, dungeon_with_rooms):
    """PUT bulk positions with room_id from another dungeon — 400."""
    # Create a second dungeon with its own room
    d2_resp = await admin_client.post(
        "/dungeons/admin/dungeons",
        json=_dungeon_payload(name="Other Dungeon"),
    )
    d2_id = d2_resp.json()["id"]
    r2_resp = await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % d2_id,
        json=_room_payload("fork", name="Other Room"),
    )
    other_room_id = r2_resp.json()["id"]

    # Try to update the other dungeon's room as if it belonged to the first dungeon
    dungeon_id = dungeon_with_rooms["dungeon"]["id"]
    payload = {
        "positions": [
            {"room_id": other_room_id, "position_x": 0.0, "position_y": 0.0},
        ]
    }
    resp = await admin_client.put(
        "/dungeons/admin/dungeons/%d/rooms/positions" % dungeon_id,
        json=payload,
    )
    assert resp.status_code == 400


async def test_bulk_update_room_not_found(admin_client, created_dungeon):
    """PUT bulk positions with nonexistent room_id — 400."""
    dungeon_id = created_dungeon["id"]
    payload = {
        "positions": [
            {"room_id": 99999, "position_x": 0.0, "position_y": 0.0},
        ]
    }
    resp = await admin_client.put(
        "/dungeons/admin/dungeons/%d/rooms/positions" % dungeon_id,
        json=payload,
    )
    assert resp.status_code == 400


async def test_bulk_update_empty_positions(admin_client, created_dungeon):
    """PUT bulk positions with empty list — 422 (Pydantic validation)."""
    dungeon_id = created_dungeon["id"]
    payload = {"positions": []}
    resp = await admin_client.put(
        "/dungeons/admin/dungeons/%d/rooms/positions" % dungeon_id,
        json=payload,
    )
    assert resp.status_code == 422


# ===========================
#  Bulk position update — auth
# ===========================

async def test_bulk_update_positions_requires_auth(no_auth_client, db_session):
    """PUT bulk positions without admin auth — 401/403."""
    payload = {
        "positions": [
            {"room_id": 1, "position_x": 0.0, "position_y": 0.0},
        ]
    }
    resp = await no_auth_client.put(
        "/dungeons/admin/dungeons/1/rooms/positions",
        json=payload,
    )
    assert resp.status_code in (401, 403, 422)


# ===========================
#  Regression — existing room CRUD still works
# ===========================

async def test_regression_create_room_without_positions(admin_client, created_dungeon):
    """Regression: creating a room without position fields still works."""
    dungeon_id = created_dungeon["id"]
    payload = {
        "room_type": "battle",
        "name": "Legacy Room",
        "description": "Created without positions",
        "sort_order": 0,
        "is_entrance": False,
        "is_boss_room": False,
        "is_mana_core_room": False,
        "room_config": None,
    }
    resp = await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
        json=payload,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Legacy Room"
    assert data["position_x"] is None
    assert data["position_y"] is None


async def test_regression_update_room_without_positions(admin_client, dungeon_with_rooms):
    """Regression: updating room name without touching positions still works."""
    room_id = dungeon_with_rooms["battle_room"]["id"]
    resp = await admin_client.put(
        "/dungeons/admin/rooms/%d" % room_id,
        json={"name": "Renamed Room"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Renamed Room"
    # Positions remain null (were never set)
    assert data.get("position_x") is None
    assert data.get("position_y") is None


async def test_regression_room_config_update_with_positions(admin_client, created_dungeon):
    """Regression: updating room_config alongside positions works correctly."""
    dungeon_id = created_dungeon["id"]
    # Create room with positions
    create_resp = await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
        json=_room_payload(
            "battle", name="Config Room",
            position_x=50.0, position_y=50.0,
            room_config={"mob_template_ids": [1]},
        ),
    )
    assert create_resp.status_code == 201
    room_id = create_resp.json()["id"]

    # Update both config and positions
    resp = await admin_client.put(
        "/dungeons/admin/rooms/%d" % room_id,
        json={
            "room_config": {"mob_template_ids": [1, 2, 3]},
            "position_x": 150.0,
            "position_y": 250.0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["room_config"] == {"mob_template_ids": [1, 2, 3]}
    assert data["position_x"] == 150.0
    assert data["position_y"] == 250.0
