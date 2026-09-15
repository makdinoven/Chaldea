"""
Item create/update rules tied to the item type (admin item form reorganisation).

- res_* / vul_* / crit fields are Float columns and must survive a round trip
  (they used to be declared int and 0.5 was silently saved as 0)
- armor_subclass only on head/body, weapon_subclass only on weapons
- 'shield' is no longer an item type; shields are weapon kinds (buckler/targe/tower_shield)
- every weapon kind maps to exactly one category
- blueprint_recipe_id is accepted for blueprints and must point at a real recipe
"""

from unittest.mock import patch, MagicMock

import models


HEADERS = {"Authorization": "Bearer admin-token"}
ADMIN = {"id": 1, "username": "admin", "role": "admin",
         "permissions": ["items:create", "items:update"]}


def _auth_ok():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = ADMIN
    return resp


def _body(**overrides):
    body = {
        "name": "Предмет",
        "item_level": 1,
        "item_type": "body",
        "item_rarity": "common",
        "max_stack_size": 1,
        "is_unique": False,
    }
    body.update(overrides)
    return body


def _post(client, body):
    with patch("auth_http.requests.get", return_value=_auth_ok()):
        return client.post("/inventory/items", json=body, headers=HEADERS)


def _put(client, item_id, body):
    with patch("auth_http.requests.get", return_value=_auth_ok()):
        return client.put(f"/inventory/items/{item_id}", json=body, headers=HEADERS)


# ===========================================================================
# 1. Fractional modifiers
# ===========================================================================

class TestFractionalModifiers:

    def test_create_keeps_fractions(self, client, db_session):
        resp = _post(client, _body(
            res_fire_modifier=0.5, vul_ice_modifier=1.25,
            critical_hit_chance_modifier=2.5, critical_damage_modifier=0.1,
        ))
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["res_fire_modifier"] == 0.5
        assert data["vul_ice_modifier"] == 1.25
        assert data["critical_hit_chance_modifier"] == 2.5
        assert data["critical_damage_modifier"] == 0.1

        stored = db_session.query(models.Items).get(data["id"])
        assert stored.res_fire_modifier == 0.5

    def test_update_keeps_fractions(self, client, db_session):
        item_id = _post(client, _body()).json()["id"]
        resp = _put(client, item_id, _body(res_magic_modifier=0.3))
        assert resp.status_code == 200, resp.text
        assert resp.json()["res_magic_modifier"] == 0.3


# ===========================================================================
# 2. Subclasses and shields
# ===========================================================================

class TestSubclassRules:

    def test_armor_subclass_on_body_ok(self, client, db_session):
        resp = _post(client, _body(item_type="head", armor_subclass="heavy_armor"))
        assert resp.status_code == 201, resp.text
        assert resp.json()["armor_subclass"] == "heavy_armor"

    def test_armor_subclass_on_cloak_rejected(self, client, db_session):
        resp = _post(client, _body(item_type="cloak", armor_subclass="cloth"))
        assert resp.status_code == 422

    def test_weapon_subclass_on_armor_rejected(self, client, db_session):
        resp = _post(client, _body(item_type="body", weapon_subclass="dagger"))
        assert resp.status_code == 422

    def test_unknown_subclass_rejected(self, client, db_session):
        resp = _post(client, _body(item_type="weapon", weapon_subclass="laser_sword"))
        assert resp.status_code == 422

    def test_shield_is_offhand_weapon_with_shield_kind(self, client, db_session):
        resp = _post(client, _body(
            name="Ростовой щит", item_type="weapon", weapon_subclass="tower_shield",
        ))
        assert resp.status_code == 201, resp.text
        assert resp.json()["weapon_subclass"] == "tower_shield"

    def test_old_class_bound_subclass_rejected(self, client, db_session):
        resp = _post(client, _body(item_type="weapon", weapon_subclass="two_handed_weapon"))
        assert resp.status_code == 422

    def test_every_weapon_kind_has_one_category(self):
        import schemas

        kinds = {k.value for k in schemas.WeaponSubclass}
        assert kinds == set(schemas.WEAPON_KIND_CATEGORY)
        assert schemas.WEAPON_KIND_CATEGORY["battle_axe"] == "two_handed"
        assert schemas.WEAPON_KIND_CATEGORY["war_hammer"] == "one_and_half"
        assert {k for k, c in schemas.WEAPON_KIND_CATEGORY.items() if c == "shield"} == {
            "buckler", "targe", "tower_shield",
        }

    def test_shield_item_type_rejected(self, client, db_session):
        resp = _post(client, _body(item_type="shield"))
        assert resp.status_code == 422


# ===========================================================================
# 3. Blueprint -> recipe link
# ===========================================================================

def _seed_recipe(db_session):
    db_session.add(models.Profession(
        id=1, name="Кузнец", slug="blacksmith", description="-", sort_order=1, is_active=True,
    ))
    result = models.Items(
        id=500, name="Меч", item_type="weapon", item_rarity="common",
        item_level=1, max_stack_size=1, is_unique=False,
    )
    db_session.add(result)
    db_session.flush()
    recipe = models.Recipe(
        name="Ковка меча", profession_id=1, required_rank=1, result_item_id=500,
        result_quantity=1, rarity="common", is_active=True, is_blueprint_recipe=True,
    )
    db_session.add(recipe)
    db_session.commit()
    return recipe


class TestBlueprintRecipeLink:

    def test_blueprint_links_to_existing_recipe(self, client, db_session):
        recipe = _seed_recipe(db_session)
        resp = _post(client, _body(
            name="Чертёж меча", item_type="blueprint", blueprint_recipe_id=recipe.id,
        ))
        assert resp.status_code == 201, resp.text
        assert resp.json()["blueprint_recipe_id"] == recipe.id

    def test_missing_recipe_returns_400(self, client, db_session):
        resp = _post(client, _body(
            name="Чертёж пустоты", item_type="blueprint", blueprint_recipe_id=9999,
        ))
        assert resp.status_code == 400
        assert "Рецепт" in resp.json()["detail"]

    def test_recipe_link_on_non_blueprint_rejected(self, client, db_session):
        recipe = _seed_recipe(db_session)
        resp = _post(client, _body(item_type="misc", blueprint_recipe_id=recipe.id))
        assert resp.status_code == 422

    def test_update_can_link_blueprint(self, client, db_session):
        recipe = _seed_recipe(db_session)
        item_id = _post(client, _body(name="Чертёж", item_type="blueprint")).json()["id"]
        resp = _put(client, item_id, _body(
            name="Чертёж", item_type="blueprint", blueprint_recipe_id=recipe.id,
        ))
        assert resp.status_code == 200, resp.text
        assert resp.json()["blueprint_recipe_id"] == recipe.id

    def test_sql_injection_in_recipe_id_rejected(self, client, db_session):
        resp = _post(client, _body(
            item_type="blueprint", blueprint_recipe_id="1 OR 1=1",
        ))
        assert resp.status_code == 422
