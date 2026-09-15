"""
Tests for FEAT-041 (unequip bug fix, atomicity) and FEAT-149 (shield off-hand).

- Unequip endpoint (no db.begin() error, item returns to inventory, slot cleared)
- FEAT-149: the 'shield' equipment SLOT is removed; later the 'shield' ITEM TYPE
  went too — a shield is an ordinary weapon of a shield kind (buckler/targe/tower_shield)
- Atomicity (flush vs commit in return_item_to_inventory)
"""

import inspect
import pytest
from unittest.mock import patch, AsyncMock

from sqlalchemy import text

import models
import crud
import schemas
from auth_http import get_current_user_via_http, UserRead


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_item(db_session, **overrides):
    """Insert an item into the DB and return it."""
    defaults = dict(
        name="Test Item",
        item_level=1,
        item_type="head",
        item_rarity="common",
        max_stack_size=1,
        is_unique=False,
        description="A test item",
    )
    defaults.update(overrides)
    item = models.Items(**defaults)
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def _create_equipment_slot(db_session, character_id, slot_type, item_id=None, is_enabled=True):
    """Insert an equipment slot and return it."""
    slot = models.EquipmentSlot(
        character_id=character_id,
        slot_type=slot_type,
        item_id=item_id,
        is_enabled=is_enabled,
    )
    db_session.add(slot)
    db_session.commit()
    db_session.refresh(slot)
    return slot


def _create_inventory_entry(db_session, character_id, item_id, quantity=1):
    """Insert an inventory entry and return it."""
    inv = models.CharacterInventory(
        character_id=character_id,
        item_id=item_id,
        quantity=quantity,
    )
    db_session.add(inv)
    db_session.commit()
    db_session.refresh(inv)
    return inv


# ---------------------------------------------------------------------------
# Fixture: authenticated client with characters table
# ---------------------------------------------------------------------------

@pytest.fixture()
def authed_client(client, db_session):
    """Client with auth overridden to user_id=1, plus characters table."""
    from main import app

    db_session.execute(text(
        """CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY,
            user_id INTEGER
        )"""
    ))
    db_session.execute(text("INSERT OR IGNORE INTO characters (id, user_id) VALUES (1, 1)"))
    db_session.commit()

    _user = UserRead(id=1, username="testuser", role="user", permissions=[])
    app.dependency_overrides[get_current_user_via_http] = lambda: _user
    yield client
    app.dependency_overrides.pop(get_current_user_via_http, None)


# ===========================================================================
# TASK 11: Test unequip endpoint
# ===========================================================================


class TestUnequipEndpoint:
    """Tests that the unequip endpoint works correctly after db.begin() removal."""

    def test_unequip_no_db_begin_in_source(self):
        """Verify that unequip_item does NOT call db.begin() (the bug fix)."""
        import main
        source = inspect.getsource(main.unequip_item)
        assert "db.begin()" not in source, (
            "unequip_item must not call db.begin() — this was the root cause of the bug"
        )

    def test_unequip_success_item_returns_to_inventory(self, authed_client, db_session):
        """After unequipping, the item must return to inventory and the slot must be cleared."""
        item = _create_item(db_session, name="Helmet of Testing", item_type="head")
        _create_equipment_slot(db_session, character_id=1, slot_type="head", item_id=item.id)

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = authed_client.post(
                "/inventory/1/unequip",
                params={"slot_type": "head"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["slot_type"] == "head"
        assert data["item_id"] is None, "Slot must be cleared after unequip"

        # Verify item appeared in inventory
        inv = db_session.query(models.CharacterInventory).filter_by(
            character_id=1, item_id=item.id
        ).first()
        assert inv is not None, "Item must be returned to inventory after unequip"
        assert inv.quantity == 1

    def test_unequip_empty_slot_returns_404(self, authed_client, db_session):
        """Unequipping an empty slot must return 404."""
        _create_equipment_slot(db_session, character_id=1, slot_type="head", item_id=None)

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = authed_client.post(
                "/inventory/1/unequip",
                params={"slot_type": "head"},
            )

        assert response.status_code == 404
        assert "Слот пуст" in response.json()["detail"]

    def test_unequip_nonexistent_slot_returns_404(self, authed_client, db_session):
        """Unequipping a slot that doesn't exist must return 404."""
        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = authed_client.post(
                "/inventory/1/unequip",
                params={"slot_type": "nonexistent_slot"},
            )

        assert response.status_code == 404

    def test_unequip_calls_apply_modifiers_negative(self, authed_client, db_session):
        """Unequip must call apply_modifiers with negative modifiers."""
        item = _create_item(
            db_session,
            name="Str Helmet",
            item_type="head",
            strength_modifier=5,
        )
        _create_equipment_slot(db_session, character_id=1, slot_type="head", item_id=item.id)

        mock_apply = AsyncMock()
        with patch("main.apply_modifiers_in_attributes_service", mock_apply):
            response = authed_client.post(
                "/inventory/1/unequip",
                params={"slot_type": "head"},
            )

        assert response.status_code == 200
        mock_apply.assert_called_once()
        call_args = mock_apply.call_args
        # First positional arg is character_id, second is modifiers dict
        assert call_args[0][0] == 1
        assert call_args[0][1]["strength"] == -5

    def test_unequip_stackable_item_stacks_in_inventory(self, authed_client, db_session):
        """When unequipping a stackable item and a partial stack exists,
        it should stack into the existing inventory slot."""
        item = _create_item(
            db_session,
            name="Test Consumable",
            item_type="consumable",
            max_stack_size=20,
        )
        # Item is in a fast slot
        _create_equipment_slot(db_session, character_id=1, slot_type="fast_slot_1",
                               item_id=item.id, is_enabled=True)
        # Existing partial stack in inventory
        inv = _create_inventory_entry(db_session, character_id=1, item_id=item.id, quantity=5)

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = authed_client.post(
                "/inventory/1/unequip",
                params={"slot_type": "fast_slot_1"},
            )

        assert response.status_code == 200
        db_session.refresh(inv)
        assert inv.quantity == 6, "Stackable item should be added to existing stack"


# ===========================================================================
# FEAT-149: Shield slot removed — shields equip into the off-hand slot
# ===========================================================================

# The 9 equipment slots every character gets (shield slot removed in FEAT-149)
DEFAULT_EQUIPMENT_SLOT_TYPES = [
    'head', 'body', 'cloak', 'belt', 'ring', 'necklace', 'bracelet',
    'main_weapon', 'additional_weapons',
]


class TestShieldOffhand:
    """FEAT-149 removed the 'shield' equipment SLOT; the balance revision after it
    removed the 'shield' item TYPE too. A shield is now a weapon item
    of a shield kind and equips into the off-hand slot."""

    # --- Item type is gone, subclass replaces it ---

    def test_shield_item_type_removed_from_schemas(self):
        assert not hasattr(schemas.ItemType, "shield")

    def test_shield_item_type_removed_from_items_model_enum(self):
        # In the test environment enums are patched to String, so check source.
        source = inspect.getsource(models)
        items_idx = source.index("class Items")
        next_class = source.find("class ", items_idx + 1)
        items_source = source[items_idx:next_class if next_class != -1 else len(source)]
        item_type_def = items_source[
            items_source.index("item_type = Column"):items_source.index("blueprint_recipe_id")
        ]
        assert "'shield'" not in item_type_def
        assert "'tower_shield'" in source, "weapon kinds must include shields"

    def test_shield_weapon_kinds_exist(self):
        assert schemas.WEAPON_KIND_CATEGORY["buckler"] == "shield"
        assert schemas.WEAPON_KIND_CATEGORY["targe"] == "shield"
        assert schemas.WEAPON_KIND_CATEGORY["tower_shield"] == "shield"

    def test_shield_leftovers_gone_from_type_sets(self):
        assert "shield" not in crud.SHARPENABLE_TYPES
        assert "shield" not in crud.SOCKETABLE_TYPES
        assert "weapon" in crud.SHARPENABLE_TYPES
        assert "weapon" in crud.SOCKETABLE_TYPES

    # --- Slot type is gone ---

    def test_shield_slot_absent_from_equipment_slot_model_enum(self):
        """'shield' must NOT appear in EquipmentSlot.slot_type column definition."""
        source = inspect.getsource(models)
        es_idx = source.index("class EquipmentSlot")
        next_class = source.find("class ", es_idx + 1)
        es_source = source[es_idx:next_class if next_class != -1 else len(source)]
        assert "'shield'" not in es_source, (
            "models.py must not include 'shield' in EquipmentSlot.slot_type Enum"
        )

    def test_create_default_equipment_slots_has_no_shield(self, db_session):
        """create_default_equipment_slots must create 9 equipment slots
        (no shield) + 10 fast slots."""
        slots = crud.create_default_equipment_slots(db_session, character_id=99)

        slot_types = [s.slot_type for s in slots]
        assert "shield" not in slot_types, "Shield slot must no longer be created"

        equip_types = [t for t in slot_types if not t.startswith("fast_slot_")]
        assert sorted(equip_types) == sorted(DEFAULT_EQUIPMENT_SLOT_TYPES)
        assert len(equip_types) == 9

        fast_types = [t for t in slot_types if t.startswith("fast_slot_")]
        assert len(fast_types) == 10

    def test_npc_equipment_slots_constant_has_no_shield(self):
        """NPC_EQUIPMENT_SLOTS must not contain the removed shield slot."""
        assert "shield" not in crud.NPC_EQUIPMENT_SLOTS

    # --- crud.is_item_compatible_with_slot ---

    def test_old_shield_type_no_longer_equips(self):
        assert crud.is_item_compatible_with_slot("shield", "additional_weapons") is False
        assert crud.is_item_compatible_with_slot("shield", "shield") is False

    def test_offhand_weapon_still_compatible_with_offhand_slot(self):
        assert crud.is_item_compatible_with_slot(
            "weapon", "additional_weapons"
        ) is True

    # Hand choice for weapons lives in main._pick_weapon_slot (see test_equipment_rules.py)

    # --- Full equip/unequip cycle for shield via endpoints ---

    def test_equip_shield_lands_in_offhand_slot(self, authed_client, db_session):
        item = _create_item(
            db_session, name="Tower Shield",
            item_type="weapon", weapon_subclass="buckler",
        )
        _create_equipment_slot(db_session, character_id=1, slot_type="additional_weapons")
        _create_inventory_entry(db_session, character_id=1, item_id=item.id, quantity=1)

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = authed_client.post("/inventory/1/equip", json={"item_id": item.id})

        assert response.status_code == 200
        data = response.json()
        assert data["slot_type"] == "additional_weapons"
        assert data["item_id"] == item.id

        inv = db_session.query(models.CharacterInventory).filter_by(
            character_id=1, item_id=item.id
        ).first()
        assert inv is None, "Equipped shield must be removed from inventory"

    def test_equip_shield_when_offhand_occupied_swaps_gracefully(self, authed_client, db_session):
        weapon = _create_item(db_session, name="Off-hand Dagger", item_type="weapon")
        shield = _create_item(
            db_session, name="Round Shield",
            item_type="weapon", weapon_subclass="buckler",
        )
        _create_equipment_slot(
            db_session, character_id=1, slot_type="additional_weapons", item_id=weapon.id
        )
        _create_inventory_entry(db_session, character_id=1, item_id=shield.id, quantity=1)

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = authed_client.post("/inventory/1/equip", json={"item_id": shield.id})

        assert response.status_code == 200
        data = response.json()
        assert data["slot_type"] == "additional_weapons"
        assert data["item_id"] == shield.id

        inv = db_session.query(models.CharacterInventory).filter_by(
            character_id=1, item_id=weapon.id
        ).first()
        assert inv is not None, "Displaced off-hand item must return to inventory"
        assert inv.quantity == 1

    def test_unequip_shield_from_offhand_preserves_enhancement(self, authed_client, db_session):
        item = _create_item(
            db_session, name="Buckler", item_type="weapon",
            weapon_subclass="buckler", max_durability=100,
        )
        slot = _create_equipment_slot(
            db_session, character_id=1, slot_type="additional_weapons", item_id=item.id
        )
        slot.enhancement_points_spent = 3
        slot.current_durability = 42
        db_session.commit()

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = authed_client.post(
                "/inventory/1/unequip", params={"slot_type": "additional_weapons"},
            )

        assert response.status_code == 200
        assert response.json()["item_id"] is None, "Slot must be cleared after unequip"

        inv = db_session.query(models.CharacterInventory).filter_by(
            character_id=1, item_id=item.id
        ).first()
        assert inv is not None, "Shield must return to inventory after unequip"
        assert inv.enhancement_points_spent == 3, "Enhancement must be preserved"
        assert inv.current_durability == 42, "Durability must be preserved"

    def test_unequip_removed_shield_slot_returns_404(self, authed_client, db_session):
        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = authed_client.post("/inventory/1/unequip", params={"slot_type": "shield"})

        assert response.status_code == 404

    # --- NPC admin equip ---

    def test_admin_equip_npc_rejects_shield_slot(self, db_session):
        from fastapi import HTTPException

        item = _create_item(
            db_session, name="NPC Shield",
            item_type="weapon", weapon_subclass="buckler",
        )

        with pytest.raises(HTTPException) as exc_info:
            crud.admin_equip_npc_item(
                db_session, character_id=100, slot_type="shield", item_id=item.id
            )

        assert exc_info.value.status_code == 400
        assert "Недопустимый тип слота" in exc_info.value.detail


class TestShieldEquipSecurity:
    """Security: equip endpoint must keep rejecting unauthenticated and
    foreign-character requests (FEAT-149 changes nothing about auth)."""

    def test_equip_without_token_returns_401(self, client, db_session):
        """Equip without Authorization header must return 401."""
        response = client.post("/inventory/1/equip", json={"item_id": 1})
        assert response.status_code == 401

    def test_equip_foreign_character_returns_403(self, authed_client, db_session):
        """An authenticated user must not equip items on another user's character."""
        # Character 2 belongs to user 2; authed_client is user 1.
        db_session.execute(text(
            "INSERT OR IGNORE INTO characters (id, user_id) VALUES (2, 2)"
        ))
        db_session.commit()
        shield = _create_item(db_session, name="Foreign Shield", item_type="shield")

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = authed_client.post(
                "/inventory/2/equip",
                json={"item_id": shield.id},
            )

        assert response.status_code == 403


# ===========================================================================
# TASK 13: Test atomicity (flush vs commit)
# ===========================================================================


class TestAtomicity:
    """Tests that return_item_to_inventory uses flush (not commit)
    so the caller controls the transaction boundary."""

    def test_return_item_to_inventory_uses_flush_not_commit(self):
        """The function must use db.flush(), not db.commit()."""
        source = inspect.getsource(crud.return_item_to_inventory)
        assert "db.flush()" in source, (
            "return_item_to_inventory must use db.flush()"
        )
        assert "db.commit()" not in source, (
            "return_item_to_inventory must NOT use db.commit() — "
            "the caller controls the transaction boundary"
        )

    def test_find_equipment_slot_uses_flush_not_commit(self):
        """find_equipment_slot_for_item must use db.flush(), not db.commit()."""
        source = inspect.getsource(crud.find_equipment_slot_for_item)
        assert "db.flush()" in source, (
            "find_equipment_slot_for_item must use db.flush()"
        )
        assert "db.commit()" not in source, (
            "find_equipment_slot_for_item must NOT use db.commit()"
        )

    def test_return_item_to_inventory_rollback_reverts_changes(self, db_session):
        """If the caller rolls back after return_item_to_inventory,
        the inventory changes must also be reverted (proving flush, not commit)."""
        item = _create_item(db_session, name="Rollback Sword", item_type="weapon")

        # Start a clean state — no inventory for character 2
        assert db_session.query(models.CharacterInventory).filter_by(
            character_id=2, item_id=item.id
        ).first() is None

        # Call return_item_to_inventory (uses flush internally)
        crud.return_item_to_inventory(db_session, character_id=2, item_obj=item)

        # The item should be visible in the session (flushed to DB)
        pending = db_session.query(models.CharacterInventory).filter_by(
            character_id=2, item_id=item.id
        ).first()
        assert pending is not None, "Flushed item should be visible in the same session"
        assert pending.quantity == 1

        # Now rollback — this simulates a failure in a later step
        db_session.rollback()

        # After rollback, the inventory entry must be gone
        reverted = db_session.query(models.CharacterInventory).filter_by(
            character_id=2, item_id=item.id
        ).first()
        assert reverted is None, (
            "After rollback, return_item_to_inventory changes must be reverted "
            "(proving it uses flush, not commit)"
        )

    def test_return_item_to_inventory_stacking_rollback(self, db_session):
        """Rollback after return_item_to_inventory with stacking must also revert."""
        item = _create_item(
            db_session, name="Stackable Potion", item_type="consumable", max_stack_size=20
        )
        inv = _create_inventory_entry(db_session, character_id=2, item_id=item.id, quantity=5)

        # Call return_item_to_inventory — should stack (5 -> 6)
        crud.return_item_to_inventory(db_session, character_id=2, item_obj=item)

        # Verify the flush is visible
        db_session.refresh(inv)
        assert inv.quantity == 6

        # Rollback
        db_session.rollback()

        # After rollback, quantity must revert to 5
        db_session.refresh(inv)
        assert inv.quantity == 5, (
            "After rollback, stacking change must be reverted "
            "(proving return_item_to_inventory uses flush, not commit)"
        )
