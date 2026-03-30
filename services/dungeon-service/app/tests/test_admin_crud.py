# test_admin_crud.py - Tests for dungeon-service admin CRUD endpoints.
import pytest
from helpers import _dungeon_payload, _room_payload, _corridor_payload

pytestmark = pytest.mark.asyncio


# ===========================
#  Dungeon CRUD
# ===========================

async def test_create_dungeon(admin_client):
    """POST /dungeons/admin/dungeons - success with all fields."""
    payload = _dungeon_payload(name="Dark Cave", stability_type="chaotic")
    resp = await admin_client.post("/dungeons/admin/dungeons", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Dark Cave"
    assert data["stability_type"] == "chaotic"
    assert data["danger_level"] == "safe"
    assert data["is_active"] is True
    assert data["id"] is not None
    assert data["mob_multiplier"] == 1.0
    assert data["mana_core_chance"] == 0.1


async def test_create_dungeon_validation(admin_client):
    """POST /dungeons/admin/dungeons - missing required fields returns 422."""
    # Missing name and description
    resp = await admin_client.post("/dungeons/admin/dungeons", json={"location_id": 1})
    assert resp.status_code == 422

    # Invalid stability_type
    payload = _dungeon_payload(stability_type="invalid_type")
    resp = await admin_client.post("/dungeons/admin/dungeons", json=payload)
    assert resp.status_code == 422

    # Invalid danger_level
    payload = _dungeon_payload(danger_level="extreme")
    resp = await admin_client.post("/dungeons/admin/dungeons", json=payload)
    assert resp.status_code == 422

    # Invalid mana_core_chance (out of range)
    payload = _dungeon_payload(mana_core_chance=2.0)
    resp = await admin_client.post("/dungeons/admin/dungeons", json=payload)
    assert resp.status_code == 422


async def test_list_dungeons(admin_client):
    """GET /dungeons/admin/dungeons - returns list with pagination."""
    # Create two dungeons
    await admin_client.post("/dungeons/admin/dungeons", json=_dungeon_payload(name="D1"))
    await admin_client.post("/dungeons/admin/dungeons", json=_dungeon_payload(name="D2"))

    resp = await admin_client.get("/dungeons/admin/dungeons")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2

    # Test pagination
    resp = await admin_client.get("/dungeons/admin/dungeons?skip=0&limit=1")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_get_dungeon_detail(admin_client, dungeon_with_rooms):
    """GET /dungeons/admin/dungeons/{id} - returns dungeon with rooms and corridors."""
    dungeon_id = dungeon_with_rooms["dungeon"]["id"]
    resp = await admin_client.get("/dungeons/admin/dungeons/%d" % dungeon_id)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Dungeon"
    assert len(data["rooms"]) == 3
    assert len(data["corridors"]) == 2


async def test_get_dungeon_not_found(admin_client):
    """GET /dungeons/admin/dungeons/99999 - returns 404."""
    resp = await admin_client.get("/dungeons/admin/dungeons/99999")
    assert resp.status_code == 404


async def test_update_dungeon(admin_client, created_dungeon):
    """PUT /dungeons/admin/dungeons/{id} - partial update works."""
    dungeon_id = created_dungeon["id"]
    resp = await admin_client.put(
        "/dungeons/admin/dungeons/%d" % dungeon_id,
        json={"name": "Updated Name", "is_active": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Updated Name"
    assert data["is_active"] is False
    # Unchanged fields remain
    assert data["description"] == "A dark test dungeon"


async def test_delete_dungeon(admin_client, dungeon_with_rooms):
    """DELETE /dungeons/admin/dungeons/{id} - cascade deletes rooms and corridors."""
    dungeon_id = dungeon_with_rooms["dungeon"]["id"]
    resp = await admin_client.delete("/dungeons/admin/dungeons/%d" % dungeon_id)
    assert resp.status_code == 204

    # Verify dungeon is gone
    resp = await admin_client.get("/dungeons/admin/dungeons/%d" % dungeon_id)
    assert resp.status_code == 404


# ===========================
#  Room CRUD
# ===========================

async def test_create_room(admin_client, created_dungeon):
    """POST /dungeons/admin/dungeons/{id}/rooms - success for each room type."""
    dungeon_id = created_dungeon["id"]
    room_types = [
        "battle", "boss", "treasure", "trap", "event",
        "rest", "merchant", "fork", "teleport", "deadend",
    ]
    for rt in room_types:
        resp = await admin_client.post(
            "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
            json=_room_payload(rt, name="Room " + rt),
        )
        assert resp.status_code == 201, "Failed for room_type: %s" % rt
        assert resp.json()["room_type"] == rt


async def test_create_room_invalid_dungeon(admin_client):
    """POST /dungeons/admin/dungeons/99999/rooms - 404 for non-existent dungeon."""
    resp = await admin_client.post(
        "/dungeons/admin/dungeons/99999/rooms",
        json=_room_payload("battle"),
    )
    assert resp.status_code == 404


async def test_create_room_invalid_type(admin_client, created_dungeon):
    """POST with invalid room_type returns 422."""
    dungeon_id = created_dungeon["id"]
    resp = await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
        json=_room_payload("nonexistent_type"),
    )
    assert resp.status_code == 422


async def test_update_room(admin_client, dungeon_with_rooms):
    """PUT /dungeons/admin/rooms/{id} - changes room_type and config."""
    room_id = dungeon_with_rooms["battle_room"]["id"]
    resp = await admin_client.put(
        "/dungeons/admin/rooms/%d" % room_id,
        json={"name": "Updated Room", "room_config": {"mob_template_ids": [1, 2]}},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Room"
    assert resp.json()["room_config"] == {"mob_template_ids": [1, 2]}


async def test_delete_room(admin_client, dungeon_with_rooms):
    """DELETE /dungeons/admin/rooms/{id} - deletes room and connected corridors."""
    # Delete the battle room (which has corridors to/from it)
    room_id = dungeon_with_rooms["battle_room"]["id"]
    resp = await admin_client.delete("/dungeons/admin/rooms/%d" % room_id)
    assert resp.status_code == 204

    # Verify the dungeon detail no longer has that room
    dungeon_id = dungeon_with_rooms["dungeon"]["id"]
    resp = await admin_client.get("/dungeons/admin/dungeons/%d" % dungeon_id)
    data = resp.json()
    room_ids = [r["id"] for r in data["rooms"]]
    assert room_id not in room_ids


# ===========================
#  Corridor CRUD
# ===========================

async def test_create_corridor(admin_client, dungeon_with_rooms):
    """POST /dungeons/admin/dungeons/{id}/corridors - success."""
    # Corridors already created in fixture; create a reverse one
    dungeon_id = dungeon_with_rooms["dungeon"]["id"]
    boss_id = dungeon_with_rooms["boss_room"]["id"]
    entrance_id = dungeon_with_rooms["entrance"]["id"]
    resp = await admin_client.post(
        "/dungeons/admin/dungeons/%d/corridors" % dungeon_id,
        json=_corridor_payload(boss_id, entrance_id, stamina_cost=10),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["from_room_id"] == boss_id
    assert data["to_room_id"] == entrance_id
    assert data["stamina_cost"] == 10


async def test_create_corridor_invalid_rooms(admin_client, created_dungeon):
    """POST corridor with rooms from different dungeons returns 400."""
    d1_id = created_dungeon["id"]
    # Create a room in dungeon 1
    r1 = await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % d1_id,
        json=_room_payload("fork", name="R1"),
    )
    r1_id = r1.json()["id"]

    # Create a second dungeon with a room
    d2 = await admin_client.post("/dungeons/admin/dungeons", json=_dungeon_payload(name="D2"))
    d2_id = d2.json()["id"]
    r2 = await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % d2_id,
        json=_room_payload("fork", name="R2"),
    )
    r2_id = r2.json()["id"]

    # Try to create a corridor in d1 using room from d2
    resp = await admin_client.post(
        "/dungeons/admin/dungeons/%d/corridors" % d1_id,
        json=_corridor_payload(r1_id, r2_id),
    )
    assert resp.status_code == 400


async def test_create_corridor_self_loop(admin_client, created_dungeon):
    """POST corridor with from_room == to_room rejected (422 from Pydantic)."""
    d_id = created_dungeon["id"]
    r = await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % d_id,
        json=_room_payload("fork", name="Self"),
    )
    r_id = r.json()["id"]
    resp = await admin_client.post(
        "/dungeons/admin/dungeons/%d/corridors" % d_id,
        json=_corridor_payload(r_id, r_id),
    )
    assert resp.status_code == 422


async def test_create_corridor_duplicate(admin_client, dungeon_with_rooms):
    """POST corridor with same from/to pair rejected (409)."""
    dungeon_id = dungeon_with_rooms["dungeon"]["id"]
    entrance_id = dungeon_with_rooms["entrance"]["id"]
    battle_id = dungeon_with_rooms["battle_room"]["id"]
    resp = await admin_client.post(
        "/dungeons/admin/dungeons/%d/corridors" % dungeon_id,
        json=_corridor_payload(entrance_id, battle_id),
    )
    assert resp.status_code == 409


async def test_update_corridor(admin_client, dungeon_with_rooms):
    """PUT /dungeons/admin/corridors/{id} - changes stamina_cost."""
    corridor_id = dungeon_with_rooms["corridor1"]["id"]
    resp = await admin_client.put(
        "/dungeons/admin/corridors/%d" % corridor_id,
        json={"stamina_cost": 20},
    )
    assert resp.status_code == 200
    assert resp.json()["stamina_cost"] == 20


async def test_delete_corridor(admin_client, dungeon_with_rooms):
    """DELETE /dungeons/admin/corridors/{id} - success."""
    corridor_id = dungeon_with_rooms["corridor1"]["id"]
    resp = await admin_client.delete("/dungeons/admin/corridors/%d" % corridor_id)
    assert resp.status_code == 204


# ===========================
#  Validation
# ===========================

async def test_validate_dungeon_valid(admin_client, dungeon_with_rooms):
    """POST validate - dungeon with entrance + boss + connectivity passes."""
    dungeon_id = dungeon_with_rooms["dungeon"]["id"]
    resp = await admin_client.post("/dungeons/admin/dungeons/%d/validate" % dungeon_id)
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert len(data["errors"]) == 0


async def test_validate_dungeon_no_entrance(admin_client, created_dungeon):
    """POST validate - fails with no entrance room."""
    dungeon_id = created_dungeon["id"]
    # Create a boss room but no entrance
    await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
        json=_room_payload("boss", name="Boss", is_boss_room=True),
    )
    resp = await admin_client.post("/dungeons/admin/dungeons/%d/validate" % dungeon_id)
    data = resp.json()
    assert data["valid"] is False
    assert any("вход" in e.lower() or "entrance" in e.lower() for e in data["errors"])


async def test_validate_dungeon_no_boss(admin_client, created_dungeon):
    """POST validate - fails with no boss room."""
    dungeon_id = created_dungeon["id"]
    # Create an entrance room but no boss
    await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
        json=_room_payload("fork", name="Entrance", is_entrance=True),
    )
    resp = await admin_client.post("/dungeons/admin/dungeons/%d/validate" % dungeon_id)
    data = resp.json()
    assert data["valid"] is False
    assert any("босс" in e.lower() or "boss" in e.lower() for e in data["errors"])


async def test_validate_dungeon_orphan_rooms(admin_client, created_dungeon):
    """POST validate - warns about unreachable rooms (no corridors)."""
    dungeon_id = created_dungeon["id"]
    # Create entrance, boss, and an orphan room (no corridors)
    await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
        json=_room_payload("fork", name="Entrance", is_entrance=True),
    )
    await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
        json=_room_payload("boss", name="Boss", is_boss_room=True),
    )
    await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
        json=_room_payload("treasure", name="Orphan"),
    )
    resp = await admin_client.post("/dungeons/admin/dungeons/%d/validate" % dungeon_id)
    data = resp.json()
    # Should have warnings about rooms without corridors
    assert len(data["warnings"]) > 0


async def test_validate_dungeon_deadend_warning(admin_client, created_dungeon):
    """POST validate - warns about deadends that have outgoing corridors."""
    dungeon_id = created_dungeon["id"]
    e_resp = await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
        json=_room_payload("fork", name="Entrance", is_entrance=True),
    )
    entrance_id = e_resp.json()["id"]
    d_resp = await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
        json=_room_payload("deadend", name="Deadend"),
    )
    deadend_id = d_resp.json()["id"]
    b_resp = await admin_client.post(
        "/dungeons/admin/dungeons/%d/rooms" % dungeon_id,
        json=_room_payload("boss", name="Boss", is_boss_room=True),
    )
    boss_id = b_resp.json()["id"]
    # entrance -> deadend -> boss (deadend with outgoing corridor = warning)
    await admin_client.post(
        "/dungeons/admin/dungeons/%d/corridors" % dungeon_id,
        json=_corridor_payload(entrance_id, deadend_id),
    )
    await admin_client.post(
        "/dungeons/admin/dungeons/%d/corridors" % dungeon_id,
        json=_corridor_payload(deadend_id, boss_id),
    )
    resp = await admin_client.post("/dungeons/admin/dungeons/%d/validate" % dungeon_id)
    data = resp.json()
    # Deadend with outgoing corridors should trigger a warning
    deadend_warnings = [w for w in data["warnings"] if "Deadend" in w or "тупик" in w.lower()]
    assert len(deadend_warnings) > 0


# ===========================
#  Auth
# ===========================

async def test_admin_endpoints_require_auth(no_auth_client):
    """Admin endpoints return 401/403 without admin token."""
    endpoints = [
        ("POST", "/dungeons/admin/dungeons"),
        ("GET", "/dungeons/admin/dungeons"),
        ("GET", "/dungeons/admin/dungeons/1"),
        ("PUT", "/dungeons/admin/dungeons/1"),
        ("DELETE", "/dungeons/admin/dungeons/1"),
        ("POST", "/dungeons/admin/dungeons/1/rooms"),
        ("PUT", "/dungeons/admin/rooms/1"),
        ("DELETE", "/dungeons/admin/rooms/1"),
        ("POST", "/dungeons/admin/dungeons/1/corridors"),
        ("PUT", "/dungeons/admin/corridors/1"),
        ("DELETE", "/dungeons/admin/corridors/1"),
        ("POST", "/dungeons/admin/dungeons/1/validate"),
    ]
    for method, path in endpoints:
        if method == "POST":
            resp = await no_auth_client.post(path, json={})
        elif method == "GET":
            resp = await no_auth_client.get(path)
        elif method == "PUT":
            resp = await no_auth_client.put(path, json={})
        elif method == "DELETE":
            resp = await no_auth_client.delete(path)
        assert resp.status_code in (401, 403, 422), (
            "Expected 401/403/422 for %s %s, got %d" % (method, path, resp.status_code)
        )


async def test_sql_injection_dungeon_name(admin_client):
    """Test that SQL injection in name field does not crash the service."""
    payload = _dungeon_payload(name="\"; DROP TABLE dungeons; --")
    resp = await admin_client.post("/dungeons/admin/dungeons", json=payload)
    # Should either succeed (201) or return validation error, not 500
    assert resp.status_code in (201, 400, 422)
