"""
Tests for battle lock in inventory-service (FEAT-066).

Covers:
1. Equip item while in battle -> 400
2. Unequip item while in battle -> 400
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy import text

from auth_http import get_current_user_via_http, UserRead


@pytest.fixture()
def authed_client(client, db_session):
    """Client with auth overridden to user_id=1.
    Creates the supporting tables needed by battle lock checks.
    """
    from main import app

    # Create characters table (needed by verify_character_ownership)
    db_session.execute(text(
        """CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY,
            user_id INTEGER
        )"""
    ))
    db_session.execute(text("INSERT OR IGNORE INTO characters (id, user_id) VALUES (1, 1)"))

    # Create battles table (needed by is_character_in_battle)
    db_session.execute(text(
        """CREATE TABLE IF NOT EXISTS battles (
            id INTEGER PRIMARY KEY,
            status TEXT DEFAULT 'in_progress'
        )"""
    ))

    # Create battle_participants table
    db_session.execute(text(
        """CREATE TABLE IF NOT EXISTS battle_participants (
            id INTEGER PRIMARY KEY,
            battle_id INTEGER,
            character_id INTEGER
        )"""
    ))

    db_session.commit()

    _user = UserRead(id=1, username="testuser", role="user", permissions=[])
    app.dependency_overrides[get_current_user_via_http] = lambda: _user
    yield client
    app.dependency_overrides.pop(get_current_user_via_http, None)


def _put_character_in_battle(db_session):
    """Insert a battle + participant row so character 1 is 'in battle'."""
    db_session.execute(text(
        "INSERT OR IGNORE INTO battles (id, status) VALUES (1, 'in_progress')"
    ))
    db_session.execute(text(
        "INSERT OR IGNORE INTO battle_participants (id, battle_id, character_id) VALUES (1, 1, 1)"
    ))
    db_session.commit()


def _create_equippable_item(db_session):
    """Create a head-type item and inventory entry for character 1."""
    import models

    item = models.Items(
        id=100,
        name="Test Helmet",
        item_level=1,
        item_type="head",
        item_rarity="common",
        max_stack_size=1,
        is_unique=False,
    )
    db_session.add(item)
    db_session.flush()

    inv = models.CharacterInventory(character_id=1, item_id=100, quantity=1)
    db_session.add(inv)

    slot = models.EquipmentSlot(
        character_id=1, slot_type="head", item_id=None, is_enabled=True
    )
    db_session.add(slot)
    db_session.commit()


# ===========================================================================
# Test 1: Equip item while in battle -> 400
# ===========================================================================
class TestEquipInBattle:
    """Equipping an item while in battle should be blocked."""

    def test_equip_blocked_in_battle(self, authed_client, db_session):
        """POST /{character_id}/equip returns 400 when in battle."""
        _create_equippable_item(db_session)
        _put_character_in_battle(db_session)

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = authed_client.post(
                "/inventory/1/equip",
                json={"item_id": 100},
            )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "бо" in detail.lower(), f"Expected Russian battle-related message, got: {detail}"


# ===========================================================================
# Test 2: Unequip item while in battle -> 400
# ===========================================================================
class TestUnequipInBattle:
    """Unequipping an item while in battle should be blocked."""

    def test_unequip_blocked_in_battle(self, authed_client, db_session):
        """POST /{character_id}/unequip returns 400 when in battle."""
        import models

        # Create equipped item
        item = models.Items(
            id=200,
            name="Equipped Shield",
            item_level=1,
            item_type="off_hand",
            item_rarity="common",
            max_stack_size=1,
            is_unique=False,
        )
        db_session.add(item)
        db_session.flush()

        slot = models.EquipmentSlot(
            character_id=1, slot_type="off_hand", item_id=200, is_enabled=True
        )
        db_session.add(slot)
        db_session.commit()

        _put_character_in_battle(db_session)

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = authed_client.post(
                "/inventory/1/unequip?slot_type=off_hand",
            )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "бо" in detail.lower(), f"Expected Russian battle-related message, got: {detail}"
