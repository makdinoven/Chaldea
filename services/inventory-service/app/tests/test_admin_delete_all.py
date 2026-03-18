"""
Tests for FEAT-021 admin endpoint in inventory-service:
- DELETE /inventory/{character_id}/all
"""

import pytest
import database
import models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_item(db, item_id=1, name="Sword", item_type="main_weapon", item_rarity="common"):
    """Create an item in the test DB."""
    item = models.Items(
        id=item_id,
        name=name,
        item_type=item_type,
        item_rarity=item_rarity,
        max_stack_size=10,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _create_inventory(db, character_id=1, item_id=1, quantity=5):
    """Create a CharacterInventory row."""
    inv = models.CharacterInventory(
        character_id=character_id,
        item_id=item_id,
        quantity=quantity,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def _create_equipment_slot(db, character_id=1, slot_type="main_weapon", item_id=None):
    """Create an EquipmentSlot row."""
    slot = models.EquipmentSlot(
        character_id=character_id,
        slot_type=slot_type,
        item_id=item_id,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def admin_client(db_session):
    """Client with mocked admin auth."""
    from main import app, get_db as main_get_db
    from auth_http import get_admin_user, get_current_user_via_http, UserRead
    from fastapi.testclient import TestClient

    admin = UserRead(id=1, username="admin", role="admin", permissions=[
        "items:create", "items:read", "items:update", "items:delete",
    ])

    def override_get_db():
        yield db_session

    def override_admin():
        return admin

    app.dependency_overrides[main_get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = override_admin
    app.dependency_overrides[get_current_user_via_http] = override_admin
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def non_admin_client(db_session):
    """Client with admin auth that raises 403."""
    from main import app, get_db as main_get_db
    from auth_http import get_admin_user, get_current_user_via_http, UserRead
    from fastapi.testclient import TestClient
    from fastapi import HTTPException

    def override_get_db():
        yield db_session

    def override_non_admin():
        raise HTTPException(status_code=403, detail="Admin access required")

    def override_non_admin_user():
        return UserRead(id=2, username="player", role="user", permissions=[])

    app.dependency_overrides[main_get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = override_non_admin
    app.dependency_overrides[get_current_user_via_http] = override_non_admin_user
    yield TestClient(app)
    app.dependency_overrides.clear()


# ===========================================================================
# DELETE /inventory/{character_id}/all
# ===========================================================================

class TestDeleteAllInventory:

    def test_delete_all_success(self, admin_client, db_session):
        item = _create_item(db_session, item_id=1, name="Sword")
        _create_inventory(db_session, character_id=1, item_id=1, quantity=5)
        _create_inventory(db_session, character_id=1, item_id=1, quantity=3)
        _create_equipment_slot(db_session, character_id=1, slot_type="main_weapon", item_id=1)

        resp = admin_client.delete("/inventory/1/all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["detail"] == "All inventory cleared"
        assert data["items_deleted"] == 2
        assert data["slots_deleted"] == 1

        # Verify DB is clean
        inv_count = db_session.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == 1
        ).count()
        assert inv_count == 0

        slot_count = db_session.query(models.EquipmentSlot).filter(
            models.EquipmentSlot.character_id == 1
        ).count()
        assert slot_count == 0

    def test_delete_all_empty_case(self, admin_client, db_session):
        """No data to delete — idempotent, returns counts=0."""
        resp = admin_client.delete("/inventory/999/all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items_deleted"] == 0
        assert data["slots_deleted"] == 0

    def test_delete_all_forbidden_for_non_admin(self, non_admin_client, db_session):
        resp = non_admin_client.delete("/inventory/1/all")
        assert resp.status_code == 403

    def test_delete_all_does_not_affect_other_characters(self, admin_client, db_session):
        """Deleting character 1's inventory should not affect character 2."""
        item = _create_item(db_session, item_id=1, name="Sword")
        _create_inventory(db_session, character_id=1, item_id=1, quantity=5)
        _create_inventory(db_session, character_id=2, item_id=1, quantity=3)
        _create_equipment_slot(db_session, character_id=2, slot_type="main_weapon", item_id=1)

        resp = admin_client.delete("/inventory/1/all")
        assert resp.status_code == 200
        assert resp.json()["items_deleted"] == 1

        # Character 2's data should still exist
        inv = db_session.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == 2
        ).count()
        assert inv == 1

        slot = db_session.query(models.EquipmentSlot).filter(
            models.EquipmentSlot.character_id == 2
        ).count()
        assert slot == 1
