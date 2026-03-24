"""
Tests for POST /inventory/internal/characters/{character_id}/consume_item endpoint.

Covers:
- Successful consumption: quantity decrements, returns 200 with remaining_quantity
- Quantity=0 rejection: returns 400
- Item not in inventory: returns 400
- Row deletion: when quantity reaches 0, the row is deleted
- SQL injection in character_id path parameter
"""

import pytest
from models import Items, CharacterInventory


def _create_consumable(db_session, **overrides):
    """Helper: insert a consumable item into the DB and return it."""
    defaults = dict(
        name="Health Potion",
        item_level=1,
        item_type="consumable",
        item_rarity="common",
        max_stack_size=10,
        is_unique=False,
        description="Restores health",
        health_recovery=50,
    )
    defaults.update(overrides)
    item = Items(**defaults)
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def _add_to_inventory(db_session, character_id, item_id, quantity=1):
    """Helper: add an item to a character's inventory."""
    inv = CharacterInventory(
        character_id=character_id,
        item_id=item_id,
        quantity=quantity,
    )
    db_session.add(inv)
    db_session.commit()
    db_session.refresh(inv)
    return inv


# -- Success cases ----------------------------------------------------------


def test_consume_item_success(client, db_session):
    """Consuming an item with quantity > 1 returns 200 and decrements quantity."""
    item = _create_consumable(db_session)
    _add_to_inventory(db_session, character_id=1, item_id=item.id, quantity=5)

    response = client.post(
        f"/inventory/internal/characters/1/consume_item",
        json={"item_id": item.id},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["remaining_quantity"] == 4


def test_consume_item_decrements_multiple_times(client, db_session):
    """Calling consume twice decrements quantity by 2 total."""
    item = _create_consumable(db_session, name="Mana Potion")
    _add_to_inventory(db_session, character_id=1, item_id=item.id, quantity=3)

    resp1 = client.post(
        "/inventory/internal/characters/1/consume_item",
        json={"item_id": item.id},
    )
    assert resp1.status_code == 200
    assert resp1.json()["remaining_quantity"] == 2

    resp2 = client.post(
        "/inventory/internal/characters/1/consume_item",
        json={"item_id": item.id},
    )
    assert resp2.status_code == 200
    assert resp2.json()["remaining_quantity"] == 1


# -- Row deletion when quantity reaches 0 -----------------------------------


def test_consume_item_deletes_row_at_zero(client, db_session):
    """When quantity reaches 0, the inventory row is deleted and remaining_quantity=0."""
    item = _create_consumable(db_session, name="Last Potion")
    _add_to_inventory(db_session, character_id=1, item_id=item.id, quantity=1)

    response = client.post(
        "/inventory/internal/characters/1/consume_item",
        json={"item_id": item.id},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["remaining_quantity"] == 0

    # Verify the row was actually deleted from the DB
    row = (
        db_session.query(CharacterInventory)
        .filter_by(character_id=1, item_id=item.id)
        .first()
    )
    assert row is None


# -- Error cases ------------------------------------------------------------


def test_consume_item_quantity_zero_rejection(client, db_session):
    """Consuming an item with quantity=0 in DB returns 400."""
    item = _create_consumable(db_session, name="Empty Potion")
    # Add with quantity=0 directly (edge case: row exists but empty)
    inv = CharacterInventory(character_id=1, item_id=item.id, quantity=0)
    db_session.add(inv)
    db_session.commit()

    response = client.post(
        "/inventory/internal/characters/1/consume_item",
        json={"item_id": item.id},
    )

    assert response.status_code == 400
    data = response.json()
    assert "Недостаточно предметов" in data["detail"]


def test_consume_item_not_in_inventory(client, db_session):
    """Consuming an item that does not exist in the character's inventory returns 400."""
    item = _create_consumable(db_session, name="Ghost Potion")
    # Item exists in items table, but NOT in character_inventory for character 1

    response = client.post(
        "/inventory/internal/characters/1/consume_item",
        json={"item_id": item.id},
    )

    assert response.status_code == 400
    data = response.json()
    assert "Недостаточно предметов" in data["detail"]


def test_consume_item_nonexistent_item_id(client, db_session):
    """Consuming a completely nonexistent item_id returns 400."""
    response = client.post(
        "/inventory/internal/characters/1/consume_item",
        json={"item_id": 99999},
    )

    assert response.status_code == 400
    data = response.json()
    assert "Недостаточно предметов" in data["detail"]


def test_consume_item_wrong_character(client, db_session):
    """Consuming an item that belongs to a different character returns 400."""
    item = _create_consumable(db_session, name="Other Potion")
    _add_to_inventory(db_session, character_id=2, item_id=item.id, quantity=5)

    response = client.post(
        "/inventory/internal/characters/1/consume_item",
        json={"item_id": item.id},
    )

    assert response.status_code == 400


# -- After full consumption, second attempt also fails ----------------------


def test_consume_item_after_deletion_returns_400(client, db_session):
    """After consuming the last unit (row deleted), next attempt returns 400."""
    item = _create_consumable(db_session, name="Single Potion")
    _add_to_inventory(db_session, character_id=1, item_id=item.id, quantity=1)

    # First call: success, row deleted
    resp1 = client.post(
        "/inventory/internal/characters/1/consume_item",
        json={"item_id": item.id},
    )
    assert resp1.status_code == 200

    # Second call: should fail
    resp2 = client.post(
        "/inventory/internal/characters/1/consume_item",
        json={"item_id": item.id},
    )
    assert resp2.status_code == 400


# -- Security: SQL injection -----------------------------------------------


def test_consume_item_sql_injection_in_body(client, db_session):
    """SQL injection attempts in item_id should not cause 500."""
    response = client.post(
        "/inventory/internal/characters/1/consume_item",
        json={"item_id": "1; DROP TABLE character_inventory; --"},
    )
    # Pydantic validation should reject non-integer, returning 422
    assert response.status_code == 422
