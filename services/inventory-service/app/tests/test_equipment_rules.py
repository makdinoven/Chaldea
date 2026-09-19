"""
Class / subclass equipment rules.

- scope resolution: no rules anywhere / class row before a subclass / subclass row after / NPCs exempt
- equip: armor class check, allowed hands, requested hand, two-handed weapons
  (main hand only, clear and lock the off-hand)
- admin CRUD: validation, auth, revalidation of characters of the class after a save
- item edit changing the weapon kind revalidates its wearers
- internal revalidate endpoint and the public per-character rules endpoint
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

import equipment_rules
import models
from auth_http import UserRead, get_current_user_via_http
import auth_http


# FEAT-169: the /inventory/internal/* routes now require `X-Internal-Token`.
_TOKEN = "test-internal-token"
_INTERNAL_HEADERS = {"X-Internal-Token": _TOKEN}


@pytest.fixture(autouse=True)
def _internal_token(monkeypatch):
    """`verify_internal_token` reads a module-level constant — pin it."""
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", _TOKEN)




CHAR = 1
USER = 1


# ---------------------------------------------------------------------------
# Shared-DB tables owned by other services
# ---------------------------------------------------------------------------

_DDL = [
    "DROP TABLE IF EXISTS characters",
    """CREATE TABLE characters (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        id_class INTEGER,
        is_npc INTEGER DEFAULT 0
    )""",
    "DROP TABLE IF EXISTS classes",
    "CREATE TABLE classes (id_class INTEGER PRIMARY KEY, name TEXT)",
    "DROP TABLE IF EXISTS character_tree_progress",
    """CREATE TABLE character_tree_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        character_id INTEGER, tree_id INTEGER, node_id INTEGER
    )""",
    "DROP TABLE IF EXISTS tree_nodes",
    """CREATE TABLE tree_nodes (
        id INTEGER PRIMARY KEY, node_type TEXT, subclass_key TEXT
    )""",
]

_TEARDOWN = [
    "DROP TABLE IF EXISTS characters",
    "DROP TABLE IF EXISTS classes",
    "DROP TABLE IF EXISTS character_tree_progress",
    "DROP TABLE IF EXISTS tree_nodes",
]


@pytest.fixture()
def world(db_session):
    for stmt in _DDL:
        db_session.execute(text(stmt))
    db_session.execute(text("INSERT INTO classes VALUES (1, 'Воин'), (2, 'Плут'), (3, 'Маг')"))
    db_session.execute(text(f"INSERT INTO characters VALUES ({CHAR}, {USER}, 1, 0)"))
    db_session.execute(text("INSERT INTO tree_nodes VALUES (10, 'subclass_choice', 'warrior_guardian')"))
    db_session.commit()
    for slot_type in ("head", "body", "main_weapon", "additional_weapons"):
        db_session.add(models.EquipmentSlot(character_id=CHAR, slot_type=slot_type))
    db_session.commit()
    yield db_session
    for stmt in _TEARDOWN:
        db_session.execute(text(stmt))
    db_session.commit()


@pytest.fixture()
def player(client, world):
    from main import app

    user = UserRead(id=USER, username="player", role="user", permissions=[])
    app.dependency_overrides[get_current_user_via_http] = lambda: user
    # equip/unequip are `async def`, so they use the awaited `_async` variants
    # of the fire-and-forget calls (review #5) — those are the ones to stub.
    with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock), \
         patch("main._reconcile_perks_async", new_callable=AsyncMock), \
         patch("main._track_cumulative_stats_async", new_callable=AsyncMock), \
         patch("main._evaluate_titles_async", new_callable=AsyncMock), \
         patch("main._reconcile_perks"), patch("main._track_cumulative_stats"), \
         patch("main.httpx.post"):
        yield client
    app.dependency_overrides.pop(get_current_user_via_http, None)


ADMIN_HEADERS = {"Authorization": "Bearer admin"}


def _auth(permissions):
    from unittest.mock import MagicMock

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"id": 99, "username": "admin", "role": "admin" if permissions else "user",
                              "permissions": permissions}
    return resp


def _as_admin():
    """Swap the player override for an admin one (require_permission reads the same dependency)."""
    from main import app

    admin = UserRead(id=99, username="admin", role="admin", permissions=["items:update"])
    app.dependency_overrides[get_current_user_via_http] = lambda: admin


def _item(db, name, item_type="weapon", kind=None, armor=None):
    item = models.Items(
        name=name, item_type=item_type, item_rarity="common", item_level=1,
        max_stack_size=1, is_unique=False, weapon_subclass=kind, armor_subclass=armor,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _give(db, item):
    inv = models.CharacterInventory(character_id=CHAR, item_id=item.id, quantity=1)
    db.add(inv)
    db.commit()
    return inv


def _rule(db, class_id=1, subclass_key=None, armor=(), main=(), off=()):
    db.add(models.EquipmentRule(
        scope_key=equipment_rules.scope_key(class_id, subclass_key),
        class_id=class_id, subclass_key=subclass_key,
        armor_classes=json.dumps(list(armor)), main_hand=json.dumps(list(main)), off_hand=json.dumps(list(off)),
    ))
    db.commit()


def _choose_subclass(db):
    db.execute(text(f"INSERT INTO character_tree_progress (character_id, tree_id, node_id) VALUES ({CHAR}, 1, 10)"))
    db.commit()


def _slot(db, slot_type):
    db.expire_all()
    return db.query(models.EquipmentSlot).filter_by(character_id=CHAR, slot_type=slot_type).first()


def _equip(client, item, slot_type=None):
    body = {"item_id": item.id}
    if slot_type:
        body["slot_type"] = slot_type
    return client.post(f"/inventory/{CHAR}/equip", json=body)


# ===========================================================================
# 1. Scope resolution
# ===========================================================================

class TestScope:

    def test_no_rules_anywhere_is_unrestricted(self, world):
        rules = equipment_rules.rules_for_character(world, CHAR)
        assert rules.restricted is False

    def test_class_row_applies_before_subclass(self, world):
        _rule(world, armor=["cloth"], main=["kind:sword"])
        _rule(world, subclass_key="warrior_guardian", armor=["heavy_armor"])
        rules = equipment_rules.rules_for_character(world, CHAR)
        assert rules.armor_classes == {"cloth"}
        assert rules.subclass_key is None

    def test_subclass_row_replaces_class_row(self, world):
        _rule(world, armor=["cloth"])
        _rule(world, subclass_key="warrior_guardian", armor=["heavy_armor"], main=["category:one_and_half"])
        _choose_subclass(world)
        rules = equipment_rules.rules_for_character(world, CHAR)
        assert rules.subclass_key == "warrior_guardian"
        assert rules.armor_classes == {"heavy_armor"}
        assert "katana" in rules.main_hand_kinds and "sword" not in rules.main_hand_kinds

    def test_subclass_without_row_is_unrestricted(self, world):
        _rule(world, armor=["cloth"])
        _choose_subclass(world)
        assert equipment_rules.rules_for_character(world, CHAR).restricted is False

    def test_npc_is_exempt(self, world):
        _rule(world, armor=[])
        world.execute(text(f"UPDATE characters SET is_npc = 1 WHERE id = {CHAR}"))
        world.commit()
        assert equipment_rules.rules_for_character(world, CHAR).restricted is False


class TestTokens:

    def test_category_expands_to_its_kinds(self):
        kinds = equipment_rules.expand_hand_tokens(["category:shield", "kind:dagger"])
        assert kinds == {"buckler", "targe", "tower_shield", "dagger"}

    @pytest.mark.parametrize("token", ["category:two_handed", "category:polearm", "kind:halberd", "kind:zweihander"])
    def test_two_handed_rejected_for_off_hand(self, token):
        with pytest.raises(ValueError):
            equipment_rules.validate_hand_tokens([token], off_hand=True)

    @pytest.mark.parametrize("token", ["category:laser", "kind:laser_sword", "dagger", "category:shield; DROP TABLE"])
    def test_garbage_rejected(self, token):
        with pytest.raises(ValueError):
            equipment_rules.validate_hand_tokens([token], off_hand=False)


# ===========================================================================
# 2. Equip
# ===========================================================================

class TestEquip:

    def test_forbidden_armor_class_rejected(self, player, world):
        _rule(world, armor=["cloth"])
        plate = _item(world, "Латы", item_type="body", armor="heavy_armor")
        _give(world, plate)
        resp = _equip(player, plate)
        assert resp.status_code == 400
        assert "класс" in resp.json()["detail"]
        assert _slot(world, "body").item_id is None

    def test_allowed_armor_and_unclassed_armor_equip(self, player, world):
        _rule(world, armor=["cloth"])
        robe = _item(world, "Роба", item_type="body", armor="cloth")
        hat = _item(world, "Шапка", item_type="head")
        _give(world, robe)
        _give(world, hat)
        assert _equip(player, robe).status_code == 200
        assert _equip(player, hat).status_code == 200

    def test_weapon_goes_to_free_allowed_hand(self, player, world):
        _rule(world, armor=[], main=["kind:sword"], off=["category:shield"])
        shield = _item(world, "Баклер", kind="buckler")
        _give(world, shield)
        resp = _equip(player, shield)
        assert resp.status_code == 200, resp.text
        assert resp.json()["slot_type"] == "additional_weapons"

    def test_weapon_not_allowed_in_any_hand(self, player, world):
        _rule(world, armor=[], main=["kind:sword"], off=[])
        bow = _item(world, "Лук", kind="bow")
        _give(world, bow)
        resp = _equip(player, bow)
        assert resp.status_code == 400
        assert "вид оружия" in resp.json()["detail"]

    def test_requested_hand_not_allowed(self, player, world):
        _rule(world, armor=[], main=["kind:dagger"], off=[])
        dagger = _item(world, "Кинжал", kind="dagger")
        _give(world, dagger)
        resp = _equip(player, dagger, "additional_weapons")
        assert resp.status_code == 400
        assert "доп. руке" in resp.json()["detail"]

    def test_requested_hand_honoured(self, player, world):
        dagger = _item(world, "Кинжал", kind="dagger")
        _give(world, dagger)
        resp = _equip(player, dagger, "additional_weapons")
        assert resp.status_code == 200
        assert resp.json()["slot_type"] == "additional_weapons"

    def test_invalid_hand_value_rejected(self, player, world):
        dagger = _item(world, "Кинжал", kind="dagger")
        _give(world, dagger)
        assert _equip(player, dagger, "head").status_code == 422

    def test_two_handed_never_in_off_hand(self, player, world):
        maul = _item(world, "Молот", kind="maul")
        _give(world, maul)
        resp = _equip(player, maul, "additional_weapons")
        assert resp.status_code == 400
        assert "Двуручное" in resp.json()["detail"]

    def test_two_handed_clears_off_hand(self, player, world):
        shield = _item(world, "Тарч", kind="targe")
        _give(world, shield)
        assert _equip(player, shield, "additional_weapons").status_code == 200

        maul = _item(world, "Молот", kind="maul")
        _give(world, maul)
        resp = _equip(player, maul)
        assert resp.status_code == 200, resp.text
        assert resp.json()["slot_type"] == "main_weapon"
        assert _slot(world, "additional_weapons").item_id is None
        back = world.query(models.CharacterInventory).filter_by(character_id=CHAR, item_id=shield.id).first()
        assert back is not None and back.quantity == 1

    def test_off_hand_locked_by_two_handed(self, player, world):
        maul = _item(world, "Молот", kind="maul")
        dagger = _item(world, "Кинжал", kind="dagger")
        _give(world, maul)
        _give(world, dagger)
        assert _equip(player, maul).status_code == 200

        resp = _equip(player, dagger, "additional_weapons")
        assert resp.status_code == 400
        assert "двуручным" in resp.json()["detail"]

        # Without a hand the dagger swaps into the main hand instead
        resp = _equip(player, dagger)
        assert resp.status_code == 200
        assert resp.json()["slot_type"] == "main_weapon"


# ===========================================================================
# 3. Admin API + revalidation
# ===========================================================================

class TestAdminApi:

    def _put(self, client, body, permissions=("items:update",)):
        with patch("auth_http.requests.get", return_value=_auth(list(permissions))):
            return client.put("/inventory/admin/equipment-rules", json=body, headers=ADMIN_HEADERS)

    def test_save_and_list(self, client, world):
        body = {"class_id": 1, "subclass_key": "warrior_guardian", "armor_classes": ["heavy_armor"],
                "main_hand": ["category:one_handed", "kind:katana"], "off_hand": ["category:shield"]}
        with patch("main._revalidate_characters", new_callable=AsyncMock):
            resp = self._put(client, body)
        assert resp.status_code == 200, resp.text
        assert resp.json()["scope_key"] == "warrior_guardian"

        # Saving again replaces, not duplicates
        body["armor_classes"] = ["medium_armor"]
        with patch("main._revalidate_characters", new_callable=AsyncMock):
            assert self._put(client, body).status_code == 200

        with patch("auth_http.requests.get", return_value=_auth(["items:read"])):
            rows = client.get("/inventory/admin/equipment-rules", headers=ADMIN_HEADERS).json()
        assert len(rows) == 1
        assert rows[0]["armor_classes"] == ["medium_armor"]

    def test_two_handed_in_off_hand_rejected(self, client, world):
        resp = self._put(client, {"class_id": 1, "off_hand": ["category:polearm"]})
        assert resp.status_code == 400

    def test_unknown_class_rejected(self, client, world):
        assert self._put(client, {"class_id": 42}).status_code == 400

    def test_bad_subclass_key_rejected(self, client, world):
        resp = self._put(client, {"class_id": 1, "subclass_key": "x'; DROP TABLE items;--"})
        assert resp.status_code == 422

    def test_requires_permission(self, client, world):
        resp = self._put(client, {"class_id": 1}, permissions=())
        assert resp.status_code == 403

    def test_requires_token(self, client, world):
        assert client.put("/inventory/admin/equipment-rules", json={"class_id": 1}).status_code == 401

    def test_delete_removes_restrictions(self, client, world):
        _rule(world, armor=["cloth"])
        with patch("auth_http.requests.get", return_value=_auth(["items:update"])):
            resp = client.delete("/inventory/admin/equipment-rules?class_id=1", headers=ADMIN_HEADERS)
            missing = client.delete("/inventory/admin/equipment-rules?class_id=1", headers=ADMIN_HEADERS)
        assert resp.status_code == 204
        assert missing.status_code == 404
        assert equipment_rules.rules_for_character(world, CHAR).restricted is False

    def test_save_unequips_now_forbidden_items(self, player, world):
        plate = _item(world, "Латы", item_type="body", armor="heavy_armor")
        _give(world, plate)
        assert _equip(player, plate).status_code == 200

        _as_admin()
        resp = player.put("/inventory/admin/equipment-rules", json={"class_id": 1, "armor_classes": ["cloth"]})
        assert resp.status_code == 200
        assert _slot(world, "body").item_id is None
        assert world.query(models.CharacterInventory).filter_by(character_id=CHAR, item_id=plate.id).first()


class TestRevalidation:

    def test_internal_endpoint_after_subclass_choice(self, player, world):
        sword = _item(world, "Меч", kind="sword")
        _give(world, sword)
        assert _equip(player, sword).status_code == 200

        _rule(world, subclass_key="warrior_guardian", armor=[], main=["kind:mace"])
        _choose_subclass(world)
        resp = player.post(f"/inventory/internal/characters/{CHAR}/revalidate-equipment", headers=_INTERNAL_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["removed_slots"] == ["main_weapon"]
        assert _slot(world, "main_weapon").item_id is None

    def test_nothing_to_remove(self, player, world):
        resp = player.post(f"/inventory/internal/characters/{CHAR}/revalidate-equipment", headers=_INTERNAL_HEADERS)
        assert resp.json()["removed_slots"] == []

    def test_skipped_in_battle(self, player, world):
        _rule(world, armor=["cloth"])
        plate = _item(world, "Латы", item_type="body", armor="heavy_armor")
        world.query(models.EquipmentSlot).filter_by(character_id=CHAR, slot_type="body").update({"item_id": plate.id})
        world.execute(text("INSERT INTO battles (id, status) VALUES (1, 'in_progress')"))
        world.execute(text(f"INSERT INTO battle_participants (id, battle_id, character_id) VALUES (1, 1, {CHAR})"))
        world.commit()
        resp = player.post(f"/inventory/internal/characters/{CHAR}/revalidate-equipment", headers=_INTERNAL_HEADERS)
        assert resp.json()["removed_slots"] == []
        assert _slot(world, "body").item_id == plate.id

    def test_item_kind_edit_unequips_wearers(self, player, world):
        _rule(world, armor=[], main=["kind:sword"], off=[])
        sword = _item(world, "Меч", kind="sword")
        _give(world, sword)
        assert _equip(player, sword).status_code == 200

        body = {"name": "Меч", "item_type": "weapon", "item_rarity": "common", "item_level": 1,
                "max_stack_size": 1, "is_unique": False, "weapon_subclass": "bow"}
        _as_admin()
        resp = player.put(f"/inventory/items/{sword.id}", json=body)
        assert resp.status_code == 200, resp.text
        assert _slot(world, "main_weapon").item_id is None


class TestCharacterRulesEndpoint:

    def test_unrestricted_response(self, client, world):
        data = client.get(f"/inventory/{CHAR}/equipment-rules").json()
        assert data["restricted"] is False
        assert data["main_hand_kinds"] is None
        assert "halberd" in data["two_handed_kinds"]

    def test_restricted_response(self, client, world):
        _rule(world, armor=["cloth"], main=["category:ranged"], off=["kind:dagger"])
        data = client.get(f"/inventory/{CHAR}/equipment-rules").json()
        assert data["restricted"] is True
        assert data["armor_classes"] == ["cloth"]
        assert data["main_hand_kinds"] == ["bow", "musket", "pistol"]
        assert data["off_hand_kinds"] == ["dagger"]
