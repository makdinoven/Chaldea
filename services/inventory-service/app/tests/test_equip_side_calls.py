"""
Equip / unequip answer as soon as what the player sees is settled.

The cumulative-stats endpoint already reconciles perks and evaluates titles, so
after it equip used to do both again, one after another — most of what an equip
cost. Now: a real slot awaits the stats call alone; a fast slot awaits the perk
reconcile; titles (which never move the stats on screen) run after the response.
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

import models
from auth_http import UserRead, get_current_user_via_http

CHAR = 1
USER = 1


@pytest.fixture()
def world(db_session):
    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.execute(text(
        "CREATE TABLE characters (id INTEGER PRIMARY KEY, user_id INTEGER, id_class INTEGER, is_npc INTEGER DEFAULT 0)"
    ))
    db_session.execute(text(f"INSERT INTO characters VALUES ({CHAR}, {USER}, 1, 0)"))
    for slot_type in ("body", "belt", "fast_slot_1"):
        db_session.add(models.EquipmentSlot(character_id=CHAR, slot_type=slot_type, is_enabled=True))
    belt = models.Items(name="Пояс", item_type="belt", item_rarity="common", item_level=1,
                        max_stack_size=1, is_unique=False, fast_slot_bonus=1)
    armor = models.Items(name="Роба", item_type="body", item_rarity="common", item_level=1,
                         max_stack_size=1, is_unique=False)
    potion = models.Items(name="Зелье", item_type="consumable", item_rarity="common", item_level=1,
                          max_stack_size=10, is_unique=False)
    db_session.add_all([belt, armor, potion])
    db_session.commit()
    db_session.query(models.EquipmentSlot).filter_by(character_id=CHAR, slot_type="belt").update({"item_id": belt.id})
    for item in (armor, potion):
        db_session.add(models.CharacterInventory(character_id=CHAR, item_id=item.id, quantity=1))
    db_session.commit()
    yield {"armor": armor, "potion": potion}
    db_session.execute(text("DROP TABLE IF EXISTS characters"))
    db_session.commit()


@pytest.fixture()
def calls(client, world):
    from main import app

    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=USER, username="p", role="user", permissions=[])
    with patch("main.apply_modifiers_in_attributes_service", new_callable=AsyncMock), \
         patch("main._reconcile_perks_async", new_callable=AsyncMock) as perks, \
         patch("main._track_cumulative_stats_async", new_callable=AsyncMock) as stats, \
         patch("main._evaluate_titles_async", new_callable=AsyncMock) as titles, \
         patch("main._in_background") as background:
        yield {"client": client, "perks": perks, "stats": stats, "titles": titles, "background": background}
    app.dependency_overrides.pop(get_current_user_via_http, None)


def test_real_slot_awaits_stats_only(calls, world):
    resp = calls["client"].post(f"/inventory/{CHAR}/equip", json={"item_id": world["armor"].id})
    assert resp.status_code == 200
    calls["stats"].assert_awaited_once()
    # The stats endpoint reconciles perks and evaluates titles itself.
    calls["perks"].assert_not_awaited()
    calls["background"].assert_not_called()


def test_fast_slot_awaits_perks_and_backgrounds_titles(calls, world):
    resp = calls["client"].post(f"/inventory/{CHAR}/equip", json={"item_id": world["potion"].id})
    assert resp.status_code == 200
    calls["stats"].assert_not_awaited()
    calls["perks"].assert_awaited_once()
    calls["background"].assert_called_once()


def test_unequip_awaits_perks_and_backgrounds_titles(calls, world):
    calls["client"].post(f"/inventory/{CHAR}/equip", json={"item_id": world["armor"].id})
    calls["perks"].reset_mock()
    calls["background"].reset_mock()

    resp = calls["client"].post(f"/inventory/{CHAR}/unequip", params={"slot_type": "body"})
    assert resp.status_code == 200
    calls["perks"].assert_awaited_once()
    calls["background"].assert_called_once()
