"""
FEAT-181 (was FEAT-102 «gold_transactions»): every gold change of trades and the
auction is ONE double-entry operation in the world economy ledger
(econ_operations + econ_postings), not single-entry gold_transactions rows.

1. Trade gold — one `trade` operation, player -> player legs, no other accounts
2. Bid — bidder -> auction escrow; outbid refund — escrow -> previous bidder
3. Buyout — buyer -> escrow, escrow -> storage 95 %, escrow -> treasury 5 % (+ tax leg)
4. Lazy expiry with a winner — `auction_settlement`
5. Cancel — escrow -> bidder; claim — storage -> seller
6. After every scenario: world sum is 0, escrow / storage accounts equal the
   auction tables, gold_transactions is no longer written
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import text

import crud
import econ_ledger
import models
import schemas
from econ_ledger import AccountRef, Leg


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
            character_id INTEGER NOT NULL,
            dropped_out_at DATETIME
        )"""
    ))
    db.commit()


def _emit(db, ref, amount):
    """Fund an account from `emission` (how genesis / the admin put money into the world)."""
    econ_ledger.post_operation(
        db, op_type="admin_emission", legs=[Leg(AccountRef.emission(), ref, amount)],
        source_service="test", comment="test seed", apply_tax=False,
    )
    db.commit()


def _insert_character(db, char_id, user_id, name="TestChar", location=1, gold=0):
    """Characters are created with 0 and funded through the ledger, so the world sum is 0."""
    db.execute(text(
        "INSERT OR IGNORE INTO characters "
        "(id, name, user_id, current_location_id, currency_balance, is_npc, npc_role, npc_status, is_alive) "
        "VALUES (:cid, :name, :uid, :loc, 0, 0, NULL, 'alive', 1)"
    ), {"cid": char_id, "name": name, "uid": user_id, "loc": location})
    db.commit()
    if gold:
        _emit(db, AccountRef.character(char_id), gold)


def _insert_npc_auctioneer(db, npc_id, location):
    db.execute(text(
        "INSERT OR IGNORE INTO characters "
        "(id, name, user_id, current_location_id, currency_balance, is_npc, npc_role, npc_status, is_alive) "
        "VALUES (:cid, 'Аукционист', 0, :loc, 0, 1, 'auctioneer', 'alive', 1)"
    ), {"cid": npc_id, "loc": location})
    db.commit()


def _create_item(db, item_id, name, max_stack=10, item_type="resource", rarity="common"):
    item = models.Items(
        id=item_id, name=name, item_level=1, item_type=item_type, item_rarity=rarity,
        max_stack_size=max_stack, is_unique=False,
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
                    buyout_price=500, status='active', region_id=None):
    now = datetime.utcnow()
    listing = models.AuctionListing(
        seller_character_id=seller_id, item_id=item_id, quantity=quantity,
        start_price=start_price, buyout_price=buyout_price, current_bid=0, current_bidder_id=None,
        status=status, created_at=now, expires_at=now + timedelta(hours=24), region_id=region_id,
    )
    db.add(listing)
    db.flush()
    return listing


def _balance(db, cid):
    return db.execute(text("SELECT currency_balance FROM characters WHERE id = :id"), {"id": cid}).scalar()


def _account(db, ref):
    value = db.execute(
        text("SELECT balance FROM econ_accounts WHERE kind = :k AND ref_id = :r"),
        {"k": ref.kind, "r": ref.ref_id},
    ).scalar()
    return int(value or 0)


def _legs(db, op_type):
    """Legs of all operations of op_type: (from_kind, from_ref, to_kind, to_ref, amount, leg_type)."""
    rows = db.execute(text(
        "SELECT fa.kind, fa.ref_id, ta.kind, ta.ref_id, p.amount, p.leg_type "
        "FROM econ_postings p "
        "JOIN econ_operations o ON o.id = p.operation_id "
        "JOIN econ_accounts fa ON fa.id = p.from_account_id "
        "JOIN econ_accounts ta ON ta.id = p.to_account_id "
        "WHERE o.op_type = :t ORDER BY p.id"
    ), {"t": op_type}).fetchall()
    return [tuple(r) for r in rows]


def _op_count(db, op_type):
    return db.execute(text("SELECT COUNT(*) FROM econ_operations WHERE op_type = :t"), {"t": op_type}).scalar()


def _assert_invariants(db):
    """World sum 0; escrow / storage accounts match the auction tables (3.2 sub-invariants)."""
    world = db.execute(text(
        "SELECT (SELECT COALESCE(SUM(currency_balance), 0) FROM characters) + "
        "(SELECT COALESCE(SUM(balance), 0) FROM econ_accounts WHERE kind <> 'character')"
    )).scalar()
    assert world == 0
    escrow_sum = db.execute(text(
        "SELECT COALESCE(SUM(current_bid), 0) FROM auction_listings "
        "WHERE status = 'active' AND current_bidder_id IS NOT NULL"
    )).scalar()
    assert _account(db, AccountRef.escrow()) == escrow_sum
    storage_sum = db.execute(text("SELECT COALESCE(SUM(gold_amount), 0) FROM auction_storage")).scalar()
    assert _account(db, AccountRef.storage()) == storage_sum


def _seed_world(db):
    """Country 1 <- region 10 <- location 1 (the auctioneer's location)."""
    db.execute(text("INSERT INTO Countries (id, name) VALUES (1, 'Country')"))
    db.execute(text("INSERT INTO Regions (id, name, country_id) VALUES (10, 'Region', 1)"))
    db.execute(text("INSERT INTO Locations (id, name, district_id, region_id, parent_id) "
                    "VALUES (1, 'Town', NULL, 10, NULL)"))
    db.commit()


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def gold_env(db_session):
    """characters table + seeded world hierarchy; ledger tables come from conftest.
    The world invariant is asserted after every test."""
    _create_characters_table(db_session)
    _seed_world(db_session)
    with patch("crud.publish_auction_notification"):
        yield db_session
    db_session.rollback()
    _assert_invariants(db_session)


# ═══════════════════════════════════════════════════════════════════════════
# Trade
# ═══════════════════════════════════════════════════════════════════════════


class TestTradeLedger:

    def _setup_trade(self, db, initiator_gold=100, target_gold=0):
        _insert_character(db, 1, user_id=1, name="Alice", location=1, gold=500)
        _insert_character(db, 2, user_id=2, name="Bob", location=1, gold=300)
        _create_item(db, 101, "TestItem", max_stack=10)
        _add_inventory(db, 1, 101, 5)
        trade = models.TradeOffer(
            initiator_character_id=1, target_character_id=2, location_id=1,
            initiator_gold=initiator_gold, target_gold=target_gold,
            initiator_confirmed=True, target_confirmed=True, status='negotiating',
        )
        db.add(trade)
        db.flush()
        db.add(models.TradeOfferItem(trade_offer_id=trade.id, character_id=1, item_id=101, quantity=1))
        db.commit()
        return trade

    def test_initiator_gold_is_one_trade_operation(self, gold_env):
        db = gold_env
        trade = self._setup_trade(db, initiator_gold=100, target_gold=0)
        crud.execute_trade(db, trade)
        db.commit()

        assert _op_count(db, "trade") == 1
        assert _legs(db, "trade") == [("character", 1, "character", 2, 100, "main")]
        assert _balance(db, 1) == 400
        assert _balance(db, 2) == 400
        assert trade.status == "completed"

    def test_both_sides_gold_single_operation_two_legs(self, gold_env):
        db = gold_env
        trade = self._setup_trade(db, initiator_gold=100, target_gold=50)
        crud.execute_trade(db, trade)
        db.commit()

        assert _op_count(db, "trade") == 1
        assert sorted(_legs(db, "trade")) == sorted([
            ("character", 1, "character", 2, 100, "main"),
            ("character", 2, "character", 1, 50, "main"),
        ])
        assert _balance(db, 1) == 450
        assert _balance(db, 2) == 350

    def test_zero_gold_trade_no_operation(self, gold_env):
        db = gold_env
        trade = self._setup_trade(db, initiator_gold=0, target_gold=0)
        crud.execute_trade(db, trade)
        db.commit()
        assert _op_count(db, "trade") == 0
        assert trade.status == "completed"

    def test_insufficient_funds_rejected_nothing_moves(self, gold_env):
        db = gold_env
        trade = self._setup_trade(db, initiator_gold=600, target_gold=0)
        with pytest.raises(ValueError, match="недостаточно марок"):
            crud.execute_trade(db, trade)
        db.rollback()
        assert _balance(db, 1) == 500
        assert _balance(db, 2) == 300
        assert _op_count(db, "trade") == 0

    def test_already_completed_trade_never_executes_again(self, gold_env):
        """Status check-and-set: a request holding a stale copy of the trade cannot re-run it."""
        db = gold_env
        trade = self._setup_trade(db, initiator_gold=100, target_gold=0)
        crud.execute_trade(db, trade)
        db.commit()

        stale = models.TradeOffer(id=trade.id)  # stand-in for a concurrent request's object
        stale.initiator_character_id, stale.target_character_id = 1, 2
        stale.initiator_gold, stale.target_gold, stale.location_id = 100, 0, 1
        db.expunge(trade)
        with pytest.raises(ValueError, match="уже завершён"):
            crud.execute_trade(db, stale)
        db.rollback()
        assert _balance(db, 1) == 400
        assert _op_count(db, "trade") == 1


# ═══════════════════════════════════════════════════════════════════════════
# Auction
# ═══════════════════════════════════════════════════════════════════════════


class TestAuctionLedger:

    def _setup_auction(self, db):
        _insert_character(db, 1, user_id=1, name="Seller", location=1, gold=5000)
        _insert_character(db, 2, user_id=2, name="Bidder1", location=1, gold=3000)
        _insert_character(db, 3, user_id=3, name="Bidder2", location=1, gold=4000)
        _insert_npc_auctioneer(db, 100, location=1)
        _create_item(db, 201, "Sword", max_stack=1, item_type="weapon")
        db.commit()

    def test_bid_moves_gold_into_escrow(self, gold_env):
        db = gold_env
        self._setup_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=1000)
        db.commit()

        crud.place_bid(db, listing.id, schemas.AuctionBidRequest(character_id=2, amount=200), user_id=2)
        db.commit()

        assert _legs(db, "auction_bid") == [("character", 2, "auction_escrow", 0, 200, "main")]
        assert _balance(db, 2) == 2800
        assert _account(db, AccountRef.escrow()) == 200
        _assert_invariants(db)

    def test_outbid_refund_is_a_leg_of_the_new_bid(self, gold_env):
        db = gold_env
        self._setup_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=1000)
        db.commit()

        crud.place_bid(db, listing.id, schemas.AuctionBidRequest(character_id=2, amount=200), user_id=2)
        db.commit()
        crud.place_bid(db, listing.id, schemas.AuctionBidRequest(character_id=3, amount=300), user_id=3)
        db.commit()

        assert _op_count(db, "auction_bid") == 2
        assert ("auction_escrow", 0, "character", 2, 200, "refund") in _legs(db, "auction_bid")
        assert _balance(db, 2) == 3000
        assert _balance(db, 3) == 3700
        assert _account(db, AccountRef.escrow()) == 300
        _assert_invariants(db)

    def test_bid_without_funds_rejected(self, gold_env):
        db = gold_env
        self._setup_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=10000)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            crud.place_bid(db, listing.id, schemas.AuctionBidRequest(character_id=2, amount=3500), user_id=2)
        assert exc.value.status_code == 400
        assert exc.value.detail == "Недостаточно марок"
        assert _balance(db, 2) == 3000
        assert _op_count(db, "auction_bid") == 0

    def test_buyout_with_prior_bid_commission_to_region_with_tax(self, gold_env):
        db = gold_env
        self._setup_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100,
                                  buyout_price=500, region_id=10)
        db.commit()

        crud.place_bid(db, listing.id, schemas.AuctionBidRequest(character_id=2, amount=200), user_id=2)
        db.commit()
        crud.execute_buyout(db, listing.id, schemas.AuctionBuyoutRequest(character_id=3), user_id=3)
        db.commit()

        legs = _legs(db, "auction_buyout")
        assert ("character", 3, "auction_escrow", 0, 500, "main") in legs
        assert ("auction_escrow", 0, "character", 2, 200, "refund") in legs
        assert ("auction_escrow", 0, "auction_storage", 0, 475, "main") in legs
        assert ("auction_escrow", 0, "region_treasury", 10, 25, "commission") in legs
        assert ("region_treasury", 10, "country_treasury", 1, 2, "tax") in legs
        assert _balance(db, 2) == 3000
        assert _balance(db, 3) == 3500
        assert _account(db, AccountRef.escrow()) == 0
        assert _account(db, AccountRef.storage()) == 475
        assert _account(db, AccountRef.region(10)) == 23
        assert _account(db, AccountRef.country(1)) == 2
        _assert_invariants(db)

    def test_legacy_listing_commission_goes_to_world_treasury(self, gold_env):
        db = gold_env
        self._setup_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=500)
        db.commit()

        crud.execute_buyout(db, listing.id, schemas.AuctionBuyoutRequest(character_id=2), user_id=2)
        db.commit()

        legs = _legs(db, "auction_buyout")
        assert ("auction_escrow", 0, "world_treasury", 0, 25, "commission") in legs
        assert not [leg for leg in legs if leg[5] == "tax"]
        assert _account(db, AccountRef.world()) == 25
        _assert_invariants(db)

    def test_listing_creation_records_location_and_region(self, gold_env):
        db = gold_env
        self._setup_auction(db)
        storage = models.AuctionStorage(character_id=1, item_id=201, quantity=1, gold_amount=0, source='deposit')
        db.add(storage)
        db.commit()

        result = crud.create_auction_listing(
            db,
            schemas.AuctionCreateListingRequest(character_id=1, storage_id=storage.id,
                                                start_price=100, buyout_price=500),
            user_id=1,
        )
        listing = db.query(models.AuctionListing).get(result["listing_id"])
        assert listing.location_id == 1
        assert listing.region_id == 10

    def test_expiry_with_winner_settles_from_escrow(self, gold_env):
        db = gold_env
        self._setup_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100,
                                  buyout_price=1000, region_id=10)
        db.commit()
        crud.place_bid(db, listing.id, schemas.AuctionBidRequest(character_id=2, amount=200), user_id=2)
        db.commit()
        listing.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()

        assert crud.expire_stale_listings(db) == 1

        legs = _legs(db, "auction_settlement")
        assert ("auction_escrow", 0, "auction_storage", 0, 190, "main") in legs
        assert ("auction_escrow", 0, "region_treasury", 10, 10, "commission") in legs
        assert ("region_treasury", 10, "country_treasury", 1, 1, "tax") in legs
        assert _account(db, AccountRef.escrow()) == 0
        assert _account(db, AccountRef.storage()) == 190
        _assert_invariants(db)

    def test_cancel_refunds_bidder_from_escrow(self, gold_env):
        db = gold_env
        self._setup_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=1000)
        db.commit()
        crud.place_bid(db, listing.id, schemas.AuctionBidRequest(character_id=2, amount=200), user_id=2)
        db.commit()

        crud.cancel_listing(db, listing.id, schemas.AuctionCancelRequest(character_id=1), user_id=1)

        assert _legs(db, "auction_refund") == [("auction_escrow", 0, "character", 2, 200, "refund")]
        assert _balance(db, 2) == 3000
        assert _account(db, AccountRef.escrow()) == 0
        _assert_invariants(db)

    def test_claim_moves_proceeds_from_storage(self, gold_env):
        db = gold_env
        self._setup_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=500)
        db.commit()
        crud.execute_buyout(db, listing.id, schemas.AuctionBuyoutRequest(character_id=2), user_id=2)
        db.commit()
        proceeds = db.query(models.AuctionStorage).filter(
            models.AuctionStorage.character_id == 1, models.AuctionStorage.source == 'sale_proceeds',
        ).one()

        result = crud.claim_from_storage(
            db, schemas.AuctionClaimRequest(character_id=1, storage_ids=[proceeds.id]), user_id=1,
        )

        assert result["claimed_gold"] == 475
        assert _legs(db, "auction_claim") == [("auction_storage", 0, "character", 1, 475, "main")]
        assert _balance(db, 1) == 5475
        assert _account(db, AccountRef.storage()) == 0
        _assert_invariants(db)


def test_gold_transactions_no_longer_written():
    """FEAT-181 froze the single-entry table: inventory's local logging helper is gone."""
    assert not hasattr(crud, "log_gold_transaction")
