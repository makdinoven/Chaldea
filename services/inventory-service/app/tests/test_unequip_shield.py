"""
Tests for FEAT-041: Unequip bug fix, shield support, and atomicity.

Task 11: Test unequip endpoint (no db.begin() error, item returns to inventory, slot cleared)
Task 12: Test shield support (slot creation, compatibility, find_equipment_slot_for_item)
Task 13: Test atomicity (flush vs commit in return_item_to_inventory)
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
# TASK 12: Test shield support
# ===========================================================================


class TestShieldSupport:
    """Tests for shield item type and equipment slot support."""

    # --- Schema validation ---

    def test_shield_in_item_type_enum(self):
        """Shield must be a valid ItemType in Pydantic schemas."""
        assert hasattr(schemas.ItemType, "shield")
        assert schemas.ItemType.shield.value == "shield"

    # --- Model validation ---

    def test_shield_in_items_model_enum(self):
        """Shield must be present in Items.item_type column definition."""
        # Check the model source references 'shield'
        col = models.Items.__table__.columns["item_type"]
        # In test environment, enums are patched to String, so check source
        source = inspect.getsource(models)
        assert "'shield'" in source, "models.py must include 'shield' in Items.item_type Enum"

    def test_shield_in_equipment_slot_model_enum(self):
        """Shield must be present in EquipmentSlot.slot_type column definition."""
        source = inspect.getsource(models)
        # Check that EquipmentSlot slot_type definition contains 'shield'
        # Find the EquipmentSlot class section
        es_idx = source.index("class EquipmentSlot")
        es_source = source[es_idx:]
        assert "'shield'" in es_source, (
            "models.py must include 'shield' in EquipmentSlot.slot_type Enum"
        )

    # --- crud.create_default_equipment_slots ---

    def test_create_default_equipment_slots_includes_shield(self, db_session):
        """create_default_equipment_slots must create a shield slot."""
        slots = crud.create_default_equipment_slots(db_session, character_id=99)

        slot_types = [s.slot_type for s in slots]
        assert "shield" in slot_types, "Default equipment slots must include 'shield'"

    def test_shield_slot_is_enabled_by_default(self, db_session):
        """The shield slot must be enabled (is_enabled=True) by default."""
        slots = crud.create_default_equipment_slots(db_session, character_id=99)

        shield_slot = [s for s in slots if s.slot_type == "shield"][0]
        assert shield_slot.is_enabled is True, "Shield slot must be enabled by default"

    # --- crud.find_equipment_slot_for_item ---

    def test_find_equipment_slot_for_shield_item(self, db_session):
        """find_equipment_slot_for_item must return the shield slot for a shield item."""
        item = _create_item(db_session, name="Iron Shield", item_type="shield")
        _create_equipment_slot(db_session, character_id=1, slot_type="shield")

        slot = crud.find_equipment_slot_for_item(db_session, character_id=1, item_obj=item)
        assert slot is not None, "Must find a shield slot for a shield item"
        assert slot.slot_type == "shield"

    def test_find_equipment_slot_shield_in_fixed_dict(self):
        """The fixed dict in find_equipment_slot_for_item must contain 'shield'."""
        source = inspect.getsource(crud.find_equipment_slot_for_item)
        assert "'shield'" in source, (
            "find_equipment_slot_for_item must include 'shield' in the fixed dict"
        )

    # --- crud.is_item_compatible_with_slot ---

    def test_shield_compatible_with_shield_slot(self):
        """is_item_compatible_with_slot must return True for shield in shield slot."""
        assert crud.is_item_compatible_with_slot("shield", "shield") is True

    def test_shield_not_compatible_with_head_slot(self):
        """Shield item must not be compatible with non-shield slots."""
        assert crud.is_item_compatible_with_slot("shield", "head") is False

    def test_head_not_compatible_with_shield_slot(self):
        """Non-shield items must not be compatible with shield slot."""
        assert crud.is_item_compatible_with_slot("head", "shield") is False

    # --- Full equip/unequip cycle for shield ---

    def test_equip_shield_item_via_endpoint(self, authed_client, db_session):
        """A shield item must be equippable via the equip endpoint."""
        item = _create_item(db_session, name="Tower Shield", item_type="shield")
        _create_equipment_slot(db_session, character_id=1, slot_type="shield")
        _create_inventory_entry(db_session, character_id=1, item_id=item.id, quantity=1)

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = authed_client.post(
                "/inventory/1/equip",
                json={"item_id": item.id},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["slot_type"] == "shield"
        assert data["item_id"] == item.id

    def test_unequip_shield_item_via_endpoint(self, authed_client, db_session):
        """A shield item must be unequippable via the unequip endpoint."""
        item = _create_item(db_session, name="Buckler", item_type="shield")
        _create_equipment_slot(db_session, character_id=1, slot_type="shield", item_id=item.id)

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = authed_client.post(
                "/inventory/1/unequip",
                params={"slot_type": "shield"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["item_id"] is None

        # Verify item returned to inventory
        inv = db_session.query(models.CharacterInventory).filter_by(
            character_id=1, item_id=item.id
        ).first()
        assert inv is not None
        assert inv.quantity == 1


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
        item = _create_item(db_session, name="Rollback Sword", item_type="main_weapon")

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
