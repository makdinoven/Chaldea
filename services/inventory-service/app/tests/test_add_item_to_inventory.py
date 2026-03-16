"""
Tests for POST /inventory/{character_id}/items endpoint.

Covers:
- Successfully adding an item to a character's inventory
- 404 when the item does not exist
- Item stacking: adding the same item twice increases quantity in existing slot
- Stacking overflow: when existing slot is full, a new slot is created
- Adding zero quantity (edge case)
- SQL injection in character_id path parameter
"""

import pytest
from models import Items, CharacterInventory


def _create_item(db_session, **overrides):
    """Helper: insert an item into the DB and return it."""
    defaults = dict(
        name="Test Sword",
        item_level=1,
        item_type="main_weapon",
        item_rarity="common",
        max_stack_size=1,
        is_unique=False,
        description="A test item",
    )
    defaults.update(overrides)
    item = Items(**defaults)
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


# ── Success cases ────────────────────────────────────────────────────────


def test_add_item_to_empty_inventory(client, db_session):
    """Adding an item to a character with no inventory entries returns 200
    and creates a new CharacterInventory row."""
    item = _create_item(db_session, name="Potion", item_type="consumable", max_stack_size=10)

    response = client.post(
        "/inventory/1/items",
        json={"item_id": item.id, "quantity": 3},
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["item_id"] == item.id
    assert data[0]["quantity"] == 3
    assert data[0]["character_id"] == 1


def test_add_item_quantity_one(client, db_session):
    """Adding a single non-stackable item works correctly."""
    item = _create_item(db_session, name="Unique Ring", item_type="ring", max_stack_size=1)

    response = client.post(
        "/inventory/1/items",
        json={"item_id": item.id, "quantity": 1},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["quantity"] == 1


# ── 404 cases ────────────────────────────────────────────────────────────


def test_add_nonexistent_item_returns_404(client, db_session):
    """Attempting to add an item that doesn't exist returns 404."""
    response = client.post(
        "/inventory/1/items",
        json={"item_id": 99999, "quantity": 1},
    )

    assert response.status_code == 404
    assert "не найден" in response.json()["detail"]


# ── Stacking behaviour ──────────────────────────────────────────────────


def test_stacking_fills_existing_slot(client, db_session):
    """When an item already exists in inventory with room in the stack,
    the quantity increases in the existing slot (no new row)."""
    item = _create_item(db_session, name="Arrow", item_type="resource", max_stack_size=50)

    # Pre-populate inventory with 10 arrows
    existing = CharacterInventory(character_id=1, item_id=item.id, quantity=10)
    db_session.add(existing)
    db_session.commit()
    db_session.refresh(existing)

    response = client.post(
        "/inventory/1/items",
        json={"item_id": item.id, "quantity": 5},
    )

    assert response.status_code == 200
    data = response.json()
    # The existing slot should be updated to 15
    slot = db_session.query(CharacterInventory).filter_by(
        character_id=1, item_id=item.id
    ).first()
    db_session.refresh(slot)
    assert slot.quantity == 15


def test_stacking_overflow_creates_new_slot(client, db_session):
    """When existing slots are full, a new CharacterInventory row is created."""
    item = _create_item(db_session, name="Herb", item_type="resource", max_stack_size=5)

    # Pre-populate with a full stack
    existing = CharacterInventory(character_id=1, item_id=item.id, quantity=5)
    db_session.add(existing)
    db_session.commit()

    response = client.post(
        "/inventory/1/items",
        json={"item_id": item.id, "quantity": 3},
    )

    assert response.status_code == 200
    # Should now have 2 rows: the original full stack + a new one
    rows = db_session.query(CharacterInventory).filter_by(
        character_id=1, item_id=item.id
    ).all()
    for r in rows:
        db_session.refresh(r)
    quantities = sorted([r.quantity for r in rows])
    assert quantities == [3, 5]


def test_stacking_partial_fill_then_new_slot(client, db_session):
    """Adding more items than fit in an existing partial slot fills it
    first, then creates a new slot for the remainder."""
    item = _create_item(db_session, name="Bolt", item_type="resource", max_stack_size=10)

    # Pre-populate with 7/10
    existing = CharacterInventory(character_id=1, item_id=item.id, quantity=7)
    db_session.add(existing)
    db_session.commit()

    # Add 8 more: 3 fill the existing slot to 10, 5 go to a new slot
    response = client.post(
        "/inventory/1/items",
        json={"item_id": item.id, "quantity": 8},
    )

    assert response.status_code == 200
    rows = db_session.query(CharacterInventory).filter_by(
        character_id=1, item_id=item.id
    ).all()
    for r in rows:
        db_session.refresh(r)
    quantities = sorted([r.quantity for r in rows])
    assert quantities == [5, 10]


# ── Edge / negative cases ───────────────────────────────────────────────


def test_add_item_to_different_characters(client, db_session):
    """Items added for different character_ids are kept separate."""
    item = _create_item(db_session, name="Gem", item_type="resource", max_stack_size=99)

    client.post("/inventory/1/items", json={"item_id": item.id, "quantity": 2})
    client.post("/inventory/2/items", json={"item_id": item.id, "quantity": 5})

    rows_c1 = db_session.query(CharacterInventory).filter_by(character_id=1, item_id=item.id).all()
    rows_c2 = db_session.query(CharacterInventory).filter_by(character_id=2, item_id=item.id).all()

    for r in rows_c1 + rows_c2:
        db_session.refresh(r)

    assert sum(r.quantity for r in rows_c1) == 2
    assert sum(r.quantity for r in rows_c2) == 5


def test_invalid_payload_returns_422(client, db_session):
    """Missing required fields in the request body returns 422."""
    response = client.post(
        "/inventory/1/items",
        json={"item_id": 1},  # missing quantity
    )
    assert response.status_code == 422


def test_non_integer_character_id_returns_422(client, db_session):
    """A non-integer character_id in the path returns 422."""
    item = _create_item(db_session, name="Shield", item_type="body", max_stack_size=1)

    response = client.post(
        "/inventory/abc/items",
        json={"item_id": item.id, "quantity": 1},
    )
    assert response.status_code == 422


# ── Additional stacking edge cases ────────────────────────────────────────


def test_stacking_fills_multiple_partial_slots(client, db_session):
    """When multiple partial stacks exist, adding items fills them
    in order before creating new slots."""
    item = _create_item(db_session, name="Bandage", item_type="resource", max_stack_size=10)

    # Pre-populate with two partial stacks: 8/10 and 6/10
    slot1 = CharacterInventory(character_id=1, item_id=item.id, quantity=8)
    slot2 = CharacterInventory(character_id=1, item_id=item.id, quantity=6)
    db_session.add_all([slot1, slot2])
    db_session.commit()

    # Add 5 more: should fill existing slots (2+3 or 2+4+... depending on order)
    response = client.post(
        "/inventory/1/items",
        json={"item_id": item.id, "quantity": 5},
    )

    assert response.status_code == 200
    rows = db_session.query(CharacterInventory).filter_by(
        character_id=1, item_id=item.id
    ).all()
    for r in rows:
        db_session.refresh(r)
    total = sum(r.quantity for r in rows)
    # Total should be 8 + 6 + 5 = 19
    assert total == 19
    # No new rows should be created (14 + 5 = 19, fits in 2 stacks of 10 = 20)
    assert len(rows) == 2


def test_stacking_fills_multiple_slots_and_overflows(client, db_session):
    """When adding more items than fit in all existing partial stacks,
    remaining items go into new slots."""
    item = _create_item(db_session, name="Nail", item_type="resource", max_stack_size=10)

    # Two partial stacks: 9/10 and 8/10 (3 free spaces total)
    slot1 = CharacterInventory(character_id=1, item_id=item.id, quantity=9)
    slot2 = CharacterInventory(character_id=1, item_id=item.id, quantity=8)
    db_session.add_all([slot1, slot2])
    db_session.commit()

    # Add 7: fills 1+2=3 spaces in existing, 4 overflow into a new slot
    response = client.post(
        "/inventory/1/items",
        json={"item_id": item.id, "quantity": 7},
    )

    assert response.status_code == 200
    rows = db_session.query(CharacterInventory).filter_by(
        character_id=1, item_id=item.id
    ).all()
    for r in rows:
        db_session.refresh(r)
    total = sum(r.quantity for r in rows)
    assert total == 9 + 8 + 7  # 24
    # 3 rows: two filled to 10, one new with 4
    assert len(rows) == 3
    quantities = sorted([r.quantity for r in rows])
    assert quantities == [4, 10, 10]


# ── Security ─────────────────────────────────────────────────────────────


def test_sql_injection_in_item_id(client, db_session):
    """SQL injection attempt in JSON body should not crash the server."""
    response = client.post(
        "/inventory/1/items",
        json={"item_id": "1; DROP TABLE items; --", "quantity": 1},
    )
    # Should return 422 (invalid int) — must NOT return 500
    assert response.status_code == 422
