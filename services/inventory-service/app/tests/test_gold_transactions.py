"""
Task #13 — QA: gold_transactions tests (inventory-service).

Tests that gold modifications in trades and auctions create gold_transaction records:
1. Trade gold transfer creates transactions for both parties
2. Auction bid creates a transaction (type "auction_buy")
3. Auction bid refund creates a transaction (type "auction_refund")
4. Auction buyout creates a transaction (type "auction_buy")
5. Auction claim creates a transaction (type "auction_sell")
6. log_gold_transaction helper — correct fields stored, exception safety
"""

import json
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
    """Create minimal characters + battle tables."""
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


def _create_gold_transactions_table(db):
    """Create the gold_transactions table (owned by character-service, shared DB)."""
    db.execute(text("DROP TABLE IF EXISTS gold_transactions"))
    db.execute(text(
        """CREATE TABLE gold_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            balance_after INTEGER NOT NULL,
            transaction_type VARCHAR(50) NOT NULL,
            source VARCHAR(100),
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


def _add_inventory(db, char_id, item_id, quantity):
    inv = models.CharacterInventory(character_id=char_id, item_id=item_id, quantity=quantity)
    db.add(inv)
    db.flush()
    return inv


def _create_listing(db, seller_id, item_id, quantity=1, start_price=100,
                    buyout_price=500, status='active'):
    """Directly create an AuctionListing in DB for testing."""
    now = datetime.utcnow()
    listing = models.AuctionListing(
        seller_character_id=seller_id,
        item_id=item_id,
        quantity=quantity,
        start_price=start_price,
        buyout_price=buyout_price,
        current_bid=0,
        current_bidder_id=None,
        status=status,
        created_at=now,
        expires_at=now + timedelta(hours=24),
    )
    db.add(listing)
    db.flush()
    return listing


def _count_gold_transactions(db, character_id=None, transaction_type=None):
    """Count rows in gold_transactions."""
    q = "SELECT COUNT(*) FROM gold_transactions WHERE 1=1"
    params = {}
    if character_id is not None:
        q += " AND character_id = :cid"
        params["cid"] = character_id
    if transaction_type is not None:
        q += " AND transaction_type = :ttype"
        params["ttype"] = transaction_type
    row = db.execute(text(q), params).fetchone()
    return row[0]


def _get_gold_transactions(db, character_id, transaction_type=None):
    """Fetch all gold_transactions for a character."""
    q = ("SELECT id, character_id, amount, balance_after, transaction_type, source, metadata "
         "FROM gold_transactions WHERE character_id = :cid")
    params = {"cid": character_id}
    if transaction_type:
        q += " AND transaction_type = :ttype"
        params["ttype"] = transaction_type
    q += " ORDER BY id"
    return db.execute(text(q), params).fetchall()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def gold_env(db_session):
    """Set up environment with characters table and gold_transactions table."""
    _create_characters_table(db_session)
    _create_gold_transactions_table(db_session)
    yield db_session


# ═══════════════════════════════════════════════════════════════════════════
# Tests: log_gold_transaction helper
# ═══════════════════════════════════════════════════════════════════════════


class TestLogGoldTransactionHelper:
    """Tests for inventory-service's log_gold_transaction() (raw SQL version)."""

    def test_correct_fields_stored(self, gold_env):
        """All fields are persisted correctly via raw SQL INSERT."""
        db = gold_env
        _insert_character(db, 1, user_id=1, gold=500)

        crud.log_gold_transaction(
            db, 1,
            amount=-100,
            balance_after=400,
            transaction_type="test_type",
            source="test_source",
            metadata={"trade_id": 42},
        )
        db.commit()

        txs = _get_gold_transactions(db, 1, "test_type")
        assert len(txs) == 1
        tx = txs[0]
        assert tx[1] == 1            # character_id
        assert tx[2] == -100         # amount
        assert tx[3] == 400          # balance_after
        assert tx[4] == "test_type"
        assert tx[5] == "test_source"
        meta = json.loads(tx[6])
        assert meta["trade_id"] == 42

    def test_none_metadata_stored_as_none(self, gold_env):
        """When metadata is None, the metadata column is None."""
        db = gold_env
        _insert_character(db, 1, user_id=1, gold=100)

        crud.log_gold_transaction(
            db, 1,
            amount=10,
            balance_after=110,
            transaction_type="minimal",
            source=None,
            metadata=None,
        )
        db.commit()

        txs = _get_gold_transactions(db, 1, "minimal")
        assert len(txs) == 1
        assert txs[0][5] is None  # source
        assert txs[0][6] is None  # metadata

    def test_exception_does_not_propagate(self, gold_env):
        """log_gold_transaction catches exceptions (table missing scenario)."""
        db = gold_env
        # Drop the table to simulate failure
        db.execute(text("DROP TABLE gold_transactions"))
        db.commit()

        # Should NOT raise — exception is caught internally
        crud.log_gold_transaction(
            db, 1,
            amount=100,
            balance_after=100,
            transaction_type="should_fail",
        )
        # Re-create the table for cleanup
        _create_gold_transactions_table(db)


# ═══════════════════════════════════════════════════════════════════════════
# Tests: Trade gold creates transactions
# ═══════════════════════════════════════════════════════════════════════════


class TestTradeGoldTransactions:
    """Tests that trade gold transfers create gold_transaction records."""

    def _setup_trade(self, db, initiator_gold=100, target_gold=0):
        """Create two characters with a trade offer."""
        _insert_character(db, 1, user_id=1, name="Alice", location=1, gold=500)
        _insert_character(db, 2, user_id=2, name="Bob", location=1, gold=300)

        _create_item(db, 101, "TestItem", max_stack=10)
        inv = _add_inventory(db, 1, 101, 5)

        trade = models.TradeOffer(
            initiator_character_id=1,
            target_character_id=2,
            location_id=1,
            initiator_gold=initiator_gold,
            target_gold=target_gold,
            initiator_confirmed=True,
            target_confirmed=True,
            status='negotiating',
        )
        db.add(trade)
        db.flush()

        # Add trade item from initiator
        trade_item = models.TradeOfferItem(
            trade_offer_id=trade.id,
            character_id=1,
            item_id=101,
            quantity=1,
        )
        db.add(trade_item)
        db.commit()
        return trade

    def test_initiator_gold_creates_transactions(self, gold_env):
        """Trade with initiator_gold creates transactions for both parties."""
        db = gold_env
        trade = self._setup_trade(db, initiator_gold=100, target_gold=0)

        crud.execute_trade(db, trade)
        db.commit()

        # Initiator should have a negative transaction (spent gold)
        initiator_txs = _get_gold_transactions(db, 1, "trade")
        neg_txs = [tx for tx in initiator_txs if tx[2] < 0]
        assert len(neg_txs) == 1
        assert neg_txs[0][2] == -100

        # Receiver should have a positive transaction (received gold)
        receiver_txs = _get_gold_transactions(db, 2, "trade")
        pos_txs = [tx for tx in receiver_txs if tx[2] > 0]
        assert len(pos_txs) == 1
        assert pos_txs[0][2] == 100

    def test_target_gold_creates_transactions(self, gold_env):
        """Trade with target_gold creates transactions for both parties."""
        db = gold_env
        trade = self._setup_trade(db, initiator_gold=0, target_gold=50)

        crud.execute_trade(db, trade)
        db.commit()

        # Target pays gold
        target_txs = _get_gold_transactions(db, 2, "trade")
        neg_txs = [tx for tx in target_txs if tx[2] < 0]
        assert len(neg_txs) == 1
        assert neg_txs[0][2] == -50

        # Initiator receives gold
        initiator_txs = _get_gold_transactions(db, 1, "trade")
        pos_txs = [tx for tx in initiator_txs if tx[2] > 0]
        assert len(pos_txs) == 1
        assert pos_txs[0][2] == 50

    def test_zero_gold_trade_no_transactions(self, gold_env):
        """Trade with no gold transfer creates no gold_transactions."""
        db = gold_env
        trade = self._setup_trade(db, initiator_gold=0, target_gold=0)

        crud.execute_trade(db, trade)
        db.commit()

        total = _count_gold_transactions(db)
        assert total == 0


# ═══════════════════════════════════════════════════════════════════════════
# Tests: Auction operations create transactions
# ═══════════════════════════════════════════════════════════════════════════


class TestAuctionGoldTransactions:
    """Tests that auction operations create gold_transaction records."""

    def _setup_auction(self, db):
        """Create characters, NPC auctioneer, item."""
        _insert_character(db, 1, user_id=1, name="Seller", location=1, gold=5000)
        _insert_character(db, 2, user_id=2, name="Bidder1", location=1, gold=3000)
        _insert_character(db, 3, user_id=3, name="Bidder2", location=1, gold=4000)
        _insert_npc_auctioneer(db, 100, location=1)
        _create_item(db, 201, "Sword", max_stack=1, item_type="main_weapon")
        db.commit()

    def test_bid_creates_auction_buy_transaction(self, gold_env):
        """Placing a bid deducts gold and creates an auction_buy transaction."""
        db = gold_env
        self._setup_auction(db)

        listing = _create_listing(db, seller_id=1, item_id=201,
                                  start_price=100, buyout_price=1000)
        db.commit()

        bid_data = schemas.AuctionBidRequest(character_id=2, amount=200)
        crud.place_bid(db, listing.id, bid_data, user_id=2)
        db.commit()

        txs = _get_gold_transactions(db, 2, "auction_buy")
        assert len(txs) == 1
        assert txs[0][2] == -200  # negative (spent)

    def test_outbid_creates_refund_transaction(self, gold_env):
        """When outbid, the previous bidder gets an auction_refund transaction."""
        db = gold_env
        self._setup_auction(db)

        listing = _create_listing(db, seller_id=1, item_id=201,
                                  start_price=100, buyout_price=1000)
        db.commit()

        # First bid
        bid1 = schemas.AuctionBidRequest(character_id=2, amount=200)
        crud.place_bid(db, listing.id, bid1, user_id=2)
        db.commit()

        # Second bid outbids the first
        bid2 = schemas.AuctionBidRequest(character_id=3, amount=300)
        crud.place_bid(db, listing.id, bid2, user_id=3)
        db.commit()

        # Bidder2 should have an auction_refund transaction
        refund_txs = _get_gold_transactions(db, 2, "auction_refund")
        assert len(refund_txs) == 1
        assert refund_txs[0][2] == 200  # positive (refund)

    def test_buyout_creates_auction_buy_transaction(self, gold_env):
        """Buyout creates an auction_buy transaction for the buyer."""
        db = gold_env
        self._setup_auction(db)

        listing = _create_listing(db, seller_id=1, item_id=201,
                                  start_price=100, buyout_price=500)
        db.commit()

        buyout_data = schemas.AuctionBuyoutRequest(character_id=2)
        crud.execute_buyout(db, listing.id, buyout_data, user_id=2)
        db.commit()

        txs = _get_gold_transactions(db, 2, "auction_buy")
        assert len(txs) == 1
        assert txs[0][2] == -500  # negative (buyout price)

    def test_claim_gold_creates_auction_sell_transaction(self, gold_env):
        """Claiming gold from storage creates an auction_sell transaction."""
        db = gold_env
        self._setup_auction(db)

        # Create a storage entry with gold (simulating sold item proceeds)
        storage = models.AuctionStorage(
            character_id=1,
            item_id=None,
            quantity=0,
            gold_amount=450,
            source='sale',
            listing_id=None,
        )
        db.add(storage)
        db.commit()

        claim_data = schemas.AuctionClaimRequest(
            character_id=1,
            storage_ids=[storage.id],
        )
        crud.claim_from_storage(db, claim_data, user_id=1)
        db.commit()

        txs = _get_gold_transactions(db, 1, "auction_sell")
        assert len(txs) == 1
        assert txs[0][2] == 450  # positive (sell income)

    def test_buyout_with_prior_bid_creates_refund(self, gold_env):
        """Buyout when there is an active bidder creates refund for the bidder."""
        db = gold_env
        self._setup_auction(db)

        listing = _create_listing(db, seller_id=1, item_id=201,
                                  start_price=100, buyout_price=500)
        db.commit()

        # Bidder2 bids
        bid_data = schemas.AuctionBidRequest(character_id=2, amount=200)
        crud.place_bid(db, listing.id, bid_data, user_id=2)
        db.commit()

        # Bidder3 buyouts — bidder2 should be refunded
        buyout_data = schemas.AuctionBuyoutRequest(character_id=3)
        crud.execute_buyout(db, listing.id, buyout_data, user_id=3)
        db.commit()

        # Bidder2 gets refund
        refund_txs = _get_gold_transactions(db, 2, "auction_refund")
        assert len(refund_txs) == 1
        assert refund_txs[0][2] == 200

        # Bidder3 has auction_buy
        buy_txs = _get_gold_transactions(db, 3, "auction_buy")
        assert len(buy_txs) == 1
        assert buy_txs[0][2] == -500
