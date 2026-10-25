"""Admin: the dungeon's state (cooldown after a clear, the group inside) and restoring it at once."""

from datetime import datetime, timedelta

import pytest

import session_state
from models import DungeonSession
from helpers import _dungeon_payload
from dungeon_harness import fake_redis  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _dungeon(client):
    return (await client.post("/dungeons/admin/dungeons", json=_dungeon_payload())).json()["id"]


async def test_a_fresh_dungeon_is_free(admin_client, fake_redis):
    did = await _dungeon(admin_client)
    resp = await admin_client.get(f"/dungeons/admin/dungeons/{did}/status")
    assert resp.status_code == 200
    assert resp.json() == {"is_on_cooldown": False, "cooldown_remaining_seconds": 0, "occupied_session_id": None}


async def test_cleared_dungeon_shows_its_cooldown_and_restores_on_demand(admin_client, db_session, fake_redis):
    did = await _dungeon(admin_client)
    db_session.add(DungeonSession(dungeon_id=did, leader_character_id=5, status="completed",
                                  cooldown_until=datetime.utcnow() + timedelta(hours=2)))
    await db_session.commit()
    await session_state.set_dungeon_cooldown(did, 1, 2)

    body = (await admin_client.get(f"/dungeons/admin/dungeons/{did}/status")).json()
    assert body["is_on_cooldown"] is True
    assert 0 < body["cooldown_remaining_seconds"] <= 2 * 3600

    assert (await admin_client.delete(f"/dungeons/admin/dungeons/{did}/cooldown")).status_code == 200
    body = (await admin_client.get(f"/dungeons/admin/dungeons/{did}/status")).json()
    assert body["is_on_cooldown"] is False
    # Redis and the DB copy are both cleared: a Redis flush does not bring the cooldown back.
    on_cd, _ = await session_state.check_dungeon_cooldown(did)
    assert on_cd is False


async def test_status_names_the_group_inside(admin_client, db_session, fake_redis):
    did = await _dungeon(admin_client)
    run = DungeonSession(dungeon_id=did, leader_character_id=5, status="active", last_activity_at=datetime.utcnow())
    db_session.add(run)
    await db_session.commit()
    body = (await admin_client.get(f"/dungeons/admin/dungeons/{did}/status")).json()
    assert body["occupied_session_id"] == run.id


async def test_status_of_unknown_dungeon(admin_client, fake_redis):
    assert (await admin_client.get("/dungeons/admin/dungeons/987654/status")).status_code == 404


async def test_status_and_restore_need_admin_rights(no_auth_client):
    assert (await no_auth_client.get("/dungeons/admin/dungeons/1/status")).status_code in (401, 403)
    assert (await no_auth_client.delete("/dungeons/admin/dungeons/1/cooldown")).status_code in (401, 403)
