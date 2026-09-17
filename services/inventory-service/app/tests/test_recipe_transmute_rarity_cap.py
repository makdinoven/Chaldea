"""
FEAT-164 — rarity cap for crafting and transmutation.

Rules (user decision 2026-09-17):
  * recipes have no quality of their own: recipes.rarity is derived from the
    result item, the payload `rarity` is ignored (create and update);
  * the auto-created recipe item (item_type='recipe') is stored as 'common';
  * equipment results MAY be mythical / divine / demonic;
  * a non-equipment result above legendary (legacy rows only — the item
    validator forbids creating them) is rejected on create and on update,
    including when the update does not touch result_item_id (stored value);
  * transmutation chain ends at legendary: legendary (and legacy mythical)
    resources are not listed and cannot be transmuted; nothing yields mythical.
"""

import pytest
from sqlalchemy import text

import main
import models
from auth_http import UserRead, get_current_user_via_http

CAP_ERROR = "Крафт не может создавать предметы мифической, божественной или демонической редкости"

EQUIPMENT_TYPES = ["head", "body", "cloak", "belt", "ring", "necklace", "bracelet", "weapon"]
EQUIPMENT_ONLY = ["mythical", "divine", "demonic"]

_admin = UserRead(
    id=99, username="admin", role="admin",
    permissions=["professions:read", "professions:create", "professions:update",
                 "professions:delete", "professions:manage"],
)
_player = UserRead(id=1, username="player1", role="user", permissions=[])


def _item(db, item_id, name, item_type="resource", rarity="common", **kw):
    extra = {"weapon_subclass": "sword"} if item_type == "weapon" else {}
    extra.update(kw)
    item = models.Items(
        id=item_id, name=name, item_level=1, item_type=item_type,
        item_rarity=rarity, max_stack_size=99, is_unique=False, **extra,
    )
    db.add(item)
    db.flush()
    return item


def _profession(db, prof_id=1, slug="blacksmith", name="Кузнец"):
    prof = models.Profession(id=prof_id, name=name, slug=slug, description="t",
                             sort_order=1, is_active=True)
    db.add(prof)
    db.flush()
    return prof


def _characters_table(db):
    db.execute(text("DROP TABLE IF EXISTS characters"))
    db.execute(text("CREATE TABLE characters (id INTEGER PRIMARY KEY, name TEXT, user_id INTEGER)"))
    db.execute(text("INSERT INTO characters (id, name, user_id) VALUES (1, 'Hero', 1), (2, 'Other', 5)"))
    db.commit()


@pytest.fixture()
def admin_env(client, db_session):
    _characters_table(db_session)
    main.app.dependency_overrides[get_current_user_via_http] = lambda: _admin
    prof = _profession(db_session)
    _item(db_session, 10, "Руда", "resource")
    db_session.commit()
    yield {"client": client, "db": db_session, "prof": prof}
    main.app.dependency_overrides.pop(get_current_user_via_http, None)


def _create(c, result_item_id, name="Рецепт", **kw):
    body = {
        "name": name, "profession_id": 1, "required_rank": 1,
        "result_item_id": result_item_id, "result_quantity": 1,
        "ingredients": [{"item_id": 10, "quantity": 2}],
    }
    body.update(kw)
    return c.post("/inventory/admin/recipes", json=body)


def _recipe_item_rarity(db, recipe_id):
    db.expire_all()
    item = db.query(models.Items).filter(models.Items.blueprint_recipe_id == recipe_id,
                                         models.Items.item_type == "recipe").first()
    return item.item_rarity if item else None


# ===========================================================================
# Admin recipe create / update
# ===========================================================================

class TestRecipeRarityCap:

    @pytest.mark.parametrize("item_type", EQUIPMENT_TYPES)
    @pytest.mark.parametrize("rarity", EQUIPMENT_ONLY)
    def test_equipment_result_may_be_equipment_only_rarity(self, admin_env, item_type, rarity):
        db, c = admin_env["db"], admin_env["client"]
        _item(db, 50, "Клинок", item_type, rarity)
        db.commit()
        resp = _create(c, 50)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["rarity"] == rarity  # derived from result
        assert data["recipe_item_id"] is not None
        assert _recipe_item_rarity(db, data["id"]) == "common"

    @pytest.mark.parametrize("rarity", EQUIPMENT_ONLY)
    @pytest.mark.parametrize("item_type", ["resource", "consumable", "gem", "misc"])
    def test_legacy_non_equipment_result_rejected(self, admin_env, rarity, item_type):
        db, c = admin_env["db"], admin_env["client"]
        _item(db, 51, "Старый ресурс", item_type, rarity)  # legacy row, bypasses validator
        db.commit()
        resp = _create(c, 51)
        assert resp.status_code == 400
        assert resp.json()["detail"] == CAP_ERROR
        assert db.query(models.Recipe).count() == 0
        assert db.query(models.Items).filter(models.Items.item_type == "recipe").count() == 0

    @pytest.mark.parametrize("payload_rarity", ["mythical", "divine", "demonic", "legendary", "garbage"])
    def test_payload_rarity_ignored_on_create(self, admin_env, payload_rarity):
        db, c = admin_env["db"], admin_env["client"]
        _item(db, 52, "Похлёбка", "consumable", "epic")
        db.commit()
        resp = _create(c, 52, rarity=payload_rarity)
        assert resp.status_code == 201, resp.text
        assert resp.json()["rarity"] == "epic"
        assert _recipe_item_rarity(db, resp.json()["id"]) == "common"

    def test_rarity_optional_on_create(self, admin_env):
        db, c = admin_env["db"], admin_env["client"]
        _item(db, 53, "Кольцо", "ring", "legendary")
        db.commit()
        resp = _create(c, 53)
        assert resp.status_code == 201
        assert resp.json()["rarity"] == "legendary"

    def test_auto_learn_recipe_has_no_recipe_item(self, admin_env):
        db, c = admin_env["db"], admin_env["client"]
        _item(db, 54, "Шлем", "head", "divine")
        db.commit()
        resp = _create(c, 54, auto_learn_rank=1)
        assert resp.status_code == 201
        assert resp.json()["recipe_item_id"] is None
        assert resp.json()["rarity"] == "divine"

    def test_update_payload_rarity_ignored(self, admin_env):
        db, c = admin_env["db"], admin_env["client"]
        _item(db, 55, "Хлеб", "consumable", "rare")
        db.commit()
        rid = _create(c, 55).json()["id"]
        resp = c.put(f"/inventory/admin/recipes/{rid}", json={"rarity": "mythical", "description": "x"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["rarity"] == "rare"
        assert resp.json()["description"] == "x"
        assert _recipe_item_rarity(db, rid) == "common"

    def test_update_result_change_rederives_rarity(self, admin_env):
        db, c = admin_env["db"], admin_env["client"]
        _item(db, 56, "Хлеб", "consumable", "common")
        _item(db, 57, "Меч богов", "weapon", "demonic")
        db.commit()
        rid = _create(c, 56).json()["id"]
        resp = c.put(f"/inventory/admin/recipes/{rid}", json={"result_item_id": 57})
        assert resp.status_code == 200, resp.text
        assert resp.json()["rarity"] == "demonic"
        assert _recipe_item_rarity(db, rid) == "common"

    def test_update_to_legacy_non_equipment_result_rejected(self, admin_env):
        db, c = admin_env["db"], admin_env["client"]
        _item(db, 58, "Хлеб", "consumable", "common")
        _item(db, 59, "Трансмутированный ресурс (мифический)", "resource", "mythical")
        db.commit()
        rid = _create(c, 58).json()["id"]
        resp = c.put(f"/inventory/admin/recipes/{rid}", json={"result_item_id": 59})
        assert resp.status_code == 400
        assert resp.json()["detail"] == CAP_ERROR
        db.expire_all()
        recipe = db.query(models.Recipe).get(rid)
        assert recipe.result_item_id == 58
        assert recipe.rarity == "common"

    def test_update_validates_stored_result(self, admin_env):
        """Legacy recipe already pointing at a mythical resource: any edit is refused."""
        db, c = admin_env["db"], admin_env["client"]
        _item(db, 60, "Мифическая пыль", "resource", "mythical")
        recipe = models.Recipe(name="Легаси", profession_id=1, required_rank=1,
                               result_item_id=60, result_quantity=1, rarity="mythical",
                               is_active=True)
        db.add(recipe)
        db.commit()
        resp = c.put(f"/inventory/admin/recipes/{recipe.id}", json={"description": "правка"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == CAP_ERROR
        db.expire_all()
        assert db.query(models.Recipe).get(recipe.id).description is None

    def test_update_legacy_recipe_fixed_by_switching_result(self, admin_env):
        db, c = admin_env["db"], admin_env["client"]
        _item(db, 61, "Мифическая пыль", "resource", "mythical")
        _item(db, 62, "Легендарная пыль", "resource", "legendary")
        recipe = models.Recipe(name="Легаси2", profession_id=1, required_rank=1,
                               result_item_id=61, result_quantity=1, rarity="mythical",
                               is_active=True)
        db.add(recipe)
        db.commit()
        resp = c.put(f"/inventory/admin/recipes/{recipe.id}", json={"result_item_id": 62})
        assert resp.status_code == 200, resp.text
        assert resp.json()["rarity"] == "legendary"

    def test_non_admin_cannot_create(self, admin_env):
        db, c = admin_env["db"], admin_env["client"]
        _item(db, 63, "Кольцо", "ring", "mythical")
        db.commit()
        main.app.dependency_overrides[get_current_user_via_http] = lambda: _player
        resp = _create(c, 63)
        assert resp.status_code == 403
        assert db.query(models.Recipe).count() == 0

    def test_no_token_401(self, client, db_session):
        resp = client.post("/inventory/admin/recipes", json={"name": "x", "profession_id": 1, "result_item_id": 1})
        assert resp.status_code == 401


# ===========================================================================
# Transmutation
# ===========================================================================

class TestTransmutationCap:

    def test_chain_constants_end_at_legendary(self):
        assert main.RARITY_CHAIN == {"common": "rare", "rare": "epic", "epic": "legendary"}
        assert not set(main.RARITY_CHAIN.values()) & set(EQUIPMENT_ONLY)
        assert not set(main.RARITY_CHAIN) & ({"legendary"} | set(EQUIPMENT_ONLY))
        assert set(main.TRANSMUTE_RESULT_NAMES) == {"rare", "epic", "legendary"}

    @pytest.fixture()
    def alch_env(self, client, db_session):
        db = db_session
        _characters_table(db)
        prof = _profession(db, prof_id=3, slug="alchemist", name="Алхимик")
        db.add(models.ProfessionRank(profession_id=prof.id, rank_number=1, name="Ученик", required_experience=0))
        db.add(models.CharacterProfession(character_id=1, profession_id=prof.id, current_rank=1, experience=0))
        rows = {}
        for iid, name, rarity in [
            (100, "Обычная трава", "common"),
            (101, "Эпическая трава", "epic"),
            (102, "Легендарная трава", "legendary"),
            (103, "Трансмутированный ресурс (мифический)", "mythical"),
        ]:
            _item(db, iid, name, "resource", rarity)
            inv = models.CharacterInventory(character_id=1, item_id=iid, quantity=10)
            db.add(inv)
            db.flush()
            rows[rarity] = inv.id
        for iid, rarity in [(200, "rare"), (201, "epic"), (202, "legendary")]:
            _item(db, iid, main.TRANSMUTE_RESULT_NAMES[rarity], "resource", rarity)
        db.commit()
        main.app.dependency_overrides[get_current_user_via_http] = lambda: _player
        yield {"client": client, "db": db, "rows": rows}
        main.app.dependency_overrides.pop(get_current_user_via_http, None)

    def test_info_lists_only_below_legendary(self, alch_env):
        resp = alch_env["client"].get("/inventory/crafting/1/transmute-info")
        assert resp.status_code == 200
        items = {i["item_rarity"]: i for i in resp.json()["items"]}
        assert set(items) == {"common", "epic"}
        assert items["epic"]["next_rarity"] == "legendary"
        for i in resp.json()["items"]:
            assert i["next_rarity"] not in EQUIPMENT_ONLY

    @pytest.mark.parametrize("rarity", ["legendary", "mythical"])
    def test_cannot_transmute_top_rarity(self, alch_env, rarity):
        db = alch_env["db"]
        resp = alch_env["client"].post(
            "/inventory/crafting/1/transmute", json={"inventory_item_id": alch_env["rows"][rarity]},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Этот ресурс уже максимальной редкости для трансмутации"
        db.expire_all()
        assert db.query(models.CharacterInventory).get(alch_env["rows"][rarity]).quantity == 10

    def test_epic_to_legendary_still_works(self, alch_env):
        db = alch_env["db"]
        resp = alch_env["client"].post(
            "/inventory/crafting/1/transmute", json={"inventory_item_id": alch_env["rows"]["epic"]},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["result_item_rarity"] == "legendary"
        db.expire_all()
        assert db.query(models.CharacterInventory).get(alch_env["rows"]["epic"]).quantity == 5
        got = db.query(models.CharacterInventory).filter_by(character_id=1, item_id=202).one()
        assert got.quantity == 1

    def test_foreign_character_forbidden(self, alch_env):
        resp = alch_env["client"].post("/inventory/crafting/2/transmute", json={"inventory_item_id": 1})
        assert resp.status_code == 403
