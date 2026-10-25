"""FEAT-178: the camp backpack.

A cloak marked `is_backpack` holds a few stacks of consumables (capacity by
rarity). Packing and unpacking happen outside a dungeon run; in a run the bag
is closed — only the backpack can be used or put on the belt, a belt item taken
off goes back into it, and the backpack itself stays on. Runs the REAL
activity-lock query against a `characters` table carrying its columns.
"""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError
from sqlalchemy import text

import auth_http
import backpack
import models
import schemas
from auth_http import UserRead, get_current_user_via_http

pytestmark = pytest.mark.real_activity_lock

CID = 1
_TOKEN = "test-internal-token"
_INTERNAL = {"X-Internal-Token": _TOKEN}


@pytest.fixture(autouse=True)
def _internal_token(monkeypatch):
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", _TOKEN)


@pytest.fixture()
def env(client, db_session):
    from main import app

    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.execute(text(
        "CREATE TABLE characters (id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT, id_class INTEGER DEFAULT 1, "
        "is_npc INTEGER DEFAULT 0, current_location_id INTEGER, currency_balance INTEGER DEFAULT 0, "
        "dungeon_session_id INTEGER, unconscious_until DATETIME)"
    ))
    db_session.execute(text("INSERT INTO characters (id, user_id, name) VALUES (1, 1, 'Hero'), (2, 2, 'Other')"))
    for slot_type in ("cloak", "belt", "fast_slot_1", "fast_slot_2"):
        db_session.add(models.EquipmentSlot(character_id=CID, slot_type=slot_type, is_enabled=True))

    def item(name, item_type="consumable", rarity="common", stack=10, **kw):
        it = models.Items(name=name, item_type=item_type, item_rarity=rarity, item_level=1,
                          max_stack_size=stack, is_unique=False, **kw)
        db_session.add(it)
        return it

    items = {
        "pack": item("Походный рюкзак", "cloak", "common", 1, is_backpack=True),
        "big_pack": item("Большой рюкзак", "cloak", "legendary", 1, is_backpack=True),
        "cloak": item("Плащ", "cloak", "common", 1),
        "potion": item("Зелье лечения", health_recovery=50),
        "elixir": item("Эликсир", stack=1, mana_recovery=20),
        "bomb": item("Бомба"),  # a battle-only consumable: nothing to recover
        "ore": item("Руда", "resource", stack=50),
        "belt": item("Пояс", "belt", "common", 1, fast_slot_bonus=2),  # fast slots come from a belt
    }
    db_session.commit()
    db_session.query(models.EquipmentSlot).filter_by(character_id=CID, slot_type="cloak").update(
        {"item_id": items["pack"].id})
    db_session.query(models.EquipmentSlot).filter_by(character_id=CID, slot_type="belt").update(
        {"item_id": items["belt"].id})
    rows = {}
    for key, qty in (("potion", 12), ("elixir", 5), ("bomb", 1), ("ore", 3), ("cloak", 1), ("big_pack", 1)):
        row = models.CharacterInventory(character_id=CID, item_id=items[key].id, quantity=qty)
        db_session.add(row)
        rows[key] = row
    db_session.commit()

    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(id=1, username="h", role="user",
                                                                             permissions=[])
    with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock), \
         patch("main.recover_in_attributes_service", new_callable=AsyncMock) as recover, \
         patch("main._reconcile_perks_async", new_callable=AsyncMock), \
         patch("main._track_cumulative_stats_async", new_callable=AsyncMock), \
         patch("main._evaluate_titles_async", new_callable=AsyncMock), \
         patch("main._in_background"):
        yield {"client": client, "db": db_session, "items": items, "rows": rows, "recover": recover}
    app.dependency_overrides.pop(get_current_user_via_http, None)
    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.commit()


def _in_run(db, on=True):
    db.execute(text("UPDATE characters SET dungeon_session_id=:s WHERE id=1"), {"s": 7 if on else None})
    db.commit()


def _bag(db, item_id):
    db.expire_all()
    return sum(r.quantity for r in db.query(models.CharacterInventory).filter_by(character_id=CID, item_id=item_id))


def _packed(db):
    db.expire_all()
    return [(r.item_id, r.quantity) for r in db.query(models.BackpackItem).filter_by(character_id=CID)
            .order_by(models.BackpackItem.id)]


def _pack(env, key, qty):
    return env["client"].post(f"/inventory/{CID}/backpack/pack",
                              json={"inventory_item_id": env["rows"][key].id, "quantity": qty})


def _first_packed_id(db):
    db.expire_all()
    return db.query(models.BackpackItem).filter_by(character_id=CID).order_by(models.BackpackItem.id).first().id


# ---------- capacity ----------

def test_capacity_by_rarity():
    def it(rarity, is_backpack=True):
        return models.Items(item_rarity=rarity, is_backpack=is_backpack)
    assert [backpack.capacity_of(it(r)) for r in ("common", "rare", "epic", "legendary", "mythical", "divine",
                                                    "demonic")] == [4, 6, 8, 10, 10, 10, 10]
    assert backpack.capacity_of(it("legendary", False)) == 0
    assert backpack.capacity_of(None) == 0


def test_only_a_cloak_can_be_a_backpack():
    base = dict(name="Рюкзак", item_level=1, item_rarity="common", max_stack_size=1, is_unique=False,
                is_backpack=True)
    schemas.ItemCreate(item_type="cloak", **base)
    with pytest.raises(ValidationError):
        schemas.ItemCreate(item_type="body", **base)


def test_get_shows_the_worn_backpack(env):
    body = env["client"].get(f"/inventory/{CID}/backpack").json()
    assert body["backpack"]["name"] == "Походный рюкзак"
    assert body["capacity"] == 4
    assert body["items"] == [] and body["in_dungeon"] is False
    # The whole belt, empty slots too, in slot order.
    assert [b["slot_type"] for b in body["belt"]] == ["fast_slot_1", "fast_slot_2"]
    assert all(b["item_id"] is None for b in body["belt"])


# ---------- packing ----------

def test_pack_fills_stacks_then_new_ones_within_capacity(env):
    db = env["db"]
    assert _pack(env, "potion", 12).status_code == 200  # stack of 10 -> two stacks
    assert _packed(db) == [(env["items"]["potion"].id, 10), (env["items"]["potion"].id, 2)]
    assert _bag(db, env["items"]["potion"].id) == 0
    assert _pack(env, "elixir", 2).status_code == 200  # stack of 1 -> two more stacks: 4/4
    resp = _pack(env, "elixir", 1)
    assert resp.status_code == 409 and resp.json()["detail"] == backpack.NO_ROOM
    assert _bag(db, env["items"]["elixir"].id) == 3  # nothing taken on a refusal
    body = env["client"].get(f"/inventory/{CID}/backpack").json()
    assert len(body["items"]) == 4 and body["items"][0]["health_recovery"] == 50


def test_only_consumables_and_only_with_a_backpack(env):
    resp = _pack(env, "ore", 1)
    assert resp.status_code == 400 and resp.json()["detail"] == backpack.NOT_PACKABLE
    env["db"].query(models.EquipmentSlot).filter_by(character_id=CID, slot_type="cloak").update({"item_id": None})
    env["db"].commit()
    resp = _pack(env, "potion", 1)
    assert resp.status_code == 409 and resp.json()["detail"] == backpack.NO_BACKPACK


def test_pack_more_than_owned(env):
    assert _pack(env, "bomb", 2).status_code == 400


def test_unpack_returns_to_the_bag(env):
    db = env["db"]
    _pack(env, "potion", 5)
    resp = env["client"].post(f"/inventory/{CID}/backpack/unpack",
                              json={"backpack_item_id": _first_packed_id(db), "quantity": 3})
    assert resp.status_code == 200
    assert _packed(db) == [(env["items"]["potion"].id, 2)]
    assert _bag(db, env["items"]["potion"].id) == 10


def test_no_packing_in_a_run(env):
    db = env["db"]
    _pack(env, "potion", 2)
    _in_run(db)
    resp = _pack(env, "potion", 1)
    assert resp.status_code == 409 and resp.json()["detail"] == backpack.PACK_IN_RUN
    resp = env["client"].post(f"/inventory/{CID}/backpack/unpack",
                              json={"backpack_item_id": _first_packed_id(db), "quantity": 1})
    assert resp.status_code == 409
    assert env["client"].get(f"/inventory/{CID}/backpack").json()["in_dungeon"] is True


# ---------- using ----------

def test_use_from_backpack_recovers_one(env):
    db = env["db"]
    _pack(env, "potion", 2)
    _in_run(db)
    resp = env["client"].post(f"/inventory/{CID}/backpack/use", json={"backpack_item_id": _first_packed_id(db)})
    assert resp.status_code == 200, resp.text
    env["recover"].assert_awaited_once_with(CID, {"health_recovery": 50})
    assert _packed(db) == [(env["items"]["potion"].id, 1)]


def test_battle_only_item_is_for_the_belt(env):
    db = env["db"]
    _pack(env, "bomb", 1)
    resp = env["client"].post(f"/inventory/{CID}/backpack/use", json={"backpack_item_id": _first_packed_id(db)})
    assert resp.status_code == 400 and "пояс" in resp.json()["detail"]
    assert _packed(db) == [(env["items"]["bomb"].id, 1)]


def test_the_bag_is_closed_in_a_run(env):
    db = env["db"]
    _in_run(db)
    resp = env["client"].post(f"/inventory/{CID}/use_item",
                              json={"item_id": env["items"]["potion"].id, "quantity": 1})
    assert resp.status_code == 409 and resp.json()["detail"] == backpack.BAG_CLOSED
    resp = env["client"].post(f"/inventory/{CID}/equip", json={"item_id": env["items"]["potion"].id})
    assert resp.status_code == 409 and resp.json()["detail"] == backpack.BAG_CLOSED
    assert _bag(db, env["items"]["potion"].id) == 12
    _in_run(db, False)
    assert env["client"].post(f"/inventory/{CID}/use_item",
                              json={"item_id": env["items"]["potion"].id, "quantity": 1}).status_code == 200


# ---------- the belt ----------

def test_belt_from_backpack_and_back_in_a_run(env):
    db = env["db"]
    _pack(env, "potion", 3)
    _in_run(db)
    pid = env["items"]["potion"].id
    resp = env["client"].post(f"/inventory/{CID}/equip", json={"item_id": pid, "backpack_item_id": _first_packed_id(db)})
    assert resp.status_code == 200, resp.text
    assert _packed(db) == [(pid, 2)]
    slot = db.query(models.EquipmentSlot).filter_by(character_id=CID, slot_type=resp.json()["slot_type"]).first()
    assert slot.item_id == pid
    # Taken off in a run: back into the backpack, not the closed bag.
    resp = env["client"].post(f"/inventory/{CID}/unequip", params={"slot_type": slot.slot_type})
    assert resp.status_code == 200, resp.text
    assert _packed(db) == [(pid, 3)]
    assert _bag(db, pid) == 9


def test_gear_cannot_go_to_the_belt_from_the_backpack(env):
    db = env["db"]
    _pack(env, "potion", 1)
    resp = env["client"].post(f"/inventory/{CID}/equip",
                              json={"item_id": env["items"]["cloak"].id, "backpack_item_id": _first_packed_id(db)})
    assert resp.status_code == 400


def test_belt_taken_off_in_a_run_spills_into_the_backpack(env):
    """The belt goes, its slots with it: in a run what lay there goes into the backpack, not the closed bag."""
    db = env["db"]
    pid, eid = env["items"]["potion"].id, env["items"]["elixir"].id
    _pack(env, "potion", 2)
    _pack(env, "elixir", 1)
    _in_run(db)
    rows = {r.item_id: r.id for r in db.query(models.BackpackItem).filter_by(character_id=CID)}
    assert env["client"].post(f"/inventory/{CID}/equip", json={"item_id": pid, "backpack_item_id": rows[pid]}).status_code == 200
    assert env["client"].post(f"/inventory/{CID}/equip", json={"item_id": eid, "backpack_item_id": rows[eid]}).status_code == 200
    assert _packed(db) == [(pid, 1)]
    resp = env["client"].post(f"/inventory/{CID}/unequip", params={"slot_type": "belt"})
    assert resp.status_code == 200, resp.text
    assert sorted(_packed(db)) == sorted([(pid, 2), (eid, 1)])
    assert _bag(db, pid) == 10 and _bag(db, eid) == 4  # the bag got nothing back


def test_belt_spill_without_room_falls_back_to_the_bag(env):
    db = env["db"]
    pid = env["items"]["potion"].id
    _pack(env, "potion", 1)
    _in_run(db)
    row = db.query(models.BackpackItem).filter_by(character_id=CID).first().id
    env["client"].post(f"/inventory/{CID}/equip", json={"item_id": pid, "backpack_item_id": row})
    # Fill the backpack to the brim with single-stack elixirs straight from the "dungeon".
    env["client"].post(f"/inventory/internal/characters/{CID}/backpack/add",
                       json={"item_id": env["items"]["elixir"].id, "quantity": 4}, headers=_INTERNAL)
    resp = env["client"].post(f"/inventory/{CID}/unequip", params={"slot_type": "belt"})
    assert resp.status_code == 200, resp.text
    assert _bag(db, pid) == 12  # nothing is lost


# ---------- the backpack coming off ----------

def test_taking_the_backpack_off_empties_it_into_the_bag(env):
    db = env["db"]
    _pack(env, "potion", 4)
    resp = env["client"].post(f"/inventory/{CID}/unequip", params={"slot_type": "cloak"})
    assert resp.status_code == 200, resp.text
    assert _packed(db) == []
    assert _bag(db, env["items"]["potion"].id) == 12


def test_swapping_backpacks_empties_the_old_one(env):
    db = env["db"]
    _pack(env, "potion", 4)
    resp = env["client"].post(f"/inventory/{CID}/equip", json={"item_id": env["items"]["big_pack"].id})
    assert resp.status_code == 200, resp.text
    assert _packed(db) == []
    assert env["client"].get(f"/inventory/{CID}/backpack").json()["capacity"] == 10


def test_the_backpack_stays_on_in_a_run(env):
    db = env["db"]
    _pack(env, "potion", 2)
    _in_run(db)
    resp = env["client"].post(f"/inventory/{CID}/unequip", params={"slot_type": "cloak"})
    assert resp.status_code == 409 and resp.json()["detail"] == backpack.KEEP_ON_IN_RUN
    resp = env["client"].post(f"/inventory/{CID}/equip", json={"item_id": env["items"]["cloak"].id})
    assert resp.status_code == 409
    assert _packed(db) == [(env["items"]["potion"].id, 2)]


# ---------- internal: the leader hands out finds ----------

def test_internal_add_puts_finds_into_the_backpack(env):
    db = env["db"]
    url = f"/inventory/internal/characters/{CID}/backpack/add"
    assert env["client"].post(url, json={"item_id": env["items"]["potion"].id, "quantity": 2}).status_code == 401
    resp = env["client"].post(url, json={"item_id": env["items"]["potion"].id, "quantity": 2}, headers=_INTERNAL)
    assert resp.status_code == 200, resp.text
    assert _packed(db) == [(env["items"]["potion"].id, 2)]
    resp = env["client"].post(url, json={"item_id": env["items"]["ore"].id, "quantity": 1}, headers=_INTERNAL)
    assert resp.status_code == 400
    resp = env["client"].post(url, json={"item_id": env["items"]["elixir"].id, "quantity": 4}, headers=_INTERNAL)
    assert resp.status_code == 409 and resp.json()["detail"] == backpack.NO_ROOM


# ---------- security ----------

def test_someone_elses_backpack(env):
    assert env["client"].get("/inventory/2/backpack").status_code == 403
    assert env["client"].post("/inventory/2/backpack/use", json={"backpack_item_id": 1}).status_code == 403


def test_bad_quantities(env):
    assert env["client"].post(f"/inventory/{CID}/backpack/pack",
                              json={"inventory_item_id": env["rows"]["potion"].id, "quantity": 0}).status_code == 422
    assert env["client"].post(f"/inventory/{CID}/backpack/unpack",
                              json={"backpack_item_id": "x", "quantity": 1}).status_code == 422
