"""FEAT-181 Q2: inventory-service money flows over the world-economy ledger.

Extends test_gold_transactions.py (B4) with:
  * trade through the HTTP endpoints: full flow, double confirm executes once, funds that vanished
    between offer and confirm, negative / huge gold, ownership and participant checks;
  * auction: bid chains, raising one's own bid, buyout by the top bidder, unaffordable buyout,
    double buyout, commission rounding, tax rate from econ_settings, region resolution at listing
    creation (district / parent / orphan -> world), expiry without bids, double claim, foreign
    storage ids, cancel edge cases, a long multi-listing scenario;
  * security: 401 without a token, 403 for foreign characters, negative and huge amounts.

After EVERY scenario (fixture teardown, plus explicit checks between steps):
  Σ characters.currency_balance + Σ econ_accounts.balance (non-character) = 0,
  auction_escrow = Σ active current_bid, auction_storage = Σ auction_storage.gold_amount,
  no character balance is negative.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import text

import crud
import econ_core
import econ_ledger
import models
import schemas
from auth_http import UserRead, get_current_user_via_http
from econ_ledger import AccountRef, Leg
from main import app
from tests.test_gold_transactions import (
    _account,
    _add_inventory,
    _assert_invariants,
    _balance,
    _create_characters_table,
    _create_item,
    _create_listing,
    _emit,
    _insert_character,
    _insert_npc_auctioneer,
    _legs,
    _op_count,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check(db):
    """Full invariant set (B4's sub-invariants + no negative player balances)."""
    _assert_invariants(db)
    negative = db.execute(text("SELECT COUNT(*) FROM characters WHERE currency_balance < 0")).scalar()
    assert negative == 0


def _seed_world(db):
    """country 1 <- region 10 <- location 1 (Locations.region_id)
       country 2 <- region 20 <- district 200 <- location 2 <- location 3 (child, no own region)
       location 4: orphan (no region anywhere) -> world treasury."""
    db.execute(text("INSERT INTO Countries (id, name) VALUES (1, 'Country A'), (2, 'Country B')"))
    db.execute(text("INSERT INTO Regions (id, name, country_id) VALUES (10, 'Region A', 1), (20, 'Region B', 2)"))
    db.execute(text("INSERT INTO Districts (id, name, region_id) VALUES (200, 'District B', 20)"))
    db.execute(text(
        "INSERT INTO Locations (id, name, district_id, region_id, parent_id) VALUES "
        "(1, 'Town', NULL, 10, NULL), (2, 'Port', 200, NULL, NULL), "
        "(3, 'Port market', NULL, NULL, 2), (4, 'Wilds', NULL, NULL, NULL)"
    ))
    db.commit()


def _as_user(user_id):
    app.dependency_overrides[get_current_user_via_http] = lambda: UserRead(
        id=user_id, username=f"u{user_id}", role="user", permissions=[],
    )


def _seed_auction(db, location=1):
    """Seller 1 (5000), bidders 2 (3000) and 3 (4000), auctioneer NPC at `location`."""
    _insert_character(db, 1, user_id=1, name="Seller", location=location, gold=5000)
    _insert_character(db, 2, user_id=2, name="Bidder1", location=location, gold=3000)
    _insert_character(db, 3, user_id=3, name="Bidder2", location=location, gold=4000)
    _insert_npc_auctioneer(db, 100, location=location)
    _create_item(db, 201, "Sword", max_stack=1, item_type="weapon")
    db.commit()


def _bid(db, listing_id, cid, amount):
    # construct() skips the schema price cap so the crud/ledger guards are exercised directly
    result = crud.place_bid(db, listing_id, schemas.AuctionBidRequest.construct(character_id=cid, amount=amount), user_id=cid)
    db.commit()
    return result


def _buyout(db, listing_id, cid):
    result = crud.execute_buyout(db, listing_id, schemas.AuctionBuyoutRequest(character_id=cid), user_id=cid)
    db.commit()
    return result


def _expire(db, listing):
    listing.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    return crud.expire_stale_listings(db)


def _storage_ids(db, cid, source=None):
    q = db.query(models.AuctionStorage).filter(models.AuctionStorage.character_id == cid)
    if source:
        q = q.filter(models.AuctionStorage.source == source)
    return [s.id for s in q.order_by(models.AuctionStorage.id).all()]


def _claim(db, cid, ids):
    return crud.claim_from_storage(db, schemas.AuctionClaimRequest(character_id=cid, storage_ids=ids), user_id=cid)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def env(db_session):
    """characters table + world hierarchy; notifications / stats calls mocked.
    The invariant set is asserted after every test."""
    econ_core.invalidate_settings_cache()
    _create_characters_table(db_session)
    _seed_world(db_session)
    with patch("crud.publish_auction_notification"), \
            patch("main.publish_notification_sync"), \
            patch("main._track_cumulative_stats"):
        yield db_session
    db_session.rollback()
    _check(db_session)
    econ_core.invalidate_settings_cache()


@pytest.fixture()
def api(env, client):
    """TestClient on the same session; auth override is cleared by `client`."""
    yield client
    app.dependency_overrides.pop(get_current_user_via_http, None)


# ═══════════════════════════════════════════════════════════════════════════
# Trade through the HTTP endpoints
# ═══════════════════════════════════════════════════════════════════════════


class TestTradeEndpoints:

    def _setup(self, db):
        _insert_character(db, 1, user_id=1, name="Alice", location=1, gold=500)
        _insert_character(db, 2, user_id=2, name="Bob", location=1, gold=300)
        _insert_character(db, 3, user_id=3, name="Eve", location=1, gold=50)
        _create_item(db, 101, "Herb", max_stack=99)
        _add_inventory(db, 1, 101, 10)
        db.commit()

    def _open_trade(self, api, alice_gold=100, bob_gold=40, herbs=2):
        _as_user(1)
        r = api.post("/inventory/trade/propose", json={"initiator_character_id": 1, "target_character_id": 2})
        assert r.status_code == 201, r.text
        trade_id = r.json()["trade_id"]
        items = [{"item_id": 101, "quantity": herbs}] if herbs else []
        r = api.put(f"/inventory/trade/{trade_id}/items",
                    json={"character_id": 1, "items": items, "gold": alice_gold})
        assert r.status_code == 200, r.text
        _as_user(2)
        r = api.put(f"/inventory/trade/{trade_id}/items", json={"character_id": 2, "items": [], "gold": bob_gold})
        assert r.status_code == 200, r.text
        return trade_id

    def _confirm(self, api, trade_id, user_cid):
        _as_user(user_cid)
        return api.post(f"/inventory/trade/{trade_id}/confirm", json={"character_id": user_cid})

    def test_full_flow_one_trade_operation(self, api, env):
        db = env
        self._setup(db)
        trade_id = self._open_trade(api)

        r = self._confirm(api, trade_id, 1)
        assert r.status_code == 200 and r.json()["status"] != "completed"
        assert _op_count(db, "trade") == 0
        r = self._confirm(api, trade_id, 2)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "completed"

        assert _op_count(db, "trade") == 1
        assert sorted(_legs(db, "trade")) == sorted([
            ("character", 1, "character", 2, 100, "main"),
            ("character", 2, "character", 1, 40, "main"),
        ])
        assert _balance(db, 1) == 440
        assert _balance(db, 2) == 360
        op = db.execute(text(
            "SELECT idempotency_key, location_id, source_service FROM econ_operations WHERE op_type = 'trade'"
        )).first()
        assert tuple(op) == (f"trade:{trade_id}", 1, "inventory-service")
        herbs_bob = db.execute(text(
            "SELECT COALESCE(SUM(quantity), 0) FROM character_inventory WHERE character_id = 2 AND item_id = 101"
        )).scalar()
        assert herbs_bob == 2
        _check(db)

    def test_double_confirm_executes_once(self, api, env):
        db = env
        self._setup(db)
        trade_id = self._open_trade(api)
        self._confirm(api, trade_id, 1)
        assert self._confirm(api, trade_id, 2).status_code == 200

        # Both sides hit confirm again (double click / retry): nothing moves.
        for cid in (2, 1):
            r = self._confirm(api, trade_id, cid)
            assert r.status_code == 400
            assert "уже завершён" in r.json()["detail"]

        assert _op_count(db, "trade") == 1
        assert _balance(db, 1) == 440
        assert _balance(db, 2) == 360
        _check(db)

    def test_funds_spent_after_offer_reject_confirm_and_roll_back(self, api, env):
        """Alice offers 100, then spends down to 30 before Bob confirms: the trade fails
        under lock, nothing moves (no items, no gold), the trade stays open."""
        db = env
        self._setup(db)
        trade_id = self._open_trade(api, alice_gold=100, bob_gold=0)
        econ_ledger.post_operation(db, op_type="teleport", legs=[Leg(AccountRef.character(1), AccountRef.region(10), 470)],
                                   source_service="test", location_id=1)
        db.commit()
        assert _balance(db, 1) == 30

        self._confirm(api, trade_id, 1)
        r = self._confirm(api, trade_id, 2)
        assert r.status_code == 400
        assert "недостаточно золота" in r.json()["detail"]

        assert _op_count(db, "trade") == 0
        assert _balance(db, 1) == 30
        assert _balance(db, 2) == 300
        herbs_alice = db.execute(text(
            "SELECT COALESCE(SUM(quantity), 0) FROM character_inventory WHERE character_id = 1 AND item_id = 101"
        )).scalar()
        assert herbs_alice == 10
        status = db.execute(text("SELECT status FROM trade_offers WHERE id = :t"), {"t": trade_id}).scalar()
        assert status in ("pending", "negotiating")
        _check(db)

    def test_target_side_insufficient_funds_also_rejected(self, env):
        db = env
        self._setup(db)
        trade = models.TradeOffer(initiator_character_id=1, target_character_id=3, location_id=1,
                                  initiator_gold=0, target_gold=51, initiator_confirmed=True,
                                  target_confirmed=True, status="negotiating")
        db.add(trade)
        db.commit()
        with pytest.raises(ValueError, match="второго участника"):
            crud.execute_trade(db, trade)
        db.rollback()
        assert _balance(db, 3) == 50
        assert _op_count(db, "trade") == 0

    def test_whole_balance_both_ways_never_negative(self, env):
        """Each side gives exactly what it has; netting keeps both balances >= 0 throughout."""
        db = env
        self._setup(db)
        trade = models.TradeOffer(initiator_character_id=1, target_character_id=2, location_id=1,
                                  initiator_gold=500, target_gold=300, initiator_confirmed=True,
                                  target_confirmed=True, status="negotiating")
        db.add(trade)
        db.commit()
        crud.execute_trade(db, trade)
        db.commit()
        assert _balance(db, 1) == 300
        assert _balance(db, 2) == 500
        _check(db)

    @pytest.mark.parametrize("gold,fragment", [
        (-1, "не может быть отрицательным"),
        (-10 ** 12, "не может быть отрицательным"),
        (10 ** 18, "Недостаточно золота"),
        (501, "Недостаточно золота"),
    ])
    def test_negative_and_huge_gold_offers_rejected(self, api, env, gold, fragment):
        db = env
        self._setup(db)
        _as_user(1)
        trade_id = api.post("/inventory/trade/propose",
                            json={"initiator_character_id": 1, "target_character_id": 2}).json()["trade_id"]
        r = api.put(f"/inventory/trade/{trade_id}/items", json={"character_id": 1, "items": [], "gold": gold})
        assert r.status_code == 400
        assert fragment in r.json()["detail"]
        stored = db.execute(text("SELECT initiator_gold FROM trade_offers WHERE id = :t"), {"t": trade_id}).scalar()
        assert (stored or 0) == 0
        assert _balance(db, 1) == 500

    def test_outsider_cannot_confirm_or_change_gold(self, api, env):
        db = env
        self._setup(db)
        trade_id = self._open_trade(api)

        _as_user(3)  # Eve owns character 3, not a participant
        assert api.post(f"/inventory/trade/{trade_id}/confirm", json={"character_id": 3}).status_code == 403
        assert api.put(f"/inventory/trade/{trade_id}/items",
                       json={"character_id": 3, "items": [], "gold": 1}).status_code == 403
        # Eve tries to act as Alice's character
        assert api.post(f"/inventory/trade/{trade_id}/confirm", json={"character_id": 1}).status_code == 403
        assert api.put(f"/inventory/trade/{trade_id}/items",
                       json={"character_id": 1, "items": [], "gold": 0}).status_code == 403
        assert _op_count(db, "trade") == 0
        _check(db)

    def test_no_token_401(self, api, env):
        self._setup(env)
        app.dependency_overrides.pop(get_current_user_via_http, None)
        assert api.post("/inventory/trade/1/confirm", json={"character_id": 1}).status_code == 401
        assert api.put("/inventory/trade/1/items", json={"character_id": 1, "gold": 5}).status_code == 401
        assert _op_count(env, "trade") == 0


# ═══════════════════════════════════════════════════════════════════════════
# Auction: bids
# ═══════════════════════════════════════════════════════════════════════════


class TestAuctionBids:

    def test_bid_chain_refunds_each_previous_bidder(self, env):
        db = env
        _seed_auction(db)
        _insert_character(db, 4, user_id=4, name="Bidder3", location=1, gold=1000)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=5000, region_id=10)
        db.commit()

        _bid(db, listing.id, 2, 200)
        _check(db)
        _bid(db, listing.id, 3, 300)
        _check(db)
        _bid(db, listing.id, 4, 450)
        _check(db)

        assert _balance(db, 2) == 3000
        assert _balance(db, 3) == 4000
        assert _balance(db, 4) == 550
        assert _account(db, AccountRef.escrow()) == 450
        refunds = [leg for leg in _legs(db, "auction_bid") if leg[5] == "refund"]
        assert refunds == [("auction_escrow", 0, "character", 2, 200, "refund"),
                           ("auction_escrow", 0, "character", 3, 300, "refund")]
        # Bids are not income of a region: no tax legs, no treasury touched.
        assert not [leg for leg in _legs(db, "auction_bid") if leg[5] == "tax"]
        assert _account(db, AccountRef.region(10)) == 0
        statuses = [b.status for b in db.query(models.AuctionBid).order_by(models.AuctionBid.id).all()]
        assert statuses == ["outbid", "outbid", "active"]

    def test_raising_own_bid_charges_only_the_difference(self, env):
        db = env
        _seed_auction(db)
        _insert_character(db, 4, user_id=4, name="Tight", location=1, gold=250)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=5000)
        db.commit()

        _bid(db, listing.id, 4, 200)
        assert _balance(db, 4) == 50
        # 250 total: raising to 250 only needs +50 thanks to netting with the self-refund
        _bid(db, listing.id, 4, 250)
        assert _balance(db, 4) == 0
        assert _account(db, AccountRef.escrow()) == 250
        _check(db)

    def test_bid_rejected_without_funds_listing_untouched(self, env):
        db = env
        _seed_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=5000)
        db.commit()
        _bid(db, listing.id, 2, 200)

        with pytest.raises(HTTPException) as exc:
            _bid(db, listing.id, 3, 4001)
        assert exc.value.status_code == 400
        db.refresh(listing)
        assert listing.current_bidder_id == 2 and listing.current_bid == 200
        assert _balance(db, 2) == 2800
        assert _balance(db, 3) == 4000
        assert _account(db, AccountRef.escrow()) == 200
        _check(db)

    @pytest.mark.parametrize("amount", [0, -1, -10 ** 9, 99])
    def test_bid_below_start_or_negative_rejected(self, env, amount):
        db = env
        _seed_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=5000)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            _bid(db, listing.id, 2, amount)
        assert exc.value.status_code == 400
        assert _balance(db, 2) == 3000
        assert _op_count(db, "auction_bid") == 0

    def test_bid_on_expired_but_unprocessed_listing_rejected(self, env):
        db = env
        _seed_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=5000)
        listing.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            _bid(db, listing.id, 2, 200)
        assert exc.value.status_code == 400
        assert _op_count(db, "auction_bid") == 0

    def test_huge_bid_without_buyout_price_moves_nothing(self, env):
        """A bid above the ledger's MAX_AMOUNT never moves money and is a 400, not a 500."""
        db = env
        _seed_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=None)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            _bid(db, listing.id, 2, econ_core.MAX_AMOUNT + 1)
        assert exc.value.status_code == 400
        db.rollback()
        assert _balance(db, 2) == 3000
        assert _op_count(db, "auction_bid") == 0
        db.refresh(listing)
        assert listing.current_bid == 0

    def test_huge_bid_within_ledger_limit_is_insufficient_funds(self, env):
        db = env
        _seed_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=None)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            _bid(db, listing.id, 2, econ_core.MAX_AMOUNT)
        assert exc.value.status_code == 400
        assert exc.value.detail == "Недостаточно золота"
        assert _balance(db, 2) == 3000


# ═══════════════════════════════════════════════════════════════════════════
# Auction: buyout, commission, tax
# ═══════════════════════════════════════════════════════════════════════════


class TestAuctionBuyout:

    def test_top_bidder_buys_out_pays_only_the_difference(self, env):
        db = env
        _seed_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=1000, region_id=10)
        db.commit()
        _bid(db, listing.id, 2, 400)
        _buyout(db, listing.id, 2)

        assert _balance(db, 2) == 2000
        legs = _legs(db, "auction_buyout")
        assert ("character", 2, "auction_escrow", 0, 1000, "main") in legs
        assert ("auction_escrow", 0, "character", 2, 400, "refund") in legs
        assert ("auction_escrow", 0, "auction_storage", 0, 950, "main") in legs
        assert ("auction_escrow", 0, "region_treasury", 10, 50, "commission") in legs
        assert ("region_treasury", 10, "country_treasury", 1, 5, "tax") in legs
        assert _account(db, AccountRef.region(10)) == 45
        assert _account(db, AccountRef.country(1)) == 5
        assert _account(db, AccountRef.escrow()) == 0
        assert _account(db, AccountRef.storage()) == 950
        _check(db)

    def test_unaffordable_buyout_keeps_previous_bid_in_escrow(self, env):
        db = env
        _seed_auction(db)
        _insert_character(db, 4, user_id=4, name="Poor", location=1, gold=999)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=1000, region_id=10)
        db.commit()
        _bid(db, listing.id, 2, 300)

        with pytest.raises(HTTPException) as exc:
            _buyout(db, listing.id, 4)
        assert exc.value.status_code == 400
        assert exc.value.detail == "Недостаточно золота"

        db.refresh(listing)
        assert listing.status == "active" and listing.current_bidder_id == 2
        assert _balance(db, 4) == 999
        assert _balance(db, 2) == 2700
        assert _account(db, AccountRef.escrow()) == 300
        assert _account(db, AccountRef.region(10)) == 0
        assert _op_count(db, "auction_buyout") == 0
        assert db.query(models.AuctionStorage).count() == 0
        _check(db)

    def test_second_buyout_rejected_paid_once(self, env):
        db = env
        _seed_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=500, region_id=10)
        db.commit()
        _buyout(db, listing.id, 2)
        with pytest.raises(HTTPException) as exc:
            _buyout(db, listing.id, 3)
        assert exc.value.status_code == 400
        assert _op_count(db, "auction_buyout") == 1
        assert _balance(db, 2) == 2500
        assert _balance(db, 3) == 4000
        _check(db)

    def test_buyout_operation_is_idempotent_per_listing(self, env):
        """Even if the status check were bypassed, the ledger key `auction_buyout:listing:<id>`
        refuses a second posting for the same listing."""
        db = env
        _seed_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=500, region_id=10)
        db.commit()
        _buyout(db, listing.id, 2)
        with pytest.raises(econ_core.DuplicateOperation):
            crud._post_auction_settlement(db, listing, "auction_buyout",
                                          [Leg(AccountRef.character(3), AccountRef.escrow(), 500)], 500, {})
        db.rollback()
        assert _balance(db, 3) == 4000
        _check(db)

    @pytest.mark.parametrize("price,seller,commission,tax", [
        (2, 1, 1, 0),
        (19, 18, 1, 0),
        (20, 19, 1, 0),
        (199, 189, 10, 1),
        (1000, 950, 50, 5),
        (12345, 11727, 618, 61),
    ])
    def test_commission_and_tax_rounding(self, env, price, seller, commission, tax):
        db = env
        _seed_auction(db)
        _emit(db, AccountRef.character(2), 20000)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=1, buyout_price=price, region_id=10)
        db.commit()
        _buyout(db, listing.id, 2)

        assert crud.auction_commission_split(price) == (seller, commission)
        assert _account(db, AccountRef.storage()) == seller
        assert _account(db, AccountRef.region(10)) == commission - tax
        assert _account(db, AccountRef.country(1)) == tax
        tax_legs = [leg for leg in _legs(db, "auction_buyout") if leg[5] == "tax"]
        assert len(tax_legs) == (1 if tax else 0)
        _check(db)

    def test_country_tax_rate_read_from_settings(self, env):
        db = env
        db.execute(text(
            "INSERT INTO econ_settings (id, currency_name, currency_genitive, currency_one, currency_few, "
            "currency_many, currency_short, country_tax_rate) "
            "VALUES (1, 'Серебро', 'серебра', 'серебряник', 'серебряника', 'серебряников', 'сер.', 0.2)"
        ))
        db.commit()
        econ_core.invalidate_settings_cache()
        _seed_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=1000, region_id=10)
        db.commit()
        _buyout(db, listing.id, 2)

        assert _account(db, AccountRef.region(10)) == 40
        assert _account(db, AccountRef.country(1)) == 10

        # The currency word in errors follows the settings too
        _insert_character(db, 4, user_id=4, name="Poor", location=1, gold=1)
        other = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=1000)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            _bid(db, other.id, 4, 200)
        assert exc.value.detail == "Недостаточно серебра"
        _check(db)

    def test_commission_of_second_region_taxed_to_its_country(self, env):
        db = env
        _seed_auction(db, location=2)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=600, region_id=20)
        db.commit()
        _buyout(db, listing.id, 3)
        assert _account(db, AccountRef.region(20)) == 27
        assert _account(db, AccountRef.country(2)) == 3
        assert _account(db, AccountRef.country(1)) == 0
        op = db.execute(text("SELECT region_id FROM econ_operations WHERE op_type = 'auction_buyout'")).scalar()
        assert op == 20
        _check(db)


# ═══════════════════════════════════════════════════════════════════════════
# Listing creation: location_id / region_id
# ═══════════════════════════════════════════════════════════════════════════


class TestListingRegion:

    @pytest.mark.parametrize("location,region", [(1, 10), (2, 20), (3, 20), (4, None)])
    def test_listing_records_location_and_resolved_region(self, env, location, region):
        db = env
        _seed_auction(db, location=location)
        storage = models.AuctionStorage(character_id=1, item_id=201, quantity=1, gold_amount=0, source="deposit")
        db.add(storage)
        db.commit()
        result = crud.create_auction_listing(
            db, schemas.AuctionCreateListingRequest(character_id=1, storage_id=storage.id,
                                                    start_price=100, buyout_price=500), user_id=1,
        )
        listing = db.query(models.AuctionListing).get(result["listing_id"])
        assert listing.location_id == location
        assert listing.region_id == region

        _buyout(db, listing.id, 2)
        expected = AccountRef.region(region) if region else AccountRef.world()
        assert ("auction_escrow", 0, expected.kind, expected.ref_id, 25, "commission") in _legs(db, "auction_buyout")
        assert len([leg for leg in _legs(db, "auction_buyout") if leg[5] == "tax"]) == (1 if region else 0)
        _check(db)

    @pytest.mark.parametrize("start,buyout", [(0, 500), (-5, 500), (100, 100), (100, 50), (100, -1)])
    def test_invalid_prices_rejected(self, env, start, buyout):
        db = env
        _seed_auction(db)
        storage = models.AuctionStorage(character_id=1, item_id=201, quantity=1, gold_amount=0, source="deposit")
        db.add(storage)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            crud.create_auction_listing(
                db, schemas.AuctionCreateListingRequest(character_id=1, storage_id=storage.id,
                                                        start_price=start, buyout_price=buyout), user_id=1,
            )
        assert exc.value.status_code == 400
        assert db.query(models.AuctionListing).count() == 0

    def test_cannot_list_from_foreign_storage(self, env):
        db = env
        _seed_auction(db)
        storage = models.AuctionStorage(character_id=2, item_id=201, quantity=1, gold_amount=0, source="deposit")
        db.add(storage)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            crud.create_auction_listing(
                db, schemas.AuctionCreateListingRequest(character_id=1, storage_id=storage.id,
                                                        start_price=100, buyout_price=500), user_id=1,
            )
        assert exc.value.status_code == 400
        assert db.query(models.AuctionStorage).get(storage.id) is not None


# ═══════════════════════════════════════════════════════════════════════════
# Expiry, cancel, claim
# ═══════════════════════════════════════════════════════════════════════════


class TestSettlementCancelClaim:

    def test_expiry_without_bids_moves_no_money(self, env):
        db = env
        _seed_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=1000, region_id=10)
        db.commit()
        assert _expire(db, listing) == 1
        db.refresh(listing)
        assert listing.status == "expired"
        assert db.execute(text("SELECT COUNT(*) FROM econ_operations WHERE op_type LIKE 'auction%'")).scalar() == 0
        assert _storage_ids(db, 1, "expired")
        _check(db)

    def test_expiry_runs_once(self, env):
        db = env
        _seed_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=1000, region_id=10)
        db.commit()
        _bid(db, listing.id, 2, 300)
        assert _expire(db, listing) == 1
        assert crud.expire_stale_listings(db) == 0
        assert _op_count(db, "auction_settlement") == 1
        assert _account(db, AccountRef.storage()) == 285
        assert _account(db, AccountRef.region(10)) == 14  # 15 commission - 1 tax
        op = db.execute(text(
            "SELECT idempotency_key FROM econ_operations WHERE op_type = 'auction_settlement'"
        )).scalar()
        assert op == f"auction_settlement:listing:{listing.id}"
        _check(db)

    def test_expired_legacy_listing_commission_to_world(self, env):
        db = env
        _seed_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=1000)
        db.commit()
        _bid(db, listing.id, 2, 400)
        _expire(db, listing)
        assert ("auction_escrow", 0, "world_treasury", 0, 20, "commission") in _legs(db, "auction_settlement")
        assert _account(db, AccountRef.world()) == 20
        _check(db)

    def test_cancel_without_bids_moves_no_money(self, env):
        db = env
        _seed_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=1000)
        db.commit()
        crud.cancel_listing(db, listing.id, schemas.AuctionCancelRequest(character_id=1), user_id=1)
        assert _op_count(db, "auction_refund") == 0
        _check(db)

    def test_cancel_twice_refunds_once(self, env):
        db = env
        _seed_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=1000)
        db.commit()
        _bid(db, listing.id, 2, 200)
        crud.cancel_listing(db, listing.id, schemas.AuctionCancelRequest(character_id=1), user_id=1)
        with pytest.raises(HTTPException) as exc:
            crud.cancel_listing(db, listing.id, schemas.AuctionCancelRequest(character_id=1), user_id=1)
        assert exc.value.status_code == 400
        assert _op_count(db, "auction_refund") == 1
        assert _balance(db, 2) == 3000
        _check(db)

    def test_cancel_by_non_seller_forbidden(self, env):
        db = env
        _seed_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=1000)
        db.commit()
        _bid(db, listing.id, 2, 200)
        with pytest.raises(HTTPException) as exc:
            crud.cancel_listing(db, listing.id, schemas.AuctionCancelRequest(character_id=2), user_id=2)
        assert exc.value.status_code == 403
        assert _account(db, AccountRef.escrow()) == 200
        _check(db)

    def test_double_claim_pays_once(self, env):
        db = env
        _seed_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=1000, region_id=10)
        db.commit()
        _buyout(db, listing.id, 2)
        ids = _storage_ids(db, 1, "sale_proceeds")

        assert _claim(db, 1, ids)["claimed_gold"] == 950
        with pytest.raises(HTTPException) as exc:
            _claim(db, 1, ids)
        assert exc.value.status_code == 404

        assert _op_count(db, "auction_claim") == 1
        assert _balance(db, 1) == 5950
        assert _account(db, AccountRef.storage()) == 0
        _check(db)

    def test_claim_several_entries_one_operation(self, env):
        db = env
        _seed_auction(db)
        a = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=1000, region_id=10)
        b = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=300, region_id=10)
        db.commit()
        _buyout(db, a.id, 2)
        _buyout(db, b.id, 3)
        # Buyer's item entries + seller's two proceeds entries
        ids = _storage_ids(db, 1, "sale_proceeds")
        assert len(ids) == 2
        result = _claim(db, 1, ids)
        assert result["claimed_gold"] == 950 + 285
        assert _legs(db, "auction_claim") == [("auction_storage", 0, "character", 1, 1235, "main")]
        _check(db)

    def test_claim_foreign_storage_ids_pays_nothing(self, env):
        db = env
        _seed_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=1000)
        db.commit()
        _buyout(db, listing.id, 2)
        seller_ids = _storage_ids(db, 1, "sale_proceeds")

        # Bidder 2 asks for the seller's proceeds with their own character
        with pytest.raises(HTTPException) as exc:
            _claim(db, 2, seller_ids)
        assert exc.value.status_code == 404
        # ...or with the seller's character but their own user
        with pytest.raises(HTTPException) as exc:
            crud.claim_from_storage(db, schemas.AuctionClaimRequest(character_id=1, storage_ids=seller_ids),
                                    user_id=2)
        assert exc.value.status_code == 403
        assert _op_count(db, "auction_claim") == 0
        assert _account(db, AccountRef.storage()) == 950
        _check(db)

    def test_claim_items_only_posts_nothing(self, env):
        db = env
        _seed_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=1000)
        db.commit()
        _buyout(db, listing.id, 2)
        result = _claim(db, 2, _storage_ids(db, 2, "purchase"))
        assert result["claimed_gold"] == 0 and result["claimed_items"] == 1
        assert _op_count(db, "auction_claim") == 0
        _check(db)


# ═══════════════════════════════════════════════════════════════════════════
# Long scenario: invariant after every step
# ═══════════════════════════════════════════════════════════════════════════


def test_multi_listing_scenario_invariant_after_every_step(env):
    db = env
    _seed_auction(db)
    a = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=2000, region_id=10)
    b = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=2000, region_id=10)
    c = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=2000)
    d = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=2000, region_id=10)
    db.commit()
    _check(db)

    steps = [
        lambda: _bid(db, a.id, 2, 200),
        lambda: _bid(db, b.id, 3, 300),
        lambda: _bid(db, c.id, 2, 150),
        lambda: _bid(db, d.id, 3, 500),
        lambda: _bid(db, a.id, 3, 250),           # outbid on A
        lambda: _buyout(db, a.id, 2),             # A bought out, 3 refunded
        lambda: _expire(db, b),                   # B settles to 3
        lambda: crud.cancel_listing(db, c.id, schemas.AuctionCancelRequest(character_id=1), user_id=1),
        lambda: _claim(db, 1, _storage_ids(db, 1, "sale_proceeds")),
        lambda: _claim(db, 2, _storage_ids(db, 2)),
        lambda: _claim(db, 3, _storage_ids(db, 3)),
    ]
    for step in steps:
        step()
        _check(db)

    # Only D is still live, holding 500 in escrow
    assert _account(db, AccountRef.escrow()) == 500
    assert _account(db, AccountRef.storage()) == 0
    # A: 2000 -> 100 commission (10 tax); B: 300 -> 15 commission (1 tax); C cancelled
    assert _account(db, AccountRef.region(10)) == 90 + 14
    assert _account(db, AccountRef.country(1)) == 11
    assert _balance(db, 1) == 5000 + 1900 + 285
    assert _balance(db, 2) == 3000 - 2000
    assert _balance(db, 3) == 4000 - 300 - 500


# ═══════════════════════════════════════════════════════════════════════════
# Auction endpoints: auth / ownership
# ═══════════════════════════════════════════════════════════════════════════


class TestAuctionEndpointSecurity:

    def _listing(self, db):
        _seed_auction(db)
        listing = _create_listing(db, seller_id=1, item_id=201, start_price=100, buyout_price=1000, region_id=10)
        db.commit()
        return listing

    def test_no_token_401_everywhere(self, api, env):
        listing = self._listing(env)
        app.dependency_overrides.pop(get_current_user_via_http, None)
        assert api.post(f"/inventory/auction/listings/{listing.id}/bid",
                        json={"character_id": 2, "amount": 200}).status_code == 401
        assert api.post(f"/inventory/auction/listings/{listing.id}/buyout",
                        json={"character_id": 2}).status_code == 401
        assert api.post(f"/inventory/auction/listings/{listing.id}/cancel",
                        json={"character_id": 1}).status_code == 401
        assert api.post("/inventory/auction/storage/claim",
                        json={"character_id": 1, "storage_ids": [1]}).status_code == 401
        assert db_ops(env) == 0

    def test_foreign_character_403(self, api, env):
        listing = self._listing(env)
        _as_user(3)  # owns character 3 only
        assert api.post(f"/inventory/auction/listings/{listing.id}/bid",
                        json={"character_id": 2, "amount": 200}).status_code == 403
        assert api.post(f"/inventory/auction/listings/{listing.id}/buyout",
                        json={"character_id": 2}).status_code == 403
        assert api.post(f"/inventory/auction/listings/{listing.id}/cancel",
                        json={"character_id": 1}).status_code == 403
        assert api.post("/inventory/auction/storage/claim",
                        json={"character_id": 1, "storage_ids": [1]}).status_code == 403
        assert _balance(env, 2) == 3000
        assert db_ops(env) == 0
        _check(env)

    def test_seller_cannot_bid_or_buy_own_listing(self, api, env):
        listing = self._listing(env)
        _as_user(1)
        assert api.post(f"/inventory/auction/listings/{listing.id}/bid",
                        json={"character_id": 1, "amount": 200}).status_code == 400
        assert api.post(f"/inventory/auction/listings/{listing.id}/buyout",
                        json={"character_id": 1}).status_code == 400
        assert db_ops(env) == 0

    def test_bid_and_buyout_through_endpoints(self, api, env):
        listing = self._listing(env)
        _as_user(2)
        r = api.post(f"/inventory/auction/listings/{listing.id}/bid", json={"character_id": 2, "amount": 200})
        assert r.status_code == 200, r.text
        assert r.json()["new_gold_balance"] == 2800
        _as_user(3)
        r = api.post(f"/inventory/auction/listings/{listing.id}/buyout", json={"character_id": 3})
        assert r.status_code == 200, r.text
        assert r.json()["new_gold_balance"] == 3000
        assert _balance(env, 2) == 3000
        _check(env)

    @pytest.mark.parametrize("amount", ["abc", 1.5, None])
    def test_malformed_amount_422(self, api, env, amount):
        listing = self._listing(env)
        _as_user(2)
        r = api.post(f"/inventory/auction/listings/{listing.id}/bid", json={"character_id": 2, "amount": amount})
        # Pydantic v1 coerces 1.5 -> 1 (below start price -> 400); garbage -> 422
        assert r.status_code in (400, 422)
        assert _balance(env, 2) == 3000
        assert db_ops(env) == 0


def db_ops(db):
    """Operations other than the test's own funding (admin_emission)."""
    return db.execute(text("SELECT COUNT(*) FROM econ_operations WHERE op_type <> 'admin_emission'")).scalar()


class TestAuctionPriceCap:
    """Auction price columns are INT: oversized prices are rejected by the request schemas."""

    def test_bid_above_int_is_rejected(self):
        import schemas
        with pytest.raises(Exception):
            schemas.AuctionBidRequest(character_id=1, amount=schemas.AUCTION_MAX_PRICE + 1)
        assert schemas.AuctionBidRequest(character_id=1, amount=schemas.AUCTION_MAX_PRICE).amount == schemas.AUCTION_MAX_PRICE

    def test_listing_prices_above_int_are_rejected(self):
        import schemas
        with pytest.raises(Exception):
            schemas.AuctionCreateListingRequest(character_id=1, storage_id=1, start_price=schemas.AUCTION_MAX_PRICE + 1)
        with pytest.raises(Exception):
            schemas.AuctionCreateListingRequest(character_id=1, storage_id=1, start_price=10,
                                                buyout_price=schemas.AUCTION_MAX_PRICE + 1)
