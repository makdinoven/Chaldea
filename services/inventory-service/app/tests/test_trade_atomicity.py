"""
Task 3.8 — QA tests for FEAT-063 Phase 3: Trade atomicity.

Tests that trade execution rolls back properly when items or gold
become insufficient between the confirmation calls, and that gold
balances remain consistent after trades.
"""

import pytest
from unittest.mock import patch
from sqlalchemy import text

from auth_http import get_current_user_via_http, UserRead
import models


# ---------------------------------------------------------------------------
# Helpers (same as test_trade.py — duplicated to keep files independent)
# ---------------------------------------------------------------------------

def _create_characters_table(db):
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


def _insert_character(db, char_id, user_id, name="TestChar", location=1, gold=0):
    db.execute(text(
        "INSERT OR IGNORE INTO characters (id, name, user_id, current_location_id, currency_balance) "
        "VALUES (:cid, :name, :uid, :loc, :gold)"
    ), {"cid": char_id, "name": name, "uid": user_id, "loc": location, "gold": gold})
    db.commit()


def _create_item(db, item_id, name, max_stack=99):
    item = models.Items(
        id=item_id,
        name=name,
        item_level=1,
        item_type="resource",
        item_rarity="common",
        max_stack_size=max_stack,
        is_unique=False,
    )
    db.add(item)
    db.flush()
    return item


def _add_inventory(db, char_id, item_id, quantity):
    inv = models.CharacterInventory(character_id=char_id, item_id=item_id, quantity=quantity)
    db.add(inv)
    db.flush()
    return inv


def _switch_user(app, user_id, username="user"):
    user = UserRead(id=user_id, username=username, role="user", permissions=[])
    app.dependency_overrides[get_current_user_via_http] = lambda: user
    return user


def _propose_trade(client, initiator=1, target=2):
    with patch("main.publish_notification_sync"):
        resp = client.post("/inventory/trade/propose", json={
            "initiator_character_id": initiator,
            "target_character_id": target,
        })
    assert resp.status_code == 201
    return resp.json()["trade_id"]


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def atomicity_env(client, db_session):
    """
    Environment for atomicity tests:
    - Alice (char 1, user 1) with 5 Herbs, 500 gold
    - Bob (char 2, user 2) with 3 Ores, 300 gold
    """
    _create_characters_table(db_session)
    _insert_character(db_session, 1, user_id=1, name="Alice", location=1, gold=500)
    _insert_character(db_session, 2, user_id=2, name="Bob", location=1, gold=300)

    _create_item(db_session, 101, "Herb")
    _create_item(db_session, 102, "Ore")
    _add_inventory(db_session, 1, 101, 5)   # Alice: 5 Herbs
    _add_inventory(db_session, 2, 102, 3)   # Bob: 3 Ores

    db_session.commit()

    from main import app
    _user1 = UserRead(id=1, username="alice", role="user", permissions=[])
    app.dependency_overrides[get_current_user_via_http] = lambda: _user1

    with patch("main.publish_notification_sync"):
        yield {
            "client": client,
            "db": db_session,
            "app": app,
        }

    app.dependency_overrides.pop(get_current_user_via_http, None)


# ---------------------------------------------------------------------------
# Test: Insufficient items at execution time (items sold between confirms)
# ---------------------------------------------------------------------------

def test_trade_execution_insufficient_items_rollback(atomicity_env):
    """
    Alice offers 5 Herbs. After she updates items but before both confirm,
    her inventory is reduced externally (simulating selling items).
    When both confirm, execute_trade should fail and the trade should NOT
    be completed. Bob's inventory must remain unchanged.
    """
    c = atomicity_env["client"]
    db = atomicity_env["db"]
    app = atomicity_env["app"]

    trade_id = _propose_trade(c)

    # Alice offers 5 Herbs
    c.put(f"/inventory/trade/{trade_id}/items", json={
        "character_id": 1,
        "items": [{"item_id": 101, "quantity": 5}],
        "gold": 0,
    })

    # Bob offers nothing (just gold=0, items=[])
    _switch_user(app, 2, "bob")
    c.put(f"/inventory/trade/{trade_id}/items", json={
        "character_id": 2,
        "items": [],
        "gold": 0,
    })

    # Bob confirms
    with patch("main.publish_notification_sync"):
        c.post(f"/inventory/trade/{trade_id}/confirm", json={"character_id": 2})

    # Simulate: Alice sells 3 Herbs externally, leaving only 2
    db.execute(text(
        "UPDATE character_inventory SET quantity = 2 "
        "WHERE character_id = 1 AND item_id = 101"
    ))
    db.commit()

    # Alice confirms -> execution should fail because she only has 2 Herbs but offered 5
    _switch_user(app, 1, "alice")
    with patch("main.publish_notification_sync"):
        resp = c.post(f"/inventory/trade/{trade_id}/confirm", json={"character_id": 1})

    assert resp.status_code == 400
    assert "недостаточно" in resp.json()["detail"].lower()

    # Bob should NOT have received any Herbs
    bob_herbs = db.execute(text(
        "SELECT COALESCE(SUM(quantity), 0) FROM character_inventory "
        "WHERE character_id = 2 AND item_id = 101"
    )).scalar()
    assert bob_herbs == 0

    # Alice should still have her 2 Herbs
    alice_herbs = db.execute(text(
        "SELECT COALESCE(SUM(quantity), 0) FROM character_inventory "
        "WHERE character_id = 1 AND item_id = 101"
    )).scalar()
    assert alice_herbs == 2


# ---------------------------------------------------------------------------
# Test: Insufficient gold at execution time
# ---------------------------------------------------------------------------

def test_trade_execution_insufficient_gold_rollback(atomicity_env):
    """
    Alice offers 400 gold. After both set items but before both confirm,
    her gold is reduced externally. Execution should fail and gold should
    remain unchanged.
    """
    c = atomicity_env["client"]
    db = atomicity_env["db"]
    app = atomicity_env["app"]

    trade_id = _propose_trade(c)

    # Alice offers 400 gold
    c.put(f"/inventory/trade/{trade_id}/items", json={
        "character_id": 1,
        "items": [],
        "gold": 400,
    })

    _switch_user(app, 2, "bob")
    c.put(f"/inventory/trade/{trade_id}/items", json={
        "character_id": 2,
        "items": [],
        "gold": 0,
    })

    # Bob confirms
    with patch("main.publish_notification_sync"):
        c.post(f"/inventory/trade/{trade_id}/confirm", json={"character_id": 2})

    # Simulate: Alice spends gold externally, now only has 100
    db.execute(text("UPDATE characters SET currency_balance = 100 WHERE id = 1"))
    db.commit()

    # Alice confirms -> execution should fail
    _switch_user(app, 1, "alice")
    with patch("main.publish_notification_sync"):
        resp = c.post(f"/inventory/trade/{trade_id}/confirm", json={"character_id": 1})

    assert resp.status_code == 400
    assert "золота" in resp.json()["detail"].lower()

    # Bob's gold should be unchanged
    bob_gold = db.execute(text(
        "SELECT currency_balance FROM characters WHERE id = 2"
    )).scalar()
    assert bob_gold == 300

    # Alice's gold should still be 100 (the externally modified value)
    alice_gold = db.execute(text(
        "SELECT currency_balance FROM characters WHERE id = 1"
    )).scalar()
    assert alice_gold == 100


# ---------------------------------------------------------------------------
# Test: Gold balance consistency after trade
# ---------------------------------------------------------------------------

def test_gold_balance_consistency_after_trade(atomicity_env):
    """
    After a successful trade, verify the accounting equation holds:
    initiator_after = initiator_before - offered_gold + received_gold
    target_after = target_before - offered_gold + received_gold
    Total gold in the system must be conserved.
    """
    c = atomicity_env["client"]
    db = atomicity_env["db"]
    app = atomicity_env["app"]

    # Record initial gold
    alice_before = db.execute(text(
        "SELECT currency_balance FROM characters WHERE id = 1"
    )).scalar()
    bob_before = db.execute(text(
        "SELECT currency_balance FROM characters WHERE id = 2"
    )).scalar()
    total_before = alice_before + bob_before

    trade_id = _propose_trade(c)

    alice_gold_offer = 150
    bob_gold_offer = 75

    # Alice offers 150 gold
    c.put(f"/inventory/trade/{trade_id}/items", json={
        "character_id": 1,
        "items": [],
        "gold": alice_gold_offer,
    })

    # Bob offers 75 gold
    _switch_user(app, 2, "bob")
    c.put(f"/inventory/trade/{trade_id}/items", json={
        "character_id": 2,
        "items": [],
        "gold": bob_gold_offer,
    })

    # Both confirm
    with patch("main.publish_notification_sync"):
        c.post(f"/inventory/trade/{trade_id}/confirm", json={"character_id": 2})

    _switch_user(app, 1, "alice")
    with patch("main.publish_notification_sync"):
        resp = c.post(f"/inventory/trade/{trade_id}/confirm", json={"character_id": 1})

    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"

    # Verify individual balances
    alice_after = db.execute(text(
        "SELECT currency_balance FROM characters WHERE id = 1"
    )).scalar()
    bob_after = db.execute(text(
        "SELECT currency_balance FROM characters WHERE id = 2"
    )).scalar()

    assert alice_after == alice_before - alice_gold_offer + bob_gold_offer
    assert bob_after == bob_before - bob_gold_offer + alice_gold_offer

    # Total gold in system must be conserved
    total_after = alice_after + bob_after
    assert total_after == total_before
