"""
Task 12 — QA tests for FEAT-096: Auction House API endpoints.

Integration tests using FastAPI TestClient for all 10 auction endpoints.
Covers auth, NPC gating, pagination, filtering, sorting, error messages.
"""

import json
import math
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import text

from auth_http import get_current_user_via_http, UserRead
import models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_characters_table(db):
    """Create minimal characters + battle tables for auction checks."""
    db.execute(text("DROP TABLE IF EXISTS battle_participants"))
    db.execute(text("DROP TABLE IF EXISTS battles"))
    db.execute(text("DROP TABLE IF EXISTS characters"))
    db.execute(text(
        """CREATE TABLE characters (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL DEFAULT 'TestChar',
            user_id INTEGER NOT NULL,
            current_location_id INTEGER DEFAULT 1,
            currency_balance INTEGER DEFAULT 0,
            is_npc INTEGER DEFAULT 0,
            npc_role TEXT DEFAULT NULL,
            is_alive INTEGER DEFAULT 1
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
        "INSERT OR IGNORE INTO characters "
        "(id, name, user_id, current_location_id, currency_balance, is_npc, npc_role, is_alive) "
        "VALUES (:cid, :name, :uid, :loc, :gold, 0, NULL, 1)"
    ), {"cid": char_id, "name": name, "uid": user_id, "loc": location, "gold": gold})
    db.commit()


def _insert_npc_auctioneer(db, npc_id, location):
    db.execute(text(
        "INSERT OR IGNORE INTO characters "
        "(id, name, user_id, current_location_id, currency_balance, is_npc, npc_role, is_alive) "
        "VALUES (:cid, 'Аукционист', 0, :loc, 0, 1, 'auctioneer', 1)"
    ), {"cid": npc_id, "loc": location})
    db.commit()


def _create_item(db, item_id, name, max_stack=10, item_type="resource", rarity="common"):
    item = models.Items(
        id=item_id,
        name=name,
        item_level=1,
        item_type=item_type,
        item_rarity=rarity,
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


def _create_listing_in_db(db, seller_id=1, item_id=201, qty=1, start=100, buyout=500, status='active'):
    now = datetime.utcnow()
    listing = models.AuctionListing(
        seller_character_id=seller_id,
        item_id=item_id,
        quantity=qty,
        start_price=start,
        buyout_price=buyout,
        current_bid=0,
        current_bidder_id=None,
        status=status,
        created_at=now,
        expires_at=now + timedelta(hours=48),
    )
    db.add(listing)
    db.flush()
    return listing


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def auction_client(client, db_session):
    """
    Set up auction test env with authenticated user and mocked RabbitMQ.
    """
    _create_characters_table(db_session)
    _insert_character(db_session, 1, user_id=1, name="Alice", location=1, gold=5000)
    _insert_character(db_session, 2, user_id=2, name="Bob", location=1, gold=3000)
    _insert_npc_auctioneer(db_session, 100, location=1)

    _create_item(db_session, 201, "Iron Sword", max_stack=1, item_type="main_weapon", rarity="common")
    _create_item(db_session, 202, "Herb", max_stack=99, item_type="resource", rarity="common")
    _create_item(db_session, 203, "Magic Staff", max_stack=1, item_type="main_weapon", rarity="epic")

    inv1 = _add_inventory(db_session, 1, 201, 1)
    inv2 = _add_inventory(db_session, 1, 202, 50)
    inv3 = _add_inventory(db_session, 1, 203, 1)

    db_session.commit()

    from main import app

    _user1 = UserRead(id=1, username="alice", role="user", permissions=[])
    app.dependency_overrides[get_current_user_via_http] = lambda: _user1

    with patch("crud.publish_auction_notification"), \
         patch("main.publish_notification_sync", create=True):
        yield {
            "client": client,
            "db": db_session,
            "app": app,
            "user1": _user1,
            "inv_sword_id": inv1.id,
            "inv_herb_id": inv2.id,
            "inv_staff_id": inv3.id,
        }

    app.dependency_overrides.pop(get_current_user_via_http, None)


def _switch_user(app, user_id, username="bob"):
    user = UserRead(id=user_id, username=username, role="user", permissions=[])
    app.dependency_overrides[get_current_user_via_http] = lambda: user
    return user


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

def test_auth_required_listings(db_session, client):
    """GET /inventory/auction/my-listings requires auth."""
    _create_characters_table(db_session)
    from main import app
    app.dependency_overrides.clear()
    # Without auth override, the call to user-service will fail
    resp = client.get("/inventory/auction/my-listings?character_id=1")
    # Should be 401 or 503 (service unavailable) because no real auth service
    assert resp.status_code in (401, 503)


def test_auth_wrong_user_create_listing(auction_client):
    """User 1 cannot create listing for user 2's character."""
    env = auction_client
    c = env["client"]

    # Add inventory for character 2
    _add_inventory(env["db"], 2, 201, 1)
    env["db"].commit()
    inv = env["db"].query(models.CharacterInventory).filter(
        models.CharacterInventory.character_id == 2,
    ).first()

    resp = c.post("/inventory/auction/listings", json={
        "character_id": 2,
        "inventory_item_id": inv.id,
        "quantity": 1,
        "start_price": 100,
    })
    assert resp.status_code == 403
    assert "своими персонажами" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /inventory/auction/listings — browse
# ---------------------------------------------------------------------------

def test_browse_listings_empty(auction_client):
    c = auction_client["client"]
    resp = c.get("/inventory/auction/listings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["listings"] == []
    assert data["total"] == 0


def test_browse_listings_pagination(auction_client):
    db = auction_client["db"]

    # Create 5 listings
    for i in range(5):
        _create_item(db, 300 + i, f"TestItem{i}", max_stack=10)
        _create_listing_in_db(db, seller_id=1, item_id=300 + i, start=10 + i)
    db.commit()

    c = auction_client["client"]
    resp = c.get("/inventory/auction/listings?page=1&per_page=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["listings"]) == 2
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["per_page"] == 2


def test_browse_listings_filter_item_type(auction_client):
    db = auction_client["db"]

    _create_listing_in_db(db, seller_id=1, item_id=201, start=100)  # main_weapon
    _create_listing_in_db(db, seller_id=1, item_id=202, start=50)   # resource
    db.commit()

    c = auction_client["client"]
    resp = c.get("/inventory/auction/listings?item_type=main_weapon")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["listings"][0]["item"]["item_type"] == "main_weapon"


def test_browse_listings_filter_rarity(auction_client):
    db = auction_client["db"]

    _create_listing_in_db(db, seller_id=1, item_id=201, start=100)  # common
    _create_listing_in_db(db, seller_id=1, item_id=203, start=500)  # epic
    db.commit()

    c = auction_client["client"]
    resp = c.get("/inventory/auction/listings?rarity=epic")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["listings"][0]["item"]["item_rarity"] == "epic"


def test_browse_listings_sort_price(auction_client):
    db = auction_client["db"]

    l1 = _create_listing_in_db(db, seller_id=1, item_id=201, start=300)
    l2 = _create_listing_in_db(db, seller_id=1, item_id=202, start=50)
    db.commit()

    c = auction_client["client"]
    resp = c.get("/inventory/auction/listings?sort=price_asc")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["listings"]) == 2
    # First should have lower start_price
    assert data["listings"][0]["start_price"] <= data["listings"][1]["start_price"]


def test_browse_listings_search(auction_client):
    db = auction_client["db"]

    _create_listing_in_db(db, seller_id=1, item_id=201, start=100)  # Iron Sword
    _create_listing_in_db(db, seller_id=1, item_id=202, start=50)   # Herb
    db.commit()

    c = auction_client["client"]
    resp = c.get("/inventory/auction/listings?search=Iron")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert "Iron" in data["listings"][0]["item"]["name"]


# ---------------------------------------------------------------------------
# GET /inventory/auction/listings/{id}
# ---------------------------------------------------------------------------

def test_get_single_listing_found(auction_client):
    db = auction_client["db"]
    listing = _create_listing_in_db(db, seller_id=1, item_id=201, start=100)
    db.commit()

    c = auction_client["client"]
    resp = c.get(f"/inventory/auction/listings/{listing.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == listing.id
    assert data["start_price"] == 100


def test_get_single_listing_not_found(auction_client):
    c = auction_client["client"]
    resp = c.get("/inventory/auction/listings/99999")
    assert resp.status_code == 404
    assert "не найден" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /inventory/auction/listings — create
# ---------------------------------------------------------------------------

def test_create_listing_success(auction_client):
    c = auction_client["client"]
    resp = c.post("/inventory/auction/listings", json={
        "character_id": 1,
        "inventory_item_id": auction_client["inv_sword_id"],
        "quantity": 1,
        "start_price": 100,
        "buyout_price": 500,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["listing_id"] is not None
    assert data["item_name"] == "Iron Sword"


def test_create_listing_limit_exceeded(auction_client):
    db = auction_client["db"]
    c = auction_client["client"]

    # Create 5 items and list them
    for i in range(5):
        _create_item(db, 400 + i, f"LimitItem{i}", max_stack=10)
        inv = _add_inventory(db, 1, 400 + i, 5)
        db.flush()
    db.commit()

    invs = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.character_id == 1,
        models.CharacterInventory.item_id.in_([400, 401, 402, 403, 404]),
    ).all()

    for inv in invs:
        resp = c.post("/inventory/auction/listings", json={
            "character_id": 1,
            "inventory_item_id": inv.id,
            "quantity": 1,
            "start_price": 10,
        })
        assert resp.status_code == 201

    # 6th should fail
    _create_item(db, 499, "OverLimit", max_stack=10)
    inv6 = _add_inventory(db, 1, 499, 5)
    db.commit()

    resp = c.post("/inventory/auction/listings", json={
        "character_id": 1,
        "inventory_item_id": inv6.id,
        "quantity": 1,
        "start_price": 10,
    })
    assert resp.status_code == 400
    assert "лимит" in resp.json()["detail"].lower()


def test_create_listing_npc_gating(auction_client):
    """Creating listing without auctioneer NPC returns 403."""
    db = auction_client["db"]
    c = auction_client["client"]

    # Move character away from auctioneer
    db.execute(text("UPDATE characters SET current_location_id = 99 WHERE id = 1 AND is_npc = 0"))
    db.commit()

    resp = c.post("/inventory/auction/listings", json={
        "character_id": 1,
        "inventory_item_id": auction_client["inv_sword_id"],
        "quantity": 1,
        "start_price": 100,
    })
    assert resp.status_code == 403
    assert "НПС-Аукционист" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /inventory/auction/listings/{id}/bid
# ---------------------------------------------------------------------------

def test_bid_success(auction_client):
    db = auction_client["db"]
    listing = _create_listing_in_db(db, seller_id=1, item_id=201, start=100, buyout=500)
    db.commit()

    _switch_user(auction_client["app"], 2, "bob")
    c = auction_client["client"]
    resp = c.post(f"/inventory/auction/listings/{listing.id}/bid", json={
        "character_id": 2,
        "amount": 150,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["amount"] == 150
    assert data["message"] == "Ставка принята"


def test_bid_on_own_listing(auction_client):
    db = auction_client["db"]
    listing = _create_listing_in_db(db, seller_id=1, item_id=201, start=100, buyout=500)
    db.commit()

    c = auction_client["client"]
    resp = c.post(f"/inventory/auction/listings/{listing.id}/bid", json={
        "character_id": 1,
        "amount": 150,
    })
    assert resp.status_code == 400
    assert "свой лот" in resp.json()["detail"]


def test_bid_insufficient_gold(auction_client):
    db = auction_client["db"]
    listing = _create_listing_in_db(db, seller_id=1, item_id=201, start=100, buyout=500)
    db.execute(text("UPDATE characters SET currency_balance = 0 WHERE id = 2"))
    db.commit()

    _switch_user(auction_client["app"], 2, "bob")
    c = auction_client["client"]
    resp = c.post(f"/inventory/auction/listings/{listing.id}/bid", json={
        "character_id": 2,
        "amount": 150,
    })
    assert resp.status_code == 400
    assert "золота" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /inventory/auction/listings/{id}/buyout
# ---------------------------------------------------------------------------

def test_buyout_success(auction_client):
    db = auction_client["db"]
    listing = _create_listing_in_db(db, seller_id=1, item_id=201, start=100, buyout=500)
    db.commit()

    _switch_user(auction_client["app"], 2, "bob")
    c = auction_client["client"]
    resp = c.post(f"/inventory/auction/listings/{listing.id}/buyout", json={
        "character_id": 2,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["amount"] == 500
    assert data["message"] == "Предмет выкуплен"


def test_buyout_no_price(auction_client):
    db = auction_client["db"]
    listing = _create_listing_in_db(db, seller_id=1, item_id=201, start=100, buyout=None)
    listing.buyout_price = None
    db.flush()
    db.commit()

    _switch_user(auction_client["app"], 2, "bob")
    c = auction_client["client"]
    resp = c.post(f"/inventory/auction/listings/{listing.id}/buyout", json={
        "character_id": 2,
    })
    assert resp.status_code == 400
    assert "нет цены выкупа" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /inventory/auction/listings/{id}/cancel
# ---------------------------------------------------------------------------

def test_cancel_success(auction_client):
    db = auction_client["db"]
    listing = _create_listing_in_db(db, seller_id=1, item_id=201, start=100, buyout=500)
    db.commit()

    c = auction_client["client"]
    resp = c.post(f"/inventory/auction/listings/{listing.id}/cancel", json={
        "character_id": 1,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "отменён" in data["message"]


def test_cancel_not_seller(auction_client):
    db = auction_client["db"]
    listing = _create_listing_in_db(db, seller_id=1, item_id=201, start=100)
    db.commit()

    _switch_user(auction_client["app"], 2, "bob")
    c = auction_client["client"]
    resp = c.post(f"/inventory/auction/listings/{listing.id}/cancel", json={
        "character_id": 2,
    })
    assert resp.status_code == 403
    assert "свои лоты" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /inventory/auction/my-listings
# ---------------------------------------------------------------------------

def test_my_listings_active_and_completed(auction_client):
    db = auction_client["db"]

    # Active listing
    _create_listing_in_db(db, seller_id=1, item_id=201, start=100)
    # Completed listing
    completed = _create_listing_in_db(db, seller_id=1, item_id=202, start=50, status='sold')
    completed.completed_at = datetime.utcnow()
    db.flush()
    db.commit()

    c = auction_client["client"]
    resp = c.get("/inventory/auction/my-listings?character_id=1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["active"]) == 1
    assert len(data["completed"]) == 1


# ---------------------------------------------------------------------------
# GET /inventory/auction/storage
# ---------------------------------------------------------------------------

def test_storage_npc_gating(auction_client):
    """Storage endpoint requires auctioneer NPC at location."""
    db = auction_client["db"]
    db.execute(text("UPDATE characters SET current_location_id = 99 WHERE id = 1 AND is_npc = 0"))
    db.commit()

    c = auction_client["client"]
    resp = c.get("/inventory/auction/storage?character_id=1")
    assert resp.status_code == 403
    assert "НПС-Аукционист" in resp.json()["detail"]


def test_storage_with_items(auction_client):
    db = auction_client["db"]
    storage = models.AuctionStorage(
        character_id=1,
        item_id=201,
        quantity=1,
        gold_amount=0,
        source='purchase',
    )
    db.add(storage)
    db.commit()

    c = auction_client["client"]
    resp = c.get("/inventory/auction/storage?character_id=1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["source"] == "purchase"


# ---------------------------------------------------------------------------
# POST /inventory/auction/storage/claim
# ---------------------------------------------------------------------------

def test_claim_success(auction_client):
    db = auction_client["db"]
    storage = models.AuctionStorage(
        character_id=1,
        item_id=202,
        quantity=5,
        gold_amount=0,
        source='purchase',
    )
    db.add(storage)
    db.commit()

    c = auction_client["client"]
    resp = c.post("/inventory/auction/storage/claim", json={
        "character_id": 1,
        "storage_ids": [storage.id],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["claimed_items"] == 1


def test_claim_npc_gating(auction_client):
    """Claim requires NPC auctioneer at location."""
    db = auction_client["db"]
    storage = models.AuctionStorage(
        character_id=1,
        item_id=202,
        quantity=5,
        gold_amount=0,
        source='purchase',
    )
    db.add(storage)
    db.execute(text("UPDATE characters SET current_location_id = 99 WHERE id = 1 AND is_npc = 0"))
    db.commit()

    c = auction_client["client"]
    resp = c.post("/inventory/auction/storage/claim", json={
        "character_id": 1,
        "storage_ids": [storage.id],
    })
    assert resp.status_code == 403
    assert "НПС-Аукционист" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /inventory/auction/check-auctioneer
# ---------------------------------------------------------------------------

def test_check_auctioneer_has(auction_client):
    c = auction_client["client"]
    resp = c.get("/inventory/auction/check-auctioneer?character_id=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_auctioneer"] is True
    assert data["auctioneer_name"] == "Аукционист"


def test_check_auctioneer_no(auction_client):
    db = auction_client["db"]
    db.execute(text("UPDATE characters SET current_location_id = 99 WHERE id = 1 AND is_npc = 0"))
    db.commit()

    c = auction_client["client"]
    resp = c.get("/inventory/auction/check-auctioneer?character_id=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_auctioneer"] is False
    assert data["auctioneer_name"] is None


# ---------------------------------------------------------------------------
# Error message verification (Russian messages)
# ---------------------------------------------------------------------------

def test_error_messages_russian_listing_not_found(auction_client):
    c = auction_client["client"]
    resp = c.get("/inventory/auction/listings/99999")
    assert resp.status_code == 404
    assert "Лот не найден" in resp.json()["detail"]


def test_error_messages_russian_insufficient_gold(auction_client):
    db = auction_client["db"]
    listing = _create_listing_in_db(db, seller_id=1, item_id=201, start=100, buyout=500)
    db.execute(text("UPDATE characters SET currency_balance = 0 WHERE id = 2"))
    db.commit()

    _switch_user(auction_client["app"], 2, "bob")
    c = auction_client["client"]
    resp = c.post(f"/inventory/auction/listings/{listing.id}/bid", json={
        "character_id": 2,
        "amount": 150,
    })
    assert resp.status_code == 400
    assert "Недостаточно золота" in resp.json()["detail"]


def test_error_messages_russian_own_listing_bid(auction_client):
    db = auction_client["db"]
    listing = _create_listing_in_db(db, seller_id=1, item_id=201, start=100)
    db.commit()

    c = auction_client["client"]
    resp = c.post(f"/inventory/auction/listings/{listing.id}/bid", json={
        "character_id": 1,
        "amount": 150,
    })
    assert "свой лот" in resp.json()["detail"]


def test_error_messages_russian_npc_required(auction_client):
    db = auction_client["db"]
    db.execute(text("UPDATE characters SET current_location_id = 99 WHERE id = 1 AND is_npc = 0"))
    db.commit()

    c = auction_client["client"]
    resp = c.post("/inventory/auction/listings", json={
        "character_id": 1,
        "inventory_item_id": auction_client["inv_sword_id"],
        "quantity": 1,
        "start_price": 100,
    })
    assert "НПС-Аукционист" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# SQL injection test
# ---------------------------------------------------------------------------

def test_sql_injection_in_search(auction_client):
    c = auction_client["client"]
    resp = c.get("/inventory/auction/listings?search='; DROP TABLE auction_listings; --")
    assert resp.status_code == 200  # Must not crash


# ---------------------------------------------------------------------------
# Sorting name_asc/name_desc
# ---------------------------------------------------------------------------

def test_browse_listings_sort_name(auction_client):
    db = auction_client["db"]
    _create_listing_in_db(db, seller_id=1, item_id=201, start=100)  # Iron Sword
    _create_listing_in_db(db, seller_id=1, item_id=202, start=50)   # Herb
    db.commit()

    c = auction_client["client"]
    resp = c.get("/inventory/auction/listings?sort=name_asc")
    assert resp.status_code == 200
    data = resp.json()
    names = [l["item"]["name"] for l in data["listings"]]
    assert names == sorted(names)
