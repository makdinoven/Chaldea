"""
Task 19 — QA for Bug #21: Race condition fix in equip endpoint.

Verifies that equip queries use .with_for_update() for row-level locking:
1. CharacterInventory query in equip_item() uses with_for_update().
2. find_equipment_slot_for_item() fixed-slot query uses with_for_update().
3. find_equipment_slot_for_item() fast-slot queries use with_for_update().
4. The equip endpoint works correctly end-to-end (functional test).
"""

import inspect
import textwrap

import pytest


# ---------------------------------------------------------------------------
# Test 1: Verify CharacterInventory query in equip_item uses with_for_update
# ---------------------------------------------------------------------------

def test_equip_item_inventory_query_has_for_update():
    """
    The equip_item endpoint in main.py must query CharacterInventory
    with .with_for_update() to prevent race conditions.
    """
    import main

    source = inspect.getsource(main.equip_item)

    # The inventory query should chain .with_for_update() before .first()
    assert "with_for_update()" in source, (
        "equip_item() must use .with_for_update() on the CharacterInventory query "
        "to prevent race conditions"
    )


# ---------------------------------------------------------------------------
# Test 2: Verify find_equipment_slot_for_item fixed-slot query has for_update
# ---------------------------------------------------------------------------

def test_find_equipment_slot_fixed_has_for_update():
    """
    find_equipment_slot_for_item() must use .with_for_update() when querying
    a fixed equipment slot (head, body, weapon, etc.).
    """
    import crud

    source = inspect.getsource(crud.find_equipment_slot_for_item)

    # Count occurrences of with_for_update — we need at least 3:
    # one for fixed slots, two for fast slots (active + fallback)
    count = source.count("with_for_update()")
    assert count >= 1, (
        "find_equipment_slot_for_item() must use .with_for_update() on the "
        "fixed-slot query to prevent race conditions"
    )


# ---------------------------------------------------------------------------
# Test 3: Verify find_equipment_slot_for_item fast-slot queries have for_update
# ---------------------------------------------------------------------------

def test_find_equipment_slot_fast_slots_have_for_update():
    """
    find_equipment_slot_for_item() must use .with_for_update() on BOTH
    fast-slot queries (active-slot lookup and fallback disabled-slot lookup).
    """
    import crud

    source = inspect.getsource(crud.find_equipment_slot_for_item)

    # We expect at least 3 occurrences total: 1 fixed + 2 fast-slot queries
    count = source.count("with_for_update()")
    assert count >= 3, (
        f"find_equipment_slot_for_item() has only {count} with_for_update() calls, "
        "expected at least 3 (1 fixed slot + 2 fast-slot queries)"
    )


# ---------------------------------------------------------------------------
# Test 4: Verify unequip already uses with_for_update (regression)
# ---------------------------------------------------------------------------

def test_unequip_item_has_for_update():
    """
    The unequip_item endpoint must continue to use .with_for_update()
    on the EquipmentSlot query (this was already correct before the fix).
    """
    import main

    source = inspect.getsource(main.unequip_item)
    assert "with_for_update()" in source, (
        "unequip_item() must retain .with_for_update() on the EquipmentSlot query"
    )


# ---------------------------------------------------------------------------
# Test 5: Functional test — equip item reduces inventory
# ---------------------------------------------------------------------------

def test_equip_item_reduces_inventory(client, db_session):
    """
    Equipping an item must reduce inventory quantity by 1
    and place the item in the appropriate equipment slot.
    """
    import models

    # Create a head-type item
    item = models.Items(
        id=1,
        name="Test Helmet",
        item_level=1,
        item_type="head",
        item_rarity="common",
        max_stack_size=1,
        is_unique=False,
    )
    db_session.add(item)
    db_session.flush()

    # Create inventory entry (character 1 has 1 of this item)
    inv = models.CharacterInventory(character_id=1, item_id=1, quantity=1)
    db_session.add(inv)

    # Create equipment slots for character 1
    slot = models.EquipmentSlot(
        character_id=1, slot_type="head", item_id=None, is_enabled=True
    )
    db_session.add(slot)
    db_session.commit()

    # Mock the external attributes-service call
    from unittest.mock import patch, AsyncMock

    with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
        response = client.post("/inventory/1/equip", json={"item_id": 1})

    assert response.status_code == 200
    data = response.json()
    assert data["item_id"] == 1
    assert data["slot_type"] == "head"

    # Verify inventory was consumed
    remaining = (
        db_session.query(models.CharacterInventory)
        .filter_by(character_id=1, item_id=1)
        .first()
    )
    assert remaining is None, "Inventory entry should be deleted when quantity reaches 0"


# ---------------------------------------------------------------------------
# Test 6: Equip with insufficient inventory fails
# ---------------------------------------------------------------------------

def test_equip_item_insufficient_inventory(client, db_session):
    """
    Equipping an item when inventory quantity is 0 must return 400.
    """
    import models

    # Create item but no inventory entry
    item = models.Items(
        id=2,
        name="Ghost Sword",
        item_level=1,
        item_type="main_weapon",
        item_rarity="common",
        max_stack_size=1,
        is_unique=False,
    )
    db_session.add(item)

    slot = models.EquipmentSlot(
        character_id=1, slot_type="main_weapon", item_id=None, is_enabled=True
    )
    db_session.add(slot)
    db_session.commit()

    from unittest.mock import patch, AsyncMock

    with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
        response = client.post("/inventory/1/equip", json={"item_id": 2})

    assert response.status_code == 400
    assert "Недостаточно" in response.json()["detail"]
