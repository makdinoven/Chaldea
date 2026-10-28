"""FEAT-180: a house's storage.

Rights come from locations-service's tables (`houses`, `house_plots`,
`house_rooms`, `house_residents`), laid out here as minimal stand-ins: the
owner puts and takes, a resident as allowed; everybody needs to stand in the
house's location. A stored item keeps its sharpening and wear.
"""

import pytest
from sqlalchemy import text

import house_storage
import house_workshop
import models
from auth_http import UserRead, get_current_user_via_http

pytestmark = pytest.mark.real_activity_lock

OWNER, RESIDENT, STRANGER = 1, 2, 3
HOUSE, TOWN, FAR = 5, 100, 200

_LOCATION_TABLES = ("houses", "house_plots", "house_rooms", "house_residents", "characters")


@pytest.fixture()
def env(client, db_session):
    from main import app

    db = db_session
    for t in _LOCATION_TABLES:
        db.execute(text(f"DROP TABLE IF EXISTS {t}"))
    db.execute(text(
        "CREATE TABLE characters (id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT, is_npc INTEGER DEFAULT 0, "
        "current_location_id INTEGER, currency_balance INTEGER DEFAULT 0, dungeon_session_id INTEGER, "
        "unconscious_until DATETIME, asleep_since DATETIME, reading_since DATETIME, house_room_id INTEGER)"))
    # Stage 7: everybody stands in the storage (room 2) unless a test moves them.
    db.execute(text("INSERT INTO characters (id, user_id, name, current_location_id, house_room_id) VALUES "
                    "(1, 1, 'Owner', :t, 2), (2, 2, 'Resident', :t, 2), (3, 3, 'Stranger', :t, 2)"), {"t": TOWN})
    db.execute(text("CREATE TABLE house_plots (id INTEGER PRIMARY KEY, location_id INTEGER)"))
    db.execute(text("CREATE TABLE houses (id INTEGER PRIMARY KEY, plot_id INTEGER, owner_character_id INTEGER, "
                    "status TEXT DEFAULT 'active')"))
    db.execute(text("CREATE TABLE house_rooms (id INTEGER PRIMARY KEY, house_id INTEGER, room_type TEXT, "
                    "level INTEGER DEFAULT 1, upgrade_to_level INTEGER, upgrade_complete_at TIMESTAMP)"))
    db.execute(text("CREATE TABLE house_residents (id INTEGER PRIMARY KEY, house_id INTEGER, character_id INTEGER, "
                    "can_take INTEGER, can_put INTEGER)"))
    db.execute(text("INSERT INTO house_plots VALUES (1, :t)"), {"t": TOWN})
    db.execute(text("INSERT INTO houses (id, plot_id, owner_character_id) VALUES (:h, 1, :o)"), {"h": HOUSE, "o": OWNER})
    db.execute(text("INSERT INTO house_rooms (id, house_id, room_type) VALUES (1, :h, 'hall'), (2, :h, 'storage')"),
               {"h": HOUSE})
    db.execute(text("INSERT INTO house_residents (house_id, character_id, can_take, can_put) VALUES (:h, :c, 0, 1)"),
               {"h": HOUSE, "c": RESIDENT})

    def item(name, stack, **kw):
        it = models.Items(name=name, item_type="resource", item_rarity="common", item_level=1,
                          max_stack_size=stack, is_unique=False, **kw)
        db.add(it)
        return it

    ore, sword = item("Руда", 10), item("Меч", 1, max_durability=100)
    db.commit()
    rows = {
        "ore": models.CharacterInventory(character_id=OWNER, item_id=ore.id, quantity=25),
        "sword": models.CharacterInventory(character_id=OWNER, item_id=sword.id, quantity=1,
                                           enhancement_points_spent=3, enhancement_bonuses='{"damage_modifier": 4}',
                                           current_durability=40),
        "res_ore": models.CharacterInventory(character_id=RESIDENT, item_id=ore.id, quantity=2),
    }
    db.add_all(rows.values())
    db.commit()

    who = {"id": OWNER}
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=who["id"], username="u", role="user", permissions=[])

    def call(path, uid, **body):
        who["id"] = uid
        return client.post(f"/inventory/houses/{HOUSE}/storage/{path}", json=body)

    def state(uid, cid):
        who["id"] = uid
        return client.get(f"/inventory/houses/{HOUSE}/storage?character_id={cid}")

    yield {"db": db, "rows": rows, "ore": ore, "sword": sword, "call": call, "state": state}
    app.dependency_overrides.pop(get_current_user_via_http, None)
    for t in _LOCATION_TABLES:
        db.execute(text(f"DROP TABLE IF EXISTS {t}"))
    db.commit()


def _stored(db):
    db.expire_all()
    return [(r.item_id, r.quantity) for r in db.query(models.HouseStorageItem).order_by(models.HouseStorageItem.id)]


def _bag(db, cid, item_id):
    db.expire_all()
    return sum(r.quantity for r in db.query(models.CharacterInventory).filter_by(character_id=cid, item_id=item_id))


def test_owner_sees_the_capacity_of_the_storage_rooms(env):
    r = env["state"](OWNER, 1)
    assert r.status_code == 200
    body = r.json()
    assert (body["capacity"], body["used"], body["can_take"], body["can_put"], body["at_house"]) == (
        house_workshop.STORAGE_STACKS_BY_LEVEL[1], 0, True, True, True)


def test_putting_fills_stacks_and_taking_returns_them(env):
    ore = env["ore"].id
    r = env["call"]("put", OWNER, character_id=1, inventory_item_id=env["rows"]["ore"].id, quantity=15)
    assert r.status_code == 200, r.text
    assert _stored(env["db"]) == [(ore, 10), (ore, 5)] and _bag(env["db"], 1, ore) == 10
    env["call"]("put", OWNER, character_id=1, inventory_item_id=env["rows"]["ore"].id, quantity=3)
    assert _stored(env["db"]) == [(ore, 10), (ore, 8)]
    first = env["state"](OWNER, 1).json()["items"][0]["id"]
    r = env["call"]("take", OWNER, character_id=1, storage_item_id=first, quantity=10)
    assert r.status_code == 200 and _stored(env["db"]) == [(ore, 8)] and _bag(env["db"], 1, ore) == 17


def test_a_sharpened_worn_item_keeps_its_state(env):
    sword = env["sword"].id
    assert env["call"]("put", OWNER, character_id=1, inventory_item_id=env["rows"]["sword"].id,
                       quantity=1).status_code == 200
    assert _bag(env["db"], 1, sword) == 0
    sid = env["state"](OWNER, 1).json()["items"][0]["id"]
    assert env["call"]("take", OWNER, character_id=1, storage_item_id=sid, quantity=1).status_code == 200
    env["db"].expire_all()
    back = env["db"].query(models.CharacterInventory).filter_by(character_id=1, item_id=sword).one()
    assert (back.enhancement_points_spent, back.current_durability) == (3, 40)
    assert back.enhancement_bonuses == '{"damage_modifier": 4}'


def test_resident_rights_and_strangers(env):
    ore = env["ore"].id
    assert env["call"]("put", RESIDENT, character_id=2, inventory_item_id=env["rows"]["res_ore"].id,
                       quantity=2).status_code == 200
    sid = env["state"](RESIDENT, 2).json()["items"][0]["id"]
    assert env["call"]("take", RESIDENT, character_id=2, storage_item_id=sid, quantity=1).status_code == 403
    assert env["state"](STRANGER, 3).status_code == 403
    assert env["state"](STRANGER, 1).status_code == 403  # someone else's character
    assert _stored(env["db"]) == [(ore, 2)]


def test_storage_needs_presence_room_and_a_storage_room(env):
    db = env["db"]
    db.execute(text("UPDATE characters SET current_location_id = :f WHERE id = 1"), {"f": FAR})
    db.commit()
    r = env["call"]("put", OWNER, character_id=1, inventory_item_id=env["rows"]["ore"].id, quantity=1)
    assert r.status_code == 403 and env["state"](OWNER, 1).json()["at_house"] is False
    db.execute(text("UPDATE characters SET current_location_id = :t WHERE id = 1"), {"t": TOWN})
    db.commit()
    assert env["call"]("put", OWNER, character_id=1, inventory_item_id=env["rows"]["ore"].id,
                       quantity=99).status_code == 400
    db.execute(text("DELETE FROM house_rooms WHERE room_type = 'storage'"))
    db.commit()
    r = env["call"]("put", OWNER, character_id=1, inventory_item_id=env["rows"]["ore"].id, quantity=1)
    assert r.status_code == 409 and r.json()["detail"] == house_storage.NO_STORAGE


def test_a_full_storage_refuses_new_stacks(env, monkeypatch):
    monkeypatch.setitem(house_workshop.STORAGE_STACKS_BY_LEVEL, 1, 1)
    assert env["call"]("put", OWNER, character_id=1, inventory_item_id=env["rows"]["ore"].id,
                       quantity=5).status_code == 200
    r = env["call"]("put", OWNER, character_id=1, inventory_item_id=env["rows"]["sword"].id, quantity=1)
    assert r.status_code == 409 and r.json()["detail"] == house_storage.NO_ROOM
    # Topping up the open stack still fits.
    assert env["call"]("put", OWNER, character_id=1, inventory_item_id=env["rows"]["ore"].id,
                       quantity=5).status_code == 200


def test_a_frozen_house_storage_can_only_be_looked_at(env):
    env["db"].execute(text("UPDATE houses SET status = 'frozen'"))
    env["db"].commit()
    state = env["state"](OWNER, 1)
    assert state.status_code == 200 and state.json()["frozen"] is True
    r = env["call"]("put", OWNER, character_id=1, inventory_item_id=env["rows"]["ore"].id, quantity=1)
    assert r.status_code == 409 and r.json()["detail"] == house_storage.FROZEN


def test_putting_and_taking_need_the_character_in_a_storage_room(env):
    """Stage 7: standing in the house's location, or in another room of it, is not enough."""
    db, ore = env["db"], env["rows"]["ore"].id
    for room in (1, None):  # the hall, then outside the house
        db.execute(text("UPDATE characters SET house_room_id = :r WHERE id = 1"), {"r": room})
        db.commit()
        r = env["call"]("put", OWNER, character_id=1, inventory_item_id=ore, quantity=1)
        assert r.status_code == 403 and r.json()["detail"] == house_storage.GO_TO_STORAGE
        state = env["state"](OWNER, 1).json()
        assert (state["at_house"], state["in_storage"]) == (True, False)
    assert _stored(db) == []
    # A cellar serves as well; a storage of another house does not.
    db.execute(text("INSERT INTO house_rooms (id, house_id, room_type) VALUES (3, :h, 'cellar'), (4, 99, 'storage')"),
               {"h": HOUSE})
    db.execute(text("UPDATE characters SET house_room_id = 4 WHERE id = 1"))
    db.commit()
    assert env["call"]("put", OWNER, character_id=1, inventory_item_id=ore, quantity=1).status_code == 403
    db.execute(text("UPDATE characters SET house_room_id = 3 WHERE id = 1"))
    db.commit()
    assert env["call"]("put", OWNER, character_id=1, inventory_item_id=ore, quantity=1).status_code == 200
    assert env["state"](OWNER, 1).json()["in_storage"] is True
    # Taking needs the same.
    sid = env["state"](OWNER, 1).json()["items"][0]["id"]
    db.execute(text("UPDATE characters SET house_room_id = 1 WHERE id = 1"))
    db.commit()
    r = env["call"]("take", OWNER, character_id=1, storage_item_id=sid, quantity=1)
    assert r.status_code == 403 and r.json()["detail"] == house_storage.GO_TO_STORAGE
