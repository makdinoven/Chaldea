"""FEAT-180: player houses — plots, purchase, rooms with posts, residents and their rights,
building, furniture, tax, the plan, and (stage 6a) profession rooms, cellar, garden rooms and the bath.

Routes run through TestClient against a file-backed SQLite: the schema is laid
out with a plain sync engine, each request opens its own aiosqlite session.
The shared tables of other services (characters, battles, ...) are minimal stand-ins.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import crud  # noqa: E402
import episodes  # noqa: E402
import houses  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
from auth_http import UserRead, get_current_user_via_http  # noqa: E402
from database import get_db  # noqa: E402
from main import app  # noqa: E402


@compiles(BigInteger, "sqlite")
def _bigint(type_, compiler, **kw):  # pragma: no cover - DDL hook
    return "INTEGER"


@compiles(MEDIUMTEXT, "sqlite")
def _mediumtext(type_, compiler, **kw):  # pragma: no cover - DDL hook
    return "TEXT"


OWNER, FRIEND, STRANGER, ADMIN = 1, 2, 3, 5
ROLES = {ADMIN: "admin"}
ADMIN_PERMS = ["locations:read", "locations:create", "locations:update", "locations:delete"]
TOWN, FAR = 100, 200
REGION = 7
# character id: (user, location, gold, is_npc)
CHARS = {
    10: (OWNER, TOWN, 1000, 0),
    11: (OWNER, FAR, 1000, 0),
    20: (FRIEND, TOWN, 50, 0),
    30: (STRANGER, TOWN, 5000, 0),
    40: (None, TOWN, 0, 1),
}
IMG = "https://s3.example/bucket/episode_images/a.webp"
LONG = "<p>" + "Слово " * 60 + "</p>"

TABLES = [models.Region, models.District, models.Location, models.HousePlot, models.HousePlotRoom,
          models.House, models.HouseRoom, models.HouseResident, models.HouseResidentRoom, models.HousePost,
          models.HouseBuildCost, models.HouseBuildCostItem, models.HouseFurniture, models.HouseSettings,
          models.GameTimeConfig, models.HousePlotLayer, models.HousePlotCell, models.HouseLayerUnlock,
          models.HouseCellUnlock, models.HouseGardenBed, models.HouseBathUse, models.HouseBuff,
          models.HouseShrineUse, models.HouseGuest]


@pytest.fixture()
def api(tmp_path, monkeypatch):
    path = tmp_path / "houses.db"
    sync = create_engine(f"sqlite:///{path}")
    with sync.begin() as conn:
        for m in TABLES:
            m.__table__.create(conn)
        conn.execute(text(
            "CREATE TABLE characters (id INTEGER PRIMARY KEY, name TEXT, avatar TEXT, user_id INTEGER, "
            "current_location_id INTEGER, currency_balance INTEGER, is_npc INTEGER, "
            "dungeon_session_id INTEGER, unconscious_until TIMESTAMP, asleep_since TIMESTAMP, "
            "sleep_regen_factor REAL, sleep_house_room_id INTEGER, reading_since TIMESTAMP, "
            "reading_house_room_id INTEGER, house_room_id INTEGER)"))
        for cid, (uid, loc, gold, npc) in CHARS.items():
            conn.execute(text("INSERT INTO characters VALUES (:i, :n, NULL, :u, :l, :g, :npc, NULL, NULL, "
                              "NULL, NULL, NULL, NULL, NULL, NULL)"),
                         {"i": cid, "n": f"Герой {cid}", "u": uid, "l": loc, "g": gold, "npc": npc})
        conn.execute(text("CREATE TABLE battles (id INTEGER PRIMARY KEY, status TEXT)"))
        conn.execute(text("CREATE TABLE battle_participants (battle_id INTEGER, character_id INTEGER, "
                          "dropped_out_at TIMESTAMP)"))
        conn.execute(text("CREATE TABLE gold_transactions (id INTEGER PRIMARY KEY, character_id INTEGER, "
                          "amount INTEGER, balance_after INTEGER, transaction_type TEXT, source TEXT, metadata TEXT)"))
        # inventory-service tables the building and storage checks read
        conn.execute(text(
            "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT, image TEXT, item_type TEXT DEFAULT 'resource', "
            "item_rarity TEXT DEFAULT 'common', description TEXT, max_stack_size INTEGER DEFAULT 10, "
            "furniture_room_type TEXT, furniture_sleep_bonus REAL DEFAULT 0, furniture_storage_stacks INTEGER DEFAULT 0, "
            "furniture_xp_bonus_pct REAL DEFAULT 0, furniture_refine_bonus_pct REAL DEFAULT 0, "
            "seed_result_item_id INTEGER, seed_result_quantity INTEGER, seed_grow_hours INTEGER, "
            "seed_room_type TEXT, seed_herbalism_xp INTEGER, resource_subcategory TEXT, "
            "is_elite_trophy INTEGER DEFAULT 0)"))
        conn.execute(text("INSERT INTO items (id, name) VALUES (1, 'Доска'), (2, 'Гвоздь')"))
        conn.execute(text(
            "INSERT INTO items (id, name, item_type, furniture_room_type, furniture_sleep_bonus, "
            "furniture_storage_stacks, max_stack_size) VALUES "
            "(10, 'Кровать', 'furniture', 'bedroom', 0.5, 0, 1), (11, 'Сундук', 'furniture', 'storage', 0, 10, 5), "
            "(12, 'Гобелен', 'furniture', 'hall', 0, 0, 5)"))
        conn.execute(text("CREATE TABLE character_inventory (id INTEGER PRIMARY KEY, character_id INTEGER, "
                          "item_id INTEGER, quantity INTEGER, enhancement_points_spent INTEGER DEFAULT 0, "
                          "socketed_gems TEXT, current_durability INTEGER)"))
        conn.execute(text("CREATE TABLE house_storage (id INTEGER PRIMARY KEY, house_id INTEGER)"))
        conn.execute(text("CREATE TABLE professions (id INTEGER PRIMARY KEY, name TEXT, slug TEXT)"))
        for pid, slug in enumerate(("blacksmith", "alchemist", "cook", "enchanter", "jeweler", "scholar"), 1):
            conn.execute(text("INSERT INTO professions VALUES (:i, :n, :s)"), {"i": pid, "n": slug, "s": slug})
        conn.execute(text("CREATE TABLE character_attributes (character_id INTEGER PRIMARY KEY, max_health INTEGER, "
                          "max_mana INTEGER, max_energy INTEGER, max_stamina INTEGER)"))
        conn.execute(text("INSERT INTO character_attributes VALUES (10, 200, 100, 50, 120), (20, 100, 100, 100, 100)"))
        for rt in houses.ROOM_TYPES:
            for lvl, (gold, hours) in {1: (100, 0), 2: (200, 0), 3: (300, 0)}.items():
                conn.execute(text("INSERT INTO house_build_costs (room_type, level, gold, build_hours) "
                                  "VALUES (:t, :l, :g, :h)"), {"t": rt, "l": lvl, "g": gold, "h": hours})
        conn.execute(text("INSERT INTO Regions (id, name, country_id, description) VALUES (:r, 'Край', 1, '')"),
                     {"r": REGION})
        conn.execute(text("INSERT INTO Districts (id, name, region_id, description, sort_order) "
                          "VALUES (1, 'Город', :r, '', 0)"), {"r": REGION})
        for lid in (TOWN, FAR):
            conn.execute(text(
                "INSERT INTO Locations (id, name, district_id, type, recommended_level, quick_travel_marker, "
                "description, marker_type, sort_order, no_quick_move, is_starting) "
                "VALUES (:i, :n, 1, 'location', 1, 0, '', 'safe', 0, 0, 0)"), {"i": lid, "n": f"Улица {lid}"})
    sync.dispose()

    engine = create_async_engine(f"sqlite+aiosqlite:///{path}", poolclass=NullPool)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _db():
        async with Session() as s:
            yield s

    who = {"id": None}

    def _user():
        uid = who["id"]
        return UserRead(id=uid, username=f"u{uid}", role=ROLES.get(uid, "user"),
                        permissions=ADMIN_PERMS if uid == ADMIN else [])

    def _viewer():
        return _user() if who["id"] else None

    xp = []

    async def _award(*args):
        xp.append(args)

    async def _quiet(*args, **kwargs):
        return None

    monkeypatch.setattr(crud, "award_post_xp_and_log", _award)
    monkeypatch.setattr(main, "_track_cumulative_stats", _quiet)
    monkeypatch.setattr(main, "_auto_progress_quest", _quiet)
    # Its query uses MySQL's NOW(); the gathering check is not what these tests are about.
    monkeypatch.setattr(main, "check_not_gathering", _quiet)
    settled = []

    async def _settle(character_id):
        settled.append(character_id)

    monkeypatch.setattr(houses, "_settle_regen", _settle)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user_via_http] = _user
    app.dependency_overrides[episodes.get_viewer] = _viewer

    def sql(query, **params):
        eng = create_engine(f"sqlite:///{path}")
        with eng.begin() as conn:
            rows = conn.execute(text(query), params)
            out = rows.fetchall() if rows.returns_rows else None
        eng.dispose()
        return out

    class Api:
        awarded = xp
        regen_settled = settled

        def __init__(self, client):
            self.c = client
            self.sql = sql

        def as_(self, uid):
            who["id"] = uid
            return self

        def __getattr__(self, method):
            return lambda url, json=None: getattr(self.c, method)(
                "/locations/houses" + url, **({"json": json} if json is not None else {}))

    with TestClient(app) as client:
        yield Api(client)
    app.dependency_overrides.clear()


def _layout(cells, width=None):
    """A first floor of `cells` open cells in one row."""
    width = width or cells
    return {"grid_w": width, "grid_h": -(-cells // width), "layers": [{"layer": "floor1"}],
            "cells": [{"layer": "floor1", "x": i % width, "y": i // width} for i in range(cells)]}


def _cell(api, hid):
    """{"cell_id": ...} of the first free place of the house (the first place when none is free)."""
    cells = api.as_(OWNER).get(f"/{hid}").json()["plan"]["cells"]
    free = [c for c in cells if c["unlocked"] and not c["room_id"]]
    return {"cell_id": (free or cells)[0]["id"]}


def _plot(api, price=300, **over):
    body = {"location_id": TOWN, "name": "Дом у мельницы", "description": "Старый дом", "image_url": IMG,
            "price": price, "map_x": 40.5, "map_y": 60.0, **_layout(4, 2),
            "rooms": [{"room_type": "hall", "name": "Гостиная", "description": "Камин", "x": 0, "y": 0},
                      {"room_type": "bedroom", "name": "Спальня", "x": 1, "y": 0},
                      {"room_type": "storage", "name": "Кладовая", "x": 0, "y": 1}]}
    body.update(over)
    r = api.as_(ADMIN).post("/admin/plots", body)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _house(api):
    """A bought house of character 10 (OWNER); returns (house_id, {room_type: room_id})."""
    pid = _plot(api)
    r = api.as_(OWNER).post(f"/plots/{pid}/buy", {"character_id": 10})
    assert r.status_code == 200, r.text
    hid = r.json()["house_id"]
    rooms = {x["room_type"]: x["id"] for x in api.get(f"/{hid}").json()["rooms"]}
    return hid, rooms


def _gold(api, cid):
    return api.sql("SELECT currency_balance FROM characters WHERE id = :c", c=cid)[0][0]


def _go(api, uid, cid, room_id):
    """The character walks into the room through the API (stage 7)."""
    r = api.as_(uid).post(f"/rooms/{room_id}/go", {"character_id": cid})
    assert r.status_code == 200, r.text
    return api


def _in(api, cid, room_id):
    """Puts the character into the room straight in the table (stage 7), whether let in or not."""
    api.sql("UPDATE characters SET house_room_id = :r WHERE id = :c", r=room_id, c=cid)


def _where(api, cid):
    return api.sql("SELECT house_room_id FROM characters WHERE id = :c", c=cid)[0][0]


# --- plots ------------------------------------------------------------------

def test_admin_lays_out_a_plot_in_the_location_region(api):
    pid = _plot(api)
    plots = api.as_(None).get(f"/by-location/{TOWN}").json()
    assert [(p["id"], p["region_id"], p["room_count"], p["house"]) for p in plots] == [(pid, REGION, 3, None)]
    assert [p["id"] for p in api.get(f"/by-region/{REGION}").json()] == [pid]
    assert len(api.get(f"/plots/{pid}").json()["rooms"]) == 3


def test_plot_rooms_must_fit_and_admin_rights_are_needed(api):
    r = api.as_(ADMIN).post("/admin/plots", {"location_id": TOWN, "name": "Тесно", "price": 1, **_layout(1),
                                             "rooms": [{"room_type": "hall", "name": "a", "x": 0, "y": 0},
                                                       {"room_type": "bedroom", "name": "b", "x": 0, "y": 0}]})
    assert r.status_code == 422
    r = api.as_(ADMIN).post("/admin/plots", {"location_id": TOWN, "name": "Пусто", "price": 1, **_layout(1),
                                             "rooms": []})
    assert r.status_code == 422
    r = api.as_(ADMIN).post("/admin/plots", {"location_id": TOWN, "name": "Чужая", "price": 1, **_layout(1),
                                             "image_url": "https://evil.example/x.png",
                                             "rooms": [{"room_type": "hall", "name": "a", "x": 0, "y": 0}]})
    assert r.status_code == 422
    r = api.as_(OWNER).post("/admin/plots", {"location_id": TOWN, "name": "x", "price": 1, **_layout(1),
                                             "rooms": [{"room_type": "hall", "name": "a", "x": 0, "y": 0}]})
    assert r.status_code == 403


# --- purchase ---------------------------------------------------------------

def test_buying_takes_gold_and_copies_the_rooms(api):
    hid, rooms = _house(api)
    assert _gold(api, 10) == 700
    house = api.as_(OWNER).get(f"/{hid}").json()
    assert house["is_owner"] and house["owner"]["id"] == 10
    assert {r["room_type"]: r["is_open"] for r in house["rooms"]} == {"hall": True, "bedroom": False, "storage": False}
    plot = api.get(f"/by-location/{TOWN}").json()[0]
    assert plot["house"]["owner"]["id"] == 10


def test_buying_needs_presence_gold_and_a_free_plot(api):
    pid = _plot(api, price=300)
    assert api.as_(OWNER).post(f"/plots/{pid}/buy", {"character_id": 11}).status_code == 400  # elsewhere
    assert api.as_(FRIEND).post(f"/plots/{pid}/buy", {"character_id": 20}).status_code == 400  # 50 gold
    assert _gold(api, 20) == 50
    assert api.as_(None).get(f"/by-location/{TOWN}").json()[0]["house"] is None
    assert api.as_(FRIEND).post(f"/plots/{pid}/buy", {"character_id": 10}).status_code == 403  # not theirs
    assert api.as_(OWNER).post(f"/plots/{pid}/buy", {"character_id": 10}).status_code == 200
    assert api.as_(STRANGER).post(f"/plots/{pid}/buy", {"character_id": 30}).status_code == 409
    assert _gold(api, 30) == 5000


def test_a_plot_with_a_house_cannot_be_deleted(api):
    hid, _ = _house(api)
    pid = api.as_(OWNER).get(f"/{hid}").json()["plot_id"]
    assert api.as_(ADMIN).delete(f"/admin/plots/{pid}").status_code == 409
    free = _plot(api)
    assert api.as_(ADMIN).delete(f"/admin/plots/{free}").status_code == 200


# --- reading and writing rooms ----------------------------------------------

def test_closed_rooms_are_read_by_residents_and_the_admin_only(api):
    hid, rooms = _house(api)
    # Stage 7: nobody outside the house looks in, not even into an open hall.
    for uid in (None, STRANGER):
        r = api.as_(uid).get(f"/rooms/{rooms['hall']}")
        assert r.status_code == 403 and r.json()["detail"] == houses.NOT_A_MEMBER
    assert api.as_(STRANGER).get(f"/rooms/{rooms['bedroom']}").status_code == 403
    assert api.as_(OWNER).get(f"/rooms/{rooms['bedroom']}").status_code == 200
    assert api.as_(ADMIN).get(f"/rooms/{rooms['bedroom']}").status_code == 200
    outsider = api.as_(STRANGER).get(f"/{hid}").json()
    assert outsider["residents"] == [] and outsider["acting"] == [] and outsider["rooms"] == []
    assert outsider["can_view_inside"] is False and outsider["plan"] is None and outsider["tax"] is None
    assert (outsider["name"], outsider["owner"]["id"], outsider["location_id"]) == ("Дом у мельницы", 10, TOWN)


def test_owner_posts_in_the_house_location_and_gets_experience(api):
    hid, rooms = _house(api)
    _go(api, OWNER, 10, rooms["hall"])
    short = api.as_(OWNER).post(f"/rooms/{rooms['hall']}/posts", {"character_id": 10, "content": "<p>Привет</p>"})
    assert short.status_code == 400
    r = api.post(f"/rooms/{rooms['hall']}/posts", {"character_id": 10, "content": LONG})
    assert r.status_code == 200, r.text
    assert r.json()["can_edit"] and r.json()["character"]["id"] == 10
    (args,) = api.awarded
    assert args[0] == 10 and args[2] == TOWN and "Дом у мельницы" in args[3]
    room = api.get(f"/rooms/{rooms['hall']}").json()
    assert [p["id"] for p in room["posts"]] == [r.json()["id"]] and [w["id"] for w in room["writers"]] == [10]
    assert room["writers"][0]["in_room"] is True and [c["id"] for c in room["present"]] == [10]


def test_writing_needs_access_and_presence(api):
    hid, rooms = _house(api)
    # A stranger standing right there is not let in.
    assert api.as_(STRANGER).post(f"/rooms/{rooms['hall']}/posts",
                                  {"character_id": 30, "content": LONG}).status_code == 403
    # The owner away from the house cannot write either.
    api.sql("UPDATE characters SET current_location_id = :l WHERE id = 10", l=FAR)
    r = api.as_(OWNER).post(f"/rooms/{rooms['hall']}/posts", {"character_id": 10, "content": LONG})
    assert r.status_code == 403 and "Дойдите" in r.json()["detail"]
    assert api.awarded == []


# --- residents --------------------------------------------------------------

def test_a_resident_enters_halls_by_default_and_rooms_as_allowed(api):
    hid, rooms = _house(api)
    rid = api.as_(OWNER).post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20}).json()["id"]
    house = api.as_(FRIEND).get(f"/{hid}").json()
    assert house["acting"][0]["room_ids"] == [rooms["hall"]]
    _go(api, FRIEND, 20, rooms["hall"])
    assert api.post(f"/rooms/{rooms['hall']}/posts", {"character_id": 20, "content": LONG}).status_code == 200
    assert api.post(f"/rooms/{rooms['bedroom']}/posts", {"character_id": 20, "content": LONG}).status_code == 403
    assert api.get(f"/rooms/{rooms['bedroom']}").status_code == 403

    r = api.as_(OWNER).put(f"/{hid}/residents/{rid}", {"character_id": 10, "room_ids": [rooms["bedroom"]],
                                                         "can_take": True, "can_put": False})
    assert r.status_code == 200
    assert _where(api, 20) is None  # out of the hall it is no longer let into
    _go(api, FRIEND, 20, rooms["bedroom"])
    assert api.as_(FRIEND).post(f"/rooms/{rooms['bedroom']}/posts", {"character_id": 20, "content": LONG}).status_code == 200
    assert api.post(f"/rooms/{rooms['hall']}/posts", {"character_id": 20, "content": LONG}).status_code == 403
    me = api.get(f"/{hid}").json()["acting"][0]
    assert (me["can_take"], me["can_put"]) == (True, False)


def test_resident_rules(api):
    hid, rooms = _house(api)
    assert api.as_(OWNER).post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 10}).status_code == 400
    assert api.post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 40}).status_code == 404  # NPC
    assert api.as_(FRIEND).post(f"/{hid}/residents", {"character_id": 20, "resident_character_id": 30}).status_code == 403
    rid = api.as_(OWNER).post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20}).json()["id"]
    assert api.post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20}).status_code == 409
    other = _plot(api)
    assert api.as_(STRANGER).post(f"/plots/{other}/buy", {"character_id": 30}).status_code == 200
    foreign_room = api.as_(STRANGER).get("/my").json()[0]["id"]
    foreign_room = api.get(f"/{foreign_room}").json()["rooms"][0]["id"]
    r = api.as_(OWNER).put(f"/{hid}/residents/{rid}", {"character_id": 10, "room_ids": [foreign_room]})
    assert r.status_code == 400
    # A stranger cannot send the resident away; the resident moves out alone.
    assert api.as_(STRANGER).delete(f"/{hid}/residents/{rid}?character_id=30").status_code == 403
    assert api.as_(FRIEND).delete(f"/{hid}/residents/{rid}?character_id=20").status_code == 200
    assert api.as_(OWNER).get(f"/{hid}").json()["residents"] == []


def test_my_houses_lists_owned_and_shared_ones(api):
    hid, _ = _house(api)
    api.as_(OWNER).post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20})
    assert [(h["id"], h["status"], h["character"]["id"]) for h in api.as_(OWNER).get("/my").json()] == [(hid, "owner", 10)]
    assert [(h["id"], h["status"]) for h in api.as_(FRIEND).get("/my").json()] == [(hid, "resident")]
    assert api.as_(STRANGER).get("/my").json() == []


# --- owner's settings and moderation ----------------------------------------

def test_only_the_owner_changes_the_house_and_its_rooms(api):
    hid, rooms = _house(api)
    body = {"character_id": 10, "name": "Мой дом", "description": "Уютно", "image_url": IMG}
    assert api.as_(OWNER).put(f"/{hid}", body).status_code == 200
    api.post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20})
    assert api.as_(FRIEND).get(f"/rooms/{rooms['bedroom']}").status_code == 403
    assert api.as_(OWNER).put(f"/{hid}/rooms/{rooms['bedroom']}", {"character_id": 10, "name": "Опочивальня",
                                                                  "is_open": True}).status_code == 200
    # Stage 7: an open room is read by everyone let into the house, still by nobody outside.
    assert api.as_(FRIEND).get(f"/rooms/{rooms['bedroom']}").status_code == 200
    assert api.as_(None).get(f"/rooms/{rooms['bedroom']}").status_code == 403
    assert api.as_(OWNER).put(f"/{hid}", {**body, "character_id": 11}).status_code == 403  # not the owner char
    assert api.as_(STRANGER).put(f"/{hid}", {**body, "character_id": 30}).status_code == 403
    assert api.as_(OWNER).get(f"/{hid}").json()["name"] == "Мой дом"


def test_post_edit_and_delete_rights(api):
    hid, rooms = _house(api)
    api.as_(OWNER).post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20})
    _in(api, 20, rooms["hall"])
    pid = api.as_(FRIEND).post(f"/rooms/{rooms['hall']}/posts", {"character_id": 20, "content": LONG}).json()["id"]
    assert api.as_(OWNER).put(f"/posts/{pid}", {"content": LONG}).status_code == 403
    edited = api.as_(FRIEND).put(f"/posts/{pid}", {"content": LONG + "<p>ещё</p>"})
    assert edited.status_code == 200 and edited.json()["edited_at"]
    assert api.as_(STRANGER).delete(f"/posts/{pid}").status_code == 403
    assert api.as_(OWNER).delete(f"/posts/{pid}").status_code == 200


def test_character_search_skips_npcs(api):
    found = api.as_(OWNER).get("/character-search?q=Герой").json()
    assert sorted(c["id"] for c in found) == [10, 11, 20, 30]


# --- stage 2: empty plots, building, levels ----------------------------------

def _empty_house(api, cells=2, price=50, **over):
    r = api.as_(ADMIN).post("/admin/plots", {"location_id": TOWN, "name": "Пустырь", "price": price,
                                             **_layout(cells), "kind": "empty", **over})
    assert r.status_code == 200, r.text
    r = api.as_(OWNER).post(f"/plots/{r.json()['id']}/buy", {"character_id": 10})
    assert r.status_code == 200, r.text
    return r.json()["house_id"]


def _rooms(api, hid):
    return {r["id"]: r for r in api.as_(OWNER).get(f"/{hid}").json()["rooms"]}


def test_an_empty_plot_has_no_rooms_and_needs_none(api):
    bad = api.as_(ADMIN).post("/admin/plots", {"location_id": TOWN, "name": "x", "price": 1, **_layout(1),
                                               "kind": "empty",
                                               "rooms": [{"room_type": "hall", "name": "a", "x": 0, "y": 0}]})
    assert bad.status_code == 422
    hid = _empty_house(api)
    house = api.as_(OWNER).get(f"/{hid}").json()
    assert house["plot_kind"] == "empty" and house["rooms"] == []


def test_building_takes_gold_and_materials_and_respects_the_plot_size(api):
    hid = _empty_house(api, cells=2)
    cost_id = api.sql("SELECT id FROM house_build_costs WHERE room_type = 'bedroom' AND level = 1")[0][0]
    api.sql("INSERT INTO house_build_cost_items (cost_id, item_id, quantity) VALUES (:c, 1, 5)", c=cost_id)
    api.sql("INSERT INTO character_inventory (character_id, item_id, quantity) VALUES (10, 1, 3), (10, 1, 4)")
    gold = _gold(api, 10)
    r = api.as_(OWNER).post(f"/{hid}/rooms", {**_cell(api, hid), "character_id": 10, "room_type": "bedroom", "name": "Спальня"})
    assert r.status_code == 200, r.text
    assert _gold(api, 10) == gold - 100
    assert api.sql("SELECT SUM(quantity) FROM character_inventory WHERE character_id = 10 AND item_id = 1")[0][0] == 2
    # Short of materials: nothing is taken and no room appears.
    short = api.post(f"/{hid}/rooms", {**_cell(api, hid), "character_id": 10, "room_type": "bedroom", "name": "Вторая"})
    assert short.status_code == 400 and "нужно 5, есть 2" in short.json()["detail"]
    assert len(_rooms(api, hid)) == 1 and _gold(api, 10) == gold - 100
    assert api.post(f"/{hid}/rooms", {**_cell(api, hid), "character_id": 10, "room_type": "hall", "name": "Зал"}).status_code == 200
    full = api.post(f"/{hid}/rooms", {**_cell(api, hid), "character_id": 10, "room_type": "hall", "name": "Ещё"})
    assert full.status_code == 409


def test_building_needs_the_owner_on_site_and_enough_gold(api):
    hid = _empty_house(api)
    api.sql("UPDATE characters SET current_location_id = :f WHERE id = 10", f=FAR)
    assert api.as_(OWNER).post(f"/{hid}/rooms", {**_cell(api, hid), "character_id": 10, "room_type": "hall",
                                                 "name": "x"}).status_code == 403
    api.sql("UPDATE characters SET current_location_id = :t, currency_balance = 5 WHERE id = 10", t=TOWN)
    r = api.post(f"/{hid}/rooms", {**_cell(api, hid), "character_id": 10, "room_type": "hall", "name": "x"})
    assert r.status_code == 400 and _rooms(api, hid) == {}
    cell = _cell(api, hid)
    assert api.as_(STRANGER).post(f"/{hid}/rooms", {**cell, "character_id": 30, "room_type": "hall",
                                                    "name": "x"}).status_code == 403


def test_a_room_being_built_is_unusable_until_its_time_passes(api):
    hid = _empty_house(api)
    api.sql("UPDATE house_build_costs SET build_hours = 6 WHERE room_type = 'hall' AND level = 1")
    rid = api.as_(OWNER).post(f"/{hid}/rooms", {**_cell(api, hid), "character_id": 10, "room_type": "hall",
                                                "name": "Зал"}).json()["room_id"]
    room = _rooms(api, hid)[rid]
    assert (room["level"], room["upgrade_to_level"]) == (0, 1)
    assert api.post(f"/rooms/{rid}/posts", {"character_id": 10, "content": LONG}).status_code == 409
    api.sql("UPDATE house_rooms SET upgrade_complete_at = '2000-01-01 00:00:00' WHERE id = :r", r=rid)
    room = _rooms(api, hid)[rid]
    assert (room["level"], room["upgrade_to_level"]) == (1, None)
    _go(api, OWNER, 10, rid)
    assert api.post(f"/rooms/{rid}/posts", {"character_id": 10, "content": LONG}).status_code == 200


def test_rooms_upgrade_to_level_three(api):
    hid, rooms = _house(api)
    bed = rooms["bedroom"]
    for level in (2, 3):
        r = api.as_(OWNER).post(f"/{hid}/rooms/{bed}/upgrade", {"character_id": 10})
        assert r.status_code == 200, r.text
        assert _rooms(api, hid)[bed]["level"] == level
    assert _rooms(api, hid)[bed]["sleep_factor"] == houses.BEDROOM_SLEEP_FACTOR[3]
    assert api.post(f"/{hid}/rooms/{bed}/upgrade", {"character_id": 10}).status_code == 409


def test_a_profession_room_serves_its_profession(api):
    hid = _empty_house(api)
    lab = api.as_(OWNER).post(f"/{hid}/rooms", {**_cell(api, hid), "character_id": 10, "room_type": "alchemy_lab",
                                                "name": "Лаборатория"}).json()["room_id"]
    room = _rooms(api, hid)[lab]
    assert (room["workshop_profession_id"], room["profession_slug"], room["furniture_group"]) == (2, "alchemist",
                                                                                                    "workshop")
    # The owner no longer chooses it: the settings keep the type's profession.
    body = {"character_id": 10, "name": "Лаборатория", "workshop_profession_id": 1}
    assert api.put(f"/{hid}/rooms/{lab}", body).status_code == 200
    assert _rooms(api, hid)[lab]["workshop_profession_id"] == 2


def test_demolishing_keeps_needed_storage_and_occupied_bedrooms(api):
    hid, rooms = _house(api)
    api.sql("INSERT INTO house_storage (house_id) VALUES (:h)", h=hid)
    assert api.as_(OWNER).delete(f"/{hid}/rooms/{rooms['storage']}?character_id=10").status_code == 409
    api.sql("DELETE FROM house_storage")
    assert api.delete(f"/{hid}/rooms/{rooms['storage']}?character_id=10").status_code == 200
    api.sql("UPDATE characters SET sleep_house_room_id = :r WHERE id = 20", r=rooms["bedroom"])
    assert api.delete(f"/{hid}/rooms/{rooms['bedroom']}?character_id=10").status_code == 409
    assert api.as_(STRANGER).delete(f"/{hid}/rooms/{rooms['hall']}?character_id=30").status_code == 403


# --- stage 2: sleep ------------------------------------------------------------

@pytest.mark.real_activity_lock
def test_sleeping_locks_activity_until_waking(api):
    hid, rooms = _house(api)
    _go(api, OWNER, 10, rooms["bedroom"])
    r = api.as_(OWNER).post(f"/rooms/{rooms['bedroom']}/sleep", {"character_id": 10})
    assert r.status_code == 200 and r.json()["sleep_factor"] == houses.BEDROOM_SLEEP_FACTOR[1]
    since, factor, room = api.sql("SELECT asleep_since, sleep_regen_factor, sleep_house_room_id "
                                  "FROM characters WHERE id = 10")[0]
    assert since is not None and factor == 2.0 and room == rooms["bedroom"]
    assert api.regen_settled == [10]
    blocked = api.post(f"/rooms/{rooms['hall']}/posts", {"character_id": 10, "content": LONG})
    assert blocked.status_code == 409 and "спит" in blocked.json()["detail"]
    assert api.get(f"/{hid}").json()["acting"][0]["asleep_room_id"] == rooms["bedroom"]
    assert api.post("/wake", {"character_id": 10}).json() == {"asleep": False}
    assert api.regen_settled == [10, 10]
    assert api.sql("SELECT asleep_since FROM characters WHERE id = 10")[0][0] is None
    _go(api, OWNER, 10, rooms["hall"])
    assert api.post(f"/rooms/{rooms['hall']}/posts", {"character_id": 10, "content": LONG}).status_code == 200


def test_sleep_needs_a_built_bedroom_access_and_presence(api):
    hid, rooms = _house(api)
    assert api.as_(OWNER).post(f"/rooms/{rooms['hall']}/sleep", {"character_id": 10}).status_code == 400
    api.as_(OWNER).post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20})
    assert api.as_(FRIEND).post(f"/rooms/{rooms['bedroom']}/sleep", {"character_id": 20}).status_code == 403
    api.sql("UPDATE characters SET current_location_id = :f WHERE id = 10", f=FAR)
    assert api.as_(OWNER).post(f"/rooms/{rooms['bedroom']}/sleep", {"character_id": 10}).status_code == 403
    assert api.as_(STRANGER).post("/wake", {"character_id": 10}).status_code == 403


def test_admin_sets_build_costs_with_materials(api):
    body = {"gold": 70, "build_hours": 3, "items": [{"item_id": 1, "quantity": 2}, {"item_id": 1, "quantity": 1}]}
    assert api.as_(ADMIN).put("/admin/build-costs/forge/2", body).status_code == 200
    cost = next(c for c in api.as_(None).get("/build-costs").json()
                if c["room_type"] == "forge" and c["level"] == 2)
    assert (cost["gold"], cost["build_hours"], [(i["item_id"], i["quantity"]) for i in cost["items"]]) == (
        70, 3, [(1, 3)])
    assert api.as_(ADMIN).put("/admin/build-costs/forge/4", body).status_code == 404
    assert api.as_(ADMIN).put("/admin/build-costs/workshop/1", body).status_code == 404
    bad = {**body, "items": [{"item_id": 77, "quantity": 1}]}
    assert api.put("/admin/build-costs/forge/1", bad).status_code == 400
    assert api.as_(OWNER).put("/admin/build-costs/forge/1", body).status_code == 403


# --- stage 3: furniture ----------------------------------------------------------

def _give(api, item_id, qty=1, cid=10):
    api.sql("INSERT INTO character_inventory (character_id, item_id, quantity) VALUES (:c, :i, :q)",
            c=cid, i=item_id, q=qty)
    return api.sql("SELECT MAX(id) FROM character_inventory")[0][0]


def _bag(api, item_id, cid=10):
    return api.sql("SELECT COALESCE(SUM(quantity), 0) FROM character_inventory WHERE character_id = :c "
                   "AND item_id = :i", c=cid, i=item_id)[0][0]


def _room_view(api, hid, room_type):
    return next(r for r in api.as_(OWNER).get(f"/{hid}").json()["rooms"] if r["room_type"] == room_type)


def test_furniture_moves_from_the_bag_and_adds_its_bonus(api):
    hid, rooms = _house(api)
    row = _give(api, 10)
    r = api.as_(OWNER).post(f"/{hid}/rooms/{rooms['bedroom']}/furniture", {"character_id": 10, "inventory_item_id": row})
    assert r.status_code == 200, r.text
    assert _bag(api, 10) == 0
    bedroom = _room_view(api, hid, "bedroom")
    assert [f["name"] for f in bedroom["furniture"]] == ["Кровать"]
    assert bedroom["sleep_factor"] == houses.BEDROOM_SLEEP_FACTOR[1] + 0.5
    _in(api, 10, rooms["bedroom"])
    assert api.post(f"/rooms/{rooms['bedroom']}/sleep", {"character_id": 10}).json()["sleep_factor"] == 2.5


def test_furniture_must_fit_the_room_and_its_free_slots(api):
    hid, rooms = _house(api)
    stack = _give(api, 11, qty=3)
    assert api.as_(OWNER).post(f"/{hid}/rooms/{rooms['hall']}/furniture",
                               {"character_id": 10, "inventory_item_id": stack}).status_code == 400
    plain = _give(api, 1)
    assert api.post(f"/{hid}/rooms/{rooms['storage']}/furniture",
                    {"character_id": 10, "inventory_item_id": plain}).status_code == 400
    assert api.post(f"/{hid}/rooms/{rooms['storage']}/furniture",
                    {"character_id": 10, "inventory_item_id": stack}).status_code == 200
    # Level 1 = one slot; a level more frees another.
    assert api.post(f"/{hid}/rooms/{rooms['storage']}/furniture",
                    {"character_id": 10, "inventory_item_id": stack}).status_code == 409
    assert api.post(f"/{hid}/rooms/{rooms['storage']}/upgrade", {"character_id": 10}).status_code == 200
    assert api.post(f"/{hid}/rooms/{rooms['storage']}/furniture",
                    {"character_id": 10, "inventory_item_id": stack}).status_code == 200
    assert _bag(api, 11) == 1
    storage = _room_view(api, hid, "storage")
    assert storage["storage_stacks"] == houses.STORAGE_STACKS_BY_LEVEL[2] + 20


def test_only_the_owner_on_site_furnishes(api):
    hid, rooms = _house(api)
    api.as_(OWNER).post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20})
    row = _give(api, 12, cid=20)
    assert api.as_(FRIEND).post(f"/{hid}/rooms/{rooms['hall']}/furniture",
                                {"character_id": 20, "inventory_item_id": row}).status_code == 403
    mine = _give(api, 12)
    api.sql("UPDATE characters SET current_location_id = :f WHERE id = 10", f=FAR)
    assert api.as_(OWNER).post(f"/{hid}/rooms/{rooms['hall']}/furniture",
                               {"character_id": 10, "inventory_item_id": mine}).status_code == 403


def test_taking_furniture_back_and_what_blocks_it(api):
    hid, rooms = _house(api)
    api.as_(OWNER).post(f"/{hid}/rooms/{rooms['storage']}/furniture",
                        {"character_id": 10, "inventory_item_id": _give(api, 11)})
    piece = _room_view(api, hid, "storage")["furniture"][0]["id"]
    # A furnished room is not pulled down.
    assert api.delete(f"/{hid}/rooms/{rooms['storage']}?character_id=10").status_code == 409
    # The storage holds 40 with the chest; 31 stored stacks keep the chest in place.
    for _ in range(31):
        api.sql("INSERT INTO house_storage (house_id) VALUES (:h)", h=hid)
    assert api.delete(f"/{hid}/rooms/{rooms['storage']}/furniture/{piece}?character_id=10").status_code == 409
    api.sql("DELETE FROM house_storage WHERE id > 1")
    assert api.delete(f"/{hid}/rooms/{rooms['storage']}/furniture/{piece}?character_id=10").status_code == 200
    assert _bag(api, 11) == 1 and _room_view(api, hid, "storage")["furniture"] == []


def test_a_bedroom_with_a_sleeper_keeps_its_furniture(api):
    hid, rooms = _house(api)
    api.as_(OWNER).post(f"/{hid}/rooms/{rooms['bedroom']}/furniture",
                        {"character_id": 10, "inventory_item_id": _give(api, 10)})
    piece = _room_view(api, hid, "bedroom")["furniture"][0]["id"]
    api.sql("UPDATE characters SET sleep_house_room_id = :r WHERE id = 20", r=rooms["bedroom"])
    assert api.delete(f"/{hid}/rooms/{rooms['bedroom']}/furniture/{piece}?character_id=10").status_code == 409


# --- stage 4: tax, inheritance, seizure, sale -----------------------------------

def _owe(api, hid, periods):
    """Moves the paid-through mark back so the house owes `periods` periods."""
    api.sql("UPDATE houses SET tax_paid_through = tax_paid_through - :n WHERE id = :h", n=periods, h=hid)


def test_the_purchase_period_is_free_and_the_tax_follows_the_size(api):
    hid, rooms = _house(api)
    tax = api.as_(OWNER).get(f"/{hid}").json()["tax"]
    # 5 % of 300 + 50 per room level (three rooms of level 1)
    assert (tax["per_season"], tax["owed_periods"], tax["due"]) == (15 + 150, 0, 0)
    assert api.post(f"/{hid}/tax", {"character_id": 10}).status_code == 400


def test_an_unpaid_period_freezes_and_paying_unfreezes(api):
    hid, rooms = _house(api)
    _owe(api, hid, 1)
    house = api.as_(OWNER).get(f"/{hid}").json()
    assert house["status"] == "active" and house["tax"]["next_step"] == "freeze"
    _owe(api, hid, 1)
    house = api.get(f"/{hid}").json()
    assert house["status"] == "frozen" and house["tax"]["due"] == 2 * 165
    blocked = api.post(f"/rooms/{rooms['hall']}/posts", {"character_id": 10, "content": LONG})
    assert blocked.status_code == 409
    assert api.post(f"/rooms/{rooms['bedroom']}/sleep", {"character_id": 10}).status_code == 409
    assert api.post(f"/{hid}/rooms/{rooms['bedroom']}/upgrade", {"character_id": 10}).status_code == 409
    gold = _gold(api, 10)
    assert api.as_(STRANGER).post(f"/{hid}/tax", {"character_id": 30}).status_code == 403
    assert api.as_(OWNER).post(f"/{hid}/tax", {"character_id": 10}).status_code == 200
    assert _gold(api, 10) == gold - 330
    assert api.get(f"/{hid}").json()["status"] == "active"


def test_a_resident_may_pay_and_short_gold_changes_nothing(api):
    hid, _ = _house(api)
    api.as_(OWNER).post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20})
    _owe(api, hid, 2)
    r = api.as_(FRIEND).post(f"/{hid}/tax", {"character_id": 20})  # 50 gold against 330
    assert r.status_code == 400 and api.as_(OWNER).get(f"/{hid}").json()["status"] == "frozen"
    api.sql("UPDATE characters SET currency_balance = 1000 WHERE id = 20")
    assert api.as_(FRIEND).post(f"/{hid}/tax", {"character_id": 20}).status_code == 200
    assert _gold(api, 20) == 1000 - 330


def test_three_unpaid_periods_seize_the_house_and_free_the_plot(api):
    hid, rooms = _house(api)
    api.as_(OWNER).post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20})
    api.sql("UPDATE characters SET sleep_house_room_id = :r, asleep_since = '2026-01-01' WHERE id = 20",
            r=rooms["bedroom"])
    pid = api.as_(OWNER).get(f"/{hid}").json()["plot_id"]
    _owe(api, hid, 3)
    assert api.get(f"/{hid}").status_code == 404
    assert api.as_(None).get(f"/by-location/{TOWN}").json()[0]["house"] is None
    assert api.sql("SELECT asleep_since FROM characters WHERE id = 20")[0][0] is None
    archive = api.as_(ADMIN).get("/admin/seized").json()
    assert [(a["id"], a["reason"], len(a["rooms"])) for a in archive] == [(hid, "tax", 3)]
    assert api.as_(FRIEND).get("/my").json() == []
    # The plot sells again with its template rooms.
    api.sql("UPDATE characters SET currency_balance = 1000 WHERE id = 30")
    r = api.as_(STRANGER).post(f"/plots/{pid}/buy", {"character_id": 30})
    assert r.status_code == 200 and r.json()["house_id"] != hid
    assert [x["level"] for x in api.get(f"/{r.json()['house_id']}").json()["rooms"]] == [1, 1, 1]


def test_the_heir_takes_the_house_when_the_owner_is_deleted(api, monkeypatch):
    hid, _ = _house(api)
    assert api.as_(OWNER).put(f"/{hid}/heir", {"character_id": 10, "heir_character_id": 30}).status_code == 400
    api.post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20})
    assert api.put(f"/{hid}/heir", {"character_id": 10, "heir_character_id": 20}).status_code == 200
    api.sql("DELETE FROM characters WHERE id = 10")
    monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", "t")
    r = api.c.post("/locations/houses/internal/character-deleted/10", headers={"X-Internal-Token": "t"})
    assert r.status_code == 200 and r.json()["houses"] == [hid]
    house = api.as_(FRIEND).get(f"/{hid}").json()
    assert house["owner"]["id"] == 20 and house["is_owner"] and house["residents"] == [] and house["heir"] is None
    assert api.c.post("/locations/houses/internal/character-deleted/10").status_code == 401


def test_without_an_heir_the_house_is_seized_even_without_the_hook(api):
    hid, _ = _house(api)
    api.sql("DELETE FROM characters WHERE id = 10")
    assert api.as_(FRIEND).get(f"/{hid}").status_code == 404
    assert [a["reason"] for a in api.as_(ADMIN).get("/admin/seized").json()] == ["no_heir"]


def test_a_resident_leaving_drops_the_heir_mark(api):
    hid, _ = _house(api)
    rid = api.as_(OWNER).post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20}).json()["id"]
    api.put(f"/{hid}/heir", {"character_id": 10, "heir_character_id": 20})
    api.as_(FRIEND).delete(f"/{hid}/residents/{rid}?character_id=20")
    assert api.as_(OWNER).get(f"/{hid}").json()["heir"] is None


def test_selling_on_the_board(api):
    hid, rooms = _house(api)
    api.as_(OWNER).post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20})
    api.put(f"/{hid}/heir", {"character_id": 10, "heir_character_id": 20})
    api.as_(OWNER).post(f"/{hid}/rooms/{rooms['hall']}/furniture", {"character_id": 10, "inventory_item_id": _give(api, 12)})
    _owe(api, hid, 1)
    assert api.put(f"/{hid}/sale", {"character_id": 10, "price": 400}).status_code == 409  # a period owed
    api.post(f"/{hid}/tax", {"character_id": 10})
    assert api.put(f"/{hid}/sale", {"character_id": 10, "price": 400}).status_code == 200
    listed = api.as_(None).get("/market").json()
    assert [(m["id"], m["price"], m["furniture_count"]) for m in listed] == [(hid, 400, 1)]
    assert api.get(f"/by-location/{TOWN}").json()[0]["house"]["sale_price"] == 400
    assert api.as_(OWNER).post(f"/{hid}/buy", {"character_id": 10}).status_code == 400
    api.sql("UPDATE characters SET current_location_id = :f WHERE id = 30", f=FAR)
    assert api.as_(STRANGER).post(f"/{hid}/buy", {"character_id": 30}).status_code == 400
    api.sql("UPDATE characters SET current_location_id = :t WHERE id = 30", t=TOWN)
    seller, buyer = _gold(api, 10), _gold(api, 30)
    r = api.as_(STRANGER).post(f"/{hid}/buy", {"character_id": 30})
    assert r.status_code == 200, r.text
    assert (_gold(api, 10), _gold(api, 30)) == (seller + 400, buyer - 400)
    house = api.get(f"/{hid}").json()
    assert house["owner"]["id"] == 30 and house["residents"] == [] and house["heir"] is None
    assert house["sale_price"] is None and [len(r["furniture"]) for r in house["rooms"]][0] == 1
    assert api.as_(None).get("/market").json() == []


def test_admin_tax_rates(api):
    body = {"tax_price_pct": 10, "tax_per_room_level": 0}
    assert api.as_(OWNER).put("/admin/settings", body).status_code == 403
    assert api.as_(ADMIN).put("/admin/settings", body).status_code == 200
    assert api.get("/admin/settings").json()["tax_price_pct"] == 10
    hid, _ = _house(api)
    assert api.as_(OWNER).get(f"/{hid}").json()["tax"]["per_season"] == 30


# --- stage 5: the plan ------------------------------------------------------------

def _plan_body(**over):
    """Two open cells on the first floor, an extension cell there, a yard and a paid second floor."""
    body = {"location_id": TOWN, "name": "Усадьба", "price": 100, "kind": "empty", "grid_w": 3, "grid_h": 2,
            "extension_price": 40,
            "layers": [{"layer": "floor1"}, {"layer": "yard"}, {"layer": "floor2", "unlock_price": 150}],
            "cells": [{"layer": "floor1", "x": 0, "y": 0}, {"layer": "floor1", "x": 1, "y": 0},
                      {"layer": "floor1", "x": 2, "y": 0, "kind": "extension"},
                      {"layer": "yard", "x": 0, "y": 1, "allowed_types": ["forge"]},
                      {"layer": "floor2", "x": 0, "y": 0}]}
    body.update(over)
    return body


def _cells(api, hid):
    return {(c["layer"], c["x"], c["y"]): c for c in api.get(f"/{hid}").json()["plan"]["cells"]}


def test_the_plan_is_validated(api):
    good = _plan_body()
    for broken in (
        {"layers": [{"layer": "yard"}]},                                     # no first floor
        {"layers": [{"layer": "floor1", "unlock_price": 5}]},                # first floor not free
        {"grid_w": 1},                                                       # a cell outside the grid
        {"extension_price": None},                                           # extensions without a price
        {"cells": good["cells"] + [{"layer": "basement", "x": 1, "y": 1}]},  # a layer not in the plan
        {"cells": [{"layer": "yard", "x": 0, "y": 0, "allowed_types": ["hall"]}]},  # a hall in the yard
        {"kind": "ready", "rooms": [{"room_type": "hall", "name": "a", "x": 2, "y": 0}]},  # on an extension
        {"kind": "ready", "rooms": [{"room_type": "hall", "name": "a", "layer": "yard", "x": 0, "y": 1}]},
        {"kind": "ready", "rooms": [{"room_type": "hall", "name": "a", "layer": "floor2", "x": 0, "y": 0}]},
    ):
        r = api.as_(ADMIN).post("/admin/plots", {**good, **broken})
        assert r.status_code == 422, broken
    pid = api.as_(ADMIN).post("/admin/plots", good).json()["id"]
    card = api.get(f"/by-location/{TOWN}").json()[0]
    assert (card["cells_open"], card["cells_total"]) == (3, 5)
    plan = api.get(f"/plots/{pid}").json()["plan"]
    assert [(l["layer"], l["unlocked"]) for l in plan["layers"]] == [("floor1", True), ("floor2", False), ("yard", True)]
    yard = next(c for c in plan["cells"] if c["layer"] == "yard")
    assert yard["allowed_types"] == ["forge"]


def test_building_follows_the_plan_and_places_are_bought(api):
    pid = api.as_(ADMIN).post("/admin/plots", _plan_body()).json()["id"]
    hid = api.as_(OWNER).post(f"/plots/{pid}/buy", {"character_id": 10}).json()["house_id"]
    cells = _cells(api, hid)
    build = lambda key, rt="hall": api.as_(OWNER).post(
        f"/{hid}/rooms", {"character_id": 10, "room_type": rt, "name": "x", "cell_id": cells[key]["id"]})

    assert build(("yard", 0, 1)).status_code == 400                      # the yard takes a forge only
    assert build(("yard", 0, 1), "forge").status_code == 200
    assert build(("floor1", 0, 0)).status_code == 200
    assert build(("floor1", 0, 0), "bedroom").status_code == 409         # taken
    assert build(("floor1", 2, 0)).status_code == 409                    # an extension not bought
    assert build(("floor2", 0, 0)).status_code == 409                    # a layer not bought

    gold = _gold(api, 10)
    unlock_cell = lambda key, cid=10: api.post(f"/{hid}/cells/{cells[key]['id']}/unlock", {"character_id": cid})
    assert unlock_cell(("floor2", 0, 0)).status_code == 409              # an open cell on a closed layer
    assert unlock_cell(("floor1", 2, 0)).status_code == 200
    assert _gold(api, 10) == gold - 40
    assert unlock_cell(("floor1", 2, 0)).status_code == 409
    assert build(("floor1", 2, 0), "storage").status_code == 200

    assert api.as_(STRANGER).post(f"/{hid}/layers/floor2/unlock", {"character_id": 30}).status_code == 403
    assert api.as_(OWNER).post(f"/{hid}/layers/basement/unlock", {"character_id": 10}).status_code == 404
    assert api.post(f"/{hid}/layers/floor2/unlock", {"character_id": 10}).status_code == 200
    assert api.post(f"/{hid}/layers/floor2/unlock", {"character_id": 10}).status_code == 409
    assert _gold(api, 10) == gold - 40 - 100 - 150
    assert build(("floor2", 0, 0), "bedroom").status_code == 200
    plan = api.get(f"/{hid}").json()["plan"]
    assert all(l["unlocked"] for l in plan["layers"])
    assert sum(bool(c["room_id"]) for c in plan["cells"]) == 4


def test_buying_a_place_needs_gold_and_a_new_owner_starts_from_the_plan(api):
    pid = api.as_(ADMIN).post("/admin/plots", _plan_body()).json()["id"]
    hid = api.as_(OWNER).post(f"/plots/{pid}/buy", {"character_id": 10}).json()["house_id"]
    api.sql("UPDATE characters SET currency_balance = 10 WHERE id = 10")
    assert api.as_(OWNER).post(f"/{hid}/layers/floor2/unlock", {"character_id": 10}).status_code == 400
    assert api.sql("SELECT COUNT(*) FROM house_layer_unlocks")[0][0] == 0
    api.sql("UPDATE characters SET currency_balance = 1000 WHERE id = 10")
    api.post(f"/{hid}/layers/floor2/unlock", {"character_id": 10})
    api.sql("UPDATE houses SET tax_paid_through = tax_paid_through - 3 WHERE id = :h", h=hid)  # seized
    api.sql("UPDATE characters SET currency_balance = 1000 WHERE id = 30")
    new = api.as_(STRANGER).post(f"/plots/{pid}/buy", {"character_id": 30}).json()["house_id"]
    layers = {l["layer"]: l["unlocked"] for l in api.get(f"/{new}").json()["plan"]["layers"]}
    assert layers["floor2"] is False


def test_the_admin_reshapes_the_plan_around_the_rooms(api):
    body = _plan_body()
    pid = api.as_(ADMIN).post("/admin/plots", body).json()["id"]
    hid = api.as_(OWNER).post(f"/plots/{pid}/buy", {"character_id": 10}).json()["house_id"]
    cells = _cells(api, hid)
    rid = api.as_(OWNER).post(f"/{hid}/rooms", {"character_id": 10, "room_type": "hall", "name": "x",
                                               "cell_id": cells[("floor1", 1, 0)]["id"]}).json()["room_id"]
    # Removing the place where the room stands is refused; other changes keep the cell ids.
    without = {**body, "cells": [c for c in body["cells"] if (c["x"], c["y"]) != (1, 0)]}
    r = api.as_(ADMIN).put(f"/admin/plots/{pid}", without)
    assert r.status_code == 409 and "стоит комната" in r.json()["detail"]
    more = {**body, "grid_h": 3, "cells": body["cells"] + [{"layer": "floor1", "x": 2, "y": 2}]}
    assert api.put(f"/admin/plots/{pid}", more).status_code == 200
    after = _cells(api, hid)
    assert after[("floor1", 1, 0)]["id"] == cells[("floor1", 1, 0)]["id"]
    assert after[("floor1", 1, 0)]["room_id"] == rid and ("floor1", 2, 2) in after


# --- stage 6a: profession rooms, cellar, garden rooms, bath -------------------------

SEED, CARROT, ROSE_SEED, ROSE, ANVIL = 20, 21, 22, 23, 13


def _estate(api, price=0):
    """An empty plot with a first floor, a free basement and a yard (two places each); bought by OWNER."""
    body = {"location_id": TOWN, "name": "Усадьба", "price": price, "kind": "empty", "grid_w": 2, "grid_h": 1,
            "layers": [{"layer": "floor1"}, {"layer": "basement"}, {"layer": "yard"}],
            "cells": [{"layer": layer, "x": x, "y": 0} for layer in ("floor1", "basement", "yard") for x in (0, 1)]}
    r = api.as_(ADMIN).post("/admin/plots", body)
    assert r.status_code == 200, r.text
    r = api.as_(OWNER).post(f"/plots/{r.json()['id']}/buy", {"character_id": 10})
    assert r.status_code == 200, r.text
    return r.json()["house_id"]


def _build(api, hid, room_type, layer, x=0):
    cell = next(c for c in api.as_(OWNER).get(f"/{hid}").json()["plan"]["cells"]
                if (c["layer"], c["x"]) == (layer, x))
    api.sql("UPDATE characters SET currency_balance = 5000 WHERE id = 10")
    return api.post(
        f"/{hid}/rooms", {"character_id": 10, "room_type": room_type, "name": room_type, "cell_id": cell["id"]})


def _built(api, hid, room_type, layer, x=0):
    r = _build(api, hid, room_type, layer, x)
    assert r.status_code == 200, r.text
    return r.json()["room_id"]


def _seeds(api):
    api.sql("INSERT INTO items (id, name) VALUES (:c, 'Морковь'), (:r, 'Роза')", c=CARROT, r=ROSE)
    api.sql("INSERT INTO items (id, name, seed_result_item_id, seed_result_quantity, seed_grow_hours, "
            "seed_room_type, seed_herbalism_xp) VALUES (:s, 'Семена моркови', :c, 3, 2, 'garden', 5), "
            "(:rs, 'Семена розы', :r, 1, 4, 'greenhouse', 9)", s=SEED, c=CARROT, rs=ROSE_SEED, r=ROSE)


def test_room_types_follow_their_layers(api):
    hid = _estate(api)
    allowed = {c["layer"]: c["allowed_types"] for c in api.as_(OWNER).get(f"/{hid}").json()["plan"]["cells"]}
    assert allowed["yard"] == ["garden", "greenhouse", "apiary", "bath", "forge", "shrine", "return_circle"]
    assert allowed["basement"] == ["storage", "cellar", "alchemy_lab", "enchanting", "return_circle"]
    assert "kitchen" in allowed["floor1"] and "cellar" not in allowed["floor1"] and "workshop" not in allowed["floor1"]
    assert _build(api, hid, "kitchen", "yard").status_code == 400
    assert _build(api, hid, "cellar", "floor1").status_code == 400
    assert _build(api, hid, "workshop", "floor1").status_code == 422
    forge = _built(api, hid, "forge", "yard")
    kitchen = _built(api, hid, "kitchen", "floor1")
    rooms = _rooms(api, hid)
    assert (rooms[forge]["workshop_profession_id"], rooms[kitchen]["workshop_profession_id"]) == (1, 3)
    # A cell cannot allow a room its layer does not take (no kitchen in the yard).
    bad = {"location_id": TOWN, "name": "x", "price": 1, "grid_w": 1, "grid_h": 1, "kind": "empty",
           "layers": [{"layer": "floor1"}, {"layer": "yard"}],
           "cells": [{"layer": "floor1", "x": 0, "y": 0},
                     {"layer": "yard", "x": 0, "y": 0, "allowed_types": ["kitchen"]}]}
    assert api.as_(ADMIN).post("/admin/plots", bad).status_code == 422


def test_ready_plots_give_profession_rooms_their_profession(api):
    pid = _plot(api, rooms=[{"room_type": "hall", "name": "Зал", "x": 0, "y": 0},
                            {"room_type": "study", "name": "Кабинет", "x": 1, "y": 0}])
    hid = api.as_(OWNER).post(f"/plots/{pid}/buy", {"character_id": 10}).json()["house_id"]
    study = _room_view(api, hid, "study")
    assert (study["workshop_profession_id"], study["profession_slug"]) == (6, "scholar")
    assert _room_view(api, hid, "hall")["workshop_profession_id"] is None


def test_furniture_follows_the_room_group(api):
    hid = _estate(api)
    api.sql("INSERT INTO items (id, name, item_type, furniture_room_type, furniture_xp_bonus_pct, max_stack_size) "
            "VALUES (:i, 'Наковальня', 'furniture', 'workshop', 10, 1)", i=ANVIL)
    kitchen = _built(api, hid, "kitchen", "floor1")
    garden = _built(api, hid, "garden", "yard")
    cellar = _built(api, hid, "cellar", "basement")
    put = lambda room, item: api.as_(OWNER).post(f"/{hid}/rooms/{room}/furniture",
                                                 {"character_id": 10, "inventory_item_id": _give(api, item)})
    assert put(kitchen, ANVIL).status_code == 200
    assert put(cellar, 12).status_code == 400            # a tapestry is hall furniture
    r = put(garden, ANVIL)
    assert r.status_code == 409 and r.json()["detail"] == "В эту комнату мебель не ставят"
    assert put(cellar, 11).status_code == 200            # storage furniture stands in a cellar
    rooms = _rooms(api, hid)
    assert rooms[cellar]["storage_stacks"] == houses.CELLAR_STACKS_BY_LEVEL[1] + 10
    assert rooms[cellar]["furniture_group"] == "storage" and rooms[garden]["furniture_group"] is None
    assert [f["name"] for f in rooms[kitchen]["furniture"]] == ["Наковальня"]


def test_a_cellar_is_a_storage(api):
    hid = _estate(api)
    cellar = _built(api, hid, "cellar", "basement")
    assert _rooms(api, hid)[cellar]["storage_stacks"] == houses.CELLAR_STACKS_BY_LEVEL[1]
    api.sql("INSERT INTO house_storage (house_id) VALUES (:h)", h=hid)
    r = api.as_(OWNER).delete(f"/{hid}/rooms/{cellar}?character_id=10")
    assert r.status_code == 409 and "кладов" in r.json()["detail"]
    # A storage takes over: the cellar may go.
    _built(api, hid, "storage", "floor1")
    assert api.as_(OWNER).delete(f"/{hid}/rooms/{cellar}?character_id=10").status_code == 200


def _garden(api, hid=None):
    hid = hid or _estate(api)
    _seeds(api)
    return hid, _built(api, hid, "garden", "yard")


def _plant(api, room, cid=10, uid=OWNER, **extra):
    _in(api, cid, room)
    return api.as_(uid).post(f"/rooms/{room}/plant", {"character_id": cid, **extra})


def test_planting_takes_a_seed_into_a_free_bed(api):
    hid, garden = _garden(api)
    beds = houses.GARDEN_BEDS_BY_LEVEL[1]
    row = _give(api, SEED, qty=beds + 1)
    r = _plant(api, garden, inventory_item_id=row)
    assert r.status_code == 200, r.text
    assert r.json()["bed_no"] == 1 and _bag(api, SEED) == beds
    view = _room_view(api, hid, "garden")
    assert view["beds_total"] == houses.GARDEN_BEDS_BY_LEVEL[1]
    (bed,) = view["beds"]
    assert (bed["bed_no"], bed["planted_by"]["id"], bed["seed"]["name"], bed["result"]["name"], bed["quantity"],
            bed["ready"]) == (1, 10, "Семена моркови", "Морковь", 3, False)
    assert api.as_(OWNER).get(f"/rooms/{garden}").json()["room"]["beds"][0]["bed_no"] == 1
    assert _plant(api, garden, inventory_item_id=row, bed_no=1).status_code == 409   # taken
    assert _plant(api, garden, inventory_item_id=row, bed_no=beds + 1).status_code == 409   # beyond the level
    for bed_no in range(2, beds + 1):
        assert _plant(api, garden, inventory_item_id=row).json()["bed_no"] == bed_no
    full = _plant(api, garden, inventory_item_id=row)
    assert full.status_code == 409 and full.json()["detail"] == "Все грядки заняты"
    assert _bag(api, SEED) == 1


def test_planting_rules(api):
    hid, garden = _garden(api)
    seed = _give(api, SEED)
    rose = _give(api, ROSE_SEED)
    board = _give(api, 1)
    wrong = _plant(api, garden, inventory_item_id=rose)
    assert wrong.status_code == 400 and "оранжерее" in wrong.json()["detail"]
    assert _plant(api, garden, inventory_item_id=board).status_code == 400          # not a seed
    assert _plant(api, garden, inventory_item_id=_give(api, SEED, cid=20)).status_code == 404  # not in this bag
    # A stranger and a resident not let in stay out; a resident let in plants.
    assert _plant(api, garden, cid=30, uid=STRANGER, inventory_item_id=_give(api, SEED, cid=30)).status_code == 403
    rid = api.as_(OWNER).post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20}).json()["id"]
    friend_seed = _give(api, SEED, cid=20)
    assert _plant(api, garden, cid=20, uid=FRIEND, inventory_item_id=friend_seed).status_code == 403
    assert api.as_(FRIEND).get(f"/rooms/{garden}/seeds?character_id=20").status_code == 403
    api.as_(OWNER).put(f"/{hid}/residents/{rid}", {"character_id": 10, "room_ids": [garden]})
    seeds = api.as_(FRIEND).get(f"/rooms/{garden}/seeds?character_id=20").json()
    assert [(s["name"], s["grow_hours"], s["result"]["name"], s["result_quantity"]) for s in seeds] == [
        ("Семена моркови", 2, "Морковь", 3)] * 2
    assert _plant(api, garden, cid=20, uid=FRIEND, inventory_item_id=friend_seed).status_code == 200
    # Away from the house, or in a frozen house, nothing is planted.
    api.sql("UPDATE characters SET current_location_id = :f WHERE id = 10", f=FAR)
    assert _plant(api, garden, inventory_item_id=seed).status_code == 403
    api.sql("UPDATE characters SET current_location_id = :t WHERE id = 10", t=TOWN)
    _owe(api, hid, 2)
    assert _plant(api, garden, inventory_item_id=seed).status_code == 409
    assert _bag(api, SEED) == 1


def test_a_garden_being_built_has_no_beds(api):
    hid = _estate(api)
    _seeds(api)
    api.sql("UPDATE house_build_costs SET build_hours = 5 WHERE room_type = 'garden' AND level = 1")
    garden = _built(api, hid, "garden", "yard")
    r = _plant(api, garden, inventory_item_id=_give(api, SEED))
    assert r.status_code == 409 and _rooms(api, hid)[garden]["beds_total"] == 0


@pytest.fixture()
def award(monkeypatch):
    calls, answer = [], {"actual_quantity_added": 3, "xp_awarded": 5, "rank_up": False}

    async def _award(character_id, payload):
        calls.append((character_id, payload))
        if isinstance(answer.get("raise"), Exception):
            raise answer["raise"]
        return answer

    monkeypatch.setattr(houses, "_inventory_award", _award)
    return {"calls": calls, "answer": answer}


def _ripen(api):
    api.sql("UPDATE house_garden_beds SET ready_at = '2000-01-01 00:00:00'")


def test_harvesting_a_grown_bed(api, award):
    hid, garden = _garden(api)
    _plant(api, garden, inventory_item_id=_give(api, SEED))
    early = api.as_(OWNER).post(f"/rooms/{garden}/harvest", {"character_id": 10, "bed_no": 1})
    assert early.status_code == 409 and "Ещё не выросло" in early.json()["detail"] and award["calls"] == []
    _ripen(api)
    assert _room_view(api, hid, "garden")["beds"][0]["ready"] is True
    assert api.as_(STRANGER).post(f"/rooms/{garden}/harvest", {"character_id": 30, "bed_no": 1}).status_code == 403
    r = api.as_(OWNER).post(f"/rooms/{garden}/harvest", {"character_id": 10, "bed_no": 1})
    assert r.status_code == 200, r.text
    assert (r.json()["added"], r.json()["item"]["name"]) == (3, "Морковь")
    ((cid, payload),) = award["calls"]
    assert cid == 10 and payload == {"skill_slug": "herbalism", "result_item_id": CARROT, "result_quantity": 3,
                                     "xp_to_add": 5, "tool_inventory_item_id": None, "tool_durability_to_consume": 0}
    assert _room_view(api, hid, "garden")["beds"] == []
    assert api.post(f"/rooms/{garden}/harvest", {"character_id": 10, "bed_no": 1}).status_code == 404


def test_a_full_bag_or_a_failed_call_keeps_the_bed(api, award):
    hid, garden = _garden(api)
    api.as_(OWNER).post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20})
    rid = api.get(f"/{hid}").json()["residents"][0]["id"]
    api.put(f"/{hid}/residents/{rid}", {"character_id": 10, "room_ids": [garden]})
    _plant(api, garden, cid=20, uid=FRIEND, inventory_item_id=_give(api, SEED, cid=20))
    _ripen(api)
    award["answer"]["actual_quantity_added"] = 0
    full = api.as_(FRIEND).post(f"/rooms/{garden}/harvest", {"character_id": 20, "bed_no": 1})
    assert full.status_code == 409 and full.json()["detail"] == "Сумка полна"
    assert len(_room_view(api, hid, "garden")["beds"]) == 1
    award["answer"]["raise"] = houses.HTTPException(503, houses.INVENTORY_UNREACHABLE)
    assert api.as_(FRIEND).post(f"/rooms/{garden}/harvest", {"character_id": 20, "bed_no": 1}).status_code == 503
    bed = _room_view(api, hid, "garden")["beds"][0]
    assert bed["planted_by"]["id"] == 20 and bed["ready"] is True
    # The owner may gather what the resident planted; a part that fits still clears the bed.
    award["answer"].pop("raise")
    award["answer"]["actual_quantity_added"] = 1
    _in(api, 10, garden)
    r = api.as_(OWNER).post(f"/rooms/{garden}/harvest", {"character_id": 10, "bed_no": 1})
    assert r.status_code == 200 and (r.json()["added"], r.json()["quantity"]) == (1, 3)
    assert _room_view(api, hid, "garden")["beds"] == []


def test_a_planted_garden_is_not_pulled_down(api):
    hid, garden = _garden(api)
    _plant(api, garden, inventory_item_id=_give(api, SEED))
    r = api.as_(OWNER).delete(f"/{hid}/rooms/{garden}?character_id=10")
    assert r.status_code == 409 and r.json()["detail"] == "Сначала соберите урожай"
    api.sql("DELETE FROM house_garden_beds")
    assert api.delete(f"/{hid}/rooms/{garden}?character_id=10").status_code == 200


@pytest.fixture()
def recover(monkeypatch):
    calls, state = [], {}

    async def _recover(character_id, amounts):
        calls.append((character_id, amounts))
        if state.get("raise"):
            raise state["raise"]

    monkeypatch.setattr(houses, "_recover", _recover)
    return {"calls": calls, "state": state}


def test_a_bath_restores_a_share_once_a_day(api, recover):
    hid = _estate(api)
    bath = _built(api, hid, "bath", "yard")
    _in(api, 10, bath)
    r = api.as_(OWNER).post(f"/rooms/{bath}/bathe", {"character_id": 10})
    assert r.status_code == 200, r.text
    # 20 % of 200 / 100 / 50 / 120 at level 1
    assert r.json()["restored"] == {"health": 40, "mana": 20, "energy": 10, "stamina": 24}
    assert recover["calls"] == [(10, {"health_recovery": 40, "mana_recovery": 20, "energy_recovery": 10,
                                      "stamina_recovery": 24})]
    assert api.get(f"/{hid}").json()["acting"][0]["bath_next_at"] is not None
    again = api.post(f"/rooms/{bath}/bathe", {"character_id": 10})
    assert again.status_code == 409 and "Баня ещё не остыла" in again.json()["detail"]
    api.sql("UPDATE house_bath_uses SET last_at = '2000-01-01 00:00:00'")
    assert api.get(f"/{hid}").json()["acting"][0]["bath_next_at"] is None
    assert api.post(f"/{hid}/rooms/{bath}/upgrade", {"character_id": 10}).status_code == 200
    assert api.post(f"/rooms/{bath}/bathe", {"character_id": 10}).json()["restored"]["health"] == 70  # 35 %


def test_bath_rights_and_a_failed_recovery(api, recover):
    hid = _estate(api)
    bath = _built(api, hid, "bath", "yard")
    hall = _built(api, hid, "hall", "floor1")
    assert api.as_(OWNER).post(f"/rooms/{hall}/bathe", {"character_id": 10}).status_code == 400
    assert api.as_(STRANGER).post(f"/rooms/{bath}/bathe", {"character_id": 30}).status_code == 403
    api.as_(OWNER).post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20})
    assert api.as_(FRIEND).post(f"/rooms/{bath}/bathe", {"character_id": 20}).status_code == 403
    recover["state"]["raise"] = houses.HTTPException(503, houses.ATTRIBUTES_UNREACHABLE)
    _in(api, 10, bath)
    assert api.as_(OWNER).post(f"/rooms/{bath}/bathe", {"character_id": 10}).status_code == 503
    assert api.sql("SELECT COUNT(*) FROM house_bath_uses")[0][0] == 0
    recover["state"].pop("raise")
    api.sql("UPDATE characters SET current_location_id = :f WHERE id = 10", f=FAR)
    assert api.post(f"/rooms/{bath}/bathe", {"character_id": 10}).status_code == 403
    api.sql("UPDATE characters SET current_location_id = :t WHERE id = 10", t=TOWN)
    assert api.post(f"/rooms/{bath}/bathe", {"character_id": 10}).status_code == 200


# --- stage 6b: library, shrine, trophy hall, guest room, return circle -----------------

ELITE, PLAIN_TROPHY = 30, 31


def _trophies(api):
    api.sql("INSERT INTO items (id, name, item_type, resource_subcategory, is_elite_trophy, max_stack_size) VALUES "
            "(:e, 'Клык вожака', 'resource', 'trophy', 1, 10), (:p, 'Клык', 'resource', 'trophy', 0, 10)",
            e=ELITE, p=PLAIN_TROPHY)


def _back(api, hours, column="reading_since", cid=10):
    api.sql(f"UPDATE characters SET {column} = datetime({column}, :d) WHERE id = :c", d=f"-{hours} hours", c=cid)


def _buff_rows(api, cid=10):
    return api.sql("SELECT source, kind, value FROM house_buffs WHERE character_id = :c ORDER BY source", c=cid)


def test_new_room_types_follow_their_layers(api):
    hid = _estate(api)
    allowed = {c["layer"]: c["allowed_types"] for c in api.as_(OWNER).get(f"/{hid}").json()["plan"]["cells"]}
    for t in ("library", "shrine", "trophy_hall", "guest_room", "return_circle"):
        assert t in allowed["floor1"]
    assert _build(api, hid, "library", "yard").status_code == 400
    assert _build(api, hid, "trophy_hall", "basement").status_code == 400
    circle = _built(api, hid, "return_circle", "basement")
    shrine = _built(api, hid, "shrine", "yard")
    guest = _built(api, hid, "guest_room", "floor1")
    rooms = _rooms(api, hid)
    assert rooms[circle]["circle_keep_chance"] == houses.CIRCLE_KEEP_CHANCE[1]
    assert rooms[shrine]["shrine_bonus"] == houses.SHRINE_BONUS[1] and rooms[shrine]["furniture_group"] is None
    assert (rooms[guest]["furniture_group"], rooms[guest]["sleep_factor"]) == ("bedroom", houses.BEDROOM_SLEEP_FACTOR[1])


@pytest.mark.real_activity_lock
def test_reading_locks_activity_and_grants_the_library_blessing(api):
    hid = _estate(api)
    library = _built(api, hid, "library", "floor1")
    hall = _built(api, hid, "hall", "floor1", x=1)
    _in(api, 10, library)
    r = api.as_(OWNER).post(f"/rooms/{library}/read", {"character_id": 10})
    assert r.status_code == 200, r.text
    assert r.json()["cap"] == houses.LIBRARY_CAP[1]
    blocked = api.post(f"/rooms/{hall}/posts", {"character_id": 10, "content": LONG})
    assert blocked.status_code == 409 and "читает" in blocked.json()["detail"]
    me = api.get(f"/{hid}").json()["acting"][0]
    assert me["reading_room_id"] == library and me["reading_since"] is not None
    _back(api, 3)
    r = api.post("/stop-reading", {"character_id": 10})
    assert r.status_code == 200, r.text
    assert (r.json()["hours"], r.json()["bonus"], r.json()["value"]) == (3, 0.03, 0.03) and r.json()["expires_at"]
    assert _buff_rows(api) == [("library", "character_xp", 0.03)]
    assert api.sql("SELECT reading_since, reading_house_room_id FROM characters WHERE id = 10")[0] == (None, None)
    _go(api, OWNER, 10, hall)
    assert api.post(f"/rooms/{hall}/posts", {"character_id": 10, "content": LONG}).status_code == 200
    _go(api, OWNER, 10, library)
    assert api.post("/stop-reading", {"character_id": 10}).json()["hours"] == 0   # not reading: nothing
    # A long read is capped by the level.
    api.post(f"/rooms/{library}/read", {"character_id": 10})
    _back(api, 20)
    assert api.post("/stop-reading", {"character_id": 10}).json()["bonus"] == houses.LIBRARY_CAP[1]
    # A smaller read keeps the higher running blessing but restarts its 24 h.
    api.sql("UPDATE house_buffs SET expires_at = datetime('now', '+1 hours')")
    api.post(f"/rooms/{library}/read", {"character_id": 10})
    _back(api, 1)
    r = api.post("/stop-reading", {"character_id": 10}).json()
    assert (r["bonus"], r["value"]) == (0.01, houses.LIBRARY_CAP[1])
    assert api.sql("SELECT expires_at > datetime('now', '+23 hours') FROM house_buffs")[0][0] == 1
    # Under an hour earns nothing and leaves the blessing as it is.
    api.post(f"/rooms/{library}/read", {"character_id": 10})
    r = api.post("/stop-reading", {"character_id": 10}).json()
    assert (r["hours"], r["bonus"], r["expires_at"]) == (0, 0.0, None)
    assert _buff_rows(api) == [("library", "character_xp", houses.LIBRARY_CAP[1])]
    buffs = api.get("/buffs?character_id=10").json()
    assert [(b["source"], b["kind"], b["value"]) for b in buffs["buffs"]] == [("library", "character_xp", 0.05)]


def test_reading_and_sleeping_exclude_each_other(api):
    hid = _estate(api)
    library = _built(api, hid, "library", "floor1")
    bedroom = _built(api, hid, "bedroom", "floor1", x=1)
    _in(api, 10, library)
    assert api.as_(OWNER).post(f"/rooms/{library}/read", {"character_id": 10}).status_code == 200
    _in(api, 10, bedroom)  # the lock is a stand-in here; the table itself refuses
    r = api.post(f"/rooms/{bedroom}/sleep", {"character_id": 10})
    assert r.status_code == 409 and "читает" in r.json()["detail"]
    api.post("/stop-reading", {"character_id": 10})
    assert api.post(f"/rooms/{bedroom}/sleep", {"character_id": 10}).status_code == 200
    _in(api, 10, library)
    assert api.post(f"/rooms/{library}/read", {"character_id": 10}).status_code == 409


def test_reading_needs_access_and_a_built_library(api):
    hid = _estate(api)
    library = _built(api, hid, "library", "floor1")
    hall = _built(api, hid, "hall", "floor1", x=1)
    assert api.as_(OWNER).post(f"/rooms/{hall}/read", {"character_id": 10}).status_code == 400
    api.post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20})
    assert api.as_(FRIEND).post(f"/rooms/{library}/read", {"character_id": 20}).status_code == 403
    assert api.as_(STRANGER).post("/stop-reading", {"character_id": 10}).status_code == 403
    api.sql("UPDATE characters SET current_location_id = :f WHERE id = 10", f=FAR)
    assert api.as_(OWNER).post(f"/rooms/{library}/read", {"character_id": 10}).status_code == 403


def test_a_library_with_a_reader_stands_and_leaving_ends_the_reading(api):
    hid = _estate(api)
    library = _built(api, hid, "library", "floor1")
    rid = api.as_(OWNER).post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20}).json()["id"]
    api.put(f"/{hid}/residents/{rid}", {"character_id": 10, "room_ids": [library]})
    _go(api, FRIEND, 20, library)
    assert api.as_(FRIEND).post(f"/rooms/{library}/read", {"character_id": 20}).status_code == 200
    r = api.as_(OWNER).delete(f"/{hid}/rooms/{library}?character_id=10")
    assert r.status_code == 409 and "читает" in r.json()["detail"]
    _back(api, 2, cid=20)
    # The resident moves out: the reading ends with what it earned.
    assert api.as_(FRIEND).delete(f"/{hid}/residents/{rid}?character_id=20").status_code == 200
    assert api.sql("SELECT reading_since FROM characters WHERE id = 20")[0][0] is None
    assert _buff_rows(api, 20) == [("library", "character_xp", 0.02)] and _where(api, 20) is None
    assert api.as_(OWNER).delete(f"/{hid}/rooms/{library}?character_id=10").status_code == 200


def test_seizure_ends_reading_with_the_bonus(api):
    hid = _estate(api)
    library = _built(api, hid, "library", "floor1")
    _in(api, 10, library)
    api.as_(OWNER).post(f"/rooms/{library}/read", {"character_id": 10})
    _back(api, 4)
    _owe(api, hid, 3)
    assert api.get(f"/{hid}").status_code == 404
    assert api.sql("SELECT reading_since FROM characters WHERE id = 10")[0][0] is None
    assert _buff_rows(api) == [("library", "character_xp", 0.04)] and _where(api, 10) is None


def test_a_shrine_blesses_once_a_day_and_a_new_prayer_replaces(api):
    hid = _estate(api)
    shrine = _built(api, hid, "shrine", "yard")
    _in(api, 10, shrine)
    assert api.as_(OWNER).post(f"/rooms/{shrine}/pray", {"character_id": 10, "blessing": "luck"}).status_code == 422
    r = api.post(f"/rooms/{shrine}/pray", {"character_id": 10, "blessing": "regen"})
    assert r.status_code == 200, r.text
    assert (r.json()["blessing"], r.json()["value"]) == ("regen", houses.SHRINE_BONUS[1]) and r.json()["next_at"]
    assert api.regen_settled == [10]
    assert _buff_rows(api) == [("shrine", "regen", 0.05)]
    assert api.get(f"/{hid}").json()["acting"][0]["pray_next_at"] is not None
    again = api.post(f"/rooms/{shrine}/pray", {"character_id": 10, "blessing": "post_xp"})
    assert again.status_code == 409 and "Святилище" in again.json()["detail"]
    api.sql("UPDATE house_shrine_uses SET last_at = '2000-01-01 00:00:00'")
    assert api.post(f"/{hid}/rooms/{shrine}/upgrade", {"character_id": 10}).status_code == 200
    r = api.post(f"/rooms/{shrine}/pray", {"character_id": 10, "blessing": "post_xp"})
    assert r.json()["value"] == houses.SHRINE_BONUS[2]
    assert _buff_rows(api) == [("shrine", "post_xp", 0.10)]
    acting = api.get(f"/{hid}").json()["acting"][0]
    assert [(b["source"], b["kind"]) for b in acting["buffs"]] == [("shrine", "post_xp")]


def test_shrine_rights(api):
    hid = _estate(api)
    shrine = _built(api, hid, "shrine", "yard")
    _built(api, hid, "guest_room", "floor1")
    assert api.as_(STRANGER).post(f"/rooms/{shrine}/pray", {"character_id": 30, "blessing": "regen"}).status_code == 403
    api.as_(OWNER).post(f"/{hid}/guests", {"character_id": 10, "guest_character_id": 30})
    assert api.as_(STRANGER).post(f"/rooms/{shrine}/pray", {"character_id": 30, "blessing": "regen"}).status_code == 403
    rid = api.as_(OWNER).post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20}).json()["id"]
    assert api.as_(FRIEND).post(f"/rooms/{shrine}/pray", {"character_id": 20, "blessing": "regen"}).status_code == 403
    api.as_(OWNER).put(f"/{hid}/residents/{rid}", {"character_id": 10, "room_ids": [shrine]})
    _go(api, FRIEND, 20, shrine)
    assert api.as_(FRIEND).post(f"/rooms/{shrine}/pray", {"character_id": 20,
                                                          "blessing": "gathering_xp"}).status_code == 200
    assert api.as_(OWNER).get("/buffs?character_id=20").status_code == 403
    assert api.as_(FRIEND).get("/buffs?character_id=20").json()["buffs"][0]["kind"] == "gathering_xp"


def test_a_trophy_hall_takes_elite_trophies_into_its_slots(api):
    hid = _estate(api)
    _trophies(api)
    hall = _built(api, hid, "trophy_hall", "floor1")
    put = lambda item: api.as_(OWNER).post(f"/{hid}/rooms/{hall}/furniture",
                                           {"character_id": 10, "inventory_item_id": _give(api, item)})
    r = put(10)
    assert r.status_code == 409 and "мебель" in r.json()["detail"]
    r = put(PLAIN_TROPHY)
    assert r.status_code == 400 and r.json()["detail"] == "Сюда вешают только элитные трофеи"
    stack = _give(api, ELITE, qty=7)
    for _ in range(houses.TROPHY_SLOTS[1]):
        assert api.post(f"/{hid}/rooms/{hall}/furniture",
                        {"character_id": 10, "inventory_item_id": stack}).status_code == 200
    assert api.post(f"/{hid}/rooms/{hall}/furniture",
                    {"character_id": 10, "inventory_item_id": stack}).status_code == 409
    assert _bag(api, ELITE) == 2
    house = api.get(f"/{hid}").json()
    room = next(r for r in house["rooms"] if r["id"] == hall)
    assert (room["trophy_slots"], room["furniture_slots"], len(room["furniture"])) == (5, 5, 5)
    assert house["trophy_bonus"] == 0.05 and house["acting"][0]["trophy_bonus"] == 0.05
    # Residents share it wherever they are; guests do not.
    api.post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20})
    api.sql("UPDATE characters SET current_location_id = :f WHERE id = 20", f=FAR)
    assert api.as_(FRIEND).get("/buffs?character_id=20").json()["trophy_bonus"] == 0.05
    api.as_(OWNER).post(f"/{hid}/guests", {"character_id": 10, "guest_character_id": 30})
    assert api.as_(STRANGER).get("/buffs?character_id=30").json()["trophy_bonus"] == 0.0
    # A trophy taken down goes back to the bag; a frozen house gives nothing.
    piece = room["furniture"][0]["id"]
    assert api.as_(OWNER).delete(f"/{hid}/rooms/{hall}/furniture/{piece}?character_id=10").status_code == 200
    assert _bag(api, ELITE) == 3 and api.get("/buffs?character_id=10").json()["trophy_bonus"] == 0.04
    _owe(api, hid, 2)
    assert api.get(f"/{hid}").json()["trophy_bonus"] == 0.0
    assert api.get("/buffs?character_id=10").json()["trophy_bonus"] == 0.0


def test_trophy_bonus_takes_the_best_house_and_is_capped(api):
    _trophies(api)
    first = _estate(api)
    second = _estate(api)
    halls = [_built(api, first, "trophy_hall", "floor1")]
    halls += [_built(api, second, "trophy_hall", "floor1"), _built(api, second, "trophy_hall", "floor1", x=1)]
    for hall in halls:
        api.sql("UPDATE house_rooms SET level = 3 WHERE id = :r", r=hall)
    for hall, pieces in zip(halls, (3, 15, 6)):
        for _ in range(pieces):
            api.sql("INSERT INTO house_furniture (room_id, item_id) VALUES (:r, :i)", r=hall, i=ELITE)
    assert api.as_(OWNER).get(f"/{first}").json()["trophy_bonus"] == 0.03
    assert api.get(f"/{second}").json()["trophy_bonus"] == houses.TROPHY_BONUS_CAP
    assert api.get("/buffs?character_id=10").json()["trophy_bonus"] == houses.TROPHY_BONUS_CAP


def test_guests_are_invited_and_sent_away(api):
    hid = _estate(api)
    assert api.as_(OWNER).post(f"/{hid}/guests", {"character_id": 10, "guest_character_id": 10}).status_code == 400
    assert api.post(f"/{hid}/guests", {"character_id": 10, "guest_character_id": 40}).status_code == 404  # NPC
    assert api.as_(FRIEND).post(f"/{hid}/guests", {"character_id": 20, "guest_character_id": 30}).status_code == 403
    assert api.as_(OWNER).post(f"/{hid}/guests", {"character_id": 10, "guest_character_id": 30}).status_code == 200
    assert api.post(f"/{hid}/guests", {"character_id": 10, "guest_character_id": 30}).status_code == 409
    api.post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20})
    assert api.post(f"/{hid}/guests", {"character_id": 10, "guest_character_id": 20}).status_code == 409
    house = api.get(f"/{hid}").json()
    assert [g["character"]["id"] for g in house["guests"]] == [30]
    assert [(h["id"], h["status"]) for h in api.as_(STRANGER).get("/my").json()] == [(hid, "guest")]
    assert api.as_(FRIEND).delete(f"/{hid}/guests/30?character_id=20").status_code == 403
    assert api.as_(STRANGER).delete(f"/{hid}/guests/30?character_id=30").status_code == 200
    assert api.as_(STRANGER).delete(f"/{hid}/guests/30?character_id=30").status_code == 404
    assert api.as_(OWNER).get(f"/{hid}").json()["guests"] == []
    # A guest becoming a resident stops being a guest.
    api.post(f"/{hid}/guests", {"character_id": 10, "guest_character_id": 30})
    api.post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 30})
    assert api.get(f"/{hid}").json()["guests"] == []


def test_a_guest_enters_only_guest_rooms_and_sleeps_there(api):
    hid = _estate(api)
    guest_room = _built(api, hid, "guest_room", "floor1")
    hall = _built(api, hid, "hall", "floor1", x=1)
    bath = _built(api, hid, "bath", "yard")
    api.as_(OWNER).post(f"/{hid}/rooms/{guest_room}/furniture", {"character_id": 10, "inventory_item_id": _give(api, 10)})
    api.post(f"/{hid}/guests", {"character_id": 10, "guest_character_id": 30})
    view = api.as_(STRANGER).get(f"/{hid}").json()
    (me,) = view["acting"]
    assert (me["is_guest"], me["room_ids"], me["can_take"], me["trophy_bonus"]) == (True, [guest_room], False, 0.0)
    assert {r["id"]: r["can_enter"] for r in view["rooms"]} == {guest_room: True, hall: False, bath: False}
    assert view["residents"] == [] and view["guests"] == []
    assert api.get(f"/rooms/{guest_room}").status_code == 200
    # Stage 7: a guest enters the house into the guest room, never elsewhere.
    entered = api.post(f"/{hid}/enter", {"character_id": 30})
    assert entered.status_code == 200 and entered.json()["room_id"] == guest_room
    assert api.post(f"/rooms/{hall}/go", {"character_id": 30}).status_code == 403
    assert api.post(f"/rooms/{guest_room}/posts", {"character_id": 30, "content": LONG}).status_code == 200
    assert api.post(f"/rooms/{hall}/posts", {"character_id": 30, "content": LONG}).status_code == 403
    assert api.post(f"/rooms/{bath}/bathe", {"character_id": 30}).status_code == 403
    r = api.post(f"/rooms/{guest_room}/sleep", {"character_id": 30})
    assert r.status_code == 200 and r.json()["sleep_factor"] == houses.BEDROOM_SLEEP_FACTOR[1] + 0.5
    # Sent away, the guest wakes up.
    assert api.as_(OWNER).delete(f"/{hid}/guests/30?character_id=10").status_code == 200
    assert api.sql("SELECT asleep_since, sleep_house_room_id FROM characters WHERE id = 30")[0] == (None, None)
    assert _where(api, 30) is None
    assert api.as_(STRANGER).post(f"/rooms/{guest_room}/posts", {"character_id": 30, "content": LONG}).status_code == 403


def test_a_sale_writes_the_guests_out(api, monkeypatch):
    hid = _estate(api)
    guest_room = _built(api, hid, "guest_room", "floor1")
    api.as_(OWNER).post(f"/{hid}/guests", {"character_id": 10, "guest_character_id": 20})
    _go(api, FRIEND, 20, guest_room)
    _go(api, OWNER, 10, guest_room)
    assert api.as_(FRIEND).post(f"/rooms/{guest_room}/sleep", {"character_id": 20}).status_code == 200
    api.as_(OWNER).put(f"/{hid}/sale", {"character_id": 10, "price": 100})
    assert api.as_(STRANGER).post(f"/{hid}/buy", {"character_id": 30}).status_code == 200
    assert api.sql("SELECT COUNT(*) FROM house_guests")[0][0] == 0
    assert api.sql("SELECT asleep_since FROM characters WHERE id = 20")[0][0] is None
    assert (_where(api, 20), _where(api, 10)) == (None, None)  # the guest and the old owner are out
    assert api.as_(FRIEND).get("/my").json() == []
    # Deleting a character drops its guest rows.
    api.as_(STRANGER).post(f"/{hid}/guests", {"character_id": 30, "guest_character_id": 20})
    monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", "t")
    api.c.post("/locations/houses/internal/character-deleted/20", headers={"X-Internal-Token": "t"})
    assert api.sql("SELECT COUNT(*) FROM house_guests")[0][0] == 0


# --- stage 7: presence inside the house --------------------------------------------


def test_entering_walking_and_leaving_the_house(api):
    hid, rooms = _house(api)
    r = api.as_(OWNER).post(f"/{hid}/enter", {"character_id": 10})
    assert r.status_code == 200, r.text
    # The first room in plan order; instant: no gold, no post anywhere.
    assert r.json() == {"house_id": hid, "room_id": rooms["hall"], "room_type": "hall", "room_name": "Гостиная"}
    assert _where(api, 10) == rooms["hall"] and _gold(api, 10) == 700 and api.awarded == []
    assert api.post(f"/rooms/{rooms['bedroom']}/go", {"character_id": 10}).json()["room_id"] == rooms["bedroom"]
    house = api.get(f"/{hid}").json()
    assert house["can_view_inside"] is True and house["acting"][0]["room_id"] == rooms["bedroom"]
    present = {r["room_type"]: [c["id"] for c in r["present"]] for r in house["rooms"]}
    assert present == {"hall": [], "bedroom": [10], "storage": []}
    assert api.post(f"/{hid}/enter", {"character_id": 10, "room_id": rooms["storage"]}).json()["room_id"] == rooms["storage"]
    assert api.post(f"/{hid}/leave", {"character_id": 10}).json() == {"house_id": hid, "room_id": None}
    assert _where(api, 10) is None and api.get(f"/{hid}").json()["acting"][0]["room_id"] is None
    assert api.post(f"/{hid}/leave", {"character_id": 10}).status_code == 200  # not inside: nothing happens


def test_who_may_enter_and_where(api):
    hid, rooms = _house(api)
    r = api.as_(STRANGER).post(f"/{hid}/enter", {"character_id": 30})
    assert r.status_code == 403 and r.json()["detail"] == "Вас не пускали в этот дом"
    assert api.post(f"/rooms/{rooms['hall']}/go", {"character_id": 30}).status_code == 403
    assert api.as_(STRANGER).post(f"/{hid}/enter", {"character_id": 10}).status_code == 403  # not their character
    assert _where(api, 10) is None
    api.as_(OWNER).post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20})
    assert api.as_(FRIEND).post(f"/{hid}/enter", {"character_id": 20}).json()["room_id"] == rooms["hall"]
    r = api.post(f"/rooms/{rooms['bedroom']}/go", {"character_id": 20})
    assert r.status_code == 403 and _where(api, 20) == rooms["hall"]
    # Away from the house nobody enters; a room of another house is not this house's.
    api.sql("UPDATE characters SET current_location_id = :f WHERE id = 10", f=FAR)
    r = api.as_(OWNER).post(f"/{hid}/enter", {"character_id": 10})
    assert r.status_code == 403 and r.json()["detail"] == houses.NOT_HERE
    api.sql("UPDATE characters SET current_location_id = :t WHERE id = 10", t=TOWN)
    assert api.post(f"/{hid}/enter", {"character_id": 10, "room_id": 9999}).status_code == 404
    # A room being built for the first time is not entered.
    api.sql("UPDATE house_build_costs SET build_hours = 6 WHERE room_type = 'hall' AND level = 1")
    api.sql("UPDATE characters SET currency_balance = 5000 WHERE id = 10")
    plot = _plot(api, kind="empty", rooms=[])
    other = api.as_(OWNER).post(f"/plots/{plot}/buy", {"character_id": 10}).json()["house_id"]
    r = api.as_(OWNER).post(f"/{other}/enter", {"character_id": 10})
    assert r.status_code == 409 and "нет готовой комнаты" in r.json()["detail"]
    site = api.post(f"/{other}/rooms", {**_cell(api, other), "character_id": 10, "room_type": "hall",
                                        "name": "Зал"}).json()["room_id"]
    assert api.as_(OWNER).post(f"/rooms/{site}/go", {"character_id": 10}).status_code == 409
    # A frozen house is not entered.
    _owe(api, hid, 2)
    assert api.as_(OWNER).post(f"/{hid}/enter", {"character_id": 10}).status_code == 409


def test_room_functions_need_the_character_in_that_room(api, recover):
    hid = _estate(api)
    hall = _built(api, hid, "hall", "floor1")
    bath = _built(api, hid, "bath", "yard")
    _go(api, OWNER, 10, hall)
    r = api.post(f"/rooms/{bath}/bathe", {"character_id": 10})
    assert r.status_code == 403 and r.json()["detail"] == houses.GO_TO_ROOM and recover["calls"] == []
    _go(api, OWNER, 10, bath)
    r = api.post(f"/rooms/{hall}/posts", {"character_id": 10, "content": LONG})
    assert r.status_code == 403 and r.json()["detail"] == "Сначала перейдите в эту комнату"
    assert api.post(f"/rooms/{bath}/bathe", {"character_id": 10}).status_code == 200


def test_presence_counts_only_in_the_house_location(api):
    hid, rooms = _house(api)
    _go(api, OWNER, 10, rooms["hall"])
    # A clear missed somewhere: the room stays written, the character stands elsewhere.
    api.sql("UPDATE characters SET current_location_id = :f WHERE id = 10", f=FAR)
    house = api.get(f"/{hid}").json()
    assert house["acting"][0]["room_id"] is None and all(r["present"] == [] for r in house["rooms"])
    r = api.post(f"/rooms/{rooms['hall']}/posts", {"character_id": 10, "content": LONG})
    assert r.status_code == 403 and r.json()["detail"] == houses.NOT_HERE


@pytest.mark.real_activity_lock
def test_a_sleeper_does_not_walk_about(api):
    hid, rooms = _house(api)
    _go(api, OWNER, 10, rooms["bedroom"])
    assert api.post(f"/rooms/{rooms['bedroom']}/sleep", {"character_id": 10}).status_code == 200
    for r in (api.post(f"/rooms/{rooms['hall']}/go", {"character_id": 10}),
              api.post(f"/{hid}/leave", {"character_id": 10})):
        assert r.status_code == 409 and "спит" in r.json()["detail"]
    assert _where(api, 10) == rooms["bedroom"]
    api.post("/wake", {"character_id": 10})
    assert api.post(f"/rooms/{rooms['hall']}/go", {"character_id": 10}).status_code == 200


def test_outsiders_see_the_facade_only(api):
    hid, rooms = _house(api)
    _go(api, OWNER, 10, rooms["hall"])
    pid = api.post(f"/rooms/{rooms['hall']}/posts", {"character_id": 10, "content": LONG}).json()["id"]
    api.put(f"/{hid}/sale", {"character_id": 10, "price": 500})
    for uid in (None, STRANGER):
        house = api.as_(uid).get(f"/{hid}").json()
        assert house["can_view_inside"] is False
        assert (house["rooms"], house["acting"], house["residents"], house["guests"], house["plan"]) == (
            [], [], [], [], None)
        assert (house["name"], house["image_url"], house["sale_price"], house["location_name"]) == (
            "Дом у мельницы", IMG, 500, f"Улица {TOWN}")
        assert api.get(f"/rooms/{rooms['hall']}").status_code == 403
    # The board still tells a buyer what the house holds.
    (listed,) = api.as_(None).get("/market").json()
    assert [r["room_type"] for r in listed["rooms"]] == ["hall", "bedroom", "storage"]
    # A moderator keeps looking in for moderation; a guest sees who is inside.
    api.as_(OWNER).post(f"/{hid}/guests", {"character_id": 10, "guest_character_id": 30})
    view = api.as_(STRANGER).get(f"/{hid}").json()
    assert view["can_view_inside"] is True
    assert next(r for r in view["rooms"] if r["id"] == rooms["hall"])["present"][0]["id"] == 10
    # An open hall is read by the guest too; a closed bedroom only by those let into it.
    assert api.as_(STRANGER).get(f"/rooms/{rooms['hall']}").status_code == 200
    r = api.get(f"/rooms/{rooms['bedroom']}")
    assert r.status_code == 403 and "впущенные" in r.json()["detail"]
    ROLES[FRIEND] = "moderator"
    try:
        assert api.as_(FRIEND).get(f"/rooms/{rooms['hall']}").json()["posts"][0]["id"] == pid
        assert api.as_(FRIEND).get(f"/{hid}").json()["can_view_inside"] is True
    finally:
        ROLES.pop(FRIEND)


def test_leaving_the_house_by_any_way_puts_the_character_out(api):
    hid, rooms = _house(api)
    rid = api.as_(OWNER).post(f"/{hid}/residents", {"character_id": 10, "resident_character_id": 20}).json()["id"]
    api.put(f"/{hid}/residents/{rid}", {"character_id": 10, "room_ids": [rooms["hall"], rooms["bedroom"]]})
    _go(api, FRIEND, 20, rooms["bedroom"])
    _go(api, OWNER, 10, rooms["storage"])
    # A room pulled down: whoever stood there is out.
    assert api.as_(OWNER).delete(f"/{hid}/rooms/{rooms['storage']}?character_id=10").status_code == 200
    assert _where(api, 10) is None
    # A resident sent away is out.
    assert api.delete(f"/{hid}/residents/{rid}?character_id=10").status_code == 200
    assert _where(api, 20) is None
