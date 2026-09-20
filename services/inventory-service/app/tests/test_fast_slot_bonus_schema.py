"""The belt bonus must survive the Pydantic layer.

`Items.fast_slot_bonus` and `crud.recalc_fast_slots` have existed for a long
time: base 4 fast slots, plus the bonus of every equipped item, capped at 10.
The admin item form has a «Бонус быстрых слотов» field and sends it. But the
column was never declared on `schemas.ItemBase`, and Pydantic v1 drops unknown
keys without complaining — so `models.Items(**item_in.dict(exclude_unset=True))`
never received it, `PUT /inventory/items/{id}` answered 200, and the value
stayed NULL. No belt in the game could grant a single extra slot, and nothing
anywhere raised.

That is the project's silent-failure pattern, so the guard is explicit: one
test that the field round-trips through the schema, one that a bonus actually
moves the slot count. Either failing means belts are inert again.
"""

import pytest

import crud
import models
import schemas


BASE_FAST_SLOTS = 4
MAX_FAST_SLOTS = 10


def _item_payload(**overrides):
    """Minimal body `POST /inventory/items` accepts."""
    payload = {
        "name": "Пояс с подсумками",
        "item_type": "belt",
        "item_rarity": "common",
        "max_stack_size": 1,
        "is_unique": False,
        "item_level": 1,
    }
    payload.update(overrides)
    return payload


def test_fast_slot_bonus_survives_the_schema():
    """The regression itself: the key must reach the ORM kwargs."""
    item = schemas.ItemCreate(**_item_payload(fast_slot_bonus=2))
    assert item.fast_slot_bonus == 2
    # This is the exact call main.create_item makes before models.Items(**payload).
    assert item.dict(exclude_unset=True)["fast_slot_bonus"] == 2


def test_fast_slot_bonus_defaults_to_zero():
    """An item that says nothing must not start handing out slots."""
    item = schemas.ItemCreate(**_item_payload())
    assert item.fast_slot_bonus == 0
    # `exclude_unset` must leave it out entirely, so the DB default stands.
    assert "fast_slot_bonus" not in item.dict(exclude_unset=True)


def test_fast_slot_bonus_is_readable_back():
    """`schemas.Item` is what the admin form reloads — the value must be there."""
    assert "fast_slot_bonus" in schemas.Item.__fields__


@pytest.mark.parametrize(
    "bonus, expected_enabled",
    [
        (0, BASE_FAST_SLOTS),
        (2, BASE_FAST_SLOTS + 2),
        (99, MAX_FAST_SLOTS),  # capped
    ],
)
def test_equipped_bonus_changes_the_slot_count(db_session, bonus, expected_enabled):
    """End of the chain: the stored bonus must move `recalc_fast_slots`."""
    character_id = 4242

    belt = models.Items(
        name="Пояс с подсумками",
        item_type="belt",
        item_rarity="common",
        max_stack_size=1,
        is_unique=False,
        fast_slot_bonus=bonus,
    )
    db_session.add(belt)
    db_session.flush()

    db_session.add(models.EquipmentSlot(
        character_id=character_id, slot_type="belt", item_id=belt.id, is_enabled=True,
    ))
    for i in range(1, MAX_FAST_SLOTS + 1):
        db_session.add(models.EquipmentSlot(
            character_id=character_id, slot_type=f"fast_slot_{i}", is_enabled=False,
        ))
    db_session.commit()

    crud.recalc_fast_slots(db_session, character_id)
    db_session.commit()

    enabled = db_session.query(models.EquipmentSlot).filter(
        models.EquipmentSlot.character_id == character_id,
        models.EquipmentSlot.slot_type.like("fast_slot_%"),
        models.EquipmentSlot.is_enabled.is_(True),
    ).count()
    assert enabled == expected_enabled
