"""
Task 7 — QA tests for FEAT-086: Jeweler gems and sockets.

Covers: insert-gem, extract-gem, socket-info endpoints,
equip/unequip with gems, build_modifiers_dict with gems, security.
FEAT-165: smelting removed; anyone may insert; no profession XP for sockets.
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
            character_id INTEGER NOT NULL,
            dropped_out_at DATETIME
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
        assert "xp_earned" not in data

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
# 2. Non-jeweler inserts — allowed since FEAT-165
# ===========================================================================

class TestInsertGemNotJeweler:

    def test_non_jeweler_can_insert(self, gem_env):
        db = gem_env["db"]
        c = gem_env["client"]
        ring_inv = gem_env["ring_inv"]
        gem_inv = gem_env["gem_inv"]

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

        assert resp.status_code == 200, resp.text
        db.expire_all()
        inv = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == ring_inv.id
        ).first()
        assert json.loads(inv.socketed_gems)[0] == gem_env["gem"].id


# ===========================================================================
# 3. Item is not jewelry — expect 400
# ===========================================================================

class TestInsertGemWrongItemType:

    def test_insert_into_non_jewelry_returns_400(self, gem_env):
        db = gem_env["db"]
        c = gem_env["client"]
        gem_inv = gem_env["gem_inv"]

        sword = _create_item(db, 50, "Меч", "weapon", max_stack=1, socket_count=2)
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
        assert "руну" in resp.json()["detail"].lower()


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
        assert data["insertable_type"] == "gem"
        assert data["can_insert"] is True
        assert data["can_extract"] is True  # jeweler
        assert data["extract_preservation_chance"] == 10


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

# ===========================================================================
# 25. No profession XP for insert/extract (FEAT-165)
# ===========================================================================

class TestGemXPAwarded:

    def _xp(self, db):
        db.expire_all()
        return db.query(models.CharacterProfession).filter(
            models.CharacterProfession.character_id == 1
        ).first().experience

    def test_no_xp_on_insert(self, gem_env):
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
        assert "xp_earned" not in resp.json()
        assert self._xp(gem_env["db"]) == 0

    def test_no_xp_on_extract(self, gem_env):
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
        assert "xp_earned" not in resp.json()
        assert self._xp(db) == 0


# ===========================================================================
# 26. Runes and belts (FEAT-165): belts take no runes, legacy belt runes can
#     still be extracted by an enchanter; anyone may insert, nobody gets XP
# ===========================================================================

def _row_gems(db, model, row_id):
    db.expire_all()
    row = db.query(model).filter(model.id == row_id).first()
    return json.loads(row.socketed_gems) if row.socketed_gems else []


def _qty(db, row_id):
    db.expire_all()
    row = db.query(models.CharacterInventory).filter(models.CharacterInventory.id == row_id).first()
    return row.quantity if row else 0


@pytest.fixture()
def rune_env(gem_env):
    db = gem_env["db"]
    rune = _create_item(db, 50, "Руна огня", "rune", max_stack=99, strength_modifier=2)
    belt = _create_item(db, 51, "Кожаный пояс", "belt", max_stack=1, socket_count=1)
    cloak = _create_item(db, 52, "Плащ странника", "cloak", max_stack=1, socket_count=1)
    enchanter = _create_profession(db, 2, "Зачарователь", "enchanter")
    _create_rank(db, profession_id=enchanter.id, rank_number=1, name="Ученик")
    rune_inv = _add_inventory(db, 1, rune.id, 3)
    db.commit()
    gem_env.update({"rune": rune, "belt": belt, "cloak": cloak,
                    "enchanter": enchanter, "rune_inv": rune_inv})
    return gem_env


def _set_profession(env, profession_id):
    db = env["db"]
    cp = db.query(models.CharacterProfession).filter(
        models.CharacterProfession.character_id == 1).first()
    cp.profession_id = profession_id
    db.commit()


def _insert(env, row_id, gem_row_id, source="inventory"):
    return env["client"].post("/inventory/crafting/1/insert-gem", json={
        "item_row_id": row_id, "source": source,
        "slot_index": 0, "gem_inventory_id": gem_row_id,
    })


def _extract(env, row_id, slot_index=0):
    return env["client"].post("/inventory/crafting/1/extract-gem", json={
        "item_row_id": row_id, "source": "inventory", "slot_index": slot_index,
    })


class TestRunesAndBelts:

    def test_belt_insert_rejected_and_rune_kept(self, rune_env):
        db = rune_env["db"]
        belt_inv = _add_inventory(db, 1, rune_env["belt"].id, 1)
        db.commit()

        resp = _insert(rune_env, belt_inv.id, rune_env["rune_inv"].id)

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Этот тип предмета не поддерживает руны"
        assert _qty(db, rune_env["rune_inv"].id) == 3
        assert _row_gems(db, models.CharacterInventory, belt_inv.id) == []

    def test_equipped_belt_insert_rejected(self, rune_env):
        db = rune_env["db"]
        slot = _create_equipment_slot(db, 1, "belt", item_id=rune_env["belt"].id)
        db.commit()

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock) as mock_apply:
            resp = _insert(rune_env, slot.id, rune_env["rune_inv"].id, source="equipment")

        assert resp.status_code == 400
        mock_apply.assert_not_awaited()
        assert _qty(db, rune_env["rune_inv"].id) == 3

    def test_socket_count_on_belt_rejected_by_item_validator(self):
        from schemas import ItemCreate
        with pytest.raises(ValueError):
            ItemCreate(name="Пояс", item_level=1, item_type="belt", item_rarity="common",
                       max_stack_size=1, is_unique=False, socket_count=1)

    def test_non_enchanter_inserts_rune_into_cloak(self, rune_env):
        """The jeweler (not an enchanter) inserts a rune — insertion is open to anyone."""
        db = rune_env["db"]
        cloak_inv = _add_inventory(db, 1, rune_env["cloak"].id, 1)
        db.commit()

        resp = _insert(rune_env, cloak_inv.id, rune_env["rune_inv"].id)

        assert resp.status_code == 200, resp.text
        assert "xp_earned" not in resp.json()
        assert _row_gems(db, models.CharacterInventory, cloak_inv.id) == [rune_env["rune"].id]
        assert _qty(db, rune_env["rune_inv"].id) == 2

    def test_character_without_profession_inserts(self, rune_env):
        db = rune_env["db"]
        db.query(models.CharacterProfession).delete()
        cloak_inv = _add_inventory(db, 1, rune_env["cloak"].id, 1)
        db.commit()

        resp = _insert(rune_env, cloak_inv.id, rune_env["rune_inv"].id)

        assert resp.status_code == 200, resp.text
        assert _row_gems(db, models.CharacterInventory, cloak_inv.id) == [rune_env["rune"].id]

    def test_gem_into_cloak_rejected(self, rune_env):
        db = rune_env["db"]
        cloak_inv = _add_inventory(db, 1, rune_env["cloak"].id, 1)
        db.commit()

        resp = _insert(rune_env, cloak_inv.id, rune_env["gem_inv"].id)

        assert resp.status_code == 400
        assert resp.json()["detail"] == "В этот предмет можно вставить только руну"
        assert _qty(db, rune_env["gem_inv"].id) == 5

    def test_rune_into_ring_rejected(self, rune_env):
        resp = _insert(rune_env, rune_env["ring_inv"].id, rune_env["rune_inv"].id)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "В украшение можно вставить только огранку"
        assert _qty(rune_env["db"], rune_env["rune_inv"].id) == 3

    def test_enchanter_extracts_legacy_belt_rune(self, rune_env):
        db = rune_env["db"]
        _set_profession(rune_env, rune_env["enchanter"].id)
        belt_inv = _add_inventory(db, 1, rune_env["belt"].id, 1,
                                  socketed_gems=[rune_env["rune"].id])
        db.commit()

        with patch("main.random.random", return_value=0.01):
            resp = _extract(rune_env, belt_inv.id)

        assert resp.status_code == 200, resp.text
        assert resp.json()["gem_preserved"] is True
        assert "xp_earned" not in resp.json()
        assert _row_gems(db, models.CharacterInventory, belt_inv.id) == [None]
        # the preserved rune went back to the inventory (3 + 1)
        db.expire_all()
        total = sum(r.quantity for r in db.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == 1,
            models.CharacterInventory.item_id == rune_env["rune"].id).all())
        assert total == 4
        cp = db.query(models.CharacterProfession).filter(
            models.CharacterProfession.character_id == 1).first()
        assert cp.experience == 0

    def test_legacy_belt_extract_from_slot_beyond_socket_count(self, rune_env):
        """Legacy rows may hold more runes than the item's current socket_count."""
        db = rune_env["db"]
        _set_profession(rune_env, rune_env["enchanter"].id)
        belt = rune_env["belt"]
        belt.socket_count = 0
        belt_inv = _add_inventory(db, 1, belt.id, 1,
                                  socketed_gems=[None, rune_env["rune"].id])
        db.commit()

        with patch("main.random.random", return_value=0.99):
            resp = _extract(rune_env, belt_inv.id, slot_index=1)

        assert resp.status_code == 200, resp.text
        assert resp.json()["gem_preserved"] is False
        assert _row_gems(db, models.CharacterInventory, belt_inv.id) == [None, None]

    def test_jeweler_cannot_extract_rune(self, rune_env):
        db = rune_env["db"]
        cloak_inv = _add_inventory(db, 1, rune_env["cloak"].id, 1,
                                   socketed_gems=[rune_env["rune"].id])
        db.commit()

        resp = _extract(rune_env, cloak_inv.id)

        assert resp.status_code == 400
        assert _row_gems(db, models.CharacterInventory, cloak_inv.id) == [rune_env["rune"].id]

    def test_enchanter_cannot_extract_gem(self, rune_env):
        db = rune_env["db"]
        _set_profession(rune_env, rune_env["enchanter"].id)
        ring_inv = rune_env["ring_inv"]
        ring_inv.socketed_gems = json.dumps([rune_env["gem"].id, None])
        db.commit()

        resp = _extract(rune_env, ring_inv.id)

        assert resp.status_code == 400
        assert _row_gems(db, models.CharacterInventory, ring_inv.id) == [rune_env["gem"].id, None]

    @pytest.mark.parametrize("slug", ["blacksmith", "alchemist", "cook", "scholar"])
    def test_other_professions_cannot_extract(self, rune_env, slug):
        db = rune_env["db"]
        other = _create_profession(db, 9, f"Проф {slug}", slug)
        _set_profession(rune_env, other.id)
        ring_inv = rune_env["ring_inv"]
        ring_inv.socketed_gems = json.dumps([rune_env["gem"].id, None])
        db.commit()

        resp = _extract(rune_env, ring_inv.id)

        assert resp.status_code == 400
        assert _row_gems(db, models.CharacterInventory, ring_inv.id) == [rune_env["gem"].id, None]

    def test_extract_without_profession(self, rune_env):
        db = rune_env["db"]
        db.query(models.CharacterProfession).delete()
        ring_inv = rune_env["ring_inv"]
        ring_inv.socketed_gems = json.dumps([rune_env["gem"].id, None])
        db.commit()

        resp = _extract(rune_env, ring_inv.id)

        assert resp.status_code == 400
        assert _row_gems(db, models.CharacterInventory, ring_inv.id) == [rune_env["gem"].id, None]


class TestSocketInfoFlags:

    def _info(self, env, row_id, source="inventory"):
        return env["client"].get(f"/inventory/crafting/1/socket-info/{row_id}?source={source}")

    def test_ring_for_jeweler(self, rune_env):
        data = self._info(rune_env, rune_env["ring_inv"].id).json()
        assert data["insertable_type"] == "gem"
        assert data["can_insert"] is True
        assert data["can_extract"] is True
        assert data["extract_preservation_chance"] == 10
        assert [g["item_id"] for g in data["available_gems"]] == [rune_env["gem"].id]

    def test_cloak_for_jeweler(self, rune_env):
        db = rune_env["db"]
        cloak_inv = _add_inventory(db, 1, rune_env["cloak"].id, 1)
        db.commit()
        data = self._info(rune_env, cloak_inv.id).json()
        assert data["insertable_type"] == "rune"
        assert data["can_insert"] is True
        assert data["can_extract"] is False
        assert data["extract_preservation_chance"] is None
        assert [g["item_id"] for g in data["available_gems"]] == [rune_env["rune"].id]

    def test_empty_belt_is_400(self, rune_env):
        db = rune_env["db"]
        belt_inv = _add_inventory(db, 1, rune_env["belt"].id, 1)
        db.commit()
        resp = self._info(rune_env, belt_inv.id)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Этот тип предмета не поддерживает руны"

    def test_legacy_belt_with_rune_for_enchanter(self, rune_env):
        db = rune_env["db"]
        _set_profession(rune_env, rune_env["enchanter"].id)
        belt_inv = _add_inventory(db, 1, rune_env["belt"].id, 1,
                                  socketed_gems=[rune_env["rune"].id])
        db.commit()
        data = self._info(rune_env, belt_inv.id).json()
        assert data["insertable_type"] == "rune"
        assert data["can_insert"] is False
        assert data["can_extract"] is True
        assert data["available_gems"] == []
        assert data["slots"][0]["gem_item_id"] == rune_env["rune"].id

    def test_non_socketable_item_400(self, rune_env):
        db = rune_env["db"]
        _create_item(db, 60, "Хлеб", "consumable")
        row = _add_inventory(db, 1, 60, 1)
        db.commit()
        assert self._info(rune_env, row.id).status_code == 400

    def test_socket_info_foreign_character_403(self, rune_env):
        _insert_character(rune_env["db"], 2, user_id=999, name="OtherPlayer")
        resp = rune_env["client"].get("/inventory/crafting/2/socket-info/1?source=inventory")
        assert resp.status_code == 403
