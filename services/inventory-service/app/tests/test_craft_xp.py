"""
FEAT-082 — QA tests for craft XP reward and auto-rank-up.

Tests covering:
1. XP awarded by rarity
2. XP override via recipe.xp_reward
3. XP accumulation across multiple crafts
4. Auto-rank-up at threshold
5. Multi-rank jump
6. Auto-learn recipes on rank-up
7. Max rank: XP grows, rank stays
8. CraftResult response fields
9. Admin recipe CRUD with xp_reward field
"""

import pytest
from unittest.mock import patch
from sqlalchemy import text

from auth_http import get_current_user_via_http, UserRead, require_permission
import models
import crud


# ---------------------------------------------------------------------------
# Helpers (reuse patterns from test_crafting.py)
# ---------------------------------------------------------------------------

def _create_characters_table(db):
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


def _create_rank(db, profession_id=1, rank_number=1, name="Ученик",
                 required_experience=0):
    rank = models.ProfessionRank(
        profession_id=profession_id, rank_number=rank_number,
        name=name, required_experience=required_experience,
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
                   result_item_id=50, rarity="common", xp_reward=None,
                   auto_learn_rank=None, is_blueprint_recipe=False):
    recipe = models.Recipe(
        name=name, profession_id=profession_id, required_rank=required_rank,
        result_item_id=result_item_id, result_quantity=1, rarity=rarity,
        xp_reward=xp_reward, auto_learn_rank=auto_learn_rank, is_active=True,
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
def xp_env(client, db_session):
    """Crafting environment with 3 ranks for XP testing.

    Ranks:
      1 — Ученик (0 XP)
      2 — Подмастерье (500 XP)
      3 — Мастер (2000 XP)
    """
    _create_characters_table(db_session)
    _insert_character(db_session, 1, user_id=1, name="Crafter")

    prof = _create_profession(db_session, 1, "Кузнец", "blacksmith")
    _create_rank(db_session, profession_id=prof.id, rank_number=1, name="Ученик",
                 required_experience=0)
    _create_rank(db_session, profession_id=prof.id, rank_number=2, name="Подмастерье",
                 required_experience=500)
    _create_rank(db_session, profession_id=prof.id, rank_number=3, name="Мастер",
                 required_experience=2000)

    # Result item
    _create_item(db_session, 50, "Железный меч", "main_weapon", max_stack=99)

    # Material items
    ore = _create_item(db_session, 100, "Железная руда", "resource")
    coal = _create_item(db_session, 101, "Уголь", "resource")

    # Default common recipe (gives 10 XP by RARITY_XP_MAP)
    recipe = _create_recipe(db_session, name="Ковка железного меча",
                            profession_id=prof.id, result_item_id=50,
                            rarity="common", auto_learn_rank=1)
    _add_ingredient(db_session, recipe.id, ore.id, 1)
    _add_ingredient(db_session, recipe.id, coal.id, 1)

    _assign_profession(db_session, 1, prof.id, rank=1, experience=0)
    _learn_recipe(db_session, 1, recipe.id)

    # Generous material supply
    _add_inventory(db_session, 1, ore.id, 500)
    _add_inventory(db_session, 1, coal.id, 500)

    db_session.commit()

    from main import app
    app.dependency_overrides[get_current_user_via_http] = lambda: _user1

    yield {
        "client": client,
        "db": db_session,
        "app": app,
        "profession": prof,
        "recipe": recipe,
        "ore": ore,
        "coal": coal,
    }

    app.dependency_overrides.pop(get_current_user_via_http, None)


@pytest.fixture()
def admin_env(client, db_session):
    """Admin environment for recipe CRUD xp_reward tests."""
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
# 1. Craft awards XP based on recipe rarity
# ===========================================================================

class TestCraftXpByRarity:

    @pytest.mark.parametrize("rarity,expected_xp", [
        ("common", 10),
        ("rare", 25),
        ("epic", 50),
        ("legendary", 100),
        ("mythical", 200),
        ("divine", 500),
        ("demonic", 500),
    ])
    def test_craft_awards_xp_by_rarity(self, xp_env, rarity, expected_xp):
        db = xp_env["db"]
        c = xp_env["client"]

        # Create recipe with specific rarity (no xp_reward override)
        result_item = _create_item(db, 200 + hash(rarity) % 1000, f"Item_{rarity}",
                                   "main_weapon", max_stack=99)
        recipe = _create_recipe(db, name=f"Recipe_{rarity}", profession_id=1,
                                result_item_id=result_item.id, rarity=rarity)
        _add_ingredient(db, recipe.id, xp_env["ore"].id, 1)
        _learn_recipe(db, 1, recipe.id)
        db.commit()

        resp = c.post("/inventory/crafting/1/craft", json={"recipe_id": recipe.id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["xp_earned"] == expected_xp


# ===========================================================================
# 2. Craft awards XP from xp_reward override
# ===========================================================================

class TestCraftXpOverride:

    def test_xp_reward_overrides_rarity(self, xp_env):
        db = xp_env["db"]
        c = xp_env["client"]

        result_item = _create_item(db, 300, "Особый клинок", "main_weapon", max_stack=99)
        recipe = _create_recipe(db, name="Рецепт с XP override", profession_id=1,
                                result_item_id=result_item.id, rarity="common",
                                xp_reward=77)
        _add_ingredient(db, recipe.id, xp_env["ore"].id, 1)
        _learn_recipe(db, 1, recipe.id)
        db.commit()

        resp = c.post("/inventory/crafting/1/craft", json={"recipe_id": recipe.id})
        assert resp.status_code == 200
        data = resp.json()
        # xp_reward=77 overrides common's default 10
        assert data["xp_earned"] == 77

    def test_xp_reward_zero_override(self, xp_env):
        """xp_reward=0 should award 0 XP (explicit override, not None fallback)."""
        db = xp_env["db"]
        c = xp_env["client"]

        result_item = _create_item(db, 301, "Бесплатный клинок", "main_weapon", max_stack=99)
        recipe = _create_recipe(db, name="Рецепт 0 XP", profession_id=1,
                                result_item_id=result_item.id, rarity="legendary",
                                xp_reward=0)
        _add_ingredient(db, recipe.id, xp_env["ore"].id, 1)
        _learn_recipe(db, 1, recipe.id)
        db.commit()

        resp = c.post("/inventory/crafting/1/craft", json={"recipe_id": recipe.id})
        assert resp.status_code == 200
        data = resp.json()
        # xp_reward=0 is an explicit value, NOT None
        # In Python: `0 if 0 is not None` is truthy, so xp_reward=0 should be used
        assert data["xp_earned"] == 0


# ===========================================================================
# 3. XP accumulates across multiple crafts
# ===========================================================================

class TestXpAccumulation:

    def test_xp_accumulates(self, xp_env):
        c = xp_env["client"]
        recipe = xp_env["recipe"]

        # Common rarity = 10 XP per craft
        total = 0
        for _ in range(5):
            resp = c.post("/inventory/crafting/1/craft", json={"recipe_id": recipe.id})
            assert resp.status_code == 200
            data = resp.json()
            total += data["xp_earned"]
            assert data["new_total_xp"] == total

        assert total == 50  # 5 * 10


# ===========================================================================
# 4. Rank auto-promotes when threshold is reached
# ===========================================================================

class TestAutoRankUp:

    def test_rank_up_at_threshold(self, xp_env):
        """Start at 490 XP, craft gives 10 → 500 XP → rank 2."""
        db = xp_env["db"]
        c = xp_env["client"]

        # Set character XP close to threshold
        cp = db.query(models.CharacterProfession).filter(
            models.CharacterProfession.character_id == 1
        ).first()
        cp.experience = 490
        db.commit()

        recipe = xp_env["recipe"]
        resp = c.post("/inventory/crafting/1/craft", json={"recipe_id": recipe.id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["xp_earned"] == 10
        assert data["new_total_xp"] == 500
        assert data["rank_up"] is True
        assert data["new_rank_name"] == "Подмастерье"

        # Verify in DB
        db.expire_all()
        cp = db.query(models.CharacterProfession).filter(
            models.CharacterProfession.character_id == 1
        ).first()
        assert cp.current_rank == 2
        assert cp.experience == 500

    def test_no_rank_up_below_threshold(self, xp_env):
        """Start at 480 XP, craft gives 10 → 490 XP → still rank 1."""
        db = xp_env["db"]
        c = xp_env["client"]

        cp = db.query(models.CharacterProfession).filter(
            models.CharacterProfession.character_id == 1
        ).first()
        cp.experience = 480
        db.commit()

        recipe = xp_env["recipe"]
        resp = c.post("/inventory/crafting/1/craft", json={"recipe_id": recipe.id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["rank_up"] is False
        assert data["new_rank_name"] is None
        assert data["new_total_xp"] == 490


# ===========================================================================
# 5. Multi-rank jump
# ===========================================================================

class TestMultiRankJump:

    def test_multi_rank_jump(self, xp_env):
        """A single craft that gives enough XP to jump from rank 1 to rank 3."""
        db = xp_env["db"]
        c = xp_env["client"]

        # Create high-XP recipe (divine = 500 XP)
        result_item = _create_item(db, 400, "Божественный клинок", "main_weapon", max_stack=99)
        recipe = _create_recipe(db, name="Божественная ковка", profession_id=1,
                                result_item_id=result_item.id, rarity="common",
                                xp_reward=2500)
        _add_ingredient(db, recipe.id, xp_env["ore"].id, 1)
        _learn_recipe(db, 1, recipe.id)

        # Start at rank 1 with 0 XP; craft gives 2500 XP
        # Thresholds: rank 2 = 500, rank 3 = 2000 → should jump to rank 3
        db.commit()

        resp = c.post("/inventory/crafting/1/craft", json={"recipe_id": recipe.id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["xp_earned"] == 2500
        assert data["new_total_xp"] == 2500
        assert data["rank_up"] is True
        # new_rank_name should be the highest rank achieved
        assert data["new_rank_name"] == "Мастер"

        # Verify DB
        db.expire_all()
        cp = db.query(models.CharacterProfession).filter(
            models.CharacterProfession.character_id == 1
        ).first()
        assert cp.current_rank == 3


# ===========================================================================
# 6. Auto-learn recipes fire on rank-up
# ===========================================================================

class TestAutoLearnOnRankUp:

    def test_auto_learn_recipes_on_rank_up(self, xp_env):
        db = xp_env["db"]
        c = xp_env["client"]

        # Create a recipe that auto-learns at rank 2
        result_item2 = _create_item(db, 401, "Стальной клинок", "main_weapon", max_stack=99)
        auto_recipe = _create_recipe(db, name="Стальная ковка", profession_id=1,
                                     result_item_id=result_item2.id, rarity="rare",
                                     auto_learn_rank=2)

        # Set XP close to rank 2 threshold
        cp = db.query(models.CharacterProfession).filter(
            models.CharacterProfession.character_id == 1
        ).first()
        cp.experience = 490
        db.commit()

        recipe = xp_env["recipe"]
        resp = c.post("/inventory/crafting/1/craft", json={"recipe_id": recipe.id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["rank_up"] is True

        # auto_learned_recipes should contain the auto-learn recipe
        auto_learned_names = [r["name"] for r in data["auto_learned_recipes"]]
        assert "Стальная ковка" in auto_learned_names

        # Verify CharacterRecipe was created in DB
        db.expire_all()
        learned = db.query(models.CharacterRecipe).filter(
            models.CharacterRecipe.character_id == 1,
            models.CharacterRecipe.recipe_id == auto_recipe.id,
        ).first()
        assert learned is not None

    def test_auto_learn_fires_for_each_intermediate_rank(self, xp_env):
        """Multi-rank jump should auto-learn recipes for every rank passed."""
        db = xp_env["db"]
        c = xp_env["client"]

        # Auto-learn recipe at rank 2
        result_item2 = _create_item(db, 402, "R2 item", "main_weapon", max_stack=99)
        r2_recipe = _create_recipe(db, name="Auto R2", profession_id=1,
                                   result_item_id=result_item2.id, auto_learn_rank=2)

        # Auto-learn recipe at rank 3
        result_item3 = _create_item(db, 403, "R3 item", "main_weapon", max_stack=99)
        r3_recipe = _create_recipe(db, name="Auto R3", profession_id=1,
                                   result_item_id=result_item3.id, auto_learn_rank=3)

        # Big XP craft to jump from rank 1 to rank 3
        result_big = _create_item(db, 404, "Mega item", "main_weapon", max_stack=99)
        big_recipe = _create_recipe(db, name="Mega craft", profession_id=1,
                                    result_item_id=result_big.id, xp_reward=3000)
        _add_ingredient(db, big_recipe.id, xp_env["ore"].id, 1)
        _learn_recipe(db, 1, big_recipe.id)
        db.commit()

        resp = c.post("/inventory/crafting/1/craft", json={"recipe_id": big_recipe.id})
        assert resp.status_code == 200
        data = resp.json()

        auto_learned_names = [r["name"] for r in data["auto_learned_recipes"]]
        assert "Auto R2" in auto_learned_names
        assert "Auto R3" in auto_learned_names


# ===========================================================================
# 7. Max rank: XP grows, rank stays
# ===========================================================================

class TestMaxRank:

    def test_max_rank_xp_accumulates_rank_stays(self, xp_env):
        db = xp_env["db"]
        c = xp_env["client"]

        # Set character at max rank (rank 3)
        cp = db.query(models.CharacterProfession).filter(
            models.CharacterProfession.character_id == 1
        ).first()
        cp.current_rank = 3
        cp.experience = 5000
        db.commit()

        recipe = xp_env["recipe"]
        resp = c.post("/inventory/crafting/1/craft", json={"recipe_id": recipe.id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["xp_earned"] == 10
        assert data["new_total_xp"] == 5010
        assert data["rank_up"] is False
        assert data["new_rank_name"] is None

        # Verify rank unchanged in DB
        db.expire_all()
        cp = db.query(models.CharacterProfession).filter(
            models.CharacterProfession.character_id == 1
        ).first()
        assert cp.current_rank == 3
        assert cp.experience == 5010


# ===========================================================================
# 8. CraftResult response fields
# ===========================================================================

class TestCraftResultFields:

    def test_craft_result_contains_all_xp_fields(self, xp_env):
        c = xp_env["client"]
        recipe = xp_env["recipe"]

        resp = c.post("/inventory/crafting/1/craft", json={"recipe_id": recipe.id})
        assert resp.status_code == 200
        data = resp.json()

        # Mandatory fields
        assert "success" in data
        assert "crafted_item" in data
        assert "consumed_materials" in data
        assert "blueprint_consumed" in data

        # New XP fields
        assert "xp_earned" in data
        assert "new_total_xp" in data
        assert "rank_up" in data
        assert "new_rank_name" in data
        assert "auto_learned_recipes" in data

        # Type checks
        assert isinstance(data["xp_earned"], int)
        assert isinstance(data["new_total_xp"], int)
        assert isinstance(data["rank_up"], bool)
        assert isinstance(data["auto_learned_recipes"], list)

    def test_craft_result_no_rank_up_fields(self, xp_env):
        """When no rank-up occurs, new_rank_name is null and auto_learned_recipes is empty."""
        c = xp_env["client"]
        recipe = xp_env["recipe"]

        resp = c.post("/inventory/crafting/1/craft", json={"recipe_id": recipe.id})
        data = resp.json()
        assert data["rank_up"] is False
        assert data["new_rank_name"] is None
        assert data["auto_learned_recipes"] == []


# ===========================================================================
# 9. Admin recipe CRUD with xp_reward
# ===========================================================================

class TestAdminRecipeXpReward:

    def test_create_recipe_with_xp_reward(self, admin_env):
        db = admin_env["db"]
        c = admin_env["client"]

        prof = _create_profession(db)
        _create_rank(db, profession_id=prof.id, rank_number=1, name="Ученик")
        result_item = _create_item(db, 50, "Железный меч", "main_weapon")
        mat = _create_item(db, 100, "Руда", "resource")
        db.commit()

        resp = c.post("/inventory/admin/recipes", json={
            "name": "Рецепт с XP",
            "profession_id": prof.id,
            "result_item_id": result_item.id,
            "rarity": "common",
            "xp_reward": 42,
            "ingredients": [{"item_id": mat.id, "quantity": 1}],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["xp_reward"] == 42

    def test_create_recipe_without_xp_reward(self, admin_env):
        db = admin_env["db"]
        c = admin_env["client"]

        prof = _create_profession(db)
        _create_rank(db, profession_id=prof.id, rank_number=1, name="Ученик")
        result_item = _create_item(db, 50, "Простой предмет", "main_weapon")
        mat = _create_item(db, 100, "Руда", "resource")
        db.commit()

        resp = c.post("/inventory/admin/recipes", json={
            "name": "Рецепт без XP override",
            "profession_id": prof.id,
            "result_item_id": result_item.id,
            "rarity": "rare",
            "ingredients": [{"item_id": mat.id, "quantity": 1}],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["xp_reward"] is None

    def test_update_recipe_xp_reward(self, admin_env):
        db = admin_env["db"]
        c = admin_env["client"]

        prof = _create_profession(db)
        _create_rank(db, profession_id=prof.id, rank_number=1, name="Ученик")
        result_item = _create_item(db, 50, "Item", "resource")
        recipe = _create_recipe(db, name="Обновляемый", profession_id=prof.id,
                                result_item_id=result_item.id, xp_reward=10)
        db.commit()

        resp = c.put(f"/inventory/admin/recipes/{recipe.id}", json={
            "xp_reward": 99,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["xp_reward"] == 99

    def test_update_recipe_xp_reward_preserved_when_not_sent(self, admin_env):
        """Not sending xp_reward in update should preserve the existing value.

        Note: the generic update_recipe pattern (`if value is not None: setattr`)
        means that explicitly sending null does NOT clear the field. This is a
        pre-existing limitation of the update pattern in crud.py (applies to all
        nullable Optional fields). Tracked as a known limitation, not a FEAT-082 issue.
        """
        db = admin_env["db"]
        c = admin_env["client"]

        prof = _create_profession(db)
        _create_rank(db, profession_id=prof.id, rank_number=1, name="Ученик")
        result_item = _create_item(db, 50, "Item2", "resource")
        recipe = _create_recipe(db, name="Сохраняемый", profession_id=prof.id,
                                result_item_id=result_item.id, xp_reward=50)
        db.commit()

        # Update a different field — xp_reward should stay 50
        resp = c.put(f"/inventory/admin/recipes/{recipe.id}", json={
            "description": "Updated desc",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["xp_reward"] == 50

    def test_read_recipe_includes_xp_reward(self, admin_env):
        db = admin_env["db"]
        c = admin_env["client"]

        prof = _create_profession(db)
        _create_rank(db, profession_id=prof.id, rank_number=1, name="Ученик")
        result_item = _create_item(db, 50, "Item3", "resource")
        recipe = _create_recipe(db, name="Читаемый", profession_id=prof.id,
                                result_item_id=result_item.id, xp_reward=123)
        db.commit()

        resp = c.get(f"/inventory/admin/recipes?search=Читаемый")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        found = [r for r in data["items"] if r["name"] == "Читаемый"]
        assert len(found) == 1
        assert found[0]["xp_reward"] == 123
