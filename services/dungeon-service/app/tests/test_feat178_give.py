"""FEAT-178: mid-run the leader hands a found consumable to a member's camp backpack."""

import pytest
from fastapi import HTTPException

import chat
import gameplay
import http_clients
from models import DungeonSessionInventory, DungeonSessionMember
from sqlalchemy import select
from dungeon_harness import fake_redis, world, build_dungeon  # noqa: F401

POTION, ORE = 501, 502


@pytest.fixture()
def run(db_session, world, monkeypatch):
    backpacks = {}
    refuse = {}

    async def item_info(item_id):
        return {"name": {POTION: "Зелье", ORE: "Руда"}[item_id],
                "item_type": "consumable" if item_id == POTION else "resource"}

    async def add_to_backpack(cid, item_id, quantity):
        if cid in refuse:
            raise HTTPException(status_code=409, detail=refuse[cid])
        backpacks.setdefault(cid, []).append((item_id, quantity))
        return {}

    monkeypatch.setattr(http_clients, "get_item_info", item_info)
    monkeypatch.setattr(http_clients, "add_to_backpack", add_to_backpack)

    async def setup():
        d, _, _ = await build_dungeon(db_session)
        world.party = {"party_id": 1, "leader_character_id": 10, "member_character_ids": [10, 11]}
        state = await gameplay.start_run(db_session, d.id, 10, 1, party=True)
        await gameplay._add_to_group_inventory(db_session, state.session_id, POTION, 3, "Сундук")
        await gameplay._add_to_group_inventory(db_session, state.session_id, ORE, 1, "Сундук")
        await db_session.commit()
        return state.session_id

    return {"setup": setup, "backpacks": backpacks, "refuse": refuse}


async def _left(db, sid, item_id):
    db.expire_all()
    rows = (await db.execute(select(DungeonSessionInventory).where(
        DungeonSessionInventory.session_id == sid, DungeonSessionInventory.item_id == item_id))).scalars().all()
    return sum(r.quantity for r in rows)


async def test_leader_gives_a_potion_into_a_backpack(db_session, world, run):
    sid = await run["setup"]()
    resp = await gameplay.give_item(db_session, sid, 10, 11, POTION, 2)
    assert run["backpacks"] == {11: [(POTION, 2)]}
    assert await _left(db_session, sid, POTION) == 1
    assert "Зелье ×2" in resp.message
    assert any(e["type"] == "item_given" and e["data"]["target_character_id"] == 11 for e in world.events)
    assert any("получает от лидера" in e["text"] for e in await chat.history(sid))


async def test_the_last_one_leaves_the_group_inventory(db_session, world, run):
    sid = await run["setup"]()
    resp = await gameplay.give_item(db_session, sid, 10, 10, POTION, 3)
    assert await _left(db_session, sid, POTION) == 0
    assert [i.item_id for i in resp.group_inventory] == [ORE]


async def test_only_consumables(db_session, world, run):
    sid = await run["setup"]()
    with pytest.raises(HTTPException) as e:
        await gameplay.give_item(db_session, sid, 10, 11, ORE, 1)
    assert e.value.status_code == 400
    assert await _left(db_session, sid, ORE) == 1 and run["backpacks"] == {}


async def test_no_room_keeps_the_item_with_the_party(db_session, world, run):
    sid = await run["setup"]()
    run["refuse"][11] = "В походном рюкзаке нет места"
    with pytest.raises(HTTPException) as e:
        await gameplay.give_item(db_session, sid, 10, 11, POTION, 1)
    assert e.value.status_code == 409 and e.value.detail == "Герой11: в рюкзаке нет места"
    assert await _left(db_session, sid, POTION) == 3


async def test_no_backpack_is_said_about_the_member(db_session, world, run):
    sid = await run["setup"]()
    run["refuse"][11] = "Наденьте походный рюкзак в слот плаща"
    with pytest.raises(HTTPException) as e:
        await gameplay.give_item(db_session, sid, 10, 11, POTION, 1)
    assert e.value.detail == "Герой11: нет походного рюкзака"


async def test_more_than_the_party_has(db_session, world, run):
    sid = await run["setup"]()
    with pytest.raises(HTTPException) as e:
        await gameplay.give_item(db_session, sid, 10, 11, POTION, 4)
    assert e.value.status_code == 409


async def test_only_the_leader_gives(db_session, world, run):
    sid = await run["setup"]()
    with pytest.raises(HTTPException) as e:
        await gameplay.give_item(db_session, sid, 11, 11, POTION, 1)
    assert e.value.status_code == 403


async def test_not_to_the_fallen_or_strangers(db_session, world, run):
    sid = await run["setup"]()
    member = (await db_session.execute(select(DungeonSessionMember).where(
        DungeonSessionMember.session_id == sid, DungeonSessionMember.character_id == 11))).scalar_one()
    member.status = "dead"
    await db_session.commit()
    with pytest.raises(HTTPException) as e:
        await gameplay.give_item(db_session, sid, 10, 11, POTION, 1)
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        await gameplay.give_item(db_session, sid, 10, 99, POTION, 1)
    assert e.value.status_code == 403
