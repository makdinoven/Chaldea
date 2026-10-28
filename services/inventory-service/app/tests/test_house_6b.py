"""FEAT-180 stage 6b in inventory-service.

* house blessings (`house_buffs`: library -> all character XP, shrine -> post or
  gathering XP) and elite trophies (battle XP) add to `crud.get_xp_multiplier`,
  each once per call, and are ignored when the tables are missing;
* the item flags `is_elite_trophy` (resource / trophy only) and `is_home_teleport`
  (scroll only);
* the home teleport scroll: targets, the move through character-service (stubbed),
  the scroll spent or kept by the circle, nothing spent when the move fails.

The locations-service tables are minimal stand-ins created per test.
"""

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import text

import crud
import home_teleport
import house_workshop
import models
import schemas
from auth_http import UserRead, get_current_user_via_http

pytestmark = pytest.mark.real_activity_lock

CID, OTHER, STRANGER = 7, 8, 9
HOUSE, TOWN, FAR = 5, 100, 200

_TABLES = ("characters", "houses", "house_plots", "house_rooms", "house_residents", "house_resident_rooms",
           "house_furniture", "house_buffs", "Locations")

ALL_CHAR = schemas.XP_BUFF_CHARACTER_ALL
QUEST = schemas.XP_BUFF_CHARACTER_QUEST
POST = schemas.XP_BUFF_CHARACTER_POST
BATTLE = schemas.XP_BUFF_CHARACTER_BATTLE
GATHERING = schemas.XP_BUFF_GATHERING
PROFESSION = schemas.XP_BUFF_PROFESSION


def _drop(db):
    for t in _TABLES:
        db.execute(text(f"DROP TABLE IF EXISTS {t}"))
    db.commit()


@pytest.fixture()
def house(db_session):
    db = db_session
    _drop(db)
    db.execute(text("CREATE TABLE characters (id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT, "
                    "current_location_id INTEGER, dungeon_session_id INTEGER, unconscious_until DATETIME, "
                    "asleep_since DATETIME, reading_since DATETIME)"))
    db.execute(text("INSERT INTO characters (id, user_id, name, current_location_id) VALUES "
                    "(:a, 1, 'Owner', :far), (:b, 2, 'Resident', :far), (:c, 3, 'Stranger', :far)"),
               {"a": CID, "b": OTHER, "c": STRANGER, "far": FAR})
    db.execute(text("CREATE TABLE \"Locations\" (id INTEGER PRIMARY KEY, name TEXT)"))
    db.execute(text("INSERT INTO \"Locations\" VALUES (:t, 'Town'), (:f, 'Far')"), {"t": TOWN, "f": FAR})
    db.execute(text("CREATE TABLE house_plots (id INTEGER PRIMARY KEY, location_id INTEGER)"))
    db.execute(text("CREATE TABLE houses (id INTEGER PRIMARY KEY, plot_id INTEGER, owner_character_id INTEGER, "
                    "name TEXT, status TEXT DEFAULT 'active')"))
    db.execute(text("CREATE TABLE house_rooms (id INTEGER PRIMARY KEY, house_id INTEGER, room_type TEXT, "
                    "level INTEGER DEFAULT 1, upgrade_to_level INTEGER, upgrade_complete_at TIMESTAMP)"))
    db.execute(text("CREATE TABLE house_residents (id INTEGER PRIMARY KEY, house_id INTEGER, character_id INTEGER)"))
    db.execute(text("CREATE TABLE house_resident_rooms (id INTEGER PRIMARY KEY, resident_id INTEGER, "
                    "room_id INTEGER)"))
    db.execute(text("CREATE TABLE house_furniture (id INTEGER PRIMARY KEY, room_id INTEGER, item_id INTEGER)"))
    db.execute(text("CREATE TABLE house_buffs (id INTEGER PRIMARY KEY, character_id INTEGER, source TEXT, "
                    "kind TEXT, value REAL, expires_at TIMESTAMP)"))
    db.execute(text("INSERT INTO house_plots VALUES (1, :t)"), {"t": TOWN})
    db.execute(text("INSERT INTO houses (id, plot_id, owner_character_id, name) VALUES (:h, 1, :o, 'Мельница')"),
               {"h": HOUSE, "o": CID})
    db.commit()
    yield db
    _drop(db)


def _room(db, room_type, level=1, house_id=HOUSE):
    db.execute(text("INSERT INTO house_rooms (house_id, room_type, level) VALUES (:h, :t, :l)"),
               {"h": house_id, "t": room_type, "l": level})
    db.commit()
    return db.execute(text("SELECT MAX(id) FROM house_rooms")).scalar()


def _blessing(db, source, kind, value, cid=CID, hours=5):
    db.execute(text("INSERT INTO house_buffs (character_id, source, kind, value, expires_at) "
                    "VALUES (:c, :s, :k, :v, :e)"),
               {"c": cid, "s": source, "k": kind, "v": value,
                "e": (datetime.utcnow() + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")})
    db.commit()


def _item(db, name, item_type="resource", **kw):
    it = models.Items(name=name, item_type=item_type, item_rarity="common", item_level=1, max_stack_size=10,
                      is_unique=False, **kw)
    db.add(it)
    db.commit()
    return it


def _trophies(db, room_id, count, elite=True):
    item = _item(db, f"Клык {room_id} {count} {elite}", resource_subcategory="trophy", is_elite_trophy=elite)
    for _ in range(count):
        db.execute(text("INSERT INTO house_furniture (room_id, item_id) VALUES (:r, :i)"), {"r": room_id, "i": item.id})
    db.commit()


def _mult(db, buff_type, cid=CID):
    return round(crud.get_xp_multiplier(db, cid, buff_type), 6)


# --- the XP multiplier -----------------------------------------------------------

def test_library_blessing_speeds_up_every_character_xp_once(house):
    _blessing(house, "library", "character_xp", 0.05)
    for bt in house_workshop.CHARACTER_XP_TYPES:
        assert _mult(house, bt) == 1.05, bt
    assert _mult(house, PROFESSION) == 1.0 and _mult(house, GATHERING) == 1.0
    # With an umbrella book the house value is still added once, not per chain step.
    crud.apply_buff(house, character_id=CID, buff_type=ALL_CHAR, value=0.10, duration_minutes=60, source_name="Книга")
    house.commit()
    assert _mult(house, QUEST) == 1.15 and _mult(house, ALL_CHAR) == 1.15


def test_shrine_blessings_go_to_their_source(house):
    _blessing(house, "shrine", "post_xp", 0.10)
    assert _mult(house, POST) == 1.10 and _mult(house, QUEST) == 1.0 and _mult(house, GATHERING) == 1.0
    house.execute(text("UPDATE house_buffs SET kind = 'gathering_xp'"))
    house.commit()
    assert _mult(house, GATHERING) == 1.10 and _mult(house, POST) == 1.0
    house.execute(text("UPDATE house_buffs SET kind = 'regen'"))
    house.commit()
    assert all(_mult(house, bt) == 1.0 for bt in (POST, GATHERING, ALL_CHAR))


def test_expired_and_foreign_blessings_count_nothing(house):
    _blessing(house, "library", "character_xp", 0.05, hours=-1)
    _blessing(house, "shrine", "post_xp", 0.15, cid=OTHER)
    assert _mult(house, POST) == 1.0


def test_trophies_speed_up_battle_xp_for_the_owner_and_residents(house):
    hall = _room(house, "trophy_hall")
    _trophies(house, hall, 7)                 # level 1 holds 5
    _trophies(house, hall, 2, elite=False)    # plain trophies count nothing
    assert _mult(house, BATTLE) == 1.05 and _mult(house, QUEST) == 1.0
    _blessing(house, "library", "character_xp", 0.03)
    assert _mult(house, BATTLE) == 1.08
    house.execute(text("INSERT INTO house_residents (house_id, character_id) VALUES (:h, :c)"),
                  {"h": HOUSE, "c": OTHER})
    house.commit()
    assert _mult(house, BATTLE, cid=OTHER) == 1.05 and _mult(house, BATTLE, cid=STRANGER) == 1.0
    house.execute(text("UPDATE houses SET status = 'frozen'"))
    house.commit()
    assert _mult(house, BATTLE, cid=OTHER) == 1.0


def test_trophies_take_the_best_house_and_cap_at_fifteen(house):
    first = _room(house, "trophy_hall", level=3)
    _trophies(house, first, 9)
    house.execute(text("INSERT INTO houses (id, plot_id, owner_character_id, name) VALUES (6, NULL, :o, 'x')"),
                  {"o": CID})
    house.execute(text("INSERT INTO house_plots VALUES (2, :t)"), {"t": TOWN})
    house.execute(text("UPDATE houses SET plot_id = 2 WHERE id = 6"))
    house.commit()
    a, b = _room(house, "trophy_hall", level=3, house_id=6), _room(house, "trophy_hall", level=3, house_id=6)
    _trophies(house, a, 10)
    _trophies(house, b, 10)
    assert house_workshop.trophy_bonus(house, CID) == house_workshop.TROPHY_BONUS_CAP
    house.execute(text("DELETE FROM house_furniture WHERE room_id IN (:a, :b)"), {"a": a, "b": b})
    house.commit()
    assert house_workshop.trophy_bonus(house, CID) == 0.09


def test_missing_house_tables_add_nothing(db_session):
    _drop(db_session)
    assert house_workshop.house_buffs(db_session, CID) == {}
    assert house_workshop.trophy_bonus(db_session, CID) == 0.0
    assert house_workshop.house_xp_bonus(db_session, CID, BATTLE) == 0.0
    assert house_workshop.return_circles(db_session, CID) == []
    assert crud.get_xp_multiplier(db_session, CID, BATTLE) == 1.0


# --- item flags --------------------------------------------------------------------

def _payload(**over):
    body = {"name": "x", "item_level": 1, "item_type": "resource", "item_rarity": "common",
            "max_stack_size": 10, "is_unique": False}
    body.update(over)
    return body


def test_only_a_trophy_is_elite_and_only_a_scroll_carries_home():
    assert schemas.ItemCreate(**_payload(resource_subcategory="trophy", is_elite_trophy=True)).is_elite_trophy
    for bad in (_payload(is_elite_trophy=True), _payload(resource_subcategory="ore", is_elite_trophy=True),
                _payload(item_type="misc", is_elite_trophy=True)):
        with pytest.raises(ValueError, match="Элитным"):
            schemas.ItemCreate(**bad)
    assert schemas.ItemCreate(**_payload(item_type="scroll", is_home_teleport=True)).is_home_teleport
    with pytest.raises(ValueError, match="Свитком возвращения"):
        schemas.ItemCreate(**_payload(is_home_teleport=True))


def test_admin_create_rejects_a_misplaced_flag(client, db_session):
    from main import app
    admin = UserRead(id=1, username="a", role="admin", permissions=["items:create", "items:update"])
    app.dependency_overrides[get_current_user_via_http] = lambda: admin
    try:
        r = client.post("/inventory/items", json=_payload(name="Свиток", item_type="misc", is_home_teleport=True))
        assert r.status_code == 422
        r = client.post("/inventory/items", json=_payload(name="Свиток", item_type="scroll", is_home_teleport=True))
        assert r.status_code in (200, 201), r.text
        assert r.json()["is_home_teleport"] is True and r.json()["is_elite_trophy"] is False
    finally:
        app.dependency_overrides.pop(get_current_user_via_http, None)


# --- the home teleport scroll ---------------------------------------------------------

@pytest.fixture()
def scroll(house, client, monkeypatch):
    from main import app
    item = _item(house, "Свиток возвращения", item_type="scroll", is_home_teleport=True)
    row = models.CharacterInventory(character_id=CID, item_id=item.id, quantity=2)
    house.add(row)
    house.commit()
    who = {"id": 1}
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=who["id"], username="u", role="user", permissions=[])
    moves, state = [], {"keep": False}

    async def _move(character_id, location_id, house_room_id=None):
        moves.append((character_id, location_id, house_room_id))
        if state.get("raise"):
            raise state["raise"]
        return {"location_name": "Town"}

    monkeypatch.setattr(home_teleport, "move_home", _move)
    monkeypatch.setattr(home_teleport, "keep_roll", lambda chance: state["keep"])

    def use(cid=CID, house_id=HOUSE, row_id=None, uid=None):
        if uid is not None:
            who["id"] = uid
        return client.post(f"/inventory/{cid}/home-teleport",
                           json={"inventory_item_id": row_id or row.id, "house_id": house_id})

    def left():
        house.expire_all()
        return sum(r.quantity for r in house.query(models.CharacterInventory).filter_by(item_id=item.id))

    yield {"use": use, "left": left, "moves": moves, "state": state, "row": row, "who": who, "client": client}
    app.dependency_overrides.pop(get_current_user_via_http, None)


def test_targets_are_houses_with_a_built_circle(house, scroll):
    assert scroll["client"].get(f"/inventory/{CID}/home-teleport/targets").json() == []
    _room(house, "return_circle", level=2)
    targets = scroll["client"].get(f"/inventory/{CID}/home-teleport/targets").json()
    circle = house.execute(text("SELECT MAX(id) FROM house_rooms")).scalar()
    assert targets == [{"house_id": HOUSE, "name": "Мельница", "location_id": TOWN, "circle_level": 2,
                        "room_id": circle, "keep_chance": house_workshop.CIRCLE_KEEP_CHANCE[2],
                        "location_name": "Town"}]
    scroll["who"]["id"] = 3
    assert scroll["client"].get(f"/inventory/{CID}/home-teleport/targets").status_code == 403


def test_a_resident_needs_to_be_let_into_the_circle(house, scroll):
    circle = _room(house, "return_circle")
    house.execute(text("INSERT INTO house_residents (id, house_id, character_id) VALUES (1, :h, :c)"),
                  {"h": HOUSE, "c": OTHER})
    house.commit()
    assert house_workshop.return_circles(house, OTHER) == []
    house.execute(text("INSERT INTO house_resident_rooms (resident_id, room_id) VALUES (1, :r)"), {"r": circle})
    house.commit()
    assert [t["house_id"] for t in house_workshop.return_circles(house, OTHER)] == [HOUSE]
    _room(house, "return_circle", level=0)  # being built: not counted
    assert house_workshop.return_circles(house, CID)[0]["circle_level"] == 1


def test_reading_the_scroll_moves_home_and_spends_it(house, scroll):
    circle = _room(house, "return_circle")
    r = scroll["use"]()
    assert r.status_code == 200, r.text
    # Stage 7: the character arrives inside the house, standing in the return circle.
    assert r.json() == {"location_id": TOWN, "location_name": "Town", "house_id": HOUSE, "house_room_id": circle,
                        "scroll_kept": False}
    assert scroll["moves"] == [(CID, TOWN, circle)] and scroll["left"]() == 1


def test_the_scroll_lands_in_the_best_circle(house, scroll):
    _room(house, "return_circle", level=1)
    best = _room(house, "return_circle", level=3)
    _room(house, "return_circle", level=2)
    assert scroll["use"]().json()["house_room_id"] == best and scroll["moves"][0][2] == best


def test_move_home_asks_character_service_to_place_the_character(monkeypatch):
    import httpx

    sent = {}

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            sent.update(url=url, json=json)
            return httpx.Response(200, json={"location_name": "Town"})

    monkeypatch.setattr(home_teleport.httpx, "AsyncClient", _Client)
    import asyncio
    assert asyncio.run(home_teleport.move_home(CID, TOWN, 77)) == {"location_name": "Town"}
    assert sent["url"].endswith(f"/characters/internal/{CID}/home-teleport")
    assert sent["json"] == {"location_id": TOWN, "house_room_id": 77}


def test_the_circle_may_keep_the_scroll(house, scroll):
    _room(house, "return_circle", level=3)
    scroll["state"]["keep"] = True
    r = scroll["use"]()
    assert r.status_code == 200 and r.json()["scroll_kept"] is True and scroll["left"]() == 2


def test_a_failed_move_spends_nothing(house, scroll):
    _room(house, "return_circle")
    scroll["state"]["raise"] = HTTPException(409, "Персонаж находится в бою — перенос невозможен")
    r = scroll["use"]()
    assert r.status_code == 409 and scroll["left"]() == 2
    scroll["state"]["raise"] = HTTPException(503, home_teleport.MOVE_FAILED)
    assert scroll["use"]().status_code == 503 and scroll["left"]() == 2


def test_scroll_rules(house, scroll):
    # No circle in the house: refused.
    assert scroll["use"]().status_code == 403
    _room(house, "return_circle")
    # Already there.
    house.execute(text("UPDATE characters SET current_location_id = :t WHERE id = :c"), {"t": TOWN, "c": CID})
    house.commit()
    r = scroll["use"]()
    assert r.status_code == 400 and "уже" in r.json()["detail"]
    house.execute(text("UPDATE characters SET current_location_id = :f WHERE id = :c"), {"f": FAR, "c": CID})
    # Reading in a library locks the character.
    house.execute(text("UPDATE characters SET reading_since = '2026-10-28 10:00:00' WHERE id = :c"), {"c": CID})
    house.commit()
    r = scroll["use"]()
    assert r.status_code == 409 and "читает" in r.json()["detail"]
    house.execute(text("UPDATE characters SET reading_since = NULL"))
    house.commit()
    # Not a home scroll / not this character's / someone else's character.
    plain = _item(house, "Свиток опознания", item_type="scroll")
    other_row = models.CharacterInventory(character_id=CID, item_id=plain.id, quantity=1)
    house.add(other_row)
    house.commit()
    assert scroll["use"](row_id=other_row.id).status_code == 400
    assert scroll["use"](row_id=999).status_code == 404
    assert scroll["use"](cid=STRANGER).status_code == 403
    assert scroll["moves"] == [] and scroll["left"]() == 2


def test_use_item_does_not_waste_a_home_scroll(house, scroll):
    item_id = scroll["row"].item_id
    r = scroll["client"].post(f"/inventory/{CID}/use_item", json={"item_id": item_id, "quantity": 1})
    assert r.status_code == 400 and scroll["left"]() == 2
