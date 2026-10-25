"""FEAT-175: HTTP layer — RBAC, admin validation (incl. 3D grid size),
my-session ownership, occupancy flags, WebSocket reconnect."""

import pytest

import gameplay
import ws_manager
from auth_http import get_current_user_via_http, UserRead
from main import app
from helpers import _dungeon_payload, _room_payload
from dungeon_harness import fake_redis, world, build_dungeon, enter_solo  # noqa: F401


def _as(user):
    app.dependency_overrides[get_current_user_via_http] = lambda: user


EDITOR = UserRead(id=5, username="ed", role="editor", permissions=["dungeons:view"])
CREATOR = UserRead(id=6, username="cr", role="moderator",
                   permissions=["dungeons:view", "dungeons:create", "dungeons:edit"])
ADMIN = UserRead(id=1, username="admin", role="admin",
                 permissions=["dungeons:view", "dungeons:create", "dungeons:edit", "dungeons:delete"])
PLAYER = UserRead(id=1, username="p1", role="user", permissions=[])
OTHER = UserRead(id=2, username="p2", role="user", permissions=[])


# ---------------------------------------------------------------- RBAC

async def test_rbac_view_only_editor(no_auth_client):
    _as(EDITOR)
    assert (await no_auth_client.get("/dungeons/admin/dungeons")).status_code == 200
    r = await no_auth_client.post("/dungeons/admin/dungeons", json=_dungeon_payload())
    assert r.status_code == 403


async def test_rbac_delete_needs_delete_permission(no_auth_client):
    _as(CREATOR)
    created = await no_auth_client.post("/dungeons/admin/dungeons", json=_dungeon_payload())
    assert created.status_code == 201
    did = created.json()["id"]
    assert (await no_auth_client.delete(f"/dungeons/admin/dungeons/{did}")).status_code == 403
    _as(ADMIN)
    assert (await no_auth_client.delete(f"/dungeons/admin/dungeons/{did}")).status_code == 204


async def test_rbac_plain_player_cannot_touch_admin(no_auth_client):
    _as(PLAYER)
    assert (await no_auth_client.get("/dungeons/admin/sessions")).status_code == 403


# ---------------------------------------------------------------- admin validation

async def test_dungeon_location_must_exist(admin_client):
    r = await admin_client.post("/dungeons/admin/dungeons", json=_dungeon_payload(location_id=4242))
    assert r.status_code == 400
    assert "Локация 4242 не найдена" in r.json()["detail"]
    ok = await admin_client.post("/dungeons/admin/dungeons", json=_dungeon_payload())
    r = await admin_client.put(f"/dungeons/admin/dungeons/{ok.json()['id']}", json={"location_id": 4242})
    assert r.status_code == 400


async def test_grid_size_create_update_and_detail(admin_client, created_dungeon):
    did = created_dungeon["id"]
    bad = await admin_client.post(f"/dungeons/admin/dungeons/{did}/rooms",
                                  json=_room_payload("fork", grid_w=9, grid_d=3))
    assert bad.status_code == 422
    assert "Размер комнаты должен быть от 2 до 8 клеток" in bad.text
    bad = await admin_client.post(f"/dungeons/admin/dungeons/{did}/rooms",
                                  json=_room_payload("fork", grid_w=3, grid_d=1))
    assert bad.status_code == 422

    ok = await admin_client.post(f"/dungeons/admin/dungeons/{did}/rooms",
                                 json=_room_payload("fork", grid_w=2, grid_d=8))
    assert ok.status_code == 201
    room = ok.json()
    assert (room["grid_w"], room["grid_d"]) == (2, 8)
    default = await admin_client.post(f"/dungeons/admin/dungeons/{did}/rooms", json=_room_payload("fork"))
    assert (default.json()["grid_w"], default.json()["grid_d"]) == (None, None)

    upd = await admin_client.put(f"/dungeons/admin/rooms/{room['id']}", json={"grid_w": 0})
    assert upd.status_code == 422
    assert "Размер комнаты должен быть от 2 до 8 клеток" in upd.text
    upd = await admin_client.put(f"/dungeons/admin/rooms/{room['id']}", json={"grid_w": 5, "grid_d": None})
    assert upd.status_code == 200
    assert (upd.json()["grid_w"], upd.json()["grid_d"]) == (5, None)

    detail = (await admin_client.get(f"/dungeons/admin/dungeons/{did}")).json()
    by_id = {r["id"]: r for r in detail["rooms"]}
    assert by_id[room["id"]]["grid_w"] == 5 and "grid_d" in by_id[room["id"]]


async def test_teleport_target_validated_on_update(admin_client, dungeon_with_rooms):
    did = dungeon_with_rooms["dungeon"]["id"]
    tp = (await admin_client.post(f"/dungeons/admin/dungeons/{did}/rooms",
                                  json=_room_payload("teleport"))).json()
    r = await admin_client.put(f"/dungeons/admin/rooms/{tp['id']}", json={"room_config": {"target_room_id": -15}})
    assert r.status_code == 422
    r = await admin_client.put(f"/dungeons/admin/rooms/{tp['id']}", json={"room_config": {"target_room_id": 99999}})
    assert r.status_code == 400
    r = await admin_client.put(f"/dungeons/admin/rooms/{tp['id']}",
                               json={"room_config": {"target_room_id": dungeon_with_rooms["boss_room"]["id"]}})
    assert r.status_code == 200
    # a room of ANOTHER dungeon is refused too
    other = (await admin_client.post("/dungeons/admin/dungeons", json=_dungeon_payload())).json()
    foreign = (await admin_client.post(f"/dungeons/admin/dungeons/{other['id']}/rooms",
                                       json=_room_payload("fork"))).json()
    r = await admin_client.put(f"/dungeons/admin/rooms/{tp['id']}",
                               json={"room_config": {"target_room_id": foreign["id"]}})
    assert r.status_code == 400
    # a red portal's rooms are checked the same way
    r = await admin_client.put(f"/dungeons/admin/rooms/{tp['id']}",
                               json={"room_config": {"portal": "red", "target_room_ids": [foreign["id"]]}})
    assert r.status_code == 400
    r = await admin_client.put(f"/dungeons/admin/rooms/{tp['id']}", json={"room_config": {
        "portal": "red", "target_room_ids": [dungeon_with_rooms["boss_room"]["id"]], "difficulty": 15}})
    assert r.status_code == 200


async def test_event_outcomes_validated(admin_client, created_dungeon):
    did = created_dungeon["id"]
    cfg = {"choices": [{"text": "a", "outcome_type": "battle", "outcome_data": '{"mob_template_ids": []}'}]}
    r = await admin_client.post(f"/dungeons/admin/dungeons/{did}/rooms", json=_room_payload("event", room_config=cfg))
    assert r.status_code == 422
    cfg = {"choices": [{"text": "a", "outcome_type": "explode", "outcome_data": "{}"}]}
    r = await admin_client.post(f"/dungeons/admin/dungeons/{did}/rooms", json=_room_payload("event", room_config=cfg))
    assert r.status_code == 422
    cfg = {"choices": [{"text": "a", "outcome_type": "heal", "outcome_data": '{"heal_percent": 30}'}]}
    r = await admin_client.post(f"/dungeons/admin/dungeons/{did}/rooms", json=_room_payload("event", room_config=cfg))
    assert r.status_code == 201


async def test_validate_reports_play_time_problems(admin_client, created_dungeon):
    did = created_dungeon["id"]
    ent = (await admin_client.post(f"/dungeons/admin/dungeons/{did}/rooms",
                                   json=_room_payload("fork", is_entrance=True))).json()
    boss = (await admin_client.post(f"/dungeons/admin/dungeons/{did}/rooms",
                                    json=_room_payload("boss", is_boss_room=True))).json()
    await admin_client.post(f"/dungeons/admin/dungeons/{did}/corridors",
                            json={"from_room_id": ent["id"], "to_room_id": boss["id"]})
    out = (await admin_client.post(f"/dungeons/admin/dungeons/{did}/validate")).json()
    assert out["valid"] is False
    assert any("не заданы мобы" in e for e in out["errors"])


async def test_cannot_delete_dungeon_with_group_inside(no_auth_client, db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await enter_solo(db_session, d)
    _as(ADMIN)
    r = await no_auth_client.delete(f"/dungeons/admin/dungeons/{d.id}")
    assert r.status_code == 409


# ---------------------------------------------------------------- player endpoints

async def test_my_session_only_for_own_character(no_auth_client, db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    _as(OTHER)
    r = await no_auth_client.get("/dungeons/my-session/10")
    assert r.status_code == 403
    _as(PLAYER)
    r = await no_auth_client.get("/dungeons/my-session/10")
    assert r.status_code == 200
    assert r.json() == {"in_dungeon": True, "session_id": st.session_id, "pending_loot_session_id": None}
    _as(UserRead(id=77, username="mod", role="moderator", permissions=[]))
    assert (await no_auth_client.get("/dungeons/my-session/10")).status_code == 200


async def test_at_location_reports_occupied(no_auth_client, db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    _as(PLAYER)
    first = (await no_auth_client.get(f"/dungeons/at-location/{d.location_id}")).json()
    assert first[0]["is_occupied"] is False
    await enter_solo(db_session, d)
    second = (await no_auth_client.get(f"/dungeons/at-location/{d.location_id}")).json()
    assert second[0]["is_occupied"] is True


async def test_invite_and_leave_routes_are_gone(no_auth_client):
    _as(PLAYER)
    assert (await no_auth_client.post("/dungeons/sessions/1/invite", json={"character_id": 2})).status_code == 404
    assert (await no_auth_client.post("/dungeons/sessions/1/leave", json={"character_id": 2})).status_code == 404


async def test_state_endpoint_rejects_foreign_character(no_auth_client, db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    _as(OTHER)
    r = await no_auth_client.get(f"/dungeons/sessions/{st.session_id}/state", params={"character_id": 10})
    assert r.status_code == 403


# ---------------------------------------------------------------- WebSocket reconnect

class _WS:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True

    async def send_json(self, data):
        pass


async def test_reconnect_does_not_kill_new_socket():
    old, new = _WS(), _WS()
    await ws_manager.connect(900, 1, old)
    await ws_manager.connect(900, 1, new)
    assert old.closed and not new.closed
    # the old handler's finally-block runs after the reconnect
    await ws_manager.disconnect(900, 1, old)
    assert ws_manager.session_connections[900][1] is new
    assert not new.closed
    await ws_manager.disconnect(900, 1, new)
    assert 900 not in ws_manager.session_connections
