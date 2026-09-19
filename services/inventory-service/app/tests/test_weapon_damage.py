"""
FEAT-167 — inventory-service owns the weapon-damage number.

Two guarantees are pinned here:

1. `crud.compute_item_damage()` is THE single source of a concrete item
   instance's damage: template `damage_modifier` + 1 per sharpening point on
   `damage_modifier` + every socketed gem's `damage_modifier`, and `0.0` for a
   broken item (`max_durability > 0 and current_durability <= 0`).
2. Weapon damage never reaches `character_attributes.damage` again:
   `build_modifiers_dict(..., slot_type="main_weapon"|"additional_weapons")`
   drops the `damage` key, while armour / jewellery keep theirs. The number is
   published per slot instead, as `effective_damage` on
   `GET /inventory/{cid}/equipment`.

The equipment-endpoint assertions read the value back through the HTTP response
after writing real rows (real column names: `enhancement_bonuses`,
`socketed_gems`, `current_durability`), so a typo in a column name or a silently
swallowed error cannot pass as green.
"""

import json

import pytest

import crud
import models


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_item(db, name, item_type="weapon", damage_modifier=0,
               max_durability=0, **extra):
    item = models.Items(
        name=name,
        item_type=item_type,
        item_rarity="common",
        item_level=1,
        damage_modifier=damage_modifier,
        max_durability=max_durability,
        **extra,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _equip(db, character_id, slot_type, item, enhancement_bonuses=None,
           socketed_gems=None, current_durability=None):
    slot = models.EquipmentSlot(
        character_id=character_id,
        slot_type=slot_type,
        item_id=item.id if item else None,
        is_enabled=True,
        enhancement_points_spent=sum((enhancement_bonuses or {}).values()),
        enhancement_bonuses=json.dumps(enhancement_bonuses) if enhancement_bonuses else None,
        socketed_gems=json.dumps(socketed_gems) if socketed_gems else None,
        current_durability=current_durability,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


# ══════════════════════════════════════════════════════════════════════════════
# 1. compute_item_damage — the single source
# ══════════════════════════════════════════════════════════════════════════════


class TestComputeItemDamage:

    def test_plain_weapon_is_its_template_value(self, db_session):
        sword = _make_item(db_session, "Меч", damage_modifier=10)
        assert crud.compute_item_damage(sword) == 10.0

    def test_zero_damage_item_is_zero(self, db_session):
        cloth = _make_item(db_session, "Тряпка", item_type="body", damage_modifier=0)
        assert crud.compute_item_damage(cloth) == 0.0

    def test_sharpening_adds_one_per_point(self, db_session):
        sword = _make_item(db_session, "Меч заточенный", damage_modifier=10)
        assert crud.compute_item_damage(
            sword, enhancement_bonuses={"damage_modifier": 5}
        ) == 15.0

    def test_sharpening_of_another_stat_does_not_add_damage(self, db_session):
        sword = _make_item(db_session, "Меч силовой", damage_modifier=10)
        assert crud.compute_item_damage(
            sword, enhancement_bonuses={"strength_modifier": 5}
        ) == 10.0

    def test_socketed_gems_add_their_damage(self, db_session):
        sword = _make_item(db_session, "Меч с камнями", damage_modifier=10)
        gem_a = _make_item(db_session, "Рубин", item_type="gem", damage_modifier=3)
        gem_b = _make_item(db_session, "Топаз", item_type="gem", damage_modifier=4)
        assert crud.compute_item_damage(sword, gem_items=[gem_a, gem_b]) == 17.0

    def test_gem_without_damage_adds_nothing(self, db_session):
        sword = _make_item(db_session, "Меч с изумрудом", damage_modifier=10)
        gem = _make_item(db_session, "Изумруд", item_type="gem",
                         damage_modifier=0, strength_modifier=5)
        assert crud.compute_item_damage(sword, gem_items=[gem]) == 10.0

    def test_sharpening_and_gems_combine(self, db_session):
        staff = _make_item(db_session, "Посох", damage_modifier=500)
        gem = _make_item(db_session, "Сапфир", item_type="gem", damage_modifier=12)
        assert crud.compute_item_damage(
            staff, enhancement_bonuses={"damage_modifier": 5}, gem_items=[gem]
        ) == 517.0

    def test_broken_weapon_is_zero(self, db_session):
        sword = _make_item(db_session, "Меч сломанный", damage_modifier=25,
                           max_durability=60)
        assert crud.compute_item_damage(
            sword, current_durability=0, max_durability=60
        ) == 0.0

    def test_broken_weapon_is_zero_even_when_sharpened_and_gemmed(self, db_session):
        sword = _make_item(db_session, "Меч сломанный+", damage_modifier=25,
                           max_durability=60)
        gem = _make_item(db_session, "Гранат", item_type="gem", damage_modifier=7)
        assert crud.compute_item_damage(
            sword, enhancement_bonuses={"damage_modifier": 3}, gem_items=[gem],
            current_durability=0, max_durability=60,
        ) == 0.0

    def test_damaged_but_not_broken_keeps_full_damage(self, db_session):
        sword = _make_item(db_session, "Меч поцарапанный", damage_modifier=25,
                           max_durability=60)
        assert crud.compute_item_damage(
            sword, current_durability=1, max_durability=60
        ) == 25.0

    def test_indestructible_item_with_null_durability_is_not_broken(self, db_session):
        sword = _make_item(db_session, "Меч вечный", damage_modifier=25,
                           max_durability=0)
        assert crud.compute_item_damage(
            sword, current_durability=None, max_durability=0
        ) == 25.0


# ══════════════════════════════════════════════════════════════════════════════
# 2. build_modifiers_dict — weapon damage must not enter the attribute
# ══════════════════════════════════════════════════════════════════════════════


class TestWeaponDamageNeverEntersTheAttribute:

    @pytest.mark.parametrize("slot_type", ["main_weapon", "additional_weapons"])
    def test_weapon_slot_drops_the_damage_key(self, db_session, slot_type):
        sword = _make_item(db_session, f"Меч {slot_type}", damage_modifier=10,
                           strength_modifier=10)
        mods = crud.build_modifiers_dict(sword, slot_type=slot_type)
        assert "damage" not in mods, (
            "weapon damage leaked into the modifiers sent to "
            "character-attributes-service — this is the FEAT-167 double count"
        )
        assert mods["strength"] == 10  # the rest of the weapon still applies

    @pytest.mark.parametrize("slot_type", ["main_weapon", "additional_weapons"])
    def test_weapon_sharpening_and_gems_do_not_leak_either(self, db_session, slot_type):
        sword = _make_item(db_session, f"Меч точ {slot_type}", damage_modifier=10)
        gem = _make_item(db_session, f"Камень {slot_type}", item_type="gem",
                         damage_modifier=4)
        mods = crud.build_modifiers_dict(
            sword, enhancement_bonuses={"damage_modifier": 3}, gem_items=[gem],
            slot_type=slot_type,
        )
        assert "damage" not in mods

    def test_armour_damage_still_goes_into_the_attribute(self, db_session):
        plate = _make_item(db_session, "Кираса", item_type="body",
                           damage_modifier=6)
        mods = crud.build_modifiers_dict(plate, slot_type="body")
        assert mods["damage"] == 6.0

    def test_jewellery_sharpening_and_gems_still_go_into_the_attribute(self, db_session):
        ring = _make_item(db_session, "Кольцо", item_type="ring",
                          damage_modifier=2)
        gem = _make_item(db_session, "Алмаз", item_type="gem", damage_modifier=3)
        mods = crud.build_modifiers_dict(
            ring, enhancement_bonuses={"damage_modifier": 1}, gem_items=[gem],
            slot_type="ring",
        )
        # 2 (template) + 1 (sharpening) + 3 (gem) — the same arithmetic as the
        # single source, taken from it
        assert mods["damage"] == 6.0
        assert mods["damage"] == crud.compute_item_damage(
            ring, enhancement_bonuses={"damage_modifier": 1}, gem_items=[gem]
        )

    def test_bag_item_without_slot_type_keeps_damage(self, db_session):
        """`slot_type=None` is the display / bag case (e.g. the food payload) —
        behaviour is unchanged there."""
        sword = _make_item(db_session, "Меч в сумке", damage_modifier=10)
        assert crud.build_modifiers_dict(sword)["damage"] == 10.0

    def test_negative_flip_still_applies_to_the_remaining_keys(self, db_session):
        """Unequip sends the negated dict; the weapon's `damage` must be absent
        in both directions, otherwise equip/unequip would not cancel out."""
        sword = _make_item(db_session, "Меч снимаемый", damage_modifier=10,
                           strength_modifier=10)
        positive = crud.build_modifiers_dict(sword, slot_type="main_weapon")
        negative = crud.build_modifiers_dict(sword, negative=True,
                                             slot_type="main_weapon")
        assert "damage" not in positive and "damage" not in negative
        assert negative["strength"] == -positive["strength"]

    def test_broken_weapon_yields_no_modifiers_at_all(self, db_session):
        sword = _make_item(db_session, "Меч разбитый", damage_modifier=25,
                           strength_modifier=5, max_durability=60)
        assert crud.build_modifiers_dict(
            sword, current_durability=0, max_durability=60,
            slot_type="main_weapon",
        ) == {}

    def test_build_modifiers_dict_takes_damage_from_the_single_source(self, db_session):
        """Anti-drift: for a non-weapon slot the `damage` value must be exactly
        what `compute_item_damage` returns, not a second copy of the arithmetic."""
        belt = _make_item(db_session, "Пояс", item_type="belt", damage_modifier=4)
        gem = _make_item(db_session, "Оникс", item_type="gem", damage_modifier=2)
        for bonuses in ({}, {"damage_modifier": 2}, {"damage_modifier": 7}):
            mods = crud.build_modifiers_dict(
                belt, enhancement_bonuses=bonuses or None, gem_items=[gem],
                slot_type="belt",
            )
            expected = crud.compute_item_damage(
                belt, enhancement_bonuses=bonuses or None, gem_items=[gem]
            )
            assert mods.get("damage", 0) == expected


# ══════════════════════════════════════════════════════════════════════════════
# 3. GET /inventory/{cid}/equipment — effective_damage per slot
# ══════════════════════════════════════════════════════════════════════════════


class TestEffectiveDamageOnEquipmentResponse:

    @pytest.fixture(autouse=True)
    def _owner(self, private_viewer):
        """FEAT-171: `/inventory/{cid}/equipment` is owner-gated now.

        These tests read the OWNER's own body, which must stay byte-identical
        to the pre-gate payload — so they keep hitting the player route.
        """
        private_viewer(character_id=7, user_id=1,
                       extra_characters=[(cid, 1) for cid in range(8, 15)])

    def _slots_by_type(self, response):
        assert response.status_code == 200, response.text
        return {slot["slot_type"]: slot for slot in response.json()}

    def test_plain_weapon_reports_template_damage(self, client, db_session):
        sword = _make_item(db_session, "Меч простой", damage_modifier=10)
        _equip(db_session, 7, "main_weapon", sword)

        slots = self._slots_by_type(client.get("/inventory/7/equipment"))
        assert slots["main_weapon"]["effective_damage"] == 10.0

    def test_sharpened_and_gemmed_weapon_reports_the_effective_value(
        self, client, db_session
    ):
        staff = _make_item(db_session, "Посох боевой", damage_modifier=500)
        gem = _make_item(db_session, "Сапфир большой", item_type="gem",
                         damage_modifier=12)
        slot = _equip(db_session, 8, "main_weapon", staff,
                      enhancement_bonuses={"damage_modifier": 5},
                      socketed_gems=[gem.id, None])

        slots = self._slots_by_type(client.get("/inventory/8/equipment"))
        assert slots["main_weapon"]["effective_damage"] == 517.0

        # read the row back: the JSON columns really hold what we think they do
        db_session.expire_all()
        stored = db_session.get(models.EquipmentSlot, slot.id)
        assert json.loads(stored.enhancement_bonuses) == {"damage_modifier": 5}
        assert json.loads(stored.socketed_gems) == [gem.id, None]
        assert crud.get_enhancement_bonuses(stored) == {"damage_modifier": 5}

    def test_each_hand_reports_its_own_number(self, client, db_session):
        sword = _make_item(db_session, "Меч руки", damage_modifier=10)
        dagger = _make_item(db_session, "Кинжал руки", damage_modifier=4)
        _equip(db_session, 9, "main_weapon", sword)
        _equip(db_session, 9, "additional_weapons", dagger)

        slots = self._slots_by_type(client.get("/inventory/9/equipment"))
        assert slots["main_weapon"]["effective_damage"] == 10.0
        assert slots["additional_weapons"]["effective_damage"] == 4.0
        assert (slots["main_weapon"]["effective_damage"]
                != slots["additional_weapons"]["effective_damage"])

    def test_broken_weapon_reports_zero(self, client, db_session):
        sword = _make_item(db_session, "Меч негодный", damage_modifier=25,
                           max_durability=60)
        _equip(db_session, 10, "main_weapon", sword, current_durability=0)

        slots = self._slots_by_type(client.get("/inventory/10/equipment"))
        assert slots["main_weapon"]["effective_damage"] == 0.0
        # the item itself is still reported, so the battle keeps its damage type
        assert slots["main_weapon"]["item"]["id"] == sword.id

    def test_empty_slot_reports_zero(self, client, db_session):
        _equip(db_session, 11, "main_weapon", None)
        slots = self._slots_by_type(client.get("/inventory/11/equipment"))
        assert slots["main_weapon"]["effective_damage"] == 0.0

    def test_armour_slot_reports_zero_even_with_damage_modifier(
        self, client, db_session
    ):
        """Armour damage belongs to the base attribute, not to a hand — the slot
        must not publish it as weapon damage as well (that would double-count)."""
        plate = _make_item(db_session, "Кираса тяжёлая", item_type="body",
                           damage_modifier=6)
        _equip(db_session, 12, "body", plate)

        slots = self._slots_by_type(client.get("/inventory/12/equipment"))
        assert slots["body"]["effective_damage"] == 0.0

    def test_response_still_carries_every_slot_field(self, client, db_session):
        """`effective_damage` is additive: existing consumers (battle-service
        `fetch_weapons`, the profile, the admin NPC editors) must still find all
        the fields they read."""
        sword = _make_item(db_session, "Меч полный", damage_modifier=10)
        _equip(db_session, 13, "main_weapon", sword, current_durability=57)

        slots = self._slots_by_type(client.get("/inventory/13/equipment"))
        main = slots["main_weapon"]
        for field in ("id", "character_id", "slot_type", "item_id", "is_enabled",
                      "enhancement_points_spent", "enhancement_bonuses",
                      "socketed_gems", "current_durability", "item",
                      "effective_damage"):
            assert field in main, f"field {field} disappeared from the slot payload"
        assert main["current_durability"] == 57

    def test_endpoint_matches_compute_item_damage_for_every_case(
        self, client, db_session
    ):
        """Parity between the published field and the single source, on one
        character carrying a plain, a sharpened+gemmed and a broken weapon."""
        sword = _make_item(db_session, "Меч парный", damage_modifier=10)
        axe = _make_item(db_session, "Топор парный", damage_modifier=8,
                         max_durability=40)
        gem = _make_item(db_session, "Камень парный", item_type="gem",
                         damage_modifier=3)
        _equip(db_session, 14, "main_weapon", sword,
               enhancement_bonuses={"damage_modifier": 2},
               socketed_gems=[gem.id])
        _equip(db_session, 14, "additional_weapons", axe, current_durability=0)

        slots = self._slots_by_type(client.get("/inventory/14/equipment"))
        assert slots["main_weapon"]["effective_damage"] == crud.compute_item_damage(
            sword, enhancement_bonuses={"damage_modifier": 2}, gem_items=[gem]
        ) == 15.0
        assert slots["additional_weapons"]["effective_damage"] == crud.compute_item_damage(
            axe, current_durability=0, max_durability=40
        ) == 0.0
