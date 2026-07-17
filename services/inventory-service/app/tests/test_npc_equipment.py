"""
Tests for FEAT-116: NPC Equipment System — admin equip/unequip endpoints.

Covers:
- Equip item to empty slot (modifiers applied)
- Equip item replacing existing (old modifiers removed, new applied)
- Invalid slot_type rejected
- Incompatible item_type rejected
- Non-existent item_id returns 404
- Lazy creation of NPC equipment slots on first equip
- Unequip from occupied slot (modifiers removed)
- Unequip from empty slot returns 400
- Unequip with invalid slot_type returns 400
- Auth: missing token returns 401, non-admin returns 403
"""

import pytest
from unittest.mock import patch, AsyncMock

import models
import crud
from auth_http import get_current_user_via_http, require_permission, UserRead


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ADMIN_USER = UserRead(
    id=1,
    username="admin",
    role="admin",
    permissions=["npcs:update", "npcs:read", "items:read"],
)

REGULAR_USER = UserRead(
    id=2,
    username="player",
    role="user",
    permissions=[],
)


@pytest.fixture()
def admin_client(client):
    """Client with auth overridden to admin user with npcs:update permission."""
    from main import app

    app.dependency_overrides[get_current_user_via_http] = lambda: ADMIN_USER
    # Override the specific require_permission("npcs:update") dependency used by endpoints
    # Since require_permission is a factory, we need to override it at the
    # get_current_user_via_http level — the checker inside require_permission
    # calls get_current_user_via_http which we already override above.
    yield client
    app.dependency_overrides.pop(get_current_user_via_http, None)


@pytest.fixture()
def non_admin_client(client):
    """Client with auth overridden to regular (non-admin) user without npcs:update."""
    from main import app

    app.dependency_overrides[get_current_user_via_http] = lambda: REGULAR_USER
    yield client
    app.dependency_overrides.pop(get_current_user_via_http, None)


# ===========================================================================
# EQUIP ENDPOINT TESTS
# ===========================================================================


class TestAdminNpcEquip:
    """Tests for POST /inventory/admin/npc/{character_id}/equip."""

    def test_equip_item_to_empty_slot(self, admin_client, db_session):
        """Equipping an item to an empty NPC slot should succeed and apply modifiers."""
        item = _create_item(
            db_session,
            name="Iron Helmet",
            item_type="head",
            strength_modifier=3,
        )
        # Pre-create equipment slots so we test equipping to an existing empty slot
        crud.create_npc_equipment_slots(db_session, character_id=100)
        db_session.commit()

        mock_apply = AsyncMock()
        with patch("main.apply_modifiers_in_attributes_service", mock_apply):
            response = admin_client.post(
                "/inventory/admin/npc/100/equip",
                json={"slot_type": "head", "item_id": item.id},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["slot_type"] == "head"
        assert data["item_id"] == item.id
        assert data["character_id"] == 100

        # Modifiers should be applied (only new item, no old)
        assert mock_apply.call_count == 1
        call_args = mock_apply.call_args
        assert call_args[0][0] == 100  # character_id
        assert call_args[0][1].get("strength", 0) == 3  # positive modifier

    def test_equip_replaces_existing_item(self, admin_client, db_session):
        """Equipping to an occupied slot should remove old modifiers and apply new ones."""
        old_item = _create_item(
            db_session,
            name="Old Helmet",
            item_type="head",
            strength_modifier=2,
        )
        new_item = _create_item(
            db_session,
            name="New Helmet",
            item_type="head",
            agility_modifier=5,
        )
        # Create slot with old item
        _create_equipment_slot(db_session, character_id=100, slot_type="head", item_id=old_item.id)

        mock_apply = AsyncMock()
        with patch("main.apply_modifiers_in_attributes_service", mock_apply):
            response = admin_client.post(
                "/inventory/admin/npc/100/equip",
                json={"slot_type": "head", "item_id": new_item.id},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["item_id"] == new_item.id

        # Two calls: first to remove old modifiers (negative), second to apply new
        assert mock_apply.call_count == 2

        # First call: negative modifiers for old item
        old_call = mock_apply.call_args_list[0]
        assert old_call[0][0] == 100
        assert old_call[0][1].get("strength", 0) == -2

        # Second call: positive modifiers for new item
        new_call = mock_apply.call_args_list[1]
        assert new_call[0][0] == 100
        assert new_call[0][1].get("agility", 0) == 5

    def test_invalid_slot_type_fast_slot(self, admin_client, db_session):
        """Fast slots (fast_slot_1 etc.) are not valid for NPC equipment."""
        item = _create_item(db_session, name="Potion", item_type="consumable")

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = admin_client.post(
                "/inventory/admin/npc/100/equip",
                json={"slot_type": "fast_slot_1", "item_id": item.id},
            )

        assert response.status_code == 400
        assert "Недопустимый тип слота" in response.json()["detail"]

    def test_invalid_slot_type_nonexistent(self, admin_client, db_session):
        """A completely invalid slot_type should return 400."""
        item = _create_item(db_session, name="Sword", item_type="main_weapon")

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = admin_client.post(
                "/inventory/admin/npc/100/equip",
                json={"slot_type": "invalid_slot", "item_id": item.id},
            )

        assert response.status_code == 400
        assert "Недопустимый тип слота" in response.json()["detail"]

    def test_incompatible_item_type(self, admin_client, db_session):
        """Equipping a weapon to a head slot should return 400."""
        weapon = _create_item(
            db_session,
            name="Big Sword",
            item_type="main_weapon",
        )

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = admin_client.post(
                "/inventory/admin/npc/100/equip",
                json={"slot_type": "head", "item_id": weapon.id},
            )

        assert response.status_code == 400
        assert "не совместим" in response.json()["detail"]

    def test_nonexistent_item_id(self, admin_client, db_session):
        """Equipping a non-existent item should return 404."""
        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = admin_client.post(
                "/inventory/admin/npc/100/equip",
                json={"slot_type": "head", "item_id": 99999},
            )

        assert response.status_code == 404
        assert "Предмет не найден" in response.json()["detail"]

    def test_lazy_slot_creation_on_first_equip(self, admin_client, db_session):
        """First equip on an NPC without equipment slots should create them lazily."""
        item = _create_item(db_session, name="Helmet", item_type="head")

        # Verify no slots exist yet
        slots_before = db_session.query(models.EquipmentSlot).filter_by(
            character_id=200
        ).all()
        assert len(slots_before) == 0

        mock_apply = AsyncMock()
        with patch("main.apply_modifiers_in_attributes_service", mock_apply):
            response = admin_client.post(
                "/inventory/admin/npc/200/equip",
                json={"slot_type": "head", "item_id": item.id},
            )

        assert response.status_code == 200

        # Verify 9 NPC equipment slots were created (no fast slots, no shield — FEAT-149)
        slots_after = db_session.query(models.EquipmentSlot).filter_by(
            character_id=200
        ).all()
        assert len(slots_after) == 9

        slot_types = sorted([s.slot_type for s in slots_after])
        expected = sorted(crud.NPC_EQUIPMENT_SLOTS)
        assert slot_types == expected

        # Verify no fast_slot_* was created
        fast_slots = [s for s in slots_after if s.slot_type.startswith("fast_slot")]
        assert len(fast_slots) == 0

    def test_equip_resets_enhancement_fields(self, admin_client, db_session):
        """Equipping a new item should reset enhancement/gem/durability fields."""
        item = _create_item(db_session, name="Cloak", item_type="cloak")

        # Create slot with some enhancement data
        slot = _create_equipment_slot(db_session, character_id=100, slot_type="cloak")
        slot.enhancement_points_spent = 5
        slot.enhancement_bonuses = '{"strength": 2}'
        slot.socketed_gems = '[1, 2]'
        slot.current_durability = 50
        db_session.commit()

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = admin_client.post(
                "/inventory/admin/npc/100/equip",
                json={"slot_type": "cloak", "item_id": item.id},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["enhancement_points_spent"] == 0
        assert data["enhancement_bonuses"] is None
        assert data["socketed_gems"] is None
        assert data["current_durability"] is None


# ===========================================================================
# UNEQUIP ENDPOINT TESTS
# ===========================================================================


class TestAdminNpcUnequip:
    """Tests for DELETE /inventory/admin/npc/{character_id}/unequip/{slot_type}."""

    def test_unequip_occupied_slot(self, admin_client, db_session):
        """Unequipping an occupied slot should clear it and apply negative modifiers."""
        item = _create_item(
            db_session,
            name="Magic Ring",
            item_type="ring",
            intelligence_modifier=4,
        )
        _create_equipment_slot(
            db_session, character_id=100, slot_type="ring", item_id=item.id
        )

        mock_apply = AsyncMock()
        with patch("main.apply_modifiers_in_attributes_service", mock_apply):
            response = admin_client.delete(
                "/inventory/admin/npc/100/unequip/ring",
            )

        assert response.status_code == 200
        data = response.json()
        assert data["slot_type"] == "ring"
        assert data["item_id"] is None
        assert data["enhancement_points_spent"] == 0

        # Negative modifiers should be applied
        mock_apply.assert_called_once()
        call_args = mock_apply.call_args
        assert call_args[0][0] == 100
        assert call_args[0][1].get("intelligence", 0) == -4

    def test_unequip_empty_slot_returns_400(self, admin_client, db_session):
        """Unequipping from an already empty slot should return 400."""
        _create_equipment_slot(
            db_session, character_id=100, slot_type="body", item_id=None
        )

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = admin_client.delete(
                "/inventory/admin/npc/100/unequip/body",
            )

        assert response.status_code == 400
        assert "Слот уже пуст" in response.json()["detail"]

    def test_unequip_invalid_slot_type(self, admin_client, db_session):
        """Invalid slot_type should return 400."""
        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = admin_client.delete(
                "/inventory/admin/npc/100/unequip/invalid_slot",
            )

        assert response.status_code == 400
        assert "Недопустимый тип слота" in response.json()["detail"]

    def test_unequip_fast_slot_returns_400(self, admin_client, db_session):
        """Fast slots are not valid for NPC unequip."""
        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = admin_client.delete(
                "/inventory/admin/npc/100/unequip/fast_slot_1",
            )

        assert response.status_code == 400
        assert "Недопустимый тип слота" in response.json()["detail"]

    def test_unequip_no_slots_exist_returns_404(self, admin_client, db_session):
        """Unequipping from a character with no equipment slots should return 404."""
        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = admin_client.delete(
                "/inventory/admin/npc/999/unequip/head",
            )

        assert response.status_code == 404
        assert "не найдены" in response.json()["detail"]


# ===========================================================================
# AUTH TESTS
# ===========================================================================


class TestNpcEquipmentAuth:
    """Tests for authentication and authorization on NPC equipment endpoints."""

    def test_equip_no_token_returns_401(self, client, db_session):
        """Request without Authorization header should return 401."""
        response = client.post(
            "/inventory/admin/npc/100/equip",
            json={"slot_type": "head", "item_id": 1},
        )
        assert response.status_code == 401

    def test_unequip_no_token_returns_401(self, client, db_session):
        """Request without Authorization header should return 401."""
        response = client.delete(
            "/inventory/admin/npc/100/unequip/head",
        )
        assert response.status_code == 401

    def test_equip_non_admin_returns_403(self, non_admin_client, db_session):
        """User without npcs:update permission should get 403."""
        response = non_admin_client.post(
            "/inventory/admin/npc/100/equip",
            json={"slot_type": "head", "item_id": 1},
        )
        assert response.status_code == 403
        assert "Недостаточно прав" in response.json()["detail"]

    def test_unequip_non_admin_returns_403(self, non_admin_client, db_session):
        """User without npcs:update permission should get 403."""
        response = non_admin_client.delete(
            "/inventory/admin/npc/100/unequip/head",
        )
        assert response.status_code == 403
        assert "Недостаточно прав" in response.json()["detail"]


# ===========================================================================
# CRUD UNIT TESTS
# ===========================================================================


class TestCreateNpcEquipmentSlots:
    """Unit tests for crud.create_npc_equipment_slots."""

    def test_creates_9_slots(self, db_session):
        """Should create exactly 9 NPC equipment slots (no fast slots,
        no shield slot — FEAT-149)."""
        crud.create_npc_equipment_slots(db_session, character_id=300)
        db_session.commit()

        slots = db_session.query(models.EquipmentSlot).filter_by(
            character_id=300
        ).all()
        assert len(slots) == 9
        slot_types = {s.slot_type for s in slots}
        assert slot_types == set(crud.NPC_EQUIPMENT_SLOTS)

    def test_idempotent_does_not_duplicate(self, db_session):
        """Calling create_npc_equipment_slots twice should not duplicate slots."""
        crud.create_npc_equipment_slots(db_session, character_id=300)
        db_session.commit()
        crud.create_npc_equipment_slots(db_session, character_id=300)
        db_session.commit()

        slots = db_session.query(models.EquipmentSlot).filter_by(
            character_id=300
        ).all()
        assert len(slots) == 9

    def test_slots_are_enabled_and_empty(self, db_session):
        """All created slots should be enabled with no item."""
        crud.create_npc_equipment_slots(db_session, character_id=300)
        db_session.commit()

        slots = db_session.query(models.EquipmentSlot).filter_by(
            character_id=300
        ).all()
        for slot in slots:
            assert slot.is_enabled is True
            assert slot.item_id is None


class TestNpcEquipmentSlotsConstant:
    """Verify the NPC_EQUIPMENT_SLOTS constant is correct."""

    def test_contains_all_equipment_slots(self):
        """NPC_EQUIPMENT_SLOTS should contain all 9 non-fast equipment slots
        (no shield slot — FEAT-149)."""
        expected = {
            'head', 'body', 'cloak', 'belt', 'ring', 'necklace', 'bracelet',
            'main_weapon', 'additional_weapons',
        }
        assert set(crud.NPC_EQUIPMENT_SLOTS) == expected

    def test_excludes_fast_slots(self):
        """NPC_EQUIPMENT_SLOTS should NOT contain any fast_slot_* entries."""
        for slot in crud.NPC_EQUIPMENT_SLOTS:
            assert not slot.startswith("fast_slot"), (
                f"NPC_EQUIPMENT_SLOTS must not include fast slots, found: {slot}"
            )


# ===========================================================================
# SECURITY TESTS
# ===========================================================================


class TestNpcEquipmentSecurity:
    """Security tests for NPC equipment endpoints."""

    def test_equip_sql_injection_in_slot_type(self, admin_client, db_session):
        """SQL injection attempt in slot_type should be safely rejected."""
        item = _create_item(db_session, name="Helmet", item_type="head")
        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = admin_client.post(
                "/inventory/admin/npc/100/equip",
                json={"slot_type": "'; DROP TABLE items; --", "item_id": item.id},
            )
        assert response.status_code == 400  # Must not crash with 500

    def test_unequip_sql_injection_in_slot_type(self, admin_client, db_session):
        """SQL injection attempt in slot_type path param should be safely rejected."""
        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            response = admin_client.delete(
                "/inventory/admin/npc/100/unequip/'; DROP TABLE items; --",
            )
        assert response.status_code == 400  # Must not crash with 500
