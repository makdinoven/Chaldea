"""
Task 11 — QA tests for FEAT-096: Auction House CRUD functions.

Tests covering: create_auction_listing, place_bid, execute_buyout,
cancel_listing, claim_from_storage, expire_stale_listings,
check_auctioneer_at_character_location, and commission calculations.
"""

import json
import math
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import text

import models
import schemas
import crud


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
            npc_status TEXT DEFAULT 'alive',
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
        "(id, name, user_id, current_location_id, currency_balance, is_npc, npc_role, npc_status, is_alive) "
        "VALUES (:cid, :name, :uid, :loc, :gold, 0, NULL, 'alive', 1)"
    ), {"cid": char_id, "name": name, "uid": user_id, "loc": location, "gold": gold})
    db.commit()


def _insert_npc_auctioneer(db, npc_id, location):
    """Insert an NPC auctioneer at the given location."""
    db.execute(text(
        "INSERT OR IGNORE INTO characters "
        "(id, name, user_id, current_location_id, currency_balance, is_npc, npc_role, npc_status, is_alive) "
        "VALUES (:cid, 'Аукционист', 0, :loc, 0, 1, 'auctioneer', 'alive', 1)"
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


def _add_inventory(db, char_id, item_id, quantity, enhancement_points=0, enhancement_bonuses=None):
    inv = models.CharacterInventory(
        character_id=char_id,
        item_id=item_id,
        quantity=quantity,
        enhancement_points_spent=enhancement_points,
        enhancement_bonuses=enhancement_bonuses,
    )
    db.add(inv)
    db.flush()
    return inv


def _deposit_to_storage(db, char_id, item_id, quantity, enhancement_data=None):
    """Create an auction storage entry (simulates deposit)."""
    storage = models.AuctionStorage(
        character_id=char_id,
        item_id=item_id,
        quantity=quantity,
        gold_amount=0,
        enhancement_data=enhancement_data,
        source='deposit',
    )
    db.add(storage)
    db.flush()
    return storage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def auction_env(db_session):
    """
    Set up a full auction test environment:
    - characters table with two characters at location 1
    - NPC auctioneer at location 1
    - items in inventories
    """
    _create_characters_table(db_session)
    _insert_character(db_session, 1, user_id=1, name="Alice", location=1, gold=5000)
    _insert_character(db_session, 2, user_id=2, name="Bob", location=1, gold=3000)
    _insert_npc_auctioneer(db_session, 100, location=1)

    _create_item(db_session, 201, "Iron Sword", max_stack=1, item_type="main_weapon")
    _create_item(db_session, 202, "Herb", max_stack=99, item_type="resource")

    inv1 = _add_inventory(db_session, 1, 201, 1)
    inv2 = _add_inventory(db_session, 1, 202, 50)

    db_session.commit()

    yield {
        "db": db_session,
        "inv_sword_id": inv1.id,
        "inv_herb_id": inv2.id,
    }


# ---------------------------------------------------------------------------
# check_auctioneer_at_character_location
# ---------------------------------------------------------------------------

def test_check_auctioneer_present(auction_env):
    db = auction_env["db"]
    result = crud.check_auctioneer_at_character_location(db, character_id=1)
    assert result is not None
    assert result["name"] == "Аукционист"


def test_check_auctioneer_absent(auction_env):
    db = auction_env["db"]
    # Move character to location 99 where there is no NPC
    db.execute(text("UPDATE characters SET current_location_id = 99 WHERE id = 1 AND is_npc = 0"))
    db.commit()
    result = crud.check_auctioneer_at_character_location(db, character_id=1)
    assert result is None


# ---------------------------------------------------------------------------
# create_auction_listing
# ---------------------------------------------------------------------------

@patch("crud.publish_auction_notification")
def test_create_listing_happy_path(mock_notify, auction_env):
    db = auction_env["db"]
    storage = _deposit_to_storage(db, 1, 201, 1)
    db.commit()

    req = schemas.AuctionCreateListingRequest(
        character_id=1,
        storage_id=storage.id,
        start_price=100,
        buyout_price=500,
    )
    result = crud.create_auction_listing(db, data=req, user_id=1)
    db.commit()

    assert result["listing_id"] is not None
    assert result["item_name"] == "Iron Sword"
    assert result["start_price"] == 100
    assert result["buyout_price"] == 500
    assert result["active_listing_count"] == 1

    # Verify storage entry removed
    remaining = db.query(models.AuctionStorage).filter(
        models.AuctionStorage.id == storage.id
    ).first()
    assert remaining is None


@patch("crud.publish_auction_notification")
def test_create_listing_from_storage(mock_notify, auction_env):
    """Listing from storage uses the full storage quantity."""
    db = auction_env["db"]
    storage = _deposit_to_storage(db, 1, 202, 10)
    db.commit()

    req = schemas.AuctionCreateListingRequest(
        character_id=1,
        storage_id=storage.id,
        start_price=50,
    )
    result = crud.create_auction_listing(db, data=req, user_id=1)
    db.commit()

    assert result["quantity"] == 10

    # Storage entry should be deleted
    remaining = db.query(models.AuctionStorage).filter(
        models.AuctionStorage.id == storage.id
    ).first()
    assert remaining is None


@patch("crud.publish_auction_notification")
def test_create_listing_storage_not_found(mock_notify, auction_env):
    db = auction_env["db"]
    req = schemas.AuctionCreateListingRequest(
        character_id=1,
        storage_id=99999,  # Non-existent storage entry
        start_price=100,
    )
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        crud.create_auction_listing(db, data=req, user_id=1)
    assert exc.value.status_code == 400
    assert "склад" in exc.value.detail.lower() or "не найден" in exc.value.detail.lower()


@patch("crud.publish_auction_notification")
def test_create_listing_max_limit(mock_notify, auction_env):
    """Cannot exceed 5 active listings."""
    db = auction_env["db"]

    # Create 5 items + storage entries and list them
    for i in range(5):
        _create_item(db, 300 + i, f"Item{i}", max_stack=10)
        storage = _deposit_to_storage(db, 1, 300 + i, 1)
        db.flush()
        req = schemas.AuctionCreateListingRequest(
            character_id=1,
            storage_id=storage.id,
            start_price=10,
        )
        crud.create_auction_listing(db, data=req, user_id=1)

    # 6th listing should fail
    _create_item(db, 399, "Extra", max_stack=10)
    storage6 = _deposit_to_storage(db, 1, 399, 1)
    db.flush()
    req6 = schemas.AuctionCreateListingRequest(
        character_id=1,
        storage_id=storage6.id,
        start_price=10,
    )
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        crud.create_auction_listing(db, data=req6, user_id=1)
    assert exc.value.status_code == 400
    assert "лимит" in exc.value.detail.lower()


@patch("crud.publish_auction_notification")
def test_create_listing_invalid_price_zero(mock_notify, auction_env):
    db = auction_env["db"]
    storage = _deposit_to_storage(db, 1, 201, 1)
    db.commit()

    req = schemas.AuctionCreateListingRequest(
        character_id=1,
        storage_id=storage.id,
        start_price=0,
    )
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        crud.create_auction_listing(db, data=req, user_id=1)
    assert exc.value.status_code == 400
    assert "больше 0" in exc.value.detail


@patch("crud.publish_auction_notification")
def test_create_listing_buyout_must_exceed_start(mock_notify, auction_env):
    db = auction_env["db"]
    storage = _deposit_to_storage(db, 1, 201, 1)
    db.commit()

    req = schemas.AuctionCreateListingRequest(
        character_id=1,
        storage_id=storage.id,
        start_price=100,
        buyout_price=50,  # lower than start
    )
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        crud.create_auction_listing(db, data=req, user_id=1)
    assert exc.value.status_code == 400
    assert "больше начальной" in exc.value.detail


@patch("crud.publish_auction_notification")
def test_deposit_no_auctioneer(mock_notify, auction_env):
    """Without NPC auctioneer at location, deposit is forbidden."""
    db = auction_env["db"]
    # Move player to location 99 (no auctioneer)
    db.execute(text("UPDATE characters SET current_location_id = 99 WHERE id = 1 AND is_npc = 0"))
    db.commit()

    req = schemas.AuctionDepositRequest(
        character_id=1,
        inventory_item_id=auction_env["inv_sword_id"],
        quantity=1,
    )
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        crud.deposit_to_auction_storage(db, data=req, user_id=1)
    assert exc.value.status_code == 403
    assert "НПС-Аукционист" in exc.value.detail


@patch("crud.publish_auction_notification")
def test_create_listing_in_battle_blocked(mock_notify, auction_env):
    """Characters in battle cannot create listings."""
    db = auction_env["db"]
    storage = _deposit_to_storage(db, 1, 201, 1)
    db.execute(text("INSERT INTO battles (id, status) VALUES (1, 'in_progress')"))
    db.execute(text("INSERT INTO battle_participants (id, battle_id, character_id) VALUES (1, 1, 1)"))
    db.commit()

    req = schemas.AuctionCreateListingRequest(
        character_id=1,
        storage_id=storage.id,
        start_price=100,
    )
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        crud.create_auction_listing(db, data=req, user_id=1)
    assert exc.value.status_code == 400
    assert "боя" in exc.value.detail


@patch("crud.publish_auction_notification")
def test_create_listing_enhancement_data_snapshot(mock_notify, auction_env):
    """Enhancement data is preserved in the listing via storage."""
    db = auction_env["db"]
    _create_item(db, 500, "Magic Sword", max_stack=1, item_type="main_weapon")
    enh_data = json.dumps({
        "enhancement_points_spent": 5,
        "enhancement_bonuses": {"strength_modifier": 3},
    })
    storage = _deposit_to_storage(db, 1, 500, 1, enhancement_data=enh_data)
    db.commit()

    req = schemas.AuctionCreateListingRequest(
        character_id=1,
        storage_id=storage.id,
        start_price=100,
    )
    result = crud.create_auction_listing(db, data=req, user_id=1)
    db.commit()

    listing = db.query(models.AuctionListing).filter(
        models.AuctionListing.id == result["listing_id"]
    ).first()
    assert listing.enhancement_data is not None
    enh = json.loads(listing.enhancement_data)
    assert enh["enhancement_points_spent"] == 5
    assert enh["enhancement_bonuses"]["strength_modifier"] == 3


# ---------------------------------------------------------------------------
# place_bid
# ---------------------------------------------------------------------------

def _create_listing(db, seller_id=1, item_id=201, qty=1, start=100, buyout=500):
    """Helper to create a listing directly in DB."""
    now = datetime.utcnow()
    listing = models.AuctionListing(
        seller_character_id=seller_id,
        item_id=item_id,
        quantity=qty,
        start_price=start,
        buyout_price=buyout,
        current_bid=0,
        current_bidder_id=None,
        status='active',
        created_at=now,
        expires_at=now + timedelta(hours=48),
    )
    db.add(listing)
    db.flush()
    return listing


@patch("crud.publish_auction_notification")
def test_place_bid_happy_path(mock_notify, auction_env):
    db = auction_env["db"]
    listing = _create_listing(db, seller_id=1, start=100, buyout=500)
    db.commit()

    req = schemas.AuctionBidRequest(character_id=2, amount=150)
    result = crud.place_bid(db, listing_id=listing.id, data=req, user_id=2)
    db.commit()

    assert result["amount"] == 150
    assert result["message"] == "Ставка принята"

    # Verify gold deducted
    gold = db.execute(text("SELECT currency_balance FROM characters WHERE id = 2")).fetchone()[0]
    assert gold == 3000 - 150


@patch("crud.publish_auction_notification")
def test_place_bid_on_own_listing(mock_notify, auction_env):
    db = auction_env["db"]
    listing = _create_listing(db, seller_id=1)
    db.commit()

    req = schemas.AuctionBidRequest(character_id=1, amount=150)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        crud.place_bid(db, listing_id=listing.id, data=req, user_id=1)
    assert exc.value.status_code == 400
    assert "свой лот" in exc.value.detail


@patch("crud.publish_auction_notification")
def test_place_bid_insufficient_gold(mock_notify, auction_env):
    db = auction_env["db"]
    listing = _create_listing(db, seller_id=1, start=100)
    db.commit()

    # Set Bob's gold to 0
    db.execute(text("UPDATE characters SET currency_balance = 0 WHERE id = 2"))
    db.commit()

    req = schemas.AuctionBidRequest(character_id=2, amount=150)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        crud.place_bid(db, listing_id=listing.id, data=req, user_id=2)
    assert exc.value.status_code == 400
    assert "золота" in exc.value.detail


@patch("crud.publish_auction_notification")
def test_place_bid_below_start_price(mock_notify, auction_env):
    db = auction_env["db"]
    listing = _create_listing(db, seller_id=1, start=100)
    db.commit()

    req = schemas.AuctionBidRequest(character_id=2, amount=50)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        crud.place_bid(db, listing_id=listing.id, data=req, user_id=2)
    assert exc.value.status_code == 400
    assert "начальной цены" in exc.value.detail


@patch("crud.publish_auction_notification")
def test_place_bid_below_current_bid(mock_notify, auction_env):
    db = auction_env["db"]
    listing = _create_listing(db, seller_id=1, start=100, buyout=1000)
    db.commit()

    # First bid
    req1 = schemas.AuctionBidRequest(character_id=2, amount=200)
    crud.place_bid(db, listing_id=listing.id, data=req1, user_id=2)
    db.commit()

    # Third character tries lower bid
    _insert_character(db, 3, user_id=3, name="Charlie", location=1, gold=5000)
    req2 = schemas.AuctionBidRequest(character_id=3, amount=150)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        crud.place_bid(db, listing_id=listing.id, data=req2, user_id=3)
    assert exc.value.status_code == 400
    assert "выше текущей" in exc.value.detail


@patch("crud.publish_auction_notification")
def test_place_bid_expired_listing(mock_notify, auction_env):
    db = auction_env["db"]
    listing = _create_listing(db, seller_id=1, start=100)
    # Expire the listing
    listing.expires_at = datetime.utcnow() - timedelta(hours=1)
    db.flush()
    db.commit()

    req = schemas.AuctionBidRequest(character_id=2, amount=150)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        crud.place_bid(db, listing_id=listing.id, data=req, user_id=2)
    assert exc.value.status_code == 400
    assert "истёк" in exc.value.detail


@patch("crud.publish_auction_notification")
def test_place_bid_refund_previous_bidder(mock_notify, auction_env):
    """When a new bid is placed, the previous bidder gets refunded."""
    db = auction_env["db"]
    listing = _create_listing(db, seller_id=1, start=100, buyout=1000)
    db.commit()

    # Bob bids 200
    req1 = schemas.AuctionBidRequest(character_id=2, amount=200)
    crud.place_bid(db, listing_id=listing.id, data=req1, user_id=2)
    db.commit()

    bob_gold_after_bid = db.execute(
        text("SELECT currency_balance FROM characters WHERE id = 2")
    ).fetchone()[0]
    assert bob_gold_after_bid == 3000 - 200

    # Charlie bids 300
    _insert_character(db, 3, user_id=3, name="Charlie", location=1, gold=5000)
    req2 = schemas.AuctionBidRequest(character_id=3, amount=300)
    crud.place_bid(db, listing_id=listing.id, data=req2, user_id=3)
    db.commit()

    # Bob should be refunded
    bob_gold_refunded = db.execute(
        text("SELECT currency_balance FROM characters WHERE id = 2")
    ).fetchone()[0]
    assert bob_gold_refunded == 3000  # fully restored

    # Previous bid marked as outbid
    old_bid = db.query(models.AuctionBid).filter(
        models.AuctionBid.bidder_character_id == 2
    ).first()
    assert old_bid.status == "outbid"


# ---------------------------------------------------------------------------
# execute_buyout
# ---------------------------------------------------------------------------

@patch("crud.publish_auction_notification")
def test_buyout_happy_path(mock_notify, auction_env):
    db = auction_env["db"]
    listing = _create_listing(db, seller_id=1, start=100, buyout=500)
    db.commit()

    req = schemas.AuctionBuyoutRequest(character_id=2)
    result = crud.execute_buyout(db, listing_id=listing.id, data=req, user_id=2)
    db.commit()

    assert result["amount"] == 500
    assert result["message"] == "Предмет выкуплен"

    # Listing marked sold
    listing = db.query(models.AuctionListing).get(listing.id)
    assert listing.status == "sold"

    # Buyer storage entry created
    buyer_storage = db.query(models.AuctionStorage).filter(
        models.AuctionStorage.character_id == 2,
        models.AuctionStorage.source == 'purchase',
    ).first()
    assert buyer_storage is not None
    assert buyer_storage.item_id == 201

    # Seller storage entry (gold) created with commission
    seller_storage = db.query(models.AuctionStorage).filter(
        models.AuctionStorage.character_id == 1,
        models.AuctionStorage.source == 'sale_proceeds',
    ).first()
    assert seller_storage is not None
    assert seller_storage.gold_amount == math.floor(500 * 0.95)  # 475


@patch("crud.publish_auction_notification")
def test_buyout_no_price_set(mock_notify, auction_env):
    db = auction_env["db"]
    listing = _create_listing(db, seller_id=1, start=100, buyout=None)
    listing.buyout_price = None
    db.flush()
    db.commit()

    req = schemas.AuctionBuyoutRequest(character_id=2)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        crud.execute_buyout(db, listing_id=listing.id, data=req, user_id=2)
    assert exc.value.status_code == 400
    assert "нет цены выкупа" in exc.value.detail


@patch("crud.publish_auction_notification")
def test_buyout_insufficient_gold(mock_notify, auction_env):
    db = auction_env["db"]
    listing = _create_listing(db, seller_id=1, start=100, buyout=500)
    db.commit()

    # Set Bob's gold to 100
    db.execute(text("UPDATE characters SET currency_balance = 100 WHERE id = 2"))
    db.commit()

    req = schemas.AuctionBuyoutRequest(character_id=2)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        crud.execute_buyout(db, listing_id=listing.id, data=req, user_id=2)
    assert exc.value.status_code == 400
    assert "золота" in exc.value.detail


@patch("crud.publish_auction_notification")
def test_buyout_commission_calculation(mock_notify, auction_env):
    """5% commission: seller receives floor(price * 0.95)."""
    db = auction_env["db"]
    listing = _create_listing(db, seller_id=1, start=100, buyout=333)
    db.commit()

    req = schemas.AuctionBuyoutRequest(character_id=2)
    crud.execute_buyout(db, listing_id=listing.id, data=req, user_id=2)
    db.commit()

    seller_storage = db.query(models.AuctionStorage).filter(
        models.AuctionStorage.character_id == 1,
        models.AuctionStorage.source == 'sale_proceeds',
    ).first()
    expected = math.floor(333 * 0.95)  # 316
    assert seller_storage.gold_amount == expected


@patch("crud.publish_auction_notification")
def test_buyout_refunds_previous_bidder(mock_notify, auction_env):
    """Buyout should refund the previous highest bidder."""
    db = auction_env["db"]
    listing = _create_listing(db, seller_id=1, start=100, buyout=1000)
    db.commit()

    # Bob bids
    bid_req = schemas.AuctionBidRequest(character_id=2, amount=200)
    crud.place_bid(db, listing_id=listing.id, data=bid_req, user_id=2)
    db.commit()

    bob_after_bid = db.execute(
        text("SELECT currency_balance FROM characters WHERE id = 2")
    ).fetchone()[0]

    # Charlie buyouts
    _insert_character(db, 3, user_id=3, name="Charlie", location=1, gold=5000)
    buyout_req = schemas.AuctionBuyoutRequest(character_id=3)
    crud.execute_buyout(db, listing_id=listing.id, data=buyout_req, user_id=3)
    db.commit()

    # Bob refunded
    bob_after_refund = db.execute(
        text("SELECT currency_balance FROM characters WHERE id = 2")
    ).fetchone()[0]
    assert bob_after_refund == bob_after_bid + 200


# ---------------------------------------------------------------------------
# cancel_listing
# ---------------------------------------------------------------------------

@patch("crud.publish_auction_notification")
def test_cancel_listing_happy_path(mock_notify, auction_env):
    db = auction_env["db"]
    listing = _create_listing(db, seller_id=1, start=100, buyout=500)
    db.commit()

    req = schemas.AuctionCancelRequest(character_id=1)
    result = crud.cancel_listing(db, listing_id=listing.id, data=req, user_id=1)
    db.commit()

    assert "отменён" in result["message"]

    # Listing cancelled
    listing = db.query(models.AuctionListing).get(listing.id)
    assert listing.status == "cancelled"

    # Item returned to storage
    storage = db.query(models.AuctionStorage).filter(
        models.AuctionStorage.character_id == 1,
        models.AuctionStorage.source == 'cancelled',
    ).first()
    assert storage is not None
    assert storage.item_id == 201


@patch("crud.publish_auction_notification")
def test_cancel_listing_not_seller(mock_notify, auction_env):
    db = auction_env["db"]
    listing = _create_listing(db, seller_id=1)
    db.commit()

    req = schemas.AuctionCancelRequest(character_id=2)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        crud.cancel_listing(db, listing_id=listing.id, data=req, user_id=2)
    assert exc.value.status_code == 403
    assert "свои лоты" in exc.value.detail


@patch("crud.publish_auction_notification")
def test_cancel_listing_refunds_bidder(mock_notify, auction_env):
    """Cancelling a listing with active bid refunds the bidder."""
    db = auction_env["db"]
    listing = _create_listing(db, seller_id=1, start=100, buyout=1000)
    db.commit()

    # Bob bids
    bid_req = schemas.AuctionBidRequest(character_id=2, amount=200)
    crud.place_bid(db, listing_id=listing.id, data=bid_req, user_id=2)
    db.commit()

    bob_before = db.execute(
        text("SELECT currency_balance FROM characters WHERE id = 2")
    ).fetchone()[0]

    # Seller cancels
    cancel_req = schemas.AuctionCancelRequest(character_id=1)
    crud.cancel_listing(db, listing_id=listing.id, data=cancel_req, user_id=1)
    db.commit()

    bob_after = db.execute(
        text("SELECT currency_balance FROM characters WHERE id = 2")
    ).fetchone()[0]
    assert bob_after == bob_before + 200

    # Bid marked as refunded
    bid = db.query(models.AuctionBid).filter(
        models.AuctionBid.bidder_character_id == 2,
        models.AuctionBid.listing_id == listing.id,
    ).first()
    assert bid.status == "refunded"


# ---------------------------------------------------------------------------
# claim_from_storage
# ---------------------------------------------------------------------------

@patch("crud.publish_auction_notification")
def test_claim_storage_items(mock_notify, auction_env):
    """Claim item from storage adds it to inventory."""
    db = auction_env["db"]
    storage = models.AuctionStorage(
        character_id=1,
        item_id=202,
        quantity=5,
        gold_amount=0,
        source='purchase',
    )
    db.add(storage)
    db.flush()
    db.commit()

    req = schemas.AuctionClaimRequest(character_id=1, storage_ids=[storage.id])
    result = crud.claim_from_storage(db, data=req, user_id=1)
    db.commit()

    assert result["claimed_items"] == 1
    assert result["claimed_gold"] == 0

    # Storage entry deleted
    remaining = db.query(models.AuctionStorage).filter(
        models.AuctionStorage.id == storage.id
    ).first()
    assert remaining is None


@patch("crud.publish_auction_notification")
def test_claim_storage_gold(mock_notify, auction_env):
    """Claim gold from storage adds to character balance."""
    db = auction_env["db"]
    initial_gold = db.execute(
        text("SELECT currency_balance FROM characters WHERE id = 1")
    ).fetchone()[0]

    storage = models.AuctionStorage(
        character_id=1,
        item_id=None,
        quantity=0,
        gold_amount=475,
        source='sale_proceeds',
    )
    db.add(storage)
    db.flush()
    db.commit()

    req = schemas.AuctionClaimRequest(character_id=1, storage_ids=[storage.id])
    result = crud.claim_from_storage(db, data=req, user_id=1)
    db.commit()

    assert result["claimed_gold"] == 475
    new_gold = db.execute(
        text("SELECT currency_balance FROM characters WHERE id = 1")
    ).fetchone()[0]
    assert new_gold == initial_gold + 475


@patch("crud.publish_auction_notification")
def test_claim_storage_with_enhancement_data(mock_notify, auction_env):
    """Enhanced item from storage should preserve enhancement data in inventory."""
    db = auction_env["db"]
    enh = json.dumps({
        "enhancement_points_spent": 10,
        "enhancement_bonuses": {"strength_modifier": 5},
        "socketed_gems": None,
        "current_durability": None,
        "is_identified": True,
    })
    storage = models.AuctionStorage(
        character_id=1,
        item_id=201,
        quantity=1,
        enhancement_data=enh,
        gold_amount=0,
        source='purchase',
    )
    db.add(storage)
    db.flush()
    db.commit()

    req = schemas.AuctionClaimRequest(character_id=1, storage_ids=[storage.id])
    crud.claim_from_storage(db, data=req, user_id=1)
    db.commit()

    # Find the new inventory entry
    inv = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.character_id == 1,
        models.CharacterInventory.item_id == 201,
        models.CharacterInventory.enhancement_points_spent == 10,
    ).first()
    assert inv is not None
    assert inv.enhancement_points_spent == 10
    bonuses = json.loads(inv.enhancement_bonuses)
    assert bonuses["strength_modifier"] == 5


# ---------------------------------------------------------------------------
# expire_stale_listings
# ---------------------------------------------------------------------------

@patch("crud.publish_auction_notification")
def test_expire_with_bids_sold(mock_notify, auction_env):
    """Expired listing with bids is marked as sold and items distributed."""
    db = auction_env["db"]
    listing = _create_listing(db, seller_id=1, start=100, buyout=500)
    listing.expires_at = datetime.utcnow() - timedelta(hours=1)
    listing.current_bid = 200
    listing.current_bidder_id = 2
    db.flush()

    # Create active bid
    bid = models.AuctionBid(
        listing_id=listing.id,
        bidder_character_id=2,
        amount=200,
        status='active',
    )
    db.add(bid)
    db.flush()
    db.commit()

    count = crud.expire_stale_listings(db)
    db.commit()

    assert count == 1

    listing = db.query(models.AuctionListing).get(listing.id)
    assert listing.status == "sold"

    # Buyer gets item in storage
    buyer_storage = db.query(models.AuctionStorage).filter(
        models.AuctionStorage.character_id == 2,
        models.AuctionStorage.source == 'purchase',
    ).first()
    assert buyer_storage is not None

    # Seller gets gold (minus commission)
    seller_storage = db.query(models.AuctionStorage).filter(
        models.AuctionStorage.character_id == 1,
        models.AuctionStorage.source == 'sale_proceeds',
    ).first()
    assert seller_storage is not None
    assert seller_storage.gold_amount == math.floor(200 * 0.95)


@patch("crud.publish_auction_notification")
def test_expire_without_bids_returned(mock_notify, auction_env):
    """Expired listing without bids returns item to seller's storage."""
    db = auction_env["db"]
    listing = _create_listing(db, seller_id=1, start=100, buyout=500)
    listing.expires_at = datetime.utcnow() - timedelta(hours=1)
    db.flush()
    db.commit()

    count = crud.expire_stale_listings(db)
    db.commit()

    assert count == 1

    listing = db.query(models.AuctionListing).get(listing.id)
    assert listing.status == "expired"

    storage = db.query(models.AuctionStorage).filter(
        models.AuctionStorage.character_id == 1,
        models.AuctionStorage.source == 'expired',
    ).first()
    assert storage is not None
    assert storage.item_id == 201


@patch("crud.publish_auction_notification")
def test_expire_sends_notifications(mock_notify, auction_env):
    """Expiration triggers notification calls."""
    db = auction_env["db"]
    listing = _create_listing(db, seller_id=1, start=100, buyout=500)
    listing.expires_at = datetime.utcnow() - timedelta(hours=1)
    db.flush()
    db.commit()

    crud.expire_stale_listings(db)
    db.commit()

    assert mock_notify.called


# ---------------------------------------------------------------------------
# Commission calculation
# ---------------------------------------------------------------------------

def test_commission_floor_calculation():
    """Verify floor(price * 0.95) for various prices."""
    rate = 0.05
    test_cases = [
        (100, 95),
        (333, 316),
        (1, 0),
        (10, 9),
        (999, 949),
        (1000, 950),
    ]
    for price, expected in test_cases:
        result = math.floor(price * (1 - rate))
        assert result == expected, f"For price {price}: expected {expected}, got {result}"


# ---------------------------------------------------------------------------
# Gold atomicity: verify atomic deduction pattern
# ---------------------------------------------------------------------------

@patch("crud.publish_auction_notification")
def test_gold_atomic_deduction_exact_balance(mock_notify, auction_env):
    """Bidding with exactly enough gold succeeds."""
    db = auction_env["db"]
    db.execute(text("UPDATE characters SET currency_balance = 150 WHERE id = 2"))
    db.commit()

    listing = _create_listing(db, seller_id=1, start=100, buyout=500)
    db.commit()

    req = schemas.AuctionBidRequest(character_id=2, amount=150)
    result = crud.place_bid(db, listing_id=listing.id, data=req, user_id=2)
    db.commit()

    assert result["new_gold_balance"] == 0
