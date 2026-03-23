"""
Task 3.7 — QA tests for FEAT-063 Phase 3: Trade System.

Tests covering propose, update items, confirm, cancel, get state,
and all validation rules for the trade endpoints.
"""

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import text

from auth_http import get_current_user_via_http, UserRead
import models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_characters_table(db):
    """Create minimal characters + battle tables for trade checks.
    Uses DROP + CREATE to ensure clean state between tests (these tables
    are not managed by SQLAlchemy metadata so drop_all doesn't touch them).
    """
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


def _create_item(db, item_id, name, max_stack=10, item_type="resource"):
    item = models.Items(
        id=item_id,
        name=name,
        item_level=1,
        item_type=item_type,
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def trade_env(client, db_session):
    """
    Set up a full trade test environment:
    - characters table with two characters on the same location
    - auth overridden to user_id=1
    - rabbitmq publisher mocked
    - an item in both characters' inventories
    """
    _create_characters_table(db_session)
    _insert_character(db_session, 1, user_id=1, name="Alice", location=1, gold=500)
    _insert_character(db_session, 2, user_id=2, name="Bob", location=1, gold=300)

    _create_item(db_session, 101, "Herb", max_stack=99)
    _create_item(db_session, 102, "Ore", max_stack=99)
    _add_inventory(db_session, 1, 101, 10)  # Alice has 10 Herbs
    _add_inventory(db_session, 2, 102, 5)   # Bob has 5 Ores

    db_session.commit()

    from main import app

    _user1 = UserRead(id=1, username="alice", role="user", permissions=[])
    app.dependency_overrides[get_current_user_via_http] = lambda: _user1

    with patch("main.publish_notification_sync"):
        yield {
            "client": client,
            "db": db_session,
            "app": app,
            "user1": _user1,
        }

    app.dependency_overrides.pop(get_current_user_via_http, None)


def _switch_user(app, user_id, username="bob"):
    """Switch the auth override to a different user."""
    user = UserRead(id=user_id, username=username, role="user", permissions=[])
    app.dependency_overrides[get_current_user_via_http] = lambda: user
    return user


# ---------------------------------------------------------------------------
# Test: Propose trade (happy path)
# ---------------------------------------------------------------------------

def test_propose_trade_happy_path(trade_env):
    c = trade_env["client"]

    with patch("main.publish_notification_sync"):
        resp = c.post("/inventory/trade/propose", json={
            "initiator_character_id": 1,
            "target_character_id": 2,
        })

    assert resp.status_code == 201
    data = resp.json()
    assert "trade_id" in data
    assert data["initiator_character_id"] == 1
    assert data["target_character_id"] == 2
    assert data["status"] == "pending"


# ---------------------------------------------------------------------------
# Test: Propose trade — self-trade blocked
# ---------------------------------------------------------------------------

def test_propose_trade_self_trade_blocked(trade_env):
    c = trade_env["client"]

    with patch("main.publish_notification_sync"):
        resp = c.post("/inventory/trade/propose", json={
            "initiator_character_id": 1,
            "target_character_id": 1,
        })

    assert resp.status_code == 400
    assert "самому себе" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test: Propose trade — characters not at same location
# ---------------------------------------------------------------------------

def test_propose_trade_different_location(trade_env):
    db = trade_env["db"]
    c = trade_env["client"]

    # Move Bob to a different location
    db.execute(text("UPDATE characters SET current_location_id = 99 WHERE id = 2"))
    db.commit()

    with patch("main.publish_notification_sync"):
        resp = c.post("/inventory/trade/propose", json={
            "initiator_character_id": 1,
            "target_character_id": 2,
        })

    assert resp.status_code == 400
    assert "одной локации" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test: Propose trade — character not owned by user
# ---------------------------------------------------------------------------

def test_propose_trade_not_owned(trade_env):
    c = trade_env["client"]

    # User 1 tries to initiate trade as character 2 (owned by user 2)
    with patch("main.publish_notification_sync"):
        resp = c.post("/inventory/trade/propose", json={
            "initiator_character_id": 2,
            "target_character_id": 1,
        })

    assert resp.status_code == 403
    assert "своими персонажами" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test: Propose trade — duplicate active trade between same characters
# ---------------------------------------------------------------------------

def test_propose_trade_duplicate_active(trade_env):
    c = trade_env["client"]

    with patch("main.publish_notification_sync"):
        resp1 = c.post("/inventory/trade/propose", json={
            "initiator_character_id": 1,
            "target_character_id": 2,
        })
    assert resp1.status_code == 201

    with patch("main.publish_notification_sync"):
        resp2 = c.post("/inventory/trade/propose", json={
            "initiator_character_id": 1,
            "target_character_id": 2,
        })

    assert resp2.status_code == 400
    assert "уже есть активное" in resp2.json()["detail"]


# ---------------------------------------------------------------------------
# Helper: create trade and return trade_id
# ---------------------------------------------------------------------------

def _propose_trade(client, initiator=1, target=2):
    with patch("main.publish_notification_sync"):
        resp = client.post("/inventory/trade/propose", json={
            "initiator_character_id": initiator,
            "target_character_id": target,
        })
    assert resp.status_code == 201
    return resp.json()["trade_id"]


# ---------------------------------------------------------------------------
# Test: Update items (happy path)
# ---------------------------------------------------------------------------

def test_update_items_happy_path(trade_env):
    c = trade_env["client"]
    trade_id = _propose_trade(c)

    resp = c.put(f"/inventory/trade/{trade_id}/items", json={
        "character_id": 1,
        "items": [{"item_id": 101, "quantity": 3}],
        "gold": 50,
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["initiator"]["gold"] == 50
    assert len(data["initiator"]["items"]) == 1
    assert data["initiator"]["items"][0]["item_id"] == 101
    assert data["initiator"]["items"][0]["quantity"] == 3
    # Confirmations should be reset
    assert data["initiator"]["confirmed"] is False
    assert data["target"]["confirmed"] is False


# ---------------------------------------------------------------------------
# Test: Update items — insufficient quantity in inventory
# ---------------------------------------------------------------------------

def test_update_items_insufficient_quantity(trade_env):
    c = trade_env["client"]
    trade_id = _propose_trade(c)

    resp = c.put(f"/inventory/trade/{trade_id}/items", json={
        "character_id": 1,
        "items": [{"item_id": 101, "quantity": 999}],  # Alice only has 10
        "gold": 0,
    })

    assert resp.status_code == 400
    assert "Недостаточно" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test: Update items — insufficient gold
# ---------------------------------------------------------------------------

def test_update_items_insufficient_gold(trade_env):
    c = trade_env["client"]
    trade_id = _propose_trade(c)

    resp = c.put(f"/inventory/trade/{trade_id}/items", json={
        "character_id": 1,
        "items": [],
        "gold": 9999,  # Alice only has 500
    })

    assert resp.status_code == 400
    assert "золота" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test: Update items — resets both confirmed flags
# ---------------------------------------------------------------------------

def test_update_items_resets_confirmations(trade_env):
    c = trade_env["client"]
    app = trade_env["app"]
    trade_id = _propose_trade(c)

    # Alice confirms first
    resp = c.post(f"/inventory/trade/{trade_id}/confirm", json={"character_id": 1})
    assert resp.status_code == 200

    # Alice updates items -> both flags should reset
    resp = c.put(f"/inventory/trade/{trade_id}/items", json={
        "character_id": 1,
        "items": [{"item_id": 101, "quantity": 1}],
        "gold": 0,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["initiator"]["confirmed"] is False
    assert data["target"]["confirmed"] is False


# ---------------------------------------------------------------------------
# Test: Update items — non-participant blocked
# ---------------------------------------------------------------------------

def test_update_items_non_participant_blocked(trade_env):
    c = trade_env["client"]
    db = trade_env["db"]
    app = trade_env["app"]
    trade_id = _propose_trade(c)

    # Create a third character owned by user 3
    _insert_character(db, 3, user_id=3, name="Eve", location=1)

    _switch_user(app, 3, "eve")

    resp = c.put(f"/inventory/trade/{trade_id}/items", json={
        "character_id": 3,
        "items": [],
        "gold": 0,
    })

    assert resp.status_code == 403
    assert "участником" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test: Confirm trade — single side confirmation
# ---------------------------------------------------------------------------

def test_confirm_trade_single_side(trade_env):
    c = trade_env["client"]
    trade_id = _propose_trade(c)

    resp = c.post(f"/inventory/trade/{trade_id}/confirm", json={"character_id": 1})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] != "completed"
    assert "Ожидание" in data["message"]


# ---------------------------------------------------------------------------
# Test: Confirm trade — both sides confirmed → trade executed
# ---------------------------------------------------------------------------

def test_confirm_trade_both_sides_executes(trade_env):
    c = trade_env["client"]
    app = trade_env["app"]
    trade_id = _propose_trade(c)

    # Alice offers 3 Herbs + 100 gold
    c.put(f"/inventory/trade/{trade_id}/items", json={
        "character_id": 1,
        "items": [{"item_id": 101, "quantity": 3}],
        "gold": 100,
    })

    # Bob offers 2 Ores + 50 gold
    _switch_user(app, 2, "bob")
    c.put(f"/inventory/trade/{trade_id}/items", json={
        "character_id": 2,
        "items": [{"item_id": 102, "quantity": 2}],
        "gold": 50,
    })

    # Bob confirms
    with patch("main.publish_notification_sync"):
        resp_bob = c.post(f"/inventory/trade/{trade_id}/confirm", json={"character_id": 2})
    assert resp_bob.status_code == 200

    # Alice confirms -> trade executes
    _switch_user(app, 1, "alice")
    with patch("main.publish_notification_sync"):
        resp_alice = c.post(f"/inventory/trade/{trade_id}/confirm", json={"character_id": 1})

    assert resp_alice.status_code == 200
    assert resp_alice.json()["status"] == "completed"


# ---------------------------------------------------------------------------
# Test: Confirm trade — verify items transferred correctly
# ---------------------------------------------------------------------------

def test_confirm_trade_items_transferred(trade_env):
    c = trade_env["client"]
    db = trade_env["db"]
    app = trade_env["app"]
    trade_id = _propose_trade(c)

    # Alice offers 3 Herbs
    c.put(f"/inventory/trade/{trade_id}/items", json={
        "character_id": 1,
        "items": [{"item_id": 101, "quantity": 3}],
        "gold": 0,
    })

    # Bob offers 2 Ores
    _switch_user(app, 2, "bob")
    c.put(f"/inventory/trade/{trade_id}/items", json={
        "character_id": 2,
        "items": [{"item_id": 102, "quantity": 2}],
        "gold": 0,
    })

    # Both confirm
    with patch("main.publish_notification_sync"):
        c.post(f"/inventory/trade/{trade_id}/confirm", json={"character_id": 2})

    _switch_user(app, 1, "alice")
    with patch("main.publish_notification_sync"):
        c.post(f"/inventory/trade/{trade_id}/confirm", json={"character_id": 1})

    # Verify Alice's inventory: should have 10-3=7 Herbs, +2 Ores
    alice_herbs = db.execute(text(
        "SELECT COALESCE(SUM(quantity), 0) FROM character_inventory "
        "WHERE character_id = 1 AND item_id = 101"
    )).scalar()
    assert alice_herbs == 7

    alice_ores = db.execute(text(
        "SELECT COALESCE(SUM(quantity), 0) FROM character_inventory "
        "WHERE character_id = 1 AND item_id = 102"
    )).scalar()
    assert alice_ores == 2

    # Verify Bob's inventory: should have 5-2=3 Ores, +3 Herbs
    bob_ores = db.execute(text(
        "SELECT COALESCE(SUM(quantity), 0) FROM character_inventory "
        "WHERE character_id = 2 AND item_id = 102"
    )).scalar()
    assert bob_ores == 3

    bob_herbs = db.execute(text(
        "SELECT COALESCE(SUM(quantity), 0) FROM character_inventory "
        "WHERE character_id = 2 AND item_id = 101"
    )).scalar()
    assert bob_herbs == 3


# ---------------------------------------------------------------------------
# Test: Confirm trade — verify gold transferred correctly
# ---------------------------------------------------------------------------

def test_confirm_trade_gold_transferred(trade_env):
    c = trade_env["client"]
    db = trade_env["db"]
    app = trade_env["app"]
    trade_id = _propose_trade(c)

    # Alice offers 100 gold, Bob offers 50 gold
    c.put(f"/inventory/trade/{trade_id}/items", json={
        "character_id": 1,
        "items": [],
        "gold": 100,
    })

    _switch_user(app, 2, "bob")
    c.put(f"/inventory/trade/{trade_id}/items", json={
        "character_id": 2,
        "items": [],
        "gold": 50,
    })

    with patch("main.publish_notification_sync"):
        c.post(f"/inventory/trade/{trade_id}/confirm", json={"character_id": 2})

    _switch_user(app, 1, "alice")
    with patch("main.publish_notification_sync"):
        c.post(f"/inventory/trade/{trade_id}/confirm", json={"character_id": 1})

    # Alice: 500 - 100 + 50 = 450
    alice_gold = db.execute(text(
        "SELECT currency_balance FROM characters WHERE id = 1"
    )).scalar()
    assert alice_gold == 450

    # Bob: 300 - 50 + 100 = 350
    bob_gold = db.execute(text(
        "SELECT currency_balance FROM characters WHERE id = 2"
    )).scalar()
    assert bob_gold == 350


# ---------------------------------------------------------------------------
# Test: Cancel trade — cancels successfully
# ---------------------------------------------------------------------------

def test_cancel_trade_success(trade_env):
    c = trade_env["client"]
    trade_id = _propose_trade(c)

    with patch("main.publish_notification_sync"):
        resp = c.post(f"/inventory/trade/{trade_id}/cancel")

    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Test: Cancel trade — non-participant blocked
# ---------------------------------------------------------------------------

def test_cancel_trade_non_participant_blocked(trade_env):
    c = trade_env["client"]
    db = trade_env["db"]
    app = trade_env["app"]
    trade_id = _propose_trade(c)

    _insert_character(db, 3, user_id=3, name="Eve", location=1)
    _switch_user(app, 3, "eve")

    with patch("main.publish_notification_sync"):
        resp = c.post(f"/inventory/trade/{trade_id}/cancel")

    assert resp.status_code == 403
    assert "участником" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test: Get trade state — returns full state with item details
# ---------------------------------------------------------------------------

def test_get_trade_state(trade_env):
    c = trade_env["client"]
    trade_id = _propose_trade(c)

    # Add items
    c.put(f"/inventory/trade/{trade_id}/items", json={
        "character_id": 1,
        "items": [{"item_id": 101, "quantity": 2}],
        "gold": 25,
    })

    resp = c.get(f"/inventory/trade/{trade_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["trade_id"] == trade_id
    assert data["initiator"]["character_id"] == 1
    assert data["initiator"]["character_name"] == "Alice"
    assert data["initiator"]["gold"] == 25
    assert len(data["initiator"]["items"]) == 1
    assert data["initiator"]["items"][0]["item_name"] == "Herb"
    assert data["target"]["character_id"] == 2
    assert data["target"]["character_name"] == "Bob"
