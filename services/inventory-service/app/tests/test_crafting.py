"""
Task 8 — QA tests for FEAT-081: Crafting system endpoints.

Tests covering recipe listing, crafting (learned + blueprint), error cases,
learn-recipe, and admin CRUD for recipes.
"""

import pytest
from unittest.mock import patch
from sqlalchemy import text

from auth_http import get_current_user_via_http, UserRead, require_permission
import models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_characters_table(db):
    """Create minimal characters + battle tables for ownership/battle checks."""
    db.execute(text("DROP TABLE IF EXISTS battle_participants"))
    db.execute(text("DROP TABLE IF EXISTS battles"))
    db.execute(text("DROP TABLE IF EXISTS characters"))
    db.execute(text(
        """CREATE TABLE characters (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL DEFAULT 'TestChar',
            user_id INTEGER NOT NULL,
            current_location_id INTEGER DEFAULT 1,
            currency_balance INTEGER DEFAULT 0
        )"""
    ))
    db.execute(text(
        """CREATE TABLE battles (
            id INTEGER PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending'
        )"""
    ))
    db.execute(text(
        """CREATE TABLE battle_participants (
            id INTEGER PRIMARY KEY,
            battle_id INTEGER NOT NULL,
            character_id INTEGER NOT NULL
        )"""
    ))
    db.commit()


def _insert_character(db, char_id, user_id, name="TestChar"):
    db.execute(text(
        "INSERT OR IGNORE INTO characters (id, name, user_id) VALUES (:cid, :name, :uid)"
    ), {"cid": char_id, "name": name, "uid": user_id})
    db.commit()


def _create_profession(db, prof_id=1, name="Кузнец", slug="blacksmith"):
    prof = models.Profession(
        id=prof_id, name=name, slug=slug, description="Test",
        sort_order=1, is_active=True,
    )
    db.add(prof)
    db.flush()
    return prof


def _create_rank(db, profession_id=1, rank_number=1, name="Ученик"):
    rank = models.ProfessionRank(
        profession_id=profession_id, rank_number=rank_number,
        name=name, required_experience=0,
    )
    db.add(rank)
    db.flush()
    return rank


def _create_item(db, item_id, name, item_type="resource", max_stack=99):
    item = models.Items(
        id=item_id, name=name, item_level=1, item_type=item_type,
        item_rarity="common", max_stack_size=max_stack, is_unique=False,
    )
    db.add(item)
    db.flush()
    return item


def _add_inventory(db, char_id, item_id, quantity):
    inv = models.CharacterInventory(character_id=char_id, item_id=item_id, quantity=quantity)
    db.add(inv)
    db.flush()
    return inv


def _create_recipe(db, name="Железный меч", profession_id=1, required_rank=1,
                   result_item_id=50, auto_learn_rank=None, is_blueprint_recipe=False):
    recipe = models.Recipe(
        name=name, profession_id=profession_id, required_rank=required_rank,
        result_item_id=result_item_id, result_quantity=1, rarity="common",
        auto_learn_rank=auto_learn_rank, is_active=True,
        is_blueprint_recipe=is_blueprint_recipe,
    )
    db.add(recipe)
    db.flush()
    return recipe


def _add_ingredient(db, recipe_id, item_id, quantity):
    ing = models.RecipeIngredient(recipe_id=recipe_id, item_id=item_id, quantity=quantity)
    db.add(ing)
    db.flush()
    return ing


def _learn_recipe(db, char_id, recipe_id):
    cr = models.CharacterRecipe(character_id=char_id, recipe_id=recipe_id)
    db.add(cr)
    db.flush()
    return cr


def _assign_profession(db, char_id, profession_id, rank=1, experience=0):
    cp = models.CharacterProfession(
        character_id=char_id, profession_id=profession_id,
        current_rank=rank, experience=experience,
    )
    db.add(cp)
    db.flush()
    return cp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_user1 = UserRead(id=1, username="player1", role="user", permissions=[])
_admin_user = UserRead(
    id=99, username="admin", role="admin",
    permissions=[
        "professions:read", "professions:create",
        "professions:update", "professions:delete", "professions:manage",
    ],
)


@pytest.fixture()
def craft_env(client, db_session):
    """Full crafting test environment with profession, recipe, and materials."""
    _create_characters_table(db_session)
    _insert_character(db_session, 1, user_id=1, name="Crafter")

    # Profession + rank
    prof = _create_profession(db_session, 1, "Кузнец", "blacksmith")
    _create_rank(db_session, profession_id=prof.id, rank_number=1, name="Ученик")
    _create_rank(db_session, profession_id=prof.id, rank_number=2, name="Подмастерье")

    # Result item
    result_item = _create_item(db_session, 50, "Железный меч", "main_weapon", max_stack=1)

    # Material items
    ore = _create_item(db_session, 100, "Железная руда", "resource")
    coal = _create_item(db_session, 101, "Уголь", "resource")

    # Recipe with ingredients
    recipe = _create_recipe(db_session, name="Ковка железного меча",
                            profession_id=prof.id, result_item_id=result_item.id,
                            auto_learn_rank=1)
    _add_ingredient(db_session, recipe.id, ore.id, 3)
    _add_ingredient(db_session, recipe.id, coal.id, 1)

    # Assign profession to character
    _assign_profession(db_session, 1, prof.id, rank=1)

    # Learn the recipe
    _learn_recipe(db_session, 1, recipe.id)

    # Add materials to inventory
    _add_inventory(db_session, 1, ore.id, 10)
    _add_inventory(db_session, 1, coal.id, 5)

    db_session.commit()

    from main import app
    app.dependency_overrides[get_current_user_via_http] = lambda: _user1

    yield {
        "client": client,
        "db": db_session,
        "app": app,
        "profession": prof,
        "recipe": recipe,
        "result_item": result_item,
        "ore": ore,
        "coal": coal,
    }

    app.dependency_overrides.pop(get_current_user_via_http, None)


@pytest.fixture()
def admin_recipe_env(client, db_session):
    """Environment with admin auth for recipe admin endpoints."""
    _create_characters_table(db_session)
    _insert_character(db_session, 1, user_id=1, name="Hero")

    from main import app
    app.dependency_overrides[get_current_user_via_http] = lambda: _admin_user
    for perm in ["professions:read", "professions:create", "professions:update",
                 "professions:delete", "professions:manage"]:
        app.dependency_overrides[require_permission(perm)] = lambda: _admin_user

    yield {"client": client, "db": db_session, "app": app}

    app.dependency_overrides.clear()


# ===========================================================================
# 1. List recipes — GET /inventory/crafting/{char_id}/recipes
# ===========================================================================

class TestListRecipes:

    def test_list_learned_recipes(self, craft_env):
        c = craft_env["client"]
        resp = c.get("/inventory/crafting/1/recipes")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        recipe = data[0]
        assert "name" in recipe
        assert "can_craft" in recipe
        assert "ingredients" in recipe
        assert "source" in recipe

    def test_list_recipes_shows_can_craft_true(self, craft_env):
        """Character has enough materials so can_craft should be true."""
        c = craft_env["client"]
        resp = c.get("/inventory/crafting/1/recipes")
        data = resp.json()
        learned_recipes = [r for r in data if r["source"] == "learned"]
        assert len(learned_recipes) >= 1
        assert learned_recipes[0]["can_craft"] is True

    def test_list_recipes_includes_blueprint_recipes(self, craft_env):
        """Blueprint items in inventory should appear as blueprint-sourced recipes."""
        db = craft_env["db"]
        c = craft_env["client"]

        # Create a blueprint recipe
        result_item2 = _create_item(db, 51, "Стальной меч", "main_weapon", max_stack=1)
        bp_recipe = _create_recipe(db, name="Ковка стального меча",
                                   profession_id=1, result_item_id=result_item2.id,
                                   is_blueprint_recipe=True)

        # Create blueprint item pointing to the recipe
        bp_item = _create_item(db, 200, "Чертёж стального меча", "blueprint", max_stack=1)
        bp_item.blueprint_recipe_id = bp_recipe.id

        # Add blueprint to inventory
        _add_inventory(db, 1, bp_item.id, 1)
        db.commit()

        resp = c.get("/inventory/crafting/1/recipes")
        data = resp.json()
        bp_sources = [r for r in data if r["source"] == "blueprint"]
        assert len(bp_sources) >= 1


# ===========================================================================
# 2. Craft success — POST /inventory/crafting/{char_id}/craft
# ===========================================================================

class TestCraftSuccess:

    def test_craft_consumes_materials_creates_item(self, craft_env):
        db = craft_env["db"]
        c = craft_env["client"]
        recipe = craft_env["recipe"]

        resp = c.post("/inventory/crafting/1/craft", json={
            "recipe_id": recipe.id,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["crafted_item"]["item_id"] == 50
        assert data["crafted_item"]["name"] == "Железный меч"
        assert data["crafted_item"]["quantity"] == 1
        assert data["blueprint_consumed"] is False
        assert len(data["consumed_materials"]) == 2

        # Verify materials were consumed
        db.expire_all()
        ore_inv = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == 1,
            models.CharacterInventory.item_id == 100,
        ).first()
        assert ore_inv.quantity == 7  # 10 - 3

        coal_inv = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == 1,
            models.CharacterInventory.item_id == 101,
        ).first()
        assert coal_inv.quantity == 4  # 5 - 1

        # Verify result item was created
        result_inv = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == 1,
            models.CharacterInventory.item_id == 50,
        ).first()
        assert result_inv is not None
        assert result_inv.quantity >= 1


# ===========================================================================
# 3. Craft with blueprint — consumes blueprint on use
# ===========================================================================

class TestCraftWithBlueprint:

    def test_blueprint_consumed_on_craft(self, craft_env):
        db = craft_env["db"]
        c = craft_env["client"]

        # Create blueprint recipe and items
        result_item2 = _create_item(db, 52, "Стальной щит", "shield", max_stack=1)
        bp_recipe = _create_recipe(db, name="Ковка стального щита",
                                   profession_id=1, result_item_id=result_item2.id,
                                   is_blueprint_recipe=True, required_rank=1)
        _add_ingredient(db, bp_recipe.id, 100, 2)  # 2 ore

        bp_item = _create_item(db, 201, "Чертёж щита", "blueprint", max_stack=1)
        bp_item.blueprint_recipe_id = bp_recipe.id
        _add_inventory(db, 1, bp_item.id, 1)
        db.commit()

        resp = c.post("/inventory/crafting/1/craft", json={
            "recipe_id": bp_recipe.id,
            "blueprint_item_id": bp_item.id,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["blueprint_consumed"] is True

        # Verify blueprint was consumed
        db.expire_all()
        bp_inv = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == 1,
            models.CharacterInventory.item_id == bp_item.id,
        ).first()
        # Blueprint should be consumed (deleted since quantity was 1)
        assert bp_inv is None


# ===========================================================================
# 4. Craft wrong profession — returns 400
# ===========================================================================

class TestCraftWrongProfession:

    def test_wrong_profession_returns_400(self, craft_env):
        db = craft_env["db"]
        c = craft_env["client"]

        # Create a recipe for a different profession
        prof2 = _create_profession(db, 2, "Алхимик", "alchemist")
        _create_rank(db, profession_id=prof2.id, rank_number=1, name="Новичок")
        result_item2 = _create_item(db, 53, "Зелье", "consumable")
        recipe2 = _create_recipe(db, name="Зелье лечения",
                                 profession_id=prof2.id, result_item_id=result_item2.id)
        _learn_recipe(db, 1, recipe2.id)
        db.commit()

        resp = c.post("/inventory/crafting/1/craft", json={
            "recipe_id": recipe2.id,
        })
        assert resp.status_code == 400
        assert "профессия" in resp.json()["detail"].lower() or "Требуется" in resp.json()["detail"]


# ===========================================================================
# 5. Craft insufficient rank — returns 400
# ===========================================================================

class TestCraftInsufficientRank:

    def test_insufficient_rank_returns_400(self, craft_env):
        db = craft_env["db"]
        c = craft_env["client"]

        # Create a recipe requiring rank 2
        result_item2 = _create_item(db, 54, "Стальной меч+", "main_weapon")
        recipe2 = _create_recipe(db, name="Улучшенная ковка",
                                 profession_id=1, result_item_id=result_item2.id,
                                 required_rank=2)
        _learn_recipe(db, 1, recipe2.id)
        db.commit()

        # Character is rank 1, recipe requires rank 2
        resp = c.post("/inventory/crafting/1/craft", json={
            "recipe_id": recipe2.id,
        })
        assert resp.status_code == 400
        assert "ранг" in resp.json()["detail"].lower()


# ===========================================================================
# 6. Craft missing materials — returns 400
# ===========================================================================

class TestCraftMissingMaterials:

    def test_missing_materials_returns_400(self, craft_env):
        db = craft_env["db"]
        c = craft_env["client"]

        # Remove all ore from inventory
        db.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == 1,
            models.CharacterInventory.item_id == 100,
        ).delete()
        db.commit()

        recipe = craft_env["recipe"]
        resp = c.post("/inventory/crafting/1/craft", json={
            "recipe_id": recipe.id,
        })
        assert resp.status_code == 400
        assert "материал" in resp.json()["detail"].lower() or "Недостаточно" in resp.json()["detail"]


# ===========================================================================
# 7. Craft unknown recipe — returns 404
# ===========================================================================

class TestCraftUnknownRecipe:

    def test_unknown_recipe_returns_404(self, craft_env):
        c = craft_env["client"]
        resp = c.post("/inventory/crafting/1/craft", json={
            "recipe_id": 99999,
        })
        assert resp.status_code == 404

    def test_unlearned_recipe_returns_400(self, craft_env):
        """Recipe exists but character hasn't learned it."""
        db = craft_env["db"]
        c = craft_env["client"]

        result_item2 = _create_item(db, 55, "Секретный клинок", "main_weapon")
        secret_recipe = _create_recipe(db, name="Секретная ковка",
                                       profession_id=1, result_item_id=result_item2.id)
        # NOT learning the recipe
        db.commit()

        resp = c.post("/inventory/crafting/1/craft", json={
            "recipe_id": secret_recipe.id,
        })
        assert resp.status_code == 400
        assert "не изучен" in resp.json()["detail"]


# ===========================================================================
# 8. Learn recipe — POST /inventory/crafting/{char_id}/learn-recipe
# ===========================================================================

class TestLearnRecipe:

    def test_learn_recipe_happy(self, craft_env):
        db = craft_env["db"]
        c = craft_env["client"]

        result_item2 = _create_item(db, 56, "Бронзовый клинок", "main_weapon")
        new_recipe = _create_recipe(db, name="Бронзовая ковка",
                                    profession_id=1, result_item_id=result_item2.id)
        db.commit()

        resp = c.post("/inventory/crafting/1/learn-recipe", json={
            "recipe_id": new_recipe.id,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Рецепт выучен"
        assert data["recipe_name"] == "Бронзовая ковка"

    def test_learn_recipe_not_found(self, craft_env):
        c = craft_env["client"]
        resp = c.post("/inventory/crafting/1/learn-recipe", json={"recipe_id": 99999})
        assert resp.status_code == 404

    def test_learn_recipe_wrong_profession(self, craft_env):
        db = craft_env["db"]
        c = craft_env["client"]

        prof2 = _create_profession(db, 2, "Алхимик", "alchemist")
        result_item2 = _create_item(db, 57, "Зелье маны", "consumable")
        alchemy_recipe = _create_recipe(db, name="Зелье маны",
                                        profession_id=prof2.id, result_item_id=result_item2.id)
        db.commit()

        resp = c.post("/inventory/crafting/1/learn-recipe", json={
            "recipe_id": alchemy_recipe.id,
        })
        assert resp.status_code == 400
        assert "профессия" in resp.json()["detail"].lower() or "Требуется" in resp.json()["detail"]

    def test_learn_recipe_insufficient_rank(self, craft_env):
        db = craft_env["db"]
        c = craft_env["client"]

        result_item2 = _create_item(db, 58, "Мастерский клинок", "main_weapon")
        rank2_recipe = _create_recipe(db, name="Мастерская ковка",
                                      profession_id=1, result_item_id=result_item2.id,
                                      required_rank=2)
        db.commit()

        resp = c.post("/inventory/crafting/1/learn-recipe", json={
            "recipe_id": rank2_recipe.id,
        })
        assert resp.status_code == 400
        assert "ранг" in resp.json()["detail"].lower()


# ===========================================================================
# 9. Learn recipe duplicate — returns 400
# ===========================================================================

class TestLearnRecipeDuplicate:

    def test_duplicate_learn_returns_400(self, craft_env):
        c = craft_env["client"]
        recipe = craft_env["recipe"]

        # Recipe is already learned via craft_env fixture
        resp = c.post("/inventory/crafting/1/learn-recipe", json={
            "recipe_id": recipe.id,
        })
        assert resp.status_code == 400
        assert "уже выучен" in resp.json()["detail"]


# ===========================================================================
# 10. Admin CRUD recipes
# ===========================================================================

class TestAdminRecipes:

    def test_create_recipe_with_ingredients(self, admin_recipe_env):
        db = admin_recipe_env["db"]
        c = admin_recipe_env["client"]

        prof = _create_profession(db)
        result_item = _create_item(db, 50, "Железный меч", "main_weapon")
        mat1 = _create_item(db, 100, "Железная руда", "resource")
        mat2 = _create_item(db, 101, "Уголь", "resource")
        db.commit()

        resp = c.post("/inventory/admin/recipes", json={
            "name": "Ковка меча",
            "description": "Базовый рецепт",
            "profession_id": prof.id,
            "required_rank": 1,
            "result_item_id": result_item.id,
            "result_quantity": 1,
            "rarity": "common",
            "auto_learn_rank": 1,
            "ingredients": [
                {"item_id": mat1.id, "quantity": 3},
                {"item_id": mat2.id, "quantity": 1},
            ],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Ковка меча"
        assert data["profession_id"] == prof.id
        assert len(data["ingredients"]) == 2

    def test_create_recipe_duplicate_name_400(self, admin_recipe_env):
        db = admin_recipe_env["db"]
        c = admin_recipe_env["client"]

        prof = _create_profession(db)
        item = _create_item(db, 50, "Item", "resource")
        _create_recipe(db, name="Existing Recipe", profession_id=prof.id,
                       result_item_id=item.id)
        db.commit()

        resp = c.post("/inventory/admin/recipes", json={
            "name": "Existing Recipe",
            "profession_id": prof.id,
            "result_item_id": item.id,
        })
        assert resp.status_code == 400

    def test_create_recipe_nonexistent_profession_400(self, admin_recipe_env):
        db = admin_recipe_env["db"]
        c = admin_recipe_env["client"]

        item = _create_item(db, 50, "Item", "resource")
        db.commit()

        resp = c.post("/inventory/admin/recipes", json={
            "name": "Bad Recipe",
            "profession_id": 9999,
            "result_item_id": item.id,
        })
        assert resp.status_code == 400

    def test_create_recipe_nonexistent_result_item_400(self, admin_recipe_env):
        db = admin_recipe_env["db"]
        c = admin_recipe_env["client"]

        prof = _create_profession(db)
        db.commit()

        resp = c.post("/inventory/admin/recipes", json={
            "name": "No Result",
            "profession_id": prof.id,
            "result_item_id": 9999,
        })
        assert resp.status_code == 400

    def test_list_recipes_paginated(self, admin_recipe_env):
        db = admin_recipe_env["db"]
        c = admin_recipe_env["client"]

        prof = _create_profession(db)
        for i in range(5):
            item = _create_item(db, 50 + i, f"Item {i}", "resource")
            _create_recipe(db, name=f"Recipe {i}", profession_id=prof.id,
                           result_item_id=item.id)
        db.commit()

        resp = c.get("/inventory/admin/recipes?page=1&per_page=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["per_page"] == 2
        assert len(data["items"]) == 2

    def test_list_recipes_filter_by_profession(self, admin_recipe_env):
        db = admin_recipe_env["db"]
        c = admin_recipe_env["client"]

        prof1 = _create_profession(db, 1, "Кузнец", "blacksmith")
        prof2 = _create_profession(db, 2, "Алхимик", "alchemist")
        item1 = _create_item(db, 50, "Sword", "main_weapon")
        item2 = _create_item(db, 51, "Potion", "consumable")
        _create_recipe(db, name="Sword Recipe", profession_id=prof1.id, result_item_id=item1.id)
        _create_recipe(db, name="Potion Recipe", profession_id=prof2.id, result_item_id=item2.id)
        db.commit()

        resp = c.get(f"/inventory/admin/recipes?profession_id={prof1.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Sword Recipe"

    def test_update_recipe(self, admin_recipe_env):
        db = admin_recipe_env["db"]
        c = admin_recipe_env["client"]

        prof = _create_profession(db)
        item = _create_item(db, 50, "Item", "resource")
        recipe = _create_recipe(db, name="Original", profession_id=prof.id,
                                result_item_id=item.id)
        db.commit()

        resp = c.put(f"/inventory/admin/recipes/{recipe.id}", json={
            "description": "Updated description",
            "required_rank": 2,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "Updated description"
        assert data["required_rank"] == 2

    def test_update_recipe_not_found_404(self, admin_recipe_env):
        c = admin_recipe_env["client"]
        resp = c.put("/inventory/admin/recipes/9999", json={"description": "X"})
        assert resp.status_code == 404

    def test_delete_recipe(self, admin_recipe_env):
        db = admin_recipe_env["db"]
        c = admin_recipe_env["client"]

        prof = _create_profession(db)
        item = _create_item(db, 50, "Item", "resource")
        recipe = _create_recipe(db, name="ToDelete", profession_id=prof.id,
                                result_item_id=item.id)
        db.commit()

        resp = c.delete(f"/inventory/admin/recipes/{recipe.id}")
        assert resp.status_code == 200
        assert "удалён" in resp.json()["detail"]

        assert db.query(models.Recipe).filter(models.Recipe.id == recipe.id).first() is None

    def test_delete_recipe_not_found_404(self, admin_recipe_env):
        c = admin_recipe_env["client"]
        resp = c.delete("/inventory/admin/recipes/9999")
        assert resp.status_code == 404


# ===========================================================================
# Security tests
# ===========================================================================

class TestCraftingSecurity:

    def test_craft_no_auth_401(self, client):
        resp = client.post("/inventory/crafting/1/craft", json={"recipe_id": 1})
        assert resp.status_code == 401

    def test_craft_wrong_character_403(self, craft_env):
        db = craft_env["db"]
        c = craft_env["client"]

        _insert_character(db, 2, user_id=999, name="OtherPlayer")
        db.commit()

        resp = c.post("/inventory/crafting/2/craft", json={"recipe_id": 1})
        assert resp.status_code == 403

    def test_craft_no_profession_400(self, craft_env):
        """Character without profession tries to craft."""
        db = craft_env["db"]
        c = craft_env["client"]

        # Create a second character with no profession
        _insert_character(db, 3, user_id=1, name="NoProfChar")
        db.commit()

        recipe = craft_env["recipe"]
        resp = c.post("/inventory/crafting/3/craft", json={"recipe_id": recipe.id})
        assert resp.status_code == 400
        assert "нет профессии" in resp.json()["detail"]

    def test_sql_injection_in_recipe_search(self, admin_recipe_env):
        c = admin_recipe_env["client"]
        resp = c.get("/inventory/admin/recipes?search='; DROP TABLE recipes; --")
        assert resp.status_code in (200, 400)
