"""
`POST /inventory/internal/update-durability` — the post-battle durability write.

This route had **no HTTP test at all** before FEAT-169 (analysis §2.4), even
though battle-service calls it after every fight and swallows the result
(`inventory_client.py:83` → `raise_for_status`, caller ignores). A regression
here loses durability writes and, worse, leaves a broken item's modifiers
applied — and nothing raises anywhere.

Covered: the durability actually persists, the clamp, the "just broke →
take the modifiers off" branch, and every skip branch. The auth matrix for the
same route lives in `test_internal_auth.py`.
"""

import pytest
from sqlalchemy import text

import auth_http
import main
import models


TOKEN = "test-internal-token"
HEADERS = {"X-Internal-Token": TOKEN}

CID = 1
ARMOR_ID = 6100
HELM_ID = 6101
RING_ID = 6102  # max_durability = 0 → indestructible


@pytest.fixture(autouse=True)
def _token_is_configured(monkeypatch):
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)


@pytest.fixture()
def applied(monkeypatch):
    """Capture the modifier-removal calls instead of doing real HTTP."""
    calls = []

    async def _fake(character_id, modifiers):
        calls.append((character_id, modifiers))

    monkeypatch.setattr(main, "apply_modifiers_in_attributes_service", _fake)
    return calls


@pytest.fixture()
def gear(client, db_session):
    db_session.add_all([
        models.Items(
            id=ARMOR_ID, name="Латный доспех", item_level=1, item_type="armor",
            item_rarity="rare", max_stack_size=1, is_unique=False,
            max_durability=50, health_modifier=10, strength_modifier=2,
        ),
        models.Items(
            id=HELM_ID, name="Шлем", item_level=1, item_type="armor",
            item_rarity="common", max_stack_size=1, is_unique=False,
            max_durability=30, health_modifier=4,
        ),
        models.Items(
            id=RING_ID, name="Кольцо", item_level=1, item_type="jewelry",
            item_rarity="common", max_stack_size=1, is_unique=False,
            max_durability=0, health_modifier=1,
        ),
    ])
    db_session.flush()
    db_session.add_all([
        models.EquipmentSlot(character_id=CID, slot_type="body",
                             item_id=ARMOR_ID, is_enabled=True, current_durability=42),
        models.EquipmentSlot(character_id=CID, slot_type="head",
                             item_id=HELM_ID, is_enabled=True, current_durability=30),
        models.EquipmentSlot(character_id=CID, slot_type="ring_1",
                             item_id=RING_ID, is_enabled=True, current_durability=0),
        models.EquipmentSlot(character_id=CID, slot_type="legs",
                             item_id=None, is_enabled=True),
    ])
    db_session.commit()
    return db_session


def _post(client, entries, character_id=CID):
    return client.post(
        "/inventory/internal/update-durability",
        headers=HEADERS,
        json={"character_id": character_id, "entries": entries},
    )


def _durability(db, slot_type, character_id=CID):
    db.expire_all()
    row = db.query(models.EquipmentSlot).filter_by(
        character_id=character_id, slot_type=slot_type).first()
    return row.current_durability if row else None


# ═══════════════════════════════════════════════════════════════════════════
# 1. Happy path — the number really lands in the DB
# ═══════════════════════════════════════════════════════════════════════════


class TestDurabilityPersists:

    def test_single_slot_is_written(self, client, gear, applied):
        response = _post(client, [{"slot_type": "body", "new_durability": 17}])

        assert response.status_code == 200, response.text
        assert response.json() == {"status": "ok", "updated": 1, "mods_removed_for": []}
        assert _durability(gear, "body") == 17, \
            "прочность не сохранилась — битва списала износ в никуда"
        assert applied == []

    def test_several_slots_in_one_call(self, client, gear, applied):
        response = _post(client, [
            {"slot_type": "body", "new_durability": 40},
            {"slot_type": "head", "new_durability": 25},
        ])

        assert response.status_code == 200, response.text
        assert response.json()["updated"] == 2
        assert _durability(gear, "body") == 40
        assert _durability(gear, "head") == 25

    def test_negative_durability_is_clamped_to_zero(self, client, gear, applied):
        response = _post(client, [{"slot_type": "body", "new_durability": -7}])

        assert response.status_code == 200, response.text
        assert _durability(gear, "body") == 0

    def test_repeated_calls_are_idempotent_on_the_stored_value(self, client, gear, applied):
        _post(client, [{"slot_type": "body", "new_durability": 20}])
        _post(client, [{"slot_type": "body", "new_durability": 20}])
        assert _durability(gear, "body") == 20

    def test_an_empty_entry_list_changes_nothing(self, client, gear, applied):
        response = _post(client, [])
        assert response.status_code == 200, response.text
        assert response.json()["updated"] == 0
        assert _durability(gear, "body") == 42


# ═══════════════════════════════════════════════════════════════════════════
# 2. The "just broke" branch — modifiers come off exactly once
# ═══════════════════════════════════════════════════════════════════════════


class TestBreakingRemovesModifiers:

    def test_reaching_zero_takes_the_modifiers_off(self, client, gear, applied):
        response = _post(client, [{"slot_type": "body", "new_durability": 0}])

        assert response.status_code == 200, response.text
        assert response.json()["mods_removed_for"] == ["body"]
        assert _durability(gear, "body") == 0

        assert len(applied) == 1, "сломанный доспех продолжает давать бонусы"
        character_id, modifiers = applied[0]
        assert character_id == CID
        assert modifiers["health"] < 0 and modifiers["strength"] < 0, modifiers

    def test_an_already_broken_slot_does_not_remove_them_twice(self, client, gear, applied):
        _post(client, [{"slot_type": "body", "new_durability": 0}])
        applied.clear()

        response = _post(client, [{"slot_type": "body", "new_durability": 0}])

        assert response.status_code == 200, response.text
        assert response.json()["mods_removed_for"] == []
        assert applied == []

    def test_a_nonzero_value_never_removes_modifiers(self, client, gear, applied):
        response = _post(client, [{"slot_type": "body", "new_durability": 1}])
        assert response.json()["mods_removed_for"] == []
        assert applied == []

    def test_a_failing_attributes_service_still_persists_the_durability(
        self, client, gear, monkeypatch
    ):
        """The modifier call is best-effort; the write must not be lost."""
        async def _boom(character_id, modifiers):
            raise RuntimeError("attributes down")

        monkeypatch.setattr(main, "apply_modifiers_in_attributes_service", _boom)

        response = _post(client, [{"slot_type": "body", "new_durability": 0}])

        assert response.status_code == 200, response.text
        assert response.json()["mods_removed_for"] == []
        assert _durability(gear, "body") == 0


# ═══════════════════════════════════════════════════════════════════════════
# 3. Skip branches
# ═══════════════════════════════════════════════════════════════════════════


class TestSkippedEntries:

    def test_unknown_slot_type_is_skipped(self, client, gear, applied):
        response = _post(client, [{"slot_type": "tail", "new_durability": 5}])
        assert response.status_code == 200, response.text
        assert response.json()["updated"] == 0

    def test_empty_slot_is_skipped(self, client, gear, applied):
        response = _post(client, [{"slot_type": "legs", "new_durability": 5}])
        assert response.status_code == 200, response.text
        assert response.json()["updated"] == 0

    def test_indestructible_item_is_skipped(self, client, gear, applied):
        """`max_durability = 0` means the item has no durability at all."""
        response = _post(client, [{"slot_type": "ring_1", "new_durability": 5}])
        assert response.status_code == 200, response.text
        assert response.json()["updated"] == 0
        assert _durability(gear, "ring_1") == 0
        assert applied == []

    def test_another_characters_slot_is_not_touched(self, client, gear, applied):
        gear.add(models.EquipmentSlot(
            character_id=42, slot_type="body", item_id=ARMOR_ID,
            is_enabled=True, current_durability=50))
        gear.commit()

        response = _post(client, [{"slot_type": "body", "new_durability": 3}],
                         character_id=CID)

        assert response.status_code == 200, response.text
        assert _durability(gear, "body", character_id=42) == 50
        assert _durability(gear, "body") == 3

    def test_a_good_entry_survives_a_bad_neighbour(self, client, gear, applied):
        response = _post(client, [
            {"slot_type": "tail", "new_durability": 9},
            {"slot_type": "head", "new_durability": 11},
        ])
        assert response.status_code == 200, response.text
        assert response.json()["updated"] == 1
        assert _durability(gear, "head") == 11


# ═══════════════════════════════════════════════════════════════════════════
# 4. Input validation
# ═══════════════════════════════════════════════════════════════════════════


class TestValidation:

    def test_missing_character_id_is_422(self, client, gear):
        response = client.post(
            "/inventory/internal/update-durability",
            headers=HEADERS,
            json={"entries": [{"slot_type": "body", "new_durability": 1}]},
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("bad", ["'; DROP TABLE equipment_slots; --", None, 1.5])
    def test_a_non_integer_durability_never_500s(self, client, gear, bad):
        response = _post(client, [{"slot_type": "body", "new_durability": bad}])
        assert response.status_code in (200, 422), response.text
        # the table is still there either way
        assert gear.execute(
            text("SELECT COUNT(*) FROM equipment_slots")).scalar() >= 1

    def test_sql_injection_in_slot_type_is_inert(self, client, gear):
        response = _post(client, [
            {"slot_type": "body'; DROP TABLE equipment_slots; --", "new_durability": 1},
        ])
        assert response.status_code == 200, response.text
        assert response.json()["updated"] == 0
        assert _durability(gear, "body") == 42
