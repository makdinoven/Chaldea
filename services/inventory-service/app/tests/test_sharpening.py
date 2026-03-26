"""
Task 4.4 — QA tests for FEAT-083: Blacksmith sharpening system.

Tests covering sharpening endpoint, sharpen-info endpoint, point-based mechanic,
whetstone validation, profession checks, and build_modifiers_dict enhancement.
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
            character_id INTEGER NOT NULL
        )"""
    ))
    db.commit()


def _insert_character(db, char_id, user_id, name="TestChar"):
    db.execute(text(
        "INSERT OR IGNORE INTO characters (id, name, user_id) VALUES (:cid, :name, :uid)"
    ), {"cid": char_id, "name": name, "uid": user_id})
    db.commit()


def _create_profession(db, prof_id=1, name="Кузнец", slug="blacksmith"):
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
                 whetstone_level=None, **kwargs):
    item = models.Items(
        id=item_id, name=name, item_level=1, item_type=item_type,
        item_rarity=kwargs.pop("item_rarity", "common"),
        max_stack_size=max_stack, is_unique=False,
        whetstone_level=whetstone_level,
        **kwargs,
    )
    db.add(item)
    db.flush()
    return item


def _add_inventory(db, char_id, item_id, quantity, enhancement_points_spent=0,
                   enhancement_bonuses=None):
    inv = models.CharacterInventory(
        character_id=char_id, item_id=item_id, quantity=quantity,
        enhancement_points_spent=enhancement_points_spent,
    )
    if enhancement_bonuses:
        inv.enhancement_bonuses = json.dumps(enhancement_bonuses)
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
                           enhancement_points_spent=0, enhancement_bonuses=None):
    slot = models.EquipmentSlot(
        character_id=char_id, slot_type=slot_type, item_id=item_id,
        is_enabled=True, enhancement_points_spent=enhancement_points_spent,
    )
    if enhancement_bonuses:
        slot.enhancement_bonuses = json.dumps(enhancement_bonuses)
    db.add(slot)
    db.flush()
    return slot


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_user1 = UserRead(id=1, username="player1", role="user", permissions=[])


@pytest.fixture()
def sharpen_env(client, db_session):
    """Full sharpening test environment: blacksmith with weapon and whetstone."""
    _create_characters_table(db_session)
    _insert_character(db_session, 1, user_id=1, name="Blacksmith")

    # Profession + rank
    prof = _create_profession(db_session, 1, "Кузнец", "blacksmith")
    _create_rank(db_session, profession_id=prof.id, rank_number=1, name="Ученик")
    _create_rank(db_session, profession_id=prof.id, rank_number=2, name="Подмастерье")

    # Weapon item (sharpenable) with some base stats
    weapon = _create_item(
        db_session, 10, "Железный меч", "main_weapon", max_stack=1,
        strength_modifier=5, damage_modifier=20,
    )

    # Common whetstone (25%)
    ws_common = _create_item(
        db_session, 20, "Обычный точильный камень", "resource",
        max_stack=99, whetstone_level=1, item_rarity="common",
    )
    # Rare whetstone (50%)
    ws_rare = _create_item(
        db_session, 21, "Редкий точильный камень", "resource",
        max_stack=99, whetstone_level=2, item_rarity="rare",
    )
    # Legendary whetstone (75%)
    ws_legendary = _create_item(
        db_session, 22, "Легендарный точильный камень", "resource",
        max_stack=99, whetstone_level=3, item_rarity="legendary",
    )

    # Add weapon and whetstone to inventory
    weapon_inv = _add_inventory(db_session, 1, weapon.id, 1)
    ws_inv = _add_inventory(db_session, 1, ws_common.id, 10)
    ws_rare_inv = _add_inventory(db_session, 1, ws_rare.id, 5)
    ws_legend_inv = _add_inventory(db_session, 1, ws_legendary.id, 3)

    _assign_profession(db_session, 1, prof.id, rank=1, experience=0)
    db_session.commit()

    from main import app
    app.dependency_overrides[get_current_user_via_http] = lambda: _user1

    yield {
        "client": client,
        "db": db_session,
        "app": app,
        "profession": prof,
        "weapon": weapon,
        "ws_common": ws_common,
        "ws_rare": ws_rare,
        "ws_legendary": ws_legendary,
        "weapon_inv": weapon_inv,
        "ws_inv": ws_inv,
        "ws_rare_inv": ws_rare_inv,
        "ws_legend_inv": ws_legend_inv,
    }

    app.dependency_overrides.pop(get_current_user_via_http, None)


# ===========================================================================
# 1. Happy path — successful sharpening
# ===========================================================================

class TestSharpenHappyPath:

    def test_sharpen_weapon_success(self, sharpen_env):
        """Mock random to succeed. Verify: stat count incremented, points_spent increased,
        whetstone consumed, correct stat delta."""
        c = sharpen_env["client"]
        db = sharpen_env["db"]
        weapon_inv = sharpen_env["weapon_inv"]
        ws_inv = sharpen_env["ws_inv"]

        with patch("main.random.random", return_value=0.1), \
             patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/sharpen", json={
                "inventory_item_id": weapon_inv.id,
                "whetstone_item_id": ws_inv.id,
                "stat_field": "strength_modifier",
                "source": "inventory",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["item_name"] == "Железный меч"
        assert data["new_value"] == 1.0  # first sharpening: count goes 0->1
        assert data["old_value"] == 0.0
        assert data["points_spent"] == 1  # existing stat costs 1
        assert data["points_remaining"] == 14
        assert data["point_cost"] == 1
        assert data["whetstone_consumed"] is True
        assert data["xp_earned"] == 10

        # Verify DB state
        db.expire_all()
        inv = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == weapon_inv.id
        ).first()
        assert inv.enhancement_points_spent == 1
        bonuses = json.loads(inv.enhancement_bonuses)
        assert bonuses["strength_modifier"] == 1

        # Whetstone consumed
        ws = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == ws_inv.id
        ).first()
        assert ws.quantity == 9  # was 10


# ===========================================================================
# 2. Failed sharpening
# ===========================================================================

class TestSharpenFailed:

    def test_sharpen_failure_whetstone_consumed_stats_unchanged(self, sharpen_env):
        """Mock random to fail. Verify: points_spent unchanged, enhancement_bonuses unchanged,
        whetstone consumed."""
        c = sharpen_env["client"]
        db = sharpen_env["db"]
        weapon_inv = sharpen_env["weapon_inv"]
        ws_inv = sharpen_env["ws_inv"]

        with patch("main.random.random", return_value=0.99), \
             patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/sharpen", json={
                "inventory_item_id": weapon_inv.id,
                "whetstone_item_id": ws_inv.id,
                "stat_field": "damage_modifier",
                "source": "inventory",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["points_spent"] == 0
        assert data["points_remaining"] == 15
        assert data["whetstone_consumed"] is True

        # DB: points unchanged
        db.expire_all()
        inv = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == weapon_inv.id
        ).first()
        assert inv.enhancement_points_spent == 0
        assert inv.enhancement_bonuses is None or json.loads(inv.enhancement_bonuses) == {}

        # Whetstone still consumed
        ws = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == ws_inv.id
        ).first()
        assert ws.quantity == 9


# ===========================================================================
# 3. Point cost — existing stat costs 1 point
# ===========================================================================

class TestPointCostExistingStat:

    def test_existing_stat_costs_1_point(self, sharpen_env):
        """Sharpening a non-zero base stat costs 1 point."""
        c = sharpen_env["client"]
        weapon_inv = sharpen_env["weapon_inv"]
        ws_inv = sharpen_env["ws_inv"]

        # strength_modifier=5 on the weapon, so it's existing
        with patch("main.random.random", return_value=0.01), \
             patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/sharpen", json={
                "inventory_item_id": weapon_inv.id,
                "whetstone_item_id": ws_inv.id,
                "stat_field": "strength_modifier",
                "source": "inventory",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["point_cost"] == 1
        assert data["points_spent"] == 1


# ===========================================================================
# 4. Point cost — new stat costs 2 points
# ===========================================================================

class TestPointCostNewStat:

    def test_new_stat_costs_2_points(self, sharpen_env):
        """Sharpening a zero base stat costs 2 points."""
        c = sharpen_env["client"]
        weapon_inv = sharpen_env["weapon_inv"]
        ws_inv = sharpen_env["ws_inv"]

        # agility_modifier=0 on the weapon, so it's new
        with patch("main.random.random", return_value=0.01), \
             patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/sharpen", json={
                "inventory_item_id": weapon_inv.id,
                "whetstone_item_id": ws_inv.id,
                "stat_field": "agility_modifier",
                "source": "inventory",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["point_cost"] == 2
        assert data["points_spent"] == 2


# ===========================================================================
# 5. Max stat (+5) — expect 400
# ===========================================================================

class TestMaxStat:

    def test_sharpen_stat_already_at_max(self, sharpen_env):
        """Try to sharpen a stat already at +5. Expect 400 error."""
        db = sharpen_env["db"]
        c = sharpen_env["client"]
        weapon_inv = sharpen_env["weapon_inv"]
        ws_inv = sharpen_env["ws_inv"]

        # Pre-set enhancement_bonuses to have strength_modifier at 5
        weapon_inv.enhancement_bonuses = json.dumps({"strength_modifier": 5})
        weapon_inv.enhancement_points_spent = 5
        db.commit()

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/sharpen", json={
                "inventory_item_id": weapon_inv.id,
                "whetstone_item_id": ws_inv.id,
                "stat_field": "strength_modifier",
                "source": "inventory",
            })

        assert resp.status_code == 400
        assert "максимум" in resp.json()["detail"].lower() or "+5" in resp.json()["detail"]


# ===========================================================================
# 6. Points exhausted — 15/15
# ===========================================================================

class TestPointsExhausted:

    def test_sharpen_when_points_exhausted(self, sharpen_env):
        """Try to sharpen when enhancement_points_spent = 15. Expect 400."""
        db = sharpen_env["db"]
        c = sharpen_env["client"]
        weapon_inv = sharpen_env["weapon_inv"]
        ws_inv = sharpen_env["ws_inv"]

        weapon_inv.enhancement_points_spent = 15
        weapon_inv.enhancement_bonuses = json.dumps({"strength_modifier": 5, "damage_modifier": 5})
        db.commit()

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/sharpen", json={
                "inventory_item_id": weapon_inv.id,
                "whetstone_item_id": ws_inv.id,
                "stat_field": "endurance_modifier",
                "source": "inventory",
            })

        assert resp.status_code == 400
        assert "поинт" in resp.json()["detail"].lower() or "Недостаточно" in resp.json()["detail"]


# ===========================================================================
# 7. Not enough points for new stat
# ===========================================================================

class TestNotEnoughPointsForNewStat:

    def test_14_points_spent_new_stat_costs_2(self, sharpen_env):
        """14 points spent, trying to add new stat (costs 2). Expect 400."""
        db = sharpen_env["db"]
        c = sharpen_env["client"]
        weapon_inv = sharpen_env["weapon_inv"]
        ws_inv = sharpen_env["ws_inv"]

        weapon_inv.enhancement_points_spent = 14
        weapon_inv.enhancement_bonuses = json.dumps({"strength_modifier": 5, "damage_modifier": 5})
        db.commit()

        # agility_modifier=0 => new stat => costs 2 => 14+2=16 > 15
        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/sharpen", json={
                "inventory_item_id": weapon_inv.id,
                "whetstone_item_id": ws_inv.id,
                "stat_field": "agility_modifier",
                "source": "inventory",
            })

        assert resp.status_code == 400

    def test_14_points_spent_existing_stat_costs_1_ok(self, sharpen_env):
        """14 points spent, sharpening existing stat (costs 1). Should succeed."""
        db = sharpen_env["db"]
        c = sharpen_env["client"]
        weapon_inv = sharpen_env["weapon_inv"]
        ws_inv = sharpen_env["ws_inv"]

        weapon_inv.enhancement_points_spent = 14
        weapon_inv.enhancement_bonuses = json.dumps({"strength_modifier": 4, "damage_modifier": 5})
        db.commit()

        # strength_modifier=5 on base item => existing => costs 1 => 14+1=15 ok
        with patch("main.random.random", return_value=0.01), \
             patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/sharpen", json={
                "inventory_item_id": weapon_inv.id,
                "whetstone_item_id": ws_inv.id,
                "stat_field": "strength_modifier",
                "source": "inventory",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["points_spent"] == 15


# ===========================================================================
# 8. Non-blacksmith
# ===========================================================================

class TestNonBlacksmith:

    def test_alchemist_cannot_sharpen(self, sharpen_env):
        """Alchemist tries to sharpen. Expect 400."""
        db = sharpen_env["db"]
        c = sharpen_env["client"]
        weapon_inv = sharpen_env["weapon_inv"]
        ws_inv = sharpen_env["ws_inv"]

        # Change profession to alchemist
        cp = db.query(models.CharacterProfession).filter(
            models.CharacterProfession.character_id == 1
        ).first()
        db.delete(cp)
        db.flush()

        prof2 = _create_profession(db, 2, "Алхимик", "alchemist")
        _create_rank(db, profession_id=prof2.id, rank_number=1, name="Новичок")
        _assign_profession(db, 1, prof2.id, rank=1)
        db.commit()

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/sharpen", json={
                "inventory_item_id": weapon_inv.id,
                "whetstone_item_id": ws_inv.id,
                "stat_field": "strength_modifier",
                "source": "inventory",
            })

        assert resp.status_code == 400
        assert "кузнец" in resp.json()["detail"].lower()


# ===========================================================================
# 9. Wrong item type
# ===========================================================================

class TestWrongItemType:

    def test_sharpen_consumable_returns_400(self, sharpen_env):
        """Try to sharpen a consumable/resource. Expect 400."""
        db = sharpen_env["db"]
        c = sharpen_env["client"]
        ws_inv = sharpen_env["ws_inv"]

        potion = _create_item(db, 30, "Зелье лечения", "consumable", max_stack=10)
        potion_inv = _add_inventory(db, 1, potion.id, 3)
        db.commit()

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/sharpen", json={
                "inventory_item_id": potion_inv.id,
                "whetstone_item_id": ws_inv.id,
                "stat_field": "health_modifier",
                "source": "inventory",
            })

        assert resp.status_code == 400
        assert "тип" in resp.json()["detail"].lower() or "затачивать" in resp.json()["detail"]


# ===========================================================================
# 10. Invalid stat_field
# ===========================================================================

class TestInvalidStatField:

    def test_nonexistent_stat_field_returns_400(self, sharpen_env):
        """Try to sharpen a non-existent stat field. Expect 400."""
        c = sharpen_env["client"]
        weapon_inv = sharpen_env["weapon_inv"]
        ws_inv = sharpen_env["ws_inv"]

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/sharpen", json={
                "inventory_item_id": weapon_inv.id,
                "whetstone_item_id": ws_inv.id,
                "stat_field": "nonexistent_stat",
                "source": "inventory",
            })

        assert resp.status_code == 400
        assert "стат" in resp.json()["detail"].lower() or "Недопустимый" in resp.json()["detail"]


# ===========================================================================
# 11. No whetstone — invalid whetstone_item_id
# ===========================================================================

class TestNoWhetstone:

    def test_invalid_whetstone_id_returns_error(self, sharpen_env):
        """Invalid whetstone_item_id. Expect 400/404."""
        c = sharpen_env["client"]
        weapon_inv = sharpen_env["weapon_inv"]

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/sharpen", json={
                "inventory_item_id": weapon_inv.id,
                "whetstone_item_id": 99999,
                "stat_field": "strength_modifier",
                "source": "inventory",
            })

        assert resp.status_code in (400, 404)


# ===========================================================================
# 12. Non-whetstone item used as whetstone
# ===========================================================================

class TestNonWhetstoneItem:

    def test_regular_item_as_whetstone_returns_400(self, sharpen_env):
        """Use a regular item as whetstone. Expect 400."""
        db = sharpen_env["db"]
        c = sharpen_env["client"]
        weapon_inv = sharpen_env["weapon_inv"]

        ore = _create_item(db, 31, "Железная руда", "resource", max_stack=99)
        ore_inv = _add_inventory(db, 1, ore.id, 5)
        db.commit()

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/sharpen", json={
                "inventory_item_id": weapon_inv.id,
                "whetstone_item_id": ore_inv.id,
                "stat_field": "strength_modifier",
                "source": "inventory",
            })

        assert resp.status_code == 400
        assert "точильн" in resp.json()["detail"].lower() or "не является" in resp.json()["detail"]


# ===========================================================================
# 13. Whetstone success chances
# ===========================================================================

class TestWhetstoneChances:

    def test_common_whetstone_25_percent(self):
        """Verify correct chance mapping: level 1 = 25%."""
        assert crud.WHETSTONE_CHANCE[1] == 0.25

    def test_rare_whetstone_50_percent(self):
        """Verify correct chance mapping: level 2 = 50%."""
        assert crud.WHETSTONE_CHANCE[2] == 0.50

    def test_legendary_whetstone_75_percent(self):
        """Verify correct chance mapping: level 3 = 75%."""
        assert crud.WHETSTONE_CHANCE[3] == 0.75


# ===========================================================================
# 14. Sharpen-info endpoint
# ===========================================================================

class TestSharpenInfoEndpoint:

    def test_sharpen_info_returns_item_stats_whetstones(self, sharpen_env):
        """GET returns correct item info, stats list, whetstones."""
        c = sharpen_env["client"]
        weapon_inv = sharpen_env["weapon_inv"]

        resp = c.get(f"/inventory/crafting/1/sharpen-info/{weapon_inv.id}?source=inventory")

        assert resp.status_code == 200
        data = resp.json()
        assert data["item_name"] == "Железный меч"
        assert data["item_type"] == "main_weapon"
        assert data["points_spent"] == 0
        assert data["points_remaining"] == 15
        assert len(data["stats"]) == len(crud.ALL_SHARPENABLE_FIELDS)
        assert len(data["whetstones"]) >= 1

        # Check that strength_modifier is existing with correct cost
        strength_stat = next(s for s in data["stats"] if s["field"] == "strength_modifier")
        assert strength_stat["is_existing"] is True
        assert strength_stat["point_cost"] == 1
        assert strength_stat["base_value"] == 5.0
        assert strength_stat["can_sharpen"] is True

        # Check that agility_modifier is new with cost 2
        agility_stat = next(s for s in data["stats"] if s["field"] == "agility_modifier")
        assert agility_stat["is_existing"] is False
        assert agility_stat["point_cost"] == 2

    def test_sharpen_info_whetstones_show_correct_chances(self, sharpen_env):
        """Whetstones section shows correct success chances."""
        c = sharpen_env["client"]
        weapon_inv = sharpen_env["weapon_inv"]

        resp = c.get(f"/inventory/crafting/1/sharpen-info/{weapon_inv.id}?source=inventory")
        data = resp.json()

        whetstones = {ws["name"]: ws for ws in data["whetstones"]}
        assert whetstones["Обычный точильный камень"]["success_chance"] == 25
        assert whetstones["Редкий точильный камень"]["success_chance"] == 50
        assert whetstones["Легендарный точильный камень"]["success_chance"] == 75

    def test_sharpen_info_nonsharpenable_item_400(self, sharpen_env):
        """Sharpen-info on a non-sharpenable item returns 400."""
        db = sharpen_env["db"]
        c = sharpen_env["client"]

        potion = _create_item(db, 40, "Зелье маны", "consumable")
        potion_inv = _add_inventory(db, 1, potion.id, 2)
        db.commit()

        resp = c.get(f"/inventory/crafting/1/sharpen-info/{potion_inv.id}?source=inventory")
        assert resp.status_code == 400


# ===========================================================================
# 15. Equipped item sharpening
# ===========================================================================

class TestEquippedItemSharpening:

    def test_sharpen_equipped_item_updates_slot(self, sharpen_env):
        """Sharpen an equipped item (source=equipment). Verify enhancement data
        updated on equipment slot and stat delta sent to attributes service."""
        db = sharpen_env["db"]
        c = sharpen_env["client"]
        weapon = sharpen_env["weapon"]
        ws_inv = sharpen_env["ws_inv"]

        # Create equipment slot with weapon equipped
        eq_slot = _create_equipment_slot(db, 1, "main_weapon", item_id=weapon.id)
        db.commit()

        mock_apply = AsyncMock()

        with patch("main.random.random", return_value=0.01), \
             patch("main.apply_modifiers_in_attributes_service", mock_apply):
            resp = c.post("/inventory/crafting/1/sharpen", json={
                "inventory_item_id": eq_slot.id,
                "whetstone_item_id": ws_inv.id,
                "stat_field": "strength_modifier",
                "source": "equipment",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        # Verify equipment slot updated
        db.expire_all()
        slot = db.query(models.EquipmentSlot).filter(
            models.EquipmentSlot.id == eq_slot.id
        ).first()
        assert slot.enhancement_points_spent == 1
        bonuses = json.loads(slot.enhancement_bonuses)
        assert bonuses["strength_modifier"] == 1

        # Verify apply_modifiers was called with correct delta
        mock_apply.assert_called_once()
        call_args = mock_apply.call_args
        assert call_args[0][0] == 1  # character_id
        delta = call_args[0][1]
        assert delta["strength"] == 1  # +1 for main stat


# ===========================================================================
# 16. XP awarded
# ===========================================================================

class TestXPAwarded:

    def test_xp_awarded_on_sharpening(self, sharpen_env):
        """Verify crafting XP is awarded after sharpening (success or failure)."""
        c = sharpen_env["client"]
        weapon_inv = sharpen_env["weapon_inv"]
        ws_inv = sharpen_env["ws_inv"]

        # Even on failure, XP should be awarded
        with patch("main.random.random", return_value=0.99), \
             patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock):
            resp = c.post("/inventory/crafting/1/sharpen", json={
                "inventory_item_id": weapon_inv.id,
                "whetstone_item_id": ws_inv.id,
                "stat_field": "strength_modifier",
                "source": "inventory",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["xp_earned"] == 10
        assert data["new_total_xp"] == 10


# ===========================================================================
# 17. build_modifiers_dict with enhancement_bonuses — unit test
# ===========================================================================

class TestBuildModifiersDictWithEnhancement:

    def test_enhancement_bonuses_added_to_base_modifiers(self, db_session):
        """Unit test that enhancement bonuses are correctly added to base modifiers."""
        # Create tables first
        _create_characters_table(db_session)

        item = _create_item(
            db_session, 50, "Тестовый меч", "main_weapon", max_stack=1,
            strength_modifier=10, damage_modifier=20, res_fire_modifier=0.5,
        )
        db_session.commit()

        # Without enhancement
        mods = crud.build_modifiers_dict(item)
        assert mods["strength"] == 10
        assert mods["damage"] == 20
        assert abs(mods["res_fire"] - 0.5) < 0.01

        # With enhancement (strength sharpened 3 times, damage 2 times, res_fire 1 time)
        enhancement_bonuses = {
            "strength_modifier": 3,
            "damage_modifier": 2,
            "res_fire_modifier": 1,
        }
        mods_enh = crud.build_modifiers_dict(item, enhancement_bonuses=enhancement_bonuses)
        assert mods_enh["strength"] == 13  # 10 + 3*1
        assert mods_enh["damage"] == 22   # 20 + 2*1
        assert abs(mods_enh["res_fire"] - 0.6) < 0.01  # 0.5 + 1*0.1

    def test_enhancement_bonuses_new_stat_added(self, db_session):
        """Enhancement on a stat with 0 base value still adds bonus via bonuses dict."""
        _create_characters_table(db_session)

        item = _create_item(
            db_session, 51, "Тестовый щит", "shield", max_stack=1,
            endurance_modifier=5,
        )
        db_session.commit()

        # Sharpen agility (which is 0 on base) — the bonuses dict tracks sharpened stats
        enhancement_bonuses = {"agility_modifier": 2}
        mods = crud.build_modifiers_dict(item, enhancement_bonuses=enhancement_bonuses)
        assert mods["endurance"] == 5
        assert mods["agility"] == 2  # 0 base + 2*1 from enhancement

    def test_enhancement_bonuses_with_negative(self, db_session):
        """Enhancement bonuses are also negated when negative=True."""
        _create_characters_table(db_session)

        item = _create_item(
            db_session, 52, "Тестовый шлем", "head", max_stack=1,
            intelligence_modifier=8,
        )
        db_session.commit()

        enhancement_bonuses = {"intelligence_modifier": 2}
        mods = crud.build_modifiers_dict(item, negative=True, enhancement_bonuses=enhancement_bonuses)
        assert mods["intelligence"] == -10  # -(8 + 2*1)


# ===========================================================================
# Security tests
# ===========================================================================

class TestSharpeningSecurity:

    def test_sharpen_no_auth_401(self, client):
        resp = client.post("/inventory/crafting/1/sharpen", json={
            "inventory_item_id": 1,
            "whetstone_item_id": 2,
            "stat_field": "strength_modifier",
        })
        assert resp.status_code == 401

    def test_sharpen_wrong_character_403(self, sharpen_env):
        db = sharpen_env["db"]
        c = sharpen_env["client"]

        _insert_character(db, 2, user_id=999, name="OtherPlayer")
        db.commit()

        resp = c.post("/inventory/crafting/2/sharpen", json={
            "inventory_item_id": 1,
            "whetstone_item_id": 2,
            "stat_field": "strength_modifier",
        })
        assert resp.status_code == 403

    def test_sharpen_no_profession_400(self, sharpen_env):
        """Character without profession tries to sharpen."""
        db = sharpen_env["db"]
        c = sharpen_env["client"]

        _insert_character(db, 3, user_id=1, name="NoProfChar")
        db.commit()

        resp = c.post("/inventory/crafting/3/sharpen", json={
            "inventory_item_id": 1,
            "whetstone_item_id": 2,
            "stat_field": "strength_modifier",
        })
        assert resp.status_code == 400
        assert "нет профессии" in resp.json()["detail"]
