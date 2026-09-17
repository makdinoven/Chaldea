"""
FEAT-165 — sharpening stone groups.

weapon_armor stones -> weapon/body/head, cloak_belt -> cloak/belt,
jewelry -> ring/necklace/bracelet. Anyone with a matching stone may sharpen;
a mismatched stone is rejected before anything is consumed; no profession XP.
Stone quantities and enhancement data are read back from the DB.
"""

import json
from unittest.mock import patch, AsyncMock

import pytest

import crud
import models
from auth_http import get_current_user_via_http
from main import app
from tests.feat165_helpers import (
    OWNER, ensure_characters, seed_professions, assign_profession, make_item,
    make_stone, add_stack, owned_quantity, profession_state, put_in_battle,
    start_gathering,
)

STONES = {"weapon_armor": 20, "cloak_belt": 21, "jewelry": 22}
GROUP_OF_TYPE = {
    "weapon": "weapon_armor", "body": "weapon_armor", "head": "weapon_armor",
    "cloak": "cloak_belt", "belt": "cloak_belt",
    "ring": "jewelry", "necklace": "jewelry", "bracelet": "jewelry",
}
ALWAYS_SUCCEEDS = 0.0


@pytest.fixture()
def env(client, db_session):
    ensure_characters(db_session)
    seed_professions(db_session)
    for group, item_id in STONES.items():
        make_stone(db_session, item_id, f"Камень {group}", group, level=1)
        add_stack(db_session, 1, item_id, 5)
    app.dependency_overrides[get_current_user_via_http] = lambda: OWNER
    yield {"client": client, "db": db_session}
    app.dependency_overrides.pop(get_current_user_via_http, None)


def _gear(db, item_type, item_id=None, character_id=1):
    item_id = item_id or 100 + list(GROUP_OF_TYPE).index(item_type)
    make_item(db, item_id, f"Предмет {item_type}", item_type=item_type,
              max_stack=1, strength_modifier=1)
    return add_stack(db, character_id, item_id, 1)


def _stone_row(db, group, character_id=1):
    db.expire_all()
    return db.query(models.CharacterInventory).filter(
        models.CharacterInventory.character_id == character_id,
        models.CharacterInventory.item_id == STONES[group],
    ).first()


def _sharpen(client, row_id, stone_row_id, source="inventory", stat="strength_modifier", character_id=1):
    return client.post(f"/inventory/crafting/{character_id}/sharpen", json={
        "inventory_item_id": row_id,
        "whetstone_item_id": stone_row_id,
        "stat_field": stat,
        "source": source,
    })


def _row(db, model, row_id):
    db.expire_all()
    return db.query(model).filter(model.id == row_id).first()


class TestGroupMapping:

    @pytest.mark.parametrize("item_type,group", list(GROUP_OF_TYPE.items()))
    def test_sharpen_group_for_type(self, item_type, group):
        assert crud.sharpen_group_for_type(item_type) == group

    @pytest.mark.parametrize("item_type", ["consumable", "resource", "gem", "rune", "recipe",
                                           "gathering_tool", "scroll", "misc", None])
    def test_not_sharpenable(self, item_type):
        assert crud.sharpen_group_for_type(item_type) is None


class TestMatchingStone:

    @pytest.mark.parametrize("item_type", list(GROUP_OF_TYPE))
    def test_matching_stone_sharpens_without_profession(self, env, item_type):
        db, c = env["db"], env["client"]
        gear = _gear(db, item_type)
        group = GROUP_OF_TYPE[item_type]
        stone = _stone_row(db, group)

        with patch("main.random.random", return_value=ALWAYS_SUCCEEDS):
            resp = _sharpen(c, gear.id, stone.id)

        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True
        assert "xp_earned" not in resp.json()
        assert _stone_row(db, group).quantity == 4
        stored = _row(db, models.CharacterInventory, gear.id)
        assert stored.enhancement_points_spent == 1
        assert json.loads(stored.enhancement_bonuses) == {"strength_modifier": 1}

    @pytest.mark.parametrize("item_type", list(GROUP_OF_TYPE))
    def test_every_other_group_is_rejected_and_not_consumed(self, env, item_type):
        db, c = env["db"], env["client"]
        gear = _gear(db, item_type)
        for group in STONES:
            if group == GROUP_OF_TYPE[item_type]:
                continue
            resp = _sharpen(c, gear.id, _stone_row(db, group).id)
            assert resp.status_code == 400, (group, resp.text)
            assert resp.json()["detail"] == "Этот камень не подходит для этого предмета"
            assert _stone_row(db, group).quantity == 5
        assert _row(db, models.CharacterInventory, gear.id).enhancement_points_spent == 0

    def test_stone_without_group_is_rejected(self, env):
        db, c = env["db"], env["client"]
        # legacy row: level set but no group (bypasses the API validator)
        make_item(db, 30, "Старый камень", subcategory="whetstone", whetstone_level=3)
        legacy = add_stack(db, 1, 30, 2)
        gear = _gear(db, "weapon")

        resp = _sharpen(c, gear.id, legacy.id)

        assert resp.status_code == 400
        assert owned_quantity(db, 1, 30) == 2

    def test_failed_roll_still_consumes_matching_stone(self, env):
        db, c = env["db"], env["client"]
        gear = _gear(db, "ring")

        with patch("main.random.random", return_value=0.99):
            resp = _sharpen(c, gear.id, _stone_row(db, "jewelry").id)

        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is False
        assert _stone_row(db, "jewelry").quantity == 4
        assert _row(db, models.CharacterInventory, gear.id).enhancement_points_spent == 0

    @pytest.mark.parametrize("slug", ["blacksmith", "alchemist", "cook", "enchanter", "jeweler", "scholar"])
    def test_any_profession_may_sharpen_and_gets_no_xp(self, env, slug):
        db, c = env["db"], env["client"]
        assign_profession(db, 1, slug, rank=1, experience=7)
        gear = _gear(db, "necklace")

        with patch("main.random.random", return_value=ALWAYS_SUCCEEDS):
            resp = _sharpen(c, gear.id, _stone_row(db, "jewelry").id)

        assert resp.status_code == 200, resp.text
        assert profession_state(db, 1) == (1, 7)

    def test_jewelry_budget_and_per_stat_cap(self, env):
        db, c = env["db"], env["client"]
        gear = _gear(db, "bracelet")
        stored = _row(db, models.CharacterInventory, gear.id)
        stored.enhancement_points_spent = crud.MAX_ENHANCEMENT_POINTS
        db.commit()

        resp = _sharpen(c, gear.id, _stone_row(db, "jewelry").id)
        assert resp.status_code == 400
        assert _stone_row(db, "jewelry").quantity == 5

        stored = _row(db, models.CharacterInventory, gear.id)
        stored.enhancement_points_spent = 5
        stored.enhancement_bonuses = json.dumps({"strength_modifier": crud.MAX_STAT_SHARPEN})
        db.commit()
        resp = _sharpen(c, gear.id, _stone_row(db, "jewelry").id)
        assert resp.status_code == 400
        assert _stone_row(db, "jewelry").quantity == 5


class TestEquippedJewelry:

    def test_equipped_ring_applies_delta(self, env):
        db, c = env["db"], env["client"]
        make_item(db, 150, "Кольцо силы", item_type="ring", max_stack=1)
        slot = models.EquipmentSlot(character_id=1, slot_type="ring", item_id=150, is_enabled=True)
        db.add(slot)
        db.commit()

        with patch("main.random.random", return_value=ALWAYS_SUCCEEDS), \
             patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock) as mock_apply:
            resp = _sharpen(c, slot.id, _stone_row(db, "jewelry").id, source="equipment",
                            stat="agility_modifier")

        assert resp.status_code == 200, resp.text
        mock_apply.assert_awaited_once_with(1, {"agility": 1})
        stored = _row(db, models.EquipmentSlot, slot.id)
        assert stored.enhancement_points_spent == 1
        assert json.loads(stored.enhancement_bonuses) == {"agility_modifier": 1}
        assert _stone_row(db, "jewelry").quantity == 4

    def test_equipped_cloak_rejects_weapon_stone(self, env):
        db, c = env["db"], env["client"]
        make_item(db, 151, "Плащ", item_type="cloak", max_stack=1)
        slot = models.EquipmentSlot(character_id=1, slot_type="cloak", item_id=151, is_enabled=True)
        db.add(slot)
        db.commit()

        with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock) as mock_apply:
            resp = _sharpen(c, slot.id, _stone_row(db, "weapon_armor").id, source="equipment")

        assert resp.status_code == 400
        mock_apply.assert_not_awaited()
        assert _stone_row(db, "weapon_armor").quantity == 5


class TestSharpenInfoGroups:

    def test_info_lists_only_matching_stones(self, env):
        db, c = env["db"], env["client"]
        make_stone(db, 23, "Резец мастера", "jewelry", level=3)
        add_stack(db, 1, 23, 1)
        gear = _gear(db, "ring")

        resp = c.get(f"/inventory/crafting/1/sharpen-info/{gear.id}?source=inventory")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["sharpen_group"] == "jewelry"
        stones = {s["name"]: s for s in data["whetstones"]}
        assert set(stones) == {"Камень jewelry", "Резец мастера"}
        assert all(s["whetstone_group"] == "jewelry" for s in stones.values())
        assert stones["Резец мастера"]["success_chance"] == 75
        assert data["points_remaining"] == crud.MAX_ENHANCEMENT_POINTS

    @pytest.mark.parametrize("item_type", ["belt", "head"])
    def test_info_group_for_other_types(self, env, item_type):
        db, c = env["db"], env["client"]
        gear = _gear(db, item_type)
        data = c.get(f"/inventory/crafting/1/sharpen-info/{gear.id}").json()
        assert data["sharpen_group"] == GROUP_OF_TYPE[item_type]
        assert [s["whetstone_group"] for s in data["whetstones"]] == [GROUP_OF_TYPE[item_type]]

    def test_info_non_sharpenable_400(self, env):
        db, c = env["db"], env["client"]
        make_item(db, 160, "Зелье", item_type="consumable")
        row = add_stack(db, 1, 160, 1)
        assert c.get(f"/inventory/crafting/1/sharpen-info/{row.id}").status_code == 400

    def test_info_foreign_character_403(self, env):
        assert env["client"].get("/inventory/crafting/2/sharpen-info/1").status_code == 403


class TestSharpenSecurity:

    def test_unauthenticated_401(self, client):
        assert client.post("/inventory/crafting/1/sharpen", json={
            "inventory_item_id": 1, "whetstone_item_id": 1, "stat_field": "strength_modifier",
        }).status_code == 401

    def test_foreign_character_403(self, env):
        db, c = env["db"], env["client"]
        gear = _gear(db, "ring", character_id=2)
        make_stone(db, 40, "Чужой резец", "jewelry")
        stone = add_stack(db, 2, 40, 3)

        resp = _sharpen(c, gear.id, stone.id, character_id=2)

        assert resp.status_code == 403
        assert owned_quantity(db, 2, 40) == 3

    def test_foreign_stone_row_not_usable(self, env):
        db, c = env["db"], env["client"]
        make_stone(db, 40, "Чужой резец", "jewelry")
        foreign_stone = add_stack(db, 2, 40, 3)
        gear = _gear(db, "ring")

        resp = _sharpen(c, gear.id, foreign_stone.id)

        assert resp.status_code == 400
        assert owned_quantity(db, 2, 40) == 3

    def test_blocked_in_battle(self, env):
        db, c = env["db"], env["client"]
        gear = _gear(db, "ring")
        stone = _stone_row(db, "jewelry")
        put_in_battle(db, 1)
        assert _sharpen(c, gear.id, stone.id).status_code == 400
        assert _stone_row(db, "jewelry").quantity == 5

    def test_blocked_while_gathering(self, env):
        db, c = env["db"], env["client"]
        gear = _gear(db, "ring")
        start_gathering(db, 1)
        resp = _sharpen(c, gear.id, _stone_row(db, "jewelry").id)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Нельзя затачивать предметы во время добычи"
        assert _stone_row(db, "jewelry").quantity == 5

    @pytest.mark.parametrize("stat", ["strength_modifier; DROP TABLE items", "id", "item_type", ""])
    def test_invalid_stat_field(self, env, stat):
        db, c = env["db"], env["client"]
        gear = _gear(db, "ring")
        resp = _sharpen(c, gear.id, _stone_row(db, "jewelry").id, stat=stat)
        assert resp.status_code == 400
        assert _stone_row(db, "jewelry").quantity == 5

    def test_invalid_source_value(self, env):
        db, c = env["db"], env["client"]
        gear = _gear(db, "ring")
        resp = c.get(f"/inventory/crafting/1/sharpen-info/{gear.id}?source=items;--")
        assert resp.status_code == 422
