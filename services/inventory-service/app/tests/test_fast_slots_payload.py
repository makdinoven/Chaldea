"""
FEAT-168 §3.3.3 — the fast-slot payload is the ONLY channel that carries an
item's battle configuration into a battle.

`battle-service/app/inventory_client.get_fast_slots` reads this response with
`.get(key, default)` everywhere, so a key that quietly disappears from here
does NOT raise anywhere: the item simply loses its effects and behaves like a
plain recovery potion. That is exactly the project's silent-failure pattern, so
the guard below is explicit — `test_effect_rows_reach_the_fast_slot_payload`
fails the moment an item's `item_effects` rows stop reaching the slot.

Every key asserted here is a key battle-service actually reads
(`inventory_client.py:130-145`).
"""

from unittest.mock import MagicMock, patch

import pytest

import auth_http
import models


# FEAT-169: the belt is read by battle-service through the internal twin
# `GET /inventory/internal/characters/{cid}/fast_slots` (X-Internal-Token).
# The payload-shape tests below speak that route, because it is the one the
# battle engine actually consumes.
_TOKEN = "test-internal-token"
_INTERNAL_HEADERS = {"X-Internal-Token": _TOKEN}


@pytest.fixture(autouse=True)
def _internal_token(monkeypatch):
    """`verify_internal_token` reads a module-level constant — pin it."""
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", _TOKEN)


# Keys battle-service reads off each slot object.
SLOT_KEYS = (
    "slot_type", "item_id", "quantity", "name", "image",
    "health_recovery", "mana_recovery", "energy_recovery", "stamina_recovery",
    "consumable_action", "coating_turns", "coating_bonus_damage",
    "effects", "damage_entries",
)

# Keys `buffs.apply_new_effects` / `battle_engine.compute_damage_with_rolls`
# read off each nested row.
EFFECT_ROW_KEYS = (
    "target_side", "effect_name", "chance", "duration", "magnitude", "attribute_key",
)
DAMAGE_ROW_KEYS = (
    "damage_type", "amount", "weapon_slot", "target_side", "chance",
    "aoe_shape", "aoe_falloff", "aoe_max_targets",
)


HEADERS = {"Authorization": "Bearer admin-token"}
ADMIN = {"id": 1, "username": "admin", "role": "admin",
         "permissions": ["items:create", "items:update"]}


def _auth_ok():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = ADMIN
    return resp


def _create_item_via_admin(client, **overrides):
    body = {
        "name": "Зелье силы",
        "item_level": 1,
        "item_type": "consumable",
        "item_rarity": "common",
        "max_stack_size": 10,
        "is_unique": False,
    }
    body.update(overrides)
    with patch("auth_http.requests.get", return_value=_auth_ok()):
        resp = client.post("/inventory/items", json=body, headers=HEADERS)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _equip_fast_slot(db_session, character_id, item_id, quantity=3,
                     slot_type="fast_slot_1"):
    db_session.add(models.CharacterInventory(
        character_id=character_id, item_id=item_id, quantity=quantity))
    db_session.add(models.EquipmentSlot(
        character_id=character_id, slot_type=slot_type,
        item_id=item_id, is_enabled=True))
    db_session.commit()


def _fast_slots(client, character_id=1):
    resp = client.get(
        f"/inventory/internal/characters/{character_id}/fast_slots",
        headers=_INTERNAL_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


_EFFECT = {
    "target_side": "self", "effect_name": "StatModifier", "description": "Сила",
    "chance": 100, "duration": 3, "magnitude": 5.0, "attribute_key": "strength",
}
_DAMAGE = {
    "damage_type": "fire", "amount": 30.0, "weapon_slot": "no_weapon",
    "target_side": "enemy", "chance": 100, "aoe_shape": "single",
    "aoe_falloff": 50, "aoe_max_targets": 3,
}


class TestFastSlotPayloadShape:

    def test_every_key_battle_service_reads_is_present(self, client, db_session):
        item_id = _create_item_via_admin(
            client,
            health_recovery=30, mana_recovery=10,
            energy_recovery=5, stamina_recovery=7,
            effects=[_EFFECT], damage_entries=[_DAMAGE],
        )
        _equip_fast_slot(db_session, 1, item_id, quantity=4)

        slots = _fast_slots(client)
        assert len(slots) == 1
        slot = slots[0]

        missing = [k for k in SLOT_KEYS if k not in slot]
        assert not missing, f"battle-service читает эти ключи, а их нет: {missing}"

        assert slot["slot_type"] == "fast_slot_1"
        assert slot["item_id"] == item_id
        assert slot["quantity"] == 4
        assert slot["name"] == "Зелье силы"
        assert slot["health_recovery"] == 30
        assert slot["mana_recovery"] == 10
        assert slot["energy_recovery"] == 5
        assert slot["stamina_recovery"] == 7

    def test_effect_rows_reach_the_fast_slot_payload(self, client, db_session):
        """ANTI-SILENT-FAILURE GUARD.

        battle-service reads `slot.get("effects") or []`: if the rows stop
        arriving, nothing raises anywhere — the potion just stops working.
        """
        item_id = _create_item_via_admin(client, effects=[_EFFECT])
        _equip_fast_slot(db_session, 1, item_id)

        # the rows really exist in the DB…
        assert db_session.query(models.ItemEffect).filter_by(item_id=item_id).count() == 1

        slot = _fast_slots(client)[0]

        # …so they must be in the payload, with every key the engine reads
        assert slot["effects"], "эффекты предмета не доехали до быстрого слота"
        row = slot["effects"][0]
        missing = [k for k in EFFECT_ROW_KEYS if k not in row]
        assert not missing, f"движок читает эти ключи строки эффекта, а их нет: {missing}"
        assert row["target_side"] == "self"
        assert row["effect_name"] == "StatModifier"
        assert row["attribute_key"] == "strength"
        assert row["magnitude"] == 5.0
        assert row["duration"] == 3
        assert row["chance"] == 100

    def test_damage_rows_reach_the_fast_slot_payload(self, client, db_session):
        item_id = _create_item_via_admin(client, name="Свиток огня",
                                         item_type="scroll", damage_entries=[_DAMAGE])
        _equip_fast_slot(db_session, 1, item_id)

        slot = _fast_slots(client)[0]
        assert slot["damage_entries"], "строки урона не доехали до быстрого слота"
        row = slot["damage_entries"][0]
        missing = [k for k in DAMAGE_ROW_KEYS if k not in row]
        assert not missing, f"движок читает эти ключи строки урона, а их нет: {missing}"
        assert row["damage_type"] == "fire"
        assert row["amount"] == 30.0
        assert row["weapon_slot"] == "no_weapon"

    def test_coating_fields_reach_the_payload(self, client, db_session):
        item_id = _create_item_via_admin(
            client, name="Яд гадюки", consumable_action="weapon_coating",
            coating_turns=4, coating_bonus_damage=12.0,
            effects=[dict(_EFFECT, target_side="enemy", effect_name="Poison",
                          attribute_key="periodic_damage", magnitude=-6.0)],
        )
        _equip_fast_slot(db_session, 1, item_id)

        slot = _fast_slots(client)[0]
        assert slot["consumable_action"] == "weapon_coating"
        assert slot["coating_turns"] == 4
        assert slot["coating_bonus_damage"] == 12.0
        assert slot["effects"][0]["effect_name"] == "Poison"

    def test_plain_item_gets_empty_lists_and_zero_recovery(self, client, db_session):
        item_id = _create_item_via_admin(client, name="Простое зелье")
        _equip_fast_slot(db_session, 1, item_id)

        slot = _fast_slots(client)[0]
        assert slot["effects"] == []
        assert slot["damage_entries"] == []
        assert slot["consumable_action"] is None
        assert slot["coating_turns"] is None
        assert slot["coating_bonus_damage"] is None
        assert slot["health_recovery"] == 0
        assert slot["mana_recovery"] == 0

    def test_quantity_sums_every_inventory_stack(self, client, db_session):
        item_id = _create_item_via_admin(client, name="Стопка", effects=[_EFFECT])
        _equip_fast_slot(db_session, 1, item_id, quantity=7)
        db_session.add(models.CharacterInventory(
            character_id=1, item_id=item_id, quantity=3))
        db_session.commit()

        slot = _fast_slots(client)[0]
        assert slot["quantity"] == 10
        assert len(slot["effects"]) == 1, "вторая стопка не должна ломать эффекты"

    def test_several_slots_keep_their_own_effects(self, client, db_session):
        buff_id = _create_item_via_admin(client, name="Зелье силы", effects=[_EFFECT])
        scroll_id = _create_item_via_admin(client, name="Свиток огня",
                                           item_type="scroll", damage_entries=[_DAMAGE])
        _equip_fast_slot(db_session, 1, buff_id, slot_type="fast_slot_1")
        _equip_fast_slot(db_session, 1, scroll_id, slot_type="fast_slot_2")

        by_slot = {s["slot_type"]: s for s in _fast_slots(client)}
        assert len(by_slot["fast_slot_1"]["effects"]) == 1
        assert by_slot["fast_slot_1"]["damage_entries"] == []
        assert by_slot["fast_slot_2"]["effects"] == []
        assert len(by_slot["fast_slot_2"]["damage_entries"]) == 1

    def test_disabled_slot_is_not_returned(self, client, db_session):
        item_id = _create_item_via_admin(client, name="Выключено", effects=[_EFFECT])
        db_session.add(models.CharacterInventory(
            character_id=1, item_id=item_id, quantity=1))
        db_session.add(models.EquipmentSlot(
            character_id=1, slot_type="fast_slot_3", item_id=item_id, is_enabled=False))
        db_session.commit()

        assert _fast_slots(client) == []

    def test_editing_the_item_updates_the_slot_payload(self, client, db_session):
        """Замена строк эффектов у предмета сразу видна в поясе."""
        item_id = _create_item_via_admin(client, effects=[_EFFECT])
        _equip_fast_slot(db_session, 1, item_id)
        assert len(_fast_slots(client)[0]["effects"]) == 1

        with patch("auth_http.requests.get", return_value=_auth_ok()):
            resp = client.put(
                f"/inventory/items/{item_id}",
                json={
                    "name": "Зелье силы", "item_level": 1, "item_type": "consumable",
                    "item_rarity": "common", "max_stack_size": 10, "is_unique": False,
                    "effects": [],
                },
                headers=HEADERS,
            )
        assert resp.status_code == 200, resp.text
        assert _fast_slots(client)[0]["effects"] == []


class TestFastSlotsAuth:

    def test_fast_slots_requires_auth(self, client, db_session):
        """FEAT-169: игровой маршрут пояса требует JWT (дыра закрыта)."""
        item_id = _create_item_via_admin(client, name="Чужое зелье")
        _equip_fast_slot(db_session, 2, item_id)

        resp = client.get("/inventory/characters/2/fast_slots")
        assert resp.status_code in (401, 403), (
            "пояс чужого персонажа отдаётся без токена"
        )
