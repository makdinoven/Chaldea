"""
FEAT-201 — the item stealth modifier `items.stealth_modifier` (inventory-service).

Stealth is the 11th primary character stat; items and food grant it like any
other main stat. Locked down here:

  * model column + migration 035 (real Alembic Operations on SQLite: nullable
    INT default 0, existing rows 0, idempotent, downgrade drops, chain head);
  * lists: MAIN_STAT_FIELDS (so sharpening + gems + ALL_MODIFIER_FIELDS),
    STAT_DISPLAY_NAMES «Скрытность», gathering-tool forbidden fields; guard
    tests that every modifier field is mapped by build_modifiers_dict and named;
  * build_modifiers_dict: base, negative, sharpening (+1 per count), gems;
  * routes: admin create / update / admin read / internal read round-trip,
    gathering tool with stealth rejected in Russian;
  * equip sends {"stealth": n}, unequip sends {"stealth": -n};
  * /internal/equipment-modifiers sums worn stealth (sharpening + gems);
  * eat-food sends the stealth modifier into the satiety payload;
  * sharpen: info lists stealth, sharpening an equipped item sends {"stealth": 1};
  * the mask validator text «Скрывать личность может только головной убор».
"""

import importlib.util
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

import auth_http
import crud
import models
import schemas
from auth_http import UserRead, get_current_user_via_http

from tests.test_sharpening import sharpen_env  # noqa: F401  (fixture re-use)

TOKEN = "test-internal-token"
INTERNAL = {"X-Internal-Token": TOKEN}
HEADERS = {"Authorization": "Bearer admin-token"}
ADMIN = {"id": 1, "username": "admin", "role": "admin",
         "permissions": ["items:create", "items:update", "items:read"]}


@pytest.fixture(autouse=True)
def _internal_token(monkeypatch):
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)


def _auth_ok():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = ADMIN
    return resp


def _item(db, name="Плащ теней", item_type="cloak", **mods):
    item = models.Items(name=name, item_type=item_type, item_rarity="common", item_level=1,
                        max_stack_size=1, is_unique=False, **mods)
    db.add(item)
    db.flush()
    return item


# ===========================================================================
# 1. Lists, display names, schemas
# ===========================================================================

class TestLists:

    def test_stealth_in_main_stat_lists(self):
        assert "stealth_modifier" in crud.MAIN_STAT_FIELDS
        assert "stealth_modifier" in crud.ALL_SHARPENABLE_FIELDS
        assert "stealth_modifier" in crud.ALL_MODIFIER_FIELDS
        assert crud.STAT_DISPLAY_NAMES["stealth_modifier"] == "Скрытность"

    def test_every_modifier_field_has_a_display_name(self):
        missing = [f for f in crud.MAIN_STAT_FIELDS + crud.FLOAT_STAT_FIELDS
                   if f not in crud.STAT_DISPLAY_NAMES]
        assert missing == []

    @pytest.mark.parametrize("field", [f for f in crud.ALL_MODIFIER_FIELDS if f != "damage_modifier"])
    def test_build_modifiers_dict_maps_every_modifier_field(self, field):
        """Guard: a field present in the lists but forgotten in build_modifiers_dict
        would be sharpenable/socketable yet never reach the character."""
        item = models.Items(name="x", item_type="body", **{field: 3})
        assert crud.build_modifiers_dict(item) == {field[:-len("_modifier")]: 3}

    def test_model_column(self):
        col = models.Items.__table__.c.stealth_modifier
        assert col.nullable is True

    def test_schemas_carry_stealth_modifier(self):
        assert "stealth_modifier" in schemas.ItemBase.__fields__
        assert "stealth_modifier" in schemas.ItemResponse.__fields__
        assert "stealth_modifier" in schemas.GATHERING_TOOL_FORBIDDEN_STAT_FIELDS

    def test_schema_rejects_non_integer(self):
        with pytest.raises(ValidationError):
            schemas.ItemCreate(name="x", item_level=1, item_type="cloak", item_rarity="common",
                               max_stack_size=1, is_unique=False, stealth_modifier="много")

    def test_gathering_tool_with_stealth_rejected(self):
        body = dict(name="Кирка тени", item_level=1, item_type="gathering_tool", item_rarity="rare",
                    max_stack_size=1, is_unique=False, max_durability=50, tool_category="pickaxe",
                    stealth_modifier=5)
        with pytest.raises(ValidationError) as exc:
            schemas.ItemCreate(**body)
        assert "Инструмент сбора не может иметь модификаторы экипировки" in str(exc.value)
        body["stealth_modifier"] = 0
        schemas.ItemCreate(**body)   # zero is fine

    def test_mask_validator_text(self):
        with pytest.raises(ValidationError) as exc:
            schemas.ItemCreate(name="x", item_level=1, item_type="cloak", item_rarity="common",
                               max_stack_size=1, is_unique=False, is_mask=True)
        assert "Скрывать личность может только головной убор" in str(exc.value)
        assert "Маской" not in str(exc.value)


# ===========================================================================
# 2. build_modifiers_dict
# ===========================================================================

class TestBuildModifiersDict:

    def test_base_and_negative(self):
        item = models.Items(name="x", item_type="cloak", stealth_modifier=7, agility_modifier=2)
        assert crud.build_modifiers_dict(item) == {"stealth": 7, "agility": 2}
        assert crud.build_modifiers_dict(item, negative=True) == {"stealth": -7, "agility": -2}

    def test_zero_or_null_not_sent(self):
        assert "stealth" not in crud.build_modifiers_dict(models.Items(name="x", stealth_modifier=0))
        assert "stealth" not in crud.build_modifiers_dict(models.Items(name="x", stealth_modifier=None))

    def test_sharpening_adds_one_per_count(self):
        item = models.Items(name="x", item_type="cloak", stealth_modifier=4)
        mods = crud.build_modifiers_dict(item, enhancement_bonuses={"stealth_modifier": 3})
        assert mods["stealth"] == 7
        # a stat the item does not have can be sharpened from zero
        bare = models.Items(name="y", item_type="cloak")
        assert crud.build_modifiers_dict(bare, enhancement_bonuses={"stealth_modifier": 2}) == {"stealth": 2}

    def test_gems_add_stealth(self):
        ring = models.Items(name="Кольцо", item_type="ring", stealth_modifier=1)
        gem = models.Items(name="Дымчатый кварц", item_type="gem", stealth_modifier=5)
        assert crud.build_modifiers_dict(ring, gem_items=[gem, gem])["stealth"] == 11
        assert crud.get_gem_modifiers_dict(gem) == {"Скрытность": 5}

    def test_broken_item_gives_nothing(self):
        item = models.Items(name="x", item_type="cloak", stealth_modifier=9)
        assert crud.build_modifiers_dict(item, current_durability=0, max_durability=10) == {}


# ===========================================================================
# 3. Admin routes: create / update / read
# ===========================================================================

def _body(**overrides):
    body = {"name": "Плащ тени", "item_level": 1, "item_type": "cloak", "item_rarity": "rare",
            "max_stack_size": 1, "is_unique": False}
    body.update(overrides)
    return body


class TestRoutes:

    def test_create_update_read_round_trip(self, client, db_session):
        with patch("auth_http.requests.get", return_value=_auth_ok()):
            resp = client.post("/inventory/items", json=_body(stealth_modifier=12), headers=HEADERS)
            assert resp.status_code == 201, resp.text
            item_id = resp.json()["id"]
            assert resp.json()["stealth_modifier"] == 12

            upd = client.put(f"/inventory/items/{item_id}", json=_body(stealth_modifier=3), headers=HEADERS)
            assert upd.status_code == 200, upd.text
            assert upd.json()["stealth_modifier"] == 3

            admin = client.get(f"/inventory/admin/items/{item_id}", headers=HEADERS)
            assert admin.status_code == 200, admin.text
            assert admin.json()["stealth_modifier"] == 3

        internal = client.get(f"/inventory/internal/items/{item_id}", headers=INTERNAL)
        assert internal.status_code == 200
        assert internal.json()["stealth_modifier"] == 3
        db_session.expire_all()
        assert db_session.query(models.Items).get(item_id).stealth_modifier == 3

    def test_create_without_stealth_defaults_to_zero_or_null(self, client, db_session):
        with patch("auth_http.requests.get", return_value=_auth_ok()):
            resp = client.post("/inventory/items", json=_body(), headers=HEADERS)
        assert resp.status_code == 201, resp.text
        assert resp.json()["stealth_modifier"] in (0, None)

    def test_gathering_tool_with_stealth_is_422(self, client, db_session):
        body = _body(name="Кирка тени", item_type="gathering_tool", max_durability=50,
                     tool_category="pickaxe", stealth_modifier=5)
        with patch("auth_http.requests.get", return_value=_auth_ok()):
            resp = client.post("/inventory/items", json=body, headers=HEADERS)
        assert resp.status_code == 422
        assert "Инструмент сбора не может иметь модификаторы экипировки" in resp.text
        assert db_session.query(models.Items).filter_by(name="Кирка тени").count() == 0

    @pytest.mark.parametrize("value", ["'; DROP TABLE items; --", "1 OR 1=1", "много"])
    def test_injection_like_values_rejected(self, client, db_session, value):
        with patch("auth_http.requests.get", return_value=_auth_ok()):
            resp = client.post("/inventory/items", json=_body(stealth_modifier=value), headers=HEADERS)
        assert resp.status_code == 422


# ===========================================================================
# 4. Equip / unequip
# ===========================================================================

CHAR = 1


@pytest.fixture()
def equip_env(client, db_session):
    from main import app

    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.execute(text(
        "CREATE TABLE characters (id INTEGER PRIMARY KEY, level INTEGER DEFAULT 1, user_id INTEGER, "
        "id_class INTEGER, is_npc INTEGER DEFAULT 0)"))
    db_session.execute(text(f"INSERT INTO characters (id, user_id, id_class, is_npc) VALUES ({CHAR}, 1, 1, 0)"))
    db_session.add(models.EquipmentSlot(character_id=CHAR, slot_type="body", is_enabled=True))
    armor = models.Items(name="Роба тени", item_type="body", item_rarity="common", item_level=1,
                         max_stack_size=1, is_unique=False, stealth_modifier=6, agility_modifier=1)
    db_session.add(armor)
    db_session.commit()
    db_session.add(models.CharacterInventory(character_id=CHAR, item_id=armor.id, quantity=1))
    db_session.commit()

    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=1, username="p", role="user", permissions=[])
    with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock) as apply, \
         patch("main._reconcile_perks_async", new_callable=AsyncMock), \
         patch("main._track_cumulative_stats_async", new_callable=AsyncMock), \
         patch("main._evaluate_titles_async", new_callable=AsyncMock), \
         patch("main._in_background"):
        yield {"client": client, "apply": apply, "armor": armor}
    app.dependency_overrides.pop(get_current_user_via_http, None)
    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.commit()


def _sent_mods(apply_mock):
    return [c.args[1] if len(c.args) > 1 else c.kwargs.get("modifiers") for c in apply_mock.await_args_list]


class TestEquip:

    def test_equip_and_unequip_send_stealth(self, equip_env):
        c = equip_env["client"]
        resp = c.post(f"/inventory/{CHAR}/equip", json={"item_id": equip_env["armor"].id})
        assert resp.status_code == 200, resp.text
        assert {"stealth": 6, "agility": 1} in _sent_mods(equip_env["apply"])

        equip_env["apply"].reset_mock()
        resp = c.post(f"/inventory/{CHAR}/unequip", params={"slot_type": "body"})
        assert resp.status_code == 200, resp.text
        assert {"stealth": -6, "agility": -1} in _sent_mods(equip_env["apply"])


# ===========================================================================
# 5. /internal/equipment-modifiers
# ===========================================================================

class TestEquipmentModifiersInternal:

    def test_worn_stealth_summed_with_sharpening_and_gems(self, client, db_session):
        db = db_session
        gem = _item(db, "Дымчатый кварц", item_type="gem", stealth_modifier=2)
        cloak = _item(db, "Плащ", item_type="cloak", stealth_modifier=10)
        ring = _item(db, "Кольцо", item_type="ring", stealth_modifier=1)
        s1 = models.EquipmentSlot(character_id=77, slot_type="cloak", item_id=cloak.id, is_enabled=True,
                                  enhancement_points_spent=2)
        crud.set_enhancement_bonuses(s1, {"stealth_modifier": 2})
        s2 = models.EquipmentSlot(character_id=77, slot_type="ring", item_id=ring.id, is_enabled=True)
        crud.set_socketed_gems(s2, [gem.id, None, gem.id])
        db.add_all([s1, s2])
        db.commit()

        resp = client.post("/inventory/internal/equipment-modifiers",
                           json={"character_ids": [77]}, headers=INTERNAL)
        assert resp.status_code == 200, resp.text
        mods = resp.json()["modifiers"]["77"]
        assert mods["stealth"] == (10 + 2) + (1 + 2 + 2)


# ===========================================================================
# 6. Food
# ===========================================================================

class TestEatFood:

    def test_food_stealth_goes_into_the_satiety_payload(self, client, db_session):
        from main import app

        db = db_session
        db.execute(text("DROP TABLE IF EXISTS characters"))
        db.execute(text("CREATE TABLE characters (id INTEGER PRIMARY KEY, level INTEGER DEFAULT 1, "
                        "user_id INTEGER, name TEXT)"))
        db.execute(text("INSERT INTO characters (id, user_id, name) VALUES (1, 1, 'Hero')"))
        db.execute(text("DROP TABLE IF EXISTS dungeon_sessions"))
        db.execute(text("CREATE TABLE dungeon_sessions (id INTEGER PRIMARY KEY, leader_character_id INTEGER, "
                        "status TEXT, started_at TIMESTAMP, finished_at TIMESTAMP)"))
        food = models.Items(name="Тихий ужин", item_level=1, item_type="consumable", item_rarity="common",
                            max_stack_size=20, is_unique=False, is_food=True, stealth_modifier=4,
                            health_recovery=5)
        db.add(food)
        db.flush()
        row = models.CharacterInventory(character_id=1, item_id=food.id, quantity=2)
        db.add(row)
        db.commit()

        ok = MagicMock(spec=httpx.Response)
        ok.status_code = 201
        ok.json.return_value = {"satiety": {
            "item_id": food.id, "source_item_name": "Тихий ужин", "rarity": "common",
            "regen_bonus_percent": 50, "modifiers": {"stealth": 4},
            "started_at": "2026-11-04T10:00:00", "expires_at": "2026-11-05T10:00:00",
            "remaining_seconds": 86400}, "stats_changed": True}
        app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
            id=1, username="hero", role="user", permissions=[])
        try:
            with patch("main.httpx.post", return_value=ok) as post:
                resp = client.post("/inventory/1/eat-food", json={"inventory_item_id": row.id})
        finally:
            app.dependency_overrides.pop(get_current_user_via_http, None)
            db.execute(text("DROP TABLE IF EXISTS characters"))
            db.execute(text("DROP TABLE IF EXISTS dungeon_sessions"))
            db.commit()
        assert resp.status_code == 200, resp.text
        assert post.call_args.kwargs["json"]["modifiers"] == {"stealth": 4}


# ===========================================================================
# 7. Sharpening
# ===========================================================================

class TestSharpenStealth:

    def test_sharpen_info_lists_stealth(self, sharpen_env):
        c = sharpen_env["client"]
        resp = c.get(f"/inventory/crafting/1/sharpen-info/{sharpen_env['weapon_inv'].id}?source=inventory")
        assert resp.status_code == 200, resp.text
        stat = next(s for s in resp.json()["stats"] if s["field"] == "stealth_modifier")
        assert stat["name"] == "Скрытность"
        assert stat["is_existing"] is False and stat["can_sharpen"] is True

    def test_sharpen_equipped_item_on_stealth_sends_plus_one(self, sharpen_env):
        db = sharpen_env["db"]
        c = sharpen_env["client"]
        slot = models.EquipmentSlot(character_id=1, slot_type="main_weapon",
                                    item_id=sharpen_env["weapon"].id, is_enabled=True)
        db.add(slot)
        db.commit()
        apply = AsyncMock()
        with patch("main.random.random", return_value=0.01), \
             patch("main.apply_modifiers_in_attributes_service", apply):
            resp = c.post("/inventory/crafting/1/sharpen", json={
                "inventory_item_id": slot.id, "whetstone_item_id": sharpen_env["ws_inv"].id,
                "stat_field": "stealth_modifier", "source": "equipment",
            })
        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True
        db.expire_all()
        assert json.loads(db.query(models.EquipmentSlot).get(slot.id).enhancement_bonuses) == {"stealth_modifier": 1}
        apply.assert_called_once()
        assert apply.call_args[0][1] == {"stealth": 1}


# ===========================================================================
# 8. Migration 035_item_stealth_modifier
# ===========================================================================

_VERSIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic", "versions"))


def _load(filename):
    spec = importlib.util.spec_from_file_location(filename[:-3], os.path.join(_VERSIONS_DIR, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def migration_db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    conn = engine.connect()
    conn.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
                      "luck_modifier INTEGER DEFAULT 0)"))
    conn.execute(text("INSERT INTO items (name, luck_modifier) VALUES ('Старый плащ', 2)"))
    conn.commit()
    mod = _load("035_item_stealth_modifier.py")
    mod.op = Operations(MigrationContext.configure(conn))
    yield conn, mod
    conn.close()
    engine.dispose()


def _cols(conn):
    return {c["name"]: c for c in inspect(conn).get_columns("items")}


class TestMigration035:

    def test_revision_chain(self):
        mod = _load("035_item_stealth_modifier.py")
        assert mod.revision == "035_item_stealth_modifier"
        assert mod.down_revision == "034_item_mask"
        assert len(mod.revision) <= 32

    def test_upgrade_downgrade_upgrade(self, migration_db):
        conn, mod = migration_db
        mod.upgrade()
        conn.commit()
        cols = _cols(conn)
        assert "stealth_modifier" in cols and cols["stealth_modifier"]["nullable"] is True
        assert conn.execute(text("SELECT stealth_modifier FROM items")).scalar() == 0
        conn.execute(text("INSERT INTO items (name) VALUES ('Новый')"))
        assert conn.execute(text("SELECT stealth_modifier FROM items WHERE name = 'Новый'")).scalar() == 0
        assert conn.execute(text("SELECT luck_modifier FROM items WHERE name = 'Старый плащ'")).scalar() == 2

        mod.upgrade()        # idempotent
        conn.commit()

        mod.downgrade()
        conn.commit()
        assert "stealth_modifier" not in _cols(conn)
        assert conn.execute(text("SELECT COUNT(*) FROM items")).scalar() == 2
        mod.downgrade()      # idempotent
        conn.commit()

        mod.upgrade()
        conn.commit()
        assert "stealth_modifier" in _cols(conn)
