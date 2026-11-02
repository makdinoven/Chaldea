"""
FEAT-195: POST /inventory/internal/equipment-modifiers.

The gear-aware rebuild of derived stats in character-attributes-service asks
inventory "what does every listed character wear, in total". The numbers must
be exactly what equip applied (crud.build_modifiers_dict per slot): sharpening,
gems, durability (broken = nothing), slot type (weapon slots drop `damage`).

Covers: internal token (401 missing/wrong, 503 unconfigured), validation (422:
empty, > 500, zero/negative, strings/floats/bools, injection-ish payloads),
duplicates ignored, every requested id present, sums across slots, sharpening +
gems, broken item, weapon slot vs armour damage, read-only, parity with the
per-slot equip maths.
"""

import json

import pytest

import auth_http
import crud
import models

TOKEN = "test-internal-token-feat195"
HEADERS = {"X-Internal-Token": TOKEN}
URL = "/inventory/internal/equipment-modifiers"

HERO = 41
NAKED = 42
BROKEN = 43
STRANGER = 44  # has a bag item, nothing equipped


@pytest.fixture(autouse=True)
def _token_is_configured(monkeypatch):
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)


def _item(db, name, item_type="head", **mods):
    item = models.Items(name=name, item_type=item_type, item_rarity="common", item_level=1,
                        max_stack_size=1, is_unique=False, **mods)
    db.add(item)
    db.flush()
    return item


def _slot(db, character_id, slot_type, item, enhancement=None, gems=None, durability=None):
    slot = models.EquipmentSlot(character_id=character_id, slot_type=slot_type,
                                item_id=item.id if item else None, is_enabled=True,
                                enhancement_points_spent=sum((enhancement or {}).values()),
                                current_durability=durability)
    crud.set_enhancement_bonuses(slot, enhancement or {})
    crud.set_socketed_gems(slot, gems or [])
    db.add(slot)
    db.flush()
    return slot


@pytest.fixture()
def world(db_session):
    db = db_session
    gem = _item(db, "Рубин силы", item_type="gem", strength_modifier=4, res_fire_modifier=0.5)
    helmet = _item(db, "Шлем", strength_modifier=10, res_fire_modifier=2.0, luck_modifier=3)
    ring = _item(db, "Кольцо", item_type="ring", luck_modifier=5, critical_hit_chance_modifier=1.5)
    sword = _item(db, "Меч", item_type="weapon", damage_modifier=12, strength_modifier=6)
    amulet = _item(db, "Амулет урона", item_type="necklace", damage_modifier=3, health_modifier=20)
    armour = _item(db, "Сломанная броня", item_type="body", strength_modifier=50,
                   max_durability=100, dodge_modifier=2.0)

    # HERO: sharpened helmet, ring with two gems (one socket empty), sword in hand,
    # amulet (non-weapon damage), plus an empty slot.
    _slot(db, HERO, "head", helmet, enhancement={"strength_modifier": 3, "res_fire_modifier": 2,
                                                "critical_hit_chance_modifier": 2})
    _slot(db, HERO, "ring", ring, gems=[gem.id, None, gem.id])
    _slot(db, HERO, "main_weapon", sword, enhancement={"damage_modifier": 4})
    _slot(db, HERO, "necklace", amulet, durability=None)
    _slot(db, HERO, "belt", None)

    _slot(db, NAKED, "head", None)

    _slot(db, BROKEN, "body", armour, durability=0)
    _slot(db, BROKEN, "head", helmet, durability=None)

    db.add(models.CharacterInventory(character_id=STRANGER, item_id=helmet.id, quantity=1))
    db.commit()
    return dict(gem=gem, helmet=helmet, ring=ring, sword=sword, amulet=amulet, armour=armour)


def _post(client, ids, headers=HEADERS):
    return client.post(URL, json={"character_ids": ids}, headers=headers)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:

    def test_missing_token_401(self, client, world):
        assert _post(client, [HERO], headers={}).status_code == 401

    def test_wrong_token_401(self, client, world):
        assert _post(client, [HERO], headers={"X-Internal-Token": "nope"}).status_code == 401

    def test_unconfigured_token_503(self, client, world, monkeypatch):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        assert _post(client, [HERO], headers={"X-Internal-Token": ""}).status_code == 503

    def test_user_jwt_is_not_enough(self, client, world):
        resp = _post(client, [HERO], headers={"Authorization": "Bearer some.jwt.token"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:

    @pytest.mark.parametrize("body", [
        {"character_ids": []},
        {"character_ids": list(range(1, 502))},
        {"character_ids": [0]},
        {"character_ids": [-5]},
        {"character_ids": [HERO, -1]},
        {"character_ids": ["41"]},
        {"character_ids": [41.0]},
        {"character_ids": [True]},
        {"character_ids": [None]},
        {"character_ids": "41"},
        {"character_ids": ["1 OR 1=1"]},
        {"character_ids": ["1); DROP TABLE equipment_slots; --"]},
        {"ids": [41]},
        {},
    ])
    def test_invalid_payload_422(self, client, world, body):
        resp = client.post(URL, json=body, headers=HEADERS)
        assert resp.status_code == 422, resp.text

    def test_exactly_500_is_allowed(self, client, world):
        resp = _post(client, list(range(1, 501)))
        assert resp.status_code == 200
        assert len(resp.json()["modifiers"]) == 500

    def test_duplicates_ignored(self, client, world):
        resp = _post(client, [HERO, HERO, NAKED, HERO])
        assert resp.status_code == 200
        assert sorted(resp.json()["modifiers"]) == sorted([str(HERO), str(NAKED)])

    def test_injection_payload_leaves_table_intact(self, client, world, db_session):
        client.post(URL, json={"character_ids": ["1; DROP TABLE equipment_slots"]}, headers=HEADERS)
        assert db_session.query(models.EquipmentSlot).count() == 8


# ---------------------------------------------------------------------------
# Sums
# ---------------------------------------------------------------------------

class TestSums:

    def test_every_requested_id_present(self, client, world):
        resp = _post(client, [NAKED, STRANGER, 999999])
        assert resp.status_code == 200
        assert resp.json() == {"modifiers": {str(NAKED): {}, str(STRANGER): {}, "999999": {}}}

    def test_hero_total_with_sharpening_gems_and_slot_types(self, client, world):
        mods = _post(client, [HERO]).json()["modifiers"][str(HERO)]
        # strength: helmet 10 + sharpening 3 + two gems 4+4 + sword 6
        assert mods["strength"] == pytest.approx(27)
        # res_fire: helmet 2.0 + sharpening 2*0.1 + gems 0.5+0.5
        assert mods["res_fire"] == pytest.approx(3.2)
        # luck: helmet 3 + ring 5
        assert mods["luck"] == pytest.approx(8)
        # crit: ring 1.5 + helmet sharpening 2*0.5
        assert mods["critical_hit_chance"] == pytest.approx(2.5)
        # damage: sword sits in a weapon slot -> dropped (even its sharpening);
        # the amulet's damage counts
        assert mods["damage"] == pytest.approx(3)
        assert mods["health"] == pytest.approx(20)
        assert set(mods) == {"strength", "res_fire", "luck", "critical_hit_chance",
                             "damage", "health"}

    def test_broken_item_contributes_nothing(self, client, world):
        mods = _post(client, [BROKEN]).json()["modifiers"][str(BROKEN)]
        assert mods == {"strength": 10, "res_fire": 2.0, "luck": 3}
        assert "dodge" not in mods

    def test_batch_keeps_characters_apart(self, client, world):
        body = _post(client, [HERO, BROKEN, NAKED]).json()["modifiers"]
        assert body[str(BROKEN)]["strength"] == 10
        assert body[str(HERO)]["strength"] == 27
        assert body[str(NAKED)] == {}

    def test_matches_per_slot_equip_maths(self, client, world, db_session):
        """The endpoint is exactly the sum of what equip sent for every slot."""
        expected = {}
        for slot in db_session.query(models.EquipmentSlot).filter_by(character_id=HERO).all():
            if not slot.item_id:
                continue
            item = db_session.query(models.Items).get(slot.item_id)
            gems = crud.get_socketed_gems(slot)
            for k, v in crud.build_modifiers_dict(
                item, enhancement_bonuses=crud.get_enhancement_bonuses(slot),
                gem_items=crud.load_gem_items(db_session, gems) if gems else [],
                current_durability=slot.current_durability,
                max_durability=item.max_durability, slot_type=slot.slot_type,
            ).items():
                expected[k] = expected.get(k, 0) + v
        got = _post(client, [HERO]).json()["modifiers"][str(HERO)]
        assert set(got) == {k for k, v in expected.items() if v}
        for k, v in got.items():
            assert v == pytest.approx(expected[k])

    def test_equip_then_unequip_nets_to_zero(self, client, world, db_session):
        """Negated per-slot dicts (what unequip sends) cancel the endpoint total."""
        total = _post(client, [HERO]).json()["modifiers"][str(HERO)]
        for slot in db_session.query(models.EquipmentSlot).filter_by(character_id=HERO).all():
            if not slot.item_id:
                continue
            item = db_session.query(models.Items).get(slot.item_id)
            gems = crud.get_socketed_gems(slot)
            for k, v in crud.build_modifiers_dict(
                item, negative=True, enhancement_bonuses=crud.get_enhancement_bonuses(slot),
                gem_items=crud.load_gem_items(db_session, gems) if gems else [],
                current_durability=slot.current_durability,
                max_durability=item.max_durability, slot_type=slot.slot_type,
            ).items():
                total[k] = total.get(k, 0) + v
        assert all(v == pytest.approx(0) for v in total.values())

    def test_read_only(self, client, world, db_session):
        def dump():
            db_session.expire_all()
            return [(s.id, s.character_id, s.item_id, s.enhancement_bonuses, s.socketed_gems,
                     s.current_durability) for s in db_session.query(models.EquipmentSlot).all()]
        before = dump()
        assert _post(client, [HERO, BROKEN]).status_code == 200
        assert dump() == before

    def test_gem_missing_from_items_is_ignored(self, client, world, db_session):
        slot = db_session.query(models.EquipmentSlot).filter_by(
            character_id=NAKED, slot_type="head").one()
        slot.item_id = world["ring"].id
        slot.socketed_gems = json.dumps([987654])
        db_session.commit()
        mods = _post(client, [NAKED]).json()["modifiers"][str(NAKED)]
        assert mods == {"luck": 5, "critical_hit_chance": 1.5}
