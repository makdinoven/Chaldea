"""FEAT-180 stage 2: house rooms seen from inventory-service.

A profession room (stage 6a: forge, alchemy lab, kitchen, ...) of the character's profession, in a house the character may use
and in the location the character stands in, raises crafting experience by its
level; a storage room holds stacks by its level; a room still being built
(level 0) gives nothing, and a finished upgrade counts at once.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import text

import house_workshop
import models
import schemas
from auth_http import get_current_user_via_http
from tests.test_craft_xp import xp_env  # noqa: F401  (fixture)

HOUSE, TOWN = 5, 1  # characters stand in location 1 by default in xp_env
OWNER, RESIDENT = 1, 2

_TABLES = ("house_furniture", "house_resident_rooms", "house_residents", "house_rooms", "houses", "house_plots")


@pytest.fixture()
def house(xp_env):  # noqa: F811
    db = xp_env["db"]
    for t in _TABLES:
        db.execute(text(f"DROP TABLE IF EXISTS {t}"))
    db.execute(text("CREATE TABLE house_plots (id INTEGER PRIMARY KEY, location_id INTEGER)"))
    db.execute(text("CREATE TABLE houses (id INTEGER PRIMARY KEY, plot_id INTEGER, owner_character_id INTEGER, "
                    "status TEXT DEFAULT 'active')"))
    db.execute(text("CREATE TABLE house_rooms (id INTEGER PRIMARY KEY, house_id INTEGER, room_type TEXT, "
                    "level INTEGER, upgrade_to_level INTEGER, upgrade_complete_at TIMESTAMP, "
                    "workshop_profession_id INTEGER)"))
    db.execute(text("CREATE TABLE house_residents (id INTEGER PRIMARY KEY, house_id INTEGER, character_id INTEGER)"))
    db.execute(text("CREATE TABLE house_resident_rooms (id INTEGER PRIMARY KEY, resident_id INTEGER, room_id INTEGER)"))
    db.execute(text("CREATE TABLE house_furniture (id INTEGER PRIMARY KEY, room_id INTEGER, item_id INTEGER)"))
    db.execute(text("INSERT INTO house_plots VALUES (1, :t)"), {"t": TOWN})
    db.execute(text("INSERT INTO houses (id, plot_id, owner_character_id) VALUES (:h, 1, :o)"), {"h": HOUSE, "o": OWNER})
    db.execute(text("INSERT OR IGNORE INTO characters (id, name, user_id) VALUES (:c, 'Resident', 2)"), {"c": RESIDENT})
    # Stage 7: where the character stands inside a house.
    db.execute(text("ALTER TABLE characters ADD COLUMN house_room_id INTEGER"))
    db.commit()

    def room(room_type, level, profession=None, upgrade_to=None, done_at=None, enter=True):
        """A room of the house; the owner walks into a new profession room (`enter=False` keeps it out)."""
        db.execute(text("INSERT INTO house_rooms (house_id, room_type, level, upgrade_to_level, "
                        "upgrade_complete_at, workshop_profession_id) VALUES (:h, :t, :l, :u, :d, :p)"),
                   {"h": HOUSE, "t": room_type, "l": level, "u": upgrade_to, "d": done_at, "p": profession})
        db.commit()
        room_id = db.execute(text("SELECT MAX(id) FROM house_rooms")).scalar()
        if enter and room_type in house_workshop.PROFESSION_ROOM_TYPES:
            stand(OWNER, room_id)
        return room_id

    def stand(character_id, room_id):
        db.execute(text("UPDATE characters SET house_room_id = :r WHERE id = :c"), {"r": room_id, "c": character_id})
        db.commit()

    def furnish(room_id, name, **bonus):
        it = models.Items(name=name, item_type="furniture", item_rarity="rare", item_level=1, max_stack_size=1,
                          is_unique=False, **bonus)
        db.add(it)
        db.commit()
        db.execute(text("INSERT INTO house_furniture (room_id, item_id) VALUES (:r, :i)"), {"r": room_id, "i": it.id})
        db.commit()

    yield {**xp_env, "room": room, "furnish": furnish, "stand": stand}
    for t in _TABLES:
        db.execute(text(f"DROP TABLE IF EXISTS {t}"))
    db.commit()


def _craft(env):
    resp = env["client"].post("/inventory/crafting/1/craft", json={"recipe_id": env["recipe"].id})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_no_workshop_no_bonus(house):
    assert _craft(house)["xp_earned"] == 10


def test_owner_workshop_of_the_profession_raises_crafting_xp(house):
    house["room"]("forge", 2, profession=house["profession"].id)
    assert house_workshop.workshop_level(house["db"], OWNER, house["profession"].id) == 2
    assert _craft(house)["xp_earned"] == 12  # 10 * (1 + 20%)


def test_workshop_of_another_profession_or_away_gives_nothing(house):
    house["room"]("forge", 3, profession=999)
    assert _craft(house)["xp_earned"] == 10
    house["room"]("forge", 3, profession=house["profession"].id)
    house["db"].execute(text("UPDATE characters SET current_location_id = 77 WHERE id = :c"), {"c": OWNER})
    house["db"].commit()
    assert _craft(house)["xp_earned"] == 10


def test_a_resident_needs_to_be_let_into_the_workshop(house):
    db, prof = house["db"], house["profession"].id
    ws = house["room"]("forge", 1, profession=prof)
    db.execute(text("INSERT INTO house_residents (id, house_id, character_id) VALUES (1, :h, :c)"),
               {"h": HOUSE, "c": RESIDENT})
    db.commit()
    house["stand"](RESIDENT, ws)
    assert house_workshop.workshop_level(db, RESIDENT, prof) == 0
    db.execute(text("INSERT INTO house_resident_rooms (resident_id, room_id) VALUES (1, :r)"), {"r": ws})
    db.commit()
    assert house_workshop.workshop_level(db, RESIDENT, prof) == 1


def test_levels_follow_building_and_finished_upgrades(house):
    db, prof = house["db"], house["profession"].id
    house["room"]("forge", 0, profession=prof, upgrade_to=1, done_at="2999-01-01 00:00:00")
    assert house_workshop.workshop_level(db, OWNER, prof) == 0
    house["room"]("forge", 1, profession=prof, upgrade_to=2, done_at="2000-01-01 00:00:00")
    assert house_workshop.workshop_level(db, OWNER, prof) == 2


def test_storage_capacity_by_level(house):
    house["room"]("storage", 1)
    house["room"]("storage", 3)
    house["room"]("storage", 0, upgrade_to=1, done_at="2999-01-01 00:00:00")
    caps = house_workshop.STORAGE_STACKS_BY_LEVEL
    assert house_workshop.storage_capacity(house["db"], HOUSE) == caps[1] + caps[3]


def test_missing_house_tables_mean_no_workshop(xp_env):  # noqa: F811
    assert house_workshop.workshop_level(xp_env["db"], OWNER, 1) == 0


# --- stage 3: furniture -----------------------------------------------------

def test_workshop_furniture_adds_to_the_level_bonus(house):
    ws = house["room"]("forge", 1, profession=house["profession"].id)
    house["furnish"](ws, "Наковальня", furniture_room_type="workshop", furniture_xp_bonus_pct=40,
                     furniture_refine_bonus_pct=5)
    bonus = house_workshop.workshop_bonus(house["db"], OWNER, house["profession"].id)
    assert bonus["level"] == 1
    assert bonus["xp"] == pytest.approx(0.10 + 0.40) and bonus["refine"] == pytest.approx(0.05 + 0.05)
    assert _craft(house)["xp_earned"] == 15  # 10 * 1.5


def test_storage_furniture_adds_stacks(house):
    st = house["room"]("storage", 2)
    house["furnish"](st, "Сундук", furniture_room_type="storage", furniture_storage_stacks=12)
    assert house_workshop.storage_capacity(house["db"], HOUSE) == house_workshop.STORAGE_STACKS_BY_LEVEL[2] + 12


def _item(**kw):
    base = {"name": "Мебель", "item_type": "furniture", "item_rarity": "common", "item_level": 1,
            "is_unique": False, "max_stack_size": 1, "furniture_room_type": "bedroom"}
    return schemas.ItemCreate(**{**base, **kw})


def test_furniture_item_rules():
    assert _item(furniture_sleep_bonus=0.5).furniture_sleep_bonus == 0.5
    with pytest.raises(ValueError):
        _item(furniture_room_type=None)
    with pytest.raises(ValueError):
        _item(furniture_room_type="hall", furniture_sleep_bonus=0.5)  # sleep bonus works in a bedroom only
    with pytest.raises(ValueError):
        _item(furniture_sleep_bonus=-1)
    with pytest.raises(ValueError):
        _item(item_type="misc")  # a room type on something that is not furniture


def test_a_frozen_house_workshop_gives_nothing(house):
    house["room"]("forge", 3, profession=house["profession"].id)
    house["db"].execute(text("UPDATE houses SET status = 'frozen'"))
    house["db"].commit()
    assert house_workshop.workshop_level(house["db"], OWNER, house["profession"].id) == 0


# --- stage 6a: profession rooms, cellar, kitchen, seeds -------------------------------

def test_any_profession_room_of_the_profession_counts(house):
    db, prof = house["db"], house["profession"].id
    house["room"]("hall", 3, profession=prof)  # not a profession room
    assert house_workshop.workshop_level(db, OWNER, prof) == 0
    house["room"]("alchemy_lab", 2, profession=prof)
    assert house_workshop.workshop_level(db, OWNER, prof) == 2


def test_a_cellar_holds_more_than_a_storage(house):
    house["room"]("storage", 1)
    cellar = house["room"]("cellar", 2)
    house["furnish"](cellar, "Бочка", furniture_room_type="storage", furniture_storage_stacks=5)
    caps = house_workshop.STORAGE_STACKS_BY_LEVEL[1] + house_workshop.CELLAR_STACKS_BY_LEVEL[2] + 5
    assert house_workshop.storage_capacity(house["db"], HOUSE) == caps


def test_only_a_cellar_is_storage_enough(house):
    house["room"]("cellar", 1)
    assert house_workshop.storage_capacity(house["db"], HOUSE) == house_workshop.CELLAR_STACKS_BY_LEVEL[1]


def test_kitchen_satiety_hours(house):
    db = house["db"]
    assert house_workshop.kitchen_satiety_hours(db, OWNER) == house_workshop.DEFAULT_SATIETY_HOURS
    kitchen = house["room"]("kitchen", 1)
    house["room"]("kitchen", 0, upgrade_to=1, done_at="2999-01-01 00:00:00")  # being built
    assert house_workshop.kitchen_satiety_hours(db, OWNER) == 30
    house["room"]("kitchen", 2, upgrade_to=3, done_at="2000-01-01 00:00:00")  # the best wins
    assert house_workshop.kitchen_satiety_hours(db, OWNER) == 48
    # A resident needs to be let into a kitchen.
    db.execute(text("INSERT INTO house_residents (id, house_id, character_id) VALUES (1, :h, :c)"),
               {"h": HOUSE, "c": RESIDENT})
    db.commit()
    db.execute(text("UPDATE characters SET current_location_id = :t WHERE id = :c"), {"t": TOWN, "c": RESIDENT})
    db.commit()
    assert house_workshop.kitchen_satiety_hours(db, RESIDENT) == 24
    db.execute(text("INSERT INTO house_resident_rooms (resident_id, room_id) VALUES (1, :r)"), {"r": kitchen})
    db.commit()
    assert house_workshop.kitchen_satiety_hours(db, RESIDENT) == 30
    # Away from the house, or in a frozen house, no kitchen.
    db.execute(text("UPDATE houses SET status = 'frozen'"))
    db.commit()
    assert house_workshop.kitchen_satiety_hours(db, OWNER) == 24


def test_eating_with_a_kitchen_lasts_longer(house):
    from tests.test_food_satiety import SATIETY_OK, _resp

    db = house["db"]
    db.execute(text("DROP TABLE IF EXISTS dungeon_sessions"))
    db.execute(text("CREATE TABLE dungeon_sessions (id INTEGER PRIMARY KEY, leader_character_id INTEGER, "
                    "status TEXT, started_at TIMESTAMP, finished_at TIMESTAMP)"))
    food = models.Items(name="Похлёбка", item_type="consumable", item_rarity="rare", item_level=1,
                        max_stack_size=10, is_unique=False, is_food=True)
    db.add(food)
    db.commit()
    row = models.CharacterInventory(character_id=OWNER, item_id=food.id, quantity=2)
    db.add(row)
    db.commit()
    house["room"]("kitchen", 2)
    with patch("main.httpx.post", return_value=_resp(201, SATIETY_OK)) as post:
        resp = house["client"].post(f"/inventory/{OWNER}/eat-food", json={"inventory_item_id": row.id})
    assert resp.status_code == 200, resp.text
    assert post.call_args.kwargs["json"]["duration_hours"] == 36
    assert resp.json()["satiety_hours"] == 36 and resp.json()["message"].endswith("Сытость на 36 ч")
    db.execute(text("DROP TABLE IF EXISTS dungeon_sessions"))
    db.commit()


def _seed(**kw):
    base = {"name": "Семена", "item_type": "resource", "item_rarity": "common", "item_level": 1,
            "is_unique": False, "max_stack_size": 20, "seed_result_item_id": 50, "seed_result_quantity": 3,
            "seed_grow_hours": 6, "seed_room_type": "garden", "seed_herbalism_xp": 10}
    return schemas.ItemCreate(**{**base, **kw})


def test_seed_item_rules():
    assert _seed().seed_room_type == "garden"
    plain = _seed(seed_result_item_id=None, seed_result_quantity=None, seed_grow_hours=None,
                  seed_room_type=None, seed_herbalism_xp=None)
    assert plain.seed_result_item_id is None
    for broken in (
        {"seed_grow_hours": None},             # all or nothing
        {"seed_room_type": "kitchen"},
        {"seed_result_quantity": 0}, {"seed_result_quantity": 101},
        {"seed_grow_hours": 0}, {"seed_grow_hours": 721},
        {"seed_herbalism_xp": -1}, {"seed_herbalism_xp": 10001},
        {"item_type": "misc"},                 # only a resource is a seed
    ):
        with pytest.raises(ValueError):
            _seed(**broken)


def test_admin_saves_a_seed_growing_into_an_existing_item(house):
    from tests.test_item_rarity_rules import ADMIN, _auth

    client = house["client"]
    house["app"].dependency_overrides.pop(get_current_user_via_http, None)  # the real admin check
    headers = {"Authorization": "Bearer t"}
    body = {"name": "Семена репы", "item_type": "resource", "item_rarity": "common", "item_level": 1,
            "is_unique": False, "max_stack_size": 20, "seed_result_item_id": 99999, "seed_result_quantity": 2,
            "seed_grow_hours": 4, "seed_room_type": "greenhouse", "seed_herbalism_xp": 3}
    with patch("auth_http.requests.get", return_value=_auth(ADMIN)):
        assert client.post("/inventory/items", json=body, headers=headers).status_code == 400
        created = client.post("/inventory/items", json={**body, "seed_result_item_id": 50}, headers=headers)
        assert created.status_code == 201, created.text
        item = created.json()
        assert (item["seed_result_item_id"], item["seed_room_type"], item["seed_grow_hours"]) == (50, "greenhouse", 4)
        itself = client.put(f"/inventory/items/{item['id']}", json={**body, "seed_result_item_id": item["id"]},
                            headers=headers)
        assert itself.status_code == 400
        # Turned into something else, it stops being a seed.
        plain = {k: v for k, v in body.items() if not k.startswith("seed_")}
        moved = client.put(f"/inventory/items/{item['id']}", json={**plain, "item_type": "misc"}, headers=headers)
        assert moved.status_code == 200, moved.text
        assert moved.json()["seed_result_item_id"] is None


def test_the_workshop_works_only_for_the_one_standing_in_it(house):
    """Stage 7: the house's location is not enough — the character stands in the profession room."""
    db, prof = house["db"], house["profession"].id
    hall = house["room"]("hall", 1)
    forge = house["room"]("forge", 3, profession=prof, enter=False)
    assert house_workshop.workshop_level(db, OWNER, prof) == 0
    house["stand"](OWNER, hall)
    assert _craft(house)["xp_earned"] == 10
    house["stand"](OWNER, forge)
    assert house_workshop.workshop_level(db, OWNER, prof) == 3
    assert _craft(house)["xp_earned"] == 13  # 10 * (1 + 30%)
    # Standing in a better forge does not count the other forges of the house.
    house["room"]("forge", 1, profession=prof)
    assert house_workshop.workshop_level(db, OWNER, prof) == 1


def test_the_kitchen_satiety_stays_with_the_location(house):
    """Stage 7 left the kitchen's longer satiety as it was: eaten anywhere in the house's location."""
    db = house["db"]
    house["room"]("kitchen", 2, enter=False)
    assert house_workshop.kitchen_satiety_hours(db, OWNER) == 36
