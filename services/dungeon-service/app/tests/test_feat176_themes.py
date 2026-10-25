"""FEAT-176: look presets for the 3D miniature — the dungeon's theme and each floor's own."""
import pytest
from sqlalchemy import select

import gameplay
from helpers import _dungeon_payload
from models import Dungeon
from dungeon_harness import (  # noqa: F401
    fake_redis, world, build_dungeon, enter_solo,
)


async def test_a_new_dungeon_is_stone_unless_told(admin_client):
    resp = await admin_client.post("/dungeons/admin/dungeons", json=_dungeon_payload())
    assert resp.status_code == 201
    assert resp.json()["theme"] == "stone" and resp.json()["floor_themes"] is None
    resp = await admin_client.post("/dungeons/admin/dungeons", json=_dungeon_payload(
        theme="catacombs", floor_themes={"2": "volcano", 3: "sewer"}))
    assert resp.status_code == 201
    data = resp.json()
    assert data["theme"] == "catacombs" and data["floor_themes"] == {"2": "volcano", "3": "sewer"}


@pytest.mark.parametrize("fields", [
    {"theme": "candyland"},
    {"floor_themes": {"2": "candyland"}},
    {"floor_themes": {"0": "ice"}},
    {"floor_themes": {"first": "ice"}},
    {"floor_themes": ["ice"]},
])
async def test_unknown_looks_are_refused(admin_client, fields):
    resp = await admin_client.post("/dungeons/admin/dungeons", json=_dungeon_payload(**fields))
    assert resp.status_code == 422


async def test_the_look_is_changed_in_editing(admin_client, created_dungeon):
    did = created_dungeon["id"]
    resp = await admin_client.put(f"/dungeons/admin/dungeons/{did}", json={"theme": "ice", "floor_themes": {"2": "mine"}})
    assert resp.status_code == 200 and resp.json()["theme"] == "ice"
    # an emptied map is stored as none: every floor takes the dungeon's look again
    resp = await admin_client.put(f"/dungeons/admin/dungeons/{did}", json={"floor_themes": {}})
    assert resp.status_code == 200 and resp.json()["floor_themes"] is None
    detail = (await admin_client.get(f"/dungeons/admin/dungeons/{did}")).json()
    assert detail["theme"] == "ice" and detail["floor_themes"] is None


async def test_the_run_knows_how_its_floors_look(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    dungeon = (await db_session.execute(select(Dungeon).where(Dungeon.id == d.id))).scalar_one()
    dungeon.theme, dungeon.floor_themes = "temple", {"2": "volcano"}
    await db_session.commit()
    st = await enter_solo(db_session, d)
    state = await gameplay.get_session_state(db_session, st.session_id, 10)
    assert state.theme == "temple" and state.floor_themes == {"2": "volcano"}
