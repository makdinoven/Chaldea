"""
Tests for POST /inventory/internal/characters/{character_id}/consume_item.

Game rule: a fast (belt) slot holds exactly ONE item. Putting an item into a
fast slot already took it out of the bag (`equip_item`). Using it in battle
spends THE SLOT — the endpoint clears the fast slot and never touches
`character_inventory`. `remaining_quantity` is the number of this character's
fast slots still holding the item.

Covers:
- the given slot is cleared, the bag quantity is unchanged
- without slot_type the first fast slot (by slot_type order) holding the item is cleared
- two slots with the same item: only one is cleared, remaining_quantity == 1
- slot_type pointing at a slot with another item -> 404, nothing changes
- no fast slot with the item -> 404 (even if the bag has it)
- another character's slot is never touched
- non-fast slots holding the item are ignored
- food -> 400 before anything else
- missing / wrong X-Internal-Token -> 401
- SQL-injection-like values in body / path -> 422, nothing breaks
"""

import pytest
from models import Items, CharacterInventory, EquipmentSlot
import auth_http


# FEAT-169: the /inventory/internal/* routes require `X-Internal-Token`.
_TOKEN = "test-internal-token"
_INTERNAL_HEADERS = {"X-Internal-Token": _TOKEN}
_NOT_IN_SLOT = "Этого предмета нет в быстром слоте"


@pytest.fixture(autouse=True)
def _internal_token(monkeypatch):
    """`verify_internal_token` reads a module-level constant — pin it."""
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", _TOKEN)


def _create_consumable(db_session, **overrides):
    defaults = dict(
        name="Health Potion",
        item_level=1,
        item_type="consumable",
        item_rarity="common",
        max_stack_size=10,
        is_unique=False,
        description="Restores health",
        health_recovery=50,
    )
    defaults.update(overrides)
    item = Items(**defaults)
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def _add_to_inventory(db_session, character_id, item_id, quantity=1):
    inv = CharacterInventory(character_id=character_id, item_id=item_id, quantity=quantity)
    db_session.add(inv)
    db_session.commit()
    return inv


def _put_in_slot(db_session, character_id, slot_type, item_id, is_enabled=True):
    slot = EquipmentSlot(character_id=character_id, slot_type=slot_type,
                         item_id=item_id, is_enabled=is_enabled)
    db_session.add(slot)
    db_session.commit()
    return slot


def _slot_item(db_session, character_id, slot_type):
    db_session.expire_all()
    slot = (db_session.query(EquipmentSlot)
            .filter_by(character_id=character_id, slot_type=slot_type).first())
    return slot.item_id if slot else "no-row"


def _bag_qty(db_session, character_id, item_id):
    db_session.expire_all()
    row = (db_session.query(CharacterInventory)
           .filter_by(character_id=character_id, item_id=item_id).first())
    return row.quantity if row else None


def _consume(client, body, character_id=1, headers=_INTERNAL_HEADERS):
    return client.post(
        f"/inventory/internal/characters/{character_id}/consume_item",
        headers=headers, json=body,
    )


# -- Success cases ----------------------------------------------------------


def test_clears_the_given_slot_and_leaves_the_bag_alone(client, db_session):
    item = _create_consumable(db_session)
    _add_to_inventory(db_session, 1, item.id, quantity=5)
    _put_in_slot(db_session, 1, "fast_slot_2", item.id)

    resp = _consume(client, {"item_id": item.id, "slot_type": "fast_slot_2"})

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "ok", "remaining_quantity": 0}
    assert _slot_item(db_session, 1, "fast_slot_2") is None
    assert _bag_qty(db_session, 1, item.id) == 5, "сумку трогать нельзя"


def test_works_with_an_empty_bag(client, db_session):
    """The slot item already left the bag at equip time — no bag row is fine."""
    item = _create_consumable(db_session, name="Last Potion")
    _put_in_slot(db_session, 1, "fast_slot_1", item.id)

    resp = _consume(client, {"item_id": item.id, "slot_type": "fast_slot_1"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["remaining_quantity"] == 0
    assert _slot_item(db_session, 1, "fast_slot_1") is None
    assert _bag_qty(db_session, 1, item.id) is None, "строка сумки не должна появиться"


@pytest.mark.parametrize("body_extra", [{}, {"slot_type": None}])
def test_without_slot_type_clears_the_first_slot_holding_the_item(
    client, db_session, body_extra
):
    item = _create_consumable(db_session, name="Mana Potion")
    other = _create_consumable(db_session, name="Other Potion")
    # fast_slot_1 holds a different item; the potion sits in 3 and 2.
    # (fast_slot_10 is avoided on purpose: SQLite orders the String-patched
    # column lexically, MySQL orders the ENUM by its index.)
    _put_in_slot(db_session, 1, "fast_slot_1", other.id)
    _put_in_slot(db_session, 1, "fast_slot_3", item.id)
    _put_in_slot(db_session, 1, "fast_slot_2", item.id)

    resp = _consume(client, {"item_id": item.id, **body_extra})

    assert resp.status_code == 200, resp.text
    assert resp.json()["remaining_quantity"] == 1
    assert _slot_item(db_session, 1, "fast_slot_2") is None
    assert _slot_item(db_session, 1, "fast_slot_3") == item.id
    assert _slot_item(db_session, 1, "fast_slot_1") == other.id


def test_two_slots_same_item_only_one_is_cleared(client, db_session):
    item = _create_consumable(db_session, name="Twin Potion")
    _add_to_inventory(db_session, 1, item.id, quantity=3)
    _put_in_slot(db_session, 1, "fast_slot_1", item.id)
    _put_in_slot(db_session, 1, "fast_slot_4", item.id)

    resp = _consume(client, {"item_id": item.id, "slot_type": "fast_slot_4"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["remaining_quantity"] == 1
    assert _slot_item(db_session, 1, "fast_slot_4") is None
    assert _slot_item(db_session, 1, "fast_slot_1") == item.id
    assert _bag_qty(db_session, 1, item.id) == 3

    # Second use spends the other slot; then nothing is left on the belt.
    resp2 = _consume(client, {"item_id": item.id})
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["remaining_quantity"] == 0
    assert _slot_item(db_session, 1, "fast_slot_1") is None
    assert _bag_qty(db_session, 1, item.id) == 3

    # Third use: belt is empty -> 404, bag still untouched.
    resp3 = _consume(client, {"item_id": item.id})
    assert resp3.status_code == 404
    assert _bag_qty(db_session, 1, item.id) == 3


# -- 404 cases --------------------------------------------------------------


def test_slot_type_pointing_at_another_item_is_404(client, db_session):
    item = _create_consumable(db_session, name="Wanted")
    other = _create_consumable(db_session, name="Something else")
    _put_in_slot(db_session, 1, "fast_slot_1", other.id)
    _put_in_slot(db_session, 1, "fast_slot_2", item.id)

    resp = _consume(client, {"item_id": item.id, "slot_type": "fast_slot_1"})

    assert resp.status_code == 404
    assert resp.json()["detail"] == _NOT_IN_SLOT
    assert _slot_item(db_session, 1, "fast_slot_1") == other.id
    assert _slot_item(db_session, 1, "fast_slot_2") == item.id


def test_item_only_in_the_bag_is_404(client, db_session):
    item = _create_consumable(db_session, name="Bag Potion")
    _add_to_inventory(db_session, 1, item.id, quantity=5)

    resp = _consume(client, {"item_id": item.id})

    assert resp.status_code == 404
    assert resp.json()["detail"] == _NOT_IN_SLOT
    assert _bag_qty(db_session, 1, item.id) == 5


def test_nonexistent_item_id_is_404(client, db_session):
    resp = _consume(client, {"item_id": 99999})
    assert resp.status_code == 404
    assert resp.json()["detail"] == _NOT_IN_SLOT


def test_non_fast_slot_holding_the_item_is_ignored(client, db_session):
    item = _create_consumable(db_session, name="Belt-ish")
    _put_in_slot(db_session, 1, "belt", item.id)

    resp = _consume(client, {"item_id": item.id})
    assert resp.status_code == 404
    assert _slot_item(db_session, 1, "belt") == item.id

    resp = _consume(client, {"item_id": item.id, "slot_type": "belt"})
    assert resp.status_code == 404
    assert _slot_item(db_session, 1, "belt") == item.id


def test_another_characters_slot_is_not_touched(client, db_session):
    item = _create_consumable(db_session, name="Other Potion")
    _add_to_inventory(db_session, 2, item.id, quantity=5)
    _put_in_slot(db_session, 2, "fast_slot_1", item.id)

    resp = _consume(client, {"item_id": item.id, "slot_type": "fast_slot_1"}, character_id=1)

    assert resp.status_code == 404
    assert _slot_item(db_session, 2, "fast_slot_1") == item.id
    assert _bag_qty(db_session, 2, item.id) == 5


def test_remaining_quantity_counts_only_this_character(client, db_session):
    item = _create_consumable(db_session, name="Shared Potion")
    _put_in_slot(db_session, 1, "fast_slot_1", item.id)
    _put_in_slot(db_session, 2, "fast_slot_1", item.id)
    _put_in_slot(db_session, 2, "fast_slot_2", item.id)

    resp = _consume(client, {"item_id": item.id})

    assert resp.status_code == 200, resp.text
    assert resp.json()["remaining_quantity"] == 0
    assert _slot_item(db_session, 2, "fast_slot_1") == item.id
    assert _slot_item(db_session, 2, "fast_slot_2") == item.id


# -- Food -------------------------------------------------------------------


def test_food_is_rejected_with_400_and_the_slot_kept(client, db_session):
    food = _create_consumable(db_session, name="Bread", is_food=True)
    _put_in_slot(db_session, 1, "fast_slot_1", food.id)

    resp = _consume(client, {"item_id": food.id, "slot_type": "fast_slot_1"})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Еду нельзя использовать в бою"
    assert _slot_item(db_session, 1, "fast_slot_1") == food.id


# -- Auth -------------------------------------------------------------------


@pytest.mark.parametrize("headers", [
    {},
    {"X-Internal-Token": "wrong"},
    {"X-Internal-Token": ""},
    {"Authorization": "Bearer player-jwt"},
], ids=["no-header", "wrong", "empty", "player-jwt"])
def test_without_a_valid_token_is_401_and_the_slot_kept(client, db_session, headers):
    item = _create_consumable(db_session, name="Guarded")
    _put_in_slot(db_session, 1, "fast_slot_1", item.id)

    resp = _consume(client, {"item_id": item.id, "slot_type": "fast_slot_1"}, headers=headers)

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Недействительный internal token"
    assert _slot_item(db_session, 1, "fast_slot_1") == item.id


# -- Security: SQL injection -----------------------------------------------


def test_sql_injection_in_item_id_is_422(client, db_session):
    resp = _consume(client, {"item_id": "1; DROP TABLE character_inventory; --"})
    assert resp.status_code == 422


def test_sql_injection_in_slot_type_does_nothing(client, db_session):
    item = _create_consumable(db_session, name="Target")
    _add_to_inventory(db_session, 1, item.id, quantity=2)
    _put_in_slot(db_session, 1, "fast_slot_1", item.id)

    resp = _consume(client, {
        "item_id": item.id,
        "slot_type": "fast_slot_1' OR '1'='1",
    })

    assert resp.status_code == 404
    assert _slot_item(db_session, 1, "fast_slot_1") == item.id
    assert _bag_qty(db_session, 1, item.id) == 2


def test_sql_injection_in_path_is_422(client, db_session):
    resp = client.post(
        "/inventory/internal/characters/1%20OR%201=1/consume_item",
        headers=_INTERNAL_HEADERS, json={"item_id": 1},
    )
    assert resp.status_code == 422
