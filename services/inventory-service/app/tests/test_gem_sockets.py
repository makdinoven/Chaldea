"""
Task 7 — QA tests for FEAT-086: Jeweler gems, sockets, smelting.

Covers: insert-gem, extract-gem, socket-info, smelt-info, smelt endpoints,
equip/unequip with gems, build_modifiers_dict with gems, security, XP.
"""

import json
import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy import text

from auth_http import get_current_user_via_http, UserRead
import models
import crud


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


def _create_profession(db, prof_id=1, name="Ювелир", slug="jeweler"):
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


def _create_item(db, item_id, name, item_type="resource", max_stack=99,
                 socket_count=0, **kwargs):
    item = models.Items(
        id=item_id, name=name, item_level=1, item_type=item_type,
        item_rarity=kwargs.pop("item_rarity", "common"),
        max_stack_size=max_stack, is_unique=False,
        socket_count=socket_count,
        **kwargs,
    )
    db.add(item)
    db.flush()
    return item


def _add_inventory(db, char_id, item_id, quantity, socketed_gems=None):
    inv = models.CharacterInventory(
        character_id=char_id, item_id=item_id, quantity=quantity,
    )
    if socketed_gems is not None:
        inv.socketed_gems = json.dumps(socketed_gems)
    db.add(inv)
    db.flush()
    return inv


def _assign_profession(db, char_id, profession_id, rank=1, experience=0):
    cp = models.CharacterProfession(
        character_id=char_id, profession_id=profession_id,
        current_rank=rank, experience=experience,
    )
    db.add(cp)
    db.flush()
    return cp


def _create_equipment_slot(db, char_id, slot_type, item_id=None,
                           socketed_gems=None):
    slot = models.EquipmentSlot(
        character_id=char_id, slot_type=slot_type, item_id=item_id,
        is_enabled=True,
    )
    if socketed_gems is not None:
        slot.socketed_gems = json.dumps(socketed_gems)
    db.add(slot)
    db.flush()
    return slot


def _create_recipe(db, recipe_id, profession_id, result_item_id, ingredients):
    """Create recipe with ingredients. ingredients = [(item_id, quantity), ...]"""
    recipe = models.Recipe(
        id=recipe_id, name=f"Recipe-{recipe_id}", profession_id=profession_id,
        required_rank=1, result_item_id=result_item_id, result_quantity=1,
        rarity="common", is_active=True,
    )
    db.add(recipe)
    db.flush()
    for item_id, qty in ingredients:
        ing = models.RecipeIngredient(
            recipe_id=recipe.id, item_id=item_id, quantity=qty,
        )
        db.add(ing)
    db.flush()
    return recipe


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_user1 = UserRead(id=1, username="player1", role="user", permissions=[])


@pytest.fixture()
def gem_env(client, db_session):
    """Full gem/socket test environment: jeweler with ring and gem."""
    _create_characters_table(db_session)
    _insert_character(db_session, 1, user_id=1, name="Jeweler")

    # Profession + ranks (3 levels for extraction tests)
    prof = _create_profession(db_session, 1, "Ювелир", "jeweler")
    _create_rank(db_session, profession_id=prof.id, rank_number=1, name="Ученик")
    _create_rank(db_session, profession_id=prof.id, rank_number=2, name="Подмастерье")
    _create_rank(db_session, profession_id=prof.id, rank_number=3, name="Мастер")

    # Jewelry item: ring with 2 sockets, has strength modifier
    ring = _create_item(
        db_session, 10, "Золотое кольцо", "ring", max_stack=1,
        socket_count=2, strength_modifier=5,
    )

    # Gem item with modifiers
    gem = _create_item(
        db_session, 20, "Рубин", "gem", max_stack=99,
        strength_modifier=3, res_fire_modifier=0.5,
    )

    # Junk item for smelting
    junk = _create_item(
        db_session, 30, "Ювелирный лом", "resource", max_stack=99,
    )

    # Ingredient resource for recipe smelting
    mat1 = _create_item(db_session, 40, "Золотой слиток", "resource", max_stack=99)
    mat2 = _create_item(db_session, 41, "Серебряный слиток", "resource", max_stack=99)

    # Add ring and gems to inventory
    ring_inv = _add_inventory(db_session, 1, ring.id, 1)
    gem_inv = _add_inventory(db_session, 1, gem.id, 5)

    _assign_profession(db_session, 1, prof.id, rank=1, experience=0)
    db_session.commit()

    from main import app
    app.dependency_overrides[get_current_user_via_http] = lambda: _user1

    yield {
        "client": client,
        "db": db_session,
        "app": app,
        "profession": prof,
        "ring": ring,
        "gem": gem,
        "junk": junk,
        "mat1": mat1,
        "mat2": mat2,
        "ring_inv": ring_inv,
        "gem_inv": gem_inv,
    }

    app.dependency_overrides.pop(get_current_user_via_http, None)


# ===========================================================================
# 1. Insert gem — happy path
# ===========================================================================

class TestInsertGemHappyPath:

    def test_insert_gem_into_empty_slot(self, gem_env):
        """Jeweler inserts gem into empty slot. Gem consumed, socketed_gems updated."""
        c = gem_env["client"]
        db = gem_env["db"]
        ring_inv = gem_env["ring_inv"]
        gem_inv = gem_env["gem_inv"]

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/insert-gem", json={
                "item_row_id": ring_inv.id,
                "source": "inventory",
                "slot_index": 0,
                "gem_inventory_id": gem_inv.id,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["item_name"] == "Золотое кольцо"
        assert data["gem_name"] == "Рубин"
        assert data["slot_index"] == 0
        assert data["xp_earned"] == 10

        # Verify DB: gem consumed
        db.expire_all()
        gem_row = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == gem_inv.id
        ).first()
        assert gem_row.quantity == 4  # was 5

        # Verify socketed_gems updated
        inv = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == ring_inv.id
        ).first()
        socketed = json.loads(inv.socketed_gems)
        assert socketed[0] == gem_env["gem"].id
        assert socketed[1] is None


# ===========================================================================
# 2. Non-jeweler tries to insert — expect 400
# ===========================================================================

class TestInsertGemNotJeweler:

    def test_non_jeweler_cannot_insert(self, gem_env):
        db = gem_env["db"]
        c = gem_env["client"]
        ring_inv = gem_env["ring_inv"]
        gem_inv = gem_env["gem_inv"]

        # Change profession to blacksmith
        cp = db.query(models.CharacterProfession).filter(
            models.CharacterProfession.character_id == 1
        ).first()
        db.delete(cp)
        db.flush()

        prof2 = _create_profession(db, 2, "Кузнец", "blacksmith")
        _create_rank(db, profession_id=prof2.id, rank_number=1, name="Ученик")
        _assign_profession(db, 1, prof2.id, rank=1)
        db.commit()

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/insert-gem", json={
                "item_row_id": ring_inv.id,
                "source": "inventory",
                "slot_index": 0,
                "gem_inventory_id": gem_inv.id,
            })

        assert resp.status_code == 400
        assert "ювелир" in resp.json()["detail"].lower()


# ===========================================================================
# 3. Item is not jewelry — expect 400
# ===========================================================================

class TestInsertGemWrongItemType:

    def test_insert_into_non_jewelry_returns_400(self, gem_env):
        db = gem_env["db"]
        c = gem_env["client"]
        gem_inv = gem_env["gem_inv"]

        sword = _create_item(db, 50, "Меч", "main_weapon", max_stack=1, socket_count=2)
        sword_inv = _add_inventory(db, 1, sword.id, 1)
        db.commit()

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/insert-gem", json={
                "item_row_id": sword_inv.id,
                "source": "inventory",
                "slot_index": 0,
                "gem_inventory_id": gem_inv.id,
            })

        assert resp.status_code == 400
        assert "украшен" in resp.json()["detail"].lower()


# ===========================================================================
# 4. Slot already occupied — expect 400
# ===========================================================================

class TestInsertGemSlotOccupied:

    def test_insert_into_occupied_slot_returns_400(self, gem_env):
        db = gem_env["db"]
        c = gem_env["client"]
        ring_inv = gem_env["ring_inv"]
        gem_inv = gem_env["gem_inv"]

        # Pre-fill slot 0
        ring_inv.socketed_gems = json.dumps([gem_env["gem"].id, None])
        db.commit()

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/insert-gem", json={
                "item_row_id": ring_inv.id,
                "source": "inventory",
                "slot_index": 0,
                "gem_inventory_id": gem_inv.id,
            })

        assert resp.status_code == 400
        assert "занят" in resp.json()["detail"].lower()


# ===========================================================================
# 5. Invalid slot_index (>= socket_count) — expect 400
# ===========================================================================

class TestInsertGemInvalidSlotIndex:

    def test_slot_index_out_of_range_returns_400(self, gem_env):
        c = gem_env["client"]
        ring_inv = gem_env["ring_inv"]
        gem_inv = gem_env["gem_inv"]

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/insert-gem", json={
                "item_row_id": ring_inv.id,
                "source": "inventory",
                "slot_index": 5,  # ring has 2 sockets (0 and 1)
                "gem_inventory_id": gem_inv.id,
            })

        assert resp.status_code == 400
        assert "индекс" in resp.json()["detail"].lower() or "слот" in resp.json()["detail"].lower()


# ===========================================================================
# 6. No gem in inventory — expect 400/404
# ===========================================================================

class TestInsertGemNoGem:

    def test_gem_not_in_inventory_returns_error(self, gem_env):
        c = gem_env["client"]
        ring_inv = gem_env["ring_inv"]

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/insert-gem", json={
                "item_row_id": ring_inv.id,
                "source": "inventory",
                "slot_index": 0,
                "gem_inventory_id": 99999,
            })

        assert resp.status_code in (400, 404)


# ===========================================================================
# 7. Item has no sockets (socket_count=0) — expect 400
# ===========================================================================

class TestInsertGemNoSockets:

    def test_item_with_zero_sockets_returns_400(self, gem_env):
        db = gem_env["db"]
        c = gem_env["client"]
        gem_inv = gem_env["gem_inv"]

        ring_no_sockets = _create_item(
            db, 55, "Простое кольцо", "ring", max_stack=1, socket_count=0,
        )
        ring_inv2 = _add_inventory(db, 1, ring_no_sockets.id, 1)
        db.commit()

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/insert-gem", json={
                "item_row_id": ring_inv2.id,
                "source": "inventory",
                "slot_index": 0,
                "gem_inventory_id": gem_inv.id,
            })

        assert resp.status_code == 400


# ===========================================================================
# 8. Extract gem — success (gem preserved)
# ===========================================================================

class TestExtractGemPreserved:

    def test_extract_gem_preserved(self, gem_env):
        """Mock random < preservation_chance. Gem returned to inventory."""
        db = gem_env["db"]
        c = gem_env["client"]
        ring_inv = gem_env["ring_inv"]
        gem = gem_env["gem"]

        # Pre-insert gem into slot 0
        ring_inv.socketed_gems = json.dumps([gem.id, None])
        db.commit()

        initial_gem_qty = gem_env["gem_inv"].quantity

        with patch("main.random.random", return_value=0.01), \
             patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/extract-gem", json={
                "item_row_id": ring_inv.id,
                "source": "inventory",
                "slot_index": 0,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["gem_preserved"] is True
        assert data["gem_name"] == "Рубин"
        assert data["preservation_chance"] == 10  # rank 1

        # Verify slot cleared
        db.expire_all()
        inv = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == ring_inv.id
        ).first()
        socketed = json.loads(inv.socketed_gems) if inv.socketed_gems else [None, None]
        assert socketed[0] is None

        # Verify gem returned (quantity increased)
        gem_rows = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == 1,
            models.CharacterInventory.item_id == gem.id,
        ).all()
        total_qty = sum(r.quantity for r in gem_rows)
        assert total_qty == initial_gem_qty + 1


# ===========================================================================
# 9. Extract gem — failed (gem destroyed)
# ===========================================================================

class TestExtractGemDestroyed:

    def test_extract_gem_destroyed(self, gem_env):
        """Mock random >= preservation_chance. Gem destroyed, slot cleared."""
        db = gem_env["db"]
        c = gem_env["client"]
        ring_inv = gem_env["ring_inv"]
        gem = gem_env["gem"]

        ring_inv.socketed_gems = json.dumps([gem.id, None])
        db.commit()

        initial_gem_qty = gem_env["gem_inv"].quantity

        with patch("main.random.random", return_value=0.99), \
             patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/extract-gem", json={
                "item_row_id": ring_inv.id,
                "source": "inventory",
                "slot_index": 0,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["gem_preserved"] is False

        # Verify slot cleared
        db.expire_all()
        inv = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == ring_inv.id
        ).first()
        socketed = json.loads(inv.socketed_gems) if inv.socketed_gems else [None, None]
        assert socketed[0] is None

        # Verify gem NOT returned (quantity unchanged)
        gem_rows = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == 1,
            models.CharacterInventory.item_id == gem.id,
        ).all()
        total_qty = sum(r.quantity for r in gem_rows)
        assert total_qty == initial_gem_qty


# ===========================================================================
# 10. Different rank chances: rank 1 (10%), rank 2 (40%), rank 3 (70%)
# ===========================================================================

class TestExtractionRankChances:

    def test_rank_1_preservation_10_percent(self):
        assert crud.GEM_PRESERVATION_CHANCES[1] == 10

    def test_rank_2_preservation_40_percent(self):
        assert crud.GEM_PRESERVATION_CHANCES[2] == 40

    def test_rank_3_preservation_70_percent(self):
        assert crud.GEM_PRESERVATION_CHANCES[3] == 70

    def test_rank2_extract_preserved_at_35(self, gem_env):
        """Rank 2 has 40% chance. random=0.35 < 0.40 => preserved."""
        db = gem_env["db"]
        c = gem_env["client"]
        ring_inv = gem_env["ring_inv"]
        gem = gem_env["gem"]

        # Upgrade to rank 2
        cp = db.query(models.CharacterProfession).filter(
            models.CharacterProfession.character_id == 1
        ).first()
        cp.current_rank = 2
        ring_inv.socketed_gems = json.dumps([gem.id, None])
        db.commit()

        with patch("main.random.random", return_value=0.35), \
             patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/extract-gem", json={
                "item_row_id": ring_inv.id,
                "source": "inventory",
                "slot_index": 0,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["gem_preserved"] is True
        assert data["preservation_chance"] == 40

    def test_rank3_extract_destroyed_at_75(self, gem_env):
        """Rank 3 has 70% chance. random=0.75 >= 0.70 => destroyed."""
        db = gem_env["db"]
        c = gem_env["client"]
        ring_inv = gem_env["ring_inv"]
        gem = gem_env["gem"]

        cp = db.query(models.CharacterProfession).filter(
            models.CharacterProfession.character_id == 1
        ).first()
        cp.current_rank = 3
        ring_inv.socketed_gems = json.dumps([gem.id, None])
        db.commit()

        with patch("main.random.random", return_value=0.75), \
             patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/extract-gem", json={
                "item_row_id": ring_inv.id,
                "source": "inventory",
                "slot_index": 0,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["gem_preserved"] is False
        assert data["preservation_chance"] == 70


# ===========================================================================
# 11. Empty slot extraction — expect 400
# ===========================================================================

class TestExtractGemEmptySlot:

    def test_extract_from_empty_slot_returns_400(self, gem_env):
        c = gem_env["client"]
        ring_inv = gem_env["ring_inv"]

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/extract-gem", json={
                "item_row_id": ring_inv.id,
                "source": "inventory",
                "slot_index": 0,
            })

        assert resp.status_code == 400
        assert "нет камня" in resp.json()["detail"].lower()


# ===========================================================================
# 12. Insert gem into equipped item
# ===========================================================================

class TestInsertGemEquipped:

    def test_insert_gem_into_equipped_item(self, gem_env):
        """Insert gem into equipped ring. Verify socketed_gems on equipment_slots."""
        db = gem_env["db"]
        c = gem_env["client"]
        gem_inv = gem_env["gem_inv"]
        ring = gem_env["ring"]

        eq_slot = _create_equipment_slot(db, 1, "ring", item_id=ring.id)
        db.commit()

        mock_apply = AsyncMock()

        with patch("main.apply_modifiers_in_attributes_service", mock_apply):
            resp = c.post("/inventory/crafting/1/insert-gem", json={
                "item_row_id": eq_slot.id,
                "source": "equipment",
                "slot_index": 0,
                "gem_inventory_id": gem_inv.id,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        # Verify equipment slot has socketed_gems
        db.expire_all()
        slot = db.query(models.EquipmentSlot).filter(
            models.EquipmentSlot.id == eq_slot.id
        ).first()
        socketed = json.loads(slot.socketed_gems)
        assert socketed[0] == gem_env["gem"].id

        # Verify modifiers were applied (apply_modifiers called)
        mock_apply.assert_called_once()
        call_args = mock_apply.call_args
        assert call_args[0][0] == 1  # character_id
        mods = call_args[0][1]
        assert mods.get("strength", 0) == 3  # gem has strength_modifier=3


# ===========================================================================
# 13. Extract gem from equipped item
# ===========================================================================

class TestExtractGemEquipped:

    def test_extract_gem_from_equipped_item(self, gem_env):
        """Extract gem from equipped ring. Verify modifiers removed."""
        db = gem_env["db"]
        c = gem_env["client"]
        ring = gem_env["ring"]
        gem = gem_env["gem"]

        eq_slot = _create_equipment_slot(db, 1, "ring", item_id=ring.id,
                                          socketed_gems=[gem.id, None])
        db.commit()

        mock_apply = AsyncMock()

        with patch("main.random.random", return_value=0.01), \
             patch("main.apply_modifiers_in_attributes_service", mock_apply):
            resp = c.post("/inventory/crafting/1/extract-gem", json={
                "item_row_id": eq_slot.id,
                "source": "equipment",
                "slot_index": 0,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["gem_preserved"] is True

        # Verify negative modifiers applied (gem removal)
        mock_apply.assert_called_once()
        call_args = mock_apply.call_args
        mods = call_args[0][1]
        assert mods.get("strength", 0) == -3  # negative of gem's strength_modifier


# ===========================================================================
# 14. Smelt jewelry with recipe — returns ~50% ingredients
# ===========================================================================

class TestSmeltWithRecipe:

    def test_smelt_with_recipe_returns_50_percent(self, gem_env):
        db = gem_env["db"]
        c = gem_env["client"]
        ring = gem_env["ring"]
        ring_inv = gem_env["ring_inv"]
        mat1 = gem_env["mat1"]
        mat2 = gem_env["mat2"]

        # Create recipe for ring: 4 gold + 2 silver
        _create_recipe(db, 1, gem_env["profession"].id, ring.id,
                       [(mat1.id, 4), (mat2.id, 2)])
        db.commit()

        resp = c.post("/inventory/crafting/1/smelt", json={
            "inventory_item_id": ring_inv.id,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["item_name"] == "Золотое кольцо"

        # Check materials returned: 4 // 2 = 2, 2 // 2 = 1
        mat_dict = {m["name"]: m["quantity"] for m in data["materials_returned"]}
        assert mat_dict["Золотой слиток"] == 2  # max(1, 4//2) = 2
        assert mat_dict["Серебряный слиток"] == 1  # max(1, 2//2) = 1

        # Ring should be deleted from inventory
        db.expire_all()
        inv = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == ring_inv.id
        ).first()
        assert inv is None


# ===========================================================================
# 15. Smelt jewelry without recipe — returns "Ювелирный лом"
# ===========================================================================

class TestSmeltWithoutRecipe:

    def test_smelt_no_recipe_returns_junk(self, gem_env):
        db = gem_env["db"]
        c = gem_env["client"]
        ring_inv = gem_env["ring_inv"]

        resp = c.post("/inventory/crafting/1/smelt", json={
            "inventory_item_id": ring_inv.id,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        mat_names = [m["name"] for m in data["materials_returned"]]
        assert "Ювелирный лом" in mat_names


# ===========================================================================
# 16. Smelt item with socketed gems — gems destroyed
# ===========================================================================

class TestSmeltWithGems:

    def test_smelt_with_gems_destroys_gems(self, gem_env):
        db = gem_env["db"]
        c = gem_env["client"]
        ring_inv = gem_env["ring_inv"]
        gem = gem_env["gem"]

        # Pre-insert gem
        ring_inv.socketed_gems = json.dumps([gem.id, None])
        db.commit()

        resp = c.post("/inventory/crafting/1/smelt", json={
            "inventory_item_id": ring_inv.id,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["gems_destroyed"] == 1


# ===========================================================================
# 17. Smelt equipped item — expect error (must be in inventory)
# ===========================================================================

class TestSmeltEquippedItem:

    def test_smelt_equipped_item_returns_error(self, gem_env):
        """Equipped items cannot be smelted — only inventory items allowed."""
        db = gem_env["db"]
        c = gem_env["client"]
        ring = gem_env["ring"]
        ring_inv = gem_env["ring_inv"]

        # Remove ring from inventory so only the equipment slot has it
        db.delete(ring_inv)
        db.flush()
        eq_slot = _create_equipment_slot(db, 1, "ring", item_id=ring.id)
        db.commit()

        # Smelt endpoint queries character_inventory — equipment slot id won't match
        resp = c.post("/inventory/crafting/1/smelt", json={
            "inventory_item_id": eq_slot.id,
        })

        assert resp.status_code in (400, 404)


# ===========================================================================
# 18. Smelt non-jewelry — expect 400
# ===========================================================================

class TestSmeltNonJewelry:

    def test_smelt_non_jewelry_returns_400(self, gem_env):
        db = gem_env["db"]
        c = gem_env["client"]

        sword = _create_item(db, 60, "Большой меч", "main_weapon", max_stack=1)
        sword_inv = _add_inventory(db, 1, sword.id, 1)
        db.commit()

        resp = c.post("/inventory/crafting/1/smelt", json={
            "inventory_item_id": sword_inv.id,
        })

        assert resp.status_code == 400
        assert "украшен" in resp.json()["detail"].lower()


# ===========================================================================
# 19. Socket-info returns correct data
# ===========================================================================

class TestSocketInfo:

    def test_socket_info_returns_correct_data(self, gem_env):
        db = gem_env["db"]
        c = gem_env["client"]
        ring_inv = gem_env["ring_inv"]
        gem = gem_env["gem"]

        # Pre-insert gem in slot 0
        ring_inv.socketed_gems = json.dumps([gem.id, None])
        db.commit()

        resp = c.get(f"/inventory/crafting/1/socket-info/{ring_inv.id}?source=inventory")

        assert resp.status_code == 200
        data = resp.json()
        assert data["item_name"] == "Золотое кольцо"
        assert data["socket_count"] == 2
        assert len(data["slots"]) == 2
        assert data["slots"][0]["gem_item_id"] == gem.id
        assert data["slots"][0]["gem_name"] == "Рубин"
        assert data["slots"][1]["gem_item_id"] is None

        # Available gems should include the gem in inventory
        assert len(data["available_gems"]) >= 1
        gem_names = [g["name"] for g in data["available_gems"]]
        assert "Рубин" in gem_names


# ===========================================================================
# 20. Smelt-info returns correct materials preview
# ===========================================================================

class TestSmeltInfo:

    def test_smelt_info_with_recipe(self, gem_env):
        db = gem_env["db"]
        c = gem_env["client"]
        ring = gem_env["ring"]
        ring_inv = gem_env["ring_inv"]
        mat1 = gem_env["mat1"]
        mat2 = gem_env["mat2"]

        _create_recipe(db, 2, gem_env["profession"].id, ring.id,
                       [(mat1.id, 6), (mat2.id, 3)])
        db.commit()

        resp = c.get(f"/inventory/crafting/1/smelt-info/{ring_inv.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["item_name"] == "Золотое кольцо"
        assert data["has_recipe"] is True
        assert len(data["ingredients"]) == 2

        ing_dict = {i["name"]: i["quantity"] for i in data["ingredients"]}
        assert ing_dict["Золотой слиток"] == 3  # max(1, 6//2)
        assert ing_dict["Серебряный слиток"] == 1  # max(1, 3//2)

    def test_smelt_info_no_recipe(self, gem_env):
        c = gem_env["client"]
        ring_inv = gem_env["ring_inv"]

        resp = c.get(f"/inventory/crafting/1/smelt-info/{ring_inv.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["has_recipe"] is False
        ing_names = [i["name"] for i in data["ingredients"]]
        assert "Ювелирный лом" in ing_names

    def test_smelt_info_shows_gems_warning(self, gem_env):
        db = gem_env["db"]
        c = gem_env["client"]
        ring_inv = gem_env["ring_inv"]
        gem = gem_env["gem"]

        ring_inv.socketed_gems = json.dumps([gem.id, None])
        db.commit()

        resp = c.get(f"/inventory/crafting/1/smelt-info/{ring_inv.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["has_gems"] is True
        assert data["gem_count"] == 1


# ===========================================================================
# 21. Equip item with socketed gems — verify gems travel to equipment
# ===========================================================================

class TestEquipWithGems:

    def test_equip_item_with_gems_copies_socketed_gems(self, gem_env):
        """Equip ring with gems. Verify socketed_gems appear on equipment_slots."""
        db = gem_env["db"]
        c = gem_env["client"]
        ring_inv = gem_env["ring_inv"]
        ring = gem_env["ring"]
        gem = gem_env["gem"]

        # Pre-insert gem into the inventory row's socketed_gems
        ring_inv.socketed_gems = json.dumps([gem.id, None])
        # Create empty ring equipment slot
        eq_slot = _create_equipment_slot(db, 1, "ring", item_id=None)
        db.commit()

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            # equip endpoint takes items.id, not inventory row id
            resp = c.post("/inventory/1/equip", json={"item_id": ring.id})

        assert resp.status_code == 200

        # Verify equipment slot has socketed_gems
        db.expire_all()
        slot = db.query(models.EquipmentSlot).filter(
            models.EquipmentSlot.character_id == 1,
            models.EquipmentSlot.slot_type == "ring",
            models.EquipmentSlot.item_id.isnot(None),
        ).first()
        assert slot is not None
        socketed = json.loads(slot.socketed_gems) if slot.socketed_gems else []
        assert gem.id in socketed


# ===========================================================================
# 22. Unequip item with socketed gems — verify gems travel to inventory
# ===========================================================================

class TestUnequipWithGems:

    def test_unequip_item_with_gems_copies_socketed_gems(self, gem_env):
        """Unequip ring with gems. Verify socketed_gems appear on inventory row."""
        db = gem_env["db"]
        c = gem_env["client"]
        ring = gem_env["ring"]
        gem = gem_env["gem"]

        eq_slot = _create_equipment_slot(db, 1, "ring", item_id=ring.id,
                                          socketed_gems=[gem.id, None])
        db.commit()

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            # unequip endpoint takes slot_type as query param
            resp = c.post("/inventory/1/unequip?slot_type=ring")

        assert resp.status_code == 200

        # Verify new inventory row has socketed_gems
        db.expire_all()
        inv = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == 1,
            models.CharacterInventory.item_id == ring.id,
        ).all()
        # Find the one with socketed_gems set
        found = False
        for row in inv:
            if row.socketed_gems:
                socketed = json.loads(row.socketed_gems)
                if gem.id in socketed:
                    found = True
                    break
        assert found, "socketed_gems not found on unequipped inventory row"


# ===========================================================================
# 23. build_modifiers_dict with gems — unit test
# ===========================================================================

class TestBuildModifiersDictWithGems:

    def test_gem_modifiers_included(self, db_session):
        """Verify gem modifiers are included in modifier calculation."""
        _create_characters_table(db_session)

        ring = _create_item(
            db_session, 70, "Тестовое кольцо", "ring", max_stack=1,
            socket_count=2, strength_modifier=5,
        )
        gem1 = _create_item(
            db_session, 71, "Тестовый рубин", "gem", max_stack=99,
            strength_modifier=3, agility_modifier=2,
        )
        gem2 = _create_item(
            db_session, 72, "Тестовый сапфир", "gem", max_stack=99,
            intelligence_modifier=4,
        )
        db_session.commit()

        mods = crud.build_modifiers_dict(ring, gem_items=[gem1, gem2])
        assert mods["strength"] == 8  # 5 (ring) + 3 (gem1)
        assert mods["agility"] == 2  # 0 (ring) + 2 (gem1)
        assert mods["intelligence"] == 4  # 0 (ring) + 4 (gem2)

    def test_gem_modifiers_negated(self, db_session):
        """Verify gem modifiers are negated when negative=True."""
        _create_characters_table(db_session)

        ring = _create_item(
            db_session, 73, "Тестовое кольцо 2", "ring", max_stack=1,
            socket_count=1, strength_modifier=5,
        )
        gem1 = _create_item(
            db_session, 74, "Тестовый рубин 2", "gem", max_stack=99,
            strength_modifier=3,
        )
        db_session.commit()

        mods = crud.build_modifiers_dict(ring, negative=True, gem_items=[gem1])
        assert mods["strength"] == -8  # -(5+3)

    def test_gem_modifiers_with_enhancement(self, db_session):
        """Verify gem + enhancement bonuses stack correctly."""
        _create_characters_table(db_session)

        ring = _create_item(
            db_session, 75, "Тестовое кольцо 3", "ring", max_stack=1,
            socket_count=1, strength_modifier=5,
        )
        gem1 = _create_item(
            db_session, 76, "Тестовый рубин 3", "gem", max_stack=99,
            strength_modifier=3,
        )
        db_session.commit()

        enh = {"strength_modifier": 2}
        mods = crud.build_modifiers_dict(ring, enhancement_bonuses=enh, gem_items=[gem1])
        # 5 (base) + 2 (enhancement: 2*1) + 3 (gem) = 10
        assert mods["strength"] == 10


# ===========================================================================
# 24. Security — no auth (401), wrong character (403)
# ===========================================================================

class TestGemSecurity:

    def test_insert_gem_no_auth_401(self, client):
        resp = client.post("/inventory/crafting/1/insert-gem", json={
            "item_row_id": 1, "source": "inventory", "slot_index": 0,
            "gem_inventory_id": 1,
        })
        assert resp.status_code == 401

    def test_extract_gem_no_auth_401(self, client):
        resp = client.post("/inventory/crafting/1/extract-gem", json={
            "item_row_id": 1, "source": "inventory", "slot_index": 0,
        })
        assert resp.status_code == 401

    def test_socket_info_no_auth_401(self, client):
        resp = client.get("/inventory/crafting/1/socket-info/1?source=inventory")
        assert resp.status_code == 401

    def test_smelt_no_auth_401(self, client):
        resp = client.post("/inventory/crafting/1/smelt", json={
            "inventory_item_id": 1,
        })
        assert resp.status_code == 401

    def test_smelt_info_no_auth_401(self, client):
        resp = client.get("/inventory/crafting/1/smelt-info/1")
        assert resp.status_code == 401

    def test_insert_gem_wrong_character_403(self, gem_env):
        db = gem_env["db"]
        c = gem_env["client"]

        _insert_character(db, 2, user_id=999, name="OtherPlayer")
        db.commit()

        resp = c.post("/inventory/crafting/2/insert-gem", json={
            "item_row_id": 1, "source": "inventory", "slot_index": 0,
            "gem_inventory_id": 1,
        })
        assert resp.status_code == 403

    def test_extract_gem_wrong_character_403(self, gem_env):
        db = gem_env["db"]
        c = gem_env["client"]

        _insert_character(db, 2, user_id=999, name="OtherPlayer")
        db.commit()

        resp = c.post("/inventory/crafting/2/extract-gem", json={
            "item_row_id": 1, "source": "inventory", "slot_index": 0,
        })
        assert resp.status_code == 403

    def test_smelt_wrong_character_403(self, gem_env):
        db = gem_env["db"]
        c = gem_env["client"]

        _insert_character(db, 2, user_id=999, name="OtherPlayer")
        db.commit()

        resp = c.post("/inventory/crafting/2/smelt", json={
            "inventory_item_id": 1,
        })
        assert resp.status_code == 403


# ===========================================================================
# 25. XP awarded for insert/extract/smelt
# ===========================================================================

class TestGemXPAwarded:

    def test_xp_awarded_on_insert(self, gem_env):
        c = gem_env["client"]
        ring_inv = gem_env["ring_inv"]
        gem_inv = gem_env["gem_inv"]

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/insert-gem", json={
                "item_row_id": ring_inv.id,
                "source": "inventory",
                "slot_index": 0,
                "gem_inventory_id": gem_inv.id,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["xp_earned"] == 10
        assert data["new_total_xp"] == 10

    def test_xp_awarded_on_extract(self, gem_env):
        db = gem_env["db"]
        c = gem_env["client"]
        ring_inv = gem_env["ring_inv"]
        gem = gem_env["gem"]

        ring_inv.socketed_gems = json.dumps([gem.id, None])
        db.commit()

        with patch("main.random.random", return_value=0.01), \
             patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/extract-gem", json={
                "item_row_id": ring_inv.id,
                "source": "inventory",
                "slot_index": 0,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["xp_earned"] == 10

    def test_xp_awarded_on_smelt(self, gem_env):
        c = gem_env["client"]
        ring_inv = gem_env["ring_inv"]

        resp = c.post("/inventory/crafting/1/smelt", json={
            "inventory_item_id": ring_inv.id,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["xp_earned"] == 10
