"""
Editing a worn item settles the difference on everyone wearing it.

Equip adds the item's numbers to the wearer and unequip takes them away. If an
admin changed the numbers in between, unequip took away the new ones and the
wearer's attributes drifted by the difference for good (seen on prod: a robe's
vulnerability edited from +5 to −5 while worn left its wearer with +10).
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

import models
from auth_http import UserRead, get_current_user_via_http

WEARER = 7
BYSTANDER = 8


@pytest.fixture()
def robe(db_session):
    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.execute(text(
        "CREATE TABLE characters (id INTEGER PRIMARY KEY, user_id INTEGER, id_class INTEGER, is_npc INTEGER DEFAULT 0)"
    ))
    db_session.commit()
    item = models.Items(name="Одеяние", item_type="body", item_rarity="common", item_level=1,
                        max_stack_size=1, is_unique=False, vul_damning_modifier=5, res_fire_modifier=2)
    db_session.add(item)
    db_session.commit()
    db_session.add(models.EquipmentSlot(character_id=WEARER, slot_type="body", item_id=item.id, is_enabled=True))
    db_session.add(models.CharacterInventory(character_id=BYSTANDER, item_id=item.id, quantity=1))
    db_session.commit()
    yield item
    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.commit()


@pytest.fixture()
def admin(client):
    from main import app

    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=1, username="admin", role="admin", permissions=["items:update"])
    with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock) as apply, \
         patch("main._reconcile_perks_async", new_callable=AsyncMock) as perks:
        yield client, apply, perks
    app.dependency_overrides.pop(get_current_user_via_http, None)


def _put(client, item, **changes):
    body = {"name": item.name, "item_type": "body", "item_rarity": "common", "item_level": 1,
            "max_stack_size": 1, "is_unique": False, **changes}
    return client.put(f"/inventory/items/{item.id}", json=body)


def test_wearer_gets_the_difference(admin, robe):
    client, apply, perks = admin
    resp = _put(client, robe, vul_damning_modifier=-5, res_fire_modifier=2)
    assert resp.status_code == 200
    apply.assert_awaited_once_with(WEARER, {"vul_damning": -10})
    perks.assert_awaited_once_with(WEARER)


def test_no_change_no_call(admin, robe):
    client, apply, _ = admin
    resp = _put(client, robe, vul_damning_modifier=5, res_fire_modifier=2, description="Новое описание")
    assert resp.status_code == 200
    apply.assert_not_awaited()
