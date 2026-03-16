"""
Tests for crud.return_item_to_inventory() stacking order fix (FEAT-018).

Covers:
- Item returned to inventory with two partial stacks: added to HIGHEST quantity stack first
- Item returned when highest stack is full: goes to next available stack
- Item returned when no existing stacks: creates a new slot
- Item returned when all stacks are full: creates a new slot
"""

import pytest
from models import Items, CharacterInventory
import crud


def _create_item(db_session, **overrides):
    """Helper: insert an item into the DB and return it."""
    defaults = dict(
        name="Test Potion",
        item_level=1,
        item_type="consumable",
        item_rarity="common",
        max_stack_size=20,
        is_unique=False,
        description="A test consumable item",
    )
    defaults.update(overrides)
    item = Items(**defaults)
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


# ── Test 1: Adds to the highest-quantity partial stack ───────────────────


def test_return_item_fills_highest_quantity_stack(db_session):
    """When two partial stacks exist, return_item_to_inventory should add
    the item to the stack with the HIGHEST quantity (not the lowest)."""
    item = _create_item(db_session, name="Healing Potion", max_stack_size=20)

    # Two partial stacks: 5 and 18
    low_stack = CharacterInventory(character_id=1, item_id=item.id, quantity=5)
    high_stack = CharacterInventory(character_id=1, item_id=item.id, quantity=18)
    db_session.add_all([low_stack, high_stack])
    db_session.commit()
    db_session.refresh(low_stack)
    db_session.refresh(high_stack)

    crud.return_item_to_inventory(db_session, character_id=1, item_obj=item)

    db_session.refresh(low_stack)
    db_session.refresh(high_stack)

    # The high stack (18) should become 19; low stack stays at 5
    assert high_stack.quantity == 19
    assert low_stack.quantity == 5


# ── Test 2: Highest stack is full, goes to next available ────────────────


def test_return_item_skips_full_stack_fills_next(db_session):
    """When the highest-quantity stack is full (at max_stack_size),
    the item should go to the next available partial stack."""
    item = _create_item(db_session, name="Mana Potion", max_stack_size=10)

    # Full stack (10/10) and partial stack (7/10)
    full_stack = CharacterInventory(character_id=1, item_id=item.id, quantity=10)
    partial_stack = CharacterInventory(character_id=1, item_id=item.id, quantity=7)
    db_session.add_all([full_stack, partial_stack])
    db_session.commit()
    db_session.refresh(full_stack)
    db_session.refresh(partial_stack)

    crud.return_item_to_inventory(db_session, character_id=1, item_obj=item)

    db_session.refresh(full_stack)
    db_session.refresh(partial_stack)

    # Full stack stays at 10 (filtered out by quantity < max_stack_size)
    # Partial stack (7) becomes 8
    assert full_stack.quantity == 10
    assert partial_stack.quantity == 8


# ── Test 3: No existing stacks — creates new slot ───────────────────────


def test_return_item_no_existing_stacks_creates_new(db_session):
    """When no inventory slots exist for the item, a new slot is created
    with quantity=1."""
    item = _create_item(db_session, name="Energy Potion", max_stack_size=20)

    # No pre-existing inventory for character 1
    crud.return_item_to_inventory(db_session, character_id=1, item_obj=item)

    rows = db_session.query(CharacterInventory).filter_by(
        character_id=1, item_id=item.id
    ).all()

    assert len(rows) == 1
    assert rows[0].quantity == 1


# ── Test 4: All stacks are full — creates new slot ──────────────────────


def test_return_item_all_stacks_full_creates_new(db_session):
    """When all existing stacks are at max_stack_size, a new inventory
    slot is created with quantity=1."""
    item = _create_item(db_session, name="Stamina Potion", max_stack_size=5)

    # Two full stacks
    stack1 = CharacterInventory(character_id=1, item_id=item.id, quantity=5)
    stack2 = CharacterInventory(character_id=1, item_id=item.id, quantity=5)
    db_session.add_all([stack1, stack2])
    db_session.commit()

    crud.return_item_to_inventory(db_session, character_id=1, item_obj=item)

    rows = db_session.query(CharacterInventory).filter_by(
        character_id=1, item_id=item.id
    ).all()
    for r in rows:
        db_session.refresh(r)

    assert len(rows) == 3
    quantities = sorted([r.quantity for r in rows])
    assert quantities == [1, 5, 5]


# ── Test 5: Non-stackable item always creates new slot ──────────────────


def test_return_nonstackable_item_creates_new_slot(db_session):
    """A non-stackable item (max_stack_size=1) should always create a new
    inventory slot, even if other slots for the same item exist."""
    item = _create_item(
        db_session, name="Unique Sword", item_type="main_weapon", max_stack_size=1
    )

    # Pre-existing slot with quantity=1
    existing = CharacterInventory(character_id=1, item_id=item.id, quantity=1)
    db_session.add(existing)
    db_session.commit()

    crud.return_item_to_inventory(db_session, character_id=1, item_obj=item)

    rows = db_session.query(CharacterInventory).filter_by(
        character_id=1, item_id=item.id
    ).all()

    assert len(rows) == 2
    assert all(r.quantity == 1 for r in rows)


# ── Test 6: Multiple partial stacks — highest is chosen ─────────────────


def test_return_item_three_partial_stacks_picks_highest(db_session):
    """With three partial stacks of different quantities, the item is
    added to the one with the highest quantity."""
    item = _create_item(db_session, name="Arrow", item_type="resource", max_stack_size=50)

    stack_low = CharacterInventory(character_id=1, item_id=item.id, quantity=3)
    stack_mid = CharacterInventory(character_id=1, item_id=item.id, quantity=25)
    stack_high = CharacterInventory(character_id=1, item_id=item.id, quantity=40)
    db_session.add_all([stack_low, stack_mid, stack_high])
    db_session.commit()
    db_session.refresh(stack_low)
    db_session.refresh(stack_mid)
    db_session.refresh(stack_high)

    crud.return_item_to_inventory(db_session, character_id=1, item_obj=item)

    db_session.refresh(stack_low)
    db_session.refresh(stack_mid)
    db_session.refresh(stack_high)

    # Only the highest stack (40) should increase to 41
    assert stack_high.quantity == 41
    assert stack_mid.quantity == 25
    assert stack_low.quantity == 3
